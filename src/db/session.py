"""
DB 세션 및 헬퍼 함수
SQLAlchemy Core 사용 (ORM 없이 간단하게)
"""

import os
import json
from datetime import datetime, timedelta
from loguru import logger
from sqlalchemy import create_engine, text

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            logger.warning("DATABASE_URL 미설정 — DB 기능 비활성화")
            return None
        _engine = create_engine(db_url, pool_pre_ping=True)
    return _engine


# ─── 기업 ────────────────────────────────────────────────────────────────────

def get_or_create_company(name: str) -> int | None:
    engine = get_engine()
    if not engine:
        return None
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM companies WHERE name = :name"), {"name": name}
        ).fetchone()
        if row:
            return row[0]
        result = conn.execute(
            text("INSERT INTO companies (name) VALUES (:name) RETURNING id"), {"name": name}
        )
        conn.commit()
        return result.fetchone()[0]


# ─── 리포트 캐시 ─────────────────────────────────────────────────────────────

def get_cached_report(company_name: str, max_age_hours: int = 24) -> dict | None:
    engine = get_engine()
    if not engine:
        return None
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT r.full_report
                FROM intelligence_reports r
                JOIN companies c ON c.id = r.company_id
                WHERE c.name = :name
                  AND r.generated_at > NOW() - INTERVAL ':hours hours'
                ORDER BY r.generated_at DESC
                LIMIT 1
            """),
            {"name": company_name, "hours": max_age_hours},
        ).fetchone()
        return row[0] if row else None


def save_report(company_name: str, report: dict):
    engine = get_engine()
    if not engine:
        return
    company_id = get_or_create_company(company_name)
    if not company_id:
        return
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO intelligence_reports
                    (company_id, score, org_structure, key_insight, approach_msg, entry_point, timing_note, full_report)
                VALUES
                    (:company_id, :score, :org, :insight, :approach, :entry, :timing, :full)
            """),
            {
                "company_id": company_id,
                "score": report.get("score", 0),
                "org": report.get("insight", {}).get("org_structure", ""),
                "insight": report.get("insight", {}).get("key_insight", ""),
                "approach": report.get("insight", {}).get("approach_message", ""),
                "entry": report.get("insight", {}).get("entry_point", ""),
                "timing": report.get("insight", {}).get("timing", ""),
                "full": json.dumps(report, ensure_ascii=False),
            },
        )
        conn.commit()


# ─── 워치리스트 ──────────────────────────────────────────────────────────────

def get_watchlist(user_id: str) -> list[str]:
    engine = get_engine()
    if not engine:
        return []
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT c.name FROM watchlist w
                JOIN companies c ON c.id = w.company_id
                WHERE w.user_id = :user_id
                ORDER BY w.added_at DESC
            """),
            {"user_id": user_id},
        ).fetchall()
        return [r[0] for r in rows]


def add_watchlist(company_name: str, user_id: str, channel_id: str):
    engine = get_engine()
    if not engine:
        return
    company_id = get_or_create_company(company_name)
    if not company_id:
        return
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO watchlist (company_id, user_id, channel_id)
                VALUES (:company_id, :user_id, :channel_id)
                ON CONFLICT (company_id, user_id) DO NOTHING
            """),
            {"company_id": company_id, "user_id": user_id, "channel_id": channel_id},
        )
        conn.commit()


def get_all_watchlist_entries() -> list[dict]:
    engine = get_engine()
    if not engine:
        return []
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT DISTINCT ON (w.company_id) c.name, w.channel_id
                FROM watchlist w
                JOIN companies c ON c.id = w.company_id
            """)
        ).fetchall()
        return [{"company_name": r[0], "channel_id": r[1]} for r in rows]
