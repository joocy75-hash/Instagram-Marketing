"""
Instagram 캡션 CTA 최적화 모듈
=====================================
오가닉 게시물의 CTA(Call To Action) 캡션 생성 및 최적화
"""

import base64
import json
import re
from typing import Dict, List, Optional
from dataclasses import dataclass

# 상대 경로 임포트
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.claude_api import ClaudeClient, get_claude_client
from config.constants import CAPTION_CTA_TEMPLATES
from utils.logger import get_logger

# 로거 설정
logger = get_logger("caption_optimizer")


# ============================================================
# CTA 문구 베스트 모음
# ============================================================

CTA_PHRASES: Dict[str, List[str]] = {
    "profile_link": [
        "👆 프로필 링크 클릭!",
        "🔗 프로필 링크에서 바로 구매!",
        "📲 프로필 링크 확인하세요!",
        "💫 프로필 링크로 지금 바로!",
        "⬆️ 바이오 링크에서 만나요!",
    ],
    "dm": [
        "💬 'OOO' 댓글 → DM 발송",
        "📩 DM으로 문의주세요!",
        "✉️ DM 보내시면 상세 안내드려요",
        "💌 '가격' 댓글 남기면 DM 드려요!",
        "🗨️ 궁금하시면 DM 주세요!",
    ],
    "comment": [
        "💬 댓글로 의견 남겨주세요!",
        "🗣️ 어떻게 생각하시나요? 댓글로!",
        "✍️ 궁금한 점은 댓글로!",
        "📝 댓글에 질문 남겨주세요!",
        "💭 여러분의 생각이 궁금해요!",
    ],
    "urgency": [
        "⏰ 오늘까지만 특가!",
        "🚨 마감 임박!",
        "⏳ 시간 한정 특가!",
        "🔥 지금 아니면 늦어요!",
        "⚡ 24시간 한정!",
    ],
    "limited": [
        "🔥 선착순 100명 마감",
        "⚠️ 한정 수량!",
        "🎯 선착순 한정!",
        "🏃 재고 소진 시 종료!",
        "✨ 단 50개 한정!",
    ],
}


# ============================================================
# 추가 CTA 템플릿 (constants.py 보완)
# ============================================================

EXTENDED_CTA_TEMPLATES: Dict[str, str] = {
    "dm": """
{main_message} ✨

━━━━━━━━━━━━━━━━
💬 '{keyword}' 댓글 남기시면 DM 드려요!
━━━━━━━━━━━━━━━━

📩 빠른 상담 원하시면 DM 주세요!

{hashtags}
""",
    "comment": """
{main_message} 💭

━━━━━━━━━━━━━━━━
✍️ 여러분의 생각을 댓글로 남겨주세요!
━━━━━━━━━━━━━━━━

❤️ 좋아요 + 저장하면 더 좋은 컨텐츠로 찾아올게요!

{hashtags}
""",
}


@dataclass
class CaptionResult:
    """캡션 생성 결과"""
    caption: str
    cta_type: str
    hashtags: List[str]
    character_count: int

    def __str__(self) -> str:
        return self.caption


