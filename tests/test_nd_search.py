"""Tests for scripts/nd_search.py against a local stub of the Search API.

    python -m unittest discover -s tests -v

The script runs as a subprocess, the way an agent runs it, and talks to a
ThreadingHTTPServer on 127.0.0.1 that records every request and answers
from a canned table. Nothing leaves the machine.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "nd_search.py")

QUOTA = {"pool": "search", "mode": "tier",
         "day": {"used": 3, "limit": 30, "remaining": 27, "reset_at": "2026-10-11T00:00:00+00:00"},
         "month": {"used": 9, "limit": 300, "remaining": 291, "reset_at": "2026-11-01T00:00:00+00:00"}}

OK = {
    ("POST", "/v1/search/web"): {"success": True, "total": 2, "query": "q", "cost": 15, "quota": QUOTA, "results": [
        {"index": 1, "title": "First", "url": "https://a.example/1", "content": "snippet one", "date": ""},
        {"index": 2, "title": "Second", "url": "https://b.example/2", "content": "snippet two", "date": "2026-01-02"},
    ]},
    ("POST", "/v1/search/read"): {"success": True, "title": "Page", "description": "", "url": "https://a.example/1",
                                  "content": "Привет, " + "x" * 500, "char_count": 508, "cost": 15,
                                  "provider_used": "fast", "quota": QUOTA},
    ("POST", "/v1/search/crawl"): {"success": True, "total": 2, "cost": 15, "quota": dict(QUOTA, pool="crawl"), "pages": [
        {"url": "https://a.example/", "title": "Home", "content": "home text", "char_count": 9},
        {"url": "https://a.example/docs", "title": "Docs", "content": "docs text", "char_count": 9},
    ]},
    ("GET", "/v1/search/tg"): {"total": 1, "query": "q", "quota": QUOTA, "results": [
        {"channel": "neuraldeep", "message_id": 1, "text": "line one\nline two", "date": "2026-10-01T10:00:00+00:00",
         "message_url": "https://t.me/neuraldeep/1", "score": 0.5, "source": "fts"},
    ]},
    ("GET", "/v1/search/quota"): {"tier": "free", "is_admin": False,
                                  "search": {"day": QUOTA["day"], "month": QUOTA["month"]},
                                  "crawl": {"day": {"used": 0, "limit": 3, "reset_at": "x"},
                                            "month": {"used": 0, "limit": 20, "reset_at": "y"}}},
}


class Stub:
    """Answers OK by default; `fail` maps a path to (status, body) for error cases."""

    def __init__(self):
        self.requests = []
        self.fail = {}
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _answer(self, method):
                parts = urlsplit(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"null") if length else None
                stub.requests.append({"method": method, "path": parts.path, "query": parse_qs(parts.query),
                                      "body": body, "auth": self.headers.get("Authorization")})
                if parts.path in stub.fail:
                    status, payload = stub.fail[parts.path]
                else:
                    status, payload = 200, OK.get((method, parts.path), {"detail": "Not Found"})
                    if (method, parts.path) not in OK:
                        status = 404
                raw = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                self._answer("GET")

            def do_POST(self):
                self._answer("POST")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class NdSearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stub = Stub()

    @classmethod
    def tearDownClass(cls):
        cls.stub.close()

    def setUp(self):
        self.stub.requests.clear()
        self.stub.fail.clear()

    def run_script(self, *argv, key="sk-env-key", extra_env=None):
        env = {k: v for k, v in os.environ.items()
               if k.upper() not in ("NEURALDEEP_API_KEY", "NEURALDEEP_BASE_URL")}
        env["NEURALDEEP_BASE_URL"] = self.stub.url
        if key is not None:
            env["NEURALDEEP_API_KEY"] = key
        # A dead proxy: the script must ignore it.
        env.update({"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
                    "http_proxy": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9",
                    "ALL_PROXY": "http://127.0.0.1:9", "NO_PROXY": "", "no_proxy": ""})
        env.update(extra_env or {})
        return subprocess.run([sys.executable, SCRIPT, *argv], env=env, capture_output=True,
                              text=True, encoding="utf-8", timeout=60)

    # key source

    def test_key_from_environment(self):
        r = self.run_script("quota")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.stub.requests[-1]["auth"], "Bearer sk-env-key")

    def test_api_key_option_wins_over_environment(self):
        r = self.run_script("quota", "--api-key", "sk-flag-key")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.stub.requests[-1]["auth"], "Bearer sk-flag-key")

    def test_api_key_option_before_the_command(self):
        r = self.run_script("--api-key", "sk-front-key", "quota", key=None)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.stub.requests[-1]["auth"], "Bearer sk-front-key")

    def test_no_key_is_a_usage_error_without_a_request(self):
        r = self.run_script("quota", key=None)
        self.assertEqual(r.returncode, 2)
        self.assertIn("NEURALDEEP_API_KEY", r.stderr)
        self.assertEqual(self.stub.requests, [])

    # commands

    def test_web_sends_query_and_limit_and_prints_results(self):
        r = self.run_script("web", "llm news", "-n", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        req = self.stub.requests[-1]
        self.assertEqual((req["method"], req["path"]), ("POST", "/v1/search/web"))
        self.assertEqual(req["body"], {"query": "llm news", "limit": 2})
        self.assertIn("[1] First", r.stdout)
        self.assertIn("https://b.example/2", r.stdout)
        self.assertIn("(2026-01-02)", r.stdout)
        self.assertIn("quota search: day 3/30, month 9/300", r.stderr)

    def test_web_limit_outside_1_to_10_is_refused_locally(self):
        r = self.run_script("web", "x", "-n", "11")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.stub.requests, [])

    def test_read_text_format_and_max_chars(self):
        r = self.run_script("read", "https://a.example/1", "--text", "--max-chars", "20")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.stub.requests[-1]["body"], {"url": "https://a.example/1", "return_format": "text"})
        self.assertIn("path: fast", r.stdout)
        self.assertIn("Привет", r.stdout)
        self.assertIn("[cut, 508 characters in total]", r.stdout)

    def test_read_markdown_is_the_default(self):
        r = self.run_script("read", "https://a.example/1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.stub.requests[-1]["body"], {"url": "https://a.example/1"})

    def test_crawl_sends_limit_and_prints_pages(self):
        r = self.run_script("crawl", "https://a.example/", "-n", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.stub.requests[-1]["body"], {"url": "https://a.example/", "limit": 2})
        self.assertIn("## [2] Docs", r.stdout)
        self.assertIn("quota crawl:", r.stderr)

    def test_tg_passes_filters_as_query_string(self):
        r = self.run_script("tg", "MTP", "-n", "3", "--channels", "neuraldeep", "--sort", "date_desc",
                            "--from", "2026-01-01")
        self.assertEqual(r.returncode, 0, r.stderr)
        q = self.stub.requests[-1]["query"]
        self.assertEqual(q["q"], ["MTP"])
        self.assertEqual(q["limit"], ["3"])
        self.assertEqual(q["channels"], ["neuraldeep"])
        self.assertEqual(q["sort_by"], ["date_desc"])
        self.assertEqual(q["date_from"], ["2026-01-01"])
        self.assertNotIn("date_to", q)
        self.assertIn("[neuraldeep] 2026-10-01 https://t.me/neuraldeep/1", r.stdout)
        self.assertIn("line one line two", r.stdout)

    def test_json_prints_the_answer_as_is(self):
        r = self.run_script("web", "x", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["results"][0]["title"], "First")

    def test_quota_lists_both_pools(self):
        r = self.run_script("quota")
        self.assertIn("search day: 3/30", r.stdout)
        self.assertIn("crawl month: 0/20", r.stdout)

    # errors

    def assert_exit(self, path, status, payload, code, needle, *argv):
        self.stub.fail[path] = (status, payload)
        r = self.run_script(*argv)
        self.assertEqual(r.returncode, code, (r.stdout, r.stderr))
        self.assertIn(needle, r.stderr)

    def test_rejected_requests_exit_3(self):
        for status, detail in ((400, "Internal URLs are blocked"), (404, "the site answered 404"),
                               (422, "No content could be extracted")):
            with self.subTest(status=status):
                self.assert_exit("/v1/search/read", status, {"detail": detail}, 3,
                                 "HTTP %d: %s" % (status, detail), "read", "https://a.example/x")

    def test_quota_exhausted_exits_4_with_reset_time(self):
        body = {"error": {"type": "quota_exceeded", "pool": "crawl", "scope": "day", "used": 3, "limit": 3,
                          "tier": "free", "reset_at": "2026-10-11T00:00:00+00:00"}}
        self.assert_exit("/v1/search/crawl", 429, body, 4, "resets at 2026-10-11T00:00:00+00:00",
                         "crawl", "https://a.example/")

    def test_access_denied_exits_5(self):
        self.assert_exit("/v1/search/web", 401, {"detail": "Invalid API key"}, 5, "Invalid API key", "web", "x")
        self.assert_exit("/v1/search/web", 402, {"detail": "wallet is empty"}, 5, "HTTP 402", "web", "x")

    def test_platform_failures_exit_6(self):
        for status in (502, 503):
            with self.subTest(status=status):
                self.assert_exit("/v1/search/web", status, {"detail": "unavailable"}, 6,
                                 "HTTP %d" % status, "web", "x")

    def test_non_json_answer_exits_6(self):
        self.assert_exit("/v1/search/web", 200, "<html>oops</html>", 6, "non-JSON", "web", "x")

    def test_unreachable_api_exits_6(self):
        r = self.run_script("quota", "--base-url", "http://127.0.0.1:9", "--timeout", "5")
        self.assertEqual(r.returncode, 6, r.stderr)
        self.assertIn("network", r.stderr)


if __name__ == "__main__":
    unittest.main()
