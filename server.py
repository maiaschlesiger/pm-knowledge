# Adapted from the FastMCP quickstart in the MCP Python SDK README:
# https://github.com/modelcontextprotocol/python-sdk
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("pm-knowledge")

@mcp.tool()
def ping(name: str) -> str:
    """Test tool: confirms the server is connected."""
    return f"Hello, {name}. pm-knowledge server is running."

if __name__ == "__main__":
    mcp.run()