class CaptionOptimizer:
    """
    Instagram 캡션 CTA 최적화 클래스

    캡션 생성, CTA 추가, 해시태그 생성 등 오가닉 게시물 최적화 기능 제공
    """

    # Instagram 캡션 최대 길이
    MAX_CAPTION_LENGTH = 2200

    def __init__(self, claude_client: Optional[ClaudeClient] = None):
        """
        초기화

        Args:
            claude_client: ClaudeClient 인스턴스 (None이면 전역 클라이언트 사용)
        """
        self._claude_client = claude_client
        logger.info("CaptionOptimizer 초기화 완료")

    @property
    def claude_client(self) -> ClaudeClient:
        """Claude 클라이언트 (lazy loading)"""
        if self._claude_client is None:
            self._claude_client = get_claude_client()
        return self._claude_client

    # ============================================================
    # 1. create_cta_caption - CTA 타입별 캡션 생성
    # ============================================================

    def create_cta_caption(
        self,
        product_info: Dict[str, str],
        cta_type: str = "profile_link"
    ) -> CaptionResult:
        """
        CTA 타입별 캡션 템플릿 사용하여 캡션 생성

        Args:
            product_info: 상품 정보 딕셔너리
                - name: 상품명
                - description: 상품 설명
                - price: 가격 (선택)
                - hashtags: 해시태그 리스트 (선택)
                - keyword: DM 키워드 (선택, dm 타입에서 사용)
                - limit: 선착순 인원 (선택, limited 타입에서 사용)
            cta_type: CTA 유형 ("profile_link", "dm", "comment", "urgency", "limited")

        Returns:
            CaptionResult: 생성된 캡션 결과
        """
        logger.info(f"CTA 캡션 생성 시작 - 타입: {cta_type}")

        # 템플릿 선택
        if cta_type in CAPTION_CTA_TEMPLATES:
            template = CAPTION_CTA_TEMPLATES[cta_type]
        elif cta_type in EXTENDED_CTA_TEMPLATES:
            template = EXTENDED_CTA_TEMPLATES[cta_type]
        else:
            logger.warning(f"알 수 없는 CTA 타입: {cta_type}, 기본값 profile_link 사용")
            template = CAPTION_CTA_TEMPLATES["profile_link"]
            cta_type = "profile_link"

        # 메인 메시지 구성
        name = product_info.get("name", "")
        description = product_info.get("description", "")
        price = product_info.get("price", "")

        main_message = name
        if description:
            main_message = f"{name}\n\n{description}"
        if price:
            main_message += f"\n💰 {price}"

        # 해시태그 처리
        hashtags = product_info.get("hashtags", [])
        if isinstance(hashtags, list):
            hashtag_str = " ".join([f"#{tag}" if not tag.startswith("#") else tag for tag in hashtags])
        else:
            hashtag_str = hashtags

        # 템플릿 변수 설정
        template_vars = {
            "main_message": main_message,
            "hashtags": hashtag_str,
            "keyword": product_info.get("keyword", "정보"),
            "limit": product_info.get("limit", "100"),
        }

        # 템플릿 적용
        try:
            caption = template.format(**template_vars)
        except KeyError as e:
            logger.error(f"템플릿 변수 누락: {e}")
            caption = f"{main_message}\n\n{hashtag_str}"

        caption = caption.strip()

        logger.info(f"CTA 캡션 생성 완료 - 길이: {len(caption)}자")

        return CaptionResult(
            caption=caption,
            cta_type=cta_type,
            hashtags=hashtags if isinstance(hashtags, list) else [],
            character_count=len(caption)
        )

    # ============================================================
    # 2. generate_caption_with_ai - AI 캡션 생성
    # ============================================================

    def generate_caption_with_ai(
        self,
        product_description: str,
        image_path: Optional[str] = None,
        cta_type: str = "profile_link",
        hashtag_count: int = 5
    ) -> CaptionResult:
        """
        Claude AI로 효과적인 CTA 캡션 생성

        Args:
            product_description: 상품/콘텐츠 설명
            image_path: 이미지 파일 경로 (선택, 이미지 분석 포함)
            cta_type: CTA 유형
            hashtag_count: 생성할 해시태그 개수

        Returns:
            CaptionResult: AI가 생성한 캡션 결과
        """
        logger.info(f"AI 캡션 생성 시작 - CTA 타입: {cta_type}, 이미지: {image_path is not None}")

        # CTA 타입별 지침
        cta_instructions = {
            "profile_link": "프로필 링크 클릭을 유도하는 문구 포함 (예: '👆 프로필 링크에서 확인!')",
            "dm": "DM 문의를 유도하는 문구 포함 (예: '💬 댓글 남기시면 DM 드려요!')",
            "comment": "댓글 참여를 유도하는 문구 포함 (예: '💭 여러분의 의견을 댓글로!')",
            "urgency": "긴급성을 강조하는 문구 포함 (예: '⏰ 오늘까지만 특가!')",
            "limited": "한정 수량을 강조하는 문구 포함 (예: '🔥 선착순 100명!')",
        }

        cta_guide = cta_instructions.get(cta_type, cta_instructions["profile_link"])

        prompt = f"""
다음 상품/콘텐츠에 대한 Instagram 캡션을 작성해주세요.

상품/콘텐츠 설명: {product_description}

요구사항:
1. 매력적이고 눈길을 끄는 첫 문장 (사람들이 "더 보기"를 클릭하게)
2. {cta_guide}
3. 이모지 적절히 활용 (과하지 않게)
4. 관련 해시태그 {hashtag_count}개 (한국어 위주, 인기 + 니치 혼합)
5. 전체 길이 2000자 이내
6. 구분선(━━━) 사용해서 시각적 구분

응답 형식 (JSON):
{{
    "caption": "완성된 캡션 텍스트",
    "hashtags": ["해시태그1", "해시태그2", ...]
}}
"""

        try:
            # 이미지가 있는 경우
            if image_path:
                caption_data = self._generate_with_image(prompt, image_path)
            else:
                caption_data = self._generate_text_only(prompt)

            caption = caption_data.get("caption", "")
            hashtags = caption_data.get("hashtags", [])

            logger.info(f"AI 캡션 생성 완료 - 길이: {len(caption)}자, 해시태그: {len(hashtags)}개")

            return CaptionResult(
                caption=caption,
                cta_type=cta_type,
                hashtags=hashtags,
                character_count=len(caption)
            )

        except Exception as e:
            logger.error(f"AI 캡션 생성 실패: {e}")
            # 폴백: 기본 템플릿 사용
            return self.create_cta_caption(
                {"name": product_description[:100], "description": "", "hashtags": []},
                cta_type
            )

    def _generate_with_image(self, prompt: str, image_path: str) -> Dict:
        """이미지 포함 캡션 생성"""
        with open(image_path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")

        ext = image_path.lower().split(".")[-1]
        media_types = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }
        media_type = media_types.get(ext, "image/jpeg")

        enhanced_prompt = f"""
이 이미지를 분석하고, 아래 요청에 맞는 캡션을 생성해주세요.

{prompt}

이미지 내용을 반영하여 더 매력적인 캡션을 작성해주세요.
"""

        response = self.claude_client.client.messages.create(
            model=self.claude_client.config.model,
            max_tokens=1500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": enhanced_prompt},
                    ],
                }
            ],
        )

        return self._parse_ai_response(response.content[0].text)

    def _generate_text_only(self, prompt: str) -> Dict:
        """텍스트만으로 캡션 생성"""
        response = self.claude_client.client.messages.create(
            model=self.claude_client.config.model,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )

        return self._parse_ai_response(response.content[0].text)

    def _parse_ai_response(self, response_text: str) -> Dict:
        """AI 응답 파싱"""
        try:
            return json.loads(response_text.strip())
        except json.JSONDecodeError:
            # JSON 추출 시도
            match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if match:
                return json.loads(match.group())
            # 파싱 실패 시 원본 텍스트 반환
            return {"caption": response_text.strip(), "hashtags": []}

    # ============================================================
    # 3. add_cta_to_existing - 기존 캡션에 CTA 추가
    # ============================================================

    def add_cta_to_existing(
        self,
        existing_caption: str,
        cta_type: str = "profile_link"
    ) -> str:
        """
        기존 캡션에 CTA 문구 추가

        Args:
            existing_caption: 기존 캡션 텍스트
            cta_type: 추가할 CTA 유형

        Returns:
            CTA가 추가된 캡션
        """
        logger.info(f"기존 캡션에 CTA 추가 - 타입: {cta_type}")

        # CTA 타입별 문구 선택 (첫 번째 문구 사용)
        cta_phrases = CTA_PHRASES.get(cta_type, CTA_PHRASES["profile_link"])
        cta_phrase = cta_phrases[0]

        # CTA 블록 구성
        cta_block = f"""

━━━━━━━━━━━━━━━━
{cta_phrase}
━━━━━━━━━━━━━━━━"""

        # 기존 캡션에서 해시태그 분리
        hashtag_pattern = r'((?:#\S+\s*)+)$'
        match = re.search(hashtag_pattern, existing_caption)

        if match:
            # 해시태그가 있는 경우: 해시태그 앞에 CTA 삽입
            hashtags = match.group(1)
            main_caption = existing_caption[:match.start()].rstrip()
            result = f"{main_caption}{cta_block}\n\n{hashtags}"
        else:
            # 해시태그가 없는 경우: 캡션 끝에 CTA 추가
            result = f"{existing_caption}{cta_block}"

        # 길이 확인
        if len(result) > self.MAX_CAPTION_LENGTH:
            logger.warning(f"캡션 길이 초과: {len(result)}자 > {self.MAX_CAPTION_LENGTH}자")
            result = self.optimize_caption_length(result)

        logger.info(f"CTA 추가 완료 - 최종 길이: {len(result)}자")
        return result

    # ============================================================
    # 4. generate_hashtags - 해시태그 생성
    # ============================================================

    def generate_hashtags(
        self,
        product_description: str,
        count: int = 10
    ) -> List[str]:
        """
        관련 해시태그 생성 (인기 + 니치 혼합)

        Args:
            product_description: 상품/콘텐츠 설명
            count: 생성할 해시태그 개수

        Returns:
            해시태그 리스트 (# 포함)
        """
        logger.info(f"해시태그 생성 시작 - 개수: {count}")

        prompt = f"""
다음 상품/콘텐츠에 대한 Instagram 해시태그를 생성해주세요.

상품/콘텐츠: {product_description}

요구사항:
1. 총 {count}개의 해시태그 생성
2. 구성:
   - 인기 해시태그 (팔로워 많음): {count // 2}개
   - 니치 해시태그 (구체적, 타겟팅): {count - count // 2}개
3. 한국어 위주 (영어도 적절히 혼합)
4. # 기호 포함

JSON 배열로만 반환:
["#해시태그1", "#해시태그2", ...]
"""

        try:
            response = self.claude_client.client.messages.create(
                model=self.claude_client.config.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )

            result_text = response.content[0].text.strip()

            # JSON 파싱
            try:
                hashtags = json.loads(result_text)
            except json.JSONDecodeError:
                match = re.search(r"\[.*\]", result_text, re.DOTALL)
                if match:
                    hashtags = json.loads(match.group())
                else:
                    logger.error(f"해시태그 파싱 실패: {result_text}")
                    hashtags = []

            # # 기호 확인 및 추가
            hashtags = [f"#{tag}" if not tag.startswith("#") else tag for tag in hashtags]

            logger.info(f"해시태그 생성 완료: {len(hashtags)}개")
            return hashtags[:count]

        except Exception as e:
            logger.error(f"해시태그 생성 실패: {e}")
            return []

    # ============================================================
    # 5. optimize_caption_length - 캡션 길이 최적화
    # ============================================================

    def optimize_caption_length(
        self,
        caption: str,
        max_length: int = 2200
    ) -> str:
        """
        Instagram 캡션 길이 제한 준수하며 압축

        Args:
            caption: 원본 캡션
            max_length: 최대 길이 (기본 2200자)

        Returns:
            최적화된 캡션
        """
        if len(caption) <= max_length:
            return caption

        logger.info(f"캡션 길이 최적화 시작 - 원본: {len(caption)}자, 목표: {max_length}자")

        # 1. 해시태그 분리
        hashtag_pattern = r'((?:#\S+\s*)+)$'
        match = re.search(hashtag_pattern, caption)

        if match:
            hashtags = match.group(1).strip()
            main_content = caption[:match.start()].strip()
        else:
            hashtags = ""
            main_content = caption

        # 2. CTA 블록 분리 (구분선 포함)
        cta_pattern = r'(━+[\s\S]*?━+)'
        cta_matches = list(re.finditer(cta_pattern, main_content))

        cta_block = ""
        if cta_matches:
            # 마지막 CTA 블록 보존
            last_cta = cta_matches[-1]
            cta_block = last_cta.group(1)
            main_content = main_content[:last_cta.start()].strip()

        # 3. 필요한 공간 계산
        reserved_space = len(cta_block) + len(hashtags) + 10  # 여유 공간
        available_for_main = max_length - reserved_space

        # 4. 메인 콘텐츠 압축
        if len(main_content) > available_for_main:
            # 문장 단위로 분할
            sentences = re.split(r'([.!?。]\s*)', main_content)

            compressed = ""
            for i in range(0, len(sentences), 2):
                sentence = sentences[i]
                separator = sentences[i + 1] if i + 1 < len(sentences) else ""

                if len(compressed) + len(sentence) + len(separator) <= available_for_main:
                    compressed += sentence + separator
                else:
                    break

            main_content = compressed.strip()

            # 여전히 긴 경우 단어 단위로 자르기
            if len(main_content) > available_for_main:
                main_content = main_content[:available_for_main - 3] + "..."

        # 5. 재조합
        result_parts = [main_content]
        if cta_block:
            result_parts.append(cta_block)
        if hashtags:
            result_parts.append(hashtags)

        result = "\n\n".join(result_parts)

        # 최종 길이 확인
        if len(result) > max_length:
            result = result[:max_length - 3] + "..."

        logger.info(f"캡션 길이 최적화 완료 - 최종: {len(result)}자")
        return result

    # ============================================================
    # 6. get_cta_templates - CTA 템플릿 조회
    # ============================================================

    def get_cta_templates(self) -> Dict[str, str]:
        """
        사용 가능한 모든 CTA 템플릿 반환

        Returns:
            CTA 타입별 템플릿 딕셔너리
        """
        # 기본 템플릿 + 확장 템플릿 병합
        all_templates = {**CAPTION_CTA_TEMPLATES, **EXTENDED_CTA_TEMPLATES}

        logger.info(f"CTA 템플릿 조회 - 총 {len(all_templates)}개")
        return all_templates

    # ============================================================
    # 추가 유틸리티 메서드
    # ============================================================

    def get_cta_phrases(self, cta_type: Optional[str] = None) -> Dict[str, List[str]]:
        """
        CTA 문구 베스트 모음 반환

        Args:
            cta_type: 특정 CTA 타입 (None이면 전체 반환)

        Returns:
            CTA 문구 딕셔너리 또는 리스트
        """
        if cta_type:
            return {cta_type: CTA_PHRASES.get(cta_type, [])}
        return CTA_PHRASES

    def validate_caption(self, caption: str) -> Dict[str, any]:
        """
        캡션 유효성 검증

        Args:
            caption: 검증할 캡션

        Returns:
            검증 결과 딕셔너리
        """
        result = {
            "is_valid": True,
            "length": len(caption),
            "max_length": self.MAX_CAPTION_LENGTH,
            "has_cta": False,
            "has_hashtags": False,
            "hashtag_count": 0,
            "warnings": [],
        }

        # 길이 체크
        if len(caption) > self.MAX_CAPTION_LENGTH:
            result["is_valid"] = False
            result["warnings"].append(f"캡션이 너무 깁니다: {len(caption)}자 > {self.MAX_CAPTION_LENGTH}자")

        # CTA 체크
        cta_keywords = ["프로필", "링크", "DM", "댓글", "클릭", "확인"]
        if any(keyword in caption for keyword in cta_keywords):
            result["has_cta"] = True
        else:
            result["warnings"].append("CTA 문구가 없습니다")

        # 해시태그 체크
        hashtags = re.findall(r'#\S+', caption)
        result["has_hashtags"] = len(hashtags) > 0
        result["hashtag_count"] = len(hashtags)

        if len(hashtags) > 30:
            result["warnings"].append(f"해시태그가 너무 많습니다: {len(hashtags)}개 (권장: 5-15개)")
        elif len(hashtags) == 0:
            result["warnings"].append("해시태그가 없습니다")

        return result


