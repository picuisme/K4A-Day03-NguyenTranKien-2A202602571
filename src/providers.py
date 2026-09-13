"""
🔌 MULTI-PROVIDER LLM ADAPTER (Google Gemini, OpenAI, Anthropic & Offline Mock)
Hỗ trợ Native Tool Calling đa vòng (multi-step) và chuyển đổi linh hoạt qua biến môi trường LLM_PROVIDER.

Nâng cấp so với bản gốc:
  - Bổ sung tham số `history` cho generate_with_tools() để LLM "nhìn thấy" kết quả (observation)
    của các bước Tool trước đó trong CÙNG một lượt hỏi -> hỗ trợ đúng nghĩa Multi-step Reasoning
    (Thought -> Action -> Observation -> Thought -> Action... ) thay vì chỉ gọi 1 Tool rồi dừng.
  - Cài đặt thật (không còn giả lập/fake) cho OpenAI và Anthropic bằng Native Tool Calling.
  - Cài đặt thật cho Gemini Function Calling (có fallback an toàn về Mock nếu SDK/API lỗi).
  - Model mặc định được nâng cấp lên các dòng model hiện đại hơn (xem từng Provider phía dưới).
"""

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()


class BaseLLMProvider:
    """Interface cơ sở cho các LLM Provider hỗ trợ Native Tool Calling"""
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        raise NotImplementedError

    def generate_with_tools(
        self,
        prompt: str,
        tools_schema: List[Dict[str, Any]],
        system_prompt: str = "",
        history: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        history: danh sách các bước Tool đã thực thi TRONG CÙNG lượt hỏi hiện tại, dạng:
            [{"id": "...", "tool_name": "...", "arguments": {...}, "observation": {...}}, ...]
        Cho phép LLM suy luận tiếp (multi-step) dựa trên observation của bước trước.
        """
        raise NotImplementedError


class MockOfflineProvider(BaseLLMProvider):
    """Offline Mock Provider dùng để chạy thử mà không tốn API Key (chủ đề: Supply Chain Agent)"""
    def __init__(self):
        self.model_name = "Offline-Mock-Model-2026"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return f"[Mock Chatbot Response]: Xin chào! Tôi đã nhận được câu hỏi '{prompt}'. (Chế độ offline không dùng Tool)."

    def generate_with_tools(
        self,
        prompt: str,
        tools_schema: List[Dict[str, Any]],
        system_prompt: str = "",
        history: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        history = history or []
        prompt_lower = prompt.lower()

        order_match = re.search(r"ord\d{6,}", prompt_lower)
        order_id = order_match.group(0).upper() if order_match else "ORD2026001"

        wants_pickup = any(k in prompt_lower for k in ["lấy hàng", "pickup", "đặt lịch"])
        wants_cancel = any(k in prompt_lower for k in ["hủy", "huỷ", "cập nhật trạng thái", "đổi trạng thái"])
        wants_lookup = any(k in prompt_lower for k in ["tra cứu", "trạng thái", "vận đơn", "kiểm tra"])

        executed_tools = [h.get("tool_name") for h in history]

        # Bước kế tiếp phụ thuộc vào những gì ĐÃ thực thi (mô phỏng Dynamic Decision)
        if "track_order" in executed_tools and wants_pickup and "schedule_pickup" not in executed_tools:
            return {
                "type": "tool_call",
                "tool_name": "schedule_pickup",
                "arguments": {"order_id": order_id, "pickup_datetime": "09:00 20/09/2026", "carrier_name": "Viettel Post"},
                "thought": "Đã có dữ liệu tra cứu ở bước trước, tiếp tục đặt lịch lấy hàng theo yêu cầu ban đầu."
            }

        if "track_order" in executed_tools and wants_cancel and "update_order_status" not in executed_tools:
            return {
                "type": "tool_call",
                "tool_name": "update_order_status",
                "arguments": {"order_id": order_id, "new_status": "Đã hủy", "reason": "Khách hàng yêu cầu hủy đơn"},
                "thought": "Đã xác nhận đơn hàng tồn tại ở bước trước, tiếp tục đề nghị cập nhật trạng thái hủy đơn."
            }

        if executed_tools:
            # Đã có ít nhất 1 quan sát và không còn hành động tiếp theo cần làm -> tổng hợp trả lời cuối
            last_obs = history[-1].get("observation", {})
            return {
                "type": "text",
                "content": f"[Mock Agent Response]: Đã xử lý xong yêu cầu cho đơn hàng {order_id}. Dữ liệu quan sát gần nhất: {json.dumps(last_obs, ensure_ascii=False)}",
                "thought": "Đã đủ dữ liệu quan sát từ các bước Tool trước, tổng hợp câu trả lời cuối cùng."
            }

        # Chưa có bước Tool nào được thực thi -> quyết định hành động đầu tiên
        if wants_cancel and (order_match or wants_lookup):
            return {
                "type": "tool_call",
                "tool_name": "update_order_status",
                "arguments": {"order_id": order_id, "new_status": "Đã hủy", "reason": "Khách hàng yêu cầu hủy đơn"},
                "thought": "Người dùng yêu cầu hủy/đổi trạng thái đơn hàng. Đây là hành động nhạy cảm cần phanh HITL."
            }
        elif order_match or wants_lookup:
            return {
                "type": "tool_call",
                "tool_name": "track_order",
                "arguments": {"order_id": order_id},
                "thought": f"Người dùng muốn tra cứu trạng thái đơn hàng {order_id}."
            }
        else:
            return {
                "type": "text",
                "content": "[Mock Agent Response]: Xin chào! Quy trình đặt hàng & giao vận bao gồm tra cứu vận đơn, đặt lịch lấy hàng và cập nhật trạng thái đơn hàng qua hệ thống trực tuyến.",
                "thought": "Câu hỏi chung về quy trình, trả lời trực tiếp không cần gọi Tool."
            }


class GeminiProvider(BaseLLMProvider):
    """
    Google Gemini Provider (Native Function Calling)

    ⚠️ LƯU Ý QUAN TRỌNG VỀ "THOUGHT SIGNATURE" (dòng Gemini 3 trở lên):
    Từ Gemini 3, mỗi lời gọi Tool (functionCall) do model sinh ra có kèm một chữ ký suy luận
    đã mã hoá gọi là `thought_signature`. Khi ta gửi lại lịch sử hội thoại nhiều bước
    (multi-step Tool Calling), functionCall part BẮT BUỘC phải mang theo đúng chữ ký gốc đó,
    nếu không API trả lỗi:
        400 INVALID_ARGUMENT: Function call is missing a thought_signature in functionCall parts

    Bản trước đây tự dựng lại functionCall part bằng tay (types.FunctionCall(name=..., args=...))
    nên chữ ký bị mất -> lỗi ngay ở vòng lặp thứ 2. Bản này lưu lại NGUYÊN VẸN đối tượng
    Content mà model trả về (đã serialize sang dict JSON thuần để còn truyền qua HTTP cho Web UI),
    rồi phát lại đúng như đã nhận -> chữ ký được giữ nguyên.

    Ngoài ra còn có lớp an toàn: nếu API vẫn báo thiếu thought_signature (ví dụ bản SDK cũ làm
    rớt trường này khi parse), provider tự động thử lại lần 2 theo cách KHÔNG phát lại functionCall
    part, mà nạp observation dưới dạng văn bản -> Agent vẫn chạy đúng nhiều bước, không gãy demo.
    """
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        # Model mặc định: gemini-3.5-flash (đã xác minh 13/09/2026 — model ID chính thức
        # trên Gemini API, hỗ trợ Function/Tool Calling + 1M context window). Thay cho
        # gemini-3.1-pro-preview cũ.
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-3.5-flash"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return "[Gemini Error]: Chưa cấu hình GEMINI_API_KEY trong file .env! Đang sử dụng chế độ Mock."
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            response = client.models.generate_content(model=self.model_name, contents=contents)
            return response.text
        except Exception as e:
            return f"[Gemini Exception]: {str(e)}"

    @staticmethod
    def _serialize_content(content) -> Optional[Dict[str, Any]]:
        """
        Chuyển đối tượng Content (pydantic) mà Gemini trả về thành dict JSON THUẦN,
        để: (1) lưu được vào `history`, (2) truyền qua HTTP cho Web UI khi tạm dừng chờ
        phê duyệt HITL, mà VẪN giữ nguyên trường `thought_signature` (SDK tự mã hoá base64).
        """
        try:
            return json.loads(content.model_dump_json(exclude_none=True))
        except Exception:
            return None

    @staticmethod
    def _build_contents(types, prompt: str, history: List[Dict[str, Any]], replay_function_calls: bool = True):
        """
        Dựng lại hội thoại multi-turn để gửi cho Gemini.

        replay_function_calls=True  (mặc định): phát lại ĐÚNG NGUYÊN VẸN Content mà model đã trả về
            ở các bước trước (kèm thought_signature) + function_response tương ứng. Đây là cách chuẩn
            theo tài liệu Gemini Function Calling.
        replay_function_calls=False (phương án dự phòng): KHÔNG phát lại functionCall part nữa —
            thay vào đó nạp kết quả Tool dưới dạng văn bản. Dùng khi API báo thiếu thought_signature
            (ví dụ do bản SDK cũ làm rớt trường này), để Agent vẫn suy luận tiếp được thay vì gãy.
        """
        contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
        for h in history:
            if replay_function_calls:
                model_content = None
                raw_content = h.get("model_content")
                if raw_content:
                    try:
                        # Khôi phục nguyên vẹn Content cũ -> giữ được thought_signature
                        model_content = types.Content.model_validate(raw_content)
                    except Exception:
                        model_content = None
                if model_content is None:
                    # Không có bản gốc (ví dụ history đến từ Mock Provider) -> dựng tạm bằng tay
                    model_content = types.Content(
                        role="model",
                        parts=[types.Part(function_call=types.FunctionCall(
                            name=h["tool_name"], args=h["arguments"]))]
                    )
                contents.append(model_content)
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(function_response=types.FunctionResponse(
                        name=h["tool_name"], response=h.get("observation", {})
                    ))]
                ))
            else:
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=(
                        f"[KẾT QUẢ TOOL ĐÃ THỰC THI] {h['tool_name']}"
                        f"({json.dumps(h.get('arguments', {}), ensure_ascii=False)}) -> "
                        f"{json.dumps(h.get('observation', {}), ensure_ascii=False)}"
                    ))]
                ))
        return contents

    def generate_with_tools(
        self,
        prompt: str,
        tools_schema: List[Dict[str, Any]],
        system_prompt: str = "",
        history: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        history = history or []
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return MockOfflineProvider().generate_with_tools(prompt, tools_schema, system_prompt, history)
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            function_declarations = [
                types.FunctionDeclaration(
                    name=t["name"],
                    description=t.get("description", ""),
                    parameters=t.get("parameters", {})
                ) for t in tools_schema
            ]
            gemini_tools = [types.Tool(function_declarations=function_declarations)]
            config = types.GenerateContentConfig(
                system_instruction=system_prompt or None,
                tools=gemini_tools
            )

            try:
                response = client.models.generate_content(
                    model=self.model_name,
                    contents=self._build_contents(types, prompt, history, replay_function_calls=True),
                    config=config
                )
            except Exception as api_error:
                # Lớp an toàn cho lỗi 400 "Function call is missing a thought_signature"
                if "thought_signature" not in str(api_error):
                    raise
                print("⚠️ [GEMINI]: Thiếu thought_signature khi phát lại functionCall "
                      "(thường do bản SDK cũ làm rớt trường này — hãy chạy 'pip install -U google-genai'). "
                      "Đang tự động thử lại theo cách nạp observation dạng văn bản...")
                response = client.models.generate_content(
                    model=self.model_name,
                    contents=self._build_contents(types, prompt, history, replay_function_calls=False),
                    config=config
                )

            candidate = response.candidates[0]
            for part in candidate.content.parts:
                if getattr(part, "function_call", None):
                    fc = part.function_call
                    return {
                        "type": "tool_call",
                        "tool_name": fc.name,
                        "arguments": dict(fc.args) if fc.args else {},
                        # Lưu nguyên vẹn Content của model (kèm thought_signature) để phát lại
                        # chính xác ở vòng lặp kế tiếp -> tránh lỗi 400 INVALID_ARGUMENT.
                        "model_content": self._serialize_content(candidate.content),
                        "thought": "Gemini đề xuất gọi Tool dựa trên yêu cầu người dùng và quan sát trước đó."
                    }
            return {
                "type": "text",
                "content": response.text,
                "thought": "Gemini trả lời trực tiếp không cần gọi Tool."
            }
        except Exception as e:
            return {
                "type": "text",
                "content": f"[Gemini Exception]: {str(e)}",
                "thought": "Lỗi khi gọi Gemini API."
            }


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Provider (Native Function/Tool Calling)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        # Nâng cấp model mặc định lên dòng hiện đại hơn gpt-4o-mini cũ.
        # gpt-5.6-sol: cân bằng năng lực/chi phí cho việc học tập & demo Tool Calling.
        # (Có thể đổi sang "gpt-6-astra" nếu cần năng lực cao nhất, tốn phí hơn.)
        self.model_name = model or os.getenv("LLM_MODEL") or "gpt-5.6-sol"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_openai_api_key_here":
            return "[OpenAI Error]: Chưa cấu hình OPENAI_API_KEY trong file .env! Đang sử dụng chế độ Mock."
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = client.chat.completions.create(model=self.model_name, messages=messages)
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"[OpenAI Exception]: {str(e)}"

    def generate_with_tools(
        self,
        prompt: str,
        tools_schema: List[Dict[str, Any]],
        system_prompt: str = "",
        history: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        history = history or []
        if not self.api_key or self.api_key == "your_openai_api_key_here":
            return MockOfflineProvider().generate_with_tools(prompt, tools_schema, system_prompt, history)
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)

            openai_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", {})
                    }
                } for t in tools_schema
            ]

            messages: List[Dict[str, Any]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # Dựng lại hội thoại multi-turn từ các bước Tool đã thực thi trước đó
            for h in history:
                call_id = h.get("id") or f"call_{h['tool_name']}"
                messages.append({
                    "role": "assistant",
                    "tool_calls": [{
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": h["tool_name"],
                            "arguments": json.dumps(h["arguments"], ensure_ascii=False)
                        }
                    }]
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(h.get("observation", {}), ensure_ascii=False)
                })

            response = client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                tools=openai_tools,
                tool_choice="auto"
            )
            choice = response.choices[0].message

            if choice.tool_calls:
                call = choice.tool_calls[0]
                arguments = json.loads(call.function.arguments or "{}")
                return {
                    "type": "tool_call",
                    "id": call.id,
                    "tool_name": call.function.name,
                    "arguments": arguments,
                    "thought": choice.content or "Đề xuất gọi Tool dựa trên yêu cầu người dùng và quan sát trước đó."
                }

            return {
                "type": "text",
                "content": choice.content or "",
                "thought": "LLM trả lời trực tiếp không cần gọi Tool."
            }
        except Exception as e:
            return {
                "type": "text",
                "content": f"[OpenAI Exception]: {str(e)}",
                "thought": "Lỗi khi gọi OpenAI API."
            }


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude Provider (Native Tool Use)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        # Nâng cấp model mặc định lên claude-sonnet-5 (thay cho claude-3-5-haiku-20241022 cũ).
        self.model_name = model or os.getenv("LLM_MODEL") or "claude-sonnet-5"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_anthropic_api_key_here":
            return "[Anthropic Error]: Chưa cấu hình ANTHROPIC_API_KEY trong file .env! Đang sử dụng chế độ Mock."
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model=self.model_name,
                max_tokens=1024,
                system=system_prompt or None,
                messages=[{"role": "user", "content": prompt}]
            )
            return "".join(block.text for block in response.content if block.type == "text")
        except Exception as e:
            return f"[Anthropic Exception]: {str(e)}"

    def generate_with_tools(
        self,
        prompt: str,
        tools_schema: List[Dict[str, Any]],
        system_prompt: str = "",
        history: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        history = history or []
        if not self.api_key or self.api_key == "your_anthropic_api_key_here":
            return MockOfflineProvider().generate_with_tools(prompt, tools_schema, system_prompt, history)
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=self.api_key)

            anthropic_tools = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters", {})
                } for t in tools_schema
            ]

            messages: List[Dict[str, Any]] = [{"role": "user", "content": prompt}]
            for h in history:
                call_id = h.get("id") or f"toolu_{h['tool_name']}"
                messages.append({
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": call_id, "name": h["tool_name"], "input": h["arguments"]}]
                })
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": call_id,
                        "content": json.dumps(h.get("observation", {}), ensure_ascii=False)
                    }]
                })

            response = client.messages.create(
                model=self.model_name,
                max_tokens=1024,
                system=system_prompt or None,
                tools=anthropic_tools,
                messages=messages
            )

            text_parts = []
            for block in response.content:
                if block.type == "tool_use":
                    return {
                        "type": "tool_call",
                        "id": block.id,
                        "tool_name": block.name,
                        "arguments": block.input,
                        "thought": " ".join(text_parts) or "Đề xuất gọi Tool dựa trên yêu cầu người dùng và quan sát trước đó."
                    }
                elif block.type == "text":
                    text_parts.append(block.text)

            return {
                "type": "text",
                "content": " ".join(text_parts),
                "thought": "LLM trả lời trực tiếp không cần gọi Tool."
            }
        except Exception as e:
            return {
                "type": "text",
                "content": f"[Anthropic Exception]: {str(e)}",
                "thought": "Lỗi khi gọi Anthropic API."
            }


def get_llm_provider() -> BaseLLMProvider:
    """Factory function khởi tạo Provider theo LLM_PROVIDER env variable"""
    provider_type = os.getenv("LLM_PROVIDER", "mock").lower()

    if provider_type == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if key and key != "your_gemini_api_key_here":
            return GeminiProvider()
        print("⚠️ GEMINI_API_KEY chưa được cài đặt. Chuyển tự động sang Offline Mock Mode.")
        return MockOfflineProvider()
    elif provider_type == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if key and key != "your_openai_api_key_here":
            return OpenAIProvider()
        print("⚠️ OPENAI_API_KEY chưa được cài đặt. Chuyển tự động sang Offline Mock Mode.")
        return MockOfflineProvider()
    elif provider_type == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY")
        if key and key != "your_anthropic_api_key_here":
            return AnthropicProvider()
        print("⚠️ ANTHROPIC_API_KEY chưa được cài đặt. Chuyển tự động sang Offline Mock Mode.")
        return MockOfflineProvider()
    elif provider_type == "mock":
        return MockOfflineProvider()
    else:
        return MockOfflineProvider()
