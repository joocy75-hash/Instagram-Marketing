"""
Instagram DM 자동 응답 시스템
=====================================
Direct Message 관리 및 자동 응답 처리

주요 기능:
- 대화 목록 및 메시지 조회
- 텍스트/이미지/Quick Reply 발송
- Ice Breaker 설정
- Webhook 기반 자동 응답
- AI 기반 자유 응답 (Claude)
"""

import json
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

# 프로젝트 모듈 임포트
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.meta_credentials import MetaCredentials, get_credentials
from config.claude_api import ClaudeClient, get_claude_client
from utils.logger import get_logger
from utils.slack_notifier import SlackNotifier, get_notifier


# ============================================================
# Ice Breaker 설정
# ============================================================

ICE_BREAKERS = [
    {"question": "가격이 궁금하신가요?", "payload": "PRICE_INQUIRY"},
    {"question": "사이즈 문의하기", "payload": "SIZE_INQUIRY"},
    {"question": "지금 구매하기", "payload": "PURCHASE_INTENT"},
    {"question": "배송 정보 확인", "payload": "SHIPPING_INFO"},
]


# ============================================================
# DM 응답 템플릿
# ============================================================

DM_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "PRICE_INQUIRY": {
        "text": "안녕하세요! 가격 문의 감사합니다\n\n상품 가격은 프로필 링크에서 확인하실 수 있어요!",
        "quick_replies": ["더 자세히 보기", "바로 구매하기"],
    },
    "SIZE_INQUIRY": {
        "text": "사이즈가 궁금하시군요!\n\n어떤 사이즈를 찾으시나요?",
        "quick_replies": ["S", "M", "L", "XL", "사이즈 표 보기"],
    },
    "PURCHASE_INTENT": {
        "text": "구매를 원하시나요?\n\n프로필 링크에서 바로 주문 가능합니다!",
        "quick_replies": ["프로필 링크 가기", "다른 상품 보기"],
    },
    "SHIPPING_INFO": {
        "text": "배송 정보 안내드려요\n\n- 평균 2-3일 소요\n- 3만원 이상 무료배송",
        "quick_replies": ["주문 추적하기", "더 궁금한 점 있어요"],
    },
}


# ============================================================
# DM 응답 데이터 클래스
# ============================================================


@dataclass
class DmMessage:
    """DM 메시지 데이터"""

    message_id: str
    sender_id: str
    recipient_id: str
    text: Optional[str]
    timestamp: datetime
    attachments: Optional[List[Dict]] = None
    is_echo: bool = False


@dataclass
class DmConversation:
    """DM 대화 데이터"""

    conversation_id: str
    participants: List[str]
    updated_time: datetime
    message_count: int = 0


# ============================================================
# DM Manager 클래스
# ============================================================


