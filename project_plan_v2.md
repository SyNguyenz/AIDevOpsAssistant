# AI DevOps Assistant — Kế hoạch 12 tuần

**Sinh viên:** Le Sy Nguyen — 20241612E   
**Stack:** Python, Qodo PR-Agent (base), code-review-graph (KG base)  
**LLM:** Gemini (primary) → Groq (fallback 1) → OpenAI (fallback 2)

---

## Contributions

1. **Core:** Knowledge Graph enriched với git history (bug frequency, contributor churn, change velocity) + test coverage mapping cho blast radius
2. **Core:** Context-aware risk scoring — weighted, explainable, configurable (dựa trên CHID paper, Springer 2025)
3. **Stretch:** CI-aware review — agent đọc CI result, kết hợp KG giải thích tại sao fail

## Base tools (không tự build)

- **Qodo PR-Agent** — webhook handler, GitHub API, LLM integration, PR review tools
- **code-review-graph** — Tree-sitter AST parsing, blast radius, SQLite graph storage

---

## Phase 0 — Research (3 tuần, đã hoàn thành)

### Week 1: Tìm hiểu framework

- Nghiên cứu LangGraph: graph, node, edge, state machine, conditional routing
- Nghiên cứu CrewAI: multi-agent, role-based, task delegation
- So sánh: LangGraph linh hoạt hơn cho custom pipeline, CrewAI thiên về multi-agent conversation
- Kết luận: LangGraph phù hợp hơn cho use case PR review (cần deterministic flow + custom state)
- Tuy nhiên architecture v2 dùng PR-Agent làm orchestrator nên LangGraph là option mở rộng

> ✅ Milestone: Tài liệu so sánh LangGraph vs CrewAI

### Week 2: Survey resource sẵn có

- Survey repos: Qodo PR-Agent, CodeRabbit ai-pr-reviewer, Vercel OpenReview, multi-repo-impact-analyzer, code-review-graph
- Survey papers:
  - "Does AI Code Review Lead to Code Changes?" (2025) — 16 tool, chỉ 0.9-19.2% comment được áp dụng
  - "Enhanced code reviews using PR-based change impact analysis" (CHID, Springer 2025) — risk scoring model
  - "Code Graph Model" (NeurIPS 2025) — code graph + LLM attention
  - "HCGS" (2025) — hierarchical code graph summarization
  - "AI-Assisted Impact Analysis" (2024) — survey graph-based impact analysis
- Survey industry: Meta Diff Risk Score, OWASP Risk Rating, Snyk reachability analysis
- Xác định gap: chưa tool nào kết hợp KG + git history + test coverage gap → risk scoring → auto action

> ✅ Milestone: Related work survey + gap analysis

### Week 3: Design architecture + lên plan

- Thiết kế system architecture v2
- Xác định 2 core contributions + 1 stretch goal
- Chọn base tools: Qodo PR-Agent + code-review-graph
- Thiết kế risk scoring model dựa trên CHID paper + OWASP
- Lập kế hoạch 12 tuần chi tiết

> ✅ Milestone: Architecture document + project plan

---

## Phase 1 — Setup + đọc code base tools (1.5 tuần)

### Week 4: Setup + đọc hiểu PR-Agent

- Clone Qodo PR-Agent, đọc kiến trúc: command dispatcher → tools → platform abstraction
- Chạy PR-Agent local với 1 test repo + GitHub PAT (fine-grained)
- Hiểu cách PR-Agent gọi LLM, post comment, handle webhook
- Setup LLM router: Gemini → Groq → OpenAI fallback
- **Backup plan:** nếu PR-Agent quá phức tạp, build lightweight webhook handler riêng (FastAPI + PyGithub, ~3-4 ngày)

> ✅ Milestone: PR-Agent chạy local, review được PR trên test repo

### Week 5 first half: Setup code-review-graph

- Install code-review-graph, build graph cho test repo
- Hiểu cấu trúc SQLite graph: nodes, edges, blast radius query
- Test: thay đổi 1 file → query blast radius → xác nhận đúng
- **Backup plan:** nếu code-review-graph có issue, tự implement simplified version (Tree-sitter + NetworkX, ~1 tuần)

> ✅ Milestone: Hiểu cả 2 codebase, sẵn sàng extend

---

## Phase 2 — Core contribution 1: KG enrichment (2.5 tuần)

### Week 5 second half + Week 6: Git history enrichment

- Extend graph schema: thêm node attributes cho git history
  - Bug frequency: đếm commits có keyword "fix", "bug", "hotfix" trong 90 ngày
  - Contributor churn: số người distinct sửa file trong 90 ngày
  - Change velocity: số commits trên file trong 90 ngày
  - Last modifier: ai sửa gần nhất, có phải author PR không
- Dùng GitPython hoặc subprocess gọi git log, git blame
- Lưu vào SQLite graph cùng với AST nodes
- Tạo dummy test repo (10-15 module, fake git history bằng script)

> ✅ Milestone: Query graph trả về blast radius + git history cho mỗi file

### Week 7: Test coverage mapper

- **Primary:** đọc `.coverage` file (SQLite format) nếu CI chạy `pytest --cov` — dùng `coverage.py` Python API để query file nào được cover và bởi test nào
- **Fallback:** nếu không có `.coverage` file, dùng convention-based mapping (test_auth.py → auth.py)
- Với mỗi file trong blast radius, check coverage → output danh sách file KHÔNG được cover → coverage gap
- **Limitation ghi rõ:** primary method yêu cầu repo đã chạy pytest-cov; fallback chỉ support Python naming convention

> ✅ Milestone: Blast radius + coverage gap report hoạt động

