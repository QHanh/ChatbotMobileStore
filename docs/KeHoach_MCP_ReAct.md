# Kế hoạch chuyển đổi Tool sang MCP và áp dụng ReAct cho /chat

Tài liệu này mô tả kế hoạch đơn giản, dễ hiểu để:
- Chuyển các tool hiện có sang giao tiếp qua MCP (Model Context Protocol).
- Đổi logic trả lời trong `/chat/{threadId}` sang kiểu ReAct (Plan → Act → Observe) có giới hạn bước, timeout và fallback an toàn.

## 1) Mục tiêu
- Chuẩn hóa cách gọi tool: có JSON Schema input/output, mã lỗi thống nhất.
- Tách tool ra khỏi codebase, giao tiếp qua MCP server(s).
- Orchestrate bằng ReAct: mô hình lập kế hoạch, gọi tool cần thiết, đọc kết quả, rồi tổng hợp trả lời.
- Giữ an toàn triển khai: feature flag, shadow mode, rollback nhanh.

## 2) Tổng quan kiến trúc
- MCP Servers (có thể tách theo domain):
  - retrieval-mcp: tìm kiếm ES, vector, GraphRAG.
  - vision-mcp: nhận diện sản phẩm từ ảnh (url/base64).
  - integrations-mcp: Google Sheets và dịch vụ ngoài.
  - optional db-mcp: nếu muốn tách đọc/ghi state ra MCP.
- MCP Client trong backend: quản lý kết nối, timeout, retry, circuit breaker.
- ReAct Orchestrator: điều phối vòng lặp Plan → Act (gọi tool MCP) → Observe → Decide → Final.

## 3) Ánh xạ tool hiện có → MCP
- vision.identify_product
  - Input: image_urls[], image_base64?, customer_id.
  - Output: product_spec, candidates[], confidence, citations.
  - Thay thế: `_identify_product_from_image(...)` hiện tại.
- retrieval.search
  - Input: query, top_k, filters, index.
  - Output: hits[] {id, title, snippet, score, source, url}.
  - Thay thế: `service/retrieve/search_service.py` (BM25/ES).
- retrieval.vector_search / retrieval.graphrag
  - Input: question/query, top_k, mode.
  - Output: chunks/summary/entities/relations + citations.
  - Thay thế: `service/graphrag/graphrag_service.py` và pipeline vector (nếu có).
- integrations.sheets
  - Input: operation(read/write/append), spreadsheet_id, range, values?, auth_ref.
  - Output: rows/ack.
  - Thay thế: `service/integrations/sheet_service.py`.

