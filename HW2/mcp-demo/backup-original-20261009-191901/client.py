"""Exercise real stdio discovery, calls and errors without an LLM or TCP port."""
import asyncio
import importlib.metadata
import json
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters


async def demo():
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name('server.py'))],
    )
    async with Client(parameters) as client:
        discovered = await client.list_tools()
        names = sorted(t.name for t in discovered.tools)
        assert names == ['add', 'lookup_schedule']
        summed = await client.call_tool('add', {'a': 7, 'b': 5})
        assert not summed.is_error and summed.structured_content == {'result': 12}
        entry = await client.call_tool('lookup_schedule', {'course': 'agents'})
        assert not entry.is_error and entry.structured_content['room'] == '314'
        assert entry.structured_content['synthetic'] is True
        bad = await client.call_tool('add', {'a': 'not-an-integer', 'b': 5})
        assert bad.is_error
        numeric_string = await client.call_tool('add', {'a': '7', 'b': 5})
        assert numeric_string.is_error
        missing = await client.call_tool('unknown_tool', {})
        assert missing.is_error
        resource = await client.read_resource('course://about')
        assert resource.contents
        return {
            'sdk': importlib.metadata.version('mcp'),
            'protocol': client.protocol_version,
            'transport': 'stdio subprocess',
            'tools': names,
            'sum': summed.structured_content,
            'schedule': entry.structured_content,
            'invalid_arguments_rejected': bool(bad.is_error),
            'numeric_string_rejected': bool(numeric_string.is_error),
            'unknown_tool_rejected': bool(missing.is_error),
            'resource_read': True,
            'llm_calls': 0,
        }


if __name__ == '__main__':
    print(json.dumps(asyncio.run(asyncio.wait_for(demo(), timeout=20)), ensure_ascii=False, indent=2))
