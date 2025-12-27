"""
Ad Multiplier - 이미지 재활용 시스템
=====================================
1장 이미지 → 10개 이상 광고 카피 변형 자동 생성

사용법:
    multiplier = AdMultiplier()

    # 캠페인 생성
    campaign_id = multiplier.create_campaign(
        name="여름 세일 캠페인",
        objective="OUTCOME_SALES",
        daily_budget_krw=50000
    )

    # 1장 이미지로 10개 광고 생성
    ad_ids = multiplier.create_ads_from_image(
        image_path="product.jpg",
        adset_id=adset_id,
        link_url="https://shop.com/product",
        count=10
    )
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
from facebook_business.exceptions import FacebookRequestError

from config.meta_credentials import MetaCredentials, init_facebook_sdk
from config.claude_api import ClaudeClient
from config.constants import CtaType
from utils.logger import get_logger


logger = get_logger(__name__)


@dataclass
class AdResult:
    """광고 생성 결과"""

    campaign_id: str
    adset_id: str
    ad_ids: List[str]
    creative_ids: List[str]
    image_hash: str


class AdMultiplierError(Exception):
    """AdMultiplier 관련 에러"""
    pass


class CampaignCreationError(AdMultiplierError):
    """캠페인 생성 실패"""
    pass


class AdSetCreationError(AdMultiplierError):
    """AdSet 생성 실패"""
    pass


class ImageUploadError(AdMultiplierError):
    """이미지 업로드 실패"""
    pass


class CreativeCreationError(AdMultiplierError):
    """Creative 생성 실패"""
    pass


class AdCreationError(AdMultiplierError):
    """Ad 생성 실패"""
    pass


class AdMultiplier:
    """
    1장 이미지로 여러 광고 조합 생성

    Meta Ads API를 활용하여 하나의 이미지에서 다양한 카피를 가진
    광고를 자동으로 생성합니다.
    """

    def __init__(self, credentials: Optional[MetaCredentials] = None):
        """
        AdMultiplier 초기화

        Args:
            credentials: Meta API 인증 정보 (없으면 환경변수에서 로드)
        """
        logger.info("AdMultiplier 초기화 시작")

        try:
            # 인증 정보 설정
            if credentials:
                self.creds = credentials
                FacebookAdsApi.init(
                    app_id=self.creds.app_id,
                    app_secret=self.creds.app_secret,
                    access_token=self.creds.access_token,
                )
            else:
                self.creds = init_facebook_sdk()

            # Claude 클라이언트 초기화
            self.claude = ClaudeClient()

            # Ad Account 객체 생성
            self.ad_account = AdAccount(self.creds.ad_account_id)

            logger.info("AdMultiplier 초기화 완료")

        except Exception as e:
            logger.error(f"AdMultiplier 초기화 실패: {e}")
            raise AdMultiplierError(f"초기화 실패: {e}")

    # ============================================================
    # 1. 캠페인 생성
    # ============================================================

    def create_campaign(
        self,
        name: str,
        objective: str,
        daily_budget_krw: int,
    ) -> str:
        """
        캠페인 생성 (CBO 활성화)

        Args:
            name: 캠페인 이름
            objective: 캠페인 목표
                - OUTCOME_TRAFFIC: 트래픽
                - OUTCOME_ENGAGEMENT: 참여
                - OUTCOME_SALES: 판매/전환
                - OUTCOME_LEADS: 리드 생성
                - OUTCOME_AWARENESS: 브랜드 인지도
                - OUTCOME_APP_PROMOTION: 앱 홍보
            daily_budget_krw: 일일 예산 (원 단위)

        Returns:
            캠페인 ID

        Raises:
            CampaignCreationError: 캠페인 생성 실패 시
        """
        logger.info(f"캠페인 생성 시작: name={name}, objective={objective}, budget={daily_budget_krw}원")

        # 유효한 objective 검증
        valid_objectives = [
            "OUTCOME_TRAFFIC",
            "OUTCOME_ENGAGEMENT",
            "OUTCOME_SALES",
            "OUTCOME_LEADS",
            "OUTCOME_AWARENESS",
            "OUTCOME_APP_PROMOTION",
        ]

        if objective not in valid_objectives:
            raise CampaignCreationError(
                f"유효하지 않은 objective: {objective}. "
                f"유효한 값: {valid_objectives}"
            )

        try:
            campaign = Campaign(parent_id=self.creds.ad_account_id)
            campaign.update(
                {
                    Campaign.Field.name: name,
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

            logger.info(f"캠페인 생성 완료: campaign_id={campaign_id}")
            return campaign_id

        except FacebookRequestError as e:
            logger.error(f"캠페인 생성 실패 (Facebook API 에러): {e.api_error_message()}")
            raise CampaignCreationError(f"Facebook API 에러: {e.api_error_message()}")
        except Exception as e:
            logger.error(f"캠페인 생성 실패: {e}")
            raise CampaignCreationError(f"캠페인 생성 실패: {e}")

    # ============================================================
    # 2. AdSet 생성
    # ============================================================

    def create_adset(
        self,
        campaign_id: str,
        name: str,
        targeting: Dict[str, Any],
        optimization_goal: str,
    ) -> str:
        """
        AdSet 생성

        Args:
            campaign_id: 캠페인 ID
            name: AdSet 이름
            targeting: 타겟팅 설정
                {
                    "geo_locations": {"countries": ["KR"]},
                    "age_min": 25,
                    "age_max": 45,
                    "genders": [1, 2],  # 1=남성, 2=여성
                    "interests": [{"id": "...", "name": "..."}],
                    "publisher_platforms": ["instagram"],
                    "instagram_positions": ["stream", "story", "reels"]
                }
            optimization_goal: 최적화 목표
                - LINK_CLICKS: 링크 클릭
                - IMPRESSIONS: 노출
                - REACH: 도달
                - POST_ENGAGEMENT: 게시물 참여
                - LANDING_PAGE_VIEWS: 랜딩페이지 조회
                - OFFSITE_CONVERSIONS: 오프사이트 전환

        Returns:
            AdSet ID

        Raises:
            AdSetCreationError: AdSet 생성 실패 시
        """
        logger.info(f"AdSet 생성 시작: name={name}, campaign_id={campaign_id}")

        # 타겟팅 기본값 설정
        if "geo_locations" not in targeting:
            targeting["geo_locations"] = {"countries": ["KR"]}

        if "publisher_platforms" not in targeting:
            targeting["publisher_platforms"] = ["instagram"]
            targeting["instagram_positions"] = ["stream", "story", "reels"]

        try:
            adset = AdSet(parent_id=self.creds.ad_account_id)
            adset.update(
                {
                    AdSet.Field.name: name,
                    AdSet.Field.campaign_id: campaign_id,
                    AdSet.Field.billing_event: AdSet.BillingEvent.impressions,
                    AdSet.Field.optimization_goal: optimization_goal,
                    AdSet.Field.targeting: targeting,
                    AdSet.Field.status: AdSet.Status.paused,
                }
            )

            adset.remote_create()
            adset_id = adset.get_id()

            logger.info(f"AdSet 생성 완료: adset_id={adset_id}")
            return adset_id

        except FacebookRequestError as e:
            logger.error(f"AdSet 생성 실패 (Facebook API 에러): {e.api_error_message()}")
            raise AdSetCreationError(f"Facebook API 에러: {e.api_error_message()}")
        except Exception as e:
            logger.error(f"AdSet 생성 실패: {e}")
            raise AdSetCreationError(f"AdSet 생성 실패: {e}")

    # ============================================================
    # 3. 이미지 업로드
    # ============================================================

    def upload_image(self, image_path: str) -> str:
        """
        이미지 업로드하여 hash 획득

        Args:
            image_path: 이미지 파일 경로

        Returns:
            이미지 해시 (image_hash)

        Raises:
            ImageUploadError: 이미지 업로드 실패 시
        """
        logger.info(f"이미지 업로드 시작: {image_path}")

        # 파일 존재 여부 확인
        import os
        if not os.path.exists(image_path):
            raise ImageUploadError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

        # 지원 형식 확인
        valid_extensions = [".jpg", ".jpeg", ".png", ".gif", ".bmp"]
        ext = os.path.splitext(image_path)[1].lower()
        if ext not in valid_extensions:
            raise ImageUploadError(
                f"지원하지 않는 이미지 형식: {ext}. "
                f"지원 형식: {valid_extensions}"
            )

        try:
            image = AdImage(parent_id=self.creds.ad_account_id)
            image[AdImage.Field.filename] = image_path
            image.remote_create()

            image_hash = image[AdImage.Field.hash]

            logger.info(f"이미지 업로드 완료: image_hash={image_hash}")
            return image_hash

        except FacebookRequestError as e:
            logger.error(f"이미지 업로드 실패 (Facebook API 에러): {e.api_error_message()}")
            raise ImageUploadError(f"Facebook API 에러: {e.api_error_message()}")
        except Exception as e:
            logger.error(f"이미지 업로드 실패: {e}")
            raise ImageUploadError(f"이미지 업로드 실패: {e}")

    # ============================================================
    # 4. 카피 변형 생성 (Claude AI 활용)
    # ============================================================

    def generate_copy_variants(
        self,
        image_path: str,
        count: int = 10,
        brand_tone: str = "친근하고 세련된",
    ) -> List[Dict[str, str]]:
        """
        Claude AI를 활용하여 광고 카피 변형 생성

        다양한 심리 트리거를 활용한 카피 생성:
        - urgency: 긴급성 (오늘만, 마감 임박)
        - social_proof: 사회적 증거 (10,000명이 선택)
        - value: 가치 (최대 50% 할인)
        - style: 스타일 (올해의 트렌드)
        - scarcity: 희소성 (선착순 100명)
        - authority: 권위 (전문가 추천)

        Args:
            image_path: 분석할 이미지 파일 경로
            count: 생성할 카피 개수 (기본 10개)
            brand_tone: 브랜드 톤앤매너

        Returns:
            카피 리스트
            [
                {
                    "text": "24시간 특가! 지금 바로",
                    "cta_type": "SHOP_NOW",
                    "theme": "urgency"
                },
                ...
            ]

        Raises:
            AdMultiplierError: 카피 생성 실패 시
        """
        logger.info(f"카피 변형 생성 시작: count={count}, brand_tone={brand_tone}")

        try:
            copies = self.claude.generate_ad_copies(
                image_path=image_path,
                count=count,
                brand_tone=brand_tone,
            )

            logger.info(f"카피 변형 생성 완료: {len(copies)}개 생성됨")

            # 생성된 카피 로깅
            for idx, copy in enumerate(copies):
                logger.debug(
                    f"카피 {idx + 1}: text={copy.get('text')}, "
                    f"cta={copy.get('cta_type')}, theme={copy.get('theme')}"
                )

            return copies

        except Exception as e:
            logger.error(f"카피 생성 실패: {e}")
            raise AdMultiplierError(f"카피 생성 실패: {e}")

    # ============================================================
    # 5. 광고 크리에이티브 생성
    # ============================================================

    def create_ad_creative(
        self,
        name: str,
        image_hash: str,
        headline: str,
        body: str,
        cta_type: CtaType,
        link_url: str,
    ) -> str:
        """
        광고 크리에이티브 생성

        Args:
            name: 크리에이티브 이름
            image_hash: 이미지 해시 (upload_image 반환값)
            headline: 헤드라인 텍스트
            body: 본문 텍스트
            cta_type: CTA 버튼 타입 (CtaType enum)
            link_url: 클릭 시 이동할 URL

        Returns:
            Creative ID

        Raises:
            CreativeCreationError: Creative 생성 실패 시
        """
        logger.info(f"Creative 생성 시작: name={name}, cta={cta_type.value}")

        try:
            creative = AdCreative(parent_id=self.creds.ad_account_id)
            creative.update(
                {
                    AdCreative.Field.name: name,
                    AdCreative.Field.object_story_spec: {
                        "page_id": self.creds.facebook_page_id,
                        "instagram_actor_id": self.creds.instagram_account_id,
                        "link_data": {
                            "image_hash": image_hash,
                            "link": link_url,
                            "name": headline,  # 헤드라인
                            "message": body,  # 본문
                            "call_to_action": {
                                "type": cta_type.value,
                                "value": {"link": link_url},
                            },
                        },
                    },
                }
            )

            creative.remote_create()
            creative_id = creative.get_id()

            logger.info(f"Creative 생성 완료: creative_id={creative_id}")
            return creative_id

        except FacebookRequestError as e:
            logger.error(f"Creative 생성 실패 (Facebook API 에러): {e.api_error_message()}")
            raise CreativeCreationError(f"Facebook API 에러: {e.api_error_message()}")
        except Exception as e:
            logger.error(f"Creative 생성 실패: {e}")
            raise CreativeCreationError(f"Creative 생성 실패: {e}")

    # ============================================================
    # 6. 광고 생성
    # ============================================================

    def create_ad(
        self,
        adset_id: str,
        creative_id: str,
        name: str,
    ) -> str:
        """
        최종 광고 생성

        Args:
            adset_id: AdSet ID
            creative_id: Creative ID
            name: 광고 이름

        Returns:
            Ad ID

        Raises:
            AdCreationError: Ad 생성 실패 시
        """
        logger.info(f"Ad 생성 시작: name={name}, adset_id={adset_id}")

        try:
            ad = Ad(parent_id=self.creds.ad_account_id)
            ad.update(
                {
                    Ad.Field.name: name,
                    Ad.Field.adset_id: adset_id,
                    Ad.Field.creative: {"creative_id": creative_id},
                    Ad.Field.status: Ad.Status.paused,
                }
            )

            ad.remote_create()
            ad_id = ad.get_id()

            logger.info(f"Ad 생성 완료: ad_id={ad_id}")
            return ad_id

        except FacebookRequestError as e:
            logger.error(f"Ad 생성 실패 (Facebook API 에러): {e.api_error_message()}")
            raise AdCreationError(f"Facebook API 에러: {e.api_error_message()}")
        except Exception as e:
            logger.error(f"Ad 생성 실패: {e}")
            raise AdCreationError(f"Ad 생성 실패: {e}")

    # ============================================================
    # 7. 핵심 기능: 1장 이미지 → N개 광고 자동 생성
    # ============================================================

    def create_ads_from_image(
        self,
        image_path: str,
        adset_id: str,
        link_url: str,
        count: int = 10,
        brand_tone: str = "친근하고 세련된",
        headline_prefix: str = "",
    ) -> List[str]:
        """
        1장 이미지로 여러 광고 자동 생성 (핵심 기능)

        이미지를 분석하여 다양한 심리 트리거를 활용한 카피를 생성하고,
        각 카피별로 Creative와 Ad를 자동으로 생성합니다.

        Args:
            image_path: 이미지 파일 경로
            adset_id: 광고를 생성할 AdSet ID
            link_url: 클릭 시 이동할 URL
            count: 생성할 광고 개수 (기본 10개)
            brand_tone: 브랜드 톤앤매너
            headline_prefix: 헤드라인 접두사 (선택)

        Returns:
            생성된 Ad ID 리스트

        Raises:
            AdMultiplierError: 광고 생성 과정에서 에러 발생 시
        """
        logger.info("=" * 60)
        logger.info("1장 이미지 → N개 광고 자동 생성 시작")
        logger.info("=" * 60)
        logger.info(f"이미지: {image_path}")
        logger.info(f"AdSet ID: {adset_id}")
        logger.info(f"링크 URL: {link_url}")
        logger.info(f"생성 개수: {count}")

        # 1. 이미지 업로드
        logger.info("[Step 1/4] 이미지 업로드 중...")
        image_hash = self.upload_image(image_path)

        # 2. Claude AI로 카피 생성
        logger.info("[Step 2/4] AI로 카피 변형 생성 중...")
        copies = self.generate_copy_variants(
            image_path=image_path,
            count=count,
            brand_tone=brand_tone,
        )

        # 3. Creative + Ad 생성
        logger.info("[Step 3/4] Creative 및 Ad 생성 중...")
        ad_ids = []
        creative_ids = []
        failed_count = 0

        for idx, copy in enumerate(copies):
            try:
                # CTA 타입 결정
                cta_str = copy.get("cta_type", "SHOP_NOW")
                try:
                    cta_type = CtaType(cta_str)
                except ValueError:
                    cta_type = CtaType.SHOP_NOW
                    logger.warning(f"알 수 없는 CTA 타입 '{cta_str}', SHOP_NOW로 대체")

                # 헤드라인 생성
                headline = f"{headline_prefix}{copy.get('text', '')}" if headline_prefix else copy.get("text", "")
                theme = copy.get("theme", "default")
                timestamp = int(time.time())

                # Creative 생성
                creative_name = f"Creative_{idx + 1}_{theme}_{timestamp}"
                creative_id = self.create_ad_creative(
                    name=creative_name,
                    image_hash=image_hash,
                    headline=headline,
                    body=copy.get("text", ""),
                    cta_type=cta_type,
                    link_url=link_url,
                )
                creative_ids.append(creative_id)

                # Ad 생성
                ad_name = f"Ad_{idx + 1}_{theme}_{timestamp}"
                ad_id = self.create_ad(
                    adset_id=adset_id,
                    creative_id=creative_id,
                    name=ad_name,
                )
                ad_ids.append(ad_id)

                logger.info(f"광고 {idx + 1}/{len(copies)} 생성 완료: {ad_id}")

            except (CreativeCreationError, AdCreationError) as e:
                failed_count += 1
                logger.error(f"광고 {idx + 1}/{len(copies)} 생성 실패: {e}")
                continue
            except Exception as e:
                failed_count += 1
                logger.error(f"광고 {idx + 1}/{len(copies)} 생성 중 예상치 못한 에러: {e}")
                continue

        # 4. 결과 요약
        logger.info("[Step 4/4] 생성 완료")
        logger.info("=" * 60)
        logger.info("광고 생성 결과 요약")
        logger.info("=" * 60)
        logger.info(f"요청 개수: {count}")
        logger.info(f"성공: {len(ad_ids)}개")
        logger.info(f"실패: {failed_count}개")
        logger.info(f"이미지 해시: {image_hash}")
        logger.info(f"생성된 Ad ID: {ad_ids}")

        if not ad_ids:
            raise AdMultiplierError("광고 생성에 모두 실패했습니다")

        return ad_ids

    # ============================================================
    # 편의 메서드: 전체 플로우 일괄 처리
    # ============================================================

    def create_full_campaign_with_ads(
        self,
        image_path: str,
        link_url: str,
        campaign_name: str,
        daily_budget_krw: int = 50000,
        objective: str = "OUTCOME_SALES",
        targeting: Optional[Dict[str, Any]] = None,
        ad_count: int = 10,
        brand_tone: str = "친근하고 세련된",
    ) -> AdResult:
        """
        캠페인부터 광고까지 전체 플로우 일괄 처리

        Args:
            image_path: 이미지 파일 경로
            link_url: 클릭 시 이동할 URL
            campaign_name: 캠페인 이름
            daily_budget_krw: 일일 예산 (원)
            objective: 캠페인 목표
            targeting: 타겟팅 설정 (없으면 기본값 사용)
            ad_count: 생성할 광고 개수
            brand_tone: 브랜드 톤앤매너

        Returns:
            AdResult 객체 (campaign_id, adset_id, ad_ids, creative_ids, image_hash)
        """
        logger.info("=" * 60)
        logger.info("전체 캠페인 생성 플로우 시작")
        logger.info("=" * 60)

        # 1. 캠페인 생성
        campaign_id = self.create_campaign(
            name=campaign_name,
            objective=objective,
            daily_budget_krw=daily_budget_krw,
        )

        # 2. 기본 타겟팅 설정
        if targeting is None:
            targeting = {
                "geo_locations": {"countries": ["KR"]},
                "age_min": 25,
                "age_max": 45,
                "publisher_platforms": ["instagram"],
                "instagram_positions": ["stream", "story", "reels"],
            }

        # 3. 최적화 목표 결정 (objective에 따라)
        optimization_goal_map = {
            "OUTCOME_TRAFFIC": "LINK_CLICKS",
            "OUTCOME_ENGAGEMENT": "POST_ENGAGEMENT",
            "OUTCOME_SALES": "OFFSITE_CONVERSIONS",
            "OUTCOME_LEADS": "LEAD_GENERATION",
            "OUTCOME_AWARENESS": "REACH",
            "OUTCOME_APP_PROMOTION": "APP_INSTALLS",
        }
        optimization_goal = optimization_goal_map.get(objective, "LINK_CLICKS")

        # 4. AdSet 생성
        adset_id = self.create_adset(
            campaign_id=campaign_id,
            name=f"{campaign_name}_AdSet",
            targeting=targeting,
            optimization_goal=optimization_goal,
        )

        # 5. 이미지 업로드
        image_hash = self.upload_image(image_path)

        # 6. 카피 생성 및 광고 생성
        copies = self.generate_copy_variants(
            image_path=image_path,
            count=ad_count,
            brand_tone=brand_tone,
        )

        ad_ids = []
        creative_ids = []

        for idx, copy in enumerate(copies):
            try:
                cta_str = copy.get("cta_type", "SHOP_NOW")
                try:
                    cta_type = CtaType(cta_str)
                except ValueError:
                    cta_type = CtaType.SHOP_NOW

                theme = copy.get("theme", "default")
                timestamp = int(time.time())

                creative_id = self.create_ad_creative(
                    name=f"Creative_{idx + 1}_{theme}_{timestamp}",
                    image_hash=image_hash,
                    headline=copy.get("text", ""),
                    body=copy.get("text", ""),
                    cta_type=cta_type,
                    link_url=link_url,
                )
                creative_ids.append(creative_id)

                ad_id = self.create_ad(
                    adset_id=adset_id,
                    creative_id=creative_id,
                    name=f"Ad_{idx + 1}_{theme}_{timestamp}",
                )
                ad_ids.append(ad_id)

                logger.info(f"광고 {idx + 1}/{len(copies)} 생성 완료")

            except Exception as e:
                logger.error(f"광고 {idx + 1} 생성 실패: {e}")
                continue

        result = AdResult(
            campaign_id=campaign_id,
            adset_id=adset_id,
            ad_ids=ad_ids,
            creative_ids=creative_ids,
            image_hash=image_hash,
        )

        logger.info("=" * 60)
        logger.info("전체 캠페인 생성 완료")
        logger.info("=" * 60)
        logger.info(f"캠페인 ID: {campaign_id}")
        logger.info(f"AdSet ID: {adset_id}")
        logger.info(f"생성된 광고: {len(ad_ids)}개")

        return result


# ============================================================
# CLI 지원
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Ad Multiplier - 이미지 재활용 광고 생성"
    )
    parser.add_argument("--image", required=True, help="이미지 파일 경로")
    parser.add_argument("--url", required=True, help="랜딩 페이지 URL")
    parser.add_argument("--budget", type=int, default=50000, help="일일 예산 (원)")
    parser.add_argument("--count", type=int, default=10, help="생성할 광고 개수")
    parser.add_argument("--name", default=None, help="캠페인 이름")
    parser.add_argument(
        "--objective",
        default="OUTCOME_SALES",
        choices=[
            "OUTCOME_TRAFFIC",
            "OUTCOME_ENGAGEMENT",
            "OUTCOME_SALES",
            "OUTCOME_LEADS",
            "OUTCOME_AWARENESS",
        ],
        help="캠페인 목표",
    )

    args = parser.parse_args()

    campaign_name = args.name or f"AutoAds_{int(time.time())}"

    multiplier = AdMultiplier()
    result = multiplier.create_full_campaign_with_ads(
        image_path=args.image,
        link_url=args.url,
        campaign_name=campaign_name,
        daily_budget_krw=args.budget,
        objective=args.objective,
        ad_count=args.count,
    )

    print("\n완료!")
    print(f"캠페인 ID: {result.campaign_id}")
    print(f"AdSet ID: {result.adset_id}")
    print(f"생성된 광고: {len(result.ad_ids)}개")
    print(f"Ad IDs: {result.ad_ids}")
