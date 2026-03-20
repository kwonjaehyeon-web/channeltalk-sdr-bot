"""
FastAPI 메인 앱

엔드포인트:
  POST /analyze       → 직접 분석 API
  POST /slack/command → Slack 슬래시 커맨드 수신
  GET  /health        → 헬스체크
"""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from loguru import logger

from app.models.schema import AnalyzeRequest, AnalyzeResponse
from app.services.serper import SerperService
from app.services.llm import LLMService
from app.services.notion import NotionService
from app.routes.slack import router as slack_router

app = FastAPI(title="ChannelTalk SDR Analyzer", version="2.0.0")

serper_service = SerperService()
llm_service    = LLMService()
notion_service = NotionService()

app.include_router(slack_router)


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    company_name = request.company_name.strip()
    if not company_name:
        return JSONResponse(status_code=400, content={"error": "company_name이 비어있습니다.", "company_name": ""})

    logger.info(f"[/analyze] {company_name}")

    try:
        search_data = serper_service.fetch_all(company_name)
        result      = llm_service.analyze(company_name, search_data)
        notion_url  = notion_service.save(company_name, result)

        return AnalyzeResponse(
            company_name          = company_name,
            company_summary       = result.get("company_summary", ""),
            icp_industry          = result.get("icp_industry", ""),
            icp_scale             = result.get("icp_scale", ""),
            icp_fit               = result.get("icp_fit", "Medium"),
            icp_fit_reason        = result.get("icp_fit_reason", ""),
            problem               = result.get("problem", ""),
            problem_evidence      = result.get("problem_evidence", ""),
            channeltalk_solution  = result.get("channeltalk_solution", ""),
            decision_maker        = result.get("decision_maker", ""),
            decision_maker_reason = result.get("decision_maker_reason", ""),
            notion_url            = notion_url,
        )

    except Exception as e:
        logger.error(f"[/analyze] {company_name} 실패: {e}")
        return JSONResponse(status_code=500, content={"error": str(e), "company_name": company_name})


@app.get("/health")
async def health():
    return {"status": "ok"}
