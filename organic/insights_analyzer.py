"""
Insights Analyzer - 인스타그램 성과 분석
=====================================
계정, 미디어, 스토리 인사이트 조회 및 분석

사용법:
    analyzer = InsightsAnalyzer()

    # 계정 인사이트 조회
    account_insights = analyzer.get_account_insights()

    # 미디어 성과 분석
    media_insights = analyzer.get_media_insights(media_id)

    # 베스트 게시물 찾기
    best_posts = analyzer.get_best_performing_posts(count=10)
"""

import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.meta_credentials import get_credentials
from utils.logger import get_logger


logger = get_logger("insights_analyzer")


class InsightPeriod(Enum):
    """인사이트 조회 기간"""
    DAY = "day"
    WEEK = "week"
    DAYS_28 = "days_28"
    LIFETIME = "lifetime"


class InsightMetric(Enum):
    """인사이트 메트릭 종류"""
    # 계정 메트릭
    IMPRESSIONS = "impressions"
    REACH = "reach"
    FOLLOWER_COUNT = "follower_count"
    PROFILE_VIEWS = "profile_views"
    WEBSITE_CLICKS = "website_clicks"
    EMAIL_CONTACTS = "email_contacts"

    # 미디어 메트릭
    LIKES = "likes"
    COMMENTS = "comments"
    SHARES = "shares"
    SAVED = "saved"
    ENGAGEMENT = "engagement"
    VIDEO_VIEWS = "video_views"

    # 스토리 메트릭
    EXITS = "exits"
    REPLIES = "replies"
    TAPS_FORWARD = "taps_forward"
    TAPS_BACK = "taps_back"


@dataclass
class MediaInsight:
    """미디어 인사이트 데이터"""
    media_id: str
    media_type: str
    caption: str
    timestamp: str
    impressions: int
    reach: int
    likes: int
    comments: int
    shares: int
    saved: int
    engagement_rate: float
    permalink: str


@dataclass
class AccountInsight:
    """계정 인사이트 데이터"""
    period: str
    impressions: int
    reach: int
    profile_views: int
    website_clicks: int
    follower_count: int
    follower_growth: int


