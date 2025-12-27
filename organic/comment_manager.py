"""
Instagram 댓글 자동 응답 시스템
=====================================
Instagram Graph API를 사용하여 댓글을 관리하고
AI 기반 자동 응답을 처리합니다.

지원 기능:
- 댓글 조회 (미디어별, 전체)
- 댓글 답글 작성
- 댓글 숨김/삭제
- AI 기반 의도 분석 및 자동 응답
- Webhook 핸들러
- 폴링 모드 (백업)

사용법:
    manager = CommentManager()

    # 최근 댓글 조회
    comments = manager.get_recent_comments(media_id)

    # 자동 응답
    manager.analyze_and_respond(comment_id, "가격 얼마에요?", "user123")

    # 폴링 실행
    manager.run_polling_check()
"""

import os
import json
import time
from datetime import datetime
from typing import List, Dict, Optional, Any, Set
from dataclasses import dataclass, field

import requests

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.meta_credentials import MetaCredentials, get_credentials
from config.claude_api import ClaudeClient, get_claude_client
from utils.logger import get_logger
from utils.slack_notifier import SlackNotifier, get_notifier


# ============================================================
# 응답 템플릿
# ============================================================

RESPONSE_TEMPLATES = {
    "price": "@{user} DM으로 가격 안내 도와드릴게요! 📩",
    "size": "@{user} 사이즈 문의는 DM 확인 부탁드려요 😊",
    "stock": "@{user} 재고 확인해드릴게요! DM 보내드렸습니다 ✨",
    "shipping": "@{user} 배송 정보는 프로필 링크에서 확인 가능해요 🚚",
    "purchase": "@{user} 구매 링크 DM 드렸어요! 💙",
    "compliment": "@{user} 감사합니다! 💕",
}


# ============================================================
# 데이터 클래스
# ============================================================

@dataclass
class Comment:
    """댓글 데이터"""
    id: str
    text: str
    username: str
    timestamp: str
    media_id: Optional[str] = None
    parent_id: Optional[str] = None
    replies_count: int = 0
    like_count: int = 0
    hidden: bool = False


@dataclass
class CommentResponse:
    """댓글 응답 결과"""
    success: bool
    comment_id: Optional[str] = None
    reply_id: Optional[str] = None
    intent: Optional[str] = None
    action: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class WebhookEvent:
    """Webhook 이벤트 데이터"""
    event_type: str
    comment_id: str
    media_id: str
    text: str
    username: str
    timestamp: str


# ============================================================
# CommentManager 클래스
# ============================================================

