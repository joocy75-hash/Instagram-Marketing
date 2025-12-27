"""
Instagram 게시물 자동 발행 모듈
=====================================
Instagram Graph API를 사용하여 게시물을 자동으로 발행

지원 기능:
- 이미지 게시물 발행
- 비디오/릴스 발행
- 캐러셀(슬라이드) 게시물 발행
- 예약 게시
- 게시물 인사이트 조회
- 게시물 삭제
"""

import time
import threading
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from dataclasses import dataclass
from enum import Enum

import requests

from config.meta_credentials import MetaCredentials, get_credentials
from utils.logger import get_logger


class MediaType(Enum):
    """미디어 타입"""
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    REELS = "REELS"
    CAROUSEL = "CAROUSEL"


class ContainerStatus(Enum):
    """컨테이너 상태"""
    FINISHED = "FINISHED"
    IN_PROGRESS = "IN_PROGRESS"
    ERROR = "ERROR"
    EXPIRED = "EXPIRED"


@dataclass
class PublishResult:
    """게시 결과"""
    success: bool
    media_id: Optional[str] = None
    container_id: Optional[str] = None
    error_message: Optional[str] = None
    permalink: Optional[str] = None


@dataclass
class MediaInsights:
    """미디어 인사이트"""
    media_id: str
    reach: int = 0
    impressions: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saved: int = 0
    engagement: int = 0
    plays: int = 0  # 비디오용


