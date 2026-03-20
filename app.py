"""
Slack Socket Mode 봇 진입점
커맨드: /회사 [기업명]
"""

import os
import threading
import httpx
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from app.services.serper import SerperService
from app.services.llm import LLMService
from app.services.notion import NotionService
from app.routes.slack import _build_blocks

load_dotenv()

app = App(token=os.environ["SLACK_BOT_TOKEN"])

serper_service = SerperService()
llm_service    = LLMService()
notion_service = NotionService()


@app.command("/회사")
def handle_company(ack, command, respond):
    ack()
    company_name = command.get("text", "").strip()
    response_url = command["response_url"]

    if not company_name:
        respond("사용법: `/회사 기업명`\n예: `/회사 무신사`")
        return

    respond(f"*{company_name}* 분석 중입니다... ⏳")
    threading.Thread(target=_analyze, args=(company_name, response_url), daemon=True).start()


def _analyze(company_name: str, response_url: str):
    try:
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

    except Exception as e:
        httpx.post(response_url, json={"text": f"*{company_name}* 분석 중 오류: {str(e)}"}, timeout=5)


if __name__ == "__main__":
    print("봇 시작 중...")
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    handler.start()
