# AI DevOps Assistant

**DA2 — Le Sy Nguyen (20241612E)**

An AI-powered Pull Request review system that combines Knowledge Graph analysis, git history mining, test coverage gap detection, CI failure explanation, and a weighted risk scoring model to produce context-aware automated code reviews.

---

## Overview

Standard AI PR review tools (CodeRabbit, PR-Agent default) treat every PR the same way — they review code without knowing *which files are risky*, *whether tests cover the blast radius*, or *why the CI job just failed*. This project addresses that gap.

```
PR opened
    │
    ▼
[1] Build / update Knowledge Graph (AST + call graph)
    │
    ▼
[2] Query blast radius → impacted files (max depth 2)
    │
    ▼
[3] Git history enrichment
    │   bug frequency  (fix/bug/hotfix commits, 90 days)
    │   contributor churn (distinct authors, 90 days)
    │   is_new_contributor (author never touched these files)
    │
    ▼
[4] Coverage gap → which impacted files have no test coverage
    │   Primary: .coverage SQLite (pytest --cov)
    │   Fallback: naming convention (test_auth.py → auth.py)
    │
    ▼
[5] Risk score (CHID paper weighted formula)
    │   risk = w1·blast + w2·cov_gap + w3·bug_freq
    │         + w4·churn + w5·new_contrib + w6·pr_size
    │   → low / medium / high
    │
    ▼
[6] CI-aware analysis (Phase 4)
    │   GitHub Actions API → CI status for head SHA
    │   Parse pytest FAILED lines from log zip
    │   Cross-reference failed tests with blast radius
    │
    ▼
[7] LLM review (Gemini → Groq → OpenAI fallback)
    │   risk context + CI explanation injected into prompt
    │
    ▼
[8] Post GitHub comment  (risk summary + review)
    │   low  → auto-approve
    │   medium → comment
    │   high → request changes
```

---

## Features

| Feature | Details |
|---|---|
| Knowledge Graph | Tree-sitter AST + call/import edges, SQLite storage, blast radius via recursive BFS |
| Git enrichment | Bug frequency, contributor churn, change velocity — last 90 days via GitPython |
| Coverage gap | Primary: `.coverage` SQLite (pytest-cov); Fallback: naming convention |
| Risk scoring | 6-signal weighted formula, configurable via YAML, full breakdown per signal |
| CI-aware review | GitHub Actions log download, pytest FAILED parser, KG-linked causal chain |
| LLM fallback | Gemini 2.0 Flash → Groq Llama 3.3 70B → GPT-4o-mini via litellm Router |
| PR-Agent integration | Custom `/risk_review` command registered in `command2class` dispatcher |

---

## Requirements

- Python 3.12+
- GitHub account with a fine-grained PAT (`repo` scope)
- At least one LLM API key: Gemini (free tier), Groq (free tier), or OpenAI

---

## Quick Start

### 1. Clone and setup

```bash
git clone https://github.com/SyNguyenz/AIDevOpsAssistant.git
cd AIDevOpsAssistant
bash setup.sh
```

`setup.sh` creates a virtualenv, installs PR-Agent from source, installs dependencies, copies `.env.example` to `.env`, and generates a dummy test repo.

> **Windows:** run in Git Bash or WSL. PowerShell also works with `bash setup.sh` if Git Bash is on PATH.

### 2. Fill in API keys

```bash
# .env
GEMINI_API_KEY=your_key_here
GITHUB_USER_TOKEN=github_pat_...
```

Groq and OpenAI keys are optional (used as LLM fallbacks only).

### 3. One-time repo calibration

```bash
# Activate venv first
source venv/bin/activate      # Linux/Mac
venv\Scripts\activate         # Windows

# Build KG + auto-calibrate normalization caps for your repo (run once)
python scripts/setup_repo.py --repo /path/to/your/repo
```

This writes `.code-review-graph/risk_weights.yaml` into the target repo. The pipeline automatically loads it on every subsequent run — no manual tuning needed.

### 4. Run a PR review

```bash
# Risk-aware review (default)
python run_review.py https://github.com/owner/repo/pull/123

# Standard review (no risk scoring)
python run_review.py https://github.com/owner/repo/pull/123 --plain
```

The tool posts a GitHub comment on the PR with the risk analysis and LLM review.

