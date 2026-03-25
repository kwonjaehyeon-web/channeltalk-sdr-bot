# 채널톡 SDR 고객 분석 자동화

> **"기업명 하나로 SDR 리서치 끝"**
> 기업명을 입력하면 AI가 자동으로 ICP 분석 → 페인포인트 도출 → 채널톡 솔루션 매칭 → 의사결정자 추론까지 처리합니다.

<br>

## 왜 만들었나

B2B 콜/메일 전 기업 리서치에 필요한 시간을 단축하기 위해 만들었다.
홈페이지, 뉴스, 채용공고, 링크드인을 각각 열어보고 손으로 정리하는 과정을 자동화하고 싶었다.
특히 **채널톡** SDR 관점에서 "이 회사에 챗봇/CRM/팀채팅 중 뭐가 맞는지"를 바로 판단할 수 있는 도구가 필요했다.

<br>

## 아키텍처

```
[Notion: 채널톡 컨텍스트]   [Notion: 분석 가이드라인]
  기능·성공사례·포지셔닝       ICP 판단 기준·솔루션 매칭 규칙
  (코드 없이 수정 가능)        (코드 없이 수정 가능)
          │                          │
          └──────────┬───────────────┘
                     │
               [Serper API]
         Google 검색 5종 병렬 수집
         기업개요 / 규모·투자 / 뉴스 / 채용공고 / LinkedIn
                     │
                     ▼
            [OpenAI GPT-4o]
        컨텍스트 + 가이드라인 + 검색 데이터
        → ICP / Problem / Solution / 의사결정자
                     │
            ┌────────┴────────┐
            ▼                 ▼
      [Streamlit UI]     [Notion DB]
      분석 리포트 출력      영구 저장
```

**채널톡 컨텍스트 / 분석 가이드라인**: Notion 페이지에서 직접 관리. 코드 배포 없이 수정하면 다음 분석부터 즉시 반영 (1시간 캐시).

**데이터 수집**: Serper API로 구글 검색 5종 — 기업개요 / 규모·투자 / 뉴스 / 채용공고 / LinkedIn 프로필

**분석**: GPT-4o가 Notion 가이드라인 + 검색 결과를 읽고 ICP·Problem·Solution·의사결정자를 JSON으로 구조화

> **모델 선택 이유**: 추론 모델(o3 등)은 수학/코딩에 특화되어 비용이 3~4배 높음.
> 이 태스크는 텍스트 → 구조화 JSON 변환이 핵심이므로 GPT-4o가 속도·비용·품질 면에서 최적.

<br>

## 프롬프트 설계

LLM 분석의 핵심은 **"무엇을 보고, 어떻게 판단하라"는 규칙을 프롬프트에 명시하는 것**이다.

### 두 종류의 인풋 분리

```
## 채널톡 제품 컨텍스트         ← Notion 페이지 (기능·성공사례·포지셔닝)
## SDR 분석 가이드라인          ← Notion 페이지 (ICP·Problem·솔루션 매칭 판단 기준)
---
## 기업 개요                   ← Serper 검색 (기업소개 쿼리)
## 규모/투자                   ← Serper 검색 (투자·매출·임직원 쿼리)
## 최신 뉴스                   ← Serper 검색 (성장·확장 쿼리)
## 채용 공고                   ← Serper 검색 (CS·마케팅 채용 쿼리)
## LinkedIn 의사결정자 후보     ← Serper 검색 (site:linkedin.com/in 쿼리)
```

**핵심 설계 원칙**:
- **채널톡 지식을 GPT 사전학습에 의존하지 않음**: Notion 페이지로 분리해 영업팀이 직접 업데이트
- **판단 기준도 코드 밖으로**: 분석 가이드라인을 Notion으로 관리해 프롬프트 튜닝을 코드 없이 가능

### 1. ICP 판단 — 근거 없으면 (추정) 표기

```
규모/매출: 투자 유치, 임직원 수, 매출 정보 추출. 없으면 "(추정)" 표기
예시: "Series B 100억 투자유치" → 성장기 스타트업
```

LLM이 숫자를 날조하지 않도록 근거 부재 시 명시적으로 추정임을 표기하게 강제.

### 2. Problem — 채용공고를 문제 지표로 해석

```
CS/고객응대 채용 → 해당 팀 부담 증가로 해석
급성장/사용자 급증 뉴스 → CS 문의 폭증 가능성
구체적 근거 반드시 포함
```

채용공고를 단순 정보가 아닌 **회사 내부 문제의 간접 지표**로 읽는 SDR 논리를 명시화.

### 3. 솔루션 매칭 — Notion 컨텍스트 기반

Notion 컨텍스트에 성공사례가 있으면 해당 사례를 근거로 제안. 없으면 if-then 규칙으로 폴백.

### 4. 의사결정자 — LinkedIn 실제 인물 우선

```
링크드인 검색 결과에 실제 인물이 있으면 반드시 언급
없으면: 커머스 → CX팀장 / SaaS → CS 리드 / 소규모 → 대표이사
```

