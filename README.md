# ReviewMindBot

LLM-powered pull request review. It reads the diff, finds real problems, and
comments them **on the lines that caused them** — with a spend cap, a response
cache, and a CI exit code you can gate on.

## Use it on your pull requests

Drop this into `.github/workflows/pr-review.yml`:

```yaml
name: PR Review
on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write   # required to post comments

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: 2001-Ankit/pr-review-mind-bot@v1
        with:
          provider: gemini
          api-key: ${{ secrets.GEMINI_API_KEY }}
          budget-usd: "0.50"
```

That's the whole setup. Add `GEMINI_API_KEY` (or `OPENAI_API_KEY` /
`GROQ_API_KEY`) to your repository secrets and open a PR.

Every run posts **inline comments** on the changed lines plus **one summary
comment**, which is edited in place on each push rather than piling up.

### Action inputs

| Input | Default | Description |
| --- | --- | --- |
| `api-key` | *required* | Key for the chosen provider |
| `provider` | `gemini` | `gemini`, `openai` or `groq` |
| `model` | provider default | Override the model |
| `github-token` | `${{ github.token }}` | Needs `pull-requests: write` |
| `comment` | `true` | Post findings to the PR |
| `inline` | `true` | Include inline comments on changed lines |
| `fail-on` | `none` | Fail the job at `low`/`medium`/`high` findings |
| `budget-usd` | `1.00` | Stop before exceeding this spend |
| `max-chunk-size` | `12000` | Characters of diff per request |
| `pr-url` | triggering PR | Review a specific PR instead |

### Action outputs

`total`, `high`, `cost-usd`, and `result-json` (path to the full JSON result),
so you can branch on the result in later steps.

> **Forked PRs** get a read-only token from GitHub, so comment posting will
> fail. Guard the job with
> `if: github.event.pull_request.head.repo.full_name == github.repository`,
> as in [`.github/workflows/pr-review.yml`](.github/workflows/pr-review.yml).

## Use it from the terminal

```bash
pip install "reviewmindbot[gemini]"   # or [openai], [groq], [all]
export GEMINI_API_KEY=...
```

```bash
# A diff file, or straight from git
reviewmindbot changes.diff
git diff main | reviewmindbot -

# A GitHub PR - review it, and post the findings back to it
reviewmindbot --pr https://github.com/owner/repo/pull/123
reviewmindbot --pr https://github.com/owner/repo/pull/123 --comment

# See what a review would cost before running it
reviewmindbot changes.diff --estimate

# Cap the spend; a run that hits the cap reports partial results
reviewmindbot changes.diff --budget-usd 0.25

# Machine-readable, or ready to paste into a PR
reviewmindbot changes.diff --output json
reviewmindbot changes.diff --output markdown

# Draft tests for newly added code
reviewmindbot changes.diff --generate-tests
```

Requires Python 3.11+.

### Configuration

Environment variables, or a `.env` file at or above your working directory
(see [.env.example](.env.example)):

| Provider | Variable | Get a key |
| --- | --- | --- |
| `gemini` | `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | <https://aistudio.google.com/apikey> |
| `openai` | `OPENAI_API_KEY` | <https://platform.openai.com/api-keys> |
| `groq` | `GROQ_API_KEY` | <https://console.groq.com/keys> |

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Ran successfully |
| `1` | Error (bad config, unreachable provider, missing file) |
| `2` | Findings met the `--fail-on` threshold |

`--fail-on` is off by default, so findings alone never fail your build.

## Cost control

An LLM tool that runs on every PR has an unbounded bill by default. Three
things keep it bounded:

- **`--estimate`** reports projected requests, tokens and cost without calling
  the model at all.
- **`--budget-usd`** is checked *before* each request, so it is a limit and not
  a post-mortem. Hitting it produces a clearly-labelled partial review rather
  than a failure — you still get the findings that were paid for.
- **A response cache** (SQLite, per-user, 14-day TTL) means a workflow re-run,
  a retried flaky job, or a push that touches one file out of thirty only pays
  for what actually changed. Keys cover the provider, model, prompt and review
  contract, so a model switch or a prompt change can never serve a stale
  answer. `--no-cache` bypasses it, `--clear-cache` empties it.

Every run reports what it spent, in the text output, the JSON `usage` block,
and the PR comment footer. Unpriced models report `null` rather than pretending
to be free.

Noise is filtered before any tokens are spent: lockfiles, minified bundles,
binaries and deleted files never reach the model.

## As a library

```python
from reviewmindbot import api

result = api.review_diff(open("changes.diff").read())

