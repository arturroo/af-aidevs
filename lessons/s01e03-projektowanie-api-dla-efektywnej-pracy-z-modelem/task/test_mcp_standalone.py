import asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

# URL Twojego serwera MCP (bez końcówki /sse, FastMCP obsłuży ścieżkę bazową)
MCP_SERVER_URL = "https://cr-s01e03-mcp-server-qsvqxjqyrq-oa.a.run.app"

async def test_mcp():
    print(f"🚀 Łączenie z serwerem MCP (FastMCP Native): {MCP_SERVER_URL}...")
    
    # Domyślna ścieżka w FastMCP to /mcp
    endpoint = f"{MCP_SERVER_URL}/mcp"
    print(f"🔗 Target endpoint: {endpoint}")

    try:
        transport = StreamableHttpTransport(url=endpoint)
        async with Client(transport) as client:
            print("✅ Połączono z serwerem FastMCP.")
            
            print("\n🔍 Pobieranie listy narzędzi...")
            tools = await client.list_tools()
            for tool in tools:
                print(f"   - [{tool.name}]: {tool.description}")

            # Testowe wywołanie
            print(f"\n🧪 Testowe wywołanie 'check_package'...")
            result = await client.call_tool("check_package", {"packageid": "PKG12345678"})
            print(f"📥 Odpowiedź: {result}")

    except Exception as e:
        print(f"❌ Błąd klienta FastMCP: {e}")

if __name__ == "__main__":
    asyncio.run(test_mcp())


