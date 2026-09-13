"""
🛠️ TOOL DEFINITIONS & NATIVE JSON SCHEMAS (Chuẩn OpenAPI / MCP Specification)
Định nghĩa các Tool Schemas chuẩn hóa dùng cho Native Tool Calling API của LLM.
Chủ đề: Trợ lý Đơn hàng & Kho vận (Supply Chain Agent)
"""

import json
from typing import Dict, Any

# ==============================================================================
# 1. KHAI BÁO TOOL SCHEMAS CHUẨN NATIVE JSON SCHEMA (TASK 1.2)
# ==============================================================================

TOOLS_SCHEMA = [
    # Tool 1: Tra cứu vận đơn / trạng thái đơn hàng
    {
        "name": "track_order",
        "description": "Tra cứu thông tin vận đơn và trạng thái hiện tại của đơn hàng theo mã đơn hàng.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "Mã đơn hàng cần tra cứu (ví dụ: 'ORD2026001')"
                }
            },
            "required": ["order_id"]
        }
    },

    # Tool 2: Đặt lịch lấy hàng (pickup) với đơn vị vận chuyển
    {
        "name": "schedule_pickup",
        "description": "Đặt lịch lấy hàng (pickup) với đơn vị vận chuyển cho một đơn hàng cụ thể.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "Mã đơn hàng (ví dụ: 'ORD2026001')"
                },
                "pickup_datetime": {
                    "type": "string",
                    "description": "Thời gian lấy hàng mong muốn (ví dụ: '09:00 20/09/2026')"
                },
                "carrier_name": {
                    "type": "string",
                    "description": "Tên đơn vị vận chuyển (mặc định: 'Giao Hàng Nhanh (GHN)')"
                }
            },
            "required": ["order_id", "pickup_datetime"]
        }
    },

    # Tool 3: Cập nhật trạng thái đơn hàng (NHẠY CẢM - cần HITL)
    {
        "name": "update_order_status",
        "description": "[HÀNH ĐỘNG NHẠY CẢM - CẦN HITL PHÊ DUYỆT] Cập nhật trạng thái đơn hàng (ví dụ: huỷ đơn, xác nhận giao thất bại, đổi trạng thái vận chuyển).",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "Mã đơn hàng cần cập nhật"
                },
                "new_status": {
                    "type": "string",
                    "description": "Trạng thái mới cần cập nhật (ví dụ: 'Đã hủy', 'Giao thất bại', 'Đã giao thành công')"
                },
                "reason": {
                    "type": "string",
                    "description": "Lý do cập nhật trạng thái"
                }
            },
            "required": ["order_id", "new_status"]
        }
    }
]

# ==============================================================================
# 2. MÔ PHỎNG DỮ LIỆU & HÀM THỰC THI TOOL (EXECUTION LAYER)
# ==============================================================================

MOCK_DATABASE = {
    "ORD2026001": {
        "customer_name": "Nguyễn Văn An",
        "product": "Laptop Dell XPS 13",
        "warehouse": "Kho Tổng Hà Nội",
        "carrier": "Giao Hàng Nhanh (GHN)",
        "status": "Đang vận chuyển",
        "current_location": "Trung tâm phân loại Hà Nội",
        "expected_delivery": "16/09/2026"
    },
    "ORD2026002": {
        "customer_name": "Trần Thị Bình",
        "product": "Bàn phím cơ Keychron K8",
        "warehouse": "Kho Tổng Hồ Chí Minh",
        "carrier": "Viettel Post",
        "status": "Đã giao thành công",
        "current_location": "Đã giao tại TP.HCM",
        "expected_delivery": "12/09/2026"
    }
}


def execute_track_order(order_id: str) -> str:
    """Thực thi tra cứu vận đơn / trạng thái đơn hàng"""
    order = MOCK_DATABASE.get(order_id.strip().upper())
    if order:
        return json.dumps({
            "status": "SUCCESS",
            "order_id": order_id,
            "data": order
        }, ensure_ascii=False)
    else:
        return json.dumps({
            "status": "NOT_FOUND",
            "message": f"Không tìm thấy dữ liệu đơn hàng có mã '{order_id}'"
        }, ensure_ascii=False)


def execute_schedule_pickup(order_id: str, pickup_datetime: str, carrier_name: str = "Giao Hàng Nhanh (GHN)") -> str:
    """Thực thi đặt lịch lấy hàng (pickup) với đơn vị vận chuyển"""
    return json.dumps({
        "status": "SUCCESS",
        "pickup_id": f"PU-{order_id}-01",
        "order_id": order_id,
        "pickup_datetime": pickup_datetime,
        "carrier": carrier_name,
        "message": f"Đặt lịch lấy hàng thành công cho đơn {order_id} với {carrier_name} vào lúc {pickup_datetime}."
    }, ensure_ascii=False)


def execute_update_order_status(order_id: str, new_status: str, reason: str = "Không có ghi chú") -> str:
    """Thực thi cập nhật trạng thái đơn hàng (Hành động nhạy cảm - Yêu cầu phanh HITL)"""
    order_id_upper = order_id.strip().upper()
    if order_id_upper in MOCK_DATABASE:
        MOCK_DATABASE[order_id_upper]["status"] = new_status
        return json.dumps({
            "status": "SUCCESS",
            "order_id": order_id_upper,
            "new_status": new_status,
            "reason": reason,
            "message": f"Đã cập nhật trạng thái đơn hàng '{order_id_upper}' thành '{new_status}'."
        }, ensure_ascii=False)
    return json.dumps({"status": "ERROR", "message": "Đơn hàng không tồn tại!"}, ensure_ascii=False)


# Router gọi tool thực tế
TOOL_ROUTER = {
    "track_order": execute_track_order,
    "schedule_pickup": execute_schedule_pickup,
    "update_order_status": execute_update_order_status
}

def dispatch_tool_call(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Hàm trung chuyển thực thi tool"""
    if tool_name in TOOL_ROUTER:
        try:
            return TOOL_ROUTER[tool_name](**arguments)
        except Exception as e:
            return json.dumps({"status": "EXECUTION_ERROR", "error": str(e)}, ensure_ascii=False)
    return json.dumps({"status": "UNKNOWN_TOOL", "error": f"Tool '{tool_name}' không tồn tại!"}, ensure_ascii=False)