for finding in result.findings:
    print(finding.severity, f"{finding.file_name}:{finding.line}", finding.message)

print(result.usage)        # {'requests': 3, 'total_tokens': 8421, 'cost_usd': 0.0021, ...}
print(result.complete)     # False if the budget stopped it early
```

Review a PR and publish the result in one call:

```python
result, outcome = api.review_pull_request(
    "https://github.com/owner/repo/pull/123",
    publish=True,
)
print(outcome.describe())  # "summary comment updated, 4 inline comment(s) posted"
```

Lower-level pieces work on their own:

```python
from reviewmindbot.core import DiffParser, build_chunks
from reviewmindbot.engine import Orchestrator, Reviewer, FileRouter
from reviewmindbot.llm import create_provider

files = DiffParser().parse(diff_text)
chunks = build_chunks(FileRouter().select(files), max_chunk_size=12000)
```

## Architecture

```
reviewmindbot/
├── cli.py            argument parsing and exit codes only
├── api.py            programmatic entry points
├── config.py         env → immutable Config, resolved once
├── errors.py         one exception hierarchy the CLI knows how to print
├── usage.py          token accounting, pricing, budget enforcement
├── cache.py          SQLite response cache, best-effort by design
├── core/
│   ├── diff_parser.py   unified diff → FileChange/Hunk, with new-file line numbers
│   └── chunking.py      hunks → model-sized Chunks that remember their files
├── engine/
│   ├── file_router.py   drops binaries, lockfiles, deleted files
│   ├── reviewer.py      Chunk → Findings; cache lookup and budget check
│   ├── aggregator.py    dedupe across overlapping chunks, sort by severity
│   ├── orchestrator.py  route → chunk → review in parallel → aggregate
│   ├── test_generator.py
│   ├── models.py        Finding, ReviewResult, Severity, Category
│   └── prompts.py
├── llm/
│   ├── base.py       LLMProvider ABC + retry/backoff + usage accounting
│   ├── factory.py    name → client registry
│   ├── gemini.py
│   └── openai.py     OpenAIProvider and Groq (OpenAI-compatible)
├── integration/
│   ├── github.py     REST client: fetch diffs, upsert comments, post reviews
│   └── publisher.py  ReviewResult → PR comments, with line validation
└── reporting/
    └── formatters.py text / json / markdown
```

**Adding a provider** is one entry in `llm/factory.PROVIDERS` plus one in
`config.PROVIDER_KEY_ENV_VARS`. The CLI's `--provider` choices, config
validation, and the Action's key wiring all derive from those tables — and a
test fails if you add a provider without wiring its key into `action.yml`.

**Adding an output format** is one function in `reporting/formatters.FORMATTERS`.

## Behaviour worth knowing

- **Findings carry a file and a line.** Chunks are rendered with a line-number
  gutter, so the model cites real line numbers instead of guessing.
- **Inline comments are validated against the diff.** GitHub rejects an entire
  review if one comment names a line outside the diff, so anything
  unverifiable is deliberately routed to the summary instead. A rejected
  review degrades to a summary-only comment; no finding is ever lost.
- **The summary comment is edited, not re-posted** — a bot that appends on
  every push buries the conversation it exists to support.
- **A failed chunk does not sink the run.** The others still report, and both
  the summary and the JSON say the review was partial.
- **Transient errors (429/5xx/timeouts) are retried** with backoff; permanent
  ones (bad key, unknown model) fail immediately instead of burning quota.
- **Overlapping chunks are de-duplicated** before output.
- **Logs go to a per-user state directory**, not your working directory, and an
  unwritable log path never stops a review.

## Development

```bash
git clone https://github.com/2001-Ankit/pr-review-mind-bot.git
cd pr-review-mind-bot
pip install -e ".[dev]"
pytest
ruff check .
```

CI builds the wheel, installs it in a clean venv, and runs the console script —
the check that would have caught the broken `0.1.0` release.

## Upgrading

See [CHANGELOG.md](CHANGELOG.md). `0.2.0` renamed the importable package from
`app` to `reviewmindbot` and moved provider SDKs to extras; `0.3.0` is additive
on top of that.

## Roadmap

- [x] Post findings as inline PR review comments
- [x] Cache reviews to avoid paying twice for the same diff
- [x] Ship a ready-made GitHub Action
- [ ] Custom rule packs and per-repo policies (`.reviewmindbot.yml`)
- [ ] Incremental review of only the commits added since the last run
- [ ] Anthropic Claude provider

## License

MIT — see [LICENSE](LICENSE).
