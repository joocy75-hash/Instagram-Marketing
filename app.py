"""
Instagram Webhook 처리 Flask 서버
=====================================
Instagram/Meta Webhook 이벤트 수신 및 처리

주요 기능:
- Webhook 검증 (GET)
- Webhook 이벤트 수신 (POST)
- 댓글/DM/멘션 이벤트 라우팅
- CAPI 구매 이벤트 수신
- 헬스체크 및 상태 모니터링

사용법:
    python app.py

환경 변수:
    - VERIFY_TOKEN: Webhook 검증 토큰
    - PORT: 서버 포트 (기본값: 5000)
    - FLASK_ENV: 환경 (development/production)
"""

import os
import traceback
from datetime import datetime
from typing import Any, Dict, Optional

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 프로젝트 모듈 임포트
from config.meta_credentials import MetaCredentials, get_credentials
from integrations.capi_server import CapiServer
from utils.logger import get_logger
from utils.slack_notifier import SlackNotifier, get_notifier

# 로거 설정
logger = get_logger("webhook_server")

# ============================================================
# Flask 앱 초기화
# ============================================================

app = Flask(__name__)

# CORS 활성화 - 모든 도메인 허용
CORS(app, resources={r"/*": {"origins": "*"}})

# JSON 설정
app.config["JSON_AS_ASCII"] = False  # 한글 지원
app.config["JSON_SORT_KEYS"] = False

# Webhook 검증 토큰 (환경 변수에서 로드)
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "instagram_marketing_webhook_2025")


# ============================================================
# 모듈 매니저 클래스 (향후 구현용 스텁)
# ============================================================

