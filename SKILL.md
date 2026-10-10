---
name: nd-search
description: >
  Use when the agent needs to search the web, read the text of a page by its URL, crawl a few
  pages of one site, or search Telegram channels through the NeuralDeep Search API
  (api.neuraldeep.ru/v1/search/*) with an sk- key. A standard-library Python client takes the key
  from --api-key or NEURALDEEP_API_KEY and prints compact text or the raw JSON. Triggers: "найди в
  интернете", "погугли", "прочитай страницу", "вытащи текст по ссылке", "search the web", "read
  this URL", "crawl the docs".
metadata:
  version: 1.0.0
  author: Pavel Rykov <paul@drteam.rocks>
  homepage: https://github.com/EvilFreelancer/nd-search
---

# NeuralDeep search: web, page reading, crawl

NeuralDeep sells search separately from its models. The endpoints under
`https://api.neuraldeep.ru/v1/search/*` take the same `sk-` key as the chat API and count their own
quota, so they never eat into the LLM limits. Every plan has them, the free one included, except the
API-only Coder plan.

All calls go through `scripts/nd_search.py` next to this file. It needs only Python 3.8+.

- **API key.** `--api-key sk-...` when given, otherwise the `NEURALDEEP_API_KEY` environment
  variable. Prefer the variable: a key on the command line lands in the shell history and in the
  process list. Never print the key or paste it into answers.
- **Proxy.** The script ignores `HTTPS_PROXY`, `HTTP_PROXY` and `ALL_PROXY` on purpose, because the
  API is reachable directly and a local proxy tends to break these calls.
- **Output.** Compact text on stdout and one line with the pool's remaining quota on stderr;
  `--json` prints the API answer as is.

```bash
S=scripts/nd_search.py          # path relative to this skill's folder
export NEURALDEEP_API_KEY=...   # once per shell, or pass --api-key
```

## Which command

| task | command | endpoint | quota pool |
|---|---|---|---|
| find pages on a topic | `python3 $S web "query" -n 5` | `POST /v1/search/web` `{query, limit}` | search |
| the text of one page | `python3 $S read URL` | `POST /v1/search/read` `{url, return_format}` | search |
| several pages of one site | `python3 $S crawl URL -n 3` | `POST /v1/search/crawl` `{url, limit}` | crawl |
| what Telegram channels wrote | `python3 $S tg "query"` | `GET /v1/search/tg?q=&limit=` | search |
| what is left | `python3 $S quota` | `GET /v1/search/quota` | free of charge |

## Workflow

Search snippets are short, about 150 characters, and as a rule they only help to pick a link. Take
facts and quotes from the page text:

1. `web` for 3-5 results; from the titles and snippets pick one to three links. If the titles are
   off-topic, rephrase the query with more specific words instead of reading the junk;
2. `read` each picked link; look at long pages with `--max-chars` so they do not flood the context;
3. a page that answered 404 or 422 will answer the same again, so take the next link from the results;
4. `crawl` only when a whole section of a site is needed, such as documentation.

For a single page use `read`, not `crawl`. Crawling draws on its own pool, about ten times smaller
than the search pool by the daily limit and smaller still by the monthly one, and with a wallet a
crawl call costs more than a read. When you do crawl, remember that links are taken in the order they
appear on the start page, so menus, other versions and language copies often come first: the second
page of `docs.vllm.ai/en/latest/` is `/en/stable`.

## Commands

```bash
python3 $S web "vllm speculative decoding" -n 5         # 1..10 results
python3 $S read https://docs.vllm.ai/en/latest/features/spec_decode.html --max-chars 4000
python3 $S read URL --text                               # plain text instead of markdown
python3 $S crawl https://docs.vllm.ai/en/latest/ -n 3    # the start page and up to two more
python3 $S tg "MTP 4090" -n 5 --sort date_desc --channels neuraldeep --from 2026-01-01
python3 $S quota
python3 $S read URL --json | jq -r .content              # the raw answer
python3 $S web "query" --api-key "$OTHER_KEY"            # explicit key wins over the variable
```

By default `crawl` cuts each page to 4000 characters and `tg` each post to 300; `read` prints the
whole page. `--max-chars 0` removes the cut. `--timeout` (default 90 s) and `--base-url` (or
`NEURALDEEP_BASE_URL`) are there for unusual setups.

Exit codes: `0` success, `2` bad arguments or no key, `3` the request was rejected (400, 404, 413,
415, 422), `4` the quota is used up (429), `5` access denied (401, 402, 403), `6` platform or network failure (5xx, timeout, broken answer). The message on stderr
says which case it is.

## What comes back

- `web` returns `results[]` with `index`, `title`, `url`, `content` (the snippet) and `date`, plus `total` and `query`;
- `read` returns `title`, `description`, `content` (markdown, or plain text with `return_format: text`), `url`, `char_count` and `provider_used`;
- `crawl` returns `pages[]` with `url`, `title`, `content` and `char_count`, plus `total`;
- `tg` returns `results[]` with `channel`, `message_id`, `text` (up to 500 characters), `date`, `message_url`, `score` and `source`, and accepts `q`, `limit`, `sources` (`vector,fts,files`), `channels`, `categories`, `date_from`, `date_to` and `sort_by` (`relevance`, `date_desc`, `date_asc`);
- every answer carries `quota` with what is left in the pool for the day and for the month.

`provider_used` names the extraction path: `fast` (a plain GET and text extractors), `reader` (a paid
reading service) or `browser` (a headless browser). The text of a page in `read` and `crawl` is cut at
50 000 characters. The `cost` field shows internal credits of the upstream, always 15, and has nothing
to do with roubles.

## Errors

| HTTP | when | what to do |
|---|---|---|
| 400 | no `query` or `url`, broken JSON, an internal address (`127.0.0.1`, private networks) | fix the request |
| 401 | the key is missing or not accepted | check the key |
| 404 | the site itself answered 404 or 410 | the link is dead, do not retry |
| 422 | the page opened but has no text (anti-bot wall, empty SPA) | take another link |
| 422 | `limit` outside 1..10 (the script refuses it before sending) | fix the request |
| 429 | the daily or monthly limit of the pool is used up; the body has `pool`, `scope`, `reset_at` | wait for `reset_at` or `Retry-After` |
| 502 | every source failed, or the upstream did not answer within 60 s | retry once, a minute later |
| 503 | a failure on the platform side | retry later |

## Quota and money

- quota is counted in requests, not results: `web -n 10` costs the same as `-n 1`;
- the `search` pool is shared by web, read and tg; `crawl` has its own;
- a quota unit is spent on every admitted request, including ones that end in 404, 422 or 502, while a wallet is charged only for a successful answer (HTTP 200), at the per-call rates shown in the dashboard;
- tier limits apply to subscriptions; a pay-as-you-go wallet with money has no tier cap, and an empty wallet does not block search: the call is served from the plan's quota and nothing is charged;
- the daily counter resets at 00:00 UTC, the monthly one on the 1st;
- the API-only Coder plan has no search: without money in the wallet the very first call gets 429;
- the free plan searches and reads only through free sources, so it gets empty results and 422 more often; a page that gives 422 on the free plan may open on a paid one.

## Gotchas

- `web` usually answers in under two seconds (five probes on 10.10.26 took 0.7-1.5 s), but a call can take about 10 s; `read` takes 1-5 s, `crawl` up to a minute;
- now and then the results are off-topic for narrow technical queries; check the titles before reading and add context words to the query;
- some anti-bot sites (Wildberries) open by no path at all and always answer 422; others, such as large marketplaces and client-side SPAs, open only through the paid path;
- the `provider` and `region` fields in the `web` and `read` bodies are deprecated and ignored, the source cannot be chosen;
- `GET /v1/search/health` answers without a key and shows whether the service itself is up.

Human documentation: <https://neuraldeep.ru/docs#search>. Keys are issued in the dashboard at
<https://neuraldeep.ru>.