### 출력 — 구조화 강제

```json
{
  "icp_industry":          "산업군 (예: 커머스 - 패션/뷰티)",
  "icp_scale":             "규모/매출 추정",
  "icp_fit":               "High | Medium | Low",
  "icp_fit_reason":        "ICP 판단 근거 1~2문장",
  "problem":               "핵심 문제 상황 (구체적 근거 포함)",
  "problem_evidence":      "근거가 된 채용공고 또는 뉴스",
  "channeltalk_solution":  "채널톡으로 해결하는 방법 (구체적 기능명 포함)",
  "decision_maker":        "의사결정권자 추정 직함",
  "decision_maker_reason": "해당 직함으로 추론한 이유",
  "company_summary":       "기업 한 줄 요약"
}
```

`response_format: json_object` + 스키마 명시로 파싱 오류 없이 UI/Notion에 바로 전달.

<br>

## 분석 항목

| 항목 | 분석 소스 | LLM 판단 기준 |
|---|---|---|
| ICP: 산업 | 기업 개요 검색 | 커머스/SaaS/오프라인 서비스 등 분류 |
| ICP: 규모/매출 | 뉴스, 기업 정보 | "Series B 100억 투자유치" → 성장기 스타트업 |
| 회사의 문제 | 채용 공고(JD) | "CS 인력 대규모 채용" → 고객 문의 폭증 |
| 채널톡 솔루션 | 매칭 로직 | CS 폭주 → 서포트봇 / 마케팅팀 채용 → CRM |
| 의사결정자 | LinkedIn + 산업 추론 | 실제 인물 우선, 없으면 산업별 직함 추론 |

<br>

## 기술 스택

| 역할 | 기술 |
|---|---|
| UI / 배포 | Streamlit |
| 검색 | Serper API (Google Search) |
| LLM | OpenAI GPT-4o |
| 프롬프트 관리 | Notion API (컨텍스트 + 가이드라인) |
| 결과 저장 | Notion API (DB) |
| 언어 | Python 3.11+ |

<br>

## 실행 방법

### 1. 환경변수 설정

```bash
cp .env.example .env
```

```env
OPENAI_API_KEY=sk-...
SERPER_API_KEY=...
NOTION_TOKEN=ntn_...
NOTION_DATABASE_ID=...              # 분석 결과 저장 DB
NOTION_CONTEXT_PAGE_ID=...         # 채널톡 컨텍스트 페이지 ID
NOTION_GUIDELINES_PAGE_ID=...      # SDR 분석 가이드라인 페이지 ID (선택)
```

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```

### 3. 실행

```bash
streamlit run streamlit_app.py
```

### Streamlit Cloud 무료 배포

1. GitHub에 푸시
2. [share.streamlit.io](https://share.streamlit.io) → New app → 레포 선택
3. App Settings → Secrets에 `.streamlit/secrets.toml.example` 내용 입력

<br>

## Notion 구조

```
🤖 채널톡 SDR 자동화 (상위 페이지)
  ├── 📋 채널톡 SDR 분석 DB        ← 분석 결과 자동 저장
  ├── 📄 채널톡 SDR 컨텍스트       ← 기능·성공사례·포지셔닝 관리
  └── 📝 SDR 분석 가이드라인        ← ICP·Problem·솔루션 판단 기준 관리
```

**프롬프트를 Notion으로 관리하는 이유**: 코드 배포 없이 판단 기준 수정 가능. 영업 현장에서 새로운 패턴 발견 시 즉시 반영.

<br>

## 프로젝트 구조

```
sales-strategy/
├── streamlit_app.py            # Streamlit UI 진입점
├── app/
│   └── services/
│       ├── serper.py           # Serper API (구글 검색 5종 + LinkedIn)
│       ├── llm.py              # GPT-4o 분석 (컨텍스트 + 가이드라인 + SDR 프롬프트)
│       └── notion.py           # Notion DB 저장 + 컨텍스트/가이드라인 읽기 (1시간 캐시)
├── .streamlit/
│   └── secrets.toml.example   # Streamlit Cloud 배포용 환경변수 예시
└── requirements.txt
```

<br>

## 배운 점 / 한계

**잘 된 것**
- 채용공고에서 페인포인트를 추론하는 로직이 생각보다 정확하게 동작함
- GPT-4o가 산업별 의사결정자 구조를 잘 맞춤 (커머스 CX팀장, SaaS CS 리드 등)
- 프롬프트를 Notion으로 분리해 코드 없이 판단 기준 수정 가능

**한계 및 개선 방향**
- 비상장 소기업은 검색 결과가 적어 분석 품질 낮음
- Serper snippet만으로는 정보 깊이가 얕음 → 추후 실제 페이지 크롤링 고려
- LinkedIn 검색은 Google 인덱싱 기반이라 최신 정보가 아닐 수 있음
- 채널톡 컨텍스트 페이지 내용이 많을수록 매칭 품질 향상 → 성공사례 지속 추가 필요
