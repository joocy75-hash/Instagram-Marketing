"""
Hourly Cron Job - 댓글 폴링 체크 (Webhook 백업)
================================================
매시간 실행되어 Webhook으로 놓친 댓글을 처리
미응답 댓글에 자동 응답하고 스팸 댓글을 숨김 처리

실행: python -m cron.hourly
또는: python cron/hourly.py

Crontab 설정 예시:
0 * * * * cd /path/to/instagram-marketing && python -m cron.hourly
"""

import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.slack_notifier import get_notifier
from config.meta_credentials import get_credentials

import requests


# 로거 설정
logger = get_logger("cron.hourly")


class CommentPollingJob:
    """
    댓글 폴링 작업

    Webhook의 백업으로 매시간 댓글을 체크하여
    놓친 댓글에 대응합니다.
    """

    def __init__(self):
        """초기화"""
        self.creds = get_credentials()
        self.base_url = self.creds.get_graph_url()
        self.access_token = self.creds.access_token
        self.ig_user_id = self.creds.instagram_account_id
        self.notifier = get_notifier()

        # 처리 통계
        self.stats = {
            "total_posts_checked": 0,
            "total_comments_found": 0,
            "new_replies_sent": 0,
            "spam_hidden": 0,
            "errors": 0,
        }

        logger.info(f"CommentPollingJob 초기화 완료: {self.ig_user_id}")

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
            self.stats["errors"] += 1
            raise

    def get_recent_media(self, hours: int = 24) -> List[Dict]:
        """
        최근 게시물 조회

        Args:
            hours: 조회할 시간 범위

        Returns:
            미디어 목록
        """
        logger.info(f"최근 {hours}시간 내 게시물 조회")

        try:
            # 최근 미디어 조회 (최대 25개)
            data = self._make_request(
                f"{self.ig_user_id}/media",
                params={
                    "fields": "id,caption,timestamp,media_type,comments_count",
                    "limit": 25,
                }
            )

            media_list = data.get("data", [])
            cutoff_time = datetime.now() - timedelta(hours=hours)

            # 시간 범위 내 게시물 필터링
            recent_media = []
            for media in media_list:
                timestamp = media.get("timestamp", "")
                if timestamp:
                    media_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    if media_time.replace(tzinfo=None) >= cutoff_time:
                        recent_media.append(media)

            logger.info(f"최근 {hours}시간 내 게시물 {len(recent_media)}개 발견")
            return recent_media

        except Exception as e:
            logger.error(f"최근 게시물 조회 실패: {e}")
            return []

    def get_comments(self, media_id: str) -> List[Dict]:
        """
        미디어의 댓글 조회

        Args:
            media_id: 미디어 ID

        Returns:
            댓글 목록
        """
        try:
            data = self._make_request(
                f"{media_id}/comments",
                params={
                    "fields": "id,text,username,timestamp,replies{id,text,username,timestamp}",
                    "limit": 50,
                }
            )

            return data.get("data", [])

        except Exception as e:
            logger.error(f"댓글 조회 실패 (media_id={media_id}): {e}")
            return []

    def is_already_replied(self, comment: Dict) -> bool:
        """
        이미 응답했는지 확인

        Args:
            comment: 댓글 데이터

        Returns:
            응답 여부
        """
        replies = comment.get("replies", {}).get("data", [])

        # 내 계정이 답글을 달았는지 확인
        # (실제로는 계정 username과 비교해야 함)
        for reply in replies:
            # 봇이 답글을 달았는지 확인하는 로직
            # 여기서는 간단히 replies가 있으면 응답한 것으로 간주
            # 실제 구현에서는 bot_username과 비교
            if reply.get("username"):
                # 봇 계정인지 확인 (실제 구현시 봇 username 설정 필요)
                pass

        return len(replies) > 0

    def is_spam_comment(self, comment_text: str) -> bool:
        """
        스팸 댓글 여부 판단

        Args:
            comment_text: 댓글 텍스트

        Returns:
            스팸 여부
        """
        spam_keywords = [
            "팔로우하세요",
            "선팔",
            "맞팔",
            "부업",
            "재택근무",
            "일당",
            "수익",
            "dm주세요",
            "카톡",
            "클릭",
            "링크",
            "무료",
            "당첨",
            "이벤트 참여",
        ]

        text_lower = comment_text.lower()

        for keyword in spam_keywords:
            if keyword in text_lower:
                return True

        # URL 패턴 체크
        import re
        url_pattern = r'https?://[^\s]+'
        if re.search(url_pattern, comment_text):
            return True

        return False

    def hide_comment(self, comment_id: str) -> bool:
        """
        스팸 댓글 숨김 처리

        Args:
            comment_id: 댓글 ID

        Returns:
            성공 여부
        """
        try:
            # 댓글 숨김 API 호출
            url = f"{self.base_url}/{comment_id}"
            params = {
                "access_token": self.access_token,
                "hide": "true",
            }

            response = requests.post(url, data=params)
            response.raise_for_status()

            logger.info(f"스팸 댓글 숨김 처리: {comment_id}")
            self.stats["spam_hidden"] += 1
            return True

        except Exception as e:
            logger.error(f"댓글 숨김 실패 (comment_id={comment_id}): {e}")
            self.stats["errors"] += 1
            return False

    def reply_to_comment(self, comment_id: str, message: str) -> bool:
        """
        댓글에 답글 달기

        Args:
            comment_id: 댓글 ID
            message: 답글 메시지

        Returns:
            성공 여부
        """
        try:
            data = self._make_request(
                f"{comment_id}/replies",
                params={"message": message},
                method="POST"
            )

            if data.get("id"):
                logger.info(f"답글 작성 완료: {comment_id}")
                self.stats["new_replies_sent"] += 1
                return True
            return False

        except Exception as e:
            logger.error(f"답글 작성 실패 (comment_id={comment_id}): {e}")
            self.stats["errors"] += 1
            return False

    def generate_auto_reply(self, comment_text: str, username: str) -> str:
        """
        자동 응답 메시지 생성

        Args:
            comment_text: 원본 댓글
            username: 댓글 작성자

        Returns:
            응답 메시지
        """
        # 기본 응답 템플릿
        templates = [
            f"@{username} 댓글 감사합니다! :)",
            f"@{username} 소중한 의견 감사드려요!",
            f"@{username} 감사합니다! 더 좋은 콘텐츠로 찾아뵐게요.",
        ]

        # 질문 감지시 다른 응답
        question_keywords = ["?", "궁금", "어떻게", "뭐", "왜", "언제", "어디"]
        is_question = any(kw in comment_text for kw in question_keywords)

        if is_question:
            return f"@{username} 좋은 질문이에요! DM으로 자세한 내용 안내드릴게요."

        # 긍정적 댓글
        positive_keywords = ["좋아", "최고", "대박", "예쁘", "멋지", "짱"]
        is_positive = any(kw in comment_text for kw in positive_keywords)

        if is_positive:
            return f"@{username} 감사합니다! 앞으로도 기대해주세요!"

        # 기본 응답 (순환)
        import random
        return random.choice(templates)

    def process_comments(self, media: Dict) -> Dict:
        """
        미디어의 댓글 처리

        Args:
            media: 미디어 데이터

        Returns:
            처리 결과
        """
        media_id = media["id"]
        result = {
            "media_id": media_id,
            "comments_checked": 0,
            "replies_sent": 0,
            "spam_hidden": 0,
        }

        try:
            comments = self.get_comments(media_id)
            result["comments_checked"] = len(comments)
            self.stats["total_comments_found"] += len(comments)

            for comment in comments:
                comment_id = comment.get("id")
                comment_text = comment.get("text", "")
                username = comment.get("username", "user")

                # 스팸 체크
                if self.is_spam_comment(comment_text):
                    if self.hide_comment(comment_id):
                        result["spam_hidden"] += 1
                    continue

                # 이미 응답한 댓글은 건너뛰기
                if self.is_already_replied(comment):
                    continue

                # 자동 응답 생성 및 전송
                reply_message = self.generate_auto_reply(comment_text, username)
                if self.reply_to_comment(comment_id, reply_message):
                    result["replies_sent"] += 1

            return result

        except Exception as e:
            logger.error(f"댓글 처리 실패 (media_id={media_id}): {e}")
            result["error"] = str(e)
            return result

    def run(self, hours: int = 1) -> Dict:
        """
        댓글 폴링 작업 실행

        Args:
            hours: 체크할 시간 범위 (기본 1시간)

        Returns:
            처리 통계
        """
        logger.info("-" * 40)
        logger.info(f"댓글 폴링 시작 (최근 {hours}시간)")

        # 최근 게시물 조회 (댓글이 달릴 수 있는 게시물은 더 넓은 범위로)
        recent_media = self.get_recent_media(hours=24)
        self.stats["total_posts_checked"] = len(recent_media)

        # 각 게시물의 댓글 처리
        for media in recent_media:
            try:
                result = self.process_comments(media)
                logger.debug(
                    f"미디어 {media['id']}: "
                    f"댓글 {result['comments_checked']}개, "
                    f"답글 {result['replies_sent']}개, "
                    f"스팸 {result['spam_hidden']}개"
                )
            except Exception as e:
                logger.error(f"미디어 {media['id']} 처리 중 에러: {e}")
                self.stats["errors"] += 1

        logger.info("-" * 40)
        logger.info("댓글 폴링 완료")
        logger.info(f"  - 체크한 게시물: {self.stats['total_posts_checked']}개")
        logger.info(f"  - 발견된 댓글: {self.stats['total_comments_found']}개")
        logger.info(f"  - 새 답글: {self.stats['new_replies_sent']}개")
        logger.info(f"  - 숨긴 스팸: {self.stats['spam_hidden']}개")
        logger.info(f"  - 에러: {self.stats['errors']}개")

        return self.stats