---

## Phase 3 — Core contribution 2: Risk scoring (1.5 tuần)

### Week 8: Risk scoring engine

- Implement scoring model dựa trên CHID paper:
  ```
  risk_score = w1 × norm(blast_radius_size)
             + w2 × norm(coverage_gap_ratio)
             + w3 × norm(bug_frequency)
             + w4 × norm(contributor_churn)
             + w5 × is_new_contributor
             + w6 × norm(pr_size_lines)
  ```
- `pr_size_lines` = tổng lines added + deleted trong PR diff (từ GitHub API hoặc git diff --stat), normalize / 1000 lines, cap tại 1.0
- Normalize mỗi signal về 0-1
- Default weights: blast_radius=0.20, coverage_gap=0.25, bug_freq=0.15, churn=0.15, new_contributor=0.15, pr_size=0.10
- Weights configurable qua file .yaml
- Threshold: low (< 0.3), medium (0.3-0.7), high (> 0.7)
- **Explainability:** mỗi score đi kèm breakdown tại sao cao/thấp

> ✅ Milestone: Risk score + explanation cho mỗi PR

### Week 9 first half: Tích hợp vào PR-Agent

- Tạo custom tool trong PR-Agent: /risk-review
- Flow: PR opened → build/update KG → query blast radius + git history + coverage → tính risk → gửi context + risk cho LLM → LLM review → post comment + risk summary
- Auto action: low → approve, medium → comment, high → request changes

> ✅ Milestone: End-to-end pipeline hoạt động

---

## Phase 4 — Stretch: CI-aware review (1 tuần, skip nếu hết thời gian)

### Week 9 second half + Week 10 first half: CI integration

- Đọc GitHub Actions API: lấy CI run status, log
- Khi CI fail: parse log tìm test nào fail (chỉ support pytest output format)
- Cross-reference với KG: test fail ở file X → file X thuộc blast radius → giải thích connection
- LLM tổng hợp: "CI fail vì test_payment.py assert error, likely caused by thay đổi auth/login.py vì payment module import auth"
- **Limitation:** chỉ parse pytest, không support Jest/Go test/etc.

> ✅ Milestone: Agent giải thích CI failure dựa trên KG context

---

## Phase 5 — Test + Polish + Deliver (2 tuần)

### Week 10 second half + Week 11: Testing + evaluation

- Test trên dummy repo: PR low risk, PR high risk, PR với coverage gap, PR conflict
- **Evaluation:** chạy 10-20 PR, manual label risk level, so sánh với model output
  - Tạo bảng: PR description | manual risk | model risk | match?
  - Không cần accuracy cao, chỉ cần show đã evaluate (tương tự CHID paper approach)
- Edge cases: repo rỗng, file binary, PR chỉ sửa README
- Prompt tuning: chỉnh LLM prompt cho review chất lượng
- Fix bugs, optimize tốc độ response

> ✅ Milestone: Hệ thống stable + evaluation table

### Week 12: Deliver

- Record demo video: full flow PR → KG query → risk score → review → action
- Viết báo cáo:
  - Related work: PR-Agent, code-review-graph, CodeRabbit, CHID paper, Meta DRS, OWASP
  - Contribution: KG enrichment + risk scoring + (CI-aware)
  - Architecture + implementation
  - Evaluation results + so sánh với existing tools
  - Limitations + future work
- Slide thuyết trình
- README + setup guide (Docker nếu kịp)

> ✅ Milestone: Sẵn sàng nộp

---

## Risk management

| Rủi ro | Xác suất | Impact | Mitigation |
|---|---|---|---|
| PR-Agent quá phức tạp để extend | Trung bình | Cao | Backup: build lightweight webhook handler (FastAPI + PyGithub) |
| code-review-graph có bug/API thay đổi | Thấp | Trung bình | Backup: simplified KG (Tree-sitter + NetworkX) |
| LLM rate limit khi demo | Thấp | Trung bình | 3 provider fallback + cache response |
| Risk scoring weights không hợp lý | Trung bình | Thấp | Configurable weights + manual tuning + evaluation table |
| Hết thời gian cho CI-aware | Cao | Thấp | Đã đánh dấu stretch, skip được |

---

## References

### Repos
- [Qodo PR-Agent](https://github.com/qodo-ai/pr-agent) — base PR review bot
- [code-review-graph](https://github.com/tirth8205/code-review-graph) — Tree-sitter KG + blast radius
- [multi-repo-impact-analyzer](https://github.com/messX/multi-repo-impact-analyzer) — LangGraph agent + risk scoring reference
- [Vercel OpenReview](https://github.com/vercel-labs/openreview) — skill-based review architecture

### Papers
- "Enhanced code reviews using pull request based change impact analysis" (CHID, Springer 2025) — **cơ sở chính cho risk scoring**
- "Does AI Code Review Lead to Code Changes?" (2025) — effectiveness analysis of 16 AI review tools
- "Code Graph Model" (NeurIPS 2025) — integrating code graph into LLM attention
- "HCGS: Hierarchical Code Graph Summarization" (2025) — multi-layer code graph
- "AI-Assisted Impact Analysis for Software Requirements Change" (2024) — survey
- "Knowledge Graph Based Repository-Level Code Generation" (ICSE 2025) — KG for code context

### Industry references
- [Meta Diff Risk Score](https://engineering.fb.com/2025/08/06/developer-tools/diff-risk-score-drs-ai-risk-aware-software-development-meta/) — LLM-based risk prediction at scale
- [OWASP Risk Rating Methodology](https://owasp.org/www-community/OWASP_Risk_Rating_Methodology) — likelihood × impact framework
