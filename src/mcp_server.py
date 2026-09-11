"""
🔌 MODEL CONTEXT PROTOCOL (MCP) SERVER MODULE
Mô phỏng kiến trúc MCP Server (Client-Server Architecture) cung cấp công cụ chuẩn hóa.
"""

import json
from typing import Dict, Any, List
from tools import TOOLS_SCHEMA, dispatch_tool_call

class MCPAcademicServer:
    """
    Giả lập MCP Server tuân thủ chuẩn giao thức Model Context Protocol
    """
    def __init__(self, server_name: str = "vinuni-academic-mcp-server"):
        self.server_name = server_name
        self.version = "2026.1.0"
        
    def list_tools(self) -> List[Dict[str, Any]]:
        """Trả về danh sách các Tools chuẩn giao thức MCP"""
        return TOOLS_SCHEMA
        
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        [TASK 2.1] HỌC VIÊN HOÀN THIỆN HÀM THỰC THI TOOL TRÊN MCP SERVER
        Thực thi request gọi Tool theo chuẩn MCP JSON-RPC
        """
        # --------------------------------------------------------------------------
        # TODO 2.1: Gọi dispatch_tool_call(tool_name, arguments) để lấy chuỗi JSON kết quả
        # Đóng gói phản hồi theo cấu trúc JSON-RPC: {"jsonrpc": "2.0", "server": ..., "tool": ..., "result": ...}
        # --------------------------------------------------------------------------
        result_json_str = dispatch_tool_call(tool_name, arguments)
        try:
            content = json.loads(result_json_str)
        except Exception:
            content = {"raw_output": result_json_str}
            
        return {
            "jsonrpc": "2.0",
            "server": self.server_name,
            "tool": tool_name,
            "result": content
        }

if __name__ == "__main__":
    server = MCPAcademicServer()
    print(f"✅ [MCP SERVER] Đã khởi tạo thành công {server.server_name} (Version: {server.version})")
    print(f"📦 Số lượng Tools công bố qua MCP: {len(server.list_tools())}")
