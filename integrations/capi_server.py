"""
Instagram/Facebook Conversions API (CAPI) 서버
=====================================
Facebook Business SDK를 사용한 서버 사이드 이벤트 전송

이벤트 종류:
- PageView: 페이지 조회
- ViewContent: 상품 상세 조회
- AddToCart: 장바구니 추가
- InitiateCheckout: 결제 시작
- Purchase: 구매 완료
- Lead: 문의/리드 수집
- Custom Events: 커스텀 이벤트
"""

import hashlib
import time
import uuid
from typing import Dict, List, Optional, Any

from facebook_business.adobjects.serverside.event import Event
from facebook_business.adobjects.serverside.event_request import EventRequest
from facebook_business.adobjects.serverside.user_data import UserData
from facebook_business.adobjects.serverside.custom_data import CustomData
from facebook_business.adobjects.serverside.content import Content
from facebook_business.adobjects.serverside.action_source import ActionSource
from facebook_business.api import FacebookAdsApi

from config.meta_credentials import MetaCredentials, get_credentials
from config.constants import CapiEventType, SystemConfig
from utils.logger import get_logger

logger = get_logger("capi_server")


class CapiServer:
    """
    Facebook Conversions API 서버

    서버 사이드 이벤트를 Facebook으로 전송하여
    광고 최적화 및 전환 추적을 개선합니다.

    Usage:
        capi = CapiServer()

        # 사용자 데이터 생성
        user_data = capi.create_user_data(
            email="user@example.com",
            phone="01012345678",
            ip="1.2.3.4",
            user_agent="Mozilla/5.0..."
        )

        # 이벤트 전송
        capi.send_page_view(user_data, "https://example.com/product")
        capi.send_purchase(order_data)
    """

    def __init__(self, credentials: Optional[MetaCredentials] = None):
        """
        CAPI 서버 초기화

        Args:
            credentials: Meta API 인증 정보 (없으면 환경변수에서 로드)
        """
        self.credentials = credentials or get_credentials()
        self.pixel_id = self.credentials.pixel_id

        # Facebook SDK 초기화
        FacebookAdsApi.init(
            app_id=self.credentials.app_id,
            app_secret=self.credentials.app_secret,
            access_token=self.credentials.access_token,
        )

        # 기본 설정
        self.default_currency = SystemConfig.DEFAULT_CURRENCY
        self.test_event_code = None  # 테스트 모드용 (설정 시 테스트 이벤트로 전송)

        logger.info(f"CAPI Server initialized with pixel_id: {self.pixel_id}")

    def set_test_mode(self, test_event_code: str):
        """
        테스트 모드 활성화

        Args:
            test_event_code: Meta Events Manager에서 발급받은 테스트 코드
        """
        self.test_event_code = test_event_code
        logger.info(f"Test mode enabled with code: {test_event_code}")

    def disable_test_mode(self):
        """테스트 모드 비활성화"""
        self.test_event_code = None
        logger.info("Test mode disabled")

    # =========================================================
    # 해싱 및 사용자 데이터
    # =========================================================

    def hash_sha256(self, value: str) -> str:
        """
        SHA256 해싱 (Meta 요구사항 준수)

        Meta Conversions API는 개인정보를 SHA256 해시로 전송해야 합니다.
        - 소문자로 변환
        - 앞뒤 공백 제거
        - SHA256 해싱

        Args:
            value: 해싱할 원본 값

        Returns:
            SHA256 해시 문자열
        """
        if not value:
            return ""

        # 정규화: 소문자 변환, 공백 제거
        normalized = value.lower().strip()

        # SHA256 해싱
        hashed = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

        return hashed

    def _normalize_phone(self, phone: str) -> str:
        """
        전화번호 정규화

        Meta 요구사항:
        - 국가 코드 포함 (한국: 82)
        - 숫자만 포함
        - 선행 0 제거

        Args:
            phone: 원본 전화번호

        Returns:
            정규화된 전화번호
        """
        if not phone:
            return ""

        # 숫자만 추출
        digits = "".join(filter(str.isdigit, phone))

        # 한국 전화번호 처리
        if digits.startswith("010"):
            # 010-xxxx-xxxx -> 8210xxxxxxxx
            digits = "82" + digits[1:]
        elif digits.startswith("82"):
            # 이미 국가코드 포함
            pass
        elif digits.startswith("0"):
            # 기타 0으로 시작하는 경우
            digits = "82" + digits[1:]

        return digits

    def _normalize_email(self, email: str) -> str:
        """
        이메일 정규화

        Args:
            email: 원본 이메일

        Returns:
            정규화된 이메일 (소문자, 공백 제거)
        """
        if not email:
            return ""

        return email.lower().strip()

    def create_user_data(
        self,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        fbc: Optional[str] = None,
        fbp: Optional[str] = None,
        external_id: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        city: Optional[str] = None,
        country: Optional[str] = None,
    ) -> UserData:
        """
        사용자 정보 객체 생성

        이메일과 전화번호는 자동으로 해싱됩니다.

        Args:
            email: 이메일 주소
            phone: 전화번호
            ip: 클라이언트 IP 주소
            user_agent: 브라우저 User-Agent
            fbc: Facebook Click ID (URL에서 추출)
            fbp: Facebook Pixel ID (쿠키에서 추출)
            external_id: 외부 사용자 ID (CRM ID 등)
            first_name: 이름
            last_name: 성
            city: 도시
            country: 국가 코드 (kr, us 등)

        Returns:
            UserData 객체
        """
        user_data = UserData()

        # 이메일 (해싱 필요)
        if email:
            normalized_email = self._normalize_email(email)
            user_data.email = self.hash_sha256(normalized_email)

        # 전화번호 (해싱 필요)
        if phone:
            normalized_phone = self._normalize_phone(phone)
            user_data.phone = self.hash_sha256(normalized_phone)

        # IP 주소 (해싱 불필요)
        if ip:
            user_data.client_ip_address = ip

        # User Agent (해싱 불필요)
        if user_agent:
            user_data.client_user_agent = user_agent

        # Facebook Click ID
        if fbc:
            user_data.fbc = fbc

        # Facebook Pixel ID
        if fbp:
            user_data.fbp = fbp

        # 외부 ID (해싱 필요)
        if external_id:
            user_data.external_id = self.hash_sha256(str(external_id))

        # 이름 (해싱 필요)
        if first_name:
            user_data.first_name = self.hash_sha256(first_name)

        if last_name:
            user_data.last_name = self.hash_sha256(last_name)

        # 지역 정보 (해싱 필요)
        if city:
            user_data.city = self.hash_sha256(city)

        if country:
            user_data.country_code = self.hash_sha256(country)

        return user_data

    # =========================================================
    # 이벤트 생성 헬퍼
    # =========================================================

    def _generate_event_id(self) -> str:
        """
        고유 이벤트 ID 생성

        중복 제거를 위해 각 이벤트마다 고유 ID를 부여합니다.
        브라우저 Pixel과 서버 CAPI에서 같은 event_id를 사용하면
        Meta에서 자동으로 중복 제거합니다.

        Returns:
            고유 이벤트 ID
        """
        return str(uuid.uuid4())

    def _get_event_time(self) -> int:
        """
        현재 Unix 타임스탬프 반환

        Returns:
            Unix 타임스탬프 (초 단위)
        """
        return int(time.time())

    def _create_base_event(
        self,
        event_name: str,
        user_data: UserData,
        event_source_url: Optional[str] = None,
        event_id: Optional[str] = None,
        custom_data: Optional[CustomData] = None,
    ) -> Event:
        """
        기본 이벤트 객체 생성

        Args:
            event_name: 이벤트 이름
            user_data: 사용자 데이터
            event_source_url: 이벤트 발생 URL
            event_id: 이벤트 ID (없으면 자동 생성)
            custom_data: 커스텀 데이터

        Returns:
            Event 객체
        """
        event = Event(
            event_name=event_name,
            event_time=self._get_event_time(),
            user_data=user_data,
            event_id=event_id or self._generate_event_id(),
            action_source=ActionSource.WEBSITE,
        )

        if event_source_url:
            event.event_source_url = event_source_url

        if custom_data:
            event.custom_data = custom_data

        return event

    def _send_event(self, event: Event) -> Dict[str, Any]:
        """
        단일 이벤트 전송

        Args:
            event: 전송할 이벤트

        Returns:
            API 응답 딕셔너리
        """
        return self.batch_send_events([event])

    # =========================================================
    # 표준 이벤트 전송 메서드
    # =========================================================

    def send_page_view(
        self,
        user_data: UserData,
        event_source_url: str,
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        PageView 이벤트 전송

        페이지 조회 시 호출합니다.

        Args:
            user_data: 사용자 데이터
            event_source_url: 조회한 페이지 URL
            event_id: 이벤트 ID (브라우저 Pixel과 중복 제거용)

        Returns:
            API 응답
        """
        event = self._create_base_event(
            event_name=CapiEventType.PAGE_VIEW.value,
            user_data=user_data,
            event_source_url=event_source_url,
            event_id=event_id,
        )

        logger.info(f"Sending PageView event for URL: {event_source_url}")
        return self._send_event(event)

    def send_view_content(
        self,
        user_data: UserData,
        content_id: str,
        content_name: str,
        value: float,
        event_source_url: Optional[str] = None,
        content_category: Optional[str] = None,
        currency: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        ViewContent 이벤트 전송

        상품 상세 페이지 조회 시 호출합니다.

        Args:
            user_data: 사용자 데이터
            content_id: 상품 ID
            content_name: 상품명
            value: 상품 가격
            event_source_url: 상품 페이지 URL
            content_category: 상품 카테고리
            currency: 통화 (기본값: KRW)
            event_id: 이벤트 ID

        Returns:
            API 응답
        """
        # Content 객체 생성
        content = Content(
            product_id=str(content_id),
            title=content_name,
            item_price=value,
            quantity=1,
        )

        if content_category:
            content.category = content_category

        # CustomData 생성
        custom_data = CustomData(
            content_name=content_name,
            content_ids=[str(content_id)],
            content_type="product",
            contents=[content],
            value=value,
            currency=currency or self.default_currency,
        )

        if content_category:
            custom_data.content_category = content_category

        event = self._create_base_event(
            event_name=CapiEventType.VIEW_CONTENT.value,
            user_data=user_data,
            event_source_url=event_source_url,
            event_id=event_id,
            custom_data=custom_data,
        )

        logger.info(f"Sending ViewContent event for product: {content_id} ({content_name})")
        return self._send_event(event)

    def send_add_to_cart(
        self,
        user_data: UserData,
        content_id: str,
        content_name: str,
        value: float,
        quantity: int = 1,
        event_source_url: Optional[str] = None,
        currency: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        AddToCart 이벤트 전송

        장바구니 추가 시 호출합니다.

        Args:
            user_data: 사용자 데이터
            content_id: 상품 ID
            content_name: 상품명
            value: 총 금액 (단가 * 수량)
            quantity: 수량
            event_source_url: 페이지 URL
            currency: 통화
            event_id: 이벤트 ID

        Returns:
            API 응답
        """
        content = Content(
            product_id=str(content_id),
            title=content_name,
            item_price=value / quantity if quantity > 0 else value,
            quantity=quantity,
        )

        custom_data = CustomData(
            content_name=content_name,
            content_ids=[str(content_id)],
            content_type="product",
            contents=[content],
            value=value,
            currency=currency or self.default_currency,
            num_items=quantity,
        )

        event = self._create_base_event(
            event_name=CapiEventType.ADD_TO_CART.value,
            user_data=user_data,
            event_source_url=event_source_url,
            event_id=event_id,
            custom_data=custom_data,
        )

        logger.info(f"Sending AddToCart event: {content_id} x {quantity}")
        return self._send_event(event)

    def send_initiate_checkout(
        self,
        user_data: UserData,
        content_ids: List[str],
        value: float,
        num_items: int,
        event_source_url: Optional[str] = None,
        currency: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        InitiateCheckout 이벤트 전송

        결제 시작 시 호출합니다.

        Args:
            user_data: 사용자 데이터
            content_ids: 상품 ID 목록
            value: 총 결제 금액
            num_items: 총 상품 수량
            event_source_url: 결제 페이지 URL
            currency: 통화
            event_id: 이벤트 ID

        Returns:
            API 응답
        """
        custom_data = CustomData(
            content_ids=[str(cid) for cid in content_ids],
            content_type="product",
            value=value,
            currency=currency or self.default_currency,
            num_items=num_items,
        )

        event = self._create_base_event(
            event_name=CapiEventType.INITIATE_CHECKOUT.value,
            user_data=user_data,
            event_source_url=event_source_url,
            event_id=event_id,
            custom_data=custom_data,
        )

        logger.info(f"Sending InitiateCheckout event: {num_items} items, {value} {currency or self.default_currency}")
        return self._send_event(event)

    def send_purchase(
        self,
        order_data: Dict[str, Any],
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Purchase 이벤트 전송 (가장 중요한 전환 이벤트)

        구매 완료 시 호출합니다.
        ROAS 계산 및 광고 최적화의 핵심 이벤트입니다.

        Args:
            order_data: 주문 정보 딕셔너리
                - order_id: 주문 번호 (필수)
                - email: 고객 이메일
                - phone: 고객 전화번호
                - ip: 클라이언트 IP
                - user_agent: 브라우저 User-Agent
                - fbc: Facebook Click ID
                - fbp: Facebook Pixel ID
                - total_amount: 총 결제 금액 (필수)
                - product_id: 상품 ID (또는 product_ids 리스트)
                - product_ids: 상품 ID 리스트
                - product_name: 상품명
                - quantity: 수량 (기본값: 1)
                - currency: 통화 (기본값: KRW)
                - event_source_url: 완료 페이지 URL
                - contents: 상품 상세 리스트 (선택)
            event_id: 이벤트 ID

        Returns:
            API 응답
        """
        # 필수 필드 검증
        required_fields = ["order_id", "total_amount"]
        for field in required_fields:
            if field not in order_data:
                raise ValueError(f"order_data에 필수 필드가 없습니다: {field}")

        # 사용자 데이터 생성
        user_data = self.create_user_data(
            email=order_data.get("email"),
            phone=order_data.get("phone"),
            ip=order_data.get("ip"),
            user_agent=order_data.get("user_agent"),
            fbc=order_data.get("fbc"),
            fbp=order_data.get("fbp"),
            external_id=order_data.get("customer_id"),
            first_name=order_data.get("first_name"),
            last_name=order_data.get("last_name"),
        )

        # 상품 ID 처리
        product_ids = order_data.get("product_ids", [])
        if not product_ids and order_data.get("product_id"):
            product_ids = [order_data["product_id"]]

        # Contents 생성
        contents = []
        if order_data.get("contents"):
            # 상세 상품 정보가 제공된 경우
            for item in order_data["contents"]:
                content = Content(
                    product_id=str(item.get("product_id", "")),
                    title=item.get("name", ""),
                    item_price=item.get("price", 0),
                    quantity=item.get("quantity", 1),
                )
                contents.append(content)
        elif product_ids:
            # 기본 상품 정보
            content = Content(
                product_id=str(product_ids[0]) if product_ids else "",
                title=order_data.get("product_name", ""),
                item_price=order_data["total_amount"],
                quantity=order_data.get("quantity", 1),
            )
            contents.append(content)

        # CustomData 생성
        custom_data = CustomData(
            content_ids=[str(pid) for pid in product_ids] if product_ids else None,
            content_type="product",
            contents=contents if contents else None,
            value=float(order_data["total_amount"]),
            currency=order_data.get("currency", self.default_currency),
            order_id=str(order_data["order_id"]),
            num_items=order_data.get("quantity", len(contents) if contents else 1),
        )

        if order_data.get("product_name"):
            custom_data.content_name = order_data["product_name"]

        # 이벤트 생성 및 전송
        event = self._create_base_event(
            event_name=CapiEventType.PURCHASE.value,
            user_data=user_data,
            event_source_url=order_data.get("event_source_url"),
            event_id=event_id,
            custom_data=custom_data,
        )

        logger.info(
            f"Sending Purchase event: order_id={order_data['order_id']}, "
            f"amount={order_data['total_amount']} {order_data.get('currency', self.default_currency)}"
        )

        return self._send_event(event)

    def send_lead(
        self,
        user_data: UserData,
        lead_type: Optional[str] = None,
        event_source_url: Optional[str] = None,
        value: Optional[float] = None,
        currency: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Lead 이벤트 전송

        문의, 상담 신청, 뉴스레터 구독 등 리드 수집 시 호출합니다.

        Args:
            user_data: 사용자 데이터
            lead_type: 리드 타입 (예: "inquiry", "newsletter", "consultation")
            event_source_url: 폼 페이지 URL
            value: 리드 예상 가치 (선택)
            currency: 통화
            event_id: 이벤트 ID

        Returns:
            API 응답
        """
        custom_data = None

        if lead_type or value:
            custom_data = CustomData()

            if lead_type:
                custom_data.content_name = lead_type
                custom_data.content_category = "lead"

            if value:
                custom_data.value = value
                custom_data.currency = currency or self.default_currency

        event = self._create_base_event(
            event_name=CapiEventType.LEAD.value,
            user_data=user_data,
            event_source_url=event_source_url,
            event_id=event_id,
            custom_data=custom_data,
        )

        logger.info(f"Sending Lead event: type={lead_type}")
        return self._send_event(event)

    def send_complete_registration(
        self,
        user_data: UserData,
        registration_method: Optional[str] = None,
        event_source_url: Optional[str] = None,
        value: Optional[float] = None,
        currency: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        CompleteRegistration 이벤트 전송

        회원가입 완료 시 호출합니다.

        Args:
            user_data: 사용자 데이터
            registration_method: 가입 방법 (예: "email", "social", "kakao")
            event_source_url: 가입 완료 페이지 URL
            value: 회원 예상 가치 (선택)
            currency: 통화
            event_id: 이벤트 ID

        Returns:
            API 응답
        """
        custom_data = None

        if registration_method or value:
            custom_data = CustomData()

            if registration_method:
                custom_data.content_name = registration_method

            if value:
                custom_data.value = value
                custom_data.currency = currency or self.default_currency

        event = self._create_base_event(
            event_name=CapiEventType.COMPLETE_REGISTRATION.value,
            user_data=user_data,
            event_source_url=event_source_url,
            event_id=event_id,
            custom_data=custom_data,
        )

        logger.info(f"Sending CompleteRegistration event: method={registration_method}")
        return self._send_event(event)

    def send_custom_event(
        self,
        event_name: str,
        user_data: UserData,
        custom_data: Optional[Dict[str, Any]] = None,
        event_source_url: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        커스텀 이벤트 전송

        표준 이벤트 외의 사용자 정의 이벤트를 전송합니다.

        Args:
            event_name: 이벤트 이름 (예: "WishlistAdd", "Share", "Search")
            user_data: 사용자 데이터
            custom_data: 커스텀 데이터 딕셔너리
            event_source_url: 이벤트 발생 URL
            event_id: 이벤트 ID

        Returns:
            API 응답
        """
        cd = None

        if custom_data:
            cd = CustomData()

            # 지원되는 필드 매핑
            field_mapping = {
                "content_ids": "content_ids",
                "content_name": "content_name",
                "content_type": "content_type",
                "content_category": "content_category",
                "value": "value",
                "currency": "currency",
                "num_items": "num_items",
                "search_string": "search_string",
                "status": "status",
            }

            for key, attr in field_mapping.items():
                if key in custom_data:
                    setattr(cd, attr, custom_data[key])

            # custom_properties로 나머지 데이터 저장
            extra_data = {k: v for k, v in custom_data.items() if k not in field_mapping}
            if extra_data:
                cd.custom_properties = extra_data

        event = self._create_base_event(
            event_name=event_name,
            user_data=user_data,
            event_source_url=event_source_url,
            event_id=event_id,
            custom_data=cd,
        )

        logger.info(f"Sending custom event: {event_name}")
        return self._send_event(event)

    # =========================================================
    # 배치 전송
    # =========================================================

    def batch_send_events(self, events: List[Event]) -> Dict[str, Any]:
        """
        여러 이벤트 일괄 전송

        최대 1000개의 이벤트를 한 번에 전송할 수 있습니다.

        Args:
            events: Event 객체 리스트

        Returns:
            API 응답 딕셔너리
                - events_received: 수신된 이벤트 수
                - messages: 메시지 리스트
                - fbtrace_id: Facebook 추적 ID
        """
        if not events:
            logger.warning("No events to send")
            return {"events_received": 0, "messages": ["No events provided"]}

        if len(events) > 1000:
            logger.warning(f"Event count ({len(events)}) exceeds limit. Truncating to 1000.")
            events = events[:1000]

        try:
            # EventRequest 생성
            request = EventRequest(
                pixel_id=self.pixel_id,
                events=events,
            )

            # 테스트 모드 설정
            if self.test_event_code:
                request.test_event_code = self.test_event_code

            # 이벤트 전송
            response = request.execute()

            # 응답 처리
            result = {
                "success": True,
                "events_received": response.events_received if hasattr(response, 'events_received') else len(events),
                "messages": response.messages if hasattr(response, 'messages') else [],
                "fbtrace_id": response.fbtrace_id if hasattr(response, 'fbtrace_id') else None,
            }

            logger.info(
                f"Successfully sent {result['events_received']} events. "
                f"fbtrace_id: {result['fbtrace_id']}"
            )

            return result

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to send events: {error_msg}")

            return {
                "success": False,
                "events_received": 0,
                "error": error_msg,
                "messages": [f"Error: {error_msg}"],
            }

    # =========================================================
    # 유틸리티 메서드
    # =========================================================

    def create_event_from_dict(
        self,
        event_type: str,
        user_info: Dict[str, Any],
        event_data: Optional[Dict[str, Any]] = None,
        event_source_url: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> Event:
        """
        딕셔너리 데이터로 이벤트 생성

        외부 시스템 연동 시 편리하게 사용할 수 있습니다.

        Args:
            event_type: 이벤트 타입 (PageView, ViewContent, Purchase 등)
            user_info: 사용자 정보 딕셔너리
            event_data: 이벤트 데이터 딕셔너리
            event_source_url: 이벤트 발생 URL
            event_id: 이벤트 ID

        Returns:
            Event 객체
        """
        # 사용자 데이터 생성
        user_data = self.create_user_data(
            email=user_info.get("email"),
            phone=user_info.get("phone"),
            ip=user_info.get("ip"),
            user_agent=user_info.get("user_agent"),
            fbc=user_info.get("fbc"),
            fbp=user_info.get("fbp"),
            external_id=user_info.get("external_id"),
        )

        # CustomData 생성
        custom_data = None
        if event_data:
            custom_data = CustomData()

            if "content_ids" in event_data:
                custom_data.content_ids = event_data["content_ids"]
            if "content_name" in event_data:
                custom_data.content_name = event_data["content_name"]
            if "content_type" in event_data:
                custom_data.content_type = event_data["content_type"]
            if "value" in event_data:
                custom_data.value = event_data["value"]
            if "currency" in event_data:
                custom_data.currency = event_data["currency"]
            if "order_id" in event_data:
                custom_data.order_id = event_data["order_id"]
            if "num_items" in event_data:
                custom_data.num_items = event_data["num_items"]

        return self._create_base_event(
            event_name=event_type,
            user_data=user_data,
            event_source_url=event_source_url,
            event_id=event_id,
            custom_data=custom_data,
        )

    def validate_user_data(self, user_data: UserData) -> Dict[str, Any]:
        """
        사용자 데이터 유효성 검증

        Meta 권장사항에 따라 데이터 품질을 확인합니다.

        Args:
            user_data: 검증할 UserData 객체

        Returns:
            검증 결과 딕셔너리
        """
        result = {
            "valid": True,
            "score": 0,
            "warnings": [],
            "recommendations": [],
        }

        # 필수 매칭 키 체크
        if user_data.email:
            result["score"] += 30
        else:
            result["warnings"].append("이메일이 없습니다.")
            result["recommendations"].append("이메일을 추가하면 매칭률이 향상됩니다.")

        if user_data.phone:
            result["score"] += 30
        else:
            result["warnings"].append("전화번호가 없습니다.")
            result["recommendations"].append("전화번호를 추가하면 매칭률이 향상됩니다.")

        # 추가 신호 체크
        if user_data.client_ip_address:
            result["score"] += 10

        if user_data.client_user_agent:
            result["score"] += 10

        if user_data.fbc:
            result["score"] += 10

        if user_data.fbp:
            result["score"] += 10

        # 점수 기반 유효성 판정
        if result["score"] < 30:
            result["valid"] = False
            result["warnings"].append("매칭 품질이 낮습니다. 더 많은 사용자 정보를 제공해주세요.")

        return result
