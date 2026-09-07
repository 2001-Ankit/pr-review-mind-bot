# Changelog

## 0.3.0

Makes the tool usable by anyone without wiring anything up, and puts a ceiling
on what it can cost. Additive: no breaking changes from 0.2.0.

### Added — runs itself on your PRs

- **A GitHub Action** (`action.yml`). Ten lines of workflow YAML and a secret
  is the entire setup; no servers, no hosting, uses the repo's own token.
  Exposes `total`, `high`, `cost-usd` and `result-json` as outputs, and writes
  a table to the job summary.
- **`--comment`** posts findings to the PR: inline review comments on the
  changed lines, plus one summary comment. The summary is **edited in place**
  on every push instead of appending, so the bot does not bury the discussion.
- **Inline comments are validated against the diff.** GitHub rejects an entire
  review if one comment names a line outside the diff, so findings whose line
  cannot be verified are routed to the summary instead, and a rejected review
  degrades to summary-only. No finding is ever silently dropped.
- **`--no-inline`** for a summary comment only.
- `api.review_pull_request(url, publish=True)` does the same from Python.

### Added — cost control

- **`--budget-usd`** (and `BUDGET_USD`), checked *before* each request rather
  than after, so the limit actually limits. Hitting it yields a clearly
  labelled partial review instead of a failure — the findings already paid for
  are still reported, and `complete: false` appears in the JSON.
- **`--estimate`** reports projected requests, tokens and cost and exits
  without calling the model.
- **A response cache** (SQLite, per-user, 14-day TTL). Re-runs on an unchanged
  diff are free. Keys cover provider, model, both prompts and a schema version,
  so a model switch or prompt change cannot serve a stale answer. Every cache
  operation is best-effort: a corrupt, locked or unwritable cache degrades to a
  miss rather than failing the review. `--no-cache`, `--clear-cache`.
- **Token and cost reporting** everywhere: text output, a `usage` block in the
  JSON, and the PR comment footer. Real provider-reported token counts are used
  when available and estimated otherwise. Unpriced models report `null` rather
  than pretending to be free.

### Improved

- **The diff parser now tracks new-file line numbers** for added lines, and
  chunks are rendered with a line-number gutter. The model cites real lines
  instead of guessing, which is what makes inline comments land correctly.
  `FileChange.commentable_lines()` exposes the lines a comment may target.
- `ReviewResult` gained `usage`, `skipped_chunks`, `budget_exhausted` and
  `complete`; partial reviews are now visible rather than looking clean.
- Providers report token usage through a new `Completion` return type.
- Tests no longer touch the developer's real cache or state directories.

## 0.2.0

Restructure release. 0.1.0 installed but could not be used as documented; this
fixes that and reworks the internals around it.

### Fixed — the package was unusable from PyPI

- **`GEMINI_API_KEY` is now read.** The code read `GOOGLE_API_KEY` while the
  README, `.env.example` and the error message all said `GEMINI_API_KEY`, so a
  user who followed the docs exactly got "GEMINI_API_KEY not found" while
  having set it. Both names are now accepted.
- **`requests` is declared.** It was imported at runtime by the GitHub
  integration but absent from `dependencies`; it only resolved because another
  package happened to pull it in.
- **The bundled example diff ships.** The README pointed at
  `app/examples/simple_change.diff`, which did not exist after `pip install`.
  Available as `reviewmindbot.examples.example_path()`.
- **Errors print a message, not a traceback.** Invalid keys, unreachable
  providers and missing files now produce one clear line.

### Changed — breaking

- **Top-level package renamed `app` → `reviewmindbot`.** Installing 0.1.0 put a
  module named `app` into `site-packages`, ready to collide with anything else
  using that very generic name. Imports move from `app.*` to `reviewmindbot.*`.
- **Provider SDKs are optional extras.** Install
  `reviewmindbot[gemini|openai|groq|all]`. A base install is 4 dependencies
  instead of ~40, and no longer installs three vendors' clients to use one.
- **`ReviewFindings` → `Finding`**, now carrying `line` and `suggestion`.
  `Severity` and `Category` are enums.
- **`Reviewer.review_chunk(str)` → `Reviewer.review(Chunk)`.**
- **`FileRouter.should_split()` → `should_review()/select()`** — it now filters
  noise rather than choosing a split strategy.
- Minimum Python lowered to 3.11.
- Switched to a `src/` layout with explicit package discovery.

### Added

- `--fail-on {none,low,medium,high}` and real exit codes (2 = gate tripped).
  Previously every run exited 0, which made the tool useless as a CI gate.
- `--output markdown` for PR comments, `--model`, `--version`, `--quiet`.
- Read a diff from stdin with `-` (`git diff main | reviewmindbot -`).
- `reviewmindbot.api` — `review_diff()` / `generate_tests()` for library use.
- `python -m reviewmindbot`.
- Parallel chunk review (`MAX_CONCURRENCY`, default 4).
- Retry with backoff on transient provider failures (`MAX_RETRIES`).
- `py.typed`.

### Improved

- **Findings are attributed to files.** Chunks now carry their source paths, so
  `file_name` is populated instead of always being `null`.
- **Fenced and prose-wrapped JSON is parsed.** Models routinely wrap output in
  ```` ```json ````; that response used to be discarded as "no findings",
  silently losing real results.
- **Duplicate findings are collapsed** across overlapping chunks.
- **One failed chunk no longer aborts the run**; the summary reports how many
  were lost.
- **Chunking splits on hunk and line boundaries**, never mid-token, and the
  default chunk size went from 500 to 12000 characters — 500 could not hold a
  single realistic hunk.
- **Lockfiles, minified bundles, binaries and deleted files are skipped**
  before any tokens are spent.
- **Logs write to a per-user state directory**, not the working directory, and
  an unwritable log path no longer aborts the run.
- **PR URLs are validated** against `github.com/<owner>/<repo>/pull/<n>` and
  fetched via the API. Any string used to get `.diff` appended and fetched with
  the user's token attached.
- **`Orchestrator` is actually used.** It, `FileRouter` and `Aggregator` were
  dead code; the CLI hand-rolled the same flow inline.
- Added lines beginning with `+` (e.g. `++i;` in C) are no longer dropped by
  the diff parser.
- Test generation runs once per file instead of once per hunk.

### Removed

- `main.py` (the console script and `python -m` cover it).
- `requirements.txt` (was UTF-16 encoded and duplicated `pyproject.toml`).
- The 250-line hardcoded sample diff embedded in `diff_parser.py`'s
  `__main__` block, which shipped inside the wheel.

## 0.1.0

Initial release.
