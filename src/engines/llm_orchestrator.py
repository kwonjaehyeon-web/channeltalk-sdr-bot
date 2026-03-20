"""
LLM 오케스트레이션 엔진

단계별 모델 분리:
  Step 1 (구조화 추출) → 소형 모델 (gpt-4o-mini)
  Step 2 (신호 해석)   → 중형 모델 (gpt-4o)
  Step 3 (인사이트)    → 고성능 모델 (gpt-4o or claude)
  Fallback: OpenAI → Gemini 자동 전환
"""

import os
import json
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential


class LLMOrchestrator:

    def __init__(self):
        self.provider = os.environ.get("LLM_PROVIDER", "openai")
        self._init_clients()

    def _init_clients(self):
        self._openai = None
        self._gemini = None

        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            from openai import OpenAI
            self._openai = OpenAI(api_key=openai_key)

        gemini_key = os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            self._gemini = genai.GenerativeModel("gemini-1.5-flash")

        if not self._openai and not self._gemini:
            logger.warning("LLM API 키 없음 — 더미 인사이트 반환")

    def generate(self, company_name: str, signals: dict, score: int) -> dict:
        """
        수집 신호 → 영업 인사이트 생성
        Returns:
            org_structure: 조직 구조 추정
            key_insight: 핵심 인사이트 1줄
            approach_message: 추천 어프로치 메시지
            entry_point: 영업 진입 포인트
        """
        if not self._openai and not self._gemini:
            return self._dummy_insight(company_name, score)

        prompt = self._build_prompt(company_name, signals, score)

        try:
            raw = self._call_llm(prompt, model_tier="high")
            return self._parse_response(raw)
        except Exception as e:
            logger.error(f"[LLM] 인사이트 생성 실패: {e}")
            return self._dummy_insight(company_name, score)

    # ─── 프롬프트 ──────────────────────────────────────────────────────────────

    def _build_prompt(self, company_name: str, signals: dict, score: int) -> str:
        job_summary = signals.get("job_summary", {})
        top_signals = signals.get("top_signals", [])
        dart_events = signals.get("dart_events", [])

        signal_text = "\n".join(
            f"- [{s['confidence']}] {s['description']}" for s in top_signals
        )
        dart_text = "\n".join(
            f"- {e['type']}: {e['title']} ({e['date']})" for e in dart_events
        ) or "없음"

        return f"""당신은 한국 B2B 세일즈 전략 전문가입니다.
아래 데이터를 바탕으로 {company_name}에 대한 영업 인사이트를 분석해주세요.

## 수집 데이터

**채용 현황**
- 총 공고: {job_summary.get('total', 0)}건
- IT/DX 비중: {int(job_summary.get('tech_ratio', 0) * 100)}%
- 관리자급 채용: {job_summary.get('management_count', 0)}건
- 직군별: {job_summary.get('categories', {})}

**주요 공시 이벤트**
{dart_text}

**감지된 영업 신호**
{signal_text}

**종합 구매 신호 스코어**: {score}/100

## 출력 형식 (JSON만 출력, 다른 텍스트 없이)
{{
  "org_structure": "조직 구조 2-3줄 추정 (부서명, 핵심 부서 등)",
  "key_insight": "가장 중요한 인사이트 1줄 (최대 50자)",
  "approach_message": "첫 연락 시 사용할 맞춤 메시지 (2-3문장, 우리 솔루션 언급 없이 고객 상황 중심으로)",
  "entry_point": "영업 진입 가장 적합한 포지션 또는 부서",
  "timing": "지금 접근이 적합한 이유 1줄"
}}"""

    # ─── LLM 호출 ─────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    def _call_llm(self, prompt: str, model_tier: str = "high") -> str:
        model_map = {
            "low": "gpt-4o-mini",
            "mid": "gpt-4o",
            "high": "gpt-4o",
        }

        # OpenAI 우선 시도
        if self._openai:
            try:
                response = self._openai.chat.completions.create(
                    model=model_map.get(model_tier, "gpt-4o"),
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    response_format={"type": "json_object"},
                )
                return response.choices[0].message.content
            except Exception as e:
                logger.warning(f"[OpenAI] 실패, Gemini fallback 시도: {e}")

        # Gemini fallback
        if self._gemini:
            response = self._gemini.generate_content(prompt)
            return response.text

        raise RuntimeError("사용 가능한 LLM 없음")

    def _parse_response(self, raw: str) -> dict:
        try:
            # JSON 블록만 추출
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]
            return json.loads(raw.strip())
        except json.JSONDecodeError:
            logger.warning(f"[LLM] JSON 파싱 실패, 원문 반환")
            return {
                "org_structure": raw[:200],
                "key_insight": "",
                "approach_message": "",
                "entry_point": "",
                "timing": "",
            }

    def _dummy_insight(self, company_name: str, score: int) -> dict:
        """API 키 없을 때 반환하는 더미 (개발/테스트용)"""
        return {
            "org_structure": f"{company_name}의 조직 구조 분석 (API 키 설정 후 활성화)",
            "key_insight": f"스코어 {score}점 — API 키 설정 후 상세 인사이트 확인 가능",
            "approach_message": ".env 파일에 OPENAI_API_KEY 또는 GEMINI_API_KEY를 설정해주세요.",
            "entry_point": "설정 필요",
            "timing": "설정 필요",
        }
