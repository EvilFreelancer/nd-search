#!/usr/bin/env python3
"""Web search, page reading and site crawling through the NeuralDeep Search API.

A thin client for api.neuraldeep.ru/v1/search/* meant for agents. The API key
comes from --api-key or, when that is not given, from NEURALDEEP_API_KEY. Proxy
variables from the environment are ignored on purpose: a corporate or local
HTTPS_PROXY tends to break these calls, and the API is reachable directly.
Answers are printed as compact text, or as the raw JSON with --json.
Python 3.8+ standard library only; Linux, macOS and Windows.

    nd_search.py web "query" [-n 5]
    nd_search.py read URL [--text] [--max-chars N]
    nd_search.py crawl URL [-n 3] [--max-chars N]
    nd_search.py tg "query" [-n 5] [--channels a,b] [--sort date_desc]
    nd_search.py quota

Exit codes: 0 success, 2 bad arguments or no API key, 3 request rejected
(400, 404, 413, 415, 422), 4 quota exhausted (429), 5 access denied
(401, 402, 403), 6 platform or network failure (5xx, timeout, broken answer).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE_URL = "https://api.neuraldeep.ru"
# The API gives up on its upstream after 60 s and answers 502 itself.
DEFAULT_TIMEOUT = 90

EXIT_OK, EXIT_USAGE, EXIT_REJECTED, EXIT_QUOTA, EXIT_ACCESS, EXIT_FAILURE = 0, 2, 3, 4, 5, 6
_REJECTED = {400, 404, 413, 415, 422}
_ACCESS = {401, 402, 403}


class ApiError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _opener() -> urllib.request.OpenerDirector:
    # An empty ProxyHandler disables HTTP(S)_PROXY and ALL_PROXY from the environment.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(args: argparse.Namespace, method: str, path: str, *,
         body: dict | None = None, params: dict | None = None) -> dict:
    key = (args.api_key or os.environ.get("NEURALDEEP_API_KEY") or "").strip()
    if not key:
        raise ApiError(EXIT_USAGE, "no API key: pass --api-key or set NEURALDEEP_API_KEY")
    base = (args.base_url or os.environ.get("NEURALDEEP_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    url = base + path
    if params:
        query = {k: v for k, v in params.items() if v not in (None, "")}
        url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "nd-search-skill/1",
    })
    try:
        with _opener().open(req, timeout=args.timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise _http_error(e) from None
    except (urllib.error.URLError, OSError) as e:
        raise ApiError(EXIT_FAILURE, "network: %s" % (getattr(e, "reason", None) or e)) from None
    try:
        return json.loads(raw)
    except ValueError:
        raise ApiError(EXIT_FAILURE, "the API returned non-JSON: %.200s" % raw) from None


def _http_error(e: urllib.error.HTTPError) -> ApiError:
    raw = e.read().decode("utf-8", "replace")
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = raw.strip()[:300]
    if e.code == 429:
        err = payload.get("error", {}) if isinstance(payload, dict) else {}
        return ApiError(EXIT_QUOTA, "HTTP 429: %s quota of pool %s is used up (%s/%s), resets at %s" % (
            err.get("scope"), err.get("pool"), err.get("used"), err.get("limit"), err.get("reset_at")))
    detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
    message = "HTTP %d: %s" % (e.code, detail)
    if e.code in _REJECTED:
        return ApiError(EXIT_REJECTED, message)
    if e.code in _ACCESS:
        return ApiError(EXIT_ACCESS, message)
    return ApiError(EXIT_FAILURE, message)


def clip(text: str, max_chars: int) -> str:
    if max_chars and len(text) > max_chars:
        return text[:max_chars] + "\n...[cut, %d characters in total]" % len(text)
    return text


def quota_line(data: dict) -> str:
    q = data.get("quota") or {}
    day, month = q.get("day") or {}, q.get("month") or {}
    if not day:
        return ""
    return "quota %s: day %s/%s, month %s/%s" % (
        q.get("pool"), day.get("used"), day.get("limit"), month.get("used"), month.get("limit"))


def cmd_web(args: argparse.Namespace) -> dict:
    data = call(args, "POST", "/v1/search/web", body={"query": args.query, "limit": args.n})
    if args.json:
        return data
    results = data.get("results") or []
    if not results:
        print("nothing found")
    for r in results:
        date = " (%s)" % r["date"] if r.get("date") else ""
        print("[%s] %s%s\n    %s" % (r.get("index"), r.get("title", ""), date, r.get("url", "")))
        if r.get("content"):
            print("    " + r["content"])
    return data


def cmd_read(args: argparse.Namespace) -> dict:
    body = {"url": args.url}
    if args.text:
        body["return_format"] = "text"
    data = call(args, "POST", "/v1/search/read", body=body)
    if args.json:
        return data
    print("# " + (data.get("title") or "(no title)"))
    print("url: %s | path: %s | characters: %s\n" % (
        data.get("url"), data.get("provider_used") or "-", data.get("char_count")))
    print(clip(data.get("content") or "", args.max_chars))
    return data


def cmd_crawl(args: argparse.Namespace) -> dict:
    data = call(args, "POST", "/v1/search/crawl", body={"url": args.url, "limit": args.n})
    if args.json:
        return data
    for i, page in enumerate(data.get("pages") or [], 1):
        print("## [%d] %s" % (i, page.get("title") or "(no title)"))
        print("url: %s | characters: %s\n" % (page.get("url"), page.get("char_count")))
        print(clip(page.get("content") or "", args.max_chars) + "\n")
    return data


def cmd_tg(args: argparse.Namespace) -> dict:
    data = call(args, "GET", "/v1/search/tg", params={
        "q": args.query, "limit": args.n, "channels": args.channels, "categories": args.categories,
        "sources": args.sources, "sort_by": args.sort, "date_from": args.date_from, "date_to": args.date_to,
    })
    if args.json:
        return data
    results = data.get("results") or []
    if not results:
        print("nothing found")
    for r in results:
        print("[%s] %s %s" % (r.get("channel"), (r.get("date") or "")[:10], r.get("message_url") or ""))
        print("    " + clip((r.get("text") or "").replace("\n", " "), args.max_chars))
    return data


def cmd_quota(args: argparse.Namespace) -> dict:
    data = call(args, "GET", "/v1/search/quota")
    if args.json:
        return data
    print("tier: %s" % data.get("tier"))
    for pool in ("search", "crawl"):
        p = data.get(pool) or {}
        for scope in ("day", "month"):
            s = p.get(scope) or {}
            print("%s %s: %s/%s, resets at %s" % (pool, scope, s.get("used"), s.get("limit"), s.get("reset_at")))
    return data


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--api-key", default=argparse.SUPPRESS,
                        help="sk- key; when omitted, NEURALDEEP_API_KEY is used")
    common.add_argument("--base-url", default=argparse.SUPPRESS,
                        help="API root; when omitted, NEURALDEEP_BASE_URL or %s" % DEFAULT_BASE_URL)
    common.add_argument("--timeout", type=float, default=argparse.SUPPRESS,
                        help="seconds to wait for the answer (default %d)" % DEFAULT_TIMEOUT)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="print the API answer as is")

    ap = argparse.ArgumentParser(prog="nd_search.py", parents=[common],
                                 description="NeuralDeep Search API: web, read, crawl, tg, quota")
    sub = ap.add_subparsers(dest="cmd")
    sub.required = True
    limit = dict(type=int, choices=range(1, 11), metavar="1..10")

    p = sub.add_parser("web", parents=[common], help="search the web")
    p.add_argument("query")
    p.add_argument("-n", default=5, help="number of results (default 5)", **limit)
    p.set_defaults(fn=cmd_web)

    p = sub.add_parser("read", parents=[common], help="the text of one page")
    p.add_argument("url")
    p.add_argument("--text", action="store_true", help="plain text instead of markdown")
    p.add_argument("--max-chars", type=int, default=0, help="cut the printed text (0 = whole page)")
    p.set_defaults(fn=cmd_read)

    p = sub.add_parser("crawl", parents=[common], help="the start page and pages of the same site")
    p.add_argument("url")
    p.add_argument("-n", default=3, help="pages including the start one (default 3)", **limit)
    p.add_argument("--max-chars", type=int, default=4000, help="cut each page (0 = whole page)")
    p.set_defaults(fn=cmd_crawl)

    p = sub.add_parser("tg", parents=[common], help="search the Telegram channel database")
    p.add_argument("query")
    p.add_argument("-n", type=int, default=5, help="number of posts (default 5)")
    p.add_argument("--channels", help="channel usernames, comma separated, without @")
    p.add_argument("--categories", help="categories, comma separated")
    p.add_argument("--sources", help="vector,fts,files (default vector,fts)")
    p.add_argument("--sort", choices=("relevance", "date_desc", "date_asc"))
    p.add_argument("--from", dest="date_from", help="ISO date, from")
    p.add_argument("--to", dest="date_to", help="ISO date, to")
    p.add_argument("--max-chars", type=int, default=300, help="cut each post (0 = whole post)")
    p.set_defaults(fn=cmd_tg)

    p = sub.add_parser("quota", parents=[common], help="what is left in both quota pools")
    p.set_defaults(fn=cmd_quota)
    return ap


def _utf8_streams() -> None:
    # A pipe on Windows gets the ANSI code page, which cannot print most of the web.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and not stream.isatty():
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _utf8_streams()
    args = build_parser().parse_args(argv)
    for name, default in (("api_key", None), ("base_url", None), ("timeout", DEFAULT_TIMEOUT), ("json", False)):
        if not hasattr(args, name):
            setattr(args, name, default)
    try:
        data = args.fn(args)
    except ApiError as e:
        print(str(e), file=sys.stderr)
        return e.code
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.cmd != "quota":
        line = quota_line(data)
        if line:
            print(line, file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
