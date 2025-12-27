"""
Claude AI 클라이언트
=====================================
광고 카피 생성, 댓글 의도 분석, 이미지 분석 등 AI 기능 제공
"""

import os
import base64
import json
from typing import List, Dict, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ClaudeConfig:
    """Claude API 설정"""

    api_key: str
    model: str = "claude-sonnet-4-20250514"  # 기본 모델
    max_tokens: int = 1000

    @classmethod
    def from_env(cls) -> "ClaudeConfig":
        """환경 변수에서 설정 로드"""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY 환경 변수가 설정되지 않았습니다")

        return cls(
            api_key=api_key, model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
        )


class ClaudeClient:
    """Claude AI 클라이언트"""

    def __init__(self, config: Optional[ClaudeConfig] = None):
        self.config = config or ClaudeConfig.from_env()
        self._client = None

    @property
    def client(self):
        """Anthropic 클라이언트 (lazy loading)"""
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.config.api_key)
        return self._client

    # ============================================================
    # 광고 카피 생성
    # ============================================================

    def generate_ad_copies(
        self, image_path: str, count: int = 10, brand_tone: str = "친근하고 세련된"
    ) -> List[Dict]:
        """
        이미지 분석 후 광고 카피 생성

        Args:
            image_path: 이미지 파일 경로
            count: 생성할 카피 개수 (기본 10개)
            brand_tone: 브랜드 톤앤매너

        Returns:
            [{"text": "...", "cta_type": "SHOP_NOW", "theme": "urgency"}, ...]
        """

        # 이미지 base64 인코딩
        with open(image_path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")

        # 파일 확장자로 미디어 타입 결정
        ext = image_path.lower().split(".")[-1]
        media_types = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }
        media_type = media_types.get(ext, "image/jpeg")

        prompt = f"""
이 이미지를 보고 Instagram 광고 카피 {count}개를 JSON 배열로 생성해주세요.

브랜드 톤앤매너: {brand_tone}

각 카피 요구사항:
- 메인 문구: 20자 이내, 임팩트 있게
- CTA 타입: SHOP_NOW, LEARN_MORE, SIGN_UP, GET_OFFER 중 하나
- 테마: urgency(긴급성), social_proof(사회적 증거), value(가치), style(스타일) 등

다양한 심리 트리거를 활용하세요.

JSON 형식만 반환 (다른 텍스트 없이):
[
  {{"text": "24시간만 특가 🔥", "cta_type": "SHOP_NOW", "theme": "urgency"}},
  {{"text": "10,000명이 선택", "cta_type": "SHOP_NOW", "theme": "social_proof"}},
  ...
]
"""

        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
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
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        result_text = response.content[0].text.strip()

        # JSON 파싱
        try:
            return json.loads(result_text)
        except json.JSONDecodeError:
            # JSON 추출 시도
            import re

            match = re.search(r"\[.*\]", result_text, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError(f"카피 생성 결과 파싱 실패: {result_text}")

    # ============================================================
    # 댓글 의도 분석
    # ============================================================

    def analyze_comment_intent(self, comment: str) -> str:
        """
        댓글 의도 분석

        Args:
            comment: 댓글 텍스트

        Returns:
            의도 분류 (price, size, stock, shipping, purchase, compliment, spam, other)
        """

        prompt = f"""
다음 인스타그램 댓글의 의도를 한 단어로 분류해주세요.

댓글: "{comment}"

분류 옵션:
- price (가격 문의)
- size (사이즈 문의)
- stock (재고 문의)
- shipping (배송 문의)
- purchase (구매 의사)
- compliment (칭찬)
- spam (스팸)
- other (기타)

답변은 분류명만 (한 단어):
"""

        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=20,
            messages=[{"role": "user", "content": prompt}],
        )

        intent = response.content[0].text.strip().lower()

        # 유효한 의도인지 확인
        valid_intents = [
            "price",
            "size",
            "stock",
            "shipping",
            "purchase",
            "compliment",
            "spam",
            "other",
        ]
        return intent if intent in valid_intents else "other"

    # ============================================================
    # 캡션 CTA 최적화
    # ============================================================

    def generate_cta_caption(
        self,
        product_description: str,
        cta_type: str = "profile_link",
        hashtag_count: int = 5,
    ) -> str:
        """
        CTA가 포함된 캡션 생성

        Args:
            product_description: 상품 설명
            cta_type: CTA 유형 (profile_link, urgency, limited)
            hashtag_count: 해시태그 개수

        Returns:
            완성된 캡션 텍스트
        """

        prompt = f"""
다음 상품에 대한 Instagram 캡션을 작성해주세요.

상품 정보: {product_description}
CTA 유형: {cta_type}
해시태그 개수: {hashtag_count}개

요구사항:
1. 메인 메시지는 매력적이고 간결하게
2. 프로필 링크 클릭 유도 문구 포함
3. 이모지 적절히 활용
4. 관련 해시태그 {hashtag_count}개 포함

캡션만 반환 (다른 텍스트 없이):
"""

        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text.strip()

    # ============================================================
    # 이미지 품질 분석 (UGC 평가용)
    # ============================================================

    def analyze_image_quality(self, image_path: str) -> Dict:
        """
        이미지 품질 분석 (광고 적합성 평가)

        Returns:
            {
                "quality_score": 8,
                "brightness": "적정",
                "composition": "좋음",
                "product_visibility": "높음",
                "recommendation": "광고 사용 적합"
            }
        """

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

        prompt = """
이 이미지를 Instagram 광고용으로 분석해주세요.

JSON 형식으로만 반환:
{
    "quality_score": (1-10점),
    "brightness": "어두움/적정/밝음",
    "composition": "나쁨/보통/좋음",
    "product_visibility": "낮음/중간/높음",
    "recommendation": "광고 사용 적합/부적합/수정 필요"
}
"""

        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=200,
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
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        result_text = response.content[0].text.strip()

        try:
            return json.loads(result_text)
        except json.JSONDecodeError:
            import re

            match = re.search(r"\{.*\}", result_text, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError(f"이미지 분석 결과 파싱 실패: {result_text}")


# 싱글톤 인스턴스
_client: Optional[ClaudeClient] = None


def get_claude_client() -> ClaudeClient:
    """전역 Claude 클라이언트 반환"""
    global _client
    if _client is None:
        _client = ClaudeClient()
    return _client
