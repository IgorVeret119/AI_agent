"""MCP version of schedule_search with explicit per-request fault control."""
import json
import sys
from pathlib import Path
from typing import Annotated, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mcp.server import MCPServer
from mcp_types import CallToolResult, TextContent
from pydantic import Field

from core import schedule_search as unstable_search
from server import ENTRIES

server = MCPServer("Unstable course schedule", version="1.0.0")


@server.tool()
def schedule_search(
    schedule_handle: Annotated[Literal["schedule-v1"], Field(description="Immutable schedule snapshot.")],
    course: Annotated[Literal["agents", "python", "databases"], Field(description="Requested course.")],
    date: Annotated[str, Field(description="Calendar date YYYY-MM-DD.")],
    fault_handle: Annotated[str, Field(description="Explicit harness handle seed:call_ordinal; no session state.")],
    response_mode: Annotated[Literal["empty", "hint"], Field(description="Experimental form of the empty response.")],
) -> CallToolResult:
    """Search the synthetic course schedule by course and calendar date."""
    payload, _ = unstable_search({"schedule_handle": schedule_handle, "course": course, "date": date}, fault_handle, response_mode == "hint", ENTRIES)
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, separators=(",", ":")))], is_error=bool(isinstance(payload, dict) and payload.get("isError")))


if __name__ == "__main__":
    server.run(transport="stdio")