class ContentPublisher:
    """
    Instagram 게시물 자동 발행 클래스

    Instagram Graph API를 사용하여 이미지, 비디오, 릴스, 캐러셀 게시물을
    생성하고 발행합니다.

    Example:
        >>> publisher = ContentPublisher()
        >>> result = publisher.publish_image(
        ...     image_url="https://example.com/image.jpg",
        ...     caption="게시물 내용 #해시태그"
        ... )
        >>> print(result.media_id)
    """

    # API 설정
    GRAPH_API_BASE = "https://graph.facebook.com"
    DEFAULT_API_VERSION = "v21.0"

    # 컨테이너 상태 확인 설정
    MAX_STATUS_CHECK_ATTEMPTS = 30
    STATUS_CHECK_INTERVAL = 2  # seconds

    # 캐러셀 제한
    MAX_CAROUSEL_ITEMS = 10
    MIN_CAROUSEL_ITEMS = 2

    def __init__(
        self,
        credentials: Optional[MetaCredentials] = None,
        api_version: Optional[str] = None
    ):
        """
        ContentPublisher 초기화

        Args:
            credentials: Meta API 인증 정보 (없으면 환경변수에서 로드)
            api_version: API 버전 (기본: v21.0)
        """
        self.credentials = credentials or get_credentials()
        self.api_version = api_version or self.DEFAULT_API_VERSION
        self.logger = get_logger("content_publisher")

        # Instagram 계정 ID
        self.ig_user_id = self.credentials.instagram_account_id
        self.access_token = self.credentials.access_token

        # 스케줄러 관련
        self._scheduled_posts: Dict[str, Dict] = {}
        self._scheduler_lock = threading.Lock()
        self._scheduler_thread: Optional[threading.Thread] = None
        self._scheduler_running = False

        self.logger.info(f"ContentPublisher 초기화 완료 (IG User ID: {self.ig_user_id})")

    @property
    def base_url(self) -> str:
        """API 기본 URL"""
        return f"{self.GRAPH_API_BASE}/{self.api_version}"

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """
        API 요청 실행

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

        # access_token 추가
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

    # =========================================================================
    # 컨테이너 생성 메서드
    # =========================================================================

    def upload_image_to_container(
        self,
        image_url: str,
        caption: Optional[str] = None,
        location_id: Optional[str] = None,
        user_tags: Optional[List[Dict]] = None
    ) -> str:
        """
        이미지 URL로 미디어 컨테이너 생성

        Instagram Graph API를 사용하여 공개 URL의 이미지로
        미디어 컨테이너를 생성합니다.

        Args:
            image_url: 공개 접근 가능한 이미지 URL (JPEG 권장)
            caption: 게시물 캡션 (해시태그, 멘션 포함 가능)
            location_id: 위치 ID (선택)
            user_tags: 태그할 사용자 목록 (선택)

        Returns:
            container_id: 생성된 컨테이너 ID

        Raises:
            ValueError: 잘못된 입력값
            requests.RequestException: API 요청 실패

        Example:
            >>> container_id = publisher.upload_image_to_container(
            ...     image_url="https://example.com/photo.jpg",
            ...     caption="아름다운 풍경 #travel #nature"
            ... )
        """
        if not image_url:
            raise ValueError("image_url은 필수입니다")

        if not image_url.startswith(("http://", "https://")):
            raise ValueError("image_url은 유효한 HTTP(S) URL이어야 합니다")

        self.logger.info(f"이미지 컨테이너 생성 시작: {image_url[:50]}...")

        # API 요청 데이터 구성
        data = {
            "image_url": image_url,
        }

        if caption:
            data["caption"] = caption

        if location_id:
            data["location_id"] = location_id

        if user_tags:
            import json
            data["user_tags"] = json.dumps(user_tags)

        # 컨테이너 생성 API 호출
        endpoint = f"{self.ig_user_id}/media"
        result = self._make_request("POST", endpoint, data=data)

        container_id = result.get("id")
        self.logger.info(f"이미지 컨테이너 생성 완료: {container_id}")

        return container_id

    def upload_video_to_container(
        self,
        video_url: str,
        caption: Optional[str] = None,
        media_type: Literal["REELS", "VIDEO"] = "REELS",
        cover_url: Optional[str] = None,
        thumb_offset: Optional[int] = None,
        share_to_feed: bool = True,
        location_id: Optional[str] = None
    ) -> str:
        """
        비디오/릴스 컨테이너 생성

        Args:
            video_url: 공개 접근 가능한 비디오 URL
            caption: 게시물 캡션
            media_type: 미디어 타입 ("REELS" 또는 "VIDEO")
            cover_url: 커버 이미지 URL (선택)
            thumb_offset: 썸네일 오프셋 (밀리초, 선택)
            share_to_feed: 피드에도 공유할지 여부 (릴스용, 기본: True)
            location_id: 위치 ID (선택)

        Returns:
            container_id: 생성된 컨테이너 ID

        Example:
            >>> container_id = publisher.upload_video_to_container(
            ...     video_url="https://example.com/video.mp4",
            ...     caption="멋진 릴스! #reels",
            ...     media_type="REELS"
            ... )
        """
        if not video_url:
            raise ValueError("video_url은 필수입니다")

        if media_type not in ("REELS", "VIDEO"):
            raise ValueError("media_type은 'REELS' 또는 'VIDEO'여야 합니다")

        self.logger.info(f"비디오 컨테이너 생성 시작 (타입: {media_type})")

        # API 요청 데이터 구성
        data = {
            "video_url": video_url,
            "media_type": media_type,
        }

        if caption:
            data["caption"] = caption

        if cover_url:
            data["cover_url"] = cover_url

        if thumb_offset is not None:
            data["thumb_offset"] = str(thumb_offset)

        if media_type == "REELS":
            data["share_to_feed"] = str(share_to_feed).lower()

        if location_id:
            data["location_id"] = location_id

        # 컨테이너 생성 API 호출
        endpoint = f"{self.ig_user_id}/media"
        result = self._make_request("POST", endpoint, data=data, timeout=120)

        container_id = result.get("id")
        self.logger.info(f"비디오 컨테이너 생성 완료: {container_id}")

        return container_id

    def upload_carousel_to_container(
        self,
        children_ids: List[str],
        caption: Optional[str] = None,
        location_id: Optional[str] = None
    ) -> str:
        """
        캐러셀(슬라이드) 게시물 컨테이너 생성

        여러 이미지/비디오를 하나의 슬라이드 게시물로 만듭니다.

        Args:
            children_ids: 자식 미디어 컨테이너 ID 목록 (2-10개)
            caption: 게시물 캡션
            location_id: 위치 ID (선택)

        Returns:
            container_id: 생성된 캐러셀 컨테이너 ID

        Raises:
            ValueError: 자식 미디어 개수가 범위를 벗어남

        Example:
            >>> # 먼저 자식 미디어 생성
            >>> child1 = publisher.upload_image_to_container("https://ex.com/1.jpg")
            >>> child2 = publisher.upload_image_to_container("https://ex.com/2.jpg")
            >>> # 캐러셀 생성
            >>> carousel_id = publisher.upload_carousel_to_container(
            ...     children_ids=[child1, child2],
            ...     caption="슬라이드 게시물! #carousel"
            ... )
        """
        if not children_ids:
            raise ValueError("children_ids는 필수입니다")

        if len(children_ids) < self.MIN_CAROUSEL_ITEMS:
            raise ValueError(f"캐러셀은 최소 {self.MIN_CAROUSEL_ITEMS}개의 미디어가 필요합니다")

        if len(children_ids) > self.MAX_CAROUSEL_ITEMS:
            raise ValueError(f"캐러셀은 최대 {self.MAX_CAROUSEL_ITEMS}개까지 가능합니다")

        self.logger.info(f"캐러셀 컨테이너 생성 시작 ({len(children_ids)}개 미디어)")

        # API 요청 데이터 구성
        data = {
            "media_type": "CAROUSEL",
            "children": ",".join(children_ids),
        }

        if caption:
            data["caption"] = caption

        if location_id:
            data["location_id"] = location_id

        # 컨테이너 생성 API 호출
        endpoint = f"{self.ig_user_id}/media"
        result = self._make_request("POST", endpoint, data=data)

        container_id = result.get("id")
        self.logger.info(f"캐러셀 컨테이너 생성 완료: {container_id}")

        return container_id

    def _upload_carousel_item(
        self,
        media_url: str,
        is_video: bool = False
    ) -> str:
        """
        캐러셀 자식 미디어 생성 (캡션 없이)

        캐러셀의 자식 미디어는 개별 캡션을 가질 수 없으며,
        is_carousel_item=true로 생성해야 합니다.

        Args:
            media_url: 미디어 URL
            is_video: 비디오 여부

        Returns:
            container_id: 자식 컨테이너 ID
        """
        data = {
            "is_carousel_item": "true",
        }

        if is_video:
            data["video_url"] = media_url
            data["media_type"] = "VIDEO"
        else:
            data["image_url"] = media_url

        endpoint = f"{self.ig_user_id}/media"
        result = self._make_request("POST", endpoint, data=data)

        return result.get("id")

    # =========================================================================
    # 컨테이너 상태 확인 및 발행
    # =========================================================================

    def check_container_status(self, container_id: str) -> str:
        """
        미디어 컨테이너 상태 확인

        비디오의 경우 업로드 및 처리에 시간이 걸릴 수 있으므로
        발행 전에 상태를 확인해야 합니다.

        Args:
            container_id: 확인할 컨테이너 ID

        Returns:
            상태 문자열: "FINISHED", "IN_PROGRESS", "ERROR", "EXPIRED"

        Example:
            >>> status = publisher.check_container_status(container_id)
            >>> if status == "FINISHED":
            ...     publisher.publish_container(container_id)
        """
        self.logger.debug(f"컨테이너 상태 확인: {container_id}")

        params = {
            "fields": "status_code,status"
        }

        result = self._make_request("GET", container_id, params=params)

        status = result.get("status_code", "UNKNOWN")
        self.logger.debug(f"컨테이너 상태: {status}")

        return status

    def _wait_for_container_ready(
        self,
        container_id: str,
        max_attempts: Optional[int] = None,
        check_interval: Optional[float] = None
    ) -> bool:
        """
        컨테이너가 준비될 때까지 대기

        Args:
            container_id: 대기할 컨테이너 ID
            max_attempts: 최대 확인 횟수
            check_interval: 확인 간격 (초)

        Returns:
            True if ready, False if error or timeout
        """
        max_attempts = max_attempts or self.MAX_STATUS_CHECK_ATTEMPTS
        check_interval = check_interval or self.STATUS_CHECK_INTERVAL

        self.logger.info(f"컨테이너 준비 대기 중: {container_id}")

        for attempt in range(max_attempts):
            status = self.check_container_status(container_id)

            if status == ContainerStatus.FINISHED.value:
                self.logger.info("컨테이너 준비 완료")
                return True

            if status == ContainerStatus.ERROR.value:
                self.logger.error("컨테이너 처리 중 에러 발생")
                return False

            if status == ContainerStatus.EXPIRED.value:
                self.logger.error("컨테이너가 만료되었습니다")
                return False

            self.logger.debug(f"대기 중... (시도 {attempt + 1}/{max_attempts})")
            time.sleep(check_interval)

        self.logger.error("컨테이너 준비 타임아웃")
        return False

    def publish_container(self, container_id: str) -> str:
        """
        컨테이너를 실제 게시물로 발행

        준비 완료된 컨테이너를 Instagram 피드에 발행합니다.

        Args:
            container_id: 발행할 컨테이너 ID

        Returns:
            media_id: 발행된 게시물의 미디어 ID

        Example:
            >>> media_id = publisher.publish_container(container_id)
            >>> print(f"게시물 발행 완료: {media_id}")
        """
        self.logger.info(f"게시물 발행 시작: {container_id}")

        data = {
            "creation_id": container_id
        }

        endpoint = f"{self.ig_user_id}/media_publish"
        result = self._make_request("POST", endpoint, data=data)

        media_id = result.get("id")
        self.logger.info(f"게시물 발행 완료: {media_id}")

        return media_id

    # =========================================================================
    # 편의 메서드 (일괄 처리)
    # =========================================================================

    def publish_image(
        self,
        image_url: str,
        caption: Optional[str] = None,
        location_id: Optional[str] = None,
        user_tags: Optional[List[Dict]] = None
    ) -> PublishResult:
        """
        이미지 업로드 + 발행 일괄 처리

        이미지 컨테이너 생성과 발행을 한 번에 처리하는 편의 메서드입니다.

        Args:
            image_url: 공개 접근 가능한 이미지 URL
            caption: 게시물 캡션
            location_id: 위치 ID (선택)
            user_tags: 태그할 사용자 목록 (선택)

        Returns:
            PublishResult: 발행 결과 객체

        Example:
            >>> result = publisher.publish_image(
            ...     image_url="https://example.com/photo.jpg",
            ...     caption="오늘의 사진 #daily"
            ... )
            >>> if result.success:
            ...     print(f"발행 완료: {result.media_id}")
        """
        try:
            # 컨테이너 생성
            container_id = self.upload_image_to_container(
                image_url=image_url,
                caption=caption,
                location_id=location_id,
                user_tags=user_tags
            )

            # 이미지는 즉시 준비됨, 바로 발행
            media_id = self.publish_container(container_id)

            # 퍼머링크 조회
            permalink = self._get_permalink(media_id)

            return PublishResult(
                success=True,
                media_id=media_id,
                container_id=container_id,
                permalink=permalink
            )

        except Exception as e:
            self.logger.error(f"이미지 발행 실패: {e}")
            return PublishResult(
                success=False,
                error_message=str(e)
            )

    def publish_video(
        self,
        video_url: str,
        caption: Optional[str] = None,
        media_type: Literal["REELS", "VIDEO"] = "REELS",
        cover_url: Optional[str] = None,
        share_to_feed: bool = True
    ) -> PublishResult:
        """
        비디오/릴스 업로드 + 발행 일괄 처리

        Args:
            video_url: 공개 접근 가능한 비디오 URL
            caption: 게시물 캡션
            media_type: "REELS" 또는 "VIDEO"
            cover_url: 커버 이미지 URL (선택)
            share_to_feed: 피드에도 공유 (릴스용)

        Returns:
            PublishResult: 발행 결과 객체
        """
        try:
            # 컨테이너 생성
            container_id = self.upload_video_to_container(
                video_url=video_url,
                caption=caption,
                media_type=media_type,
                cover_url=cover_url,
                share_to_feed=share_to_feed
            )

            # 비디오 처리 대기
            if not self._wait_for_container_ready(container_id):
                return PublishResult(
                    success=False,
                    container_id=container_id,
                    error_message="비디오 처리 실패 또는 타임아웃"
                )

            # 발행
            media_id = self.publish_container(container_id)
            permalink = self._get_permalink(media_id)

            return PublishResult(
                success=True,
                media_id=media_id,
                container_id=container_id,
                permalink=permalink
            )

        except Exception as e:
            self.logger.error(f"비디오 발행 실패: {e}")
            return PublishResult(
                success=False,
                error_message=str(e)
            )

    def publish_carousel(
        self,
        image_urls: List[str],
        caption: Optional[str] = None,
        location_id: Optional[str] = None
    ) -> PublishResult:
        """
        캐러셀 업로드 + 발행 일괄 처리

        여러 이미지를 슬라이드 형태의 단일 게시물로 발행합니다.

        Args:
            image_urls: 이미지 URL 목록 (2-10개)
            caption: 게시물 캡션
            location_id: 위치 ID (선택)

        Returns:
            PublishResult: 발행 결과 객체

        Example:
            >>> result = publisher.publish_carousel(
            ...     image_urls=[
            ...         "https://example.com/1.jpg",
            ...         "https://example.com/2.jpg",
            ...         "https://example.com/3.jpg"
            ...     ],
            ...     caption="여행 사진 모음 #travel"
            ... )
        """
        try:
            if len(image_urls) < self.MIN_CAROUSEL_ITEMS:
                raise ValueError(f"최소 {self.MIN_CAROUSEL_ITEMS}개의 이미지가 필요합니다")

            if len(image_urls) > self.MAX_CAROUSEL_ITEMS:
                raise ValueError(f"최대 {self.MAX_CAROUSEL_ITEMS}개까지만 가능합니다")

            self.logger.info(f"캐러셀 발행 시작 ({len(image_urls)}개 이미지)")

            # 자식 미디어 컨테이너 생성
            children_ids = []
            for i, url in enumerate(image_urls):
                self.logger.debug(f"자식 미디어 생성 중 ({i+1}/{len(image_urls)})")
                child_id = self._upload_carousel_item(url, is_video=False)
                children_ids.append(child_id)

            # 캐러셀 컨테이너 생성
            container_id = self.upload_carousel_to_container(
                children_ids=children_ids,
                caption=caption,
                location_id=location_id
            )

            # 발행
            media_id = self.publish_container(container_id)
            permalink = self._get_permalink(media_id)

            return PublishResult(
                success=True,
                media_id=media_id,
                container_id=container_id,
                permalink=permalink
            )

        except Exception as e:
            self.logger.error(f"캐러셀 발행 실패: {e}")
            return PublishResult(
                success=False,
                error_message=str(e)
            )

    # =========================================================================
    # 예약 게시
    # =========================================================================

    def schedule_post(
        self,
        image_url: str,
        caption: str,
        publish_time: datetime,
        post_id: Optional[str] = None
    ) -> str:
        """
        예약 게시 등록

        Instagram Graph API는 직접적인 예약 발행을 지원하지 않으므로,
        내부 스케줄러를 사용하여 지정된 시간에 발행합니다.

        Args:
            image_url: 이미지 URL
            caption: 게시물 캡션
            publish_time: 발행 예정 시각 (datetime)
            post_id: 게시물 식별자 (선택, 없으면 자동 생성)

        Returns:
            post_id: 예약된 게시물 ID (취소용)

        Raises:
            ValueError: 과거 시간 지정 시

        Example:
            >>> from datetime import datetime, timedelta
            >>> publish_at = datetime.now() + timedelta(hours=2)
            >>> post_id = publisher.schedule_post(
            ...     image_url="https://example.com/photo.jpg",
            ...     caption="예약 게시물 #scheduled",
            ...     publish_time=publish_at
            ... )
            >>> print(f"예약 완료: {post_id}")
        """
        # 과거 시간 체크
        if publish_time <= datetime.now():
            raise ValueError("발행 시간은 현재 시간 이후여야 합니다")

        # 게시물 ID 생성
        if post_id is None:
            post_id = f"scheduled_{int(datetime.now().timestamp())}_{len(self._scheduled_posts)}"

        # 예약 정보 저장
        with self._scheduler_lock:
            self._scheduled_posts[post_id] = {
                "image_url": image_url,
                "caption": caption,
                "publish_time": publish_time,
                "status": "pending"
            }

        self.logger.info(f"게시물 예약 완료: {post_id} -> {publish_time}")

        # 스케줄러 시작 (아직 실행 중이 아니면)
        self._start_scheduler()

        return post_id

    def cancel_scheduled_post(self, post_id: str) -> bool:
        """
        예약된 게시물 취소

        Args:
            post_id: 취소할 게시물 ID

        Returns:
            성공 여부
        """
        with self._scheduler_lock:
            if post_id in self._scheduled_posts:
                del self._scheduled_posts[post_id]
                self.logger.info(f"예약 취소됨: {post_id}")
                return True

        self.logger.warning(f"예약된 게시물을 찾을 수 없음: {post_id}")
        return False

    def get_scheduled_posts(self) -> Dict[str, Dict]:
        """
        예약된 게시물 목록 조회

        Returns:
            예약된 게시물 딕셔너리
        """
        with self._scheduler_lock:
            return self._scheduled_posts.copy()

    def _start_scheduler(self):
        """스케줄러 스레드 시작"""
        if self._scheduler_running:
            return

        self._scheduler_running = True
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True
        )
        self._scheduler_thread.start()
        self.logger.info("스케줄러 시작됨")

    def _scheduler_loop(self):
        """스케줄러 메인 루프"""
        while self._scheduler_running:
            now = datetime.now()
            posts_to_publish = []

            # 발행할 게시물 확인
            with self._scheduler_lock:
                for post_id, post_info in list(self._scheduled_posts.items()):
                    if post_info["status"] == "pending" and post_info["publish_time"] <= now:
                        posts_to_publish.append((post_id, post_info))
                        post_info["status"] = "publishing"

            # 게시물 발행
            for post_id, post_info in posts_to_publish:
                try:
                    self.logger.info(f"예약 게시물 발행 중: {post_id}")
                    result = self.publish_image(
                        image_url=post_info["image_url"],
                        caption=post_info["caption"]
                    )

                    with self._scheduler_lock:
                        if result.success:
                            self._scheduled_posts[post_id]["status"] = "published"
                            self._scheduled_posts[post_id]["media_id"] = result.media_id
                            self.logger.info(f"예약 게시물 발행 완료: {post_id} -> {result.media_id}")
                        else:
                            self._scheduled_posts[post_id]["status"] = "failed"
                            self._scheduled_posts[post_id]["error"] = result.error_message
                            self.logger.error(f"예약 게시물 발행 실패: {post_id}")

                except Exception as e:
                    self.logger.error(f"예약 게시물 발행 중 오류: {e}")
                    with self._scheduler_lock:
                        self._scheduled_posts[post_id]["status"] = "failed"
                        self._scheduled_posts[post_id]["error"] = str(e)

            # 완료/실패 게시물 정리 (1시간 후)
            with self._scheduler_lock:
                for post_id in list(self._scheduled_posts.keys()):
                    post_info = self._scheduled_posts[post_id]
                    if post_info["status"] in ("published", "failed"):
                        publish_time = post_info["publish_time"]
                        if (now - publish_time).total_seconds() > 3600:
                            del self._scheduled_posts[post_id]

            # 대기
            time.sleep(30)  # 30초마다 체크

    def stop_scheduler(self):
        """스케줄러 중지"""
        self._scheduler_running = False
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
        self.logger.info("스케줄러 중지됨")

    # =========================================================================
    # 인사이트 및 관리
    # =========================================================================

    def get_media_insights(self, media_id: str) -> MediaInsights:
        """
        게시물 인사이트 조회

        게시물의 도달, 노출, 좋아요 등 성과 지표를 조회합니다.

        Args:
            media_id: 조회할 미디어 ID

        Returns:
            MediaInsights: 인사이트 데이터 객체

        Example:
            >>> insights = publisher.get_media_insights(media_id)
            >>> print(f"도달: {insights.reach}, 좋아요: {insights.likes}")
        """
        self.logger.info(f"미디어 인사이트 조회: {media_id}")

        # 기본 미디어 정보 조회
        params = {
            "fields": "like_count,comments_count,media_type"
        }
        media_info = self._make_request("GET", media_id, params=params)

        # 인사이트 조회 (metric별)
        # 이미지/캐러셀: reach, impressions, saved
        # 비디오/릴스: reach, impressions, saved, plays, shares
        media_type = media_info.get("media_type", "IMAGE")

        metrics = ["reach", "impressions", "saved"]
        if media_type in ("VIDEO", "REELS"):
            metrics.extend(["plays", "shares"])

        insights_params = {
            "metric": ",".join(metrics)
        }

        try:
            insights_result = self._make_request(
                "GET",
                f"{media_id}/insights",
                params=insights_params
            )

            # 인사이트 데이터 파싱
            insights_data = {}
            for item in insights_result.get("data", []):
                name = item.get("name")
                values = item.get("values", [])
                if values:
                    insights_data[name] = values[0].get("value", 0)

        except Exception as e:
            self.logger.warning(f"인사이트 조회 실패 (권한 또는 데이터 부족): {e}")
            insights_data = {}

        return MediaInsights(
            media_id=media_id,
            reach=insights_data.get("reach", 0),
            impressions=insights_data.get("impressions", 0),
            likes=media_info.get("like_count", 0),
            comments=media_info.get("comments_count", 0),
            saved=insights_data.get("saved", 0),
            shares=insights_data.get("shares", 0),
            plays=insights_data.get("plays", 0)
        )

    def delete_media(self, media_id: str) -> bool:
        """
        게시물 삭제

        주의: 삭제된 게시물은 복구할 수 없습니다.

        Args:
            media_id: 삭제할 미디어 ID

        Returns:
            성공 여부

        Example:
            >>> success = publisher.delete_media(media_id)
            >>> if success:
            ...     print("게시물이 삭제되었습니다")
        """
        self.logger.warning(f"게시물 삭제 요청: {media_id}")

        try:
            # Instagram Graph API는 직접 삭제를 지원하지 않음
            # Facebook Page API를 통해 삭제해야 함
            # 여기서는 Facebook Page와 연결된 경우만 가능

            result = self._make_request("DELETE", media_id)

            if result.get("success", False):
                self.logger.info(f"게시물 삭제 완료: {media_id}")
                return True

            return False

        except Exception as e:
            self.logger.error(f"게시물 삭제 실패: {e}")
            return False

    def _get_permalink(self, media_id: str) -> Optional[str]:
        """미디어 퍼머링크 조회"""
        try:
            params = {"fields": "permalink"}
            result = self._make_request("GET", media_id, params=params)
            return result.get("permalink")
        except Exception:
            return None

    # =========================================================================
    # 유틸리티 메서드
    # =========================================================================

    def get_account_info(self) -> Dict[str, Any]:
        """
        Instagram 계정 정보 조회

        Returns:
            계정 정보 딕셔너리
        """
        params = {
            "fields": "id,username,name,profile_picture_url,followers_count,follows_count,media_count,biography"
        }

        return self._make_request("GET", self.ig_user_id, params=params)

    def get_recent_media(self, limit: int = 25) -> List[Dict]:
        """
        최근 게시물 목록 조회

        Args:
            limit: 조회할 개수 (최대 25)

        Returns:
            미디어 목록
        """
        params = {
            "fields": "id,media_type,media_url,thumbnail_url,permalink,caption,timestamp,like_count,comments_count",
            "limit": min(limit, 25)
        }

        result = self._make_request("GET", f"{self.ig_user_id}/media", params=params)
        return result.get("data", [])

    def validate_image_url(self, image_url: str, timeout: int = 10) -> bool:
        """
        이미지 URL 유효성 검증

        Instagram API에서 사용하기 전에 이미지 URL이
        공개적으로 접근 가능한지 확인합니다.

        Args:
            image_url: 검증할 이미지 URL
            timeout: 요청 타임아웃 (초)

        Returns:
            유효 여부
        """
        try:
            response = requests.head(image_url, timeout=timeout, allow_redirects=True)

            if response.status_code != 200:
                self.logger.warning(f"이미지 URL 접근 불가: {response.status_code}")
                return False

            content_type = response.headers.get("Content-Type", "")
            if not content_type.startswith("image/"):
                self.logger.warning(f"이미지가 아닌 콘텐츠 타입: {content_type}")
                return False

            return True

        except Exception as e:
            self.logger.warning(f"이미지 URL 검증 실패: {e}")
            return False


# 모듈 레벨 헬퍼 함수
def publish_image_quick(
    image_url: str,
    caption: str,
    credentials: Optional[MetaCredentials] = None
) -> PublishResult:
    """
    간편 이미지 발행 함수

    ContentPublisher 인스턴스 생성 없이 바로 이미지를 발행합니다.

    Args:
        image_url: 이미지 URL
        caption: 캡션
        credentials: 인증 정보 (선택)

    Returns:
        PublishResult: 발행 결과

    Example:
        >>> result = publish_image_quick(
        ...     "https://example.com/photo.jpg",
        ...     "간편 발행 테스트 #test"
        ... )
    """
    publisher = ContentPublisher(credentials=credentials)
    return publisher.publish_image(image_url, caption)