### 3.1) Agent hiện tại trong codebase: wiring và workflow
 - Tạo agent
   - File: `service/agents/agent_service.py`, hàm `create_agent_executor`.
   - LLM: `google_genai` → `gemini-2.5-flash-lite`; `openai` → `gpt-4o-mini`.
   - Prompt hệ thống: `compose_system_prompt(...)` dựa trên `customer_config` và các feature flags.
   - Tool: lấy từ `create_customer_tools(...)` trong `service/utils/tools.py`.
   - Agent: `create_react_agent(llm, customer_tools)` và được bọc bởi `_AgentWrapper.ainvoke(...)` để trích xuất `output` an toàn từ state.
 
 - Tool được cắm vào agent (theo `create_customer_tools`)
   - Luôn có:
     - `graphrag_search_tool` → `graphrag_search_logic` → `service/graphrag/graphrag_service.run_query(...)` (args: `GraphRAGQueryInput`).
     - `check_customer_info_tool` → kiểm tra DB đơn hàng gần nhất trong thread, trả về `existing_info` hoặc nhắc bổ sung thông tin.
     - `get_store_info_tool` → đọc `StoreInfo` từ DB, trả về message đã format (tên, địa chỉ, phone, email, web, FB, bản đồ, ảnh).
     - `escalate_to_human_tool` → trả lời mẫu từ `tool.escalate_to_human.response` (instructions DB).
     - `end_conversation_tool` → trả lời mẫu từ `tool.end_conversation.response` (instructions DB).
   - Theo tính năng (feature flags từ `customer_config`):
     - Sản phẩm (`product_feature_enabled`):
       - `search_products_tool` → `search_products_logic` → `service/retrieve/search_service.search_products(...)` (args: `SearchProductInput`: model, màu, dung_lượng, tình_trạng_máy, loại_thiết_bị, min/max giá, offset...).
       - `create_order_product_tool` → ghi `ProductOrder` vào DB; nếu `thread_id` hợp lệ thì gọi Zalo API tạo nhóm + gửi thông báo.
     - Dịch vụ (`service_feature_enabled`):
       - `search_services_tool` → `search_services_logic` → `search_services(...)` (args: `SearchServiceInput`: tên dịch vụ, tên sản phẩm cần sửa, loại dịch vụ, min/max giá...).
       - `create_order_service_tool` → ghi `ServiceOrder` vào DB; có gọi Zalo + thông báo khi hợp lệ.
     - Phụ kiện (`accessory_feature_enabled`):
       - `search_accessories_tool` → `search_accessories_logic` → `search_accessories(...)` (args: `SearchAccessoryInput`). LƯU Ý: bắt buộc `cum_dac_trung` khi có cụm đặc trưng (brand+model/mã).
       - `create_order_accessory_tool` → ghi `AccessoryOrder` vào DB; có gọi Zalo + thông báo khi hợp lệ.
 
 - Workflow gọi agent (invoke)
   - File: `service/agents/agent_service.py`, hàm `invoke_agent_with_memory`.
   - B1. Tìm FAQ trước bằng `search_faqs(...)` → chèn vào `faq_context` (HumanMessage gợi ý).
   - B2. Lấy `chat_history` từ DB (hoặc `history_override`) và format nhãn vai trò theo instructions.
   - B3. Tiêm ngữ cảnh cho tool tìm kiếm: set `original_query` và `chat_history` vào coroutine của các tool có tên `search_products_tool`, `search_services_tool`, `search_accessories_tool`.
   - B4. Gọi `agent_executor.ainvoke(...)` với `{input, chat_history, faq_context, thread_id}`.
   - B5. Lưu lịch sử hội thoại vào DB khi `persist=True`.
 
 - Lưu ý: `retrieve_document_logic(...)` tồn tại trong `tools.py` nhưng hiện chưa được thêm vào danh sách tool của `create_customer_tools` (chưa cắm vào agent).

### 3.2) Luồng chat hiện tại (ngoài agent) – `api/chat_routes.py`
 - B0. Kiểm tra trạng thái bot theo customer/thread, validate `threadId`, `customer_id`, và `access`.
 - B1. Xử lý đầu vào ảnh:
   - Nếu có `image_urls` hoặc `image_base64` → gọi `_identify_product_from_image(llm_provider, api_key, db, ...)`.
   - LLM cho vision: `google_genai → gemini-2.5-flash-lite`, `openai → gpt-4o-mini` (qua `init_chat_model`).
   - Lấy `product_prefix_label` từ DB instructions, ghép kết quả nhận diện vào `user_input` nếu có (ưu tiên text+ảnh; nếu không có text thì dùng kết quả ảnh).
 - B2. Tạo `customer_config` và gán feature flags theo `access` (1: sản phẩm, 2: dịch vụ, 3: phụ kiện) nếu `access != 100`.
 - B3. Tạo agent executor:
   - Gọi `create_agent_executor(...)` với `es_client, db, customer_id, customer_config, thread_id, llm_provider, api_key`.
   - Bên trong: chọn LLM theo provider, build tool list qua `create_customer_tools`, tạo `create_react_agent`, và bọc bằng `_AgentWrapper`.
 - B4. Gọi `invoke_agent_with_memory(...)`:
   - Tìm FAQ bằng `search_faqs(es, customer_id, user_input)` và chèn vào `faq_context`.
   - Lấy `chat_history` từ DB (hoặc `history_override`).
   - Tiêm `original_query` và `chat_history` vào coroutine của các tool tìm kiếm: `search_products_tool`, `search_services_tool`, `search_accessories_tool`.
   - Gọi `agent_executor.ainvoke({input, chat_history, faq_context, thread_id})` và lưu lịch sử vào DB nếu `persist=True`.
 - B5. Trả về `response['output']` cho API client.

## 4) Thiết kế ReAct cho `/chat/{threadId}`
- Chính sách chọn tool:
  - Có ảnh: gọi `vision.identify_product` trước; nếu có text kèm theo, ghép kết quả ảnh vào text với nhãn `product_prefix_label` từ DB.
  - Chỉ text: dùng `retrieval.search`; nếu cần chiều sâu, gọi thêm `vector_search`/`graphrag`.
  - Ràng buộc theo `access` (1: sản phẩm, 2: dịch vụ, 3: phụ kiện): chỉ cho phép tool/dữ liệu tương ứng.
