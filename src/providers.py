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
import time
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()


_RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*:\s*['\"]?(\d+)s")

# Nếu Google yêu cầu chờ <= số giây này thì tự chờ rồi thử lại; lâu hơn thì báo cho người dùng.
MAX_AUTO_RETRY_WAIT_SECONDS = int(os.getenv("MAX_AUTO_RETRY_WAIT_SECONDS", "12"))


def parse_quota_error(error) -> Optional[int]:
    """
    Nhận diện lỗi hết hạn mức (429 RESOURCE_EXHAUSTED) và bóc ra số giây cần chờ.
    Trả về số giây (int) nếu đúng là lỗi quota, ngược lại trả về None.
    """
    text = str(error)
    if "RESOURCE_EXHAUSTED" not in text and "429" not in text:
        return None
    match = _RETRY_DELAY_RE.search(text)
    return int(match.group(1)) if match else 60


def format_quota_message(wait_seconds: int, model_name: str) -> str:
    """Thông báo thân thiện (Markdown) thay cho khối JSON lỗi dài dòng của Google."""
    return (
        f"⏳ **Đã chạm giới hạn miễn phí của Gemini API** (lỗi `429 RESOURCE_EXHAUSTED`).\n\n"
        f"Gói **Free Tier** chỉ cho phép khoảng **5 lượt gọi/phút** với model `{model_name}`, "
        f"trong khi mỗi câu hỏi so sánh tiêu tốn nhiều lượt (Chatbot Baseline + Layer 2 Guardrail "
        f"+ mỗi vòng lặp ReAct là một lượt).\n\n"
        f"**Cách xử lý:**\n"
        f"1. Chờ khoảng **{wait_seconds} giây** rồi hỏi lại.\n"
        f"2. Hỏi lại đúng câu vừa rồi — kết quả Guardrail đã được lưu đệm (cache) nên tiết kiệm 1 lượt.\n"
        f"3. Đặt `GUARDRAIL_MODEL` trong `.env` sang một model khác để tách hạn mức cho Guardrail.\n"
        f"4. Hoặc bật thanh toán cho dự án Google Cloud để nâng hạn mức."
    )


class BaseLLMProvider:
    """Interface cơ sở cho các LLM Provider hỗ trợ Native Tool Calling"""

    is_rule_based = False       # True nếu đây là engine suy luận theo luật, không gọi API
    last_quota_wait = None      # Số giây cần chờ nếu lượt gọi gần nhất bị lỗi 429 (None = không lỗi)

    def clone_with_model(self, model: str) -> "BaseLLMProvider":
        """Tạo bản sao dùng model khác (phục vụ GUARDRAIL_MODEL). Mặc định: giữ nguyên."""
        try:
            return self.__class__(api_key=getattr(self, "api_key", None), model=model)
        except Exception:
            return self

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


class RuleBasedProvider(BaseLLMProvider):
    """
    🧩 ENGINE RULE-BASED OFFLINE (không gọi API, không tốn hạn mức)

    Vai trò kép:
      1. Chạy thử toàn bộ Lab khi chưa có API Key.
      2. LÀM PHƯƠNG ÁN DỰ PHÒNG khi API thật hết hạn mức (429 RESOURCE_EXHAUSTED) —
         xem QuotaAwareFallbackProvider phía dưới. Nhờ vậy buổi demo không bị gãy giữa chừng.

    Cách hoạt động: quyết định bước tiếp theo bằng LUẬT (rule) dựa trên từ khóa trong câu hỏi
    + danh sách Tool ĐÃ thực thi (history). Đây là suy luận theo luật cố định, KHÔNG phải
    suy luận ngữ nghĩa như LLM — mọi câu trả lời đều được gắn nhãn rõ ràng để không gây nhầm lẫn.
    """
    is_rule_based = True

    def __init__(self):
        self.model_name = "RuleBased-Offline-Engine-2026"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return (
            "🧩 **[Engine rule-based offline]** — không gọi API nên không có dữ liệu thời gian thực.\n\n"
            "Quy trình đặt hàng & giao vận gồm: xác nhận đơn → xuất kho → vận chuyển → giao hàng. "
            "Để tra cứu một đơn hàng cụ thể, hãy dùng ReAct Agent ở khung bên phải (có Tool `track_order`)."
        )

    @staticmethod
    def synthesize_final_answer(order_id: str, history: List[Dict[str, Any]]) -> str:
        """
        Tổng hợp câu trả lời cuối cùng bằng Markdown theo TỪNG BƯỚC, dựa trên dữ liệu THẬT
        mà các Tool đã trả về (history) — không bịa thêm số liệu.
        """
        lines = [f"🧩 **[Engine rule-based offline]** — tổng hợp từ {len(history)} kết quả Tool đã thực thi:", ""]
        for idx, entry in enumerate(history, start=1):
            tool = entry.get("tool_name", "?")
            obs = entry.get("observation", {}) or {}
            data = obs.get("data", {}) if isinstance(obs, dict) else {}
            if tool == "track_order" and data:
                lines.append(
                    f"{idx}. Gọi `track_order` cho đơn **{obs.get('order_id', order_id)}** → "
                    f"sản phẩm *{data.get('product', 'N/A')}*, trạng thái **{data.get('status', 'N/A')}**, "
                    f"vị trí gần nhất: {data.get('current_location', 'N/A')}, "
                    f"dự kiến giao **{data.get('expected_delivery', 'N/A')}** qua **{data.get('carrier', 'N/A')}**."
                )
            elif tool == "schedule_pickup":
                lines.append(
                    f"{idx}. Gọi `schedule_pickup` → đã đặt lịch lấy hàng lúc "
                    f"**{obs.get('pickup_datetime', 'N/A')}** với **{obs.get('carrier', 'N/A')}** "
                    f"(mã phiếu `{obs.get('pickup_id', 'N/A')}`)."
                )
            elif tool == "update_order_status":
                lines.append(
                    f"{idx}. Gọi `update_order_status` → đã cập nhật đơn **{obs.get('order_id', order_id)}** "
                    f"sang trạng thái **{obs.get('new_status', 'N/A')}**."
                )
            else:
                lines.append(f"{idx}. Gọi `{tool}` → {json.dumps(obs, ensure_ascii=False)}")

        lines.append("")
        lines.append("**Kết luận:** đã xử lý xong yêu cầu cho đơn hàng **" + order_id + "** "
                     "dựa trên dữ liệu do MCP Server trả về.")
        return "\n".join(lines)

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
            return {
                "type": "text",
                "content": self.synthesize_final_answer(order_id, history),
                "thought": "Đã đủ dữ liệu quan sát từ các bước Tool trước, tổng hợp câu trả lời cuối cùng (theo luật)."
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
                "content": (
                    "🧩 **[Engine rule-based offline]**\n\n"
                    "Mình có thể hỗ trợ 3 việc:\n"
                    "1. Tra cứu vận đơn — Tool `track_order`\n"
                    "2. Đặt lịch lấy hàng — Tool `schedule_pickup`\n"
                    "3. Cập nhật trạng thái đơn hàng — Tool `update_order_status` (**cần phê duyệt HITL**)\n\n"
                    "Hãy nêu kèm mã đơn hàng (ví dụ **ORD2026001**) để mình tra cứu giúp bạn."
                ),
                "thought": "Câu hỏi chung về quy trình, trả lời trực tiếp không cần gọi Tool."
            }


# Tên cũ giữ lại để tương thích ngược với các đoạn code/tài liệu đã viết trước đó
MockOfflineProvider = RuleBasedProvider


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
        self.last_quota_wait = None
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return "[Gemini Error]: Chưa cấu hình GEMINI_API_KEY trong file .env! Đang dùng engine rule-based."
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            response = client.models.generate_content(model=self.model_name, contents=contents)
            return response.text
        except Exception as e:
            wait = parse_quota_error(e)
            if wait is not None:
                self.last_quota_wait = wait
                return format_quota_message(wait, self.model_name)
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
        self.last_quota_wait = None
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return RuleBasedProvider().generate_with_tools(prompt, tools_schema, system_prompt, history)
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
                # Lỗi hết hạn mức (429): nếu chỉ phải chờ ngắn thì tự chờ rồi thử lại 1 lần
                wait = parse_quota_error(api_error)
                if wait is not None:
                    if wait <= MAX_AUTO_RETRY_WAIT_SECONDS:
                        print(f"⏳ [GEMINI]: Chạm giới hạn hạn mức, tự động chờ {wait + 1}s rồi thử lại...")
                        time.sleep(wait + 1)
                        response = client.models.generate_content(
                            model=self.model_name,
                            contents=self._build_contents(types, prompt, history, replay_function_calls=True),
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
                                    "model_content": self._serialize_content(candidate.content),
                                    "thought": "Gemini đề xuất gọi Tool (sau khi chờ hết giới hạn hạn mức)."
                                }
                        return {"type": "text", "content": response.text,
                                "thought": "Gemini trả lời trực tiếp (sau khi chờ hết giới hạn hạn mức)."}
                    self.last_quota_wait = wait
                    return {
                        "type": "text",
                        "content": format_quota_message(wait, self.model_name),
                        "quota_exhausted": True,
                        "retry_after_seconds": wait,
                        "thought": "Hết hạn mức API — cần chuyển sang engine dự phòng."
                    }
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
            wait = parse_quota_error(e)
            if wait is not None:
                self.last_quota_wait = wait
                return {
                    "type": "text",
                    "content": format_quota_message(wait, self.model_name),
                    "quota_exhausted": True,
                    "retry_after_seconds": wait,
                    "thought": "Hết hạn mức API — cần chuyển sang engine dự phòng."
                }
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
            self.last_quota_wait = parse_quota_error(e)
            if self.last_quota_wait is not None:
                return format_quota_message(self.last_quota_wait, self.model_name)
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
            self.last_quota_wait = parse_quota_error(e)
            if self.last_quota_wait is not None:
                return {
                    "type": "text",
                    "content": format_quota_message(self.last_quota_wait, self.model_name),
                    "quota_exhausted": True,
                    "retry_after_seconds": self.last_quota_wait,
                    "thought": "Hết hạn mức API — cần chuyển sang engine dự phòng."
                }
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
            self.last_quota_wait = parse_quota_error(e)
            if self.last_quota_wait is not None:
                return format_quota_message(self.last_quota_wait, self.model_name)
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
            self.last_quota_wait = parse_quota_error(e)
            if self.last_quota_wait is not None:
                return {
                    "type": "text",
                    "content": format_quota_message(self.last_quota_wait, self.model_name),
                    "quota_exhausted": True,
                    "retry_after_seconds": self.last_quota_wait,
                    "thought": "Hết hạn mức API — cần chuyển sang engine dự phòng."
                }
            return {
                "type": "text",
                "content": f"[Anthropic Exception]: {str(e)}",
                "thought": "Lỗi khi gọi Anthropic API."
            }


class QuotaAwareFallbackProvider(BaseLLMProvider):
    """
    🔀 LỚP TỰ ĐỘNG CHUYỂN ĐỔI KHI HẾT HẠN MỨC (429 RESOURCE_EXHAUSTED)

    Bọc quanh 1 Provider LLM thật (Gemini/OpenAI/Anthropic) + 1 Engine rule-based offline:

        Câu hỏi ─► [LLM thật]  ──(429 hết hạn mức)──►  [Engine rule-based]  ─► Câu trả lời
                        ▲                                                          │
                        └──────── tự quay lại sau khi hết thời gian chờ ◄───────────┘

    Cơ chế "cooldown": ngay khi gặp 429, lớp này ghi nhận mốc thời gian cần chờ (do chính Google
    trả về trong `retryDelay`) và chuyển TOÀN BỘ lượt gọi kế tiếp sang engine rule-based —
    vừa giúp demo không gãy giữa chừng, vừa TRÁNH tiếp tục bắn request vào API (càng bắn càng
    bị khoá lâu). Hết thời gian chờ, lớp này tự động quay lại dùng LLM thật mà không cần
    khởi động lại chương trình.

    Mọi câu trả lời sinh ra ở chế độ dự phòng đều được gắn cờ `rule_based_fallback=True` để
    Trace Log và giao diện Web hiển thị rõ ràng — KHÔNG bao giờ giả vờ đó là kết quả của LLM thật.
    """
    is_rule_based = False

    def __init__(self, primary: BaseLLMProvider, fallback: Optional[BaseLLMProvider] = None):
        self.primary = primary
        self.fallback = fallback or RuleBasedProvider()
        self.quota_blocked_until = 0.0
        self.active_engine = primary          # engine đã phục vụ lượt gọi gần nhất
        self.fallback_activations = 0

    @property
    def model_name(self) -> str:
        return getattr(self.primary, "model_name", "n/a")

    @property
    def is_rule_based_now(self) -> bool:
        """Có đang trong thời gian chờ hết hạn mức (tức đang chạy bằng engine rule-based) không."""
        return time.time() < self.quota_blocked_until

    def remaining_cooldown_seconds(self) -> int:
        return max(0, int(round(self.quota_blocked_until - time.time())))

    def clone_with_model(self, model: str) -> BaseLLMProvider:
        try:
            return QuotaAwareFallbackProvider(self.primary.clone_with_model(model), self.fallback)
        except Exception:
            return self

    def _activate_fallback(self, wait_seconds: int):
        self.quota_blocked_until = time.time() + wait_seconds
        self.fallback_activations += 1
        print(f"🔀 [FALLBACK]: Hết hạn mức API (429) → chuyển sang engine rule-based "
              f"'{self.fallback.model_name}' trong {wait_seconds}s. Hệ thống vẫn chạy bình thường.")

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if self.is_rule_based_now:
            self.active_engine = self.fallback
            return self.fallback.generate(prompt, system_prompt)

        result = self.primary.generate(prompt, system_prompt)
        if self.primary.last_quota_wait is not None:
            self._activate_fallback(self.primary.last_quota_wait)
            self.active_engine = self.fallback
            return self.fallback.generate(prompt, system_prompt)

        self.active_engine = self.primary
        return result

    def generate_with_tools(
        self,
        prompt: str,
        tools_schema: List[Dict[str, Any]],
        system_prompt: str = "",
        history: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        if self.is_rule_based_now:
            self.active_engine = self.fallback
            return self._tag_fallback(
                self.fallback.generate_with_tools(prompt, tools_schema, system_prompt, history))

        result = self.primary.generate_with_tools(prompt, tools_schema, system_prompt, history)
        if result.get("quota_exhausted") or self.primary.last_quota_wait is not None:
            wait = result.get("retry_after_seconds") or self.primary.last_quota_wait or 60
            self._activate_fallback(wait)
            self.active_engine = self.fallback
            return self._tag_fallback(
                self.fallback.generate_with_tools(prompt, tools_schema, system_prompt, history))

        self.active_engine = self.primary
        return result

    def _tag_fallback(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Gắn nhãn minh bạch: kết quả này do engine rule-based sinh ra, không phải LLM thật."""
        tagged = dict(result)
        tagged["rule_based_fallback"] = True
        tagged["thought"] = (
            f"[ENGINE RULE-BASED DỰ PHÒNG - còn {self.remaining_cooldown_seconds()}s nữa mới "
            f"gọi lại được API] " + (result.get("thought") or "")
        )
        return tagged


def get_llm_provider() -> BaseLLMProvider:
    """Factory function khởi tạo Provider theo LLM_PROVIDER env variable"""
    provider_type = os.getenv("LLM_PROVIDER", "mock").lower()

    # Bọc Provider thật bằng lớp tự động chuyển sang engine rule-based khi hết hạn mức API.
    # Tắt bằng cách đặt ENABLE_RULE_BASED_FALLBACK=false trong .env (khi đó lỗi 429 sẽ hiện
    # thẳng ra cho người dùng thay vì âm thầm chạy bằng luật).
    enable_fallback = os.getenv("ENABLE_RULE_BASED_FALLBACK", "true").strip().lower() not in ("false", "0", "no")

    def wrap(real_provider: BaseLLMProvider) -> BaseLLMProvider:
        return QuotaAwareFallbackProvider(real_provider) if enable_fallback else real_provider

    if provider_type == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if key and key != "your_gemini_api_key_here":
            return wrap(GeminiProvider())
        print("⚠️ GEMINI_API_KEY chưa được cài đặt. Chuyển tự động sang Engine rule-based offline.")
        return RuleBasedProvider()
    elif provider_type == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if key and key != "your_openai_api_key_here":
            return wrap(OpenAIProvider())
        print("⚠️ OPENAI_API_KEY chưa được cài đặt. Chuyển tự động sang Engine rule-based offline.")
        return RuleBasedProvider()
    elif provider_type == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY")
        if key and key != "your_anthropic_api_key_here":
            return wrap(AnthropicProvider())
        print("⚠️ ANTHROPIC_API_KEY chưa được cài đặt. Chuyển tự động sang Engine rule-based offline.")
        return RuleBasedProvider()
    else:
        return RuleBasedProvider()
