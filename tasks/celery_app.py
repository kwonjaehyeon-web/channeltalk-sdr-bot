"""
Celery 비동기 태스크
- analyze_company_task: 기업 분석 메인 파이프라인
- add_to_watchlist_task: 워치리스트 등록
- batch_monitor_task: 매일 새벽 2시 변화 감지 (스케줄)
"""

import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# ─── Celery 설정 ─────────────────────────────────────────────────────────────

celery = Celery(
    "sales_intel",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    task_track_started=True,
    task_acks_late=True,              # 작업 실패 시 재시도 보장
    worker_prefetch_multiplier=1,     # 분석 작업은 무거우므로 1개씩 처리
)

# 매일 새벽 2시 배치 모니터링
celery.conf.beat_schedule = {
    "daily-watchlist-monitor": {
        "task": "tasks.celery_app.batch_monitor_task",
        "schedule": crontab(hour=2, minute=0),
    },
}


# ─── 메인 분석 태스크 ─────────────────────────────────────────────────────────

@celery.task(bind=True, max_retries=2, default_retry_delay=60)
def analyze_company_task(self, company_name: str, channel_id: str, user_id: str):
    """
    기업 분석 파이프라인:
    1. 캐시 확인 → 있으면 바로 전송
    2. 수집: DART + 채용공고 + 뉴스
    3. 신호 감지 + 스코어 계산
    4. LLM 인사이트 생성
    5. Slack으로 리포트 전송
    """
    from src.collectors.dart_collector import DartCollector
    from src.collectors.job_crawler import JobCrawler
    from src.collectors.search_collector import SearchCollector
    from src.engines.signal_detector import SignalDetector
    from src.engines.llm_orchestrator import LLMOrchestrator
    from src.db.session import get_cached_report, save_report
    from slack_sdk import WebClient

    slack_client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])

    try:
        logger.info(f"[{company_name}] 분석 시작")

        # 1. 캐시 확인 (24시간)
        cached = get_cached_report(company_name)
        if cached:
            logger.info(f"[{company_name}] 캐시 히트")
            _send_report(slack_client, channel_id, cached)
            return

        # 2. 병렬 수집
        dart = DartCollector()
        jobs = JobCrawler()
        search = SearchCollector()

        dart_data = dart.fetch(company_name)
        job_data = jobs.fetch(company_name)
        news_data = search.fetch(company_name)

        logger.info(f"[{company_name}] 수집 완료: DART={len(dart_data)}건, 채용={len(job_data)}건, 뉴스={len(news_data)}건")

        # 3. 신호 감지 + 스코어
        detector = SignalDetector()
        signals = detector.detect(dart_data, job_data, news_data)
        score = detector.score(signals)

        # 4. LLM 인사이트 생성
        llm = LLMOrchestrator()
        insight = llm.generate(company_name, signals, score)

        # 5. 리포트 조립 및 저장
        report = {
            "company_name": company_name,
            "score": score,
            "signals": signals,
            "insight": insight,
        }
        save_report(company_name, report)

        # 6. Slack 전송
        _send_report(slack_client, channel_id, report)
        logger.info(f"[{company_name}] 분석 완료 → 스코어={score}")

    except Exception as exc:
        logger.error(f"[{company_name}] 분석 실패: {exc}")
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            slack_client.chat_postMessage(
                channel=channel_id,
                text=f"*{company_name}* 분석 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            )


# ─── 워치리스트 등록 ──────────────────────────────────────────────────────────

@celery.task
def add_to_watchlist_task(company_name: str, user_id: str, channel_id: str):
    from src.db.session import add_watchlist
    add_watchlist(company_name, user_id, channel_id)
    logger.info(f"워치리스트 등록: {company_name} / user={user_id}")


# ─── 배치 모니터링 (매일 새벽 2시) ───────────────────────────────────────────

@celery.task
def batch_monitor_task():
    """워치리스트 기업 변화 감지 → 변화 있는 기업만 알림 발송"""
    from src.db.session import get_all_watchlist_entries
    from src.engines.signal_detector import SignalDetector
    from slack_sdk import WebClient

    slack_client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    detector = SignalDetector()
    entries = get_all_watchlist_entries()

    for entry in entries:
        company_name = entry["company_name"]
        channel_id = entry["channel_id"]

        try:
            changed, summary = detector.check_delta(company_name)
            if changed:
                slack_client.chat_postMessage(
                    channel=channel_id,
                    text=f"📡 *{company_name}* 변화 감지\n{summary}\n`/intel {company_name}` 으로 전체 리포트 확인",
                )
                logger.info(f"[배치] {company_name} 변화 감지 → 알림 발송")
        except Exception as e:
            logger.error(f"[배치] {company_name} 처리 실패: {e}")


# ─── Slack 리포트 전송 (Block Kit) ───────────────────────────────────────────

def _send_report(slack_client, channel_id: str, report: dict):
    """Slack Block Kit 형태로 인텔리전스 리포트 전송"""
    company = report["company_name"]
    score = report["score"]
    insight = report["insight"]
    signals = report.get("signals", {})

    # 스코어 이모지
    score_emoji = "🟢" if score >= 60 else "🟡" if score >= 40 else "🔴"

    # 핵심 신호 텍스트
    signal_lines = []
    for s in signals.get("top_signals", [])[:4]:
        signal_lines.append(f"• {s['description']}")
    signal_text = "\n".join(signal_lines) if signal_lines else "• 수집된 신호 없음"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{company}  {score_emoji} 구매 신호 스코어: {score}"},
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*📌 핵심 신호 (최근 30일)*\n{signal_text}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🏢 조직 추정*\n{insight.get('org_structure', '분석 중')}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*💬 추천 어프로치*\n{insight.get('approach_message', '생성 중')}",
            },
        },
        {"type": "divider"},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📊 Sheets 내보내기"},
                    "action_id": "export_sheets",
                    "value": company,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "👁 워치리스트 추가"},
                    "action_id": "add_to_watchlist",
                    "value": company,
                    "style": "primary",
                },
            ],
        },
    ]

    slack_client.chat_postMessage(channel=channel_id, blocks=blocks, text=f"{company} 인텔리전스 리포트")
