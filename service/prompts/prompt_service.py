from typing import Dict, List
from sqlalchemy.orm import Session

from database.database import SystemInstruction, Customer


def load_instructions(db: Session) -> Dict[str, str]:
    rows = db.query(SystemInstruction).all()
    data = {row.key: row.value for row in rows}
    print(f"[PROMPT] Loaded SystemInstruction keys: {list(data.keys())}")
    return data


def _render(text: str, params: Dict[str, str]) -> str:
    if not text:
        return ""
    for k, v in params.items():
        text = text.replace("{" + k + "}", v or "")
    return text


def compose_system_prompt(
    db: Session,
    customer_config: Customer,
    product_feature_enabled: bool,
    service_feature_enabled: bool,
    accessory_feature_enabled: bool,
) -> str:
    instr = load_instructions(db)
    
    def _pick(key: str, default_value: str) -> str:
        if key in instr:
            print(f"[PROMPT] {key}: DB")
            return instr.get(key, default_value)
        else:
            print(f"[PROMPT] {key}: default")
            return default_value

    ai_name = customer_config.ai_name or ""
    ai_role = customer_config.ai_role or ""
    params = {"ai_name": ai_name, "ai_role": ai_role}

    persona_template = _pick(
        "persona_template",
        (
            "Bạn là một chuyên gia tư vấn của một cửa hàng sản phẩm và cung cấp một số các dịch vụ, "
            "đóng vai là một {ai_role} am hiểu và thân thiện tên là {ai_name}."
        ),
    )
    persona_section = _render(persona_template, params).strip()

    tone_style = _pick(
        "tone_style",
        (
            "Luôn xưng hô là \"em\" và gọi khách hàng là \"anh/chị\". Khi nói về cửa hàng, hãy dùng \"bên em\".\n"
            "Hãy mô tả một cách khách quan, ví dụ: \"sản phẩm có...\", \"máy được trang bị...\"."
        ),
    )

    base_instructions = _pick("base_instructions", "")

    product_workflow = _pick(
        "product_workflow",
        "-   Khi khách hỏi về **sản phẩm** (điện thoại, máy tính bảng, ...), dùng `search_products_tool`.",
    )
    service_workflow = _pick(
        "service_workflow",
        "-   Khi khách hỏi về **dịch vụ** (sửa chữa, thay pin, ...), dùng `search_services_tool`.",
    )
    accessory_workflow = _pick(
        "accessory_workflow",
        (
            "-   Khi khách hỏi về **linh kiện / phụ kiện** (ốp lưng, sạc, tai nghe, ...), dùng `search_accessories_tool`. "
            "Nếu khách chốt mua, dùng `create_order_accessory_tool`."
        ),
    )

    steps: List[str] = []
    if product_feature_enabled:
        steps.append(product_workflow)
    if service_feature_enabled:
        steps.append(service_workflow)
    if accessory_feature_enabled:
        steps.append(accessory_workflow)

    workflow_header = _pick("workflow_header", "**Quy trình làm việc:**")
    if steps:
        steps_block = "\n   " + "\n   ".join(steps)
    else:
        steps_block = ""

    workflow_section = (
        f"{workflow_header}\n"
        "1. Xác định nhu cầu của khách: **sản phẩm**, **dịch vụ**, hay **linh kiện/phụ kiện**.\n"
        "2. Sử dụng công cụ tìm kiếm tương ứng:\n"
        f"   {steps_block}\n"
        "3. Mọi câu hỏi tra cứu tri thức/chính sách/hướng dẫn KHÔNG thuộc 3 nhóm trên: **DÙNG `graphrag_search_tool`**.\n"
        "   - Chọn phương thức phù hợp: `local` (thực thể cụ thể), `global` (tổng hợp toàn cục), `drift` (kết hợp), `basic` (RAG vector cơ bản).\n"
    )

    workflow_instructions_add = _pick("workflow_instructions", "")

    pagination_instruction = _pick(
        "pagination_instruction",
        (
            "**Phân trang kết quả (Pagination):**\n"
            "- Mỗi lần tìm kiếm, công cụ chỉ trả về tối đa 10 kết quả.\n"
            "- Nếu người dùng muốn xem thêm (ví dụ: \"còn gì nữa không?\", \"xem thêm các sản phẩm khác\"), bạn BẮT BUỘC phải gọi lại đúng công cụ tìm kiếm đó với các tham số y hệt lần trước, nhưng TĂNG giá trị của tham số `offset` lên 10.\n"
            "- Nếu công cụ trả về một danh sách rỗng, điều đó có nghĩa là đã hết kết quả để hiển thị. Hãy thông báo cho khách hàng biết điều này."
        ),
    )

    faq_instruction = _pick(
        "faq_instruction",
        (
            "**Quy trình ưu tiên FAQ:**\n"
            "- Hệ thống có thể đã tìm kiếm trước trong kho Câu hỏi thường gặp (FAQ) và cung cấp một gợi ý trong context.\n"
            "- **Ưu tiên tuyệt đối:** Hãy xem xét kỹ gợi ý này trước tiên (nếu có).\n"
            "- Nếu gợi ý phù hợp với câu hỏi của người dùng, hãy dùng nó để trả lời.\n"
            "- **QUAN TRỌNG:** Nếu không có gợi ý nào từ FAQ, hoặc gợi ý không phù hợp, bạn BẮT BUỘC phải bỏ qua nó và tiếp tục quy trình làm việc bình thường bằng cách sử dụng các công cụ khác để tìm thông tin và trả lời câu hỏi. TUYỆT ĐỐI không được trả về câu trả lời rỗng chỉ vì không có FAQ."
        ),
    )

    other_instructions = _pick("other_instructions", "")

    custom_prompt_text = customer_config.custom_prompt or ""
    print(f"[PROMPT] custom_prompt: {'present' if custom_prompt_text else 'empty'}")
    custom_prompt_section = (
        f"\n**Lưu ý đặc biệt cần ưu tiên tuân thủ (Strictly follow this):**\n{custom_prompt_text}\n"
        if custom_prompt_text
        else ""
    )

    final_system_prompt = "\n".join(
        filter(
            None,
            [
                persona_section,
                tone_style,
                base_instructions,
                workflow_section,
                custom_prompt_section,
                pagination_instruction,
                workflow_instructions_add,
                faq_instruction,
                other_instructions,
            ],
        )
    )

    return final_system_prompt
