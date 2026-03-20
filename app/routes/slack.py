"""
Slack 슬래시 커맨드 라우트 (/회사)
즉시 ack → 백그라운드 분석 → Slack 리포트 + Notion 저장
"""

import hashlib
import hmac
import os
import time
import threading
from urllib.parse import parse_qs

import httpx
from fastapi import APIRouter, Request, HTTPException
from loguru import logger

from app.services.serper import SerperService
from app.services.llm import LLMService
from app.services.notion import NotionService

router = APIRouter()

serper_service = SerperService()
llm_service    = LLMService()
notion_service = NotionService()


# ── 슬래시 커맨드 엔드포인트 ──────────────────────────────────────────────────

@router.post("/slack/command")
async def slack_command(request: Request):
    body_bytes = await request.body()
    _verify_slack_signature(request.headers, body_bytes)

    params       = parse_qs(body_bytes.decode("utf-8"))
    company_name = params.get("text", [""])[0].strip()
    response_url = params.get("response_url", [""])[0]
    user_name    = params.get("user_name", ["unknown"])[0]

    if not company_name:
        return {
            "response_type": "ephemeral",
            "text": "사용법: `/회사 기업명`\n예: `/회사 무신사`",
        }

    logger.info(f"[Slack] {user_name} → {company_name}")

    threading.Thread(
        target=_run_and_respond,
        args=(company_name, response_url),
        daemon=True,
    ).start()

    return {
        "response_type": "in_channel",
        "text": f"*{company_name}* 분석 중입니다... ⏳",
    }


# ── 분석 파이프라인 ───────────────────────────────────────────────────────────

def _run_and_respond(company_name: str, response_url: str):
    try:
        logger.info(f"[분석 시작] {company_name}")

        ct_context  = notion_service.fetch_channeltalk_context()
        search_data = serper_service.fetch_all(company_name)
        result      = llm_service.analyze(company_name, search_data, ct_context)
        notion_url  = notion_service.save(company_name, result)

        blocks = _build_blocks(company_name, result, notion_url)
        httpx.post(
            response_url,
            json={"response_type": "in_channel", "blocks": blocks, "text": f"{company_name} 분석 완료"},
            timeout=10,
        )
        logger.info(f"[전송 완료] {company_name}")

    except Exception as e:
        logger.error(f"[에러] {company_name}: {e}")
        httpx.post(
            response_url,
            json={"text": f"*{company_name}* 분석 중 오류: {str(e)}"},
            timeout=5,
        )


# ── Block Kit 조립 ────────────────────────────────────────────────────────────

def _build_blocks(company_name: str, r: dict, notion_url: str | None) -> list:
    icp_fit   = r.get("icp_fit", "Medium")
    fit_emoji = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}.get(icp_fit, "🟡")

    notion_line = f"\n<{notion_url}|📎 Notion에서 보기>" if notion_url else ""

    return [
        # 헤더
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📊 {company_name} SDR 분석 리포트"},
        },
        {"type": "divider"},

        # ICP
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*🎯 ICP 분석*\n"
                    f"• 산업: {r.get('icp_industry', '-')}\n"
                    f"• 규모/매출: {r.get('icp_scale', '-')}\n"
                    f"• 적합도: {fit_emoji} *{icp_fit}* — {r.get('icp_fit_reason', '')}"
                ),
            },
        },
        {"type": "divider"},

        # Problem
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*🔥 회사의 문제 (Problem)*\n"
                    f"{r.get('problem', '-')}\n"
                    f"_근거: {r.get('problem_evidence', '-')}_"
                ),
            },
        },
        {"type": "divider"},

        # 채널톡 솔루션
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*💬 채널톡 솔루션 매칭*\n{r.get('channeltalk_solution', '-')}",
            },
        },
        {"type": "divider"},

        # 의사결정자
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*👤 의사결정자*\n"
                    f"{r.get('decision_maker', '-')}\n"
                    f"_이유: {r.get('decision_maker_reason', '-')}_"
                    f"{notion_line}"
                ),
            },
        },
    ]


# ── Slack 서명 검증 ───────────────────────────────────────────────────────────

def _verify_slack_signature(headers, body: bytes):
    signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "")
    if not signing_secret:
        return

    timestamp = headers.get("x-slack-request-timestamp", "")
    if abs(time.time() - int(timestamp)) > 60 * 5:
        raise HTTPException(status_code=403, detail="Timestamp too old")

    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    computed = "v0=" + hmac.new(
        signing_secret.encode(), sig_basestring.encode(), hashlib.sha256
    ).hexdigest()
    slack_sig = headers.get("x-slack-signature", "")

    if not hmac.compare_digest(computed, slack_sig):
        raise HTTPException(status_code=403, detail="Invalid signature")
