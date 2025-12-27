"""
Slack 알림 유틸리티
=====================================
광고 상태 변경, 에러 등 알림 발송
"""

import os
import json
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()


class SlackNotifier:
    """Slack 알림 발송"""

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self._enabled = bool(self.webhook_url)

    @property
    def enabled(self) -> bool:
        """알림 활성화 여부"""
        return self._enabled

    def send(
        self,
        message: str,
        title: Optional[str] = None,
        color: str = "#36a64f",
        fields: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Slack 메시지 발송

        Args:
            message: 메시지 본문
            title: 제목 (선택)
            color: 사이드바 색상 (기본: 초록)
            fields: 추가 필드 {"필드명": "값", ...}

        Returns:
            성공 여부
        """

        if not self._enabled:
            print(f"[Slack 비활성화] {message}")
            return False

        import requests

        # Attachment 구성
        attachment = {
            "color": color,
            "text": message,
        }

        if title:
            attachment["title"] = title

        if fields:
            attachment["fields"] = [
                {"title": k, "value": v, "short": True} for k, v in fields.items()
            ]

        payload = {"attachments": [attachment]}

        try:
            response = requests.post(
                self.webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Slack 알림 실패: {e}")
            return False

    # ============================================================
    # 편의 메서드
    # ============================================================

    def notify_ad_paused(self, ad_id: str, reason: str):
        """광고 중단 알림"""
        self.send(
            message=f"⚠️ 광고가 자동 중단되었습니다.",
            title="광고 자동 중단",
            color="#ff9800",
            fields={"광고 ID": ad_id, "중단 사유": reason},
        )

    def notify_ad_scaled(self, ad_id: str, old_budget: int, new_budget: int):
        """광고 예산 증액 알림"""
        self.send(
            message=f"🎉 고성과 광고 예산이 증액되었습니다!",
            title="예산 증액",
            color="#4caf50",
            fields={
                "광고 ID": ad_id,
                "기존 예산": f"{old_budget:,}원",
                "신규 예산": f"{new_budget:,}원",
            },
        )

    def notify_error(self, error_msg: str, context: Optional[str] = None):
        """에러 알림"""
        fields = {"에러": error_msg}
        if context:
            fields["컨텍스트"] = context

        self.send(
            message=f"🚨 시스템 에러가 발생했습니다.",
            title="시스템 에러",
            color="#f44336",
            fields=fields,
        )

    def notify_daily_report(self, stats: Dict[str, Any]):
        """일일 리포트 알림"""
        self.send(
            message="📊 일일 광고 성과 리포트",
            title="Daily Report",
            color="#2196f3",
            fields={
                "총 지출": f"{stats.get('spend', 0):,}원",
                "총 전환": f"{stats.get('conversions', 0)}건",
                "평균 ROAS": f"{stats.get('roas', 0):.2f}",
                "활성 광고": f"{stats.get('active_ads', 0)}개",
            },
        )


# 싱글톤 인스턴스
_notifier: Optional[SlackNotifier] = None


def get_notifier() -> SlackNotifier:
    """전역 알림 인스턴스 반환"""
    global _notifier
    if _notifier is None:
        _notifier = SlackNotifier()
    return _notifier
