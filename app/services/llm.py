"""
LLM 서비스 — 채널톡 SDR 특화 고객 분석
Serper 검색 결과를 바탕으로 ICP + Qualify 분석 수행
"""

import os
import json
from loguru import logger
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))


class LLMService:

    def analyze(self, company_name: str, search_data: dict, channeltalk_context: str = "", analysis_guidelines: str = "") -> dict:
        """
        search_data: SerperService.fetch_all() 결과
        channeltalk_context: Notion 컨텍스트 페이지 텍스트
        반환: ICP + Qualify 분석 결과 dict
        """
        prompt = self._build_prompt(company_name, search_data, channeltalk_context, analysis_guidelines)

        try:
            raw = self._call_openai(prompt)
            result = json.loads(raw)
            logger.info(f"[LLM] {company_name} 분석 완료")
            return result
        except Exception as e:
            logger.error(f"[LLM] 분석 실패: {e}")
            return self._fallback(company_name)

    # ── 프롬프트 ────────────────────────────────────────────────────────────────

    def _build_prompt(self, company_name: str, search_data: dict, channeltalk_context: str = "", analysis_guidelines: str = "") -> str:
        overview_text  = self._format_results(search_data.get("overview", []))
        scale_text     = self._format_results(search_data.get("scale", []))
        news_text      = self._format_results(search_data.get("news", []))
        jobs_text      = self._format_results(search_data.get("jobs", []))
        linkedin_text  = self._format_results(search_data.get("linkedin", []))

        context_section = ""
        if channeltalk_context:
            context_section = f"""
## 채널톡 제품 컨텍스트 (반드시 이 내용을 기반으로 솔루션 매칭할 것)
{channeltalk_context}

---
"""

        guidelines_section = ""
        if analysis_guidelines:
            guidelines_section = f"""
## SDR 분석 가이드라인 (반드시 이 판단 기준을 따를 것)
{analysis_guidelines}

---
"""

        default_guidelines = "" if analysis_guidelines else """
**ICP 분석**
- 산업군: 커머스/SaaS/오프라인 서비스/핀테크/헬스케어 등 구체적으로 분류
- 규모/매출: 검색 결과에서 투자 유치, 임직원 수, 매출 정보 추출. 없으면 "(추정)" 표기
  예시: "Series B 100억 투자유치 → 성장기 스타트업", "임직원 200명 → 중소기업"

**Problem 분석** (채용 공고 중심)
- JD에서 CS/고객응대/마케팅 관련 채용이 있으면 → 해당 팀 부담 증가로 해석
- 뉴스에서 급성장, 사용자 급증, 서비스 확장 → CS 문의 폭증 가능성
- 구체적 근거를 반드시 포함

**채널톡 솔루션 매칭**
- CS 문의 폭증/CS 채용 → 서포트봇으로 단순 문의 자동화
- 마케팅팀 채용/리텐션 이슈 → CRM 마케팅으로 타겟 캠페인
- 리모트/하이브리드 팀 → 팀 채팅으로 협업 효율화
- 복합적 상황이면 여러 기능 조합 제안

**의사결정자 추론**
- 커머스: CX팀장, 마케팅 본부장
- SaaS: CS 리드, Growth 팀장
- 오프라인 서비스: 운영팀장, 대표이사(소규모)
- 산업/규모에 맞게 추론
- 링크드인 검색 결과에 실제 인물이 있으면 반드시 언급할 것
"""

        return f"""당신은 채널톡(ChannelTalk) B2B SDR 전문가입니다.
아래 채널톡 컨텍스트와 기업 검색 데이터를 분석해 {company_name}에 대한 SDR 분석 리포트를 작성하세요.
{context_section}{guidelines_section}
## 기업 개요
{overview_text}

## 규모 / 투자 정보
{scale_text}

## 최신 뉴스
{news_text}

## 채용 공고
{jobs_text}

## 링크드인 — 의사결정자 후보
{linkedin_text}

## 분석 지침
{default_guidelines}

## 출력 형식 (JSON만, 다른 텍스트 없이)
{{
  "icp_industry": "산업군 (예: 커머스 - 패션/뷰티)",
  "icp_scale": "규모/매출 추정 (예: Series B 스타트업, 임직원 약 150명)",
  "icp_fit": "High | Medium | Low",
  "icp_fit_reason": "ICP 판단 근거 1~2문장",
  "problem": "핵심 문제 상황 (구체적 근거 포함, 2~3문장)",
  "problem_evidence": "근거가 된 채용공고 또는 뉴스 제목/내용",
  "channeltalk_solution": "채널톡으로 해결하는 방법 (구체적 기능명 포함, 2~3문장)",
  "decision_maker": "의사결정권자 추정 직함 (예: CX팀장 또는 마케팅 본부장)",
  "decision_maker_reason": "해당 직함으로 추론한 이유",
  "company_summary": "기업 한 줄 요약"
}}"""

    def _format_results(self, results: list[dict]) -> str:
        if not results:
            return "(검색 결과 없음)"
        lines = []
        for r in results:
            lines.append(f"- {r['title']}\n  {r['snippet']}")
        return "\n".join(lines)

    # ── LLM 호출 ───────────────────────────────────────────────────────────────

    def _call_openai(self, prompt: str) -> str:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    def _fallback(self, company_name: str) -> dict:
        return {
            "icp_industry": "분석 불가",
            "icp_scale": "분석 불가",
            "icp_fit": "Medium",
            "icp_fit_reason": "LLM 분석 실패 — 검색 데이터 기반 수동 확인 필요",
            "problem": "LLM 분석 실패",
            "problem_evidence": "-",
            "channeltalk_solution": "LLM 분석 실패",
            "decision_maker": "CS팀장 / 마케팅팀장 (추정)",
            "decision_maker_reason": "LLM 분석 실패",
            "company_summary": f"{company_name} — 분석 실패",
        }
