"""
Meta API 인증 정보 관리
=====================================
환경 변수에서 인증 정보를 로드하여 안전하게 관리

사용 전 필수 설정:
1. .env 파일 생성
2. 아래 변수들 설정

필요 권한:
- ads_management
- ads_read
- instagram_basic
- instagram_content_publish
- instagram_manage_comments
- instagram_manage_messages
- instagram_manage_insights
"""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()


@dataclass
class MetaCredentials:
    """Meta API 인증 정보"""

    # Facebook/Meta App 정보
    app_id: str
    app_secret: str
    access_token: str

    # 광고 계정 정보
    ad_account_id: str  # 'act_' 접두어 포함

    # Page/Instagram 정보
    facebook_page_id: str
    instagram_account_id: str

    # Pixel 정보
    pixel_id: str

    @classmethod
    def from_env(cls) -> "MetaCredentials":
        """환경 변수에서 인증 정보 로드"""

        required_vars = [
            "META_APP_ID",
            "META_APP_SECRET",
            "META_ACCESS_TOKEN",
            "META_AD_ACCOUNT_ID",
            "META_FB_PAGE_ID",
            "META_IG_ACCOUNT_ID",
            "META_PIXEL_ID",
        ]

        # 필수 변수 체크
        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            raise ValueError(f"필수 환경 변수가 없습니다: {missing}")

        return cls(
            app_id=os.getenv("META_APP_ID"),
            app_secret=os.getenv("META_APP_SECRET"),
            access_token=os.getenv("META_ACCESS_TOKEN"),
            ad_account_id=os.getenv("META_AD_ACCOUNT_ID"),
            facebook_page_id=os.getenv("META_FB_PAGE_ID"),
            instagram_account_id=os.getenv("META_IG_ACCOUNT_ID"),
            pixel_id=os.getenv("META_PIXEL_ID"),
        )

    def validate(self) -> bool:
        """인증 정보 유효성 검증"""

        # ad_account_id는 'act_'로 시작해야 함
        if not self.ad_account_id.startswith("act_"):
            raise ValueError("ad_account_id는 'act_'로 시작해야 합니다")

        # access_token 길이 체크 (일반적으로 200자 이상)
        if len(self.access_token) < 100:
            raise ValueError("access_token이 너무 짧습니다. 올바른 토큰인지 확인하세요")

        return True

    def get_api_version(self) -> str:
        """현재 사용할 API 버전 반환"""
        return "v21.0"  # 2025년 기준 최신 버전

    def get_graph_url(self) -> str:
        """Graph API 기본 URL"""
        return f"https://graph.facebook.com/{self.get_api_version()}"


def init_facebook_sdk():
    """Facebook Business SDK 초기화"""

    from facebook_business.api import FacebookAdsApi

    creds = MetaCredentials.from_env()
    creds.validate()

    FacebookAdsApi.init(
        app_id=creds.app_id,
        app_secret=creds.app_secret,
        access_token=creds.access_token,
    )

    return creds


# 싱글톤 인스턴스 (선택적 사용)
_credentials: Optional[MetaCredentials] = None


def get_credentials() -> MetaCredentials:
    """전역 인증 정보 반환 (싱글톤)"""
    global _credentials
    if _credentials is None:
        _credentials = MetaCredentials.from_env()
    return _credentials
