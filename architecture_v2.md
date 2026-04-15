# AI DevOps Assistant — System Architecture v2

## Overview

AI DevOps Assistant là một hệ thống tự động review Pull Request trên GitHub, sử dụng Knowledge Graph (KG) để hiểu codebase context và tính risk score cho mỗi PR. Hệ thống kết hợp static analysis (AST parsing), git history mining, test coverage mapping, và LLM reasoning để đưa ra review có context-awareness — thứ mà các tool hiện tại chưa làm tốt.

## Contributions

1. **Core:** Knowledge Graph enriched với git history (bug frequency, contributor churn, change velocity) + test coverage mapping cho blast radius
2. **Core:** Context-aware risk scoring — weighted, explainable, configurable (dựa trên CHID paper, Springer 2025)
3. **Stretch:** CI-aware review — agent đọc CI result, kết hợp KG giải thích tại sao fail

## Base tools (không tự build)

- **Qodo PR-Agent** — webhook handler, GitHub API, LLM integration, PR review tools
- **code-review-graph** — Tree-sitter AST parsing, blast radius, SQLite graph storage

## Tech stack

- Python
- Qodo PR-Agent (orchestrator)
- code-review-graph (KG engine)
- Gemini API (primary LLM) → Groq (fallback 1) → OpenAI (fallback 2)
- SQLite (graph + cache)
- GitHub REST API / PyGithub
- GitPython (git history extraction)

---

## Architecture diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     GitHub Webhook                          │
│                  PR opened / updated                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Qodo PR-Agent Orchestrator                     │
│              Extended with custom tools                     │
└──────────┬──────────────────────────────────┬───────────────┘
           │                                  │
           ▼                                  ▼
┌─────────────────────────┐    ┌──────────────────────────────┐
│  Knowledge Graph Engine  │    │       LLM + CI Layer         │
│  ┌────────────────────┐ │    │  ┌─────────────────────────┐ │
│  │ code-review-graph  │ │    │  │ LLM Router              │ │
│  │ (base)             │ │    │  │ Gemini → Groq → OpenAI  │ │
│  │ Tree-sitter AST    │ │    │  └─────────────────────────┘ │
│  │ + blast radius     │ │    │  ┌─────────────────────────┐ │
│  └────────────────────┘ │    │  │ Context-aware prompt    │ │
│  ┌────────────────────┐ │    │  │ KG context → structured │ │
│  │ Git history        │ │───▶│  │ prompt for LLM          │ │
│  │ enrichment         │ │    │  └─────────────────────────┘ │
│  │ Bug freq,          │ │    │  ┌─────────────────────────┐ │
│  │ contributor, vel.  │ │    │  │ CI result reader        │ │
│  └────────────────────┘ │    │  │ Parse GitHub Actions    │ │
│  ┌────────────────────┐ │    │  │ log (STRETCH)           │ │
│  │ Test coverage      │ │    │  └─────────────────────────┘ │
│  │ mapper             │ │    │  ┌─────────────────────────┐ │
│  │ Blast radius ×     │ │    │  │ CI-aware explanation    │ │
│  │ test coverage      │ │    │  │ KG + CI fail → explain  │ │
│  └────────────────────┘ │    │  │ why (STRETCH)           │ │
│  ┌────────────────────┐ │    │  └─────────────────────────┘ │
│  │ Pending PR         │ │    │                              │
│  │ conflict scan      │ │    │                              │
│  │ Overlap detection  │ │    │                              │
│  └────────────────────┘ │    │                              │
└─────────────┬───────────┘    └──────────────┬───────────────┘
              │                               │
              └───────────────┬───────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│             Context-Aware Risk Scoring (CORE)               │
│                                                             │
│  risk = w1 × blast_radius + w2 × coverage_gap              │
│        + w3 × bug_freq + w4 × contributor_churn             │
│        + w5 × is_new_contributor + w6 × pr_size             │
│                                                             │
│  Weighted, explainable, configurable                        │
│  Based on: CHID paper (Springer 2025) + OWASP methodology  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Review Engine                            │
│              LLM review + risk explanation                  │
└──────┬──────────────────┬───────────────────┬───────────────┘
       │                  │                   │
       ▼                  ▼                   ▼
┌──────────────┐  ┌───────────────┐  ┌────────────────┐
│  Auto merge  │  │ Review comment│  │ Block + explain│
│  Risk = low  │  │ Risk = medium │  │ Risk = high    │
│  CI pass +   │  │ Inline +      │  │ Coverage gap + │
│  tests cover │  │ risk summary  │  │ bug history    │
└──────────────┘  └───────────────┘  └────────────────┘
                           │
                           ▼
