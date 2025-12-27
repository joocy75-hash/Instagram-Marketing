"""
Kill Switch - 자동 광고 중단 시스템
=====================================
실시간 성과 모니터링 -> 저성과 광고 자동 중단 -> 고성과 광고 예산 증액

4단계 성과 판정 로직:
- Level 1: 노출 500회 + 클릭 0 -> 중단
- Level 2: 노출 1000회 + CTR < 0.5% -> 중단
- Level 3: 지출 5000원 + CPC > 500원 -> 중단
- Level 4: 지출 10000원 + ROAS < 2.0 -> 중단
- 승자: CTR >= 1.5% + ROAS >= 4.0 -> 예산 50% 증액

사용법:
    kill_switch = KillSwitch()
    kill_switch.monitor_all_ads()          # 1회 체크
    kill_switch.run_monitoring_loop()       # 지속 모니터링 (30분 간격)
"""

import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.exceptions import FacebookRequestError

from config.meta_credentials import init_facebook_sdk
from config.constants import KillSwitchThresholds
from utils.logger import get_logger
from utils.slack_notifier import get_notifier


logger = get_logger(__name__)


class KillSwitch:
    """
    광고 자동 중단/증액 시스템 (Kill Switch)

    실시간으로 광고 성과를 모니터링하여:
    - 저성과 광고를 자동으로 중단
    - 고성과 광고의 예산을 자동으로 증액
    """

    def __init__(self):
        """KillSwitch 초기화 - SDK 및 계정 설정"""
        # SDK 초기화 및 인증 정보 로드
        self.credentials = init_facebook_sdk()
        self.ad_account = AdAccount(self.credentials.ad_account_id)

        # 임계값 설정
        self.thresholds = KillSwitchThresholds

        # Slack 알림
        self.notifier = get_notifier()

        logger.info(f"KillSwitch 초기화 완료 - 계정: {self.credentials.ad_account_id}")

    # ============================================================
    # 1. get_active_ads() - 활성 광고 조회
    # ============================================================

    def get_active_ads(self) -> List[Dict]:
        """
        현재 활성(ACTIVE) 상태인 모든 광고 조회

        Returns:
            List[Dict]: 활성 광고 정보 리스트
                - id: 광고 ID
                - name: 광고 이름
                - adset_id: AdSet ID
                - campaign_id: 캠페인 ID
                - status: 상태
                - effective_status: 유효 상태
        """
        try:
            ads = self.ad_account.get_ads(
                fields=[
                    Ad.Field.id,
                    Ad.Field.name,
                    Ad.Field.adset_id,
                    Ad.Field.campaign_id,
                    Ad.Field.status,
                    Ad.Field.effective_status,
                ],
                params={
                    "effective_status": ["ACTIVE"],
                }
            )

            result = []
            for ad in ads:
                result.append({
                    "id": ad.get("id"),
                    "name": ad.get("name"),
                    "adset_id": ad.get("adset_id"),
                    "campaign_id": ad.get("campaign_id"),
                    "status": ad.get("status"),
                    "effective_status": ad.get("effective_status"),
                })

            logger.info(f"활성 광고 {len(result)}개 조회 완료")
            return result

        except FacebookRequestError as e:
            logger.error(f"활성 광고 조회 실패: {e.api_error_message()}")
            self.notifier.notify_error(
                error_msg=str(e.api_error_message()),
                context="get_active_ads"
            )
            return []
        except Exception as e:
            logger.error(f"활성 광고 조회 중 예외 발생: {e}")
            self.notifier.notify_error(error_msg=str(e), context="get_active_ads")
            return []

    # ============================================================
    # 2. get_ad_insights() - 광고 성과 지표 조회
    # ============================================================

    def get_ad_insights(self, ad_id: str, use_today: bool = True) -> Dict:
        """
        광고 성과 지표 조회

        Args:
            ad_id: 광고 ID
            use_today: True면 date_preset='today', False면 최근 7일

        Returns:
            Dict: 광고 성과 지표
                - impressions: 노출 수
                - clicks: 클릭 수
                - spend: 지출액 (원)
                - ctr: 클릭률 (%)
                - cpc: 클릭당 비용 (원)
                - conversions: 전환 수
                - revenue: 매출액 (원)
                - roas: 광고 수익률
                - actions: 액션 데이터 (raw)
        """
        try:
            ad = Ad(ad_id)

            # 조회 기간 설정
            if use_today:
                params = {
                    "date_preset": "today",
                }
            else:
                # 최근 7일
                since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
                until = datetime.now().strftime("%Y-%m-%d")
                params = {
                    "time_range": {"since": since, "until": until},
                }

            # Insights 조회
            insights = ad.get_insights(
                fields=[
                    "impressions",
                    "clicks",
                    "spend",
                    "ctr",
                    "cpc",
                    "actions",
                    "action_values",
                    "cost_per_action_type",
                ],
                params=params,
            )

            if not insights:
                logger.debug(f"광고 {ad_id}: 인사이트 데이터 없음")
                return self._empty_insights()

            insight = insights[0]

            # 기본 지표 추출
            impressions = int(insight.get("impressions", 0))
            clicks = int(insight.get("clicks", 0))
            spend = float(insight.get("spend", 0))
            ctr = float(insight.get("ctr", 0))
            cpc = float(insight.get("cpc", 0)) if insight.get("cpc") else 0

            # 전환 데이터 추출
            actions = insight.get("actions", [])
            conversions = 0
            for action in actions:
                action_type = action.get("action_type", "")
                if action_type in ["purchase", "lead", "complete_registration", "omni_purchase"]:
                    conversions += int(action.get("value", 0))

            # 매출 데이터 추출
            action_values = insight.get("action_values", [])
            revenue = 0.0
            for av in action_values:
                action_type = av.get("action_type", "")
                if action_type in ["purchase", "omni_purchase"]:
                    revenue += float(av.get("value", 0))

            # ROAS 계산
            roas = (revenue / spend) if spend > 0 else 0.0

            return {
                "impressions": impressions,
                "clicks": clicks,
                "spend": spend,
                "ctr": ctr,
                "cpc": cpc,
                "conversions": conversions,
                "revenue": revenue,
                "roas": roas,
                "actions": actions,
            }

        except FacebookRequestError as e:
            logger.error(f"광고 {ad_id} 인사이트 조회 실패: {e.api_error_message()}")
            return self._empty_insights()
        except Exception as e:
            logger.error(f"광고 {ad_id} 인사이트 조회 중 예외: {e}")
            return self._empty_insights()

    def _empty_insights(self) -> Dict:
        """빈 인사이트 데이터 반환"""
        return {
            "impressions": 0,
            "clicks": 0,
            "spend": 0.0,
            "ctr": 0.0,
            "cpc": 0.0,
            "conversions": 0,
            "revenue": 0.0,
            "roas": 0.0,
            "actions": [],
        }

    # ============================================================
    # 3. check_ad_performance() - 4단계 성과 판정
    # ============================================================

    def check_ad_performance(self, ad_id: str) -> Tuple[str, Optional[str]]:
        """
        광고 성과 판정 (4단계 로직)

        판정 순서:
        1. Level 1: 노출 500회 + 클릭 0 -> ("kill", "노출 500회 클릭 0")
        2. Level 2: 노출 1000회 + CTR < 0.5% -> ("kill", "CTR 부족")
        3. Level 3: 지출 5000원 + CPC > 500원 -> ("kill", "CPC 초과")
        4. Level 4: 지출 10000원 + ROAS < 2.0 -> ("kill", "ROAS 부족")
        5. 승자: CTR >= 1.5% + ROAS >= 4.0 -> ("scale", None)
        6. 그 외: ("keep", None)

        Args:
            ad_id: 광고 ID

        Returns:
            Tuple[str, Optional[str]]: (판정 결과, 사유)
                - 판정 결과: "kill", "scale", "keep"
                - 사유: 중단 사유 (kill인 경우만) 또는 None
        """
        # 성과 지표 조회
        insights = self.get_ad_insights(ad_id, use_today=True)

        impressions = insights["impressions"]
        clicks = insights["clicks"]
        spend = insights["spend"]
        ctr = insights["ctr"]
        cpc = insights["cpc"]
        roas = insights["roas"]

        th = self.thresholds

        # Level 1: 노출 500회 이상 + 클릭 0
        if impressions >= th.MIN_IMPRESSIONS_FOR_CHECK and clicks == 0:
            logger.info(f"광고 {ad_id}: Level 1 - 노출 {impressions}회, 클릭 0 -> KILL")
            return ("kill", "노출 500회 클릭 0")

        # Level 2: 노출 1000회 이상 + CTR < 0.5%
        if impressions >= th.CTR_CHECK_IMPRESSIONS and ctr < th.MIN_CTR_PERCENT:
            logger.info(f"광고 {ad_id}: Level 2 - 노출 {impressions}회, CTR {ctr:.2f}% -> KILL")
            return ("kill", "CTR 부족")

        # Level 3: 지출 5000원 이상 + CPC > 500원
        if spend >= th.CPC_CHECK_SPEND and cpc > th.MAX_CPC:
            logger.info(f"광고 {ad_id}: Level 3 - 지출 {spend:.0f}원, CPC {cpc:.0f}원 -> KILL")
            return ("kill", "CPC 초과")

        # Level 4: 지출 10000원 이상 + ROAS < 2.0
        if spend >= th.ROAS_CHECK_SPEND and roas < th.MIN_ROAS:
            logger.info(f"광고 {ad_id}: Level 4 - 지출 {spend:.0f}원, ROAS {roas:.2f} -> KILL")
            return ("kill", "ROAS 부족")

        # 승자: CTR >= 1.5% + ROAS >= 4.0
        if ctr >= th.WINNER_MIN_CTR and roas >= th.WINNER_MIN_ROAS:
            logger.info(f"광고 {ad_id}: 승자 - CTR {ctr:.2f}%, ROAS {roas:.2f} -> SCALE")
            return ("scale", None)

        # 그 외: 유지
        logger.debug(f"광고 {ad_id}: 유지 - CTR {ctr:.2f}%, ROAS {roas:.2f}")
        return ("keep", None)

    # ============================================================
    # 4. pause_ad() - 광고 중단
    # ============================================================

    def pause_ad(self, ad_id: str, reason: str) -> bool:
        """
        광고 상태를 PAUSED로 변경

        Args:
            ad_id: 광고 ID
            reason: 중단 사유

        Returns:
            bool: 성공 여부
        """
        try:
            ad = Ad(ad_id)

            # 광고 상태 변경
            ad.api_update(params={
                Ad.Field.status: Ad.Status.paused,
            })

            logger.warning(f"광고 중단: {ad_id} (사유: {reason})")

            # Slack 알림
            self.notifier.notify_ad_paused(ad_id, reason)

            return True

        except FacebookRequestError as e:
            logger.error(f"광고 {ad_id} 중단 실패: {e.api_error_message()}")
            self.notifier.notify_error(
                error_msg=f"광고 중단 실패: {e.api_error_message()}",
                context=f"pause_ad({ad_id})"
            )
            return False
        except Exception as e:
            logger.error(f"광고 {ad_id} 중단 중 예외: {e}")
            self.notifier.notify_error(
                error_msg=str(e),
                context=f"pause_ad({ad_id})"
            )
            return False

    # ============================================================
    # 5. scale_up_winner() - 고성과 광고 예산 증액
    # ============================================================

    def scale_up_winner(self, ad_id: str) -> bool:
        """
        고성과 광고의 AdSet 예산 50% 증액

        Args:
            ad_id: 광고 ID

        Returns:
            bool: 성공 여부
        """
        try:
            # 광고에서 AdSet ID 조회
            ad = Ad(ad_id)
            ad_data = ad.api_get(fields=[Ad.Field.adset_id, Ad.Field.name])
            adset_id = ad_data.get("adset_id")
            ad_name = ad_data.get("name", ad_id)

            if not adset_id:
                logger.error(f"광고 {ad_id}의 AdSet ID를 찾을 수 없음")
                return False

            # AdSet 현재 예산 조회
            adset = AdSet(adset_id)
            adset_data = adset.api_get(fields=[
                AdSet.Field.daily_budget,
                AdSet.Field.lifetime_budget,
                AdSet.Field.name,
            ])

            # daily_budget 또는 lifetime_budget 확인
            current_budget = int(adset_data.get("daily_budget", 0))
            budget_type = "daily_budget"

            if current_budget == 0:
                current_budget = int(adset_data.get("lifetime_budget", 0))
                budget_type = "lifetime_budget"

            if current_budget == 0:
                logger.warning(f"AdSet {adset_id}의 예산 정보가 없음")
                return False

            # 50% 증액 (Meta API는 센트 단위이므로 100 나누기/곱하기 필요할 수 있음)
            # KRW의 경우 소수점 없이 원 단위
            new_budget = int(current_budget * self.thresholds.WINNER_BUDGET_INCREASE_RATE)

            # 예산 업데이트
            update_params = {budget_type: str(new_budget)}
            adset.api_update(params=update_params)

            logger.info(
                f"예산 증액 완료: 광고 '{ad_name}' ({ad_id})\n"
                f"  AdSet: {adset_id}\n"
                f"  기존 예산: {current_budget:,}원 -> 신규 예산: {new_budget:,}원 (+50%)"
            )

            # Slack 알림
            self.notifier.notify_ad_scaled(ad_id, current_budget, new_budget)

            return True

        except FacebookRequestError as e:
            logger.error(f"광고 {ad_id} 예산 증액 실패: {e.api_error_message()}")
            self.notifier.notify_error(
                error_msg=f"예산 증액 실패: {e.api_error_message()}",
                context=f"scale_up_winner({ad_id})"
            )
            return False
        except Exception as e:
            logger.error(f"광고 {ad_id} 예산 증액 중 예외: {e}")
            self.notifier.notify_error(
                error_msg=str(e),
                context=f"scale_up_winner({ad_id})"
            )
            return False

    # ============================================================
    # 6. monitor_all_ads() - 전체 광고 모니터링
    # ============================================================

    def monitor_all_ads(self) -> Dict[str, int]:
        """
        모든 활성 광고 순회하며 성과 판정 후 액션 수행

        Returns:
            Dict[str, int]: 처리 결과 통계
                - total: 총 광고 수
                - kept: 유지된 광고 수
                - paused: 중단된 광고 수
                - scaled: 증액된 광고 수
                - errors: 에러 발생 수
        """
        logger.info("=" * 60)
        logger.info("Kill Switch 모니터링 시작")
        logger.info(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)

        # 활성 광고 조회
        active_ads = self.get_active_ads()

        stats = {
            "total": len(active_ads),
            "kept": 0,
            "paused": 0,
            "scaled": 0,
            "errors": 0,
        }

        if not active_ads:
            logger.info("활성 광고가 없습니다.")
            return stats

        logger.info(f"활성 광고 {len(active_ads)}개 발견")
        logger.info("-" * 40)

        # 각 광고 성과 판정 및 액션 수행
        for ad in active_ads:
            ad_id = ad["id"]
            ad_name = ad.get("name", "Unknown")

            try:
                # 성과 판정
                action, reason = self.check_ad_performance(ad_id)

                if action == "kill":
                    # 광고 중단
                    success = self.pause_ad(ad_id, reason)
                    if success:
                        stats["paused"] += 1
                        logger.warning(f"  [{ad_name}] 중단됨 - 사유: {reason}")
                    else:
                        stats["errors"] += 1

                elif action == "scale":
                    # 예산 증액
                    success = self.scale_up_winner(ad_id)
                    if success:
                        stats["scaled"] += 1
                        logger.info(f"  [{ad_name}] 예산 증액됨")
                    else:
                        stats["errors"] += 1

                else:  # "keep"
                    stats["kept"] += 1
                    logger.debug(f"  [{ad_name}] 유지")

            except Exception as e:
                stats["errors"] += 1
                logger.error(f"  [{ad_name}] 처리 중 에러: {e}")

        # 결과 요약
        logger.info("-" * 40)
        logger.info("모니터링 완료 - 결과 요약:")
        logger.info(f"  총 광고: {stats['total']}개")
        logger.info(f"  유지: {stats['kept']}개")
        logger.info(f"  중단: {stats['paused']}개")
        logger.info(f"  증액: {stats['scaled']}개")
        logger.info(f"  에러: {stats['errors']}개")
        logger.info("=" * 60)

        return stats

    # ============================================================
    # 7. run_monitoring_loop() - 지속 모니터링 루프
    # ============================================================

    def run_monitoring_loop(self, interval_seconds: int = 1800) -> None:
        """
        30분마다 모니터링 실행 (무한 루프)

        Args:
            interval_seconds: 모니터링 간격 (초), 기본값 1800 (30분)
        """
        logger.info("=" * 60)
        logger.info("Kill Switch 모니터링 루프 시작")
        logger.info(f"모니터링 간격: {interval_seconds}초 ({interval_seconds // 60}분)")
        logger.info("=" * 60)

        # Slack 알림 - 모니터링 시작
        self.notifier.send(
            message="Kill Switch 모니터링이 시작되었습니다.",
            title="Kill Switch 시작",
            color="#2196f3",
            fields={
                "모니터링 간격": f"{interval_seconds // 60}분",
                "계정 ID": self.credentials.ad_account_id,
            }
        )

        try:
            while True:
                # 모니터링 실행
                stats = self.monitor_all_ads()

                # 다음 실행까지 대기
                next_run = datetime.now() + timedelta(seconds=interval_seconds)
                logger.info(
                    f"다음 모니터링: {next_run.strftime('%H:%M:%S')} "
                    f"(처리: {stats['total']}개)"
                )
                logger.info("")

                time.sleep(interval_seconds)

        except KeyboardInterrupt:
            logger.info("사용자에 의해 모니터링 중단됨")
            self.notifier.send(
                message="Kill Switch 모니터링이 중단되었습니다.",
                title="Kill Switch 중단",
                color="#ff9800",
            )
        except Exception as e:
            logger.error(f"모니터링 루프 에러: {e}")
            self.notifier.notify_error(
                error_msg=str(e),
                context="run_monitoring_loop"
            )
            raise

    # ============================================================
    # 유틸리티 메서드
    # ============================================================

    def get_performance_summary(self, ad_id: str) -> Dict:
        """
        광고 성과 요약 조회 (디버깅/리포트용)

        Args:
            ad_id: 광고 ID

        Returns:
            Dict: 성과 요약 정보
        """
        insights = self.get_ad_insights(ad_id, use_today=True)
        action, reason = self.check_ad_performance(ad_id)

        return {
            "ad_id": ad_id,
            "impressions": insights["impressions"],
            "clicks": insights["clicks"],
            "spend": insights["spend"],
            "ctr": round(insights["ctr"], 2),
            "cpc": round(insights["cpc"], 0),
            "conversions": insights["conversions"],
            "revenue": insights["revenue"],
            "roas": round(insights["roas"], 2),
            "action": action,
            "reason": reason,
        }

    def get_all_performance_report(self) -> List[Dict]:
        """
        모든 활성 광고의 성과 리포트

        Returns:
            List[Dict]: 광고별 성과 리포트
        """
        active_ads = self.get_active_ads()
        report = []

        for ad in active_ads:
            summary = self.get_performance_summary(ad["id"])
            summary["name"] = ad.get("name", "Unknown")
            report.append(summary)

        return report


