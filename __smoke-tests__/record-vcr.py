import hashlib
import json
import re
from urllib.parse import urlsplit, urlunsplit

from hotglue_smoke_test.vcr.tap import VCRTapTestRunner


class Runner(VCRTapTestRunner):
    FILTER_HEADERS = [
        *VCRTapTestRunner.FILTER_HEADERS,
        "cookie",
        "x-github-request-id",
        "x-oauth-client-id",
        "etag",
    ]
    TOKEN_KEYS = [*VCRTapTestRunner.TOKEN_KEYS, "private_key", "redirect_uri"]
    PRESERVE_KEYS = {
        "created_at",  # Incremental event boundary when updated_at is absent.
        "updated_at",  # Incremental early-stop boundary for sorted responses.
    }

    def __init__(self, test_case, script_dir):
        super().__init__(test_case, script_dir)
        self.catalog_attr = "properties"
        self._ids = {}

    def scrub_id(self, value):
        # Fixture-local aliases carry no original ID and cannot be GitHub IDs.
        if int(value) < 0:
            return value
        key = str(value)
        if key not in self._ids:
            self._ids[key] = -(len(self._ids) + 1)
        alias = self._ids[key]
        return str(alias) if isinstance(value, str) else alias

    def module(self) -> str:
        return "tap_github"

    def launch(self):
        from tap_github import main

        main()

    def scrub_uri(self, uri: str) -> str:
        parts = urlsplit(uri)
        path = parts.path.split("/")
        if parts.netloc == "api.github.com" and len(path) > 2:
            if (
                path[1]
                in {"repositories", "organizations", "orgs", "users", "user"}
                and path[2].isdigit()
            ):
                path[2] = self.scrub_id(path[2])
            count = {"repos": 2, "users": 1, "orgs": 1}.get(path[1], 0)
            for index in range(2, min(len(path), 2 + count)):
                if path[index] and not path[index].lstrip("-").isdigit():
                    digest = hashlib.sha256(
                        path[index].lower().encode()
                    ).hexdigest()
                    path[index] = "fake-" + digest[:12]
        return urlunsplit(parts._replace(path="/".join(path)))

    def before_record_response(self, response):
        response = super().before_record_response(response)
        for key, values in response["headers"].items():
            if key.lower() == "link":
                response["headers"][key] = [
                    re.sub(
                        r"<([^>]+)>",
                        lambda m: "<" + self.scrub_uri(m[1]) + ">",
                        value,
                    )
                    for value in values
                ]
        return response

    def scrub_response_body(self, body, faker, cache):
        original = json.loads(body)
        scrubbed = json.loads(super().scrub_response_body(body, faker, cache))

        def restore_references(raw, fake):
            if isinstance(raw, list):
                for item, replacement in zip(raw, fake):
                    restore_references(item, replacement)
            elif isinstance(raw, dict):
                url = raw.get("url", "")
                # The selected streams follow only these API URL shapes.
                if isinstance(url, str) and re.fullmatch(
                    r"https://api\.github\.com/"
                    r"(users/[^/]+|repos/[^/]+/[^/]+/pulls/\d+)",
                    url,
                ):
                    fake["url"] = self.scrub_uri(url)
                    if "/pulls/" in url and "number" in raw:
                        # Child PR endpoint paths.
                        fake["number"] = raw["number"]
                for key, value in raw.items():
                    if (key == "id" or key.endswith("_id")) and (
                        isinstance(value, int)
                        or isinstance(value, str)
                        and value.lstrip("-").isdigit()
                    ):
                        fake[key] = self.scrub_id(value)
                    elif isinstance(value, (dict, list)):
                        restore_references(value, fake[key])

        restore_references(original, scrubbed)
        return json.dumps(scrubbed)


if __name__ == "__main__":
    Runner.main()
