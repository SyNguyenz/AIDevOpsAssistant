# AIDevOpsAssistant

- **Core feature (mũi nhọn):** Context-aware PR review — phân tích impact, dependency, risk score
- **3 LLM providers:** Gemini (primary), Groq (fallback 1), OpenAI (fallback 2)
- **Platform:** GitHub, Python
- **1 người, 2 tháng**Đây là system architecture. T giải thích luồng chính:

**Luồng hoạt động:**

1. **GitHub Webhook** — khi có PR mở/cập nhật, GitHub gửi event tới server
2. **Agent Orchestrator** — dùng LangGraph để điều phối flow, quản lý state. Đây là "não" của hệ thống
3. **3 module phân tích song song:**
   - **Diff Analyzer**: parse diff, xác định file nào thay đổi, thay đổi bao nhiêu dòng
   - **Impact Analyzer** *(mũi nhọn)*: build dependency graph từ codebase, phân tích PR này ảnh hưởng module nào khác, có break import/interface không
   - **History Analyzer**: check git log xem file này hay bị bug không, có PR pending nào conflict không
4. **Context Aggregator** — gom tất cả context lại, build prompt có cấu trúc cho LLM
5. **LLM Router** — gọi Gemini trước, fail thì Groq, fail nữa thì OpenAI. Có cache để không gọi lại cùng 1 commit
6. **Review Engine** — LLM trả về review + risk score (low/medium/high)
7. **Actions** dựa trên risk:
   - Low risk + CI pass → auto merge
   - Medium → comment review, chờ human
   - High → request changes, flag cho human

**Tech stack dự kiến:**
- Python + FastAPI (nhận webhook)
- LangGraph (orchestrator)
- Tree-sitter hoặc AST parser (phân tích dependency — đây là phần mũi nhọn)
- SQLite (lưu review history, cache)
- GitHub REST API / PyGithub

**Điểm khác biệt so với thị trường:** phần Impact Analyzer dùng static analysis (parse AST) để hiểu dependency thật sự của codebase, không chỉ đọc diff text rồi nhờ LLM đoán. Đây là thứ CodeRabbit không làm sâu.