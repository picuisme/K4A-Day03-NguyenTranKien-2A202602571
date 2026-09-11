# 📊 BÁO CÁO AGENTIC FIT SCORING MATRIX & TRACE EVALUATION (BƯỚC 3)

> **Họ và Tên Học viên:** [Điền Họ và Tên]  
> **Mã Sinh Viên / Mã Học viên:** [Điền MSSV]  
> **Chủ đề Lựa chọn:** [Điền tên chủ đề đã chọn từ docs/DANH_SACH_DE_TAI.md]  

---

## 1. BẢNG CHẤM ĐIỂM AGENTIC FIT SCORING MATRIX

| Tiêu chí Đánh giá | Mức độ (1 - 5) | Giải trình chi tiết lý do chọn điểm |
| :--- | :---: | :--- |
| **1. Multi-step Reasoning** | / 5 | Bài toán có yêu cầu chia nhỏ nhiều bước suy luận nối tiếp nhau không? |
| **2. Tool Interaction** | / 5 | Hệ thống có cần kết nối với MCP Server / Cơ sở dữ liệu bên ngoài không? |
| **3. Dynamic Decision** | / 5 | Bước tiếp theo có phụ thuộc vào kết quả quan sát bước trước không? |
| **4. Long Horizon Goal** | / 5 | Hệ thống có phải giữ mục tiêu xuyên suốt qua nhiều lượt xử lý không? |
| **TỔNG ĐIỂM AGENTIC FIT** | **/ 20** | *Nếu tổng điểm > 12/20: Bài toán rất phù hợp triển khai Agentic System.* |

---

## 2. NHẬT KÝ WATERFALL TRACE LOG

Sau khi thực thi mã nguồn `python src/app.py`, hãy mở file `docs/trace_waterfall.json` dán tóm tắt 1 lượt Trace hoàn chỉnh dưới đây:

```json
[
  {
    "step": 1,
    "action_type": "TOOL_EXECUTION",
    "tool_name": "academic_query",
    "arguments": {
      "student_id": "SV2026001"
    },
    "observation": {
      "status": "SUCCESS",
      "student_id": "SV2026001",
      "data": {
        "full_name": "Nguyễn Văn An",
        "gpa": 3.85
      }
    },
    "latency_ms": 120.5
  }
]
```

---

## 3. BIÊN BẢN KẾT QUẢ PHÒNG THỦ & DEMO ARENA

- Số câu Prompt Injection bị chặn bởi Input Guardrail: ___ / 3
- Số lần kích hoạt phanh Human-in-the-loop (HITL) phê duyệt con người: ___
- Kích hoạt thành công phanh an toàn trước hành động nhạy cảm: [ ] Đã hoàn thành

---

> [!TIP]
> **BƯỚC TIẾP THEO:** Sau khi hoàn thành bảng đánh giá Agentic Fit, học viên chuyển sang Bước 4 (Nội dung trọng tâm):  
> 👉 **[Chuyển sang Bước 4: Thực hành Codelab từng bước (docs/CODELAB.md)](file:///d:/slide%20nhan%20tai%20AI%20VinUni/00_Tan_Binh/Kh%C3%B3a%204/Repo-Lab-k4/Day03/K4-Day03-Lab-Chatbot-vs-ReAct-Agent-MCP/docs/CODELAB.md)**
