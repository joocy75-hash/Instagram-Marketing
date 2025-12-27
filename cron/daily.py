"""
Daily Cron Job - 일일 성과 리포트
==================================
매일 오전 9시 실행되어 전날 Instagram 성과를 분석하고
Slack으로 리포트 발송

실행: python -m cron.daily
또는: python cron/daily.py

Crontab 설정 예시:
0 9 * * * cd /path/to/instagram-marketing && python -m cron.daily
"""

import sys
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.slack_notifier import get_notifier
from organic.insights_analyzer import InsightsAnalyzer, InsightPeriod


# 로거 설정
logger = get_logger("cron.daily")


class DailyReportGenerator:
    """
    일일 리포트 생성기

    어제 vs 그저께 성과 비교,
    베스트/워스트 게시물 선정,
    광고 성과 요약 등을 포함한 리포트 생성
    """

    def __init__(self):
        """초기화"""
        self.analyzer = InsightsAnalyzer()
        self.notifier = get_notifier()

        # 날짜 설정
        self.today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self.yesterday = self.today - timedelta(days=1)
        self.day_before = self.today - timedelta(days=2)

        logger.info("DailyReportGenerator 초기화 완료")

    def get_yesterday_insights(self) -> Dict[str, Any]:
        """
        어제 계정 인사이트 조회

        Returns:
            어제 인사이트 데이터
        """
        logger.info("어제 인사이트 조회")

        try:
            insights = self.analyzer.get_account_insights(
                period=InsightPeriod.DAY,
                since=self.yesterday,
                until=self.today
            )

            return {
                "impressions": insights.impressions,
                "reach": insights.reach,
                "profile_views": insights.profile_views,
                "website_clicks": insights.website_clicks,
                "follower_count": insights.follower_count,
            }

        except Exception as e:
            logger.error(f"어제 인사이트 조회 실패: {e}")
            return {
                "impressions": 0,
                "reach": 0,
                "profile_views": 0,
                "website_clicks": 0,
                "follower_count": 0,
            }

    def get_day_before_insights(self) -> Dict[str, Any]:
        """
        그저께 계정 인사이트 조회

        Returns:
            그저께 인사이트 데이터
        """
        logger.info("그저께 인사이트 조회")

        try:
            insights = self.analyzer.get_account_insights(
                period=InsightPeriod.DAY,
                since=self.day_before,
                until=self.yesterday
            )

            return {
                "impressions": insights.impressions,
                "reach": insights.reach,
                "profile_views": insights.profile_views,
                "website_clicks": insights.website_clicks,
                "follower_count": insights.follower_count,
            }

        except Exception as e:
            logger.error(f"그저께 인사이트 조회 실패: {e}")
            return {
                "impressions": 0,
                "reach": 0,
                "profile_views": 0,
                "website_clicks": 0,
                "follower_count": 0,
            }

    def calculate_change(self, current: int, previous: int) -> str:
        """
        변화율 계산

        Args:
            current: 현재 값
            previous: 이전 값

        Returns:
            변화율 문자열 (예: "+15%", "-3%")
        """
        if previous == 0:
            if current > 0:
                return "+100%"
            return "0%"

        change = ((current - previous) / previous) * 100
        sign = "+" if change >= 0 else ""
        return f"{sign}{change:.0f}%"

    def get_best_posts(self, limit: int = 3) -> List[Dict]:
        """
        베스트 게시물 조회

        Args:
            limit: 조회할 게시물 수

        Returns:
            베스트 게시물 목록
        """
        logger.info(f"베스트 게시물 {limit}개 조회")

        try:
            best_posts = self.analyzer.get_best_performing_posts(
                count=limit,
                metric="reach",
                days=1
            )

            result = []
            for post in best_posts:
                media_type_display = {
                    "IMAGE": "이미지",
                    "VIDEO": "비디오",
                    "CAROUSEL_ALBUM": "캐러셀",
                    "REELS": "릴스",
                }.get(post.media_type, post.media_type)

                result.append({
                    "media_id": post.media_id,
                    "media_type": media_type_display,
                    "reach": post.reach,
                    "likes": post.likes,
                    "comments": post.comments,
                    "engagement_rate": post.engagement_rate,
                    "caption_preview": post.caption[:30] + "..." if len(post.caption) > 30 else post.caption,
                })

            return result

        except Exception as e:
            logger.error(f"베스트 게시물 조회 실패: {e}")
            return []

    def get_worst_posts(self, limit: int = 2) -> List[Dict]:
        """
        저성과 게시물 조회 (개선 필요)

        Args:
            limit: 조회할 게시물 수

        Returns:
            저성과 게시물 목록
        """
        logger.info(f"저성과 게시물 {limit}개 조회")

        try:
            worst_posts = self.analyzer.get_worst_performing_posts(
                count=limit,
                metric="reach",
                days=1
            )

            result = []
            for post in worst_posts:
                media_type_display = {
                    "IMAGE": "이미지",
                    "VIDEO": "비디오",
                    "CAROUSEL_ALBUM": "캐러셀",
                    "REELS": "릴스",
                }.get(post.media_type, post.media_type)

                result.append({
                    "media_id": post.media_id,
                    "media_type": media_type_display,
                    "reach": post.reach,
                    "engagement_rate": post.engagement_rate,
                })

            return result

        except Exception as e:
            logger.error(f"저성과 게시물 조회 실패: {e}")
            return []

    def get_ad_performance_summary(self) -> Optional[Dict[str, Any]]:
        """
        광고 성과 요약 (선택적)

        Returns:
            광고 성과 데이터 또는 None
        """
        logger.info("광고 성과 요약 조회")

        try:
            # KillSwitch에서 광고 정보 조회
            from paid.kill_switch import KillSwitch

            kill_switch = KillSwitch()
            active_ads = kill_switch.get_active_ads()

            total_spend = 0.0
            total_impressions = 0
            total_clicks = 0
            total_conversions = 0

            for ad in active_ads:
                insights = kill_switch.get_ad_insights(ad["id"], use_today=False)
                total_spend += insights["spend"]
                total_impressions += insights["impressions"]
                total_clicks += insights["clicks"]
                total_conversions += insights["conversions"]

            # 중단된 광고 수는 별도 조회 필요 (여기서는 추정)
            paused_count = 0

            return {
                "active_count": len(active_ads),
                "paused_count": paused_count,
                "total_spend": total_spend,
                "total_impressions": total_impressions,
                "total_clicks": total_clicks,
                "total_conversions": total_conversions,
                "avg_ctr": (total_clicks / total_impressions * 100) if total_impressions > 0 else 0,
            }

        except Exception as e:
            logger.warning(f"광고 성과 조회 실패 (선택적): {e}")
            return None

    def generate_markdown_report(self) -> str:
        """
        Markdown 형식 리포트 생성

        Returns:
            Markdown 리포트 문자열
        """
        logger.info("Markdown 리포트 생성")

        # 데이터 수집
        yesterday_data = self.get_yesterday_insights()
        day_before_data = self.get_day_before_insights()
        best_posts = self.get_best_posts(limit=3)
        ad_summary = self.get_ad_performance_summary()

        # 변화율 계산
        reach_change = self.calculate_change(
            yesterday_data["reach"], day_before_data["reach"]
        )
        impressions_change = self.calculate_change(
            yesterday_data["impressions"], day_before_data["impressions"]
        )
        profile_views_change = self.calculate_change(
            yesterday_data["profile_views"], day_before_data["profile_views"]
        )

        # 리포트 생성
        report_date = self.yesterday.strftime("%Y-%m-%d")

        report_lines = [
            f"일일 Instagram 리포트 ({report_date})",
            "",
            "--- 주요 지표 ---",
            f"- 도달: {yesterday_data['reach']:,} ({reach_change})",
            f"- 노출: {yesterday_data['impressions']:,} ({impressions_change})",
            f"- 프로필 방문: {yesterday_data['profile_views']:,} ({profile_views_change})",
            f"- 팔로워: {yesterday_data['follower_count']:,}",
            "",
        ]

        # 베스트 게시물
        if best_posts:
            report_lines.append("--- 베스트 게시물 ---")
            for i, post in enumerate(best_posts, 1):
                report_lines.append(
                    f"{i}. [{post['media_type']}] {post['reach']:,} reach, "
                    f"{post['likes']} likes"
                )
            report_lines.append("")

        # 광고 성과 (있는 경우)
        if ad_summary:
            report_lines.append("--- 광고 성과 ---")
            report_lines.append(f"- 활성 광고: {ad_summary['active_count']}개")
            if ad_summary['paused_count'] > 0:
                report_lines.append(f"- 중단된 광고: {ad_summary['paused_count']}개")
            report_lines.append(f"- 총 지출: {ad_summary['total_spend']:,.0f}원")
            if ad_summary['total_conversions'] > 0:
                report_lines.append(f"- 총 전환: {ad_summary['total_conversions']}건")
            report_lines.append("")

        return "\n".join(report_lines)

    def generate_slack_report(self) -> Dict[str, Any]:
        """
        Slack 발송용 리포트 데이터 생성

        Returns:
            Slack 메시지 데이터
        """
        logger.info("Slack 리포트 데이터 생성")

        # 데이터 수집
        yesterday_data = self.get_yesterday_insights()
        day_before_data = self.get_day_before_insights()
        best_posts = self.get_best_posts(limit=3)
        ad_summary = self.get_ad_performance_summary()

        # 변화율 계산
        reach_change = self.calculate_change(
            yesterday_data["reach"], day_before_data["reach"]
        )
        impressions_change = self.calculate_change(
            yesterday_data["impressions"], day_before_data["impressions"]
        )
        profile_views_change = self.calculate_change(
            yesterday_data["profile_views"], day_before_data["profile_views"]
        )

        report_date = self.yesterday.strftime("%Y-%m-%d")

        # 주요 지표 섹션
        metrics_text = (
            f"*주요 지표*\n"
            f"- 도달: {yesterday_data['reach']:,} ({reach_change})\n"
            f"- 노출: {yesterday_data['impressions']:,} ({impressions_change})\n"
            f"- 프로필 방문: {yesterday_data['profile_views']:,} ({profile_views_change})\n"
            f"- 팔로워: {yesterday_data['follower_count']:,}"
        )

        # 베스트 게시물 섹션
        best_text = "*베스트 게시물*\n"
        if best_posts:
            for i, post in enumerate(best_posts, 1):
                best_text += (
                    f"{i}. [{post['media_type']}] "
                    f"{post['reach']:,} reach\n"
                )
        else:
            best_text += "어제 게시된 콘텐츠가 없습니다."

        # 광고 섹션
        ad_text = ""
        if ad_summary:
            ad_text = (
                f"*광고 성과*\n"
                f"- 활성 광고: {ad_summary['active_count']}개\n"
                f"- 총 지출: {ad_summary['total_spend']:,.0f}원"
            )
            if ad_summary['total_conversions'] > 0:
                ad_text += f"\n- 총 전환: {ad_summary['total_conversions']}건"

        # 전체 메시지 조합
        full_message = f"{metrics_text}\n\n{best_text}"
        if ad_text:
            full_message += f"\n\n{ad_text}"

        return {
            "title": f"일일 Instagram 리포트 ({report_date})",
            "message": full_message,
            "color": "#2196f3",
            "fields": {
                "도달": f"{yesterday_data['reach']:,} ({reach_change})",
                "노출": f"{yesterday_data['impressions']:,} ({impressions_change})",
                "프로필 방문": f"{yesterday_data['profile_views']:,}",
                "팔로워": f"{yesterday_data['follower_count']:,}",
            }
        }

    def send_report(self) -> bool:
        """
        리포트 Slack 발송

        Returns:
            발송 성공 여부
        """
        logger.info("리포트 Slack 발송")

        try:
            report_data = self.generate_slack_report()

            success = self.notifier.send(
                message=report_data["message"],
                title=report_data["title"],
                color=report_data["color"],
                fields=report_data["fields"]
            )

            if success:
                logger.info("리포트 발송 완료")
            else:
                logger.warning("리포트 발송 실패 (Slack 비활성화 또는 에러)")

            return success

        except Exception as e:
            logger.error(f"리포트 발송 중 에러: {e}")
            return False


def run_daily_report():
    """
    일일 성과 리포트 실행

    주요 기능:
    1. 어제 vs 그저께 성과 비교
    2. 베스트/워스트 게시물 선정
    3. 광고 성과 요약
    4. Slack으로 리포트 발송
    """
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("[Cron] 일일 성과 리포트 생성 시작")
    logger.info(f"시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    notifier = get_notifier()

    try:
        # 리포트 생성기 초기화
        generator = DailyReportGenerator()

        # Markdown 리포트 생성 및 로깅
        markdown_report = generator.generate_markdown_report()
        logger.info("-" * 40)
        logger.info("생성된 리포트:")
        for line in markdown_report.split("\n"):
            logger.info(f"  {line}")
        logger.info("-" * 40)

        # Slack 발송
        send_success = generator.send_report()

        # 실행 시간 계산
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info(f"리포트 발송: {'성공' if send_success else '실패'}")
        logger.info(f"종료 시간: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"실행 시간: {duration:.1f}초")
        logger.info("=" * 60)

        return {
            "success": send_success,
            "duration": duration,
        }

    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        error_msg = f"일일 리포트 생성 실패: {str(e)}"
        logger.error(error_msg)
        logger.exception(e)

        # 에러 Slack 알림
        notifier.notify_error(
            error_msg=str(e),
            context="cron.daily.run_daily_report"
        )

        logger.info(f"종료 시간: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"실행 시간: {duration:.1f}초 (실패)")
        logger.info("=" * 60)

        raise


def main():
    """메인 진입점"""
    try:
        result = run_daily_report()

        # 정상 종료
        sys.exit(0 if result["success"] else 1)

    except Exception as e:
        logger.error(f"Cron 작업 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
