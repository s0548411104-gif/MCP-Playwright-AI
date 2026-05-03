import netfree_unstrict_ssl
import asyncio
from contextlib import AsyncExitStack
from typing import Any
import os

import httpx
import google.generativeai as genai  #[cite: 4]
from client import MCPClient
from dotenv import load_dotenv

load_dotenv()

class ChatHost:
    def __init__(self):
        # הגדרת המפתח של גוגל[cite: 4]
        genai.configure(api_key=os.environ["GOOGLE_API_KEY"], transport="rest")
        # שימוש במודל Pro העדכני ביותר שמופיע אצלך ברשימה[cite: 4]
        self.model_name = "gemini-2.5-flash"
        
        # רשימת שרתי ה-MCP המחוברים[cite: 4, 8]
        self.mcp_clients: list[MCPClient] = [
            MCPClient("./weather_USA.py"),
            MCPClient("./weather_Israel.py")
        ]
        self.tool_clients: dict[str, tuple[MCPClient, str]] = {}
        self.clients_connected = False
        self.exit_stack = AsyncExitStack()

    async def connect_mcp_clients(self):
        """Connect all configured MCP clients once."""
        if self.clients_connected:
            return

        for client in self.mcp_clients:
            if client.session is None:
                await client.connect_to_server()

        if not self.mcp_clients:
            raise RuntimeError("No MCP clients are connected")

        self.clients_connected = True

    async def get_available_tools(self) -> list[dict[str, Any]]:
        """Collect tools from all MCP clients and map them back to their owner."""
        await self.connect_mcp_clients()
        self.tool_clients = {}
        available_tools: list[dict[str, Any]] = []

        for client in self.mcp_clients:
            if client.session is None:
                continue

            try:
                response = await client.session.list_tools()
                for tool in response.tools:
                    exposed_name = f"{client.client_name}_{tool.name}"
                    
                    # ניקוי ה-Schema עבור Gemini - הסרת שדות 'title'[cite: 4]
                    input_schema = dict(tool.inputSchema)
                    input_schema.pop("title", None)
                    if "properties" in input_schema:
                        clean_props = {}
                        for p_name, p_val in input_schema["properties"].items():
                            p_dict = dict(p_val)
                            p_dict.pop("title", None)
                            clean_props[p_name] = p_dict
                        input_schema["properties"] = clean_props

                    if exposed_name in self.tool_clients:
                        raise RuntimeError(f"Duplicate tool name detected: {exposed_name}")

                    self.tool_clients[exposed_name] = (client, tool.name)
                    available_tools.append({
                        "name": exposed_name,
                        "description": tool.description,
                        "parameters": input_schema,
                    })
            except Exception as e:
                print(f"Warning: Failed to get tools from {client.client_name}: {str(e)}")
                continue

        return available_tools

    async def process_query(self, query: str) -> str:
        """Process a query using Gemini and available tools"""
        available_tools = await self.get_available_tools()
        
        # המרת הכלים לפורמט של גמינאי[cite: 4]
        gemini_tools = [{"function_declarations": [
            {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"]
            } for t in available_tools
        ]}] if available_tools else None

        model = genai.GenerativeModel(model_name=self.model_name, tools=gemini_tools)
        chat = model.start_chat(history=[])
        final_text = []
        
        response = chat.send_message(query)
        
        while True:
            # שליפת טקסט בצורה בטוחה
            for part in response.candidates[0].content.parts:
                if part.text:
                    final_text.append(part.text)

            # בדיקה אם יש קריאה לכלים[cite: 4]
            tool_calls = [part.function_call for part in response.candidates[0].content.parts if part.function_call]
            
            if not tool_calls:
                break
                
            tool_responses = []
            for call in tool_calls:
                tool_name = call.name
                tool_args = dict(call.args)

                client, original_tool_name = self.tool_clients[tool_name]
                final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")
                
                # הפעלת הכלי בשרת ה-MCP[cite: 3, 4]
                result = await client.session.call_tool(original_tool_name, tool_args)
                
            # החזרת התשובה לגמינאי בפורמט מילון פשוט
                tool_responses.append({
                    "function_response": {
                        "name": tool_name,
                        "response": {"result": str(result.content)}
                    }
                })
            # שליחת תוצאות הכלים חזרה למודל
            response = chat.send_message(tool_responses)

        return "\n".join(final_text)

    async def chat_loop(self):
        print("\nMCP Client Started (with Gemini)!")
        print("Type your queries or 'quit' to exit.")
        while True:
            try:
                query = input("\nQuery: ").strip()
                if query.lower() == 'quit': break
                response = await self.process_query(query)
                print("\n" + response)
            except Exception as e:
                print(f"\nchat_loop Error: {str(e)}")
                
    async def cleanup(self):
        for client in reversed(self.mcp_clients):
            await client.cleanup()
        await self.exit_stack.aclose()

async def main():
    host = ChatHost()
    try:
        await host.chat_loop()
    finally:
        await host.cleanup()
        
if __name__ == "__main__":
    asyncio.run(main())