class InsightsAnalyzer:
    """
    Instagram 인사이트 분석기

    Instagram Graph API를 사용하여 계정, 미디어, 스토리의
    성과 데이터를 조회하고 분석합니다.
    """

    def __init__(self):
        """InsightsAnalyzer 초기화"""
        self.creds = get_credentials()
        self.base_url = self.creds.get_graph_url()
        self.access_token = self.creds.access_token
        self.ig_user_id = self.creds.instagram_account_id

        logger.info(f"InsightsAnalyzer 초기화 완료: {self.ig_user_id}")

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        method: str = "GET"
    ) -> Dict:
        """
        Graph API 요청 수행

        Args:
            endpoint: API 엔드포인트
            params: 쿼리 파라미터
            method: HTTP 메서드

        Returns:
            API 응답 데이터
        """
        url = f"{self.base_url}/{endpoint}"

        if params is None:
            params = {}
        params["access_token"] = self.access_token

        try:
            if method == "GET":
                response = requests.get(url, params=params)
            else:
                response = requests.post(url, data=params)

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"API 요청 실패: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"응답: {e.response.text}")
            raise

    # ============================================================
    # 계정 인사이트
    # ============================================================

    def get_account_insights(
        self,
        period: InsightPeriod = InsightPeriod.DAY,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> AccountInsight:
        """
        계정 인사이트 조회

        Args:
            period: 조회 기간 (day, week, days_28)
            since: 시작일 (선택)
            until: 종료일 (선택)

        Returns:
            AccountInsight 객체
        """
        logger.info(f"계정 인사이트 조회: period={period.value}")

        # 메트릭 목록
        metrics = [
            "impressions",
            "reach",
            "profile_views",
            "website_clicks",
            "follower_count",
        ]

        params = {
            "metric": ",".join(metrics),
            "period": period.value,
        }

        # 날짜 범위 설정
        if since and until:
            params["since"] = int(since.timestamp())
            params["until"] = int(until.timestamp())

        try:
            data = self._make_request(
                f"{self.ig_user_id}/insights",
                params=params
            )

            # 응답 파싱
            result = {
                "impressions": 0,
                "reach": 0,
                "profile_views": 0,
                "website_clicks": 0,
                "follower_count": 0,
            }

            for item in data.get("data", []):
                metric_name = item.get("name")
                values = item.get("values", [])
                if values:
                    result[metric_name] = values[0].get("value", 0)

            # 팔로워 수 별도 조회 (insights에 없을 수 있음)
            if result["follower_count"] == 0:
                account_data = self._make_request(
                    self.ig_user_id,
                    params={"fields": "followers_count"}
                )
                result["follower_count"] = account_data.get("followers_count", 0)

            return AccountInsight(
                period=period.value,
                impressions=result["impressions"],
                reach=result["reach"],
                profile_views=result["profile_views"],
                website_clicks=result["website_clicks"],
                follower_count=result["follower_count"],
                follower_growth=0,  # 별도 계산 필요
            )

        except Exception as e:
            logger.error(f"계정 인사이트 조회 실패: {e}")
            raise

    def get_follower_demographics(self) -> Dict[str, Any]:
        """
        팔로워 인구통계 조회

        Returns:
            {
                "audience_city": {...},
                "audience_country": {...},
                "audience_gender_age": {...},
                "audience_locale": {...}
            }
        """
        logger.info("팔로워 인구통계 조회")

        metrics = [
            "audience_city",
            "audience_country",
            "audience_gender_age",
            "audience_locale",
        ]

        params = {
            "metric": ",".join(metrics),
            "period": "lifetime",
        }

        try:
            data = self._make_request(
                f"{self.ig_user_id}/insights",
                params=params
            )

            result = {}
            for item in data.get("data", []):
                metric_name = item.get("name")
                values = item.get("values", [])
                if values:
                    result[metric_name] = values[0].get("value", {})

            return result

        except Exception as e:
            logger.error(f"팔로워 인구통계 조회 실패: {e}")
            return {}

    # ============================================================
    # 미디어 인사이트
    # ============================================================

    def get_media_insights(self, media_id: str) -> MediaInsight:
        """
        개별 미디어 인사이트 조회

        Args:
            media_id: 미디어 ID

        Returns:
            MediaInsight 객체
        """
        logger.info(f"미디어 인사이트 조회: {media_id}")

        try:
            # 미디어 기본 정보 조회
            media_data = self._make_request(
                media_id,
                params={
                    "fields": "id,caption,media_type,timestamp,permalink,like_count,comments_count"
                }
            )

            # 미디어 인사이트 조회
            metrics = ["impressions", "reach", "saved", "shares"]

            # 비디오인 경우 video_views 추가
            if media_data.get("media_type") in ["VIDEO", "REELS"]:
                metrics.append("video_views")

            insights_data = self._make_request(
                f"{media_id}/insights",
                params={"metric": ",".join(metrics)}
            )

            # 인사이트 파싱
            insights = {
                "impressions": 0,
                "reach": 0,
                "saved": 0,
                "shares": 0,
            }

            for item in insights_data.get("data", []):
                metric_name = item.get("name")
                values = item.get("values", [])
                if values:
                    insights[metric_name] = values[0].get("value", 0)

            # 좋아요, 댓글
            likes = media_data.get("like_count", 0)
            comments = media_data.get("comments_count", 0)

            # Engagement Rate 계산 (likes + comments + saved + shares) / reach * 100
            reach = insights["reach"]
            total_engagement = likes + comments + insights["saved"] + insights["shares"]
            engagement_rate = (total_engagement / reach * 100) if reach > 0 else 0

            return MediaInsight(
                media_id=media_id,
                media_type=media_data.get("media_type", ""),
                caption=media_data.get("caption", "")[:100],
                timestamp=media_data.get("timestamp", ""),
                impressions=insights["impressions"],
                reach=reach,
                likes=likes,
                comments=comments,
                shares=insights["shares"],
                saved=insights["saved"],
                engagement_rate=round(engagement_rate, 2),
                permalink=media_data.get("permalink", ""),
            )

        except Exception as e:
            logger.error(f"미디어 인사이트 조회 실패: {e}")
            raise

    def get_recent_media(self, limit: int = 25) -> List[Dict]:
        """
        최근 미디어 목록 조회

        Args:
            limit: 조회할 미디어 수 (최대 50)

        Returns:
            미디어 목록
        """
        logger.info(f"최근 미디어 조회: limit={limit}")

        try:
            data = self._make_request(
                f"{self.ig_user_id}/media",
                params={
                    "fields": "id,caption,media_type,timestamp,permalink,like_count,comments_count",
                    "limit": min(limit, 50),
                }
            )

            return data.get("data", [])

        except Exception as e:
            logger.error(f"최근 미디어 조회 실패: {e}")
            return []

    def get_best_performing_posts(
        self,
        count: int = 10,
        metric: str = "engagement_rate",
        days: int = 30,
    ) -> List[MediaInsight]:
        """
        베스트 성과 게시물 조회

        Args:
            count: 조회할 게시물 수
            metric: 정렬 기준 (engagement_rate, reach, impressions, likes)
            days: 조회 기간 (일)

        Returns:
            정렬된 MediaInsight 리스트
        """
        logger.info(f"베스트 게시물 조회: count={count}, metric={metric}")

        # 최근 미디어 조회
        recent_media = self.get_recent_media(limit=50)

        # 기간 필터
        cutoff_date = datetime.now() - timedelta(days=days)

        insights_list = []
        for media in recent_media:
            try:
                # 날짜 필터
                timestamp = media.get("timestamp", "")
                if timestamp:
                    media_date = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    if media_date.replace(tzinfo=None) < cutoff_date:
                        continue

                # 인사이트 조회
                insight = self.get_media_insights(media["id"])
                insights_list.append(insight)

            except Exception as e:
                logger.warning(f"미디어 {media['id']} 인사이트 조회 실패: {e}")
                continue

        # 정렬
        sort_key = {
            "engagement_rate": lambda x: x.engagement_rate,
            "reach": lambda x: x.reach,
            "impressions": lambda x: x.impressions,
            "likes": lambda x: x.likes,
            "comments": lambda x: x.comments,
            "saved": lambda x: x.saved,
        }.get(metric, lambda x: x.engagement_rate)

        insights_list.sort(key=sort_key, reverse=True)

        return insights_list[:count]

    def get_worst_performing_posts(
        self,
        count: int = 10,
        metric: str = "engagement_rate",
        days: int = 30,
    ) -> List[MediaInsight]:
        """
        저성과 게시물 조회 (개선 필요한 컨텐츠 분석용)

        Args:
            count: 조회할 게시물 수
            metric: 정렬 기준
            days: 조회 기간

        Returns:
            저성과 순 정렬된 MediaInsight 리스트
        """
        logger.info(f"저성과 게시물 조회: count={count}")

        best_posts = self.get_best_performing_posts(count=50, metric=metric, days=days)
        best_posts.reverse()  # 역순 정렬

        return best_posts[:count]

    # ============================================================
    # 스토리 인사이트
    # ============================================================

    def get_stories(self) -> List[Dict]:
        """
        현재 활성 스토리 목록 조회

        Returns:
            스토리 목록
        """
        logger.info("스토리 목록 조회")

        try:
            data = self._make_request(
                f"{self.ig_user_id}/stories",
                params={"fields": "id,media_type,timestamp"}
            )

            return data.get("data", [])

        except Exception as e:
            logger.error(f"스토리 조회 실패: {e}")
            return []

    def get_story_insights(self, story_id: str) -> Dict:
        """
        스토리 인사이트 조회

        Args:
            story_id: 스토리 ID

        Returns:
            스토리 인사이트 데이터
        """
        logger.info(f"스토리 인사이트 조회: {story_id}")

        metrics = [
            "impressions",
            "reach",
            "replies",
            "exits",
            "taps_forward",
            "taps_back",
        ]

        try:
            data = self._make_request(
                f"{story_id}/insights",
                params={"metric": ",".join(metrics)}
            )

            result = {}
            for item in data.get("data", []):
                metric_name = item.get("name")
                values = item.get("values", [])
                if values:
                    result[metric_name] = values[0].get("value", 0)

            return result

        except Exception as e:
            logger.error(f"스토리 인사이트 조회 실패: {e}")
            return {}

    # ============================================================
    # 분석 및 리포트
    # ============================================================

    def generate_performance_report(
        self,
        period_days: int = 7,
    ) -> Dict[str, Any]:
        """
        성과 리포트 생성

        Args:
            period_days: 분석 기간 (일)

        Returns:
            종합 성과 리포트
        """
        logger.info(f"성과 리포트 생성: {period_days}일")

        try:
            # 계정 인사이트
            account = self.get_account_insights(InsightPeriod.DAY)

            # 베스트 게시물
            best_posts = self.get_best_performing_posts(count=5, days=period_days)

            # 저성과 게시물
            worst_posts = self.get_worst_performing_posts(count=3, days=period_days)

            # 전체 미디어 평균 계산
            all_insights = self.get_best_performing_posts(count=50, days=period_days)

            if all_insights:
                avg_engagement = sum(i.engagement_rate for i in all_insights) / len(all_insights)
                avg_reach = sum(i.reach for i in all_insights) / len(all_insights)
                avg_likes = sum(i.likes for i in all_insights) / len(all_insights)
            else:
                avg_engagement = avg_reach = avg_likes = 0

            report = {
                "period": f"최근 {period_days}일",
                "generated_at": datetime.now().isoformat(),
                "account_summary": {
                    "impressions": account.impressions,
                    "reach": account.reach,
                    "profile_views": account.profile_views,
                    "website_clicks": account.website_clicks,
                    "follower_count": account.follower_count,
                },
                "media_summary": {
                    "total_posts_analyzed": len(all_insights),
                    "avg_engagement_rate": round(avg_engagement, 2),
                    "avg_reach": round(avg_reach),
                    "avg_likes": round(avg_likes),
                },
                "best_posts": [
                    {
                        "media_id": p.media_id,
                        "engagement_rate": p.engagement_rate,
                        "reach": p.reach,
                        "likes": p.likes,
                        "caption_preview": p.caption[:50] + "..." if len(p.caption) > 50 else p.caption,
                    }
                    for p in best_posts
                ],
                "worst_posts": [
                    {
                        "media_id": p.media_id,
                        "engagement_rate": p.engagement_rate,
                        "reach": p.reach,
                        "caption_preview": p.caption[:50] + "..." if len(p.caption) > 50 else p.caption,
                    }
                    for p in worst_posts
                ],
                "recommendations": self._generate_recommendations(all_insights),
            }

            logger.info("성과 리포트 생성 완료")
            return report

        except Exception as e:
            logger.error(f"성과 리포트 생성 실패: {e}")
            raise

    def _generate_recommendations(
        self,
        insights: List[MediaInsight]
    ) -> List[str]:
        """
        성과 기반 개선 권장사항 생성

        Args:
            insights: 미디어 인사이트 리스트

        Returns:
            권장사항 리스트
        """
        recommendations = []

        if not insights:
            return ["충분한 데이터가 없습니다. 더 많은 게시물을 발행해주세요."]

        # 평균 Engagement Rate 분석
        avg_er = sum(i.engagement_rate for i in insights) / len(insights)

        if avg_er < 1.0:
            recommendations.append(
                "평균 참여율이 1% 미만입니다. CTA 문구를 강화하고 "
                "질문형 캡션을 사용해보세요."
            )
        elif avg_er < 3.0:
            recommendations.append(
                "참여율이 양호합니다. 릴스/캐러셀 형태의 콘텐츠로 "
                "더 높은 참여를 유도해보세요."
            )
        else:
            recommendations.append(
                "참여율이 우수합니다! 현재 콘텐츠 전략을 유지하세요."
            )

        # Saved 비율 분석
        total_saved = sum(i.saved for i in insights)
        total_likes = sum(i.likes for i in insights)

        if total_likes > 0:
            save_ratio = total_saved / total_likes
            if save_ratio < 0.05:
                recommendations.append(
                    "저장률이 낮습니다. 정보성/팁 콘텐츠를 늘려보세요."
                )

        # 콘텐츠 타입 분석
        video_count = sum(1 for i in insights if i.media_type in ["VIDEO", "REELS"])
        if video_count < len(insights) * 0.3:
            recommendations.append(
                "릴스/비디오 콘텐츠 비중이 낮습니다. "
                "릴스는 도달률이 높으니 비중을 늘려보세요."
            )

        return recommendations

    def compare_periods(
        self,
        period1_start: datetime,
        period1_end: datetime,
        period2_start: datetime,
        period2_end: datetime,
    ) -> Dict[str, Any]:
        """
        두 기간 성과 비교

        Args:
            period1_*: 첫 번째 기간
            period2_*: 두 번째 기간

        Returns:
            비교 결과
        """
        logger.info("기간별 성과 비교")

        try:
            # 기간 1 데이터
            insights1 = self.get_account_insights(
                InsightPeriod.DAY,
                since=period1_start,
                until=period1_end
            )

            # 기간 2 데이터
            insights2 = self.get_account_insights(
                InsightPeriod.DAY,
                since=period2_start,
                until=period2_end
            )

            # 변화율 계산
            def calc_change(v1, v2):
                if v1 == 0:
                    return 0
                return round((v2 - v1) / v1 * 100, 1)

            return {
                "period1": {
                    "start": period1_start.isoformat(),
                    "end": period1_end.isoformat(),
                    "data": {
                        "impressions": insights1.impressions,
                        "reach": insights1.reach,
                        "profile_views": insights1.profile_views,
                    }
                },
                "period2": {
                    "start": period2_start.isoformat(),
                    "end": period2_end.isoformat(),
                    "data": {
                        "impressions": insights2.impressions,
                        "reach": insights2.reach,
                        "profile_views": insights2.profile_views,
                    }
                },
                "changes": {
                    "impressions_change": calc_change(insights1.impressions, insights2.impressions),
                    "reach_change": calc_change(insights1.reach, insights2.reach),
                    "profile_views_change": calc_change(insights1.profile_views, insights2.profile_views),
                }
            }

        except Exception as e:
            logger.error(f"기간 비교 실패: {e}")
            raise


# 싱글톤 인스턴스
_analyzer: Optional[InsightsAnalyzer] = None


def get_insights_analyzer() -> InsightsAnalyzer:
    """전역 InsightsAnalyzer 반환"""
    global _analyzer
    if _analyzer is None:
        _analyzer = InsightsAnalyzer()
    return _analyzer
