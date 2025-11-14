# Tasks MCP + ReAct (API mới, không làm hỏng logic cũ)

Tài liệu này liệt kê các đầu việc theo mức ưu tiên để triển khai MCP + ReAct **thông qua API mới**, giữ nguyên logic /chat hiện tại.

Tham chiếu chính: `docs/KeHoach_MCP_ReAct.md` (kiến trúc, agent, API cấu hình).

---

## P0 – Nền tảng & API cấu hình (bắt buộc trước)

- P0.1 **Thiết kế schema cấu hình MCP**  
  - Bảng `mcp_servers` (MCPServer).  
  - Bảng `agent_bindings` (AgentBinding).  
  - Trường `config_version` theo tenant để hỗ trợ cache/reload.

- P0.2 **Implement API cấu hình MCP theo Agent (không đụng /chat cũ)**  
  Dựa theo mục `4.3) API cấu hình MCP theo Agent` trong `KeHoach_MCP_ReAct.md`:  
  - REST cho MCP servers: tạo/list/chi tiết/update/delete + probe health/tools.  
  - REST cho Agent ↔ MCP bindings theo `{tenant_id, agent_type}`.  
  - REST đọc effective config + endpoint reload cache.

- P0.3 **MCP Client Manager + Cache 3 lớp (per-tenant)**  
  - Triển khai module quản lý kết nối MCP (MultiServer client) + cache: connection, tool list, agent.  
  - Chưa gắn vào /chat, chỉ dùng cho API test/internal.

---

## P1 – Orchestrator + Agent mới (song song với logic cũ)

- P1.1 **Orchestrator ReAct mới (không sửa create_agent_executor/invoke_agent_with_memory)**  
  - Tạo module mới (vd. `service/agents/mcp_orchestrator.py`).  
  - Nhận vào: tenant_id, user_input, history, access, effective config.  
  - Thực hiện vòng ReAct: Plan → chọn agent → gọi agent → Observe → Decide → Final, có giới hạn bước/timeout.
  - phần này hãy sử dụng thư viện `langchain` để thực hiện vòng lặp ReAct.
  - sử dụng langraph để tạo edge tới các agent

- P1.2 **Triển khai các Agent mới ở dạng module/class riêng**  
  Không sửa tools cũ, chỉ tạo lớp/ham mới gọi MCP:  
  - VisionAgent → `vision.identify_product`.  
  - ProductAgent → `retrieval.search`/`vector_search`/`graphrag` (index=products).  
  - ServiceAgent → `retrieval.search` (services).  
  - AccessoryAgent → `retrieval.search` (accessories, hỗ trợ `cum_dac_trung`).  
  - FAQAgent → `retrieval.search` (faq).  
  - KnowledgeAgent → `retrieval.graphrag`.  
  - StoreInfoAgent, CustomerInfoAgent, OrderAgent, EscalationAgent, ClosingAgent: giai đoạn đầu có thể wrap lại logic cũ thành adapter, nhưng ở file/module mới.
    -tất cả các agent này bạn cần tìm lại trong code base để thực hiện đúng logic của nó
    khi thực hiện tạo model LLM cho các agent bạn cần để động cho khách hàng lựa chọn model lưu model vào database thêm trường model nếu chưa có. 1 model sử dụng cho tất cả các agent
    
- P1.3 **Chuẩn hóa interface Agent**  
  - Mỗi agent nhận context chuẩn: `{tenant_id, user_input, history, bindings, defaults}`.  
  - Trả về `{answer, observations, used_tools}` để orchestrator ghi log.

---

## P2 – API chat mới dùng MCP + ReAct (giữ nguyên /chat hiện tại)

- P2.1 **Tạo endpoint chat mới (ví dụ `/chat-mcp/{threadId}`)**  
  - File router mới (vd. `api/chat_routes_mcp.py`).  
  - Luồng: validate input tương tự /chat → dùng orchestrator mới + MCP client manager.  
  - Không đụng code trong `/chat/{threadId}` hiện tại.

- P2.2 **Feature flag & cấu hình routing**  
  - Cho phép bật tắt sử dụng `/chat-mcp` theo tenant hoặc theo environment.  
  - Có thể triển khai frontend gọi endpoint mới cho nhóm thử nghiệm.

- P2.3 **Log/metrics cho chat mới**  
  - Ghi lại: agent_type, tool_name, latency, error_code, tokens.  
  - So sánh latency và chất lượng giữa `/chat` cũ và `/chat-mcp` mới.

---

## P3 – UI quản trị & migration dần sang MCP

- P3.1 **Trang quản trị MCP Servers & Agent Bindings**  
  - UI để thêm/sửa/xóa MCP server, test probe, xem health.  
  - UI để gán MCP cho từng agent per-tenant (dùng API P0.2).

- P3.2 **Công cụ debug & quan sát**  
  - Endpoint/Trang xem effective config của một tenant.  
  - Log viewer đơn giản cho các bước ReAct (khi debug).

- P3.3 **Chiến lược migration**  
  - Bắt đầu với một số tenant chọn lọc dùng `/chat-mcp`.  
  - Khi ổn định, cân nhắc:  
    - Hoặc đổi frontend trỏ `/chat` → `/chat-mcp`.  
    - Hoặc dần refactor logic cũ để dùng chung orchestrator (sau khi đã đủ tự tin).

---

## P4 – Dọn dẹp & hợp nhất (chỉ thực hiện khi đã ổn định)

- P4.1 **Đánh giá lại agent/tool legacy**  
  - Xác định tool/agent nào không dùng nữa sau MCP.  
  - Lên kế hoạch xoá dần hoặc giữ ở chế độ legacy.

- P4.2 **Hợp nhất logic chung**  
  - Nếu cần, refactor dần để cả chat cũ và mới dùng chung một số module (vd. format lịch sử, truy vấn DB).  
  - Chỉ làm khi đảm bảo không ảnh hưởng tenant đang chạy.
