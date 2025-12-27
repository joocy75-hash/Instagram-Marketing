"""
DCO Optimizer - Dynamic Creative Optimization
=====================================
Meta의 Dynamic Creative 및 Advantage+ 캠페인 자동화

사용법:
    optimizer = DcoOptimizer()

    # DCO 캠페인 생성
    result = optimizer.create_full_dco_campaign(
        name="Winter Sale DCO",
        images=["image1.jpg", "image2.jpg"],
        headlines=["겨울 세일", "50% 할인"],
        descriptions=["지금 바로 구매하세요", "한정 수량"],
        targeting={"geo_locations": {"countries": ["KR"]}},
        link_url="https://shop.com",
        daily_budget_krw=100000
    )

주요 기능:
    - Dynamic Creative Optimization (DCO) 캠페인 생성
    - Asset Feed Spec 기반 다중 에셋 조합
    - Advantage+ Shopping Campaign 지원
    - 조합별 성과 분석 (Breakdown)
"""

import time
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.adcreative import AdCreative
from facebook_business.adobjects.adimage import AdImage
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adsinsights import AdsInsights

from config.meta_credentials import get_credentials
from config.constants import CtaType
from utils.logger import get_logger


logger = get_logger(__name__)


@dataclass
class DcoResult:
    """DCO 캠페인 생성 결과"""

    campaign_id: str
    adset_id: str
    ad_id: str
    creative_id: str
    asset_count: Dict[str, int]  # 에셋 타입별 개수


@dataclass
class DcoBreakdownResult:
    """DCO 조합별 성과 분석 결과"""

    ad_id: str
    combinations: List[Dict[str, Any]]
    best_combination: Optional[Dict[str, Any]]
    total_impressions: int
    total_clicks: int
    total_spend: float