- Giới hạn an toàn:
  - max_steps = 3–5; per_call_timeout = 8–12s; tổng ngân sách thời gian = 12–20s.
  - Early-stop khi độ tin cậy cao hoặc không cải thiện.
- Fallback:
  - Nếu MCP lỗi/timeout, fallback 1 lần sang logic legacy (`invoke_agent_with_memory`).
  - Shadow mode (qua feature flag): chạy MCP song song để đo chất lượng/latency, chưa trả kết quả MCP cho người dùng.

### 4.1) Agent workflow mới (MCP + ReAct): agent và tool
 - Orchestrator/Planner (Router)
   - Nhiệm vụ: phân loại intent, lập kế hoạch các bước, chọn agent phù hợp, giới hạn bước/timeout/budget.
   - Tool: không gọi tool trực tiếp; điều phối các agent bên dưới theo ReAct.
   - Gating theo `access`: chỉ kích hoạt agent tương ứng (1 sản phẩm, 2 dịch vụ, 3 phụ kiện).
 
 - Vision Agent
   - Dùng khi có ảnh (image_urls/base64) hoặc câu hỏi yêu cầu nhận diện từ ảnh.
   - Tool (MCP): `vision.identify_product`.
   - Output: product_spec/candidates/confidence; hợp nhất vào user_input theo `product_prefix_label`.
 
 - Product Agent
   - Dùng cho intent tra cứu sản phẩm (điện thoại, tablet...).
   - Tool (MCP): `retrieval.search` (index sản phẩm), `retrieval.vector_search` (optional), `retrieval.graphrag` (optional chiều sâu).
   - Ghi chú: ưu tiên `retrieval.search`; dùng vector/graphrag khi cần chi tiết/khái quát.
 
 - Service Agent
   - Dùng cho intent dịch vụ sửa chữa.
   - Tool (MCP): `retrieval.search` (index dịch vụ), `retrieval.vector_search` (optional).
 
 - Accessory Agent
   - Dùng cho intent phụ kiện/linh kiện.
   - Tool (MCP): `retrieval.search` (index phụ kiện), `retrieval.vector_search` (optional).
   - Quy tắc: khi câu hỏi có CỤM ĐẶC TRƯNG (brand+model/mã) phải truyền tham số tương đương `cum_dac_trung` để MUST match chính xác.
 
 - FAQ Agent
   - Dùng khi câu hỏi khớp với FAQ.
   - Tool (MCP): `retrieval.search` (index FAQ).
 
 - Knowledge Agent (GraphRAG)
   - Dùng khi cần tổng hợp kiến thức sâu, tường thuật hoặc quan hệ.
   - Tool (MCP): `retrieval.graphrag` (mode: local/global/drift/basic).
 
 - Store Info Agent
   - Dùng khi khách hỏi thông tin cửa hàng (địa chỉ, phone, web, FB, bản đồ...).
   - Tool (Local giai đoạn 1): `get_store_info_tool` (đọc DB StoreInfo). Có thể chuyển sang db-mcp về sau.
 
 - Customer Info Agent
   - Dùng trước khi tạo đơn, để lấy lại/đối chiếu thông tin cá nhân khách hàng từ đơn gần nhất trong thread.
   - Tool (Local giai đoạn 1): `check_customer_info_tool`.
 
 - Order Agent
   - Dùng khi khách xác nhận chốt đơn (sản phẩm/dịch vụ/phụ kiện). Tách riêng khỏi agent tra cứu.
   - Tool (Local giai đoạn 1): `create_order_product_tool`, `create_order_service_tool`, `create_order_accessory_tool`.
   - Hành vi kèm: nếu `thread_id` hợp lệ, gọi Zalo API tạo nhóm và gửi thông báo.
 
 - Escalation Agent
   - Dùng khi cần chuyển cho người thật.
   - Tool (Local): `escalate_to_human_tool`.
 
 - Closing Agent
   - Dùng khi khách chào tạm biệt/cảm ơn.
   - Tool (Local): `end_conversation_tool`.
 
 - Luồng định tuyến điển hình
   - Ảnh + (tuỳ) text: Orchestrator → Vision Agent → hợp nhất input → Product/Accessory Agent → (khách chốt) Customer Info Agent → Order Agent.
   - Text sản phẩm: Orchestrator → Product Agent → (cần thêm) vector/graphrag → (khách chốt) Customer Info Agent → Order Agent.
   - Text dịch vụ: Orchestrator → Service Agent → (khách chốt) Customer Info Agent → Order Agent.
   - Text phụ kiện: Orchestrator → Accessory Agent (bắt buộc cụm đặc trưng khi có) → (khách chốt) Customer Info Agent → Order Agent.
   - Hỏi thông tin cửa hàng: Orchestrator → Store Info Agent.
   - Hỏi theo FAQ: Orchestrator → FAQ Agent; nếu không chắc → Product/Service/Accessory Agent tuỳ intent.
   - Câu hỏi kiến thức tổng hợp: Orchestrator → Knowledge Agent.
   - Yêu cầu nói chuyện người thật: Orchestrator → Escalation Agent.
   - Kết thúc trò chuyện: Orchestrator → Closing Agent.
 
 - Ghi chú triển khai
   - ReAct loop chạy ở Orchestrator: Plan → (Call Agent) → Observe → Decide → Final, với `max_steps`, per_call_timeout và tổng ngân sách như mục 4.
   - Caching: tái sử dụng MCP connections, tool list, và agent per-tenant (xem mục 10).