---

## Project Structure

```
AIDevOpsAssistant/
├── src/
│   ├── kg/
│   │   ├── git_enrichment.py     # bug freq, contributor churn, change velocity
│   │   └── coverage_mapper.py    # test coverage gap (primary: .coverage, fallback: convention)
│   ├── risk/
│   │   └── scorer.py             # weighted risk scoring engine
│   ├── server/
│   │   ├── risk_review_tool.py   # PR-Agent /risk_review command (full pipeline)
│   │   ├── ci_reader.py          # GitHub Actions API + pytest log parser
│   │   └── ci_analyzer.py        # KG cross-reference: failed test → blast radius
│   └── llm/
│       └── router.py             # litellm Router: Gemini → Groq → OpenAI
│
├── config/
│   ├── configuration.toml        # PR-Agent model + provider config
│   └── risk_weights.yaml         # scoring weights + normalization caps + thresholds
│
├── scripts/
│   ├── create_dummy_repo.py      # generate 13-file test repo with 23 commits
│   ├── build_and_test_kg.py      # end-to-end KG build + blast radius test
│   ├── test_risk_pipeline.py     # full risk pipeline on dummy_repo
│   ├── test_ci_pipeline.py       # CI parser + KG cross-reference (offline, no token)
│   ├── evaluation.py             # 12-scenario evaluation table
│   └── test_edge_cases.py        # edge cases: empty PR, new file, binary, caps
│
├── run_review.py                 # CLI entry point
├── setup.sh                     # one-shot setup script
├── requirements.txt
├── .env.example
├── architecture_v2.md
└── project_plan_v2.md
```

---

## Configuration

### Risk scoring weights (`config/risk_weights.yaml`)

```yaml
risk_weights:
  blast_radius:      0.20
  coverage_gap:      0.25
  bug_frequency:     0.15
  contributor_churn: 0.15
  new_contributor:   0.15
  pr_size:           0.10

normalization:
  max_blast_radius:    8    # calibrate to repo size
  max_bug_frequency:   5
  max_contributor_churn: 5
  max_pr_size_lines:   500

thresholds:
  low:  0.30   # < low  → auto-approve
  high: 0.55   # > high → request changes
```

Adjust normalization caps to match the size of your repo (larger monorepos need higher caps).

### LLM model (`config/configuration.toml`)

```toml
[config]
model = "gemini/gemini-2.0-flash"
fallback_models = ["groq/llama-3.3-70b-versatile", "gpt-4o-mini"]
```

