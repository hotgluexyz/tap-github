import json
import unittest
from pathlib import Path
from unittest import mock

import requests

import tap_github


class TestPullRequestFileIdentity(unittest.TestCase):
    def test_identity_distinguishes_paths_and_survives_content_changes(self):
        schema = json.loads(
            (
                Path(tap_github.__file__).parent
                / "schemas/pull_request_files.json"
            ).read_text()
        )
        files = [
            {"filename": "src/first.py", "sha": "a" * 40},
            {"filename": "src/second.py", "sha": "a" * 40},
        ]
        changed = [{"filename": "src/first.py", "sha": "b" * 40}]
        outputs = []
        for pr_id, payload in ((17, files), (17, changed), (23, files)):
            response = requests.Response()
            response.status_code = 200
            response._content = json.dumps(payload).encode()
            with mock.patch(
                "requests.Session.request", return_value=response
            ), mock.patch(
                "singer.utils.parse_args", return_value=mock.Mock(config={})
            ):
                outputs.append(
                    list(
                        tap_github.get_pull_request_files(
                            4, pr_id, schema, "example/project", {}, []
                        )
                    )
                )

        first, updated, other_pr = outputs
        self.assertEqual(
            [row["filename"] for row in first],
            ["src/first.py", "src/second.py"],
        )
        self.assertEqual(len({row["id"] for row in first}), 2)
        self.assertEqual(first[0]["id"], updated[0]["id"])
        self.assertNotEqual(first[0]["id"], other_pr[0]["id"])
        self.assertEqual(updated[0]["sha"], "b" * 40)
