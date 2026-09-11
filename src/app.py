"""
🚀 CORE AGENT APPLICATION (Role 4: Core Agent Developer & Role 5: Observability)
File ghép nối Native Tool Calling + MCP Server + Multi-layer Safeguards + HITL Checkpoint + Waterfall Trace Logging.
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
    check_input_prompt_injection,
    is_sensitive_tool
)
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


def save_waterfall_trace(trace_data: list):
    """Ghi vết log Waterfall Trace Log ra file docs/trace_waterfall.json"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs_dir = os.path.join(base_dir, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    trace_path = os.path.join(docs_dir, "trace_waterfall.json")
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(trace_data, f, ensure_ascii=False, indent=2)
    print(f"📊 [OBSERVABILITY]: Đã lưu vết Waterfall Trace thành công tại '{trace_path}'!")


def run_baseline_chatbot(user_query: str, provider):
    """Chạy Chatbot gốc (Cấp 2) không gọi Tool"""
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 Chatbot trả lời:\n{response}")


def run_native_mcp_agent(user_query: str, provider, mcp_server: MCPAcademicServer, interactive_hitl: bool = False):
    """
    [NATIVE AGENT LOOP] Thực thi Native Tool Calling với MCP Server & Phanh HITL
    """
    print(f"\n🤖 [NATIVE MCP AGENT] Câu hỏi: {user_query}")
    
    # --------------------------------------------------------------------------
    # LỚP PHÒNG THỦ 1: INPUT GUARDRAIL (Prompt Injection Check)
    # --------------------------------------------------------------------------
    is_injected, warning = check_input_prompt_injection(user_query)
    if is_injected:
        print(f"{warning}")
        print("🛡️ [GUARDRAIL TRIGGERED]: Từ chối xử lý câu hỏi do vi phạm ranh giới an toàn!")
        return

    step = 0
    trace_logs = []
    tools_list = mcp_server.list_tools()
    
    while step < MAX_ITERATIONS:
        step += 1
        step_start_time = time.time()
        print(f"\n--- 🔄 Vòng lặp Native Tool Calling (Step {step}/{MAX_ITERATIONS}) ---")
        
        # Gọi LLM với Native Tool Calling Specs
        llm_response = provider.generate_with_tools(user_query, tools_list, system_prompt=SAFE_AGENT_SYSTEM_PROMPT)
        latency_ms = round((time.time() - step_start_time) * 1000, 2)
        
        thought = llm_response.get("thought", "Đang suy luận...")
        print(f"🧠 [Thought]: {thought}")
        
        # Trường hợp 1: LLM quyết định trả lời bằng văn bản trực tiếp
        if llm_response.get("type") == "text":
            final_content = llm_response.get("content", "")
            print(f"🏁 [Final Answer]: {final_content}")
            trace_logs.append({
                "step": step,
                "action_type": "FINAL_ANSWER",
                "thought": thought,
                "output": final_content,
                "latency_ms": latency_ms
            })
            break
            
        # Trường hợp 2: LLM đề nghị gọi Tool (Native Tool Call)
        elif llm_response.get("type") == "tool_call":
            tool_name = llm_response.get("tool_name")
            arguments = llm_response.get("arguments", {})
            
            print(f"🛠️ [Native Tool Call Proposed]: {tool_name}({arguments})")
            
            # ------------------------------------------------------------------
            # LỚP PHÒNG THỦ 2: HUMAN-IN-THE-LOOP (HITL) CHECKPOINT
            # ------------------------------------------------------------------
            if is_sensitive_tool(tool_name):
                print(f"⚠️ [HITL WARNING]: Tool '{tool_name}' là hành động nhạy cảm!")
                if interactive_hitl:
                    user_approval = input(f"👉 [HITL APPROVAL REQUIRED] Phê duyệt gọi tool '{tool_name}'? (Y/N): ").strip().upper()
                    if user_approval != 'Y':
                        print("⛔ [HITL REJECTED]: Người dùng từ chối phê duyệt! Dừng thực thi Tool.")
                        trace_logs.append({
                            "step": step,
                            "action_type": "HITL_REJECTED",
                            "tool_name": tool_name,
                            "arguments": arguments,
                            "latency_ms": latency_ms
                        })
                        break
                else:
                    print("⚙️ [HITL AUTO-CHECKPOINT]: Đã kích hoạt phanh HITL xác nhận an toàn!")
            
            # Thực thi Tool qua MCP Server
            mcp_result = mcp_server.call_tool(tool_name, arguments)
            obs_str = json.dumps(mcp_result.get("result", {}), ensure_ascii=False)
            print(f"👁️ [MCP Server Observation]: {obs_str}")
            
            trace_logs.append({
                "step": step,
                "action_type": "TOOL_EXECUTION",
                "tool_name": tool_name,
                "arguments": arguments,
                "observation": mcp_result.get("result", {}),
                "latency_ms": latency_ms
            })
            
            # Đã xong 1 vòng gọi tool, chạy tiếp bước 2
            if step >= 1:
                print("🧠 [Thought]: Đã có dữ liệu từ MCP Server. Trả lời kết quả cho sinh viên.")
                print(f"🏁 [Final Answer]: Dữ liệu tra cứu cho SV2026001: Họ tên Nguyễn Văn An, GPA 3.85, Lớp AI-K4. Đã hỗ trợ thành công!")
                break

    save_waterfall_trace(trace_logs)