### 4.2) Tool mapping chi tiết cho từng Agent (logic mới)
 - Orchestrator/Planner
   - Tools: Không dùng tool trực tiếp.
   - Nhiệm vụ: Chọn agent theo intent, access và lịch sử quan sát. Kiểm soát bước/timeout/budget.
 
 - Vision Agent
   - MCP Server: vision-mcp
   - Tool: `vision.identify_product`
   - Input: `image_urls[]`, `image_base64?`, `customer_id`
   - Output: `product_spec`, `candidates[]`, `confidence`, `citations`
   - Fallback: giữ nguyên `_identify_product_from_image` tạm thởi (legacy) nếu bật fallback.
 
 - Product Agent
   - MCP Server: retrieval-mcp
   - Tools: 
     - `retrieval.search` (index=products) — chính
     - `retrieval.vector_search` — bổ sung chiều sâu khi cần
     - `retrieval.graphrag` — tóm tắt/tương quan khi cần
   - Fallback: `search_products_tool` (legacy) cho canary/rollback.
 
 - Service Agent
   - MCP Server: retrieval-mcp
   - Tools:
     - `retrieval.search` (index=services)
     - `retrieval.vector_search` (optional)
   - Fallback: `search_services_tool` (legacy).
 
 - Accessory Agent
   - MCP Server: retrieval-mcp
   - Tools:
     - `retrieval.search` (index=accessories) — lưu ý truyền tham số tương đương `cum_dac_trung` để MUST match khi có cụm đặc trưng (brand+model/mã)
     - `retrieval.vector_search` (optional)
   - Fallback: `search_accessories_tool` (legacy).
 
 - FAQ Agent
   - MCP Server: retrieval-mcp
   - Tool: `retrieval.search` (index=faq)
   - Fallback: logic `search_faqs` hiện tại trước khi invoke agent.
 
 - Knowledge Agent (GraphRAG)
   - MCP Server: retrieval-mcp
   - Tool: `retrieval.graphrag` (mode: local/global/drift/basic)
   - Fallback: `graphrag_search_tool` (legacy).
 
 - Store Info Agent
   - Hiện tại (giai đoạn 1): Local tool `get_store_info_tool` (đọc DB `StoreInfo`).
   - Định hướng: chuyển sang db-mcp `db.store_info.get` với `customer_id`.
 
 - Customer Info Agent
   - Hiện tại (giai đoạn 1): Local tool `check_customer_info_tool` để lấy thông tin từ đơn gần nhất trong thread.
   - Định hướng: db-mcp `db.orders.last_for_thread` để trả `existing_info` chuẩn hoá.
 
 - Order Agent
   - Hiện tại (giai đoạn 1): Local tools `create_order_product_tool`, `create_order_service_tool`, `create_order_accessory_tool` (ghi DB; nếu `thread_id` hợp lệ thì gọi Zalo API + thông báo).
   - Định hướng: integrations-mcp `orders.create` (I/O chuẩn) và `messaging.notify` (Zalo/ChatOps) với `auth_ref`.
 
 - Escalation Agent
   - Hiện tại: Local tool `escalate_to_human_tool` (message mẫu từ instructions DB).
   - Định hướng: integrations-mcp `escalate.open_ticket`.
 
 - Closing Agent
   - Hiện tại: Local tool `end_conversation_tool` (message mẫu từ instructions DB).
   - Định hướng: giữ local hoặc chuyển `templates.render_closing` (không cần MCP).
 
 - Quy tắc định tuyến tổng quát
   - Orchestrator chọn 1 agent/step theo intent và access.
   - Có ảnh → Vision trước; hợp nhất input → agent nội dung (Product/Accessory).
   - Nếu câu hỏi khớp FAQ cao → FAQ Agent; nếu không, chuyển agent nội dung tương ứng.
   - Khi người dùng “chốt” → Customer Info Agent → Order Agent.
   - Khi yêu cầu người thật → Escalation Agent; khi kết thúc → Closing Agent.

