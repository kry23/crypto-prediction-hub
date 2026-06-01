"""crypto-predictor FastMCP server — entry point for MCP tools."""
from __future__ import annotations

from datetime import datetime, timezone

from fastmcp import FastMCP

from crypto_predictor import __version__

mcp = FastMCP("crypto-predictor")


@mcp.tool()
def ping() -> dict:
    """Health check — returns server status, version, and current UTC timestamp."""
    return {
        "status": "ok",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    mcp.run()
