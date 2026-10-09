import json

import pytest
from jsonschema import Draft202012Validator

from client import META, PROTOCOL, WireClient

CASES = [
    ("schedule_search", {"course": "agents"}, ["agents-mon", "agents-wed"]),
    ("schedule_get", {"entry_id": "agents-mon"}, ["agents-mon"]),
    ("schedule_day", {"day": "wednesday"}, ["databases-wed", "agents-wed"]),
    ("schedule_room", {"room": "210"}, ["python-tue"]),
]


@pytest.fixture(scope="module")
def client():
    with WireClient() as connection:
        yield connection


@pytest.mark.parametrize("name,args,ids", CASES)
@pytest.mark.parametrize("response_format", ["concise", "detailed"])
def test_success(client, name, args, ids, response_format):
    answer = client.call(name, {"schedule_handle": "schedule-v1", **args, "response_format": response_format})
    assert not answer.get("isError", False)
    payload = answer["structuredContent"]
    assert [e["id"] for e in payload["entries"]] == ids
    assert payload["synthetic"] is True
    assert ("teacher" in payload["entries"][0]) == (response_format == "detailed")
    assert json.loads(answer["content"][0]["text"]) == payload
    schema = next(t["outputSchema"] for t in client.request("tools/list")["tools"] if t["name"] == name)
    Draft202012Validator(schema).validate(payload)


@pytest.mark.parametrize("name,args,_", CASES)
@pytest.mark.parametrize("invalid", [{"schedule_handle": "missing"}, {"response_format": "xml"}, {"unexpected": 1}])
def test_error(client, name, args, _, invalid):
    answer = client.call(name, {"schedule_handle": "schedule-v1", **args, **invalid})
    assert answer["isError"] is True
    message = json.loads(answer["content"][0]["text"])
    assert message["hint"]
    assert "Traceback" not in answer["content"][0]["text"]


@pytest.mark.parametrize("name,args", [("schedule_get", {"entry_id": "unknown"}), ("schedule_day", {"day": "friday"}), ("schedule_room", {"room": 314}), ("schedule_search", {"course": "unknown"})])
def test_domain_errors(client, name, args):
    answer = client.call(name, {"schedule_handle": "schedule-v1", **args})
    assert answer["isError"]
    assert json.loads(answer["content"][0]["text"])["hint"]


def test_discovery_schema_and_metadata(client):
    discovery = client.request("server/discover")
    assert PROTOCOL in discovery["supportedVersions"]
    assert "tools" in discovery["capabilities"]
    tools = client.request("tools/list")["tools"]
    assert {t["name"] for t in tools} == {case[0] for case in CASES}
    for tool in tools:
        schema = tool["inputSchema"]
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False
        for field in schema["properties"].values():
            assert field["description"]
        assert schema["properties"]["response_format"]["enum"] == ["concise", "detailed"]
        check_closed_schema(tool["outputSchema"])
    assert all(item["request"]["params"]["_meta"] == META for item in client.trace if "request" in item)


def test_call_before_discovery_and_missing_handle():
    with WireClient() as fresh:
        assert not fresh.call("schedule_search", {"schedule_handle": "schedule-v1"}).get("isError", False)
        assert fresh.call("schedule_search", {})["isError"]
        assert fresh.call("unknown_tool", {})["isError"]


def test_snapshot_survives_restart(client):
    first = client.call("schedule_get", {"schedule_handle": "schedule-v1", "entry_id": "agents-mon"})
    with WireClient() as other:
        second = other.call("schedule_get", {"schedule_handle": "schedule-v1", "entry_id": "agents-mon"})
    assert first["structuredContent"] == second["structuredContent"]


def check_closed_schema(schema):
    if schema.get("type") == "object":
        assert schema["additionalProperties"] is False
        for field in schema["properties"].values():
            assert field["description"]
            check_closed_schema(field)
    if schema.get("type") == "array":
        check_closed_schema(schema["items"])


def test_no_matches(client):
    answer = client.call("schedule_search", {"schedule_handle": "schedule-v1", "course": "python", "day": "monday"})
    assert not answer.get("isError", False)
    assert answer["structuredContent"]["entries"] == []
