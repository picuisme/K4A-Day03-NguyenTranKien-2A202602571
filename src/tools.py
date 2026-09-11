"""
🛠️ TOOL DEFINITIONS & NATIVE JSON SCHEMAS (Chuẩn OpenAPI / MCP Specification)
Định nghĩa các Tool Schemas chuẩn hóa dùng cho Native Tool Calling API của LLM.
"""

import json
from typing import Dict, Any

# ==============================================================================
# 1. KHAI BÁO TOOL SCHEMAS CHUẨN NATIVE JSON SCHEMA (TASK 1.2)
# ==============================================================================

TOOLS_SCHEMA = [
    # Tool 1: Đã mẫu sẵn cho Học viên tham khảo
    {
        "name": "academic_query",
        "description": "Tra cứu hồ sơ và thông tin học vụ của sinh viên VinUni bằng mã sinh viên.",
        "parameters": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "string",
                    "description": "Mã sinh viên cần tra cứu (ví dụ: 'SV2026001')"
                }
            },
            "required": ["student_id"]
        }
    },
    
    # --------------------------------------------------------------------------
    # TODO 1.2: HỌC VIÊN KHAI BÁO TOOL SCHEMA CHO 'schedule_appointment'
    # --------------------------------------------------------------------------
    {
        "name": "schedule_appointment",
        "description": "Đặt lịch hẹn tư vấn học vụ với Cố vấn học tập VinUni.",
        "parameters": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "string",
                    "description": "Mã sinh viên (ví dụ: 'SV2026001')"
                },
                "datetime_str": {
                    "type": "string",
                    "description": "Thời gian hẹn (ví dụ: '14:00 15/09/2026')"
                },
                "advisor_name": {
                    "type": "string",
                    "description": "Tên cố vấn (mặc định: 'PGS.TS Nguyễn Văn A')"
                }
            },
            "required": ["student_id", "datetime_str"]
        }
    },

    # --------------------------------------------------------------------------
    # TODO 1.2: HỌC VIÊN KHAI BÁO TOOL SCHEMA CHO 'update_student_profile' (NHẠY CẢM)
    # --------------------------------------------------------------------------
    {
        "name": "update_student_profile",
        "description": "[HÀNH ĐỘNG NHẠY CẢM - CẦN HITL PHÊ DUYỆT] Cập nhật thông tin hồ sơ sinh viên.",
        "parameters": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "string",
                    "description": "Mã sinh viên"
                },
                "field_to_update": {
                    "type": "string",
                    "description": "Trường dữ liệu cần sửa (ví dụ: 'email')"
                },
                "new_value": {
                    "type": "string",
                    "description": "Giá trị mới cần cập nhật"
                }
            },
            "required": ["student_id", "field_to_update", "new_value"]
        }
    }
]

# ==============================================================================
# 2. MÔ PHỎNG DỮ LIỆU & HÀM THỰC THI TOOL (EXECUTION LAYER)
# ==============================================================================

MOCK_DATABASE = {
    "SV2026001": {
        "full_name": "Nguyễn Văn An",
        "class": "AI-K4",
        "gpa": 3.85,
        "email": "an.nv@vinuni.edu.vn",
        "status": "Đang học",
        "advisor": "PGS.TS Nguyễn Văn A"
    },
    "SV2026002": {
        "full_name": "Trần Thị Bình",
        "class": "AI-K4",
        "gpa": 3.60,
        "email": "binh.tt@vinuni.edu.vn",
        "status": "Đang học",
        "advisor": "TS. Lê Thị B"
    }
}


def execute_academic_query(student_id: str) -> str:
    """Thực thi tra cứu học vụ"""
    student = MOCK_DATABASE.get(student_id.strip().upper())
    if student:
        return json.dumps({
            "status": "SUCCESS",
            "student_id": student_id,
            "data": student
        }, ensure_ascii=False)
    else:
        return json.dumps({
            "status": "NOT_FOUND",
            "message": f"Không tìm thấy dữ liệu sinh viên có mã '{student_id}'"
        }, ensure_ascii=False)


def execute_schedule_appointment(student_id: str, datetime_str: str, advisor_name: str = "PGS.TS Nguyễn Văn A") -> str:
    """Thực thi đặt lịch hẹn tư vấn học vụ"""
    return json.dumps({
        "status": "SUCCESS",
        "booking_id": f"BK-{student_id}-99",
        "student_id": student_id,
        "datetime": datetime_str,
        "advisor": advisor_name,
        "message": f"Đặt lịch thành công cho sinh viên {student_id} với {advisor_name} vào lúc {datetime_str}."
    }, ensure_ascii=False)


def execute_update_student_profile(student_id: str, field_to_update: str, new_value: str) -> str:
    """Thực thi cập nhật hồ sơ sinh viên (Hành động nhạy cảm - Yêu cầu phanh HITL)"""
    student_id_upper = student_id.strip().upper()
    if student_id_upper in MOCK_DATABASE:
        MOCK_DATABASE[student_id_upper][field_to_update] = new_value
        return json.dumps({
            "status": "SUCCESS",
            "student_id": student_id_upper,
            "updated_field": field_to_update,
            "new_value": new_value,
            "message": f"Đã cập nhật thành công trường '{field_to_update}' thành '{new_value}' cho SV {student_id_upper}."
        }, ensure_ascii=False)
    return json.dumps({"status": "ERROR", "message": "Sinh viên không tồn tại!"}, ensure_ascii=False)


# Router gọi tool thực tế
TOOL_ROUTER = {
    "academic_query": execute_academic_query,
    "schedule_appointment": execute_schedule_appointment,
    "update_student_profile": execute_update_student_profile
}

def dispatch_tool_call(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Hàm trung chuyển thực thi tool"""
    if tool_name in TOOL_ROUTER:
        try:
            return TOOL_ROUTER[tool_name](**arguments)
        except Exception as e:
            return json.dumps({"status": "EXECUTION_ERROR", "error": str(e)}, ensure_ascii=False)
    return json.dumps({"status": "UNKNOWN_TOOL", "error": f"Tool '{tool_name}' không tồn tại!"}, ensure_ascii=False)
