# AI DevOps Assistant — Kế hoạch 8 tuần

## Phase 1 — Learn by doing (2 tuần)

### Week 1: GitHub API + project setup

- Setup Python project (FastAPI, Poetry/pip)
- GitHub App registration + webhook endpoint
- Dùng PyGithub: list PRs, read diff, post comment
- Test: mở PR → webhook trigger → bot comment "Hello"

> ✅ Milestone: Bot nhận webhook và comment được lên PR

### Week 2: LangGraph + LLM router

- Học LangGraph: graph, node, edge, state
- Build LLM router: Gemini → Groq → OpenAI fallback
- Tích hợp: nhận diff → gửi LLM → nhận review text
- Test: PR thật → bot review bằng LLM → comment lên GitHub

> ✅ Milestone: End-to-end basic: PR → LLM review → GitHub comment

---

## Phase 2 — Core feature / mũi nhọn (3 tuần)

### Week 3: Diff analyzer + AST parser

- Dùng tree-sitter parse Python AST từ changed files
- Extract: functions, classes, imports bị thay đổi
- Build dependency map: file A import gì, ai import file A

> ✅ Milestone: Từ 1 PR diff → ra danh sách affected modules

### Week 4: Impact analyzer + risk scoring

- Cross-reference dependency map với PR diff
- Tính risk score: số module bị ảnh hưởng, độ sâu dependency
- Kết hợp git log: file hay bị bug → tăng risk
- Output: structured context cho LLM prompt

> ✅ Milestone: Risk score hoạt động: low / medium / high

### Week 5: History analyzer + conflict detection

- Scan pending PRs: có overlap file không
- Git blame: ai sửa file này gần nhất, tần suất lỗi
- Gom tất cả context → Context Aggregator → LLM prompt

> ✅ Milestone: Full context pipeline hoàn chỉnh

---

## Phase 3 — Actions + automation (1 tuần)

### Week 6: Review engine + auto actions

- LLM output → structured review (inline comments + summary)
- Auto merge logic: risk=low + CI pass → merge
- Request changes logic: risk=high → block + tag reviewer
- SQLite: lưu review history, cache LLM response

> ✅ Milestone: Tự động merge PR low-risk, block PR high-risk

---

## Phase 4 — Test + polish (1 tuần)

### Week 7: Testing + edge cases

- Test với repo thật (tạo dummy repo nhiều module)
- Edge cases: PR rỗng, file binary, repo không có tests
- Prompt tuning: chỉnh LLM prompt cho review chất lượng hơn
- Fix bugs, optimize tốc độ response

> ✅ Milestone: Hệ thống stable, xử lý được edge cases

---

## Phase 5 — Deliver (1 tuần)

### Week 8: Demo + báo cáo + slide

- Record demo video: full flow PR → review → merge
- Viết báo cáo: kiến trúc, công nghệ, kết quả, so sánh
- Làm slide thuyết trình
- README + Docker setup cho cô chạy thử

> ✅ Milestone: Sẵn sàng nộp và thuyết trình

---

## Lưu ý quan trọng

- **Rủi ro lớn nhất:** Week 3-4 (AST parsing + dependency graph). Giới hạn scope: chỉ support Python trước.
- **Tháng đã qua (16/3 – 14/4):** Cần chuẩn bị tài liệu research so sánh LangGraph vs CrewAI để justify lựa chọn framework.
- **Tại sao LangGraph thay vì CrewAI:** LangGraph linh hoạt hơn cho custom state machine, phù hợp với luồng review PR. CrewAI thiên về multi-agent conversation, không cần thiết cho use case này.