def run_hourly_comment_check():
    """
    매시간 댓글 체크 실행

    주요 기능:
    1. 최근 1시간 내 게시물 댓글 조회
    2. 미응답 댓글 자동 응답
    3. 스팸 댓글 숨김 처리
    4. 처리 통계 로깅
    """
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("[Cron] 매시간 댓글 폴링 시작")
    logger.info(f"시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    notifier = get_notifier()

    try:
        # 댓글 폴링 작업 실행
        job = CommentPollingJob()
        stats = job.run(hours=1)

        # 실행 시간 계산
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # 처리 건수가 있으면 Slack 알림
        if stats["new_replies_sent"] > 0 or stats["spam_hidden"] > 0:
            notifier.send(
                message=(
                    f"댓글 폴링 완료\n"
                    f"- 체크 게시물: {stats['total_posts_checked']}개\n"
                    f"- 새 답글: {stats['new_replies_sent']}개\n"
                    f"- 숨긴 스팸: {stats['spam_hidden']}개"
                ),
                title="매시간 댓글 처리",
                color="#4caf50",
                fields={
                    "체크 게시물": f"{stats['total_posts_checked']}개",
                    "발견 댓글": f"{stats['total_comments_found']}개",
                    "새 답글": f"{stats['new_replies_sent']}개",
                    "숨긴 스팸": f"{stats['spam_hidden']}개",
                }
            )

        logger.info(f"종료 시간: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"실행 시간: {duration:.1f}초")
        logger.info("=" * 60)

        return stats

    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        error_msg = f"댓글 폴링 실패: {str(e)}"
        logger.error(error_msg)
        logger.exception(e)

        # 에러 Slack 알림
        notifier.notify_error(
            error_msg=str(e),
            context="cron.hourly.run_hourly_comment_check"
        )

        logger.info(f"종료 시간: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"실행 시간: {duration:.1f}초 (실패)")
        logger.info("=" * 60)

        raise


def main():
    """메인 진입점"""
    try:
        stats = run_hourly_comment_check()

        # 정상 종료
        sys.exit(0)

    except Exception as e:
        logger.error(f"Cron 작업 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