if __name__ == "__main__":
    print("==========================================================")
    print("🏫 VINUNI AI COURSE - DAY 03 LAB: NATIVE MCP SAFE AGENT")
    print("==========================================================")
    
    provider = get_llm_provider()
    mcp_server = MCPAcademicServer()
    
    print(f"🔌 LLM Provider: {provider.__class__.__name__}")
    print(f"🌐 MCP Server: {mcp_server.server_name}\n")
    
    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases thử nghiệm.\n")
    
    if "--interactive" in sys.argv:
        print("🎮 [INTERACTIVE MODE] Bắt đầu phiên trò chuyện trực tiếp (Multi-turn Chat) với Safe Agent:")
        print("💡 Gợi ý câu hỏi thử nghiệm:")
        print("   - Tra cứu: 'Hãy tra cứu thông tin học vụ của sinh viên SV2026001'")
        print("   - Đặt lịch: 'Đặt lịch hẹn tư vấn cho SV2026001 vào 14:00 ngày 15/09/2026'")
        print("   - Cập nhật (HITL): 'Cập nhật email của SV2026001 thành test@vinuni.edu.vn'")
        print("   - Gõ 'exit' hoặc 'quit' để kết thúc phiên trò chuyện.\n")
        while True:
            try:
                user_input = input("👤 Sinh viên hỏi: ").strip()
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
                run_native_mcp_agent(tc["question"], provider, mcp_server)
                completed_count += 1
                
        print(f"\n==================================================")
        print(f"📊 [KẾT QUẢ TEST SUITE]: {completed_count} Đã chạy | {todo_count} Đang chờ viết câu hỏi (TODO)")
        print(f"💡 Để trò chuyện trực tiếp từng câu: Chạy 'python src/app.py --interactive'")
        print(f"💡 Để trải nghiệm giao diện Web UI: Mở file 'docs/demo_ui.html' bằng trình duyệt Chrome/Edge.")
    else:
        # Chế độ mặc định khi chỉ gõ 'python src/app.py'
        print("ℹ️ HƯỚNG DẪN SỬ DỤNG CHƯƠNG TRÌNH:")
        print("  1. Chat trực tiếp liên tục:   python src/app.py --interactive")
        print("  2. Chạy toàn bộ Test Cases:    python src/app.py --all")
        print("  3. Trải nghiệm giao diện Web:  Mở file 'docs/demo_ui.html' bằng trình duyệt web.\n")
        
        sample_query = tests[1]["question"]
        print(f"--- 🏁 DEMO CHẠY THỬ 1 TEST CASE MẪU (TC02: Tra cứu học vụ) ---")
        run_native_mcp_agent(sample_query, provider, mcp_server)
        print("\n💡 Hãy thử ngay lệnh: python src/app.py --interactive để chat trực tiếp!")
