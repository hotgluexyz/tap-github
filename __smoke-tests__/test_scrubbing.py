import base64
import json
import runpy
from pathlib import Path

from faker import Faker

Runner = runpy.run_path(str(Path(__file__).with_name("record-vcr.py")))[
    "Runner"
]


def test_numeric_ids_and_pagination_share_nonidentifying_aliases():
    runner = Runner("repositories-as-objects_test", str(Path(__file__).parent))
    node_id = base64.b64encode(b"04:User121").decode()
    raw = {
        "id": 245,
        "owner": {"id": 121, "node_id": node_id},
        "actor": {"id": "121"},
        "repository_id": 245,
        "number": 19,
        "created_at": "2025-01-02T03:04:05Z",
    }
    fake = json.loads(runner.scrub_response_body(json.dumps(raw), Faker(), {}))
    assert fake["id"] < 0
    assert fake["owner"]["id"] < 0
    assert fake["id"] != fake["owner"]["id"]
    assert fake["actor"]["id"] == str(fake["owner"]["id"])
    assert fake["repository_id"] == fake["id"]
    assert node_id not in json.dumps(fake)
    assert "04:User121" not in json.dumps(fake)
    assert fake["created_at"] == raw["created_at"]

    for prefix, original, alias in (
        ("repositories", 245, fake["id"]),
        ("orgs", 121, fake["owner"]["id"]),
        ("organizations", 121, fake["owner"]["id"]),
        ("users", 121, fake["owner"]["id"]),
        ("user", 121, fake["owner"]["id"]),
    ):
        uri = f"https://api.github.com/{prefix}/{original}/members?page=2"
        expected = f"https://api.github.com/{prefix}/{alias}/members?page=2"
        assert runner.scrub_uri(uri) == expected
        assert runner.scrub_uri(expected) == expected
        response = runner.before_record_response(
            {"headers": {"Link": [f'<{uri}>; rel="next"']}}
        )
        assert response["headers"]["Link"] == [f'<{expected}>; rel="next"']

    # PR numbers are endpoint selectors, not globally identifying entity IDs.
    pr = {
        "id": 377,
        "number": 19,
        "url": "https://api.github.com/repos/example/project/pulls/19",
    }
    fake_pr = json.loads(
        runner.scrub_response_body(json.dumps(pr), Faker(), {})
    )
    assert fake_pr["id"] < 0
    assert fake_pr["number"] == 19
    assert fake_pr["url"].endswith("/pulls/19")
