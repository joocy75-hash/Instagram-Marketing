"""
시스템 상수 및 설정값
=====================================
Kill-Switch 임계값, CTA 타입, 응답 템플릿 등 관리
"""

from enum import Enum
from typing import Dict, List


# ============================================================
# Kill-Switch 임계값 설정
# ============================================================


class KillSwitchThresholds:
    """광고 자동 중단 판정 기준"""

    # Level 1: 노출 대비 클릭 없음
    MIN_IMPRESSIONS_FOR_CHECK = 500  # 최소 노출 수

    # Level 2: CTR 기준
    CTR_CHECK_IMPRESSIONS = 1000  # CTR 체크 시작 노출 수
    MIN_CTR_PERCENT = 0.5  # 최소 CTR (%)

    # Level 3: CPC 기준
    CPC_CHECK_SPEND = 5000  # CPC 체크 시작 지출 (원)
    MAX_CPC = 500  # 최대 허용 CPC (원)

    # Level 4: ROAS 기준
    ROAS_CHECK_SPEND = 10000  # ROAS 체크 시작 지출 (원)
    MIN_ROAS = 2.0  # 최소 ROAS

    # 승자 광고 기준 (예산 증액)
    WINNER_MIN_CTR = 1.5  # 승자 최소 CTR (%)
    WINNER_MIN_ROAS = 4.0  # 승자 최소 ROAS
    WINNER_BUDGET_INCREASE_RATE = 1.5  # 예산 증액 배율 (50%)

    # 모니터링 주기
    MONITOR_INTERVAL_SECONDS = 1800  # 30분


# ============================================================
# CTA 버튼 타입 (광고 전용)
# ============================================================


class CtaType(Enum):
    """Instagram/Facebook 광고 CTA 버튼 종류"""

    SHOP_NOW = "SHOP_NOW"  # 지금 쇼핑하기
    LEARN_MORE = "LEARN_MORE"  # 더 알아보기
    SIGN_UP = "SIGN_UP"  # 가입하기
    BOOK_TRAVEL = "BOOK_TRAVEL"  # 예약하기
    CONTACT_US = "CONTACT_US"  # 문의하기
    DOWNLOAD = "DOWNLOAD"  # 다운로드
    GET_OFFER = "GET_OFFER"  # 혜택 받기
    GET_QUOTE = "GET_QUOTE"  # 견적 받기
    WATCH_MORE = "WATCH_MORE"  # 더 보기
    APPLY_NOW = "APPLY_NOW"  # 지금 신청
    SUBSCRIBE = "SUBSCRIBE"  # 구독하기


# 카테고리별 기본 CTA 매핑
CATEGORY_CTA_MAPPING: Dict[str, CtaType] = {
    "의류": CtaType.SHOP_NOW,
    "패션": CtaType.SHOP_NOW,
    "쇼핑몰": CtaType.SHOP_NOW,
    "서비스": CtaType.LEARN_MORE,
    "교육": CtaType.LEARN_MORE,
    "앱": CtaType.DOWNLOAD,
    "게임": CtaType.DOWNLOAD,
    "여행": CtaType.BOOK_TRAVEL,
    "호텔": CtaType.BOOK_TRAVEL,
    "레스토랑": CtaType.BOOK_TRAVEL,
    "이벤트": CtaType.GET_OFFER,
    "할인": CtaType.GET_OFFER,
    "구독": CtaType.SUBSCRIBE,
    "뉴스레터": CtaType.SUBSCRIBE,
}


# ============================================================
# 댓글 의도 분류
# ============================================================


class CommentIntent(Enum):
    """댓글 의도 분류"""

    PRICE = "price"  # 가격 문의
    SIZE = "size"  # 사이즈 문의
    STOCK = "stock"  # 재고 문의
    SHIPPING = "shipping"  # 배송 문의
    PURCHASE = "purchase"  # 구매 의사
    COMPLIMENT = "compliment"  # 칭찬
    COMPLAINT = "complaint"  # 불만
    SPAM = "spam"  # 스팸
    OTHER = "other"  # 기타


# 의도별 자동 응답 템플릿
COMMENT_RESPONSE_TEMPLATES: Dict[str, str] = {
    "price": "@{username} DM으로 가격 안내 도와드릴게요! 📩",
    "size": "@{username} 사이즈 문의는 DM 확인 부탁드려요 😊",
    "stock": "@{username} 재고 확인해드릴게요! DM 보내드렸습니다 ✨",
    "shipping": "@{username} 배송 정보는 프로필 링크에서 확인 가능해요 🚚",
    "purchase": "@{username} 구매 링크 DM 드렸어요! 💙",
    "compliment": "@{username} 감사합니다! 💕",
    "other": "@{username} 문의 감사합니다! DM 확인 부탁드려요 😊",
}


# ============================================================
# DM Ice Breaker 설정
# ============================================================

ICE_BREAKERS: List[Dict[str, str]] = [
    {"question": "💰 가격이 궁금하신가요?", "payload": "PRICE_INQUIRY"},
    {"question": "📏 사이즈 문의하기", "payload": "SIZE_INQUIRY"},
    {"question": "🛒 지금 구매하기", "payload": "PURCHASE_INTENT"},
    {"question": "📦 배송 정보 확인", "payload": "SHIPPING_INFO"},
]


# ============================================================
# 캡션 CTA 템플릿
# ============================================================

CAPTION_CTA_TEMPLATES: Dict[str, str] = {
    "profile_link": """
{main_message} 🔥

━━━━━━━━━━━━━━━━
👆 프로필 링크에서 바로 구매!
━━━━━━━━━━━━━━━━

💬 사이즈/가격 문의 → DM 주세요!
📦 당일 발송 | 무료 배송

{hashtags}
""",
    "urgency": """
⏰ {main_message}

🔥 오늘까지만 특가!
━━━━━━━━━━━━━━━━
👆 프로필 링크 클릭!
━━━━━━━━━━━━━━━━

{hashtags}
""",
    "limited": """
🔥 {main_message}

⚠️ 선착순 {limit}명 마감!
━━━━━━━━━━━━━━━━
👆 프로필 링크에서 확인
━━━━━━━━━━━━━━━━

{hashtags}
""",
}


# ============================================================
# CAPI 이벤트 설정
# ============================================================


class CapiEventType(Enum):
    """Conversions API 이벤트 종류"""

    PAGE_VIEW = "PageView"
    VIEW_CONTENT = "ViewContent"
    ADD_TO_CART = "AddToCart"
    INITIATE_CHECKOUT = "InitiateCheckout"
    PURCHASE = "Purchase"
    LEAD = "Lead"
    COMPLETE_REGISTRATION = "CompleteRegistration"


# ============================================================
# 시스템 설정
# ============================================================


class SystemConfig:
    """시스템 전역 설정"""

    # API 버전
    META_API_VERSION = "v21.0"

    # 로깅
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Webhook
    WEBHOOK_VERIFY_TOKEN = "instagram_marketing_webhook_2025"

    # 재시도 설정
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 5

    # 기본 통화
    DEFAULT_CURRENCY = "KRW"
