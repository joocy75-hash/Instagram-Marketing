"""
CTA 버튼 관리자
=====================================
광고 CTA 버튼 자동 설정 및 최적화
카테고리별 최적 CTA 추천, A/B 테스트 지원
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from facebook_business.adobjects.adcreative import AdCreative
from facebook_business.adobjects.ad import Ad

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.meta_credentials import init_facebook_sdk, get_credentials
from config.constants import CtaType, CATEGORY_CTA_MAPPING
from utils.logger import get_logger


logger = get_logger("cta_manager")


@dataclass
class CtaPerformance:
    """CTA 성과 데이터"""

    cta_type: str
    impressions: int
    clicks: int
    conversions: int
    spend: float
    ctr: float  # Click Through Rate (%)
    cvr: float  # Conversion Rate (%)
    cpa: float  # Cost Per Action


class CtaManager:
    """
    CTA 버튼 관리자

    주요 기능:
    - 카테고리별 최적 CTA 추천
    - 광고 CTA 업데이트
    - CTA별 성과 분석
    - A/B 테스트 관리
    """

    def __init__(self):
        """CTA 관리자 초기화"""
        self.creds = init_facebook_sdk()
        self.ad_account_id = self.creds.ad_account_id
        logger.info(f"CtaManager 초기화 완료: {self.ad_account_id}")

    # ============================================================
    # CTA 추천
    # ============================================================

    def get_recommended_cta(self, category: str) -> CtaType:
        """
        카테고리별 권장 CTA 반환

        Args:
            category: 상품/서비스 카테고리 (의류, 교육, 앱 등)

        Returns:
            권장 CTA 타입
        """
        # 정확한 매칭 먼저 시도
        if category in CATEGORY_CTA_MAPPING:
            return CATEGORY_CTA_MAPPING[category]

        # 부분 매칭 시도
        category_lower = category.lower()
        for key, cta in CATEGORY_CTA_MAPPING.items():
            if key in category_lower or category_lower in key:
                logger.info(f"카테고리 '{category}' → CTA '{cta.value}' 추천")
                return cta

        # 기본값: LEARN_MORE
        logger.info(f"카테고리 '{category}' 매칭 없음 → LEARN_MORE 기본 적용")
        return CtaType.LEARN_MORE

    def get_all_cta_types(self) -> List[Dict[str, str]]:
        """
        사용 가능한 모든 CTA 타입 반환

        Returns:
            [{"value": "SHOP_NOW", "label": "지금 쇼핑하기"}, ...]
        """
        cta_labels = {
            "SHOP_NOW": "지금 쇼핑하기",
            "LEARN_MORE": "더 알아보기",
            "SIGN_UP": "가입하기",
            "BOOK_TRAVEL": "예약하기",
            "CONTACT_US": "문의하기",
            "DOWNLOAD": "다운로드",
            "GET_OFFER": "혜택 받기",
            "GET_QUOTE": "견적 받기",
            "WATCH_MORE": "더 보기",
            "APPLY_NOW": "지금 신청",
            "SUBSCRIBE": "구독하기",
        }

        return [
            {"value": cta.value, "label": cta_labels.get(cta.value, cta.value)}
            for cta in CtaType
        ]

    # ============================================================
    # CTA 업데이트
    # ============================================================

    def update_ad_cta(self, ad_id: str, new_cta: str) -> bool:
        """
        광고의 CTA 버튼 변경

        Args:
            ad_id: 광고 ID
            new_cta: 새 CTA 타입 (SHOP_NOW, LEARN_MORE 등)

        Returns:
            성공 여부

        Note:
            Meta API는 크리에이티브 수정 대신 새 크리에이티브 생성을 권장합니다.
            이 메서드는 새 크리에이티브를 생성하고 광고에 연결합니다.
        """
        try:
            # 1. 기존 광고 정보 조회
            ad = Ad(ad_id)
            ad_info = ad.api_get(fields=["creative", "name", "adset_id"])

            creative_id = ad_info.get("creative", {}).get("id")
            if not creative_id:
                logger.error(f"광고 {ad_id}의 크리에이티브를 찾을 수 없습니다")
                return False

            # 2. 기존 크리에이티브 정보 조회
            creative = AdCreative(creative_id)
            creative_info = creative.api_get(
                fields=[
                    "name",
                    "object_story_spec",
                    "image_hash",
                    "link_url",
                ]
            )

            # 3. object_story_spec에서 CTA 업데이트
            object_story_spec = creative_info.get("object_story_spec", {})

            # link_data 또는 video_data에서 CTA 수정
            if "link_data" in object_story_spec:
                object_story_spec["link_data"]["call_to_action"] = {
                    "type": new_cta,
                    "value": {"link": object_story_spec["link_data"].get("link", "")},
                }
            elif "video_data" in object_story_spec:
                object_story_spec["video_data"]["call_to_action"] = {
                    "type": new_cta,
                    "value": {
                        "link": object_story_spec["video_data"].get("link", "")
                    },
                }

            # 4. 새 크리에이티브 생성
            from facebook_business.adobjects.adaccount import AdAccount

            ad_account = AdAccount(self.ad_account_id)

            new_creative = ad_account.create_ad_creative(
                params={
                    "name": f"{creative_info.get('name', 'Creative')}_CTA_{new_cta}",
                    "object_story_spec": object_story_spec,
                }
            )

            new_creative_id = new_creative.get_id()
            logger.info(f"새 크리에이티브 생성: {new_creative_id}")

            # 5. 광고에 새 크리에이티브 연결
            ad.api_update(params={"creative": {"creative_id": new_creative_id}})

            logger.info(f"광고 {ad_id} CTA 변경 완료: {new_cta}")
            return True

        except Exception as e:
            logger.error(f"CTA 업데이트 실패: {e}")
            return False

    # ============================================================
    # CTA 성과 분석
    # ============================================================

    def analyze_cta_performance(
        self, campaign_id: Optional[str] = None, date_preset: str = "last_30d"
    ) -> List[CtaPerformance]:
        """
        CTA별 성과 분석

        Args:
            campaign_id: 특정 캠페인만 분석 (None이면 전체)
            date_preset: 기간 (today, yesterday, last_7d, last_30d 등)

        Returns:
            CTA별 성과 데이터 리스트
        """
        from facebook_business.adobjects.adaccount import AdAccount

        try:
            ad_account = AdAccount(self.ad_account_id)

            # 광고 조회 파라미터
            params = {
                "fields": [
                    "id",
                    "name",
                    "creative{id,call_to_action_type}",
                ],
                "filtering": [{"field": "effective_status", "operator": "IN", "value": ["ACTIVE", "PAUSED"]}],
            }

            if campaign_id:
                params["filtering"].append(
                    {"field": "campaign.id", "operator": "EQUAL", "value": campaign_id}
                )

            ads = ad_account.get_ads(params=params)

            # CTA별 성과 집계
            cta_stats: Dict[str, Dict] = {}

            for ad in ads:
                # CTA 타입 추출
                creative = ad.get("creative", {})
                cta_type = creative.get("call_to_action_type", "LEARN_MORE")

                # 인사이트 조회
                insights = Ad(ad["id"]).get_insights(
                    params={
                        "date_preset": date_preset,
                        "fields": [
                            "impressions",
                            "clicks",
                            "spend",
                            "actions",
                        ],
                    }
                )

                if not insights:
                    continue

                insight = insights[0] if insights else {}

                impressions = int(insight.get("impressions", 0))
                clicks = int(insight.get("clicks", 0))
                spend = float(insight.get("spend", 0))

                # 전환 수 추출 (purchase 또는 lead)
                conversions = 0
                actions = insight.get("actions", [])
                for action in actions:
                    if action.get("action_type") in ["purchase", "lead", "complete_registration"]:
                        conversions += int(action.get("value", 0))

                # 집계
                if cta_type not in cta_stats:
                    cta_stats[cta_type] = {
                        "impressions": 0,
                        "clicks": 0,
                        "conversions": 0,
                        "spend": 0,
                    }

                cta_stats[cta_type]["impressions"] += impressions
                cta_stats[cta_type]["clicks"] += clicks
                cta_stats[cta_type]["conversions"] += conversions
                cta_stats[cta_type]["spend"] += spend

            # CtaPerformance 객체로 변환
            results = []
            for cta_type, stats in cta_stats.items():
                impressions = stats["impressions"]
                clicks = stats["clicks"]
                conversions = stats["conversions"]
                spend = stats["spend"]

                ctr = (clicks / impressions * 100) if impressions > 0 else 0
                cvr = (conversions / clicks * 100) if clicks > 0 else 0
                cpa = (spend / conversions) if conversions > 0 else 0

                results.append(
                    CtaPerformance(
                        cta_type=cta_type,
                        impressions=impressions,
                        clicks=clicks,
                        conversions=conversions,
                        spend=spend,
                        ctr=round(ctr, 2),
                        cvr=round(cvr, 2),
                        cpa=round(cpa, 2),
                    )
                )

            # CTR 기준 정렬
            results.sort(key=lambda x: x.ctr, reverse=True)

            logger.info(f"CTA 성과 분석 완료: {len(results)}개 CTA 타입")
            return results

        except Exception as e:
            logger.error(f"CTA 성과 분석 실패: {e}")
            return []

    def get_best_performing_cta(
        self, campaign_id: Optional[str] = None
    ) -> Optional[str]:
        """
        가장 높은 CTR의 CTA 타입 반환

        Args:
            campaign_id: 특정 캠페인만 분석

        Returns:
            최고 성과 CTA 타입 또는 None
        """
        performances = self.analyze_cta_performance(campaign_id)

        if not performances:
            return None

        # 최소 노출 1000회 이상인 것 중에서 선택
        valid_performances = [p for p in performances if p.impressions >= 1000]

        if not valid_performances:
            return performances[0].cta_type if performances else None

        best = max(valid_performances, key=lambda x: x.ctr)
        logger.info(f"최고 성과 CTA: {best.cta_type} (CTR: {best.ctr}%)")
        return best.cta_type

    # ============================================================
    # CTA A/B 테스트
    # ============================================================

    def create_cta_ab_test(
        self,
        base_ad_id: str,
        test_ctas: List[str],
    ) -> List[str]:
        """
        동일 광고로 CTA만 다른 A/B 테스트 광고 생성

        Args:
            base_ad_id: 원본 광고 ID
            test_ctas: 테스트할 CTA 타입 목록

        Returns:
            생성된 테스트 광고 ID 목록
        """
        from facebook_business.adobjects.adaccount import AdAccount

        try:
            # 원본 광고 정보 조회
            base_ad = Ad(base_ad_id)
            base_info = base_ad.api_get(
                fields=["name", "adset_id", "creative"]
            )

            creative_id = base_info.get("creative", {}).get("id")
            adset_id = base_info.get("adset_id")
            base_name = base_info.get("name", "Ad")

            # 원본 크리에이티브 정보
            creative = AdCreative(creative_id)
            creative_info = creative.api_get(
                fields=["object_story_spec", "name"]
            )
            object_story_spec = creative_info.get("object_story_spec", {})

            ad_account = AdAccount(self.ad_account_id)
            created_ads = []

            for cta in test_ctas:
                # CTA 수정된 object_story_spec 복사
                new_spec = object_story_spec.copy()

                if "link_data" in new_spec:
                    new_spec["link_data"] = new_spec["link_data"].copy()
                    new_spec["link_data"]["call_to_action"] = {
                        "type": cta,
                        "value": {"link": new_spec["link_data"].get("link", "")},
                    }

                # 새 크리에이티브 생성
                new_creative = ad_account.create_ad_creative(
                    params={
                        "name": f"{creative_info.get('name', 'Creative')}_CTA_{cta}",
                        "object_story_spec": new_spec,
                    }
                )

                # 새 광고 생성
                new_ad = ad_account.create_ad(
                    params={
                        "name": f"{base_name}_AB_CTA_{cta}",
                        "adset_id": adset_id,
                        "creative": {"creative_id": new_creative.get_id()},
                        "status": "PAUSED",  # 검토 후 활성화
                    }
                )

                created_ads.append(new_ad.get_id())
                logger.info(f"A/B 테스트 광고 생성: CTA={cta}, ID={new_ad.get_id()}")

            logger.info(f"CTA A/B 테스트 생성 완료: {len(created_ads)}개 광고")
            return created_ads

        except Exception as e:
            logger.error(f"CTA A/B 테스트 생성 실패: {e}")
            return []

    def get_ab_test_results(
        self, ad_ids: List[str], date_preset: str = "last_7d"
    ) -> Dict[str, CtaPerformance]:
        """
        A/B 테스트 결과 조회

        Args:
            ad_ids: 테스트 광고 ID 목록
            date_preset: 분석 기간

        Returns:
            {ad_id: CtaPerformance} 딕셔너리
        """
        results = {}

        for ad_id in ad_ids:
            try:
                ad = Ad(ad_id)

                # 크리에이티브에서 CTA 타입 추출
                ad_info = ad.api_get(fields=["creative"])
                creative_id = ad_info.get("creative", {}).get("id")

                creative = AdCreative(creative_id)
                creative_info = creative.api_get(fields=["call_to_action_type"])
                cta_type = creative_info.get("call_to_action_type", "UNKNOWN")

                # 인사이트 조회
                insights = ad.get_insights(
                    params={
                        "date_preset": date_preset,
                        "fields": ["impressions", "clicks", "spend", "actions"],
                    }
                )

                if not insights:
                    continue

                insight = insights[0]
                impressions = int(insight.get("impressions", 0))
                clicks = int(insight.get("clicks", 0))
                spend = float(insight.get("spend", 0))

                conversions = 0
                for action in insight.get("actions", []):
                    if action.get("action_type") in ["purchase", "lead"]:
                        conversions += int(action.get("value", 0))

                ctr = (clicks / impressions * 100) if impressions > 0 else 0
                cvr = (conversions / clicks * 100) if clicks > 0 else 0
                cpa = (spend / conversions) if conversions > 0 else 0

                results[ad_id] = CtaPerformance(
                    cta_type=cta_type,
                    impressions=impressions,
                    clicks=clicks,
                    conversions=conversions,
                    spend=spend,
                    ctr=round(ctr, 2),
                    cvr=round(cvr, 2),
                    cpa=round(cpa, 2),
                )

            except Exception as e:
                logger.error(f"광고 {ad_id} 결과 조회 실패: {e}")

        return results

    def determine_ab_winner(
        self, ad_ids: List[str], metric: str = "ctr"
    ) -> Optional[Tuple[str, CtaPerformance]]:
        """
        A/B 테스트 승자 결정

        Args:
            ad_ids: 테스트 광고 ID 목록
            metric: 판정 기준 (ctr, cvr, cpa)

        Returns:
            (승자 광고 ID, 성과 데이터) 또는 None
        """
        results = self.get_ab_test_results(ad_ids)

        if not results:
            return None

        # 최소 노출 필터 (100회 이상)
        valid_results = {
            ad_id: perf
            for ad_id, perf in results.items()
            if perf.impressions >= 100
        }

        if not valid_results:
            logger.warning("충분한 노출을 가진 광고가 없습니다")
            return None

        # 메트릭별 승자 선정
        if metric == "ctr":
            winner_id = max(valid_results, key=lambda x: valid_results[x].ctr)
        elif metric == "cvr":
            winner_id = max(valid_results, key=lambda x: valid_results[x].cvr)
        elif metric == "cpa":
            # CPA는 낮을수록 좋음
            winner_id = min(valid_results, key=lambda x: valid_results[x].cpa or float("inf"))
        else:
            winner_id = max(valid_results, key=lambda x: valid_results[x].ctr)

        winner = valid_results[winner_id]
        logger.info(
            f"A/B 테스트 승자: {winner_id} (CTA: {winner.cta_type}, {metric}: {getattr(winner, metric)})"
        )

        return winner_id, winner


# 싱글톤 인스턴스
_manager: Optional[CtaManager] = None


def get_cta_manager() -> CtaManager:
    """전역 CTA 관리자 반환"""
    global _manager
    if _manager is None:
        _manager = CtaManager()
    return _manager
