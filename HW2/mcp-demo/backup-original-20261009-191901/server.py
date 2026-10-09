"""A real local MCP server. All schedule data are invented for the exercise."""
from pydantic import BaseModel, StrictInt
from mcp.server import MCPServer

server = MCPServer('Course tools')


class ScheduleEntry(BaseModel):
    course: str
    room: str
    source: str
    synthetic: bool = True


@server.tool()
def lookup_schedule(course: str) -> ScheduleEntry:
    """Read the synthetic course schedule. Supported key: agents."""
    if course != 'agents':
        raise ValueError('Unknown course')
    return ScheduleEntry(course=course, room='314', source='fixture:schedule-v1')


@server.tool()
def add(a: StrictInt, b: StrictInt) -> int:
    """Add two integer arguments."""
    return a + b


@server.resource('course://about')
def about() -> str:
    return 'Учебная синтетическая среда; реального расписания здесь нет.'


if __name__ == '__main__':
    server.run(transport='stdio')
