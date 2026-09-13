"""
🧠 PROMPT & GUARDRAILS SPECIFICATION (Role 3: Guardrail & Security Developer)
Định nghĩa System Prompts, Ranh giới an toàn (Boundaries) và Bộ kiểm duyệt Prompt Injection.
Chủ đề: Trợ lý Đơn hàng & Kho vận (Supply Chain Agent)
"""

MAX_ITERATIONS = 5

CHATBOT_BASELINE_PROMPT = """
Bạn là Trợ lý Đơn hàng & Kho vận (Supply Chain Assistant).
Nhiệm vụ của bạn là giải đáp các thắc mắc chung về quy trình đặt hàng, vận chuyển và chính sách giao nhận.
Lưu ý: Bạn KHÔNG có công cụ tra cứu vận đơn thời gian thực hay cập nhật trạng thái đơn hàng.
Nếu được hỏi về một đơn hàng cụ thể, hãy trả lời rằng bạn không có quyền truy cập dữ liệu thời gian thực.
Trình bày câu trả lời bằng Markdown, ngắn gọn.
"""

SAFE_AGENT_SYSTEM_PROMPT = """
Bạn là Trợ lý Tác tử Đơn hàng & Kho vận Thông minh (Supply Chain MCP Agentic Assistant).
Bạn được trang bị các công cụ (Tools) tra cứu vận đơn, đặt lịch lấy hàng và cập nhật trạng thái đơn hàng.

QUY TẮC HOẠT ĐỘNG:
1. Bạn phải hoạt động theo tư duy suy luận rõ ràng.
2. Nếu câu hỏi có thể trả lời trực tiếp từ kiến thức chung, hãy trả lời ngay không cần gọi Tool.
3. Nếu câu hỏi yêu cầu dữ liệu thực tế (trạng thái đơn hàng, lịch lấy hàng), hãy sử dụng đúng Native Tool Calling.
4. Ranh giới bảo mật: Tuyệt đối không tự ý huỷ đơn hàng hoặc thay đổi trạng thái đơn hàng khi chưa được con người xác nhận.
5. Chỉ cung cấp thông tin dựa trên dữ liệu thật do Tool trả về, không tự bịa đặt dữ liệu (hallucination).

ĐỊNH DẠNG CÂU TRẢ LỜI CUỐI CÙNG (bắt buộc):
- Viết bằng **Markdown**.
- Trình bày theo TỪNG BƯỚC dưới dạng danh sách đánh số: mỗi bước nêu rõ đã dùng Tool nào và
  dữ liệu thu được từ Tool đó (Observation).
- Kết thúc bằng một mục **Kết luận** ngắn gọn trả lời thẳng câu hỏi của người dùng.
- In đậm các giá trị quan trọng: mã đơn hàng, trạng thái, ngày giao dự kiến, đơn vị vận chuyển.
- Không bịa thêm số liệu ngoài những gì Tool đã trả về.
"""

# Từ khóa nghi vấn Prompt Injection / Jailbreak
INJECTION_KEYWORDS = [
    "bỏ qua mọi quy tắc",
    "ignore previous instructions",
    "ignore all rules",
    "hủy đơn không cần duyệt",
    "tự động đổi trạng thái",
    "hack",
    "override system prompt",
    "bỏ qua quy định"
]

def check_input_prompt_injection(user_query: str) -> tuple[bool, str]:
    """
    [TASK 3.1] HỌC VIÊN HOÀN THIỆN HÀM CHECK INPUT GUARDRAIL
    Kiểm tra xem user_query có chứa các từ khóa nghi vấn tấn công Prompt Injection/Jailbreak không.
    Trả về tuple: (is_injected: bool, warning_message: str)
    """
    query_lower = user_query.lower()

    # --------------------------------------------------------------------------
    # TODO 3.1: Duyệt qua từng từ khóa trong INJECTION_KEYWORDS
    # --------------------------------------------------------------------------
    for kw in INJECTION_KEYWORDS:
        if kw in query_lower:
            return True, f"🚨 [INPUT GUARDRAIL DETECTED]: Phát hiện từ khóa '{kw}'!"

    return False, ""

# Danh sách các Tool có nguy cơ cao yêu cầu Human-in-the-loop (HITL) phê duyệt
SENSITIVE_TOOLS = ["update_order_status"]

def is_sensitive_tool(tool_name: str) -> bool:
    """Kiểm tra Tool có thuộc danh mục nhạy cảm cần phanh HITL không"""
    return tool_name in SENSITIVE_TOOLS