# ============================================================
# 모듈 레벨 함수 (편의성)
# ============================================================

_optimizer: Optional[CaptionOptimizer] = None


def get_caption_optimizer() -> CaptionOptimizer:
    """전역 CaptionOptimizer 인스턴스 반환"""
    global _optimizer
    if _optimizer is None:
        _optimizer = CaptionOptimizer()
    return _optimizer


def create_cta_caption(product_info: Dict[str, str], cta_type: str = "profile_link") -> CaptionResult:
    """CTA 캡션 생성 (편의 함수)"""
    return get_caption_optimizer().create_cta_caption(product_info, cta_type)


def generate_caption_with_ai(
    product_description: str,
    image_path: Optional[str] = None,
    cta_type: str = "profile_link",
    hashtag_count: int = 5
) -> CaptionResult:
    """AI 캡션 생성 (편의 함수)"""
    return get_caption_optimizer().generate_caption_with_ai(
        product_description, image_path, cta_type, hashtag_count
    )


# ============================================================
# 테스트 코드
# ============================================================

if __name__ == "__main__":
    # 테스트용 상품 정보
    test_product = {
        "name": "여름 린넨 원피스",
        "description": "시원한 린넨 소재로 여름철 편안함을 선사합니다.",
        "price": "59,000원",
        "hashtags": ["여름원피스", "린넨원피스", "데일리룩", "여름패션", "OOTD"],
    }

    optimizer = CaptionOptimizer()

    print("=" * 50)
    print("1. CTA 캡션 생성 테스트")
    print("=" * 50)

    for cta_type in ["profile_link", "urgency", "limited", "dm", "comment"]:
        result = optimizer.create_cta_caption(test_product, cta_type)
        print(f"\n[{cta_type}]")
        print(result.caption)
        print(f"길이: {result.character_count}자")
        print("-" * 30)

    print("\n" + "=" * 50)
    print("2. CTA 템플릿 조회")
    print("=" * 50)
    templates = optimizer.get_cta_templates()
    print(f"사용 가능한 템플릿: {list(templates.keys())}")

    print("\n" + "=" * 50)
    print("3. CTA 문구 조회")
    print("=" * 50)
    phrases = optimizer.get_cta_phrases()
    for cta_type, phrase_list in phrases.items():
        print(f"\n[{cta_type}]")
        for phrase in phrase_list[:2]:
            print(f"  - {phrase}")

    print("\n" + "=" * 50)
    print("4. 기존 캡션에 CTA 추가")
    print("=" * 50)
    existing = "오늘의 코디 추천! 시원한 린넨 원피스로 여름을 준비하세요.\n\n#여름코디 #OOTD"
    result = optimizer.add_cta_to_existing(existing, "profile_link")
    print(result)

    print("\n" + "=" * 50)
    print("5. 캡션 유효성 검증")
    print("=" * 50)
    validation = optimizer.validate_caption(result)
    print(f"유효성: {validation['is_valid']}")
    print(f"길이: {validation['length']}자")
    print(f"CTA 포함: {validation['has_cta']}")
    print(f"해시태그: {validation['hashtag_count']}개")
    if validation['warnings']:
        print(f"경고: {validation['warnings']}")
