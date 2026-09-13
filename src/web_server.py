"""
🌐 LOCAL WEB BACKEND cho docs/demo_ui.html (So sánh Chatbot Baseline vs ReAct MCP Agent)

TẠI SAO CẦN FILE NÀY?
Trước đây docs/demo_ui.html tự mô phỏng toàn bộ logic (Guardrail, Tool execution, câu trả
lời cuối cùng) bằng JavaScript viết tay/hardcode cho từng loại câu hỏi -> đây chính là lý do
kết quả "ảo giác"/không nhất quán mà học viên phản hồi: đó không phải là suy luận thật, mà là
kịch bản lập trình cứng giả lập, và trạng thái MOCK_DB dùng chung trong JS dễ bị lệch pha.

File này chạy MỘT backend Python cực nhẹ (chỉ dùng thư viện chuẩn `http.server`, không cần
cài Flask) để:
  1. Phục vụ chính file docs/demo_ui.html qua HTTP (http://localhost:8787) — bắt buộc phải
     mở qua URL này (KHÔNG mở trực tiếp bằng File > Open trong trình duyệt), vì trình duyệt
     chỉ cho phép JavaScript gọi API cùng origin (same-origin) khi trang được phục vụ qua HTTP.
  2. Cung cấp 2 API thực thi bằng Python, TÁI SỬ DỤNG chính xác logic đã kiểm chứng trong
     src/app.py, src/guardrails.py, src/providers.py, src/tools.py — nghĩa là:
       - /api/baseline : gọi THẬT provider.generate() (Gemini nếu đã cấu hình .env) — không Tool,
         không Guardrail — đúng bản chất 1 Chatbot LLM thuần.
       - /api/agent     : chạy THẬT run_native_mcp_agent_resumable() — 2 tầng Guardrail (Layer 1
         Keyword + Layer 2 LLM Semantic Classifier), Native Tool Calling qua MCP Server, và
         phanh HITL thật (tạm dừng chờ phê duyệt qua /api/agent/resume).
  3. Không còn bất kỳ đoạn hardcode "nếu câu hỏi chứa X thì trả lời Y" nào trong JavaScript nữa
     — toàn bộ quyết định đến từ đúng 1 nguồn duy nhất (Single Source of Truth): code Python
     phía server, giống hệt khi chạy `python src/app.py --interactive`.

CHẠY:
    pip install -r requirements.txt
    python src/web_server.py
    -> Mở trình duyệt tại: http://localhost:8787
"""

import copy
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from mcp_server import MCPAcademicServer
from prompts import CHATBOT_BASELINE_PROMPT
from providers import get_llm_provider
import tools as tools_module
from app import run_native_mcp_agent_resumable, save_waterfall_trace

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_HTML_PATH = os.path.join(BASE_DIR, "docs", "demo_ui.html")

# Snapshot dữ liệu gốc để hỗ trợ API /api/reset (đưa MOCK_DATABASE về trạng thái ban đầu
# giữa các lần demo, tránh nhầm lẫn do 1 phiên demo trước đã hủy/đổi trạng thái đơn hàng).
_PRISTINE_DB = copy.deepcopy(tools_module.MOCK_DATABASE)

provider = get_llm_provider()
mcp_server = MCPAcademicServer()