class DmManager:
    """Instagram DM 관리자"""

    def __init__(
        self,
        credentials: Optional[MetaCredentials] = None,
        claude_client: Optional[ClaudeClient] = None,
        slack_notifier: Optional[SlackNotifier] = None,
    ):
        """
        DM Manager 초기화

        Args:
            credentials: Meta API 인증 정보 (기본: 환경변수에서 로드)
            claude_client: Claude AI 클라이언트 (기본: 환경변수에서 로드)
            slack_notifier: Slack 알림 클라이언트 (기본: 환경변수에서 로드)
        """
        self.credentials = credentials or get_credentials()
        self.claude_client = claude_client or get_claude_client()
        self.slack = slack_notifier or get_notifier()
        self.logger = get_logger("dm_manager")

        # API 기본 설정
        self.base_url = self.credentials.get_graph_url()
        self.ig_account_id = self.credentials.instagram_account_id
        self.access_token = self.credentials.access_token

        self.logger.info(f"DmManager 초기화 완료 - IG Account: {self.ig_account_id}")

    # ============================================================
    # 헬퍼 메서드
    # ============================================================

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
    ) -> Dict:
        """
        Graph API 요청 실행

        Args:
            method: HTTP 메서드 (GET, POST, DELETE)
            endpoint: API 엔드포인트
            params: URL 파라미터
            data: POST 데이터

        Returns:
            API 응답 JSON
        """
        url = f"{self.base_url}/{endpoint}"

        # access_token 추가
        if params is None:
            params = {}
        params["access_token"] = self.access_token

        try:
            if method == "GET":
                response = requests.get(url, params=params)
            elif method == "POST":
                response = requests.post(url, params=params, json=data)
            elif method == "DELETE":
                response = requests.delete(url, params=params)
            else:
                raise ValueError(f"지원하지 않는 HTTP 메서드: {method}")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                error_detail = response.json()
            except Exception:
                error_detail = response.text

            self.logger.error(f"API 요청 실패: {e} - {error_detail}")
            raise Exception(f"Graph API 오류: {error_detail}")

    # ============================================================
    # 대화 및 메시지 조회
    # ============================================================

    def get_conversations(self, limit: int = 20) -> List[DmConversation]:
        """
        대화 목록 조회

        Args:
            limit: 조회할 대화 수 (기본: 20)

        Returns:
            DmConversation 객체 리스트
        """
        self.logger.info(f"대화 목록 조회 - limit: {limit}")

        endpoint = f"{self.ig_account_id}/conversations"
        params = {
            "platform": "instagram",
            "fields": "id,participants,updated_time,message_count",
            "limit": limit,
        }

        result = self._make_request("GET", endpoint, params)
        conversations = []

        for conv_data in result.get("data", []):
            # participants 처리
            participants = []
            if "participants" in conv_data:
                participants = [
                    p.get("id") for p in conv_data["participants"].get("data", [])
                ]

            # updated_time 파싱
            updated_time = datetime.now()
            if "updated_time" in conv_data:
                updated_time = datetime.fromisoformat(
                    conv_data["updated_time"].replace("Z", "+00:00")
                )

            conversation = DmConversation(
                conversation_id=conv_data["id"],
                participants=participants,
                updated_time=updated_time,
                message_count=conv_data.get("message_count", 0),
            )
            conversations.append(conversation)

        self.logger.info(f"총 {len(conversations)}개 대화 조회 완료")
        return conversations

    def get_messages(
        self, conversation_id: str, limit: int = 10
    ) -> List[DmMessage]:
        """
        대화 내 메시지 조회

        Args:
            conversation_id: 대화 ID
            limit: 조회할 메시지 수 (기본: 10)

        Returns:
            DmMessage 객체 리스트
        """
        self.logger.info(f"메시지 조회 - conversation: {conversation_id}, limit: {limit}")

        endpoint = f"{conversation_id}/messages"
        params = {
            "fields": "id,message,from,to,created_time,attachments,is_echo",
            "limit": limit,
        }

        result = self._make_request("GET", endpoint, params)
        messages = []

        for msg_data in result.get("data", []):
            # timestamp 파싱
            created_time = datetime.now()
            if "created_time" in msg_data:
                created_time = datetime.fromisoformat(
                    msg_data["created_time"].replace("Z", "+00:00")
                )

            # from/to 처리
            sender_id = msg_data.get("from", {}).get("id", "")
            recipient_id = ""
            if "to" in msg_data and "data" in msg_data["to"]:
                to_list = msg_data["to"]["data"]
                if to_list:
                    recipient_id = to_list[0].get("id", "")

            # attachments 처리
            attachments = None
            if "attachments" in msg_data:
                attachments = msg_data["attachments"].get("data", [])

            message = DmMessage(
                message_id=msg_data["id"],
                sender_id=sender_id,
                recipient_id=recipient_id,
                text=msg_data.get("message"),
                timestamp=created_time,
                attachments=attachments,
                is_echo=msg_data.get("is_echo", False),
            )
            messages.append(message)

        self.logger.info(f"총 {len(messages)}개 메시지 조회 완료")
        return messages

    # ============================================================
    # 메시지 발송
    # ============================================================

    def send_message(self, recipient_id: str, text: str) -> Dict:
        """
        텍스트 메시지 발송

        Args:
            recipient_id: 수신자 Instagram 사용자 ID
            text: 메시지 텍스트

        Returns:
            API 응답
        """
        self.logger.info(f"메시지 발송 - recipient: {recipient_id}")

        endpoint = f"{self.ig_account_id}/messages"
        data = {
            "recipient": {"id": recipient_id},
            "message": {"text": text},
        }

        result = self._make_request("POST", endpoint, data=data)
        self.logger.info(f"메시지 발송 완료 - message_id: {result.get('message_id')}")

        return result

    def send_image(self, recipient_id: str, image_url: str) -> Dict:
        """
        이미지 메시지 발송

        Args:
            recipient_id: 수신자 Instagram 사용자 ID
            image_url: 이미지 URL

        Returns:
            API 응답
        """
        self.logger.info(f"이미지 발송 - recipient: {recipient_id}")

        endpoint = f"{self.ig_account_id}/messages"
        data = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "image",
                    "payload": {"url": image_url},
                }
            },
        }

        result = self._make_request("POST", endpoint, data=data)
        self.logger.info(f"이미지 발송 완료 - message_id: {result.get('message_id')}")

        return result

    def send_quick_replies(
        self, recipient_id: str, text: str, options: List[str]
    ) -> Dict:
        """
        Quick Reply 버튼이 포함된 메시지 발송

        Args:
            recipient_id: 수신자 Instagram 사용자 ID
            text: 메시지 텍스트
            options: Quick Reply 옵션 텍스트 리스트

        Returns:
            API 응답
        """
        self.logger.info(
            f"Quick Reply 발송 - recipient: {recipient_id}, options: {len(options)}개"
        )

        # Quick Reply 구성 (최대 13개)
        quick_replies = []
        for option in options[:13]:
            quick_replies.append(
                {
                    "content_type": "text",
                    "title": option,
                    "payload": option.upper().replace(" ", "_"),
                }
            )

        endpoint = f"{self.ig_account_id}/messages"
        data = {
            "recipient": {"id": recipient_id},
            "message": {
                "text": text,
                "quick_replies": quick_replies,
            },
        }

        result = self._make_request("POST", endpoint, data=data)
        self.logger.info(f"Quick Reply 발송 완료 - message_id: {result.get('message_id')}")

        return result

    # ============================================================
    # Ice Breaker 설정
    # ============================================================

    def setup_ice_breakers(
        self, ice_breakers: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Ice Breaker 설정

        Args:
            ice_breakers: Ice Breaker 리스트 (기본: ICE_BREAKERS 상수 사용)
                [{"question": "...", "payload": "..."}, ...]

        Returns:
            API 응답
        """
        if ice_breakers is None:
            ice_breakers = ICE_BREAKERS

        self.logger.info(f"Ice Breaker 설정 - {len(ice_breakers)}개")

        endpoint = f"{self.ig_account_id}/messenger_profile"
        data = {"ice_breakers": ice_breakers}

        result = self._make_request("POST", endpoint, data=data)
        self.logger.info("Ice Breaker 설정 완료")

        return result

    def get_ice_breakers(self) -> List[Dict]:
        """
        현재 Ice Breaker 설정 조회

        Returns:
            Ice Breaker 리스트
        """
        self.logger.info("Ice Breaker 조회")

        endpoint = f"{self.ig_account_id}/messenger_profile"
        params = {"fields": "ice_breakers"}

        result = self._make_request("GET", endpoint, params)

        ice_breakers = result.get("data", [{}])[0].get("ice_breakers", [])
        self.logger.info(f"Ice Breaker {len(ice_breakers)}개 조회 완료")

        return ice_breakers

    def delete_ice_breakers(self) -> Dict:
        """
        Ice Breaker 삭제

        Returns:
            API 응답
        """
        self.logger.info("Ice Breaker 삭제")

        endpoint = f"{self.ig_account_id}/messenger_profile"
        params = {"fields": "ice_breakers"}

        result = self._make_request("DELETE", endpoint, params)
        self.logger.info("Ice Breaker 삭제 완료")

        return result

    # ============================================================
    # 자동 응답 시스템
    # ============================================================

    def handle_dm_webhook(self, webhook_data: Dict) -> Optional[Dict]:
        """
        DM Webhook 처리

        Args:
            webhook_data: Webhook 페이로드

        Returns:
            응답 결과 또는 None
        """
        self.logger.info("Webhook 수신")

        try:
            # Webhook 데이터 파싱
            entry = webhook_data.get("entry", [])
            if not entry:
                self.logger.warning("빈 Webhook 데이터")
                return None

            for e in entry:
                messaging = e.get("messaging", [])
                for msg_event in messaging:
                    sender_id = msg_event.get("sender", {}).get("id")
                    recipient_id = msg_event.get("recipient", {}).get("id")

                    # 자신의 메시지(에코) 무시
                    if sender_id == self.ig_account_id:
                        continue

                    # 메시지 처리
                    if "message" in msg_event:
                        message = msg_event["message"]
                        text = message.get("text", "")

                        # Quick Reply payload 확인
                        quick_reply = message.get("quick_reply", {})
                        payload = quick_reply.get("payload")

                        return self.process_message(
                            sender_id=sender_id,
                            message_text=text,
                            payload=payload,
                        )

                    # Postback (Ice Breaker) 처리
                    if "postback" in msg_event:
                        postback = msg_event["postback"]
                        payload = postback.get("payload")

                        return self.process_message(
                            sender_id=sender_id,
                            message_text="",
                            payload=payload,
                        )

        except Exception as e:
            self.logger.error(f"Webhook 처리 오류: {e}")
            self.slack.notify_error(str(e), "DM Webhook 처리")
            raise

        return None

    def process_message(
        self,
        sender_id: str,
        message_text: str,
        payload: Optional[str] = None,
    ) -> Dict:
        """
        메시지/페이로드 처리 및 자동 응답

        Args:
            sender_id: 발신자 ID
            message_text: 메시지 텍스트
            payload: Ice Breaker 또는 Quick Reply payload

        Returns:
            응답 결과
        """
        self.logger.info(
            f"메시지 처리 - sender: {sender_id}, text: {message_text[:50] if message_text else 'N/A'}, payload: {payload}"
        )

        try:
            # 1. payload가 있으면 템플릿 응답
            if payload and payload in DM_TEMPLATES:
                return self._send_template_response(sender_id, payload)

            # 2. Quick Reply 텍스트 매칭 시도
            normalized_text = message_text.upper().replace(" ", "_")
            if normalized_text in DM_TEMPLATES:
                return self._send_template_response(sender_id, normalized_text)

            # 3. 키워드 기반 의도 분류
            intent = self._detect_intent(message_text)
            if intent:
                return self._send_template_response(sender_id, intent)

            # 4. AI 기반 자유 응답
            ai_response = self.generate_ai_response(message_text)
            return self.send_message(sender_id, ai_response)

        except Exception as e:
            self.logger.error(f"메시지 처리 오류: {e}")
            self.slack.notify_error(str(e), f"DM 응답 처리 - sender: {sender_id}")
            raise

    def _detect_intent(self, message_text: str) -> Optional[str]:
        """
        메시지에서 의도 감지 (키워드 기반)

        Args:
            message_text: 메시지 텍스트

        Returns:
            감지된 의도 또는 None
        """
        text_lower = message_text.lower()

        intent_keywords = {
            "PRICE_INQUIRY": ["가격", "얼마", "price", "비용", "금액"],
            "SIZE_INQUIRY": ["사이즈", "크기", "size", "치수", "호수"],
            "PURCHASE_INTENT": ["구매", "주문", "사고싶", "살래", "buy", "order"],
            "SHIPPING_INFO": ["배송", "배달", "택배", "shipping", "delivery"],
        }

        for intent, keywords in intent_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return intent

        return None

    def _send_template_response(self, recipient_id: str, intent: str) -> Dict:
        """
        템플릿 기반 응답 발송

        Args:
            recipient_id: 수신자 ID
            intent: 의도 키

        Returns:
            API 응답
        """
        template = DM_TEMPLATES.get(intent)
        if not template:
            return self.send_message(recipient_id, "문의해 주셔서 감사합니다!")

        text = template["text"]
        quick_replies = template.get("quick_replies", [])

        if quick_replies:
            return self.send_quick_replies(recipient_id, text, quick_replies)
        else:
            return self.send_message(recipient_id, text)

    def get_auto_reply(self, intent: str) -> Dict:
        """
        의도별 자동 응답 생성

        Args:
            intent: 의도 키 (PRICE_INQUIRY, SIZE_INQUIRY 등)

        Returns:
            응답 데이터 {"text": "...", "quick_replies": [...]}
        """
        template = DM_TEMPLATES.get(intent)
        if template:
            return template.copy()

        # 기본 응답
        return {
            "text": "문의해 주셔서 감사합니다! 곧 답변 드리겠습니다.",
            "quick_replies": [],
        }

    # ============================================================
    # AI 기반 자유 응답
    # ============================================================

    def generate_ai_response(
        self,
        message_text: str,
        context: Optional[Dict] = None,
    ) -> str:
        """
        AI 기반 자유 응답 생성 (Claude 활용)

        Args:
            message_text: 사용자 메시지
            context: 추가 컨텍스트 정보 (이전 대화, 상품 정보 등)

        Returns:
            AI 생성 응답 텍스트
        """
        self.logger.info(f"AI 응답 생성 - message: {message_text[:50]}")

        # 시스템 프롬프트
        system_prompt = """당신은 Instagram 쇼핑몰의 친절한 고객 상담 AI입니다.

응답 가이드라인:
1. 친근하고 따뜻한 톤으로 응답하세요
2. 답변은 2-3문장으로 간결하게 작성하세요
3. 구매 전환을 자연스럽게 유도하세요
4. 모르는 질문에는 "담당자가 곧 답변 드릴게요"라고 안내하세요
5. 불필요한 이모지 사용을 자제하세요

상점 정보:
- 평균 배송: 2-3일
- 3만원 이상 무료배송
- 교환/환불: 7일 이내 가능
"""

        # 컨텍스트 구성
        user_message = message_text
        if context:
            context_info = json.dumps(context, ensure_ascii=False)
            user_message = f"[컨텍스트]\n{context_info}\n\n[고객 메시지]\n{message_text}"

        try:
            response = self.claude_client.client.messages.create(
                model=self.claude_client.config.model,
                max_tokens=300,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )

            ai_response = response.content[0].text.strip()
            self.logger.info(f"AI 응답 생성 완료: {ai_response[:50]}...")

            return ai_response

        except Exception as e:
            self.logger.error(f"AI 응답 생성 실패: {e}")
            # 폴백 응답
            return "문의해 주셔서 감사합니다! 담당자가 확인 후 곧 답변 드릴게요."

    # ============================================================
    # 대화 컨텍스트 관리
    # ============================================================

    def get_conversation_context(
        self, sender_id: str, message_limit: int = 5
    ) -> Dict:
        """
        발신자와의 대화 컨텍스트 조회

        Args:
            sender_id: 발신자 ID
            message_limit: 조회할 이전 메시지 수

        Returns:
            컨텍스트 정보 {"previous_messages": [...], "last_interaction": ...}
        """
        try:
            # 해당 사용자와의 대화 찾기
            conversations = self.get_conversations(limit=50)

            for conv in conversations:
                if sender_id in conv.participants:
                    messages = self.get_messages(
                        conv.conversation_id, limit=message_limit
                    )

                    return {
                        "conversation_id": conv.conversation_id,
                        "previous_messages": [
                            {
                                "sender": msg.sender_id,
                                "text": msg.text,
                                "timestamp": msg.timestamp.isoformat(),
                            }
                            for msg in messages
                        ],
                        "last_interaction": conv.updated_time.isoformat(),
                    }

            return {"previous_messages": [], "last_interaction": None}

        except Exception as e:
            self.logger.warning(f"대화 컨텍스트 조회 실패: {e}")
            return {"previous_messages": [], "last_interaction": None}

    # ============================================================
    # 통계 및 알림
    # ============================================================

    def notify_new_dm(
        self, sender_id: str, message_text: str, auto_replied: bool = True
    ):
        """
        새 DM 수신 Slack 알림

        Args:
            sender_id: 발신자 ID
            message_text: 메시지 내용
            auto_replied: 자동 응답 여부
        """
        status = "자동 응답 완료" if auto_replied else "수동 응답 필요"

        self.slack.send(
            message=f"새 DM이 도착했습니다: {message_text[:50]}...",
            title="Instagram DM",
            color="#833ab4",  # Instagram 색상
            fields={
                "발신자": sender_id,
                "상태": status,
            },
        )


# ============================================================
# 편의 함수
# ============================================================


def get_dm_manager() -> DmManager:
    """전역 DmManager 인스턴스 반환"""
    return DmManager()


# ============================================================
# CLI 테스트
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Instagram DM Manager")
    parser.add_argument(
        "--action",
        choices=[
            "conversations",
            "messages",
            "setup-ice-breakers",
            "get-ice-breakers",
            "test-ai",
        ],
        required=True,
        help="실행할 액션",
    )
    parser.add_argument(
        "--conversation-id",
        help="대화 ID (messages 액션용)",
    )
    parser.add_argument(
        "--message",
        help="테스트 메시지 (test-ai 액션용)",
    )

    args = parser.parse_args()

    dm_manager = DmManager()

    if args.action == "conversations":
        conversations = dm_manager.get_conversations()
        print(f"\n=== 대화 목록 ({len(conversations)}개) ===")
        for conv in conversations:
            print(f"- ID: {conv.conversation_id}")
            print(f"  참여자: {conv.participants}")
            print(f"  업데이트: {conv.updated_time}")
            print()

    elif args.action == "messages":
        if not args.conversation_id:
            print("--conversation-id 필요")
            exit(1)

        messages = dm_manager.get_messages(args.conversation_id)
        print(f"\n=== 메시지 목록 ({len(messages)}개) ===")
        for msg in messages:
            print(f"- [{msg.timestamp}] {msg.sender_id}: {msg.text}")

    elif args.action == "setup-ice-breakers":
        result = dm_manager.setup_ice_breakers()
        print(f"Ice Breaker 설정 완료: {result}")

    elif args.action == "get-ice-breakers":
        ice_breakers = dm_manager.get_ice_breakers()
        print(f"\n=== Ice Breakers ({len(ice_breakers)}개) ===")
        for ib in ice_breakers:
            print(f"- {ib}")

    elif args.action == "test-ai":
        message = args.message or "이 제품 사이즈 추천해주세요"
        response = dm_manager.generate_ai_response(message)
        print(f"\n입력: {message}")
        print(f"AI 응답: {response}")
