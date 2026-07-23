"""ServerAlly MCP server package.

Exposes ServerAlly's bounded tools to a customer's *own* AI client (Claude Code,
Claude Desktop, ChatGPT, Cursor…) over Streamable HTTP. See
``docs/MCP-SERVER-PLAN.md`` for the full design and ``server.py`` for the tools.
"""
from app.mcp.server import mcp_server

__all__ = ["mcp_server"]
