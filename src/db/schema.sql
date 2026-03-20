-- Sales Intelligence Platform — PostgreSQL 스키마
-- 실행: psql -d sales_intel -f src/db/schema.sql

-- ─── 기업 마스터 ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS companies (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(200) NOT NULL UNIQUE,
    dart_code   VARCHAR(20),                    -- DART 고유 기업코드
    industry    VARCHAR(100),
    employee_est INT,                           -- 추정 임직원수
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

-- ─── 채용공고 ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS job_postings (
    id            SERIAL PRIMARY KEY,
    company_id    INT REFERENCES companies(id) ON DELETE CASCADE,
    source        VARCHAR(50) NOT NULL,         -- saramin | jobkorea | wanted
    title         VARCHAR(500) NOT NULL,
    category      VARCHAR(50),                  -- tech | dx | management | data | ops | sales | other
    is_management BOOLEAN DEFAULT FALSE,
    posted_date   DATE,
    collected_at  TIMESTAMP DEFAULT NOW(),
    raw_data      JSONB
);

CREATE INDEX IF NOT EXISTS idx_job_company ON job_postings(company_id);
CREATE INDEX IF NOT EXISTS idx_job_category ON job_postings(category);
CREATE INDEX IF NOT EXISTS idx_job_collected ON job_postings(collected_at);

-- ─── DART 공시 ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dart_filings (
    id          SERIAL PRIMARY KEY,
    company_id  INT REFERENCES companies(id) ON DELETE CASCADE,
    title       VARCHAR(500),
    event_type  VARCHAR(50),                    -- investment | ma | executive | restructure | finance | other
    filed_date  DATE,
    dart_url    TEXT,
    collected_at TIMESTAMP DEFAULT NOW(),
    raw_data    JSONB
);

CREATE INDEX IF NOT EXISTS idx_dart_company ON dart_filings(company_id);
CREATE INDEX IF NOT EXISTS idx_dart_event ON dart_filings(event_type);

-- ─── 신호 스코어 (시계열) ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS signal_scores (
    id          SERIAL PRIMARY KEY,
    company_id  INT REFERENCES companies(id) ON DELETE CASCADE,
    score       INT NOT NULL CHECK (score BETWEEN 0 AND 100),
    signals     JSONB,                          -- 감지된 신호 목록
    scored_at   TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_score_company ON signal_scores(company_id);
CREATE INDEX IF NOT EXISTS idx_score_date ON signal_scores(scored_at);

-- ─── 인텔리전스 리포트 (캐시) ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS intelligence_reports (
    id           SERIAL PRIMARY KEY,
    company_id   INT REFERENCES companies(id) ON DELETE CASCADE,
    score        INT,
    org_structure TEXT,
    key_insight  TEXT,
    approach_msg TEXT,
    entry_point  VARCHAR(200),
    timing_note  VARCHAR(300),
    full_report  JSONB,                         -- 전체 리포트 JSON
    generated_at TIMESTAMP DEFAULT NOW(),
    expires_at   TIMESTAMP GENERATED ALWAYS AS (generated_at + INTERVAL '24 hours') STORED
);

CREATE INDEX IF NOT EXISTS idx_report_company ON intelligence_reports(company_id);
CREATE INDEX IF NOT EXISTS idx_report_expires ON intelligence_reports(expires_at);

-- ─── 워치리스트 ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS watchlist (
    id          SERIAL PRIMARY KEY,
    company_id  INT REFERENCES companies(id) ON DELETE CASCADE,
    user_id     VARCHAR(100) NOT NULL,          -- Slack user ID
    channel_id  VARCHAR(100) NOT NULL,          -- 알림 보낼 Slack 채널
    added_at    TIMESTAMP DEFAULT NOW(),
    UNIQUE(company_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist(user_id);