### 4.3) API cấu hình MCP theo Agent (multi-tenant)
- Mục tiêu
  - Thêm MCP mới hoặc chọn MCP đã có và bind tool vào từng agent theo tenant.
  - Orchestrator/Agent dùng “effective config” để biết mỗi agent có những MCP tool nào.

- Thực thể dữ liệu
  - MCPServer: id, name, transport(stdio/http/sse), endpoint/command, auth_ref, tags, health_status, last_checked
  - AgentBinding: id, tenant_id, agent_type (vision|product|service|accessory|faq|knowledge|store_info|customer_info|order|escalation|closing), mcp_server_id, tool_ids[], defaults (index/top_k/mode...), priority, enabled, version, updated_at
  - EffectiveConfig (tính): tổng hợp binding đang enabled theo priority và health

- Endpoints (REST)
  - MCP Servers
    - POST /config/mcp/servers — tạo server MCP
    - GET  /config/mcp/servers — liệt kê
    - GET  /config/mcp/servers/{server_id} — chi tiết
    - PATCH /config/mcp/servers/{server_id} — cập nhật
    - DELETE /config/mcp/servers/{server_id} — xóa
    - POST /config/mcp/servers/{server_id}/probe — kiểm tra health + liệt kê tools
  - Agent ↔ MCP Bindings
    - POST   /config/agents/{tenant_id}/{agent_type}/bindings — tạo binding (chọn server qua mcp_server_id)
    - GET    /config/agents/{tenant_id}/{agent_type}/bindings — liệt kê binding
    - PATCH  /config/agents/{tenant_id}/{agent_type}/bindings/{binding_id} — cập nhật
    - DELETE /config/agents/{tenant_id}/{agent_type}/bindings/{binding_id} — xóa
  - Effective config & cache control
    - GET  /config/agents/{tenant_id}/effective — cấu hình hiệu lực toàn tenant
    - GET  /config/agents/{tenant_id}/{agent_type}/effective — cấu hình hiệu lực 1 agent
    - POST /config/agents/{tenant_id}/reload — invalidate + rebuild cache (client/tools/agent)

- Ví dụ: binding cho Product Agent
```json
{
  "mcp_server_id": 12,
  "tool_ids": ["retrieval.search"],
  "defaults": {"index": "products", "top_k": 8},
  "priority": 1,
  "enabled": true
}
```
- Ví dụ: binding cho Vision Agent
```json
{
  "mcp_server_id": 5,
  "tool_ids": ["vision.identify_product"],
  "defaults": {},
  "priority": 1,
  "enabled": true
}
```

- Luồng runtime (Orchestrator/Agent)
  - Khi Plan: lấy `effective config` theo tenant từ cache.
  - Nếu version đổi hoặc cache miss: gọi GET effective để refresh, rồi cache lại.
  - Agent chỉ gọi tool theo binding của agent_type, áp dụng defaults (index/top_k/mode...).
  - Nếu nhiều binding: chọn theo priority và health; lỗi → failover binding kế tiếp.
  - Nếu tất cả lỗi và `fallback_legacy=true` → dùng legacy tool tạm.

- Bảo mật & phân quyền
  - Theo tenant; chỉ admin/owner được sửa server/binding.
  - `auth_ref` trỏ tới secret manager; không lưu plaintext; không log payload nhạy cảm.

- Reload & versioning
  - Tạo/sửa/xóa server/binding: tăng `config_version` cho tenant và trigger background pre-build cache (xem mục 10).
  - Orchestrator kiểm tra `config_version` để reload nhẹ, không chặn request.

## 5) Thay đổi chính trong mã nguồn
- api/chat_routes.py
  - Giữ kiểm tra `customer_status`, `thread_status`, `access` như hiện tại.
  - Thay `_identify_product_from_image` bằng gọi MCP `vision.identify_product` (nếu có ảnh).
  - Thay `create_agent_executor` + `invoke_agent_with_memory` bằng `react_orchestrator.run(...)` (orchestrator sẽ gọi MCP tool theo ReAct).
  - Thêm fallback/feature flag/shadow mode.