class CommentManager:
    """
    Instagram 댓글 자동 응답 관리자

    Instagram Graph API를 사용하여 댓글을 조회, 응답, 관리하고
    Claude AI를 활용하여 의도를 분석하고 자동 응답합니다.

    Example:
        >>> manager = CommentManager()
        >>> comments = manager.get_recent_comments(media_id)
        >>> for comment in comments:
        ...     manager.analyze_and_respond(comment.id, comment.text, comment.username)
    """

    # API 설정
    GRAPH_API_BASE = "https://graph.facebook.com"
    DEFAULT_API_VERSION = "v21.0"

    # 폴링 설정
    DEFAULT_POLLING_INTERVAL = 60  # seconds
    RESPONDED_COMMENTS_FILE = ".responded_comments.json"

    def __init__(
        self,
        credentials: Optional[MetaCredentials] = None,
        claude_client: Optional[ClaudeClient] = None,
        slack_notifier: Optional[SlackNotifier] = None,
        api_version: Optional[str] = None
    ):
        """
        CommentManager 초기화

        Args:
            credentials: Meta API 인증 정보 (없으면 환경변수에서 로드)
            claude_client: Claude AI 클라이언트 (없으면 자동 생성)
            slack_notifier: Slack 알림 발송기 (없으면 자동 생성)
            api_version: API 버전 (기본: v21.0)
        """
        self.credentials = credentials or get_credentials()
        self.claude_client = claude_client or get_claude_client()
        self.slack = slack_notifier or get_notifier()
        self.api_version = api_version or self.DEFAULT_API_VERSION
        self.logger = get_logger("comment_manager")

        # Instagram 계정 정보
        self.ig_user_id = self.credentials.instagram_account_id
        self.access_token = self.credentials.access_token

        # 응답 완료 댓글 추적 (in-memory)
        self._responded_comments: Set[str] = set()

        # 파일 기반 추적 로드
        self._load_responded_comments()

        self.logger.info(f"CommentManager 초기화 완료 (IG User ID: {self.ig_user_id})")

    @property
    def base_url(self) -> str:
        """API 기본 URL"""
        return f"{self.GRAPH_API_BASE}/{self.api_version}"

    # ============================================================
    # API 요청 헬퍼
    # ============================================================

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        Graph API 요청 수행

        Args:
            method: HTTP 메서드 (GET, POST, DELETE)
            endpoint: API 엔드포인트
            params: 쿼리 파라미터
            data: POST 데이터
            timeout: 요청 타임아웃 (초)

        Returns:
            API 응답 딕셔너리

        Raises:
            requests.RequestException: API 요청 실패 시
        """
        url = f"{self.base_url}/{endpoint}"

        if params is None:
            params = {}
        params["access_token"] = self.access_token

        self.logger.debug(f"API 요청: {method} {endpoint}")

        try:
            response = requests.request(
                method=method,
                url=url,
                params=params,
                data=data,
                timeout=timeout
            )

            result = response.json()

            # 에러 체크
            if "error" in result:
                error = result["error"]
                error_msg = f"API 에러: {error.get('message', 'Unknown error')} (code: {error.get('code')})"
                self.logger.error(error_msg)
                raise requests.RequestException(error_msg)

            return result

        except requests.exceptions.Timeout:
            self.logger.error(f"API 요청 타임아웃: {endpoint}")
            raise
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API 요청 실패: {e}")
            raise

    # ============================================================
    # 댓글 조회
    # ============================================================

    def get_recent_comments(
        self,
        media_id: str,
        limit: int = 50
    ) -> List[Comment]:
        """
        특정 미디어의 최근 댓글 조회

        Args:
            media_id: 미디어 ID
            limit: 조회할 댓글 수 (최대 50)

        Returns:
            Comment 객체 리스트

        Example:
            >>> comments = manager.get_recent_comments("17895695668004550")
            >>> for c in comments:
            ...     print(f"{c.username}: {c.text}")
        """
        self.logger.info(f"댓글 조회: media_id={media_id}, limit={limit}")

        try:
            params = {
                "fields": "id,text,username,timestamp,like_count,hidden,replies{id,text,username,timestamp}",
                "limit": min(limit, 50)
            }

            result = self._make_request("GET", f"{media_id}/comments", params=params)

            comments = []
            for item in result.get("data", []):
                comment = Comment(
                    id=item.get("id"),
                    text=item.get("text", ""),
                    username=item.get("username", ""),
                    timestamp=item.get("timestamp", ""),
                    media_id=media_id,
                    like_count=item.get("like_count", 0),
                    hidden=item.get("hidden", False),
                    replies_count=len(item.get("replies", {}).get("data", []))
                )
                comments.append(comment)

            self.logger.info(f"댓글 {len(comments)}개 조회 완료")
            return comments

        except Exception as e:
            self.logger.error(f"댓글 조회 실패: {e}")
            return []

    def get_all_media_comments(
        self,
        limit_per_media: int = 25
    ) -> Dict[str, List[Comment]]:
        """
        모든 미디어의 댓글 조회

        계정의 모든 최근 미디어에서 댓글을 조회합니다.

        Args:
            limit_per_media: 미디어당 조회할 댓글 수 (최대 50)

        Returns:
            {media_id: [Comment, ...], ...} 형태의 딕셔너리

        Example:
            >>> all_comments = manager.get_all_media_comments()
            >>> for media_id, comments in all_comments.items():
            ...     print(f"미디어 {media_id}: {len(comments)}개 댓글")
        """
        self.logger.info(f"전체 미디어 댓글 조회 시작")

        all_comments: Dict[str, List[Comment]] = {}

        try:
            # 최근 미디어 목록 조회
            params = {
                "fields": "id,caption,timestamp,comments_count",
                "limit": 25
            }

            result = self._make_request("GET", f"{self.ig_user_id}/media", params=params)

            media_list = result.get("data", [])
            self.logger.info(f"총 {len(media_list)}개 미디어 발견")

            for media in media_list:
                media_id = media.get("id")
                comments_count = media.get("comments_count", 0)

                if comments_count > 0:
                    comments = self.get_recent_comments(media_id, limit=limit_per_media)
                    if comments:
                        all_comments[media_id] = comments

            total_comments = sum(len(c) for c in all_comments.values())
            self.logger.info(f"전체 미디어 댓글 조회 완료: {total_comments}개")

            return all_comments

        except Exception as e:
            self.logger.error(f"전체 미디어 댓글 조회 실패: {e}")
            return {}

    # ============================================================
    # 댓글 답글/관리
    # ============================================================

    def reply_to_comment(
        self,
        comment_id: str,
        message: str
    ) -> Optional[str]:
        """
        댓글에 답글 작성

        Args:
            comment_id: 답글을 달 댓글 ID
            message: 답글 내용

        Returns:
            생성된 답글의 ID (실패 시 None)

        Example:
            >>> reply_id = manager.reply_to_comment(
            ...     comment_id="17895695668004550",
            ...     message="@user123 감사합니다!"
            ... )
        """
        self.logger.info(f"댓글 답글 작성: comment_id={comment_id}")

        try:
            data = {
                "message": message
            }

            result = self._make_request(
                "POST",
                f"{comment_id}/replies",
                data=data
            )

            reply_id = result.get("id")
            self.logger.info(f"답글 작성 완료: reply_id={reply_id}")

            return reply_id

        except Exception as e:
            self.logger.error(f"답글 작성 실패: {e}")
            return None

    def hide_comment(self, comment_id: str) -> bool:
        """
        댓글 숨김 처리

        스팸이나 부적절한 댓글을 숨깁니다.

        Args:
            comment_id: 숨길 댓글 ID

        Returns:
            성공 여부

        Example:
            >>> success = manager.hide_comment("17895695668004550")
        """
        self.logger.info(f"댓글 숨김 처리: comment_id={comment_id}")

        try:
            data = {
                "hide": "true"
            }

            result = self._make_request(
                "POST",
                comment_id,
                data=data
            )

            success = result.get("success", False)
            if success:
                self.logger.info(f"댓글 숨김 완료: {comment_id}")
            else:
                self.logger.warning(f"댓글 숨김 실패: {comment_id}")

            return success

        except Exception as e:
            self.logger.error(f"댓글 숨김 실패: {e}")
            return False

    def delete_comment(self, comment_id: str) -> bool:
        """
        댓글 삭제

        주의: 삭제된 댓글은 복구할 수 없습니다.

        Args:
            comment_id: 삭제할 댓글 ID

        Returns:
            성공 여부

        Example:
            >>> success = manager.delete_comment("17895695668004550")
        """
        self.logger.warning(f"댓글 삭제 요청: comment_id={comment_id}")

        try:
            result = self._make_request("DELETE", comment_id)

            success = result.get("success", False)
            if success:
                self.logger.info(f"댓글 삭제 완료: {comment_id}")
            else:
                self.logger.warning(f"댓글 삭제 실패: {comment_id}")

            return success

        except Exception as e:
            self.logger.error(f"댓글 삭제 실패: {e}")
            return False

    # ============================================================
    # AI 기반 자동 응답
    # ============================================================

    def analyze_and_respond(
        self,
        comment_id: str,
        comment_text: str,
        username: str,
        auto_reply: bool = True
    ) -> CommentResponse:
        """
        AI 기반 댓글 분석 및 자동 응답

        Claude AI를 사용하여 댓글의 의도를 분석하고
        적절한 응답을 자동으로 작성합니다.

        Args:
            comment_id: 댓글 ID
            comment_text: 댓글 내용
            username: 작성자 사용자명
            auto_reply: 자동 답글 작성 여부 (기본: True)

        Returns:
            CommentResponse: 응답 결과 객체

        Example:
            >>> result = manager.analyze_and_respond(
            ...     comment_id="17895695668004550",
            ...     comment_text="가격이 얼마인가요?",
            ...     username="customer123"
            ... )
            >>> print(f"의도: {result.intent}, 응답: {result.action}")
        """
        self.logger.info(f"댓글 분석 시작: {comment_id} - @{username}: {comment_text[:50]}...")

        try:
            # 1. Claude AI로 의도 분석
            intent = self.claude_client.analyze_comment_intent(comment_text)
            self.logger.info(f"의도 분석 결과: {intent}")

            # 2. 스팸 처리
            if intent == "spam":
                self.logger.info(f"스팸 댓글 감지: {comment_id}")
                hide_success = self.hide_comment(comment_id)

                # Slack 알림
                if self.slack.enabled:
                    self.slack.send(
                        message=f"스팸 댓글이 숨김 처리되었습니다.",
                        title="스팸 댓글 감지",
                        color="#ff9800",
                        fields={
                            "댓글 ID": comment_id,
                            "작성자": f"@{username}",
                            "내용": comment_text[:100]
                        }
                    )

                return CommentResponse(
                    success=hide_success,
                    comment_id=comment_id,
                    intent=intent,
                    action="hidden"
                )

            # 3. 응답 템플릿 적용
            template = RESPONSE_TEMPLATES.get(intent)

            if template is None:
                # other 또는 알 수 없는 의도: 응답하지 않음
                self.logger.info(f"자동 응답 대상 아님: intent={intent}")
                return CommentResponse(
                    success=True,
                    comment_id=comment_id,
                    intent=intent,
                    action="skipped"
                )

            # 4. 응답 메시지 생성
            response_message = template.format(user=username)
            self.logger.info(f"응답 메시지: {response_message}")

            # 5. 자동 답글 작성
            reply_id = None
            if auto_reply:
                reply_id = self.reply_to_comment(comment_id, response_message)

                if reply_id:
                    # 응답 완료 기록
                    self._mark_as_responded(comment_id)

                    # Slack 알림
                    if self.slack.enabled:
                        self.slack.send(
                            message=f"댓글에 자동 응답했습니다.",
                            title="자동 응답 완료",
                            color="#4caf50",
                            fields={
                                "의도": intent,
                                "작성자": f"@{username}",
                                "원문": comment_text[:50],
                                "응답": response_message
                            }
                        )

            return CommentResponse(
                success=reply_id is not None if auto_reply else True,
                comment_id=comment_id,
                reply_id=reply_id,
                intent=intent,
                action="replied" if reply_id else "analyzed"
            )

        except Exception as e:
            self.logger.error(f"댓글 분석/응답 실패: {e}")

            # 에러 Slack 알림
            if self.slack.enabled:
                self.slack.notify_error(
                    error_msg=str(e),
                    context=f"댓글 자동 응답 실패 (comment_id: {comment_id})"
                )

            return CommentResponse(
                success=False,
                comment_id=comment_id,
                error_message=str(e)
            )

    def batch_analyze_and_respond(
        self,
        comments: List[Comment],
        auto_reply: bool = True
    ) -> List[CommentResponse]:
        """
        여러 댓글 일괄 분석 및 응답

        Args:
            comments: 처리할 Comment 리스트
            auto_reply: 자동 답글 작성 여부

        Returns:
            CommentResponse 리스트

        Example:
            >>> comments = manager.get_recent_comments(media_id)
            >>> results = manager.batch_analyze_and_respond(comments)
        """
        self.logger.info(f"일괄 댓글 처리 시작: {len(comments)}개")

        results = []
        for comment in comments:
            # 이미 응답한 댓글 건너뛰기
            if self._is_responded(comment.id):
                self.logger.debug(f"이미 응답한 댓글 건너뛰기: {comment.id}")
                continue

            # 숨겨진 댓글 건너뛰기
            if comment.hidden:
                self.logger.debug(f"숨겨진 댓글 건너뛰기: {comment.id}")
                continue

            # 이미 답글이 있는 댓글 건너뛰기
            if comment.replies_count > 0:
                self.logger.debug(f"이미 답글 있는 댓글 건너뛰기: {comment.id}")
                self._mark_as_responded(comment.id)
                continue

            result = self.analyze_and_respond(
                comment_id=comment.id,
                comment_text=comment.text,
                username=comment.username,
                auto_reply=auto_reply
            )
            results.append(result)

            # API 레이트 리밋 방지를 위한 딜레이
            time.sleep(1)

        self.logger.info(f"일괄 댓글 처리 완료: {len(results)}개 처리됨")
        return results

    # ============================================================
    # Webhook 핸들러
    # ============================================================

    def handle_webhook(self, webhook_data: Dict[str, Any]) -> Optional[CommentResponse]:
        """
        Webhook 데이터 처리

        Instagram에서 전송하는 Webhook 이벤트를 파싱하고
        댓글 이벤트에 대해 자동 응답을 트리거합니다.

        Args:
            webhook_data: Instagram Webhook 페이로드

        Returns:
            CommentResponse: 처리 결과 (댓글 이벤트가 아니면 None)

        Webhook 페이로드 구조:
            {
                "entry": [{
                    "id": "...",
                    "time": 1234567890,
                    "changes": [{
                        "field": "comments",
                        "value": {
                            "id": "comment_id",
                            "text": "댓글 내용",
                            "from": {"id": "...", "username": "..."},
                            "media": {"id": "media_id"},
                            "created_time": 1234567890
                        }
                    }]
                }]
            }

        Example:
            >>> # Flask 예시
            >>> @app.route('/webhook', methods=['POST'])
            >>> def webhook():
            ...     data = request.json
            ...     result = manager.handle_webhook(data)
            ...     return 'OK', 200
        """
        self.logger.info("Webhook 이벤트 수신")
        self.logger.debug(f"Webhook 데이터: {json.dumps(webhook_data, ensure_ascii=False)}")

        try:
            # Webhook 구조 파싱
            entries = webhook_data.get("entry", [])

            for entry in entries:
                changes = entry.get("changes", [])

                for change in changes:
                    field = change.get("field")

                    # 댓글 이벤트만 처리
                    if field != "comments":
                        self.logger.debug(f"비댓글 이벤트 무시: field={field}")
                        continue

                    value = change.get("value", {})

                    # 이벤트 데이터 추출
                    event = WebhookEvent(
                        event_type="comment",
                        comment_id=value.get("id", ""),
                        media_id=value.get("media", {}).get("id", ""),
                        text=value.get("text", ""),
                        username=value.get("from", {}).get("username", ""),
                        timestamp=str(value.get("created_time", ""))
                    )

                    # 유효성 검증
                    if not event.comment_id or not event.text or not event.username:
                        self.logger.warning("불완전한 Webhook 이벤트 데이터")
                        continue

                    self.logger.info(
                        f"댓글 Webhook 이벤트: @{event.username} - {event.text[:50]}..."
                    )

                    # 이미 응답한 댓글인지 확인
                    if self._is_responded(event.comment_id):
                        self.logger.debug(f"이미 응답한 댓글: {event.comment_id}")
                        continue

                    # 자동 응답 처리
                    result = self.analyze_and_respond(
                        comment_id=event.comment_id,
                        comment_text=event.text,
                        username=event.username
                    )

                    return result

            self.logger.info("처리할 댓글 이벤트 없음")
            return None

        except Exception as e:
            self.logger.error(f"Webhook 처리 실패: {e}")

            if self.slack.enabled:
                self.slack.notify_error(
                    error_msg=str(e),
                    context="Webhook 처리 실패"
                )

            return None

    def verify_webhook(self, params: Dict[str, str]) -> Optional[str]:
        """
        Webhook 검증 요청 처리

        Instagram Webhook 설정 시 검증 요청에 응답합니다.

        Args:
            params: GET 요청 파라미터
                - hub.mode: "subscribe"
                - hub.verify_token: 설정한 검증 토큰
                - hub.challenge: 반환할 챌린지 값

        Returns:
            hub.challenge 값 (검증 성공 시) 또는 None (실패 시)

        Example:
            >>> # Flask 예시
            >>> @app.route('/webhook', methods=['GET'])
            >>> def webhook_verify():
            ...     challenge = manager.verify_webhook(request.args)
            ...     if challenge:
            ...         return challenge, 200
            ...     return 'Forbidden', 403
        """
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")

        # 환경 변수에서 검증 토큰 가져오기
        verify_token = os.getenv("INSTAGRAM_WEBHOOK_VERIFY_TOKEN", "")

        if mode == "subscribe" and token == verify_token:
            self.logger.info("Webhook 검증 성공")
            return challenge

        self.logger.warning(f"Webhook 검증 실패: mode={mode}, token={token[:10]}...")
        return None

    # ============================================================
    # 폴링 모드
    # ============================================================

    def run_polling_check(
        self,
        limit_per_media: int = 25
    ) -> Dict[str, Any]:
        """
        폴링 모드로 미응답 댓글 확인 및 자동 응답

        모든 미디어의 댓글을 순회하며 아직 응답하지 않은
        댓글에 대해 자동 응답을 수행합니다.
        Webhook의 백업 메커니즘으로 사용됩니다.

        Args:
            limit_per_media: 미디어당 확인할 댓글 수

        Returns:
            처리 결과 요약
            {
                "total_media": 10,
                "total_comments": 50,
                "processed": 5,
                "replied": 3,
                "hidden": 1,
                "skipped": 1,
                "errors": 0
            }

        Example:
            >>> # 단일 실행
            >>> result = manager.run_polling_check()
            >>> print(f"처리: {result['processed']}, 응답: {result['replied']}")

            >>> # 주기적 실행 (cron 또는 스케줄러)
            >>> while True:
            ...     manager.run_polling_check()
            ...     time.sleep(60)  # 1분 간격
        """
        self.logger.info("폴링 체크 시작")

        summary = {
            "total_media": 0,
            "total_comments": 0,
            "processed": 0,
            "replied": 0,
            "hidden": 0,
            "skipped": 0,
            "errors": 0,
            "started_at": datetime.now().isoformat()
        }

        try:
            # 모든 미디어 댓글 조회
            all_comments = self.get_all_media_comments(limit_per_media=limit_per_media)

            summary["total_media"] = len(all_comments)
            summary["total_comments"] = sum(len(c) for c in all_comments.values())

            self.logger.info(
                f"총 {summary['total_media']}개 미디어에서 "
                f"{summary['total_comments']}개 댓글 발견"
            )

            # 각 미디어의 댓글 처리
            for media_id, comments in all_comments.items():
                for comment in comments:
                    # 이미 응답한 댓글 건너뛰기
                    if self._is_responded(comment.id):
                        continue

                    # 숨겨진 댓글 건너뛰기
                    if comment.hidden:
                        continue

                    # 이미 답글이 있는 댓글 건너뛰기
                    if comment.replies_count > 0:
                        self._mark_as_responded(comment.id)
                        continue

                    # 자동 응답 처리
                    try:
                        result = self.analyze_and_respond(
                            comment_id=comment.id,
                            comment_text=comment.text,
                            username=comment.username
                        )

                        summary["processed"] += 1

                        if result.action == "replied":
                            summary["replied"] += 1
                        elif result.action == "hidden":
                            summary["hidden"] += 1
                        elif result.action == "skipped":
                            summary["skipped"] += 1

                        if not result.success:
                            summary["errors"] += 1

                    except Exception as e:
                        self.logger.error(f"댓글 처리 중 오류: {e}")
                        summary["errors"] += 1

                    # API 레이트 리밋 방지
                    time.sleep(1)

            summary["completed_at"] = datetime.now().isoformat()

            self.logger.info(
                f"폴링 체크 완료: "
                f"처리={summary['processed']}, "
                f"응답={summary['replied']}, "
                f"숨김={summary['hidden']}, "
                f"스킵={summary['skipped']}, "
                f"오류={summary['errors']}"
            )

            # 일일 요약 Slack 알림 (처리된 항목이 있을 때만)
            if summary["processed"] > 0 and self.slack.enabled:
                self.slack.send(
                    message="댓글 자동 응답 폴링 완료",
                    title="폴링 체크 완료",
                    color="#2196f3",
                    fields={
                        "확인 댓글": str(summary["total_comments"]),
                        "처리됨": str(summary["processed"]),
                        "자동 응답": str(summary["replied"]),
                        "스팸 숨김": str(summary["hidden"])
                    }
                )

            return summary

        except Exception as e:
            self.logger.error(f"폴링 체크 실패: {e}")
            summary["errors"] += 1
            summary["error_message"] = str(e)

            if self.slack.enabled:
                self.slack.notify_error(
                    error_msg=str(e),
                    context="폴링 체크 실패"
                )

            return summary

    def start_polling_loop(
        self,
        interval: int = None,
        limit_per_media: int = 25
    ):
        """
        폴링 루프 시작 (무한 루프)

        지정된 간격으로 폴링 체크를 반복 실행합니다.
        Ctrl+C로 중단할 수 있습니다.

        Args:
            interval: 폴링 간격 (초, 기본: 60)
            limit_per_media: 미디어당 확인할 댓글 수

        Example:
            >>> # 60초 간격으로 폴링 시작
            >>> manager.start_polling_loop(interval=60)
        """
        interval = interval or self.DEFAULT_POLLING_INTERVAL

        self.logger.info(f"폴링 루프 시작: {interval}초 간격")

        try:
            while True:
                self.run_polling_check(limit_per_media=limit_per_media)
                self.logger.debug(f"{interval}초 대기 중...")
                time.sleep(interval)

        except KeyboardInterrupt:
            self.logger.info("폴링 루프 중단됨 (KeyboardInterrupt)")

    # ============================================================
    # 응답 추적 관리
    # ============================================================

    def _is_responded(self, comment_id: str) -> bool:
        """댓글에 이미 응답했는지 확인"""
        return comment_id in self._responded_comments

    def _mark_as_responded(self, comment_id: str):
        """댓글을 응답 완료로 표시"""
        self._responded_comments.add(comment_id)
        self._save_responded_comments()

    def _load_responded_comments(self):
        """파일에서 응답 완료 댓글 목록 로드"""
        try:
            if os.path.exists(self.RESPONDED_COMMENTS_FILE):
                with open(self.RESPONDED_COMMENTS_FILE, "r") as f:
                    data = json.load(f)
                    self._responded_comments = set(data.get("comment_ids", []))
                    self.logger.debug(
                        f"응답 완료 댓글 {len(self._responded_comments)}개 로드됨"
                    )
        except Exception as e:
            self.logger.warning(f"응답 완료 댓글 로드 실패: {e}")
            self._responded_comments = set()

    def _save_responded_comments(self):
        """응답 완료 댓글 목록을 파일에 저장"""
        try:
            # 최근 1000개만 유지 (메모리/파일 크기 관리)
            if len(self._responded_comments) > 1000:
                self._responded_comments = set(
                    list(self._responded_comments)[-1000:]
                )

            data = {
                "comment_ids": list(self._responded_comments),
                "updated_at": datetime.now().isoformat()
            }

            with open(self.RESPONDED_COMMENTS_FILE, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            self.logger.warning(f"응답 완료 댓글 저장 실패: {e}")

    def clear_responded_comments(self):
        """응답 완료 댓글 기록 초기화"""
        self._responded_comments.clear()
        if os.path.exists(self.RESPONDED_COMMENTS_FILE):
            os.remove(self.RESPONDED_COMMENTS_FILE)
        self.logger.info("응답 완료 댓글 기록 초기화됨")

    # ============================================================
    # 유틸리티 메서드
    # ============================================================

    def get_comment_details(self, comment_id: str) -> Optional[Comment]:
        """
        특정 댓글 상세 정보 조회

        Args:
            comment_id: 댓글 ID

        Returns:
            Comment 객체 (실패 시 None)
        """
        self.logger.debug(f"댓글 상세 조회: {comment_id}")

        try:
            params = {
                "fields": "id,text,username,timestamp,like_count,hidden,parent_id"
            }

            result = self._make_request("GET", comment_id, params=params)

            return Comment(
                id=result.get("id"),
                text=result.get("text", ""),
                username=result.get("username", ""),
                timestamp=result.get("timestamp", ""),
                parent_id=result.get("parent_id"),
                like_count=result.get("like_count", 0),
                hidden=result.get("hidden", False)
            )

        except Exception as e:
            self.logger.error(f"댓글 상세 조회 실패: {e}")
            return None

    def get_response_stats(self) -> Dict[str, int]:
        """
        응답 통계 조회

        Returns:
            {
                "total_responded": 150,
                "pending_in_memory": 150
            }
        """
        return {
            "total_responded": len(self._responded_comments),
            "pending_in_memory": len(self._responded_comments)
        }


# ============================================================
# 싱글톤 인스턴스
# ============================================================

_manager: Optional[CommentManager] = None


def get_comment_manager() -> CommentManager:
    """전역 CommentManager 반환"""
    global _manager
    if _manager is None:
        _manager = CommentManager()
    return _manager
