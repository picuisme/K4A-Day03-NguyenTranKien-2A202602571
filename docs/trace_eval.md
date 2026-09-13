# 📊 BÁO CÁO AGENTIC FIT SCORING MATRIX & TRACE EVALUATION (BƯỚC 3)

> **Họ và Tên Học viên:** Nguyễn Trần Kiên  
> **Mã Sinh Viên / Mã Học viên:** 2A202602571   
> **Chủ đề Lựa chọn:** Trợ lý Đơn hàng & Kho vận (Supply Chain Agent)  

---

## 1. BẢNG CHẤM ĐIỂM AGENTIC FIT SCORING MATRIX

| Tiêu chí Đánh giá | Mức độ (1 - 5) | Giải trình chi tiết lý do chọn điểm |
| :--- | :---: | :--- |
| **1. Multi-step Reasoning** | 4 / 5 | Yêu cầu tra vận đơn rồi mới quyết định đặt lịch lấy hàng / cập nhật trạng thái là chuỗi 2-3 bước suy luận nối tiếp (không phải 1 lệnh tra cứu đơn lẻ). |
| **2. Tool Interaction** | 4 / 5 | Cần kết nối MCP Server tới ít nhất 2-3 hệ thống khác nhau: quản lý kho/đơn hàng (WMS), đơn vị vận chuyển (carrier), và hệ thống ghi nhận trạng thái. |
| **3. Dynamic Decision** | 5 / 5 | Bước kế tiếp (đặt lịch lấy hàng, hủy đơn, hay chỉ trả lời) phụ thuộc HOÀN TOÀN vào observation vừa tra cứu được (đơn còn hàng, đã giao, hay bị delay) — đúng bản chất ReAct. |
| **4. Long Horizon Goal** | 4 / 5 | Mục tiêu theo dõi đơn hàng kéo dài suốt vòng đời (xuất kho → vận chuyển → giao hàng), Agent phải giữ ngữ cảnh (mã đơn nào, đã xử lý bước gì) qua nhiều lượt. |
| **TỔNG ĐIỂM AGENTIC FIT** | **17 / 20** | *Vượt xa ngưỡng 12/20 → Bài toán RẤT PHÙ HỢP để triển khai Agentic System (ReAct + MCP + Guardrails).* |

---

## 2. NHẬT KÝ WATERFALL TRACE LOG

Trace log dưới đây được trích từ lượt thực thi thật của **TC03 (multi_step_tool_call)** khi chạy `python src/app.py --all` ở chế độ Offline Mock — minh chứng Agent tự chuỗi đúng 2 bước Tool nối tiếp (`track_order` → `schedule_pickup`) dựa trên observation của bước trước, rồi tự tổng hợp câu trả lời cuối:

```json
[
  {
    "step": 0,
    "action_type": "GUARDRAIL_CHECK",
    "keyword_guardrail_triggered": false,
    "probabilistic_guardrail": { "probability": 0.0, "risk_level": "LOW", "matched_signals": [] },
    "latency_ms": 0.5
  },
  {
    "step": 1,
    "action_type": "TOOL_EXECUTION",
    "tool_name": "track_order",
    "arguments": { "order_id": "ORD2026002" },
    "observation": {
      "status": "SUCCESS",
      "order_id": "ORD2026002",
      "data": {
        "customer_name": "Trần Thị Bình",
        "product": "Bàn phím cơ Keychron K8",
        "warehouse": "Kho Tổng Hồ Chí Minh",
        "carrier": "Viettel Post",
        "status": "Đã giao thành công",
        "current_location": "Đã giao tại TP.HCM",
        "expected_delivery": "12/09/2026"
      }
    },
    "latency_ms": 0.02
  },
  {
    "step": 2,
    "action_type": "TOOL_EXECUTION",
    "tool_name": "schedule_pickup",
    "arguments": { "order_id": "ORD2026002", "pickup_datetime": "09:00 20/09/2026", "carrier_name": "Viettel Post" },
    "observation": {
      "status": "SUCCESS",
      "pickup_id": "PU-ORD2026002-01",
      "order_id": "ORD2026002",
      "pickup_datetime": "09:00 20/09/2026",
      "carrier": "Viettel Post",
      "message": "Đặt lịch lấy hàng thành công cho đơn ORD2026002 với Viettel Post vào lúc 09:00 20/09/2026."
    },
    "latency_ms": 0.01
  },
  {
    "step": 3,
    "action_type": "FINAL_ANSWER",
    "thought": "Đã đủ dữ liệu quan sát từ các bước Tool trước, tổng hợp câu trả lời cuối cùng.",
    "output": "[Mock Agent Response]: Đã xử lý xong yêu cầu cho đơn hàng ORD2026002...",
    "latency_ms": 0.02
  }
]
```

---

## 3. BIÊN BẢN KẾT QUẢ PHÒNG THỦ & DEMO ARENA

Kết quả dưới đây được đo thật khi chạy `python src/app.py --all` (5/5 test case) ở chế độ Offline Mock (chưa gắn API key thật):

- Số câu Prompt Injection bị chặn bởi Input Guardrail: **1 / 1** (TC05 — bị chặn bởi CẢ 2 tầng: Keyword Guardrail khớp từ khóa `"bỏ qua mọi quy tắc"` VÀ Probabilistic Guardrail chấm `risk_level=HIGH, p=0.8`). *(Con số "/3" gốc của template ứng với vòng Live Demo Discord Red Teaming Arena ở Phần 5 — điền tiếp trong buổi học vì cần tấn công trực tiếp, không thể mô phỏng trước.)*
- Số lần kích hoạt phanh Human-in-the-loop (HITL) phê duyệt con người: **1** (TC04 — đề nghị gọi `update_order_status`, hệ thống in `[HITL WARNING]` và `[HITL AUTO-CHECKPOINT]`; khi chạy `python src/app.py --interactive` hệ thống sẽ dừng lại chờ xác nhận `Y/N` thật từ người dùng thay vì tự động duyệt).
- Kích hoạt thành công phanh an toàn trước hành động nhạy cảm: [x] Đã hoàn thành *(xác minh qua TC04, xem log `⚠️ [HITL WARNING]: Tool 'update_order_status' cần xác nhận (hành động nhạy cảm)!`)*.

---

> [!TIP]
> **BƯỚC TIẾP THEO:** Sau khi hoàn thành bảng đánh giá Agentic Fit, học viên chuyển sang Bước 4 (Nội dung trọng tâm):  
> 👉 **[Chuyển sang Bước 4: Thực hành Codelab từng bước (docs/CODELAB.md)](file:///d:/slide%20nhan%20tai%20AI%20VinUni/00_Tan_Binh/Kh%C3%B3a%204/Repo-Lab-k4/Day03/K4-Day03-Lab-Chatbot-vs-ReAct-Agent-MCP/docs/CODELAB.md)**
