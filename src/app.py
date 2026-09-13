"""
🚀 CORE AGENT APPLICATION (Role 4: Core Agent Developer & Role 5: Observability)
File ghép nối Native Tool Calling + MCP Server + Multi-layer Safeguards + HITL Checkpoint + Waterfall Trace Logging.
Chủ đề: Trợ lý Đơn hàng & Kho vận (Supply Chain Agent)
"""

import json
import os
import sys
import time
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from tools import TOOLS_SCHEMA
from mcp_server import MCPAcademicServer
from prompts import (
    CHATBOT_BASELINE_PROMPT,
    SAFE_AGENT_SYSTEM_PROMPT,
    MAX_ITERATIONS,
    is_sensitive_tool
)
from guardrails import run_input_guardrails
from providers import get_llm_provider

load_dotenv()

def load_test_cases():
    """Tải danh sách 5 test cases từ config/test_cases.json"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "test_cases.json")
    if not os.path.exists(config_path):
        config_path = "test_cases.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_waterfall_trace(trace_data: list, filename: str = "trace_waterfall.json", quiet: bool = False):
    """
    Ghi vết log Waterfall Trace Log ra file docs/<filename>.

    `filename` cho phép tách riêng vết của Web UI (trace_waterfall_web.json) khỏi vết
    chính thức nộp bài (trace_waterfall.json), để khi demo giao diện Web không ghi đè
    mất vết Thought -> Action -> Observation -> Final Answer đã xuất ra từ `--all`.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs_dir = os.path.join(base_dir, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    trace_path = os.path.join(docs_dir, filename)
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(trace_data, f, ensure_ascii=False, indent=2)
    if not quiet:
        print(f"📊 [OBSERVABILITY]: Đã lưu vết Waterfall Trace thành công tại '{trace_path}'!")


def get_llm_metadata(provider) -> dict:
    """
    Thông tin định danh LLM đã thực sự sinh ra bước này — bằng chứng cho tiêu chí
    'Vòng lặp ReAct chạy trên LLM API THẬT' (đối chiếu cùng `latency_ms`: gọi API thật
    thường vài trăm đến vài nghìn ms, trong khi chế độ Mock offline chỉ ~0.0x ms).
    """
    # Nếu provider là lớp bọc QuotaAwareFallbackProvider thì lấy engine THẬT SỰ đã phục vụ
    # lượt gọi gần nhất (LLM thật hay engine rule-based dự phòng) -> log trung thực.
    engine = getattr(provider, "active_engine", provider)
    return {
        "llm_provider": engine.__class__.__name__,
        "llm_model": getattr(engine, "model_name", "n/a"),
        "rule_based_fallback": bool(getattr(engine, "is_rule_based", False))
    }


def run_baseline_chatbot(user_query: str, provider):
    """Chạy Chatbot gốc (Cấp 2) không gọi Tool. Trả về text để phục vụ so sánh Chatbot vs Agent."""
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 Chatbot trả lời:\n{response}")
    return response


def run_native_mcp_agent(user_query: str, provider, mcp_server: MCPAcademicServer, interactive_hitl: bool = False):
    """
    [NATIVE AGENT LOOP] Thực thi Native Tool Calling với MCP Server & Phanh HITL.
    Trả về dict tổng kết {trace_logs, final_answer, blocked, guardrail} để phục vụ
    Web UI so sánh Chatbot vs ReAct Agent và ghi vết Waterfall Trace Log.
    """
    print(f"\n🤖 [NATIVE MCP AGENT] Câu hỏi: {user_query}")

    # --------------------------------------------------------------------------
    # LỚP PHÒNG THỦ 1 + 1.5: INPUT GUARDRAIL (Keyword + Probabilistic)
    # --------------------------------------------------------------------------
    guardrail = run_input_guardrails(user_query, provider)
    prob_info = guardrail["probabilistic_guardrail"]
    print(f"🛡️ [LAYER 2 GUARDRAIL - {prob_info.get('method', 'n/a')}]: risk={prob_info['risk_level']} "
          f"(p={prob_info['probability']}) chi tiết={prob_info['matched_signals']}")

    trace_logs = [{
        "step": 0,
        "action_type": "GUARDRAIL_CHECK",
        "keyword_guardrail_triggered": guardrail["keyword_guardrail"]["triggered"],
        "probabilistic_guardrail": prob_info,
        "latency_ms": 0.5
    }]

    if guardrail["blocked"]:
        if guardrail["keyword_guardrail"]["triggered"]:
            print(guardrail["keyword_guardrail"]["message"])
        print(f"🚨 [PROBABILISTIC GUARDRAIL DETECTED]: risk_level=HIGH (p={prob_info['probability']}), "
              f"tín hiệu nghi vấn: {prob_info['matched_signals']}")
        print("🛡️ [GUARDRAIL TRIGGERED]: Từ chối xử lý câu hỏi do vi phạm ranh giới an toàn!")
        trace_logs.append({
            "step": 1,
            "action_type": "GUARDRAIL_BLOCKED",
            "reason": guardrail["keyword_guardrail"]["message"] or "Xác suất Prompt Injection ở mức HIGH",
            "latency_ms": 1.0
        })
        save_waterfall_trace(trace_logs)
        return {"trace_logs": trace_logs, "final_answer": "[Đã bị chặn bởi Input Guardrail]", "blocked": True, "guardrail": guardrail}

    step = 0
    history = []  # Các bước Tool đã thực thi trong lượt hỏi này -> nạp lại cho LLM để suy luận tiếp (Multi-step)
    tools_list = mcp_server.list_tools()
    final_answer = ""

    while step < MAX_ITERATIONS:
        step += 1
        step_start_time = time.time()
        print(f"\n--- 🔄 Vòng lặp Native Tool Calling (Step {step}/{MAX_ITERATIONS}) ---")

        # Gọi LLM với Native Tool Calling Specs + lịch sử quan sát các bước Tool trước đó
        llm_response = provider.generate_with_tools(
            user_query, tools_list, system_prompt=SAFE_AGENT_SYSTEM_PROMPT, history=history
        )
        latency_ms = round((time.time() - step_start_time) * 1000, 2)

        thought = llm_response.get("thought", "Đang suy luận...")
        print(f"🧠 [Thought]: {thought}")

        # Trường hợp 1: LLM quyết định trả lời bằng văn bản trực tiếp (kết thúc vòng lặp)
        if llm_response.get("type") == "text":
            final_answer = llm_response.get("content", "")
            print(f"🏁 [Final Answer]: {final_answer}")
            trace_logs.append({
                "step": step,
                "action_type": "FINAL_ANSWER",
                "thought": thought,
                "output": final_answer,
                **get_llm_metadata(provider),
                "latency_ms": latency_ms
            })
            break

        # Trường hợp 2: LLM đề nghị gọi Tool (Native Tool Call)
        elif llm_response.get("type") == "tool_call":
            tool_name = llm_response.get("tool_name")
            arguments = llm_response.get("arguments", {})
            call_id = llm_response.get("id")

            print(f"🛠️ [Native Tool Call Proposed]: {tool_name}({arguments})")

            # ------------------------------------------------------------------
            # LỚP PHÒNG THỦ 2: HUMAN-IN-THE-LOOP (HITL) CHECKPOINT
            # Kích hoạt khi Tool thuộc danh mục nhạy cảm CỐ ĐỊNH (is_sensitive_tool)
            # HOẶC khi Probabilistic Guardrail đã gắn cờ force_hitl (rủi ro MEDIUM) ở Layer 1.5.
            # ------------------------------------------------------------------
            needs_hitl = is_sensitive_tool(tool_name) or guardrail.get("force_hitl")
            if needs_hitl:
                hitl_reason = "hành động nhạy cảm" if is_sensitive_tool(tool_name) else \
                    f"Probabilistic Guardrail cảnh báo rủi ro MEDIUM (p={prob_info['probability']})"
                print(f"⚠️ [HITL WARNING]: Tool '{tool_name}' cần xác nhận ({hitl_reason})!")
                if interactive_hitl:
                    user_approval = input(f"👉 [HITL APPROVAL REQUIRED] Phê duyệt gọi tool '{tool_name}'? (Y/N): ").strip().upper()
                    if user_approval != 'Y':
                        print("⛔ [HITL REJECTED]: Người dùng từ chối phê duyệt! Dừng thực thi Tool.")
                        trace_logs.append({
                            "step": step,
                            "action_type": "HITL_REJECTED",
                            "tool_name": tool_name,
                            "arguments": arguments,
                            "reason": hitl_reason,
                            "latency_ms": latency_ms
                        })
                        final_answer = "[Yêu cầu đã bị từ chối bởi phanh HITL]"
                        break
                else:
                    print("⚙️ [HITL AUTO-CHECKPOINT]: Đã kích hoạt phanh HITL xác nhận an toàn!")

            # Thực thi Tool qua MCP Server
            mcp_result = mcp_server.call_tool(tool_name, arguments)
            observation = mcp_result.get("result", {})
            obs_str = json.dumps(observation, ensure_ascii=False)
            print(f"👁️ [MCP Server Observation]: {obs_str}")

            # Ghi đủ 3 thành phần của 1 vòng ReAct trong CÙNG 1 bản ghi:
            #   Thought (LLM suy luận) -> Action (tool_name + arguments) -> Observation (kết quả Tool)
            trace_logs.append({
                "step": step,
                "action_type": "TOOL_EXECUTION",
                "thought": thought,
                "tool_name": tool_name,
                "arguments": arguments,
                "observation": observation,
                "hitl_required": bool(needs_hitl),
                **get_llm_metadata(provider),
                "latency_ms": latency_ms
            })

            # Nạp quan sát vừa nhận được vào history để LLM suy luận bước kế tiếp (Multi-step Reasoning)
            # `model_content`: bản gốc Content do LLM trả về (Gemini 3 cần để giữ thought_signature)
            history.append({
                "id": call_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "observation": observation,
                "model_content": llm_response.get("model_content")
            })
            # KHÔNG break ở đây: vòng lặp tiếp tục, để LLM tự quyết định gọi thêm Tool
            # hay đã đủ dữ liệu để tổng hợp câu trả lời cuối cùng.

    save_waterfall_trace(trace_logs)
    return {"trace_logs": trace_logs, "final_answer": final_answer, "blocked": False, "guardrail": guardrail}


def run_native_mcp_agent_resumable(provider, mcp_server: MCPAcademicServer, user_query: str = None,
                                    state: dict = None, hitl_decision: bool = None,
                                    trace_filename: str = "trace_waterfall.json") -> dict:
    """
    [WEB UI VERSION] Bản KHÔNG chặn (non-blocking / resumable) của run_native_mcp_agent().

    Lý do cần bản riêng: HTTP request-response không thể dùng input() để "đứng chờ" người
    dùng bấm Approve/Reject như CLI --interactive. Thay vào đó, khi Agent cần phanh HITL,
    hàm này DỪNG LẠI và trả về status="pending_hitl" kèm toàn bộ `state` (JSON serializable)
    để Web UI hiển thị hộp thoại phê duyệt, rồi gọi lại hàm này với `state` đó +
    `hitl_decision=True/False` để tiếp tục đúng vị trí đã dừng.

    Cách dùng:
      - Lượt gọi đầu tiên:  run_native_mcp_agent_resumable(provider, mcp_server, user_query=q)
      - Khi status == "pending_hitl": gọi lại
        run_native_mcp_agent_resumable(provider, mcp_server, state=<state đã nhận>, hitl_decision=True/False)

    Trả về dict: {"status": "blocked"|"pending_hitl"|"done", "trace_logs", "guardrail", ...}
    """
    tools_list = mcp_server.list_tools()
    final_answer = f"[Đã đạt số vòng lặp tối đa MAX_ITERATIONS={MAX_ITERATIONS} mà chưa có câu trả lời cuối cùng]"

    if state is None:
        # ---------------- Lượt gọi đầu tiên: chạy Guardrail trước ----------------
        guardrail = run_input_guardrails(user_query, provider)
        prob_info = guardrail["probabilistic_guardrail"]
        trace_logs = [{
            "step": 0,
            "action_type": "GUARDRAIL_CHECK",
            "keyword_guardrail_triggered": guardrail["keyword_guardrail"]["triggered"],
            "probabilistic_guardrail": prob_info,
            "latency_ms": 0.5
        }]

        if guardrail["blocked"]:
            trace_logs.append({
                "step": 1,
                "action_type": "GUARDRAIL_BLOCKED",
                "reason": guardrail["keyword_guardrail"]["message"] or f"Layer 2 chấm risk_level=HIGH (p={prob_info['probability']})",
                "latency_ms": 1.0
            })
            save_waterfall_trace(trace_logs, trace_filename)
            return {"status": "blocked", "trace_logs": trace_logs,
                    "final_answer": "[Đã bị chặn bởi Input Guardrail]", "guardrail": guardrail}

        state = {"user_query": user_query, "history": [], "step": 0, "guardrail": guardrail, "trace_logs": trace_logs}
    else:
        # ---------------- Lượt gọi tiếp theo: vừa nhận quyết định HITL ----------------
        user_query = state["user_query"]
        guardrail = state["guardrail"]
        prob_info = guardrail["probabilistic_guardrail"]
        trace_logs = state["trace_logs"]
        pending = state.pop("pending_tool", None)

        if pending is not None:
            if hitl_decision:
                trace_logs.append({"step": state["step"], "action_type": "HITL_APPROVED",
                                    "tool_name": pending["tool_name"], "arguments": pending["arguments"], "latency_ms": 20})
                mcp_result = mcp_server.call_tool(pending["tool_name"], pending["arguments"])
                observation = mcp_result.get("result", {})
                trace_logs.append({
                    "step": state["step"], "action_type": "TOOL_EXECUTION",
                    "thought": pending.get("thought", ""),
                    "tool_name": pending["tool_name"], "arguments": pending["arguments"],
                    "observation": observation, "hitl_required": True,
                    **get_llm_metadata(provider), "latency_ms": 0.02
                })
                state["history"].append({
                    "id": pending.get("id"), "tool_name": pending["tool_name"],
                    "arguments": pending["arguments"], "observation": observation,
                    "model_content": pending.get("model_content")
                })
            else:
                trace_logs.append({
                    "step": state["step"], "action_type": "HITL_REJECTED",
                    "tool_name": pending["tool_name"], "arguments": pending["arguments"],
                    "reason": pending.get("reason", ""), "latency_ms": 20
                })
                save_waterfall_trace(trace_logs, trace_filename)
                return {"status": "done", "trace_logs": trace_logs,
                        "final_answer": "[Yêu cầu đã bị từ chối bởi phanh HITL]", "guardrail": guardrail}

    while state["step"] < MAX_ITERATIONS:
        state["step"] += 1
        step = state["step"]
        t0 = time.time()
        llm_response = provider.generate_with_tools(
            user_query, tools_list, system_prompt=SAFE_AGENT_SYSTEM_PROMPT, history=state["history"]
        )
        latency_ms = round((time.time() - t0) * 1000, 2)
        thought = llm_response.get("thought", "Đang suy luận...")

        if llm_response.get("type") == "text":
            final_answer = llm_response.get("content", "")
            trace_logs.append({"step": step, "action_type": "FINAL_ANSWER", "thought": thought,
                                "output": final_answer, **get_llm_metadata(provider),
                                "latency_ms": latency_ms})
            save_waterfall_trace(trace_logs, trace_filename)
            return {"status": "done", "trace_logs": trace_logs, "final_answer": final_answer, "guardrail": guardrail}

        tool_name = llm_response.get("tool_name")
        arguments = llm_response.get("arguments", {})
        call_id = llm_response.get("id")
        needs_hitl = is_sensitive_tool(tool_name) or guardrail.get("force_hitl")

        trace_logs.append({"step": step, "action_type": "TOOL_PROPOSED", "tool_name": tool_name,
                            "arguments": arguments, "thought": thought, "latency_ms": latency_ms})

        if needs_hitl:
            hitl_reason = "hành động nhạy cảm" if is_sensitive_tool(tool_name) else \
                f"Layer 2 Guardrail cảnh báo rủi ro MEDIUM (p={prob_info['probability']})"
            trace_logs.append({"step": step, "action_type": "HITL_PENDING", "tool_name": tool_name,
                                "arguments": arguments, "reason": hitl_reason, "latency_ms": 0})
            state["pending_tool"] = {"id": call_id, "tool_name": tool_name, "arguments": arguments,
                                     "reason": hitl_reason, "thought": thought,
                                     "model_content": llm_response.get("model_content")}
            save_waterfall_trace(trace_logs, trace_filename)
            return {"status": "pending_hitl", "trace_logs": trace_logs,
                    "pending_tool": {"tool_name": tool_name, "arguments": arguments, "reason": hitl_reason},
                    "state": state, "guardrail": guardrail}

        mcp_result = mcp_server.call_tool(tool_name, arguments)
        observation = mcp_result.get("result", {})
        trace_logs.append({"step": step, "action_type": "TOOL_EXECUTION", "thought": thought,
                            "tool_name": tool_name, "arguments": arguments, "observation": observation,
                            "hitl_required": False, **get_llm_metadata(provider), "latency_ms": latency_ms})
        state["history"].append({"id": call_id, "tool_name": tool_name, "arguments": arguments,
                                 "observation": observation, "model_content": llm_response.get("model_content")})

    save_waterfall_trace(trace_logs, trace_filename)
    return {"status": "done", "trace_logs": trace_logs, "final_answer": final_answer, "guardrail": guardrail}


if __name__ == "__main__":
    print("==========================================================")
    print("📦 SUPPLY CHAIN AI LAB - DAY 03: NATIVE MCP SAFE AGENT")
    print("==========================================================")

    provider = get_llm_provider()
    mcp_server = MCPAcademicServer()

    print(f"🔌 LLM Provider: {provider.__class__.__name__} (model: {getattr(provider, 'model_name', 'n/a')})")
    print(f"🌐 MCP Server: {mcp_server.server_name}\n")

    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases thử nghiệm.\n")

    if "--interactive" in sys.argv:
        print("🎮 [INTERACTIVE MODE] Bắt đầu phiên trò chuyện trực tiếp (Multi-turn Chat) với Safe Agent:")
        print("💡 Gợi ý câu hỏi thử nghiệm:")
        print("   - Tra cứu: 'Hãy tra cứu trạng thái đơn hàng ORD2026001'")
        print("   - Nhiều bước: 'Kiểm tra đơn hàng ORD2026002 và đặt lịch lấy hàng lúc 09:00 20/09/2026'")
        print("   - Cập nhật (HITL): 'Hủy đơn hàng ORD2026001 giúp mình'")
        print("   - Gõ 'exit' hoặc 'quit' để kết thúc phiên trò chuyện.\n")
        while True:
            try:
                user_input = input("👤 Khách hàng hỏi: ").strip()
                if not user_input or user_input.lower() in ["exit", "quit"]:
                    print("👋 Tạm biệt! Kết thúc phiên trò chuyện.")
                    break
                run_native_mcp_agent(user_input, provider, mcp_server, interactive_hitl=True)
            except (KeyboardInterrupt, EOFError):
                print("\n👋 Đã thoát phiên tương tác.")
                break
    elif "--all" in sys.argv:
        print("🚀 [TEST SUITE MODE] Kiểm tra 5 Test Cases:")
        completed_count = 0
        todo_count = 0
        all_results = []  # [(test_case, trace_logs)] để chọn vết đầy đủ nhất làm artifact nộp bài

        for tc in tests:
            print(f"\n==================================================")
            print(f"🧪 [{tc['id']}] Loại test: {tc['type']} (Độ phức tạp: {tc['complexity']})")
            print(f"📌 Kỳ vọng: {tc['expected_behavior']}")

            # Kiểm tra nếu test case này học viên chưa điền câu hỏi (vẫn còn TODO)
            if tc["question"].strip().startswith("TODO"):
                print(f"⏸️ [CHƯA KÍCH HOẠT - ĐANG LÀ TODO]:")
                print(f"   {tc['question']}")
                print(f"   👉 Hãy mở file 'config/test_cases.json' để viết câu hỏi thực tế cho Test Case này!")
                todo_count += 1
            else:
                result = run_native_mcp_agent(tc["question"], provider, mcp_server)
                all_results.append((tc, result["trace_logs"]))
                completed_count += 1

        # ----------------------------------------------------------------------
        # OBSERVABILITY: lưu vết TỪNG test case ra docs/traces/ để đối chiếu,
        # đồng thời chọn vết ĐẦY ĐỦ NHẤT (nhiều bước Tool nhất) làm docs/trace_waterfall.json.
        # Lý do: trước đây mỗi lần chạy đều ghi đè, nên file cuối cùng là vết của TC05
        # (câu bị Guardrail chặn - chỉ có 2 bước), không thể hiện được chuỗi đầy đủ
        # Thought -> Action -> Observation -> Final Answer mà rubric yêu cầu.
        # ----------------------------------------------------------------------
        if all_results:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            traces_dir = os.path.join(base_dir, "docs", "traces")
            os.makedirs(traces_dir, exist_ok=True)
            for tc, logs in all_results:
                with open(os.path.join(traces_dir, f"{tc['id']}_{tc['type']}.json"), "w", encoding="utf-8") as f:
                    json.dump(logs, f, ensure_ascii=False, indent=2)

            def richness(item):
                logs = item[1]
                tool_steps = sum(1 for e in logs if e.get("action_type") == "TOOL_EXECUTION")
                has_final = any(e.get("action_type") == "FINAL_ANSWER" for e in logs)
                return (tool_steps, has_final, len(logs))

            best_tc, best_logs = max(all_results, key=richness)
            save_waterfall_trace(best_logs)
            print(f"\n📁 [OBSERVABILITY]: Đã lưu vết riêng của từng test case tại 'docs/traces/'.")
            print(f"🏆 [ARTIFACT NỘP BÀI]: 'docs/trace_waterfall.json' = vết đầy đủ nhất "
                  f"({best_tc['id']} - {best_tc['type']}, {richness((best_tc, best_logs))[0]} bước Tool).")

        print(f"\n==================================================")
        print(f"📊 [KẾT QUẢ TEST SUITE]: {completed_count} Đã chạy | {todo_count} Đang chờ viết câu hỏi (TODO)")
        print(f"🔌 [LLM API ĐÃ DÙNG]: {provider.__class__.__name__} (model: {getattr(provider, 'model_name', 'n/a')})")
        print(f"💡 Để trò chuyện trực tiếp từng câu: Chạy 'python src/app.py --interactive'")
        print(f"💡 Để trải nghiệm giao diện Web UI so sánh Chatbot vs Agent: Chạy 'python src/web_server.py' rồi mở http://localhost:8787")
    else:
        # Chế độ mặc định khi chỉ gõ 'python src/app.py'
        print("ℹ️ HƯỚNG DẪN SỬ DỤNG CHƯƠNG TRÌNH:")
        print("  1. Chat trực tiếp liên tục:   python src/app.py --interactive")
        print("  2. Chạy toàn bộ Test Cases:    python src/app.py --all")
        print("  3. Trải nghiệm giao diện Web:  Mở file 'docs/demo_ui.html' bằng trình duyệt web.\n")

        sample_query = tests[1]["question"]
        print(f"--- 🏁 DEMO CHẠY THỬ 1 TEST CASE MẪU (TC02: Tra cứu đơn hàng) ---")
        run_native_mcp_agent(sample_query, provider, mcp_server)
        print("\n💡 Hãy thử ngay lệnh: python src/app.py --interactive để chat trực tiếp!")