# ============================================================
# CLI 지원
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Kill Switch - Instagram 광고 자동 중단/증액 시스템"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="1회만 모니터링 실행"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=1800,
        help="모니터링 간격 (초, 기본값: 1800)"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="성과 리포트만 출력 (액션 없음)"
    )
    parser.add_argument(
        "--check",
        type=str,
        metavar="AD_ID",
        help="특정 광고 성과 판정 확인"
    )

    args = parser.parse_args()

    # KillSwitch 초기화
    kill_switch = KillSwitch()

    if args.report:
        # 성과 리포트 출력
        print("\n=== 활성 광고 성과 리포트 ===\n")
        report = kill_switch.get_all_performance_report()

        for item in report:
            print(f"광고: {item['name']} ({item['ad_id']})")
            print(f"  노출: {item['impressions']:,}  클릭: {item['clicks']:,}")
            print(f"  CTR: {item['ctr']}%  CPC: {item['cpc']:,.0f}원")
            print(f"  지출: {item['spend']:,.0f}원  매출: {item['revenue']:,.0f}원")
            print(f"  ROAS: {item['roas']}  전환: {item['conversions']}")
            print(f"  판정: {item['action'].upper()}", end="")
            if item['reason']:
                print(f" ({item['reason']})")
            else:
                print()
            print()

    elif args.check:
        # 단일 광고 판정 확인
        summary = kill_switch.get_performance_summary(args.check)
        print(f"\n광고 ID: {args.check}")
        print(f"노출: {summary['impressions']:,}  클릭: {summary['clicks']:,}")
        print(f"CTR: {summary['ctr']}%  CPC: {summary['cpc']:,.0f}원")
        print(f"ROAS: {summary['roas']}")
        print(f"판정: {summary['action'].upper()}", end="")
        if summary['reason']:
            print(f" (사유: {summary['reason']})")
        else:
            print()

    elif args.once:
        # 1회 모니터링
        stats = kill_switch.monitor_all_ads()
        print(f"\n결과: 유지 {stats['kept']} / 중단 {stats['paused']} / 증액 {stats['scaled']}")

    else:
        # 지속 모니터링
        kill_switch.run_monitoring_loop(interval_seconds=args.interval)