class DcoOptimizer:
    """Dynamic Creative Optimization 관리"""

    def __init__(self):
        self.creds = get_credentials()

        # SDK 초기화
        FacebookAdsApi.init(
            app_id=self.creds.app_id,
            app_secret=self.creds.app_secret,
            access_token=self.creds.access_token,
        )

        self.ad_account = AdAccount(self.creds.ad_account_id)

    # ============================================================
    # DCO 캠페인 생성
    # ============================================================

    def create_dco_campaign(
        self,
        name: str,
        daily_budget_krw: int = 50000,
        objective: str = "OUTCOME_SALES",
    ) -> str:
        """
        Dynamic Creative용 캠페인 생성 (CBO 활성화)

        Args:
            name: 캠페인 이름
            daily_budget_krw: 일일 예산 (원화)
            objective: 캠페인 목표
                - OUTCOME_SALES: 판매
                - OUTCOME_TRAFFIC: 트래픽
                - OUTCOME_ENGAGEMENT: 참여
                - OUTCOME_LEADS: 잠재고객
                - OUTCOME_APP_PROMOTION: 앱 프로모션
                - OUTCOME_AWARENESS: 인지도

        Returns:
            캠페인 ID
        """

        logger.info(f"DCO 캠페인 생성 시작: {name}")

        campaign = Campaign(parent_id=self.creds.ad_account_id)
        campaign.update(
            {
                Campaign.Field.name: f"[DCO] {name}",
                Campaign.Field.objective: objective,
                Campaign.Field.status: Campaign.Status.paused,
                Campaign.Field.special_ad_categories: [],
                # CBO (Campaign Budget Optimization) 활성화
                Campaign.Field.daily_budget: daily_budget_krw,
                Campaign.Field.bid_strategy: Campaign.BidStrategy.lowest_cost_without_cap,
            }
        )

        campaign.remote_create()
        campaign_id = campaign.get_id()

        logger.info(f"DCO 캠페인 생성 완료: {campaign_id}")
        return campaign_id

    # ============================================================
    # DCO AdSet 생성
    # ============================================================

    def create_dco_adset(
        self,
        campaign_id: str,
        name: str,
        targeting: Optional[Dict] = None,
        optimization_goal: str = "LINK_CLICKS",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> str:
        """
        DCO용 AdSet 생성 (Dynamic Creative 활성화)

        Args:
            campaign_id: 캠페인 ID
            name: AdSet 이름
            targeting: 타겟팅 설정
            optimization_goal: 최적화 목표
                - LINK_CLICKS: 링크 클릭
                - LANDING_PAGE_VIEWS: 랜딩 페이지 조회
                - IMPRESSIONS: 노출
                - REACH: 도달
                - OFFSITE_CONVERSIONS: 전환
                - VALUE: 가치 최적화
            start_time: 시작 시간 (ISO 8601)
            end_time: 종료 시간 (ISO 8601)

        Returns:
            AdSet ID
        """

        logger.info(f"DCO AdSet 생성 시작: {name}")

        # 기본 타겟팅 (한국, 25-40세)
        default_targeting = {
            "geo_locations": {"countries": ["KR"]},
            "age_min": 25,
            "age_max": 40,
            "publisher_platforms": ["instagram", "facebook"],
            "instagram_positions": ["stream", "story", "reels", "explore"],
            "facebook_positions": ["feed", "story", "reels"],
        }

        targeting = targeting or default_targeting

        adset_params = {
            AdSet.Field.name: f"[DCO] {name}",
            AdSet.Field.campaign_id: campaign_id,
            AdSet.Field.billing_event: AdSet.BillingEvent.impressions,
            AdSet.Field.optimization_goal: optimization_goal,
            AdSet.Field.targeting: targeting,
            AdSet.Field.status: AdSet.Status.paused,
            # Dynamic Creative 활성화 (핵심 설정)
            "is_dynamic_creative": True,
        }

        # 일정 설정
        if start_time:
            adset_params[AdSet.Field.start_time] = start_time
        if end_time:
            adset_params[AdSet.Field.end_time] = end_time

        adset = AdSet(parent_id=self.creds.ad_account_id)
        adset.update(adset_params)

        adset.remote_create()
        adset_id = adset.get_id()

        logger.info(f"DCO AdSet 생성 완료: {adset_id}")
        return adset_id

    # ============================================================
    # 이미지 업로드
    # ============================================================

    def _upload_images(self, image_paths: List[str]) -> List[str]:
        """
        여러 이미지 업로드

        Args:
            image_paths: 이미지 파일 경로 리스트

        Returns:
            이미지 해시 리스트
        """

        image_hashes = []

        for path in image_paths:
            logger.info(f"이미지 업로드: {path}")

            image = AdImage(parent_id=self.creds.ad_account_id)
            image[AdImage.Field.filename] = path
            image.remote_create()

            image_hash = image[AdImage.Field.hash]
            image_hashes.append(image_hash)

            logger.info(f"이미지 업로드 완료: {image_hash}")

        return image_hashes

    # ============================================================
    # Asset Feed Spec 생성
    # ============================================================

    def create_asset_feed_spec(
        self,
        images: List[str],
        headlines: List[str],
        descriptions: List[str],
        cta_type: CtaType = CtaType.SHOP_NOW,
        link_url: str = "",
        videos: Optional[List[str]] = None,
        primary_texts: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Dynamic Creative용 에셋 피드 구성

        Args:
            images: 이미지 파일 경로 리스트 (최대 10개)
            headlines: 헤드라인 리스트 (최대 5개)
            descriptions: 설명 리스트 (최대 5개)
            cta_type: CTA 버튼 타입
            link_url: 랜딩 페이지 URL
            videos: 비디오 ID 리스트 (선택)
            primary_texts: 본문 텍스트 리스트 (선택, headlines와 별도)

        Returns:
            asset_feed_spec 딕셔너리

        Note:
            Meta가 자동으로 모든 에셋 조합을 테스트하여 최적 조합을 찾습니다.
            예: 3개 이미지 x 2개 헤드라인 x 2개 설명 = 12개 조합
        """

        logger.info("Asset Feed Spec 생성 시작")
        logger.info(f"이미지: {len(images)}개, 헤드라인: {len(headlines)}개, 설명: {len(descriptions)}개")

        # 이미지 업로드
        image_hashes = self._upload_images(images)

        # Asset Feed Spec 구성
        asset_feed_spec = {
            # 이미지 에셋
            "images": [{"hash": h} for h in image_hashes],
            # 헤드라인 에셋 (광고 제목)
            "titles": [{"text": t} for t in headlines[:5]],
            # 설명 에셋 (보조 텍스트)
            "descriptions": [{"text": d} for d in descriptions[:5]],
            # CTA 버튼
            "call_to_action_types": [cta_type.value],
            # 랜딩 페이지
            "link_urls": [{"website_url": link_url}],
        }

        # 본문 텍스트 (Primary Text) 추가
        if primary_texts:
            asset_feed_spec["bodies"] = [{"text": t} for t in primary_texts[:5]]
        else:
            # 기본적으로 descriptions를 bodies로도 사용
            asset_feed_spec["bodies"] = [{"text": d} for d in descriptions[:5]]

        # 비디오 에셋 추가 (선택)
        if videos:
            asset_feed_spec["videos"] = [{"video_id": v} for v in videos]

        # Ad Format (추가 포맷 옵션)
        asset_feed_spec["ad_formats"] = ["SINGLE_IMAGE"]

        logger.info(f"Asset Feed Spec 생성 완료: {len(image_hashes)}개 이미지, {len(headlines)}개 헤드라인")

        return asset_feed_spec

    # ============================================================
    # DCO Creative 생성
    # ============================================================

    def create_dco_creative(
        self,
        name: str,
        asset_feed_spec: Dict[str, Any],
        page_id: Optional[str] = None,
    ) -> str:
        """
        Dynamic Creative 생성

        Args:
            name: Creative 이름
            asset_feed_spec: 에셋 피드 스펙 (create_asset_feed_spec 결과)
            page_id: Facebook Page ID (없으면 환경변수 사용)

        Returns:
            Creative ID
        """

        logger.info(f"DCO Creative 생성 시작: {name}")

        page_id = page_id or self.creds.facebook_page_id

        creative = AdCreative(parent_id=self.creds.ad_account_id)
        creative.update(
            {
                AdCreative.Field.name: f"[DCO] {name}",
                # Object Story Spec - 페이지 정보
                AdCreative.Field.object_story_spec: {
                    "page_id": page_id,
                    "instagram_actor_id": self.creds.instagram_account_id,
                },
                # Asset Feed Spec - 다이나믹 크리에이티브 에셋
                AdCreative.Field.asset_feed_spec: asset_feed_spec,
            }
        )

        creative.remote_create()
        creative_id = creative.get_id()

        logger.info(f"DCO Creative 생성 완료: {creative_id}")
        return creative_id

    # ============================================================
    # DCO Ad 생성
    # ============================================================

    def _create_dco_ad(
        self,
        adset_id: str,
        creative_id: str,
        name: str,
    ) -> str:
        """
        DCO Ad 생성

        Args:
            adset_id: AdSet ID
            creative_id: Creative ID
            name: 광고 이름

        Returns:
            Ad ID
        """

        logger.info(f"DCO Ad 생성 시작: {name}")

        ad = Ad(parent_id=self.creds.ad_account_id)
        ad.update(
            {
                Ad.Field.name: f"[DCO] {name}",
                Ad.Field.adset_id: adset_id,
                Ad.Field.creative: {"creative_id": creative_id},
                Ad.Field.status: Ad.Status.paused,
            }
        )

        ad.remote_create()
        ad_id = ad.get_id()

        logger.info(f"DCO Ad 생성 완료: {ad_id}")
        return ad_id

    # ============================================================
    # Advantage+ Shopping Campaign
    # ============================================================

    def create_advantage_plus_campaign(
        self,
        name: str,
        daily_budget_krw: int = 100000,
        country_code: str = "KR",
    ) -> str:
        """
        Advantage+ Shopping Campaign 생성

        자동 타겟팅, 자동 배치, 자동 크리에이티브 최적화를 활용한
        고급 쇼핑 캠페인입니다.

        Args:
            name: 캠페인 이름
            daily_budget_krw: 일일 예산 (원화)
            country_code: 대상 국가 코드

        Returns:
            캠페인 ID

        Note:
            Advantage+ Shopping Campaign은 다음 기능을 자동화합니다:
            - 타겟팅: Meta AI가 최적의 오디언스 탐색
            - 배치: 모든 플랫폼에서 최적 배치 선택
            - 크리에이티브: 에셋 조합 자동 최적화
        """

        logger.info(f"Advantage+ Shopping Campaign 생성 시작: {name}")

        campaign = Campaign(parent_id=self.creds.ad_account_id)
        campaign.update(
            {
                Campaign.Field.name: f"[ASC+] {name}",
                Campaign.Field.objective: "OUTCOME_SALES",
                Campaign.Field.status: Campaign.Status.paused,
                # Special Ad Categories 없음 (표준 상거래용)
                Campaign.Field.special_ad_categories: [],
                # CBO 활성화
                Campaign.Field.daily_budget: daily_budget_krw,
                Campaign.Field.bid_strategy: Campaign.BidStrategy.lowest_cost_without_cap,
                # Advantage+ Shopping Campaign 설정
                "smart_promotion_type": "GUIDED_CREATION",
                # 타겟팅 국가
                "promoted_object": {
                    "country": country_code,
                },
            }
        )

        campaign.remote_create()
        campaign_id = campaign.get_id()

        logger.info(f"Advantage+ Shopping Campaign 생성 완료: {campaign_id}")
        return campaign_id

    def create_advantage_plus_adset(
        self,
        campaign_id: str,
        name: str,
        pixel_id: Optional[str] = None,
        custom_audience_ids: Optional[List[str]] = None,
    ) -> str:
        """
        Advantage+ Shopping Campaign용 AdSet 생성

        Args:
            campaign_id: Advantage+ 캠페인 ID
            name: AdSet 이름
            pixel_id: 픽셀 ID (없으면 환경변수 사용)
            custom_audience_ids: 기존 고객 오디언스 ID (선택)

        Returns:
            AdSet ID
        """

        logger.info(f"Advantage+ AdSet 생성 시작: {name}")

        pixel_id = pixel_id or self.creds.pixel_id

        adset_params = {
            AdSet.Field.name: f"[ASC+] {name}",
            AdSet.Field.campaign_id: campaign_id,
            AdSet.Field.billing_event: AdSet.BillingEvent.impressions,
            AdSet.Field.optimization_goal: "OFFSITE_CONVERSIONS",
            AdSet.Field.status: AdSet.Status.paused,
            # Advantage+ 자동 타겟팅 (빈 타겟팅 = 완전 자동)
            AdSet.Field.targeting: {
                "geo_locations": {"countries": ["KR"]},
            },
            # 픽셀 기반 전환 추적
            "promoted_object": {
                "pixel_id": pixel_id,
                "custom_event_type": "PURCHASE",
            },
        }

        # 기존 고객 제외 (선택)
        if custom_audience_ids:
            adset_params[AdSet.Field.targeting]["exclusions"] = {
                "custom_audiences": [{"id": cid} for cid in custom_audience_ids]
            }

        adset = AdSet(parent_id=self.creds.ad_account_id)
        adset.update(adset_params)

        adset.remote_create()
        adset_id = adset.get_id()

        logger.info(f"Advantage+ AdSet 생성 완료: {adset_id}")
        return adset_id

    # ============================================================
    # DCO 조합별 성과 분석
    # ============================================================

    def get_dco_breakdown(
        self,
        ad_id: str,
        date_preset: str = "last_7d",
    ) -> DcoBreakdownResult:
        """
        DCO 광고의 조합별 성과 분석

        Args:
            ad_id: DCO 광고 ID
            date_preset: 기간 프리셋
                - last_7d: 최근 7일
                - last_14d: 최근 14일
                - last_30d: 최근 30일
                - this_month: 이번 달
                - last_month: 지난 달

        Returns:
            DcoBreakdownResult 객체 (조합별 성과 포함)

        Note:
            어떤 이미지+헤드라인+설명 조합이 최고 성과인지 확인할 수 있습니다.
            Meta가 자동으로 성과 좋은 조합에 예산을 집중합니다.
        """

        logger.info(f"DCO 성과 분석 시작: {ad_id}")

        ad = Ad(ad_id)

        # 조합별 성과 가져오기
        insights = ad.get_insights(
            params={
                "date_preset": date_preset,
                "breakdowns": ["body_asset", "title_asset", "image_asset", "description_asset"],
                "fields": [
                    "impressions",
                    "clicks",
                    "ctr",
                    "cpc",
                    "spend",
                    "actions",
                    "body_asset",
                    "title_asset",
                    "image_asset",
                    "description_asset",
                ],
            }
        )

        combinations = []
        total_impressions = 0
        total_clicks = 0
        total_spend = 0.0
        best_combination = None
        best_ctr = 0.0

        for insight in insights:
            combo = {
                "body": insight.get("body_asset", {}).get("text", "N/A"),
                "title": insight.get("title_asset", {}).get("text", "N/A"),
                "image_hash": insight.get("image_asset", {}).get("hash", "N/A"),
                "description": insight.get("description_asset", {}).get("text", "N/A"),
                "impressions": int(insight.get("impressions", 0)),
                "clicks": int(insight.get("clicks", 0)),
                "ctr": float(insight.get("ctr", 0)),
                "cpc": float(insight.get("cpc", 0)),
                "spend": float(insight.get("spend", 0)),
            }

            combinations.append(combo)
            total_impressions += combo["impressions"]
            total_clicks += combo["clicks"]
            total_spend += combo["spend"]

            # 최고 CTR 조합 찾기
            if combo["ctr"] > best_ctr and combo["impressions"] >= 100:
                best_ctr = combo["ctr"]
                best_combination = combo

        logger.info(f"DCO 분석 완료: {len(combinations)}개 조합")

        if best_combination:
            logger.info(f"최고 성과 조합 - CTR: {best_ctr:.2f}%")
            logger.info(f"  제목: {best_combination['title']}")
            logger.info(f"  설명: {best_combination['description']}")

        return DcoBreakdownResult(
            ad_id=ad_id,
            combinations=combinations,
            best_combination=best_combination,
            total_impressions=total_impressions,
            total_clicks=total_clicks,
            total_spend=total_spend,
        )

    def get_asset_performance(
        self,
        ad_id: str,
        asset_type: str = "image",
        date_preset: str = "last_7d",
    ) -> List[Dict[str, Any]]:
        """
        특정 에셋 타입별 성과 조회

        Args:
            ad_id: DCO 광고 ID
            asset_type: 에셋 타입 (image, title, body, description)
            date_preset: 기간 프리셋

        Returns:
            에셋별 성과 리스트
        """

        breakdown_map = {
            "image": "image_asset",
            "title": "title_asset",
            "body": "body_asset",
            "description": "description_asset",
        }

        breakdown = breakdown_map.get(asset_type, "image_asset")

        ad = Ad(ad_id)
        insights = ad.get_insights(
            params={
                "date_preset": date_preset,
                "breakdowns": [breakdown],
                "fields": [
                    "impressions",
                    "clicks",
                    "ctr",
                    "spend",
                    breakdown,
                ],
            }
        )

        results = []
        for insight in insights:
            asset_info = insight.get(breakdown, {})
            results.append(
                {
                    "asset": asset_info,
                    "impressions": int(insight.get("impressions", 0)),
                    "clicks": int(insight.get("clicks", 0)),
                    "ctr": float(insight.get("ctr", 0)),
                    "spend": float(insight.get("spend", 0)),
                }
            )

        # CTR 기준 정렬
        results.sort(key=lambda x: x["ctr"], reverse=True)

        return results

    # ============================================================
    # 전체 DCO 캠페인 생성 플로우
    # ============================================================

    def create_full_dco_campaign(
        self,
        name: str,
        images: List[str],
        headlines: List[str],
        descriptions: List[str],
        targeting: Optional[Dict] = None,
        link_url: str = "",
        daily_budget_krw: int = 50000,
        cta_type: CtaType = CtaType.SHOP_NOW,
        optimization_goal: str = "LINK_CLICKS",
        page_id: Optional[str] = None,
        primary_texts: Optional[List[str]] = None,
    ) -> DcoResult:
        """
        전체 DCO 캠페인 생성 플로우 (일괄 처리)

        Args:
            name: 캠페인 이름
            images: 이미지 파일 경로 리스트 (최대 10개)
            headlines: 헤드라인 리스트 (최대 5개)
            descriptions: 설명 리스트 (최대 5개)
            targeting: 타겟팅 설정 (없으면 기본값)
            link_url: 랜딩 페이지 URL
            daily_budget_krw: 일일 예산 (원화)
            cta_type: CTA 버튼 타입
            optimization_goal: 최적화 목표
            page_id: Facebook Page ID (없으면 환경변수 사용)
            primary_texts: 본문 텍스트 리스트 (선택)

        Returns:
            DcoResult 객체

        Note:
            이 메서드는 다음 순서로 DCO 캠페인을 생성합니다:
            1. DCO 캠페인 생성 (CBO 활성화)
            2. DCO AdSet 생성 (Dynamic Creative 활성화)
            3. Asset Feed Spec 생성 (이미지 업로드 포함)
            4. DCO Creative 생성
            5. DCO Ad 생성

            Meta AI가 자동으로 모든 에셋 조합을 테스트하고
            최적의 조합에 예산을 집중합니다.
        """

        logger.info("=== DCO 캠페인 전체 생성 시작 ===")
        logger.info(f"캠페인명: {name}")
        logger.info(f"이미지: {len(images)}개, 헤드라인: {len(headlines)}개, 설명: {len(descriptions)}개")
        logger.info(f"예상 조합 수: {len(images) * len(headlines) * len(descriptions)}개")

        try:
            # 1. DCO 캠페인 생성
            campaign_id = self.create_dco_campaign(
                name=name,
                daily_budget_krw=daily_budget_krw,
            )

            # 2. DCO AdSet 생성
            adset_id = self.create_dco_adset(
                campaign_id=campaign_id,
                name=f"{name}_AdSet",
                targeting=targeting,
                optimization_goal=optimization_goal,
            )

            # 3. Asset Feed Spec 생성
            asset_feed_spec = self.create_asset_feed_spec(
                images=images,
                headlines=headlines,
                descriptions=descriptions,
                cta_type=cta_type,
                link_url=link_url,
                primary_texts=primary_texts,
            )

            # 4. DCO Creative 생성
            creative_id = self.create_dco_creative(
                name=f"{name}_Creative",
                asset_feed_spec=asset_feed_spec,
                page_id=page_id,
            )

            # 5. DCO Ad 생성
            ad_id = self._create_dco_ad(
                adset_id=adset_id,
                creative_id=creative_id,
                name=f"{name}_Ad",
            )

            result = DcoResult(
                campaign_id=campaign_id,
                adset_id=adset_id,
                ad_id=ad_id,
                creative_id=creative_id,
                asset_count={
                    "images": len(images),
                    "headlines": len(headlines),
                    "descriptions": len(descriptions),
                    "combinations": len(images) * len(headlines) * len(descriptions),
                },
            )

            logger.info("=== DCO 캠페인 전체 생성 완료 ===")
            logger.info(f"캠페인 ID: {campaign_id}")
            logger.info(f"AdSet ID: {adset_id}")
            logger.info(f"Ad ID: {ad_id}")
            logger.info(f"총 조합 수: {result.asset_count['combinations']}개")

            return result

        except Exception as e:
            logger.error(f"DCO 캠페인 생성 실패: {e}")
            raise

    # ============================================================
    # 유틸리티 메서드
    # ============================================================

    def activate_campaign(self, campaign_id: str) -> bool:
        """
        캠페인 활성화

        Args:
            campaign_id: 캠페인 ID

        Returns:
            성공 여부
        """

        try:
            campaign = Campaign(campaign_id)
            campaign.update({Campaign.Field.status: Campaign.Status.active})
            campaign.remote_update()

            logger.info(f"캠페인 활성화 완료: {campaign_id}")
            return True

        except Exception as e:
            logger.error(f"캠페인 활성화 실패: {e}")
            return False

    def pause_campaign(self, campaign_id: str) -> bool:
        """
        캠페인 일시 중지

        Args:
            campaign_id: 캠페인 ID

        Returns:
            성공 여부
        """

        try:
            campaign = Campaign(campaign_id)
            campaign.update({Campaign.Field.status: Campaign.Status.paused})
            campaign.remote_update()

            logger.info(f"캠페인 일시 중지: {campaign_id}")
            return True

        except Exception as e:
            logger.error(f"캠페인 일시 중지 실패: {e}")
            return False

    def update_budget(
        self,
        campaign_id: str,
        daily_budget_krw: int,
    ) -> bool:
        """
        캠페인 예산 업데이트

        Args:
            campaign_id: 캠페인 ID
            daily_budget_krw: 새 일일 예산 (원화)

        Returns:
            성공 여부
        """

        try:
            campaign = Campaign(campaign_id)
            campaign.update({Campaign.Field.daily_budget: daily_budget_krw})
            campaign.remote_update()

            logger.info(f"예산 업데이트 완료: {campaign_id} -> {daily_budget_krw:,}원")
            return True

        except Exception as e:
            logger.error(f"예산 업데이트 실패: {e}")
            return False


# ============================================================
# CLI 지원
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="DCO Optimizer - Dynamic Creative Optimization"
    )
    parser.add_argument("--name", required=True, help="캠페인 이름")
    parser.add_argument("--images", nargs="+", required=True, help="이미지 파일 경로들")
    parser.add_argument("--headlines", nargs="+", required=True, help="헤드라인들")
    parser.add_argument("--descriptions", nargs="+", required=True, help="설명들")
    parser.add_argument("--url", required=True, help="랜딩 페이지 URL")
    parser.add_argument("--budget", type=int, default=50000, help="일일 예산 (원)")

    args = parser.parse_args()

    optimizer = DcoOptimizer()
    result = optimizer.create_full_dco_campaign(
        name=args.name,
        images=args.images,
        headlines=args.headlines,
        descriptions=args.descriptions,
        link_url=args.url,
        daily_budget_krw=args.budget,
    )

    print(f"\n완료!")
    print(f"캠페인 ID: {result.campaign_id}")
    print(f"총 조합 수: {result.asset_count['combinations']}개")
