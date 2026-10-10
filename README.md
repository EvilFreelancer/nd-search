# nd-search

**`/nd-search`** lets an AI agent search the web, read the clean text of a page by URL, crawl a few
pages of one site and search Telegram channels through the
[NeuralDeep](https://neuraldeep.ru) Search API (`api.neuraldeep.ru/v1/search/*`), with the same `sk-`
key as the NeuralDeep chat API.

The skill gives the agent a workflow (search, then read the picked links, crawl only a whole section)
and a small client, `scripts/nd_search.py`, that turns each call into one command with compact output
and meaningful exit codes.

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Agent instructions (frontmatter `name`, `description`, `metadata.version`). |
| `scripts/nd_search.py` | The client: `web`, `read`, `crawl`, `tg`, `quota`. Python 3.8+ standard library only. |
| `tests/test_nd_search.py` | Unit tests against a local stub of the API: `python -m unittest discover -s tests -v`. |

## Usage

```bash
export NEURALDEEP_API_KEY=sk-...        # or pass --api-key to any command

python3 scripts/nd_search.py web "vllm speculative decoding" -n 5
python3 scripts/nd_search.py read https://docs.vllm.ai/en/latest/features/spec_decode.html --max-chars 4000
python3 scripts/nd_search.py crawl https://docs.vllm.ai/en/latest/ -n 3
python3 scripts/nd_search.py tg "RAG in production" -n 5 --sort date_desc
python3 scripts/nd_search.py quota
python3 scripts/nd_search.py read https://example.com --json    # the raw API answer
```

The key is taken from `--api-key` when given, otherwise from `NEURALDEEP_API_KEY`. The client ignores
proxy variables from the environment and talks to the API directly.

Exit codes: `0` success, `2` bad arguments or no key, `3` request rejected (400, 404, 413, 415, 422),
`4` quota used up (429), `5` access denied (401, 402, 403), `6` platform or network failure.

Every NeuralDeep plan except the API-only Coder includes search, the free one too, with a quota of
its own that does not touch the LLM limits. Endpoints, fields, errors and quota rules are described
in `SKILL.md` and in the [NeuralDeep docs](https://neuraldeep.ru/docs#search).

## Install

The repository is the skill folder: `SKILL.md` lives at its root. Clone it into the skill root of your agent:

```bash
git clone https://github.com/EvilFreelancer/nd-search.git ~/.claude/skills/nd-search
```

| Tool          | Path                          |
|---------------|-------------------------------|
| Claude Code   | `~/.claude/skills/nd-search/` |
| Cursor        | `~/.cursor/skills/nd-search/` |
| OpenAI Codex  | `~/.codex/skills/nd-search/`  |
| Kimi Code CLI | `~/.kimi/skills/nd-search/`   |

The directory name must match the `name` field in `SKILL.md`. To update, run `git pull` in that folder.

## How to invoke

- **Slash command**: type `/nd-search` in agent chat.
- **`@` context**: attach the skill folder or `SKILL.md`.
- **Automatic**: the agent may load it when your request matches the `description` in `SKILL.md`
  ("найди в интернете", "прочитай страницу", "search the web", "read this URL").

## Source & attribution

Written by [Pavel Rykov](https://t.me/evilfreelancer).

Licensed under the MIT License, see [LICENSE](LICENSE).