┌──────────────┐  ┌───────────────┐  ┌────────────────┐
│   SQLite     │  │  GitHub API   │  │   LLM APIs     │
│  KG + cache  │  │ Repo, PR, CI  │  │ 3 providers    │
└──────────────┘  └───────────────┘  └────────────────┘
```

---

## Data flow chi tiết

### 1. Trigger
- GitHub webhook gửi event khi PR opened/updated
- PR-Agent nhận event, extract PR metadata (diff, files changed, author)

### 2. Knowledge Graph query
- code-review-graph update incremental (chỉ parse file thay đổi)
- Blast radius: trace callers, dependents, tests bị ảnh hưởng (2-hop BFS)
- Git history enrichment: query git log/blame cho mỗi file trong blast radius
  - Bug frequency: đếm commits chứa "fix", "bug", "hotfix" trong 90 ngày
  - Contributor churn: số distinct authors trong 90 ngày
  - Change velocity: số commits trong 90 ngày
  - Last modifier: ai sửa gần nhất
- Test coverage mapper: check file trong blast radius có test tương ứng không
- Pending PR scan: check PR khác có overlap file không

### 3. Risk scoring
- Normalize mỗi signal về 0-1
- Tính weighted sum (weights configurable qua .yaml)
- Threshold: low (< 0.3), medium (0.3-0.7), high (> 0.7)
- Output: score + breakdown explanation

### 4. LLM review
- Build structured prompt: diff + KG context + risk breakdown
- Gửi qua LLM router: Gemini → Groq → OpenAI (fallback chain)
- LLM trả về: inline review comments + risk-aware summary

### 5. Action
- Low risk + CI pass + full test coverage → auto approve/merge
- Medium risk → post review comment + risk summary, chờ human
- High risk → request changes + giải thích chi tiết (coverage gap, bug history)

### 6. Stretch: CI-aware review
- Khi CI fail: parse GitHub Actions log, extract failed test
- Cross-reference với KG: test fail ở file X → file X trong blast radius của PR
- LLM giải thích connection: "CI fail vì test_payment.py assert error, likely caused by thay đổi auth/login.py vì payment module import auth"

---

## Risk scoring model

### Cơ sở lý thuyết
- **CHID paper** (Springer 2025): weighted sum từ code churn, bug frequency, co-changed files, author merge rate, PR size, impact size (PageRank)
- **OWASP Risk Rating**: risk = likelihood × impact, customizable weights
- **Meta DRS**: LLM-based risk prediction (reference only, quá nặng cho scope đồ án)

### Formula

```
risk_score = w1 × norm(blast_radius_size)
           + w2 × norm(coverage_gap_ratio)
           + w3 × norm(bug_frequency)
           + w4 × norm(contributor_churn)
           + w5 × is_new_contributor
           + w6 × norm(pr_size_lines)
```

### Signal definitions

| Signal | Cách tính | Normalize |
|---|---|---|
| blast_radius_size | Số file bị ảnh hưởng (2-hop BFS trên KG) | / max_files_in_repo, cap tại 1.0 |
| coverage_gap_ratio | Số file trong blast radius KHÔNG có test / tổng blast radius | Đã là ratio 0-1 |
| bug_frequency | Số commits "fix/bug/hotfix" trên changed files trong 90 ngày | / max_bug_freq across repo |
| contributor_churn | Số distinct authors trên changed files trong 90 ngày | / max_churn across repo |
| is_new_contributor | PR author chưa từng commit vào file này = 1, đã từng = 0 | Binary |
| pr_size_lines | Tổng số lines added + deleted trong PR diff | / max_pr_size (e.g. 1000 lines), cap tại 1.0 |

### Default weights (configurable)

```yaml
risk_weights:
  blast_radius: 0.20
  coverage_gap: 0.25
  bug_frequency: 0.15
  contributor_churn: 0.15
  new_contributor: 0.15
  pr_size: 0.10
```

### Explainability

Mỗi risk score đi kèm breakdown:

```
Risk: HIGH (0.82)
Breakdown:
  - Blast radius: 12 files affected (0.24/0.25)
  - Coverage gap: 4/12 files have no tests (0.30/0.30)
  - Bug frequency: auth.py had 8 bug fixes in 90 days (0.12/0.15)
  - Contributor churn: 5 different authors (0.08/0.15)
  - New contributor: PR author never touched auth.py (0.15/0.15)
Recommendation: Add tests for payment/checkout.py and utils/validator.py before merge
```

---

## Limitations

- **Python only**: prototype chỉ support Python repos, extensible to other languages
- **Test mapping**: primary dùng `coverage.py` output (`.coverage` file) nếu CI chạy pytest với coverage — chính xác hơn; fallback về convention-based (test_x.py → x.py) nếu không có file coverage
- **Risk weights chưa optimize**: default weights dựa trên CHID paper + manual tuning, chưa có ML-based optimization
- **Blast radius over-predict**: code-review-graph conservative — flag nhiều hơn cần thiết (perfect recall, lower precision)
- **CI-aware chỉ cho pytest**: stretch goal chỉ parse pytest output format

---

## So sánh với existing tools

| Feature | Qodo PR-Agent | code-review-graph | CodeRabbit | **Ours** |
|---|---|---|---|---|
| LLM review | ✅ | ❌ | ✅ | ✅ |
| Blast radius (KG) | ❌ | ✅ | ❌ | ✅ |
| Git history in risk | ❌ | ❌ | ❌ | ✅ |
| Test coverage gap | ❌ | Partial (detect test files) | ❌ | ✅ |
| Risk score | ❌ | ❌ | ❌ | ✅ |
| Explainable risk | ❌ | ❌ | ❌ | ✅ |
| Auto merge/block | ❌ | ❌ | ❌ | ✅ |
| CI-aware review | ❌ | ❌ | ❌ | Stretch |