class CommentManager:
    """
    댓글 관리 매니저 (스텁)

    향후 organic/comment_manager.py에서 구현될 클래스입니다.
    댓글 이벤트 처리 및 자동 응답 기능을 담당합니다.
    """

    def __init__(self, credentials: Optional[MetaCredentials] = None):
        self.credentials = credentials or get_credentials()
        self.logger = get_logger("comment_manager")

    def handle_webhook(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        댓글 Webhook 이벤트 처리

        Args:
            event_data: Webhook 이벤트 데이터
                - id: 댓글 ID
                - text: 댓글 내용
                - media: 미디어 정보
                - from: 작성자 정보

        Returns:
            처리 결과
        """
        comment_id = event_data.get("id", "unknown")
        text = event_data.get("text", "")
        from_user = event_data.get("from", {})
        username = from_user.get("username", "unknown")

        self.logger.info(f"Comment received: id={comment_id}, from={username}, text={text[:50]}...")

        # TODO: 댓글 의도 분석 및 자동 응답 로직 구현
        # 1. 의도 분류 (가격, 사이즈, 재고 등)
        # 2. 자동 응답 생성
        # 3. 응답 포스팅

        return {
            "status": "processed",
            "comment_id": comment_id,
            "username": username,
            "action": "logged"  # TODO: "replied"로 변경
        }


class DmManager:
    """
    DM 관리 매니저 (스텁)

    향후 organic/dm_manager.py에서 구현될 클래스입니다.
    DM 수신 및 자동 응답 기능을 담당합니다.
    """

    def __init__(self, credentials: Optional[MetaCredentials] = None):
        self.credentials = credentials or get_credentials()
        self.logger = get_logger("dm_manager")

    def handle_dm_webhook(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        DM Webhook 이벤트 처리

        Args:
            event_data: Webhook 이벤트 데이터
                - sender: 발신자 정보
                - recipient: 수신자 정보
                - message: 메시지 내용

        Returns:
            처리 결과
        """
        sender = event_data.get("sender", {})
        sender_id = sender.get("id", "unknown")
        message = event_data.get("message", {})
        text = message.get("text", "") if isinstance(message, dict) else str(message)

        self.logger.info(f"DM received: from={sender_id}, text={text[:50] if text else 'N/A'}...")

        # TODO: DM 자동 응답 로직 구현
        # 1. 메시지 의도 분석
        # 2. Ice Breaker 응답 또는 자연어 응답
        # 3. 응답 발송

        return {
            "status": "processed",
            "sender_id": sender_id,
            "action": "logged"  # TODO: "replied"로 변경
        }


# ============================================================
# 전역 인스턴스 초기화
# ============================================================

# 지연 초기화를 위한 변수
_comment_manager: Optional[CommentManager] = None
_dm_manager: Optional[DmManager] = None
_capi_server: Optional[CapiServer] = None
_slack_notifier: Optional[SlackNotifier] = None


def get_comment_manager() -> CommentManager:
    """CommentManager 싱글톤 반환"""
    global _comment_manager
    if _comment_manager is None:
        try:
            _comment_manager = CommentManager()
        except Exception as e:
            logger.warning(f"CommentManager 초기화 실패: {e}")
            _comment_manager = CommentManager.__new__(CommentManager)
            _comment_manager.logger = get_logger("comment_manager")
    return _comment_manager


def get_dm_manager() -> DmManager:
    """DmManager 싱글톤 반환"""
    global _dm_manager
    if _dm_manager is None:
        try:
            _dm_manager = DmManager()
        except Exception as e:
            logger.warning(f"DmManager 초기화 실패: {e}")
            _dm_manager = DmManager.__new__(DmManager)
            _dm_manager.logger = get_logger("dm_manager")
    return _dm_manager


def get_capi_server() -> Optional[CapiServer]:
    """CapiServer 싱글톤 반환"""
    global _capi_server
    if _capi_server is None:
        try:
            _capi_server = CapiServer()
        except Exception as e:
            logger.warning(f"CapiServer 초기화 실패: {e}")
            return None
    return _capi_server


def get_slack() -> SlackNotifier:
    """SlackNotifier 싱글톤 반환"""
    global _slack_notifier
    if _slack_notifier is None:
        _slack_notifier = get_notifier()
    return _slack_notifier


# ============================================================
# Webhook 엔드포인트
# ============================================================

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """
    Instagram Webhook 메인 엔드포인트

    GET: Meta에서 Webhook 검증 요청
        - hub.mode: subscribe
        - hub.verify_token: 검증 토큰
        - hub.challenge: 챌린지 값 (반환해야 함)

    POST: Webhook 이벤트 수신
        - object: "instagram"
        - entry: 이벤트 목록

    Returns:
        GET: hub.challenge 값
        POST: {"status": "ok"}
    """

    if request.method == 'GET':
        # Webhook 검증 처리
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')

        logger.info(f"Webhook verification: mode={mode}, token={token[:10]}..." if token else "No token")

        if mode == 'subscribe' and token == VERIFY_TOKEN:
            logger.info("Webhook verified successfully")
            return challenge, 200
        else:
            logger.warning(f"Webhook verification failed: invalid token or mode")
            return "Forbidden", 403

    elif request.method == 'POST':
        # Webhook 이벤트 처리
        try:
            data = request.get_json()

            if not data:
                logger.warning("Empty webhook payload received")
                return jsonify({"status": "error", "message": "Empty payload"}), 400

            logger.info(f"Webhook received: object={data.get('object')}")

            # Instagram 객체 확인
            if data.get('object') != 'instagram':
                logger.warning(f"Unknown object type: {data.get('object')}")
                return jsonify({"status": "ok", "message": "Unknown object type"}), 200

            # 엔트리 처리
            entries = data.get('entry', [])
            results = []

            for entry in entries:
                entry_id = entry.get('id')
                timestamp = entry.get('time')
                changes = entry.get('changes', [])

                logger.info(f"Processing entry: id={entry_id}, changes={len(changes)}")

                for change in changes:
                    field = change.get('field')
                    value = change.get('value', {})

                    result = process_webhook_event(field, value, entry_id)
                    results.append(result)

            return jsonify({
                "status": "ok",
                "processed": len(results),
                "results": results
            }), 200

        except Exception as e:
            logger.error(f"Webhook processing error: {str(e)}")
            logger.error(traceback.format_exc())

            # Slack 에러 알림
            get_slack().notify_error(
                error_msg=str(e),
                context="Webhook POST 처리"
            )

            return jsonify({"status": "error", "message": str(e)}), 500


def process_webhook_event(
    field: str,
    value: Dict[str, Any],
    entry_id: str
) -> Dict[str, Any]:
    """
    Webhook 이벤트 라우팅 및 처리

    Args:
        field: 이벤트 필드 타입 (comments, messages, mentions 등)
        value: 이벤트 데이터
        entry_id: 엔트리 ID (Instagram 계정 ID)

    Returns:
        처리 결과
    """
    logger.info(f"Processing event: field={field}, entry_id={entry_id}")

    try:
        if field == 'comments':
            # 댓글 이벤트 처리
            comment_manager = get_comment_manager()
            return {
                "field": field,
                "result": comment_manager.handle_webhook(value)
            }

        elif field == 'messages':
            # DM 이벤트 처리
            dm_manager = get_dm_manager()
            return {
                "field": field,
                "result": dm_manager.handle_dm_webhook(value)
            }

        elif field == 'mentions':
            # 멘션 이벤트 - 로깅만 수행
            media_id = value.get('media_id', 'unknown')
            comment_id = value.get('comment_id')

            logger.info(f"Mention received: media_id={media_id}, comment_id={comment_id}")

            return {
                "field": field,
                "result": {
                    "status": "logged",
                    "media_id": media_id,
                    "comment_id": comment_id
                }
            }

        elif field == 'story_insights':
            # 스토리 인사이트 이벤트
            logger.info(f"Story insights received: {value}")
            return {
                "field": field,
                "result": {"status": "logged"}
            }

        else:
            # 알 수 없는 이벤트 타입
            logger.warning(f"Unknown webhook field: {field}")
            return {
                "field": field,
                "result": {"status": "unknown_field"}
            }

    except Exception as e:
        logger.error(f"Event processing error: field={field}, error={str(e)}")
        return {
            "field": field,
            "result": {"status": "error", "error": str(e)}
        }


# ============================================================
# CAPI 엔드포인트
# ============================================================

@app.route('/capi/purchase', methods=['POST'])
def capi_purchase():
    """
    외부 쇼핑몰에서 구매 이벤트 수신

    외부 쇼핑몰(Cafe24, Shopify 등)에서 구매 완료 시
    이 엔드포인트로 데이터를 전송하면 Meta CAPI로 전달합니다.

    Request Body:
        {
            "order_id": "주문번호",
            "total_amount": 금액,
            "email": "고객 이메일 (선택)",
            "phone": "고객 전화번호 (선택)",
            "product_id": "상품 ID (선택)",
            "product_name": "상품명 (선택)",
            "quantity": 수량 (선택),
            "currency": "통화 (선택, 기본: KRW)",
            "ip": "클라이언트 IP (선택)",
            "user_agent": "User-Agent (선택)",
            "fbc": "Facebook Click ID (선택)",
            "fbp": "Facebook Pixel ID (선택)",
            "event_source_url": "구매 완료 페이지 URL (선택)",
            "contents": [상품 상세 리스트] (선택)
        }

    Returns:
        CAPI 전송 결과
    """
    try:
        order_data = request.get_json()

        if not order_data:
            return jsonify({
                "status": "error",
                "message": "Request body is required"
            }), 400

        # 필수 필드 검증
        required_fields = ["order_id", "total_amount"]
        missing_fields = [f for f in required_fields if f not in order_data]

        if missing_fields:
            return jsonify({
                "status": "error",
                "message": f"Missing required fields: {missing_fields}"
            }), 400

        logger.info(
            f"CAPI Purchase received: order_id={order_data['order_id']}, "
            f"amount={order_data['total_amount']}"
        )

        # CAPI 서버 인스턴스 가져오기
        capi = get_capi_server()

        if capi is None:
            logger.error("CapiServer not available")
            return jsonify({
                "status": "error",
                "message": "CAPI server not initialized"
            }), 503

        # 클라이언트 정보 자동 추가 (없는 경우)
        if 'ip' not in order_data:
            order_data['ip'] = request.remote_addr
        if 'user_agent' not in order_data:
            order_data['user_agent'] = request.headers.get('User-Agent')

        # CAPI로 Purchase 이벤트 전송
        result = capi.send_purchase(order_data)

        logger.info(f"CAPI Purchase sent: success={result.get('success')}")

        return jsonify({
            "status": "ok",
            "result": result
        }), 200

    except ValueError as e:
        logger.error(f"CAPI Purchase validation error: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400

    except Exception as e:
        logger.error(f"CAPI Purchase error: {str(e)}")
        logger.error(traceback.format_exc())

        get_slack().notify_error(
            error_msg=str(e),
            context="CAPI Purchase 처리"
        )

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/capi/event', methods=['POST'])
def capi_event():
    """
    범용 CAPI 이벤트 수신

    Purchase 외의 다양한 이벤트를 수신합니다.

    Request Body:
        {
            "event_type": "이벤트 타입 (ViewContent, AddToCart 등)",
            "user_info": {
                "email": "이메일",
                "phone": "전화번호",
                ...
            },
            "event_data": {
                "content_id": "콘텐츠 ID",
                "value": 금액,
                ...
            },
            "event_source_url": "URL",
            "event_id": "이벤트 ID (선택)"
        }

    Returns:
        CAPI 전송 결과
    """
    try:
        data = request.get_json()

        if not data or 'event_type' not in data:
            return jsonify({
                "status": "error",
                "message": "event_type is required"
            }), 400

        event_type = data['event_type']
        user_info = data.get('user_info', {})
        event_data = data.get('event_data', {})
        event_source_url = data.get('event_source_url')
        event_id = data.get('event_id')

        logger.info(f"CAPI Event received: type={event_type}")

        capi = get_capi_server()

        if capi is None:
            return jsonify({
                "status": "error",
                "message": "CAPI server not initialized"
            }), 503

        # 클라이언트 정보 추가
        if 'ip' not in user_info:
            user_info['ip'] = request.remote_addr
        if 'user_agent' not in user_info:
            user_info['user_agent'] = request.headers.get('User-Agent')

        # 이벤트 생성 및 전송
        event = capi.create_event_from_dict(
            event_type=event_type,
            user_info=user_info,
            event_data=event_data,
            event_source_url=event_source_url,
            event_id=event_id
        )

        result = capi.batch_send_events([event])

        return jsonify({
            "status": "ok",
            "result": result
        }), 200

    except Exception as e:
        logger.error(f"CAPI Event error: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ============================================================
# 헬스체크 및 상태 엔드포인트
# ============================================================

@app.route('/health')
def health():
    """
    헬스체크 엔드포인트

    서버가 정상 작동 중인지 확인합니다.
    로드밸런서, 쿠버네티스 등에서 사용합니다.

    Returns:
        {"status": "ok", "timestamp": "ISO 형식 시간"}
    """
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "service": "instagram-webhook-server"
    }), 200


@app.route('/status')
def status():
    """
    상세 상태 엔드포인트

    각 모듈의 상태를 확인합니다.

    Returns:
        각 모듈의 초기화 상태 및 설정 정보
    """
    status_info = {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "environment": os.getenv("FLASK_ENV", "production"),
        "modules": {}
    }

    # 인증 정보 상태
    try:
        creds = get_credentials()
        status_info["modules"]["credentials"] = {
            "status": "ok",
            "instagram_account_id": creds.instagram_account_id[:10] + "..." if creds.instagram_account_id else None,
            "pixel_id": creds.pixel_id[:10] + "..." if creds.pixel_id else None
        }
    except Exception as e:
        status_info["modules"]["credentials"] = {
            "status": "error",
            "error": str(e)
        }

    # CommentManager 상태
    try:
        cm = get_comment_manager()
        status_info["modules"]["comment_manager"] = {
            "status": "ok" if cm else "not_initialized"
        }
    except Exception as e:
        status_info["modules"]["comment_manager"] = {
            "status": "error",
            "error": str(e)
        }

    # DmManager 상태
    try:
        dm = get_dm_manager()
        status_info["modules"]["dm_manager"] = {
            "status": "ok" if dm else "not_initialized"
        }
    except Exception as e:
        status_info["modules"]["dm_manager"] = {
            "status": "error",
            "error": str(e)
        }

    # CapiServer 상태
    try:
        capi = get_capi_server()
        status_info["modules"]["capi_server"] = {
            "status": "ok" if capi else "not_initialized"
        }
    except Exception as e:
        status_info["modules"]["capi_server"] = {
            "status": "error",
            "error": str(e)
        }

    # Slack 알림 상태
    try:
        slack = get_slack()
        status_info["modules"]["slack_notifier"] = {
            "status": "ok",
            "enabled": slack.enabled
        }
    except Exception as e:
        status_info["modules"]["slack_notifier"] = {
            "status": "error",
            "error": str(e)
        }

    # 전체 상태 판정
    has_error = any(
        m.get("status") == "error"
        for m in status_info["modules"].values()
    )

    if has_error:
        status_info["status"] = "degraded"

    return jsonify(status_info), 200


@app.route('/')
def index():
    """
    루트 엔드포인트

    API 정보를 반환합니다.
    """
    return jsonify({
        "service": "Instagram Marketing Webhook Server",
        "version": "1.0.0",
        "endpoints": {
            "webhook": {
                "GET /webhook": "Webhook 검증",
                "POST /webhook": "Webhook 이벤트 수신"
            },
            "capi": {
                "POST /capi/purchase": "구매 이벤트 전송",
                "POST /capi/event": "범용 이벤트 전송"
            },
            "monitoring": {
                "GET /health": "헬스체크",
                "GET /status": "상세 상태"
            }
        },
        "documentation": "https://developers.facebook.com/docs/instagram-api/guides/webhooks"
    }), 200


# ============================================================
# 에러 핸들러
# ============================================================

@app.errorhandler(400)
def bad_request(error):
    """400 Bad Request 핸들러"""
    logger.warning(f"Bad request: {error}")
    return jsonify({
        "status": "error",
        "code": 400,
        "message": "Bad Request",
        "details": str(error)
    }), 400


@app.errorhandler(404)
def not_found(error):
    """404 Not Found 핸들러"""
    logger.warning(f"Not found: {request.path}")
    return jsonify({
        "status": "error",
        "code": 404,
        "message": "Not Found",
        "path": request.path
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):
    """405 Method Not Allowed 핸들러"""
    logger.warning(f"Method not allowed: {request.method} {request.path}")
    return jsonify({
        "status": "error",
        "code": 405,
        "message": "Method Not Allowed",
        "method": request.method,
        "path": request.path
    }), 405


@app.errorhandler(500)
def internal_error(error):
    """500 Internal Server Error 핸들러"""
    logger.error(f"Internal server error: {error}")
    logger.error(traceback.format_exc())

    # Slack 알림 발송
    try:
        get_slack().notify_error(
            error_msg=str(error),
            context=f"{request.method} {request.path}"
        )
    except Exception as slack_error:
        logger.error(f"Failed to send Slack notification: {slack_error}")

    return jsonify({
        "status": "error",
        "code": 500,
        "message": "Internal Server Error",
        "timestamp": datetime.now().isoformat()
    }), 500


@app.errorhandler(Exception)
def handle_exception(error):
    """전역 예외 핸들러"""
    logger.error(f"Unhandled exception: {error}")
    logger.error(traceback.format_exc())

    # Slack 알림 발송
    try:
        get_slack().notify_error(
            error_msg=str(error),
            context=f"Unhandled Exception: {request.method} {request.path}"
        )
    except Exception as slack_error:
        logger.error(f"Failed to send Slack notification: {slack_error}")

    return jsonify({
        "status": "error",
        "code": 500,
        "message": "Internal Server Error",
        "timestamp": datetime.now().isoformat()
    }), 500


# ============================================================
# 요청 전후 처리
# ============================================================

@app.before_request
def before_request():
    """요청 전 처리"""
    # 요청 로깅 (debug 모드에서만)
    if app.debug:
        logger.debug(f"Request: {request.method} {request.path}")


@app.after_request
def after_request(response):
    """요청 후 처리"""
    # 응답 헤더 추가
    response.headers["X-Service"] = "instagram-webhook-server"
    response.headers["X-Version"] = "1.0.0"
    return response


# ============================================================
# 메인 실행
# ============================================================

if __name__ == '__main__':
    # 포트 설정
    port = int(os.getenv('PORT', 5000))

    # 환경 설정
    debug = os.getenv('FLASK_ENV') == 'development'

    # 시작 로그
    logger.info("=" * 60)
    logger.info("Instagram Webhook Server Starting...")
    logger.info(f"  Port: {port}")
    logger.info(f"  Debug: {debug}")
    logger.info(f"  Environment: {os.getenv('FLASK_ENV', 'production')}")
    logger.info(f"  Verify Token: {VERIFY_TOKEN[:10]}...")
    logger.info("=" * 60)

    # 서버 실행
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )
