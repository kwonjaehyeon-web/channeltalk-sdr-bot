"""
기업 분석 엔진
- ICP 자동 추론
- Qualify 질문 자동 생성
- Pain Point 추론
- SaaS 솔루션 추천
"""

import os
import json
import threading
import httpx
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def analyze_and_send(company_name: str, response_url: str):
    thread = threading.Thread(
        target=_run_analysis,
        args=(company_name, response_url),
        daemon=True,
    )
    thread.start()


def _run_analysis(company_name: str, response_url: str):
    try:
        print(f"[분석 시작] {company_name}")
        result = _analyze(company_name)
        print(f"[분석 완료] 스코어={result.get('score')}")
        _send_report(response_url, company_name, result)
        print(f"[전송 완료]")
    except Exception as e:
        print(f"[에러] {e}")
        httpx.post(response_url, json={"text": f"*{company_name}* 분석 중 오류가 발생했습니다: {str(e)}"})


def _analyze(company_name: str) -> dict:
    prompt = f"""당신은 한국 B2B 세일즈 전략 전문가이자 AX 컨설턴트입니다.
{company_name}에 대해 아래 항목을 분석하세요.

다음 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{{
  "score": 0~100 사이 정수 (IT/SaaS 솔루션 구매 가능성),
  "score_reason": "스코어 산출 근거 한 줄",

  "org_summary": "조직 구조 요약 2~3줄 (규모, 주요 사업부, IT팀 여부)",

  "key_signals": [
    "영업에 유리한 신호 1 (구체적 근거 포함)",
    "영업에 유리한 신호 2",
    "영업에 유리한 신호 3"
  ],

  "icp_verdict": {{
    "fit": "high / medium / low",
    "reason": "ICP 적합 여부 판단 근거 2~3줄",
    "industry": "산업군",
    "revenue_tier": "매출 규모 추정 (예: 500억~1000억)",
    "saas_readiness": "SaaS 도입 가능성 (high/medium/low) + 근거 한 줄",
    "it_team_exists": true or false
  }},

  "pain_points": [
    {{
      "pain": "Pain Point 1 (구체적)",
      "evidence": "근거 (매출 감소, 인건비 증가 등)",
      "solution_hint": "이 Pain에 대응 가능한 솔루션 카테고리"
    }},
    {{
      "pain": "Pain Point 2",
      "evidence": "근거",
      "solution_hint": "솔루션 카테고리"
    }},
    {{
      "pain": "Pain Point 3",
      "evidence": "근거",
      "solution_hint": "솔루션 카테고리"
    }}
  ],

  "qualify_questions": [
    "첫 미팅에서 던질 Qualify 질문 1 (현재 운영 방식 파악용)",
    "Qualify 질문 2 (예산/의사결정 구조 파악용)",
    "Qualify 질문 3 (도입 장벽 파악용)",
    "Qualify 질문 4 (경쟁사/현재 솔루션 파악용)"
  ],

  "saas_recommendations": [
    {{
      "category": "솔루션 카테고리 (예: CRM, CS툴, HR, 마케팅 자동화)",
      "products": ["제품1", "제품2"],
      "reason": "이 솔루션이 맞는 이유 한 줄"
    }},
    {{
      "category": "두 번째 카테고리",
      "products": ["제품1", "제품2"],
      "reason": "이유"
    }}
  ],

  "decision_maker": "의사결정권자 추정 포지션",
  "approach_message": "첫 연락 시 사용할 맞춤 메시지 (2~3문장, 고객 Pain 중심으로 작성)",
  "caution": "주의할 점 또는 경쟁사 현황"
}}"""

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    return json.loads(response.choices[0].message.content)


def _send_report(response_url: str, company_name: str, data: dict):
    score = data.get("score", 0)
    score_emoji = "🟢" if score >= 60 else "🟡" if score >= 40 else "🔴"

    # ICP
    icp = data.get("icp_verdict", {})
    fit = icp.get("fit", "")
    fit_emoji = "🟢" if fit == "high" else "🟡" if fit == "medium" else "🔴"
    saas_ready = icp.get("saas_readiness", "")

    # 신호
    signals_text = "\n".join(f"• {s}" for s in data.get("key_signals", []))

    # Pain Points
    pain_text = "\n".join(
        f"• *{p['pain']}*\n  └ {p['evidence']} → _{p['solution_hint']}_"
        for p in data.get("pain_points", [])
    )

    # Qualify 질문
    qualify_text = "\n".join(
        f"{i+1}. {q}" for i, q in enumerate(data.get("qualify_questions", []))
    )

    # SaaS 추천
    saas_text = "\n".join(
        f"• *{r['category']}*: {', '.join(r['products'])}\n  └ {r['reason']}"
        for r in data.get("saas_recommendations", [])
    )

    blocks = [
        # 헤더
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{company_name}  {score_emoji} 구매 신호 스코어: {score}/100",
            },
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"_{data.get('score_reason', '')}_"},
        },
        {"type": "divider"},

        # ICP 판정
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*🎯 ICP 적합도: {fit_emoji} {fit.upper()}*\n"
                    f"{icp.get('reason', '')}\n"
                    f"산업군: {icp.get('industry', '')}  |  규모: {icp.get('revenue_tier', '')}  |  SaaS 도입 가능성: {saas_ready}"
                ),
            },
        },
        {"type": "divider"},

        # 조직 요약 + 핵심 신호
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*🏢 조직 요약*\n{data.get('org_summary', '')}"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*📌 핵심 신호*\n{signals_text}"},
        },
        {"type": "divider"},

        # Pain Points
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*🔥 Pain Points*\n{pain_text}"},
        },
        {"type": "divider"},

        # Qualify 질문
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*❓ 추천 Qualify 질문*\n{qualify_text}"},
        },
        {"type": "divider"},

        # SaaS 추천
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*💡 추천 솔루션*\n{saas_text}"},
        },
        {"type": "divider"},

        # 타겟 + 주의사항
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*👤 타겟 포지션*\n{data.get('decision_maker', '')}"},
                {"type": "mrkdwn", "text": f"*⚠️ 주의사항*\n{data.get('caution', '')}"},
            ],
        },
        {"type": "divider"},

        # 어프로치 메시지
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*💬 추천 어프로치 메시지*\n{data.get('approach_message', '')}",
            },
        },
    ]

    httpx.post(
        response_url,
        json={
            "response_type": "in_channel",
            "blocks": blocks,
            "text": f"{company_name} 인텔리전스 리포트",
        },
    )