print("==========================================================")
print("🌐 SUPPLY CHAIN AGENT — WEB UI BACKEND (docs/demo_ui.html)")
print("==========================================================")
print(f"🔌 LLM Provider: {provider.__class__.__name__} (model: {getattr(provider, 'model_name', 'n/a')})")
if getattr(provider, "is_rule_based", False):
    print("⚠️  Đang chạy ở chế độ MOCK OFFLINE (không có API Key thật).")
    print("    -> Chatbot Baseline sẽ trả lời bằng câu mô phỏng cố định, KHÔNG phải LLM thật.")
    print("    -> Layer 2 Guardrail sẽ tự rơi về fallback từ khóa (heuristic_keyword_fallback).")
    print("    -> Hãy điền GEMINI_API_KEY thật + LLM_PROVIDER=gemini trong file .env để bật LLM thật.")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[web_server] {self.address_string()} - {fmt % args}\n")

    # ---------------------------------------------------------------- helpers
    def _send_json(self, payload: dict, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_text: str):
        body = html_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    # ---------------------------------------------------------------- routes
    def do_GET(self):
        if self.path in ("/", "/demo_ui.html", "/index.html"):
            try:
                with open(DEMO_HTML_PATH, "r", encoding="utf-8") as f:
                    self._send_html(f.read())
            except FileNotFoundError:
                self._send_json({"error": f"Không tìm thấy {DEMO_HTML_PATH}"}, status=404)
        elif self.path == "/api/info":
            engine = getattr(provider, "active_engine", provider)
            self._send_json({
                "provider": engine.__class__.__name__,
                "model": getattr(engine, "model_name", "n/a"),
                "llm_provider_env": os.getenv("LLM_PROVIDER", "mock"),
                "rule_based_fallback": bool(getattr(provider, "is_rule_based_now", False)
                                            or getattr(provider, "is_rule_based", False)),
                "fallback_cooldown_seconds": (provider.remaining_cooldown_seconds()
                                              if hasattr(provider, "remaining_cooldown_seconds") else 0),
            })
        elif self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        else:
            self._send_json({"error": "Not found"}, status=404)

    def do_POST(self):
        try:
            body = self._read_json_body()
        except Exception as e:
            self._send_json({"error": f"Body JSON không hợp lệ: {e}"}, status=400)
            return

        try:
            if self.path == "/api/baseline":
                self._send_json(self._handle_baseline(body))
            elif self.path == "/api/agent":
                self._send_json(self._handle_agent(body))
            elif self.path == "/api/agent/resume":
                self._send_json(self._handle_agent_resume(body))
            elif self.path == "/api/reset":
                tools_module.MOCK_DATABASE.clear()
                tools_module.MOCK_DATABASE.update(copy.deepcopy(_PRISTINE_DB))
                self._send_json({"status": "ok", "message": "Đã khôi phục MOCK_DATABASE về trạng thái gốc."})
            else:
                self._send_json({"error": "Not found"}, status=404)
        except Exception as e:
            self._send_json({"error": f"[SERVER EXCEPTION] {type(e).__name__}: {e}"}, status=500)

    # ---------------------------------------------------------------- handlers
    def _handle_baseline(self, body: dict) -> dict:
        """
        Chatbot Baseline THẬT: gọi provider.generate() trực tiếp — KHÔNG Tool, KHÔNG Guardrail,
        KHÔNG dữ liệu thời gian thực. Nếu LLM_PROVIDER=gemini + có API Key thật, đây là 1 lượt
        gọi Gemini thật; nếu không, provider tự động là MockOfflineProvider (câu trả lời mô phỏng
        rõ ràng được đánh dấu "[Mock Chatbot Response]", không giả vờ là thật).
        """
        query = (body.get("query") or "").strip()
        if not query:
            return {"error": "Thiếu 'query'"}

        t0 = time.time()
        reply = provider.generate(query, system_prompt=CHATBOT_BASELINE_PROMPT)
        latency_ms = round((time.time() - t0) * 1000, 2)

        return {
            "reply": reply,
            "trace": [{
                "step": 1,
                "action_type": "LLM_CALL",
                "rule_based_fallback": bool(getattr(getattr(provider, "active_engine", provider), "is_rule_based", False)),
                "note": "Chatbot Baseline: gọi LLM trực tiếp — KHÔNG Tool, KHÔNG Guardrail, KHÔNG dữ liệu thời gian thực.",
                "model": getattr(getattr(provider, "active_engine", provider), "model_name", "n/a"),
                "latency_ms": latency_ms
            }]
        }

    def _handle_agent(self, body: dict) -> dict:
        query = (body.get("query") or "").strip()
        if not query:
            return {"error": "Thiếu 'query'"}
        # Ghi vết ra file RIÊNG (trace_waterfall_web.json) để việc demo Web UI không ghi đè
        # mất 'docs/trace_waterfall.json' — artifact chính thức xuất ra từ 'python src/app.py --all'.
        return run_native_mcp_agent_resumable(provider, mcp_server, user_query=query,
                                              trace_filename="trace_waterfall_web.json")

    def _handle_agent_resume(self, body: dict) -> dict:
        state = body.get("state")
        approved = bool(body.get("approved"))
        if not state:
            return {"error": "Thiếu 'state' (phải truyền lại state nhận được từ /api/agent lúc status=pending_hitl)"}
        return run_native_mcp_agent_resumable(provider, mcp_server, state=state, hitl_decision=approved,
                                              trace_filename="trace_waterfall_web.json")


if __name__ == "__main__":
    port = int(os.getenv("WEB_UI_PORT", "8787"))
    server = ThreadingHTTPServer(("localhost", port), Handler)
    print(f"🌐 MCP Server (nội bộ): {mcp_server.server_name}")
    print(f"🚀 Đang chạy tại: http://localhost:{port}")
    print("💡 Mở URL trên bằng trình duyệt để dùng giao diện so sánh Chatbot vs Agent.")
    print("   (Nhấn Ctrl+C để dừng server)\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Đã dừng Web Server.")
        server.shutdown()
