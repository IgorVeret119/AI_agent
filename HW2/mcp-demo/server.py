"""Synthetic course schedule, MCP 2026-07-28, no session state."""
import json
from typing import Annotated, Literal

from jsonschema import Draft202012Validator
from mcp.server import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

PROTOCOL = "2026-07-28"
HANDLE = "schedule-v1"
Format = Annotated[Literal["concise", "detailed"], Field(description="Amount of detail in the response.")]
Handle = Annotated[Literal["schedule-v1"], Field(description="Explicit immutable schedule snapshot handle.")]
Course = Annotated[Literal["all", "agents", "python", "databases"], Field(description="Course filter; all selects every course.")]
Day = Annotated[Literal["all", "monday", "tuesday", "wednesday"], Field(description="Weekday filter; all selects every day.")]
Room = Annotated[Literal["314", "210", "115"], Field(description="Supported classroom number.")]
EntryId = Annotated[str, Field(description="Entry identifier returned by schedule_search.", min_length=1, max_length=64)]
ENTRIES = (
    {"id": "agents-mon", "course": "agents", "day": "monday", "start": "10:00", "end": "11:30", "room": "314", "teacher": "Anna Petrova"},
    {"id": "python-tue", "course": "python", "day": "tuesday", "start": "12:00", "end": "13:30", "room": "210", "teacher": "Ivan Smirnov"},
    {"id": "databases-wed", "course": "databases", "day": "wednesday", "start": "14:00", "end": "15:30", "room": "115", "teacher": "Maria Volkova"},
    {"id": "agents-wed", "course": "agents", "day": "wednesday", "start": "10:00", "end": "11:30", "room": "314", "teacher": "Anna Petrova"},
)


def string_field(description, values=None):
    return {"type": "string", "description": description, **({"enum": values} if values else {})}


OUTPUT_SCHEMA = {
    "type": "object", "description": "Synthetic schedule query result.", "additionalProperties": False,
    "required": ["schedule_handle", "synthetic", "entries"],
    "properties": {
        "schedule_handle": string_field("Immutable snapshot handle.", [HANDLE]),
        "synthetic": {"type": "boolean", "enum": [True], "description": "Data are invented for this exercise."},
        "source": string_field("Fixture provenance.", ["fixture:schedule-v1"]),
        "timezone": string_field("Timezone of the listed class times.", ["Europe/Moscow"]),
        "note": string_field("Disclaimer about the synthetic dataset."),
        "entries": {
            "type": "array", "description": "Matching classes; empty when no classes match.",
            "items": {
                "type": "object", "description": "One class; detailed mode adds course, end and teacher.",
                "additionalProperties": False, "required": ["id", "day", "start", "room"],
                "properties": {
                    "id": string_field("Entry identifier for schedule_get."),
                    "course": string_field("Course identifier.", ["agents", "python", "databases"]),
                    "day": string_field("Class weekday.", ["monday", "tuesday", "wednesday"]),
                    "start": string_field("Start time HH:MM in the schedule timezone."),
                    "end": string_field("End time HH:MM in the schedule timezone."),
                    "room": string_field("Classroom number.", ["314", "210", "115"]),
                    "teacher": string_field("Synthetic teacher name."),
                },
            },
        },
    },
}


def error(code, message, hint):
    payload = {"code": code, "message": message, "hint": hint}
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, separators=(",", ":")))], is_error=True)


def result(rows, response_format):
    fields = ("id", "day", "start", "room")
    entries = [dict(row) if response_format == "detailed" else {k: row[k] for k in fields} for row in rows]
    payload = {"schedule_handle": HANDLE, "synthetic": True, "entries": entries}
    if response_format == "detailed":
        payload.update(source="fixture:schedule-v1", timezone="Europe/Moscow", note="Invented teaching data; not an actual course timetable.")
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, separators=(",", ":")))], structured_content=payload)


class ScheduleServer(MCPServer):
    """Validate the advertised closed schema at the public tool-call boundary."""

    async def list_tools(self):
        tools = await super().list_tools()
        for tool in tools:
            tool.input_schema["additionalProperties"] = False
            tool.input_schema["description"] = tool.description
            for field in tool.input_schema["properties"].values():
                if "const" in field:
                    field["enum"] = [field.pop("const")]
            tool.output_schema = OUTPUT_SCHEMA
        return tools

    async def call_tool(self, name, arguments, context=None):
        tools = {t.name: t for t in await self.list_tools()}
        if name not in tools:
            return error("unknown_tool", "Tool does not exist.", "Choose a schedule_* tool from tools/list.")
        issues = sorted(Draft202012Validator(tools[name].input_schema).iter_errors(arguments), key=lambda e: str(list(e.path)))
        if issues:
            locations = sorted({".".join(map(str, e.path)) or "arguments" for e in issues})
            return error("invalid_arguments", "Invalid fields: " + ", ".join(locations), "Use tools/list: supply required fields, enum values and correct types; remove extra fields.")
        try:
            return await super().call_tool(name, arguments, context)
        except Exception:
            return error("internal_error", "Could not read the schedule.", "Retry the same schedule_handle; if this persists, contact the server maintainer.")


server = ScheduleServer("Course schedule", version="1.0.0")
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)


@server.tool(annotations=READ_ONLY)
def schedule_search(schedule_handle: Handle, course: Course = "all", day: Day = "all", response_format: Format = "concise") -> CallToolResult:
    """Search the explicit synthetic schedule snapshot by course and weekday."""
    return result([r for r in ENTRIES if (course == "all" or r["course"] == course) and (day == "all" or r["day"] == day)], response_format)


@server.tool(annotations=READ_ONLY)
def schedule_get(schedule_handle: Handle, entry_id: EntryId, response_format: Format = "concise") -> CallToolResult:
    """Get one schedule entry; obtain entry_id using schedule_search."""
    rows = [r for r in ENTRIES if r["id"] == entry_id]
    if not rows:
        return error("entry_not_found", "Entry does not exist in this snapshot.", "Call schedule_search with the same schedule_handle and use an id from its entries.")
    return result(rows, response_format)


@server.tool(annotations=READ_ONLY)
def schedule_day(schedule_handle: Handle, day: Annotated[Literal["monday", "tuesday", "wednesday"], Field(description="Weekday to inspect.")], response_format: Format = "concise") -> CallToolResult:
    """List every scheduled class on one supported weekday."""
    return result([r for r in ENTRIES if r["day"] == day], response_format)


@server.tool(annotations=READ_ONLY)
def schedule_room(schedule_handle: Handle, room: Room, response_format: Format = "concise") -> CallToolResult:
    """List classes in one supported classroom."""
    return result([r for r in ENTRIES if r["room"] == room], response_format)


if __name__ == "__main__":
    server.run(transport="stdio")
