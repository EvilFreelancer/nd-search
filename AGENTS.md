# Authoring and maintaining the `nd-search` skill

Agent guide for working **inside this skill repository**. Read it before editing `SKILL.md`, the
script, the tests or any plugin manifest.

> Naming (Russian): the adjective for "agent / agentic" is **"агентный"**, never "агентский".

## Repository layout

The skill is packaged for **Claude Code**, **Codex** and **Cursor**, and installs as a plain skill
folder for any other agent. The layout is flat: `SKILL.md` and its assets live at the repo root and
the plugin manifests point their skill source at `./`.

```
nd-search/
├─ .claude-plugin/plugin.json
├─ .cursor-plugin/plugin.json
├─ .codex-plugin/plugin.json
├─ .github/workflows/test.yml   # unit tests on Linux, macOS, Windows; manifests agree
├─ SKILL.md                     # CANONICAL skill: YAML frontmatter + instructions for the agent
├─ README.md                    # human-facing documentation
├─ AGENTS.md                    # this file
├─ scripts/nd_search.py         # the client: web, read, crawl, tg, quota
└─ tests/test_nd_search.py      # python -m unittest discover -s tests
```

## Hard rules for this skill

1. **The key never leaks.** `--api-key` wins, `NEURALDEEP_API_KEY` is the fallback, and the script
   never prints the key, puts it in a URL or writes it anywhere. SKILL.md keeps telling the agent to
   prefer the variable;
2. **Proxy variables are ignored.** The client builds its opener with an empty `ProxyHandler`; a test
   runs every call behind a dead proxy to keep it that way;
3. **No upstream vendor names.** NeuralDeep does not name the providers behind search and reading.
   SKILL.md, README and the script speak of "web search", "page reading", "crawling", and of the
   extraction paths `fast`, `reader`, `browser` as the API returns them;
4. **Exit codes are a contract.** `0` ok, `2` usage or no key, `3` rejected (400, 404, 413, 415,
   422), `4` quota (429), `5` access (401, 402, 403), `6` platform or network. Agents branch on
   them; change them only with a major version bump and update SKILL.md, README and the tests together;
5. **No dependency beyond the Python standard library** (3.8+), and the three platforms stay equal.

## Checking against the live API

The unit tests never touch the network. Before a release that changes request or answer handling,
run each command once against the real API with your own key and compare the fields with SKILL.md:

```bash
python3 scripts/nd_search.py quota
python3 scripts/nd_search.py web "test query" -n 2 --json
python3 scripts/nd_search.py read https://example.com --json
```

## Testing

```bash
python3 -m unittest discover -s tests -v
```

The suite runs the script as a subprocess against a `ThreadingHTTPServer` stub on `127.0.0.1`. It
covers the key order (flag, then variable, then a usage error without a request), every command's
request and output, the exit code of each HTTP status class, a non-JSON answer, an unreachable API
and the dead-proxy bypass. CI repeats it on Linux, macOS and Windows.

## Versioning

`version` must be identical in `SKILL.md` (`metadata.version`), `.claude-plugin/plugin.json`,
`.cursor-plugin/plugin.json` and `.codex-plugin/plugin.json`, and the `description` the same in the
three manifests (the CI lint job checks both). Bump it on every change that should reach users.

The skill is not listed in the rpa-skills catalog; users install it by cloning this repository.
A copy of `scripts/nd_search.py` lives in the NeuralDeep hub repository as
`.agents/skills/web-search-nd/nd_search.py`: change the client here first, then copy it there.

## Commit checklist

- [ ] `python3 -m unittest discover -s tests` green locally, CI green on all three systems.
- [ ] SKILL.md, README and the script agree on commands, flags, fields and exit codes.
- [ ] `version` bumped and identical everywhere; `description` consistent.
- [ ] The copy of the client in the NeuralDeep hub repository updated when the script changed.
- [ ] Conventional commit message, e.g. `feat(nd-search): ...` / `fix(nd-search): ...`.