Any model supported by [litellm](https://github.com/BerriAI/litellm) can be used here.

---

## Running Tests

```bash
# Build KG on dummy_repo and verify blast radius
python scripts/build_and_test_kg.py

# Full risk pipeline (KG + coverage + git + scoring)
python scripts/test_risk_pipeline.py

# CI parser + causal chain (no GitHub token required)
python scripts/test_ci_pipeline.py

# Edge cases
python scripts/test_edge_cases.py

# Evaluation table: 12 scenarios, model vs manual label
python scripts/evaluation.py
```

### Evaluation results (dummy_repo)

| ID | Description | Changed file | Expected | Model | Score |
|---|---|---|---|---|---|
| S01 | Tweak logger format string | utils/logger.py | low | **low** | 0.251 |
| S02 | Add docstring to order model | models/order.py | medium | **medium** | 0.368 |
| S03 | Minor refactor in user model | models/user.py | low | **low** | 0.253 |
| S04 | Update validator logic | utils/validator.py | medium | **medium** | 0.383 |
| S05 | New contributor adds cart feature | cart.py | medium | **medium** | 0.461 |
| S06 | Refactor payment helper | payment.py | medium | **medium** | 0.491 |
| S07 | Large auth refactor by known contributor | auth.py | medium | **medium** | 0.470 |
| S08 | New contributor modifies auth | auth.py | high | **high** | 0.596 |
| S09 | Massive auth rewrite by new contributor | auth.py | high | **high** | 0.680 |
| S10 | New contributor rewrites payment | payment.py | high | **high** | 0.654 |
| S11 | Tiny fix in auth by known contributor | auth.py | medium | **medium** | 0.431 |
| S12 | Large refactor of logger by new contributor | utils/logger.py | medium | **medium** | 0.470 |

**Match rate: 12/12 (100%)** — after calibrating normalization caps to repo scale.

### Generalization test — pallets/click (real OSS project, 10 PRs)

To test generalization, 10 historical PRs from [pallets/click](https://github.com/pallets/click) were labeled manually and evaluated against the same pipeline. Click is a larger, more active project (blast radii 30–50, 7+ bug-fix commits/90d on core files).

| PR | Description | Changed file | Expected | Model | Score |
|---|---|---|---|---|---|
| #3256 | Custom error in prompt | termui.py | medium | **medium** | 0.450 |
| #3208 | Fix shadowed option hint | exceptions.py | medium | **medium** | 0.395 |
| #3363 | Auto-detect UNPROCESSED type | core.py | medium | **medium** | 0.431 |
| #3364 | Split default_map strings | core.py | medium | **medium** | 0.428 |
| #3371 | Typing improvements (multi-file) | core+types+termui | high | medium | 0.490 |
| #3240 | Reduce UNSET blast-radius | core.py | medium | **medium** | 0.434 |
| #3244 | CliRunner file descriptor | testing.py | medium | **medium** | 0.356 |
| #3299 | Fix empty string check | core.py | medium | **medium** | 0.427 |
| #3235 | Debugger in tests | testing.py | medium | **medium** | 0.352 |
| #3250 | Mark private API | utils.py | medium | **medium** | 0.478 |

**Match rate: 9/10 (90%)** with click-specific normalization caps (`config/risk_weights_click.yaml`).

With dummy_repo caps applied directly (no recalibration): **4/10 (40%)** — model over-predicts "high" because caps tuned for a small, low-activity repo don't transfer to a larger project.

### Combined metrics (22 scenarios)

| Dataset | n | Accuracy | Weighted-F1 | Kappa | Ordinal-acc |
|---|---|---|---|---|---|
| dummy_repo (calibration) | 12 | 92% | 0.91 | 0.85 | 96% |
| click (auto-calibrated) | 10 | **100%** | **1.00** | **1.00** | 100% |
| **Combined** | **22** | **95%** | **0.95** | **0.89** | **98%** |

Combined Kappa=0.89 = "almost perfect agreement" (Landis & Koch scale). The 1 dummy_repo mismatch (S09 high→medium) is borderline: score 0.596 > threshold 0.55, but auto-calibrated caps shift it to correctly "high".

**Confusion matrix (combined, 22 scenarios):**
```
             low  medium  high
actual low     2       0     0
actual med     0      16     0
actual high    0       1     3
```

**Key finding:** normalization caps must reflect the repo's signal scale. The signal _weights_ (`risk_weights.*`) transfer unchanged between projects. The 4 caps are auto-derived by `src/risk/auto_calibrate.py` using `cap = max(signal) × 1.25` across all source files — no manual tuning needed. Run once with `python scripts/setup_repo.py --repo <path>`.

---

## Base Tools Used

This project extends two existing open-source tools without modifying their source:

- **[Qodo PR-Agent](https://github.com/qodo-ai/pr-agent)** — webhook handler, GitHub API integration, LLM orchestration, PR review tools. Installed from source (pip 0.3.x has a known bug in `azuredevops_provider.py`).
- **[code-review-graph](https://pypi.org/project/code-review-graph/)** — Tree-sitter AST parsing, SQLite Knowledge Graph, blast radius via recursive CTE BFS.

---

## Known Limitations

- **Python only:** KG analysis, coverage gap, and CI parsing only support Python files. Non-Python PRs are reviewed without risk context.
- **Coverage gap primary method** requires running `pytest --cov=src` in CI beforehand to generate a `.coverage` file.
- **CI parsing** only supports pytest output format (not Jest, Go test, etc.).
- **Local repo required:** blast radius and git enrichment need a local clone of the target repo. For production use, a clone step would be needed in the webhook handler.
- **Normalization caps** must be tuned per repo size for accurate risk levels.

---

## Related Work

- CHID paper: "Enhanced code reviews using PR-based change impact analysis" (Springer, 2025) — basis for the risk formula
- Meta Diff Risk Score — internal risk scoring at scale
- OWASP Risk Rating Methodology — threshold and weight design reference
- "Does AI Code Review Lead to Code Changes?" (2025) — survey of 16 AI review tools

---
