"""
🧠 PROMPT & GUARDRAILS SPECIFICATION (Role 3: Guardrail & Security Developer)
Định nghĩa System Prompts, Ranh giới an toàn (Boundaries) và Bộ kiểm duyệt Prompt Injection.
"""

MAX_ITERATIONS = 5

CHATBOT_BASELINE_PROMPT = """
Bạn là Trợ lý Học vụ thuộc Đại học VinUni.
Nhiệm vụ của bạn là giải đáp các thắc mắc chung của sinh viên về quy chế học vụ.
Lưu ý: Bạn KHÔNG có công cụ tra cứu cơ sở dữ liệu thời gian thực hay cập nhật thông tin cá nhân.
Nếu được hỏi về thông tin sinh viên cụ thể, hãy trả lời rằng bạn không có quyền truy cập dữ liệu thời gian thực.
"""

SAFE_AGENT_SYSTEM_PROMPT = """
Bạn là Trợ lý Tác tử Học vụ Thông minh (MCP Agentic Assistant) của Đại học VinUni.
Bạn được trang bị các công cụ (Tools) tra cứu cơ sở dữ liệu và hỗ trợ sinh viên.

QUY TẮC HOẠT ĐỘNG:
1. Bạn phải hoạt động theo tư duy suy luận rõ ràng.
2. Nếu câu hỏi có thể trả lời trực tiếp từ kiến thức chung, hãy trả lời ngay không cần gọi Tool.
3. Nếu câu hỏi yêu cầu dữ liệu thực tế (thông tin sinh viên, lịch hẹn), hãy sử dụng đúng Native Tool Calling.
4. Ranh giới bảo mật: Tuyệt đối không thực hiện các yêu cầu vi phạm chính sách nhà trường, không tự ý thay đổi điểm số.
5. Chỉ cung cấp thông tin dựa trên dữ liệu thật do Tool trả về, không tự bịa đặt dữ liệu (hallucination).
"""

# Từ khóa nghi vấn Prompt Injection / Jailbreak
INJECTION_KEYWORDS = [
    "bỏ qua mọi quy tắc",
    "ignore previous instructions",
    "ignore all rules",
    "thay đổi điểm",
    "sửa điểm",
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
    # Nếu kw in query_lower:
    #     trả về (True, f"🚨 [INPUT GUARDRAIL DETECTED]: Phát hiện từ khóa '{kw}'!")
    # --------------------------------------------------------------------------
    # (Học viên tự viết code vòng lặp duyệt INJECTION_KEYWORDS tại đây)

    return False, ""

# Danh sách các Tool có nguy cơ cao yêu cầu Human-in-the-loop (HITL) phê duyệt
SENSITIVE_TOOLS = ["update_student_profile"]

def is_sensitive_tool(tool_name: str) -> bool:
    """Kiểm tra Tool có thuộc danh mục nhạy cảm cần phanh HITL không"""
    return tool_name in SENSITIVE_TOOLS