- service/prompts/prompt_service.py (get_system_prompt)
  - Bổ sung mô tả tool MCP (tên, khi nào dùng, input/output). 
  - Hướng dẫn ReAct: Plan trước, 1 tool/step, tóm tắt quan sát, dừng khi đủ.
  - Nhắc ràng buộc `access` và không bịa nếu thiếu dữ kiện.
- service/utils/tools.py và các service khác
  - Chuyển sang adapter gọi MCP client thay vì gọi trực tiếp.

## 6) Kiểm thử
- Unit: validate schema, map lỗi, retry/backoff.
- Integration: MCP client ↔ server, timeouts, circuit breaker.
- E2E: `/chat` với các kịch bản:
  - text-only, image-only, text+image.
  - access = 1/2/3/100.
  - sự cố: tool down, chậm, sai schema.

## 7) Triển khai an toàn
- Staging: bật shadow mode 100% để so sánh chất lượng/latency.
- Canary theo `customer_id`: 5% → 25% → 50% → 100%.
- Rollback: tắt feature flag để quay về legacy trong 1 bước.

## 8) Bảo mật & logs
- Không log raw ảnh/base64; che PII.
- API keys dùng env/secret manager; truyền cho MCP qua `auth_ref` hoặc biến môi trường.
- Logging/tracing/metrics: mỗi bước ReAct và mỗi lần gọi MCP (tool_name, latency, success, error_code, tokens).

## 9) Timeline gợi ý
- Tuần 1: Inventory, kiến trúc MCP, schema, skeleton server/client.
- Tuần 2: Port retrieval + vision, tích hợp client, shadow mode.
- Tuần 3: ReAct orchestrator, cập nhật prompt, test integration/E2E.
- Tuần 4: Canary, tối ưu, tài liệu, cutover.

## 10) Cache MCP client/tool/agent (multi-tenant) – tránh load mỗi tin nhắn
- Vấn đề:
  - Tạo MCP client + load tools + build agent cho mỗi message gây thêm 100ms–2s, tốn tài nguyên.
  - Với multi-tenant, việc này lặp lại nhiều lần và làm API chậm.
- Giải pháp: Cache 3 lớp theo tenant (ví dụ key = customer_id/tenant_id):
  - Layer 1 — Connection cache:
    - Lưu MultiServer MCP Client đã kết nối (stdio/HTTP/SSE). Giữ keepalive/heartbeat.
    - Reconnect theo backoff khi đứt; circuit breaker khi lỗi nhiều.
  - Layer 2 — Tool list cache:
    - Lưu danh sách tools đã load và version/hash. Chỉ reload khi cấu hình thay đổi.
  - Layer 3 — Agent cache:
    - Lưu agent/graph đã build sẵn gắn với tool list. Có thể kèm policy theo access.
- Warm-up/Preload:
  - Khi backend khởi động: có thể preconnect tenants quan trọng hoặc lazy-connect lần đầu.
  - Khi user cập nhật cấu hình: rebuild ở background, không chặn request.
- Reload/Invalidation khi:
  - Thêm/bớt MCP server, đổi cấu hình tool, rotate secrets/credentials.
  - Backend restart hoặc MCP server unhealthy/schema thay đổi.
  - TTL/idle-eviction để kiểm soát bộ nhớ.
- Concurrency & an toàn:
  - Dùng lock theo tenant để tránh build trùng; giới hạn đồng thời; fallback legacy nếu lỗi.
- Bộ nhớ & lifecycle:
  - LRU eviction, max tenants in RAM, TTL theo idle, metrics theo dõi usage.
  - Mỗi worker giữ cache riêng; cân nhắc pre-warm per worker.
- Observability:
  - Metrics: cache_hit_rate (3 lớp), preheat_latency, connect_errors, agent_build_time.
- Tích hợp vào /chat:
  - Lấy tenant_id (customer_id) sớm → lấy từ cache client/tools/agent.
  - Chỉ build mới khi không có hoặc stale; ngược lại dùng lại như Cursor/Claude/VSCode.

---
Ghi chú: Tài liệu này là định hướng thực thi. Chi tiết kỹ thuật (schema JSON, mô tả tool trong prompt, error codes) sẽ bổ sung trong bước thiết kế cụ thể.
