# Noesis Plan

## Top-Level Overview

Build `noesis.py` — a single-file Python 3 CLI that acts as a pre-flight knowledge checker for coding agents. Before an agent edits anything, Noesis interrogates the codebase using git history, cross-references, and test coverage to surface everything the agent might not know. Results are persisted in `.noesis/ledger.json` inside the target repo so state accumulates across multiple invocations.

A companion test file `test_noesis.py` covers every collector and all verdict paths using pytest and temporary git repos, no third-party packages beyond pytest itself.

**Constraints:**
- `noesis.py` ≤ 500 lines, standard library only (`os`, `sys`, `re`, `json`, `subprocess`, `argparse`, `pathlib`, `datetime`, `collections`).
- `test_noesis.py` uses pytest, but the tool under test uses only stdlib.
- No external dependencies, no pip installs.

---

## Sub-Task 1 — Project Skeleton and CLI Entry Point

**Intent:** Establish the file structure, argparse scaffolding, and the ledger read/write helpers so all other sub-tasks can build on a stable foundation.

**Expected Outcomes:**
- `noesis.py` exists and is importable.
- Running `python noesis.py --help` shows four sub-commands: `check`, `resolve`, `add-unknown`, `drift`.
- `load_ledger(repo)` reads `.noesis/ledger.json` and returns a dict; creates the file/folder with a default structure if missing.
- `save_ledger(repo, ledger)` atomically writes the ledger to disk.
- Ledger schema: `{ "unknowns": [], "footprint": [], "next_id": 1 }`.

**Todo List:**
- [ ] Create `noesis.py` with a `main()` guarded by `if __name__ == "__main__"`.
- [ ] Add argparse top-level parser with four sub-command parsers: `check`, `resolve`, `add-unknown`, `drift`.
  - `check`: `--repo PATH`, `--change TEXT`, `--target FILE[:SYMBOL]` (all required)
  - `resolve`: positional `unknown_id`, `--evidence TEXT`, `--source TEXT` (all required)
  - `add-unknown`: `--category TEXT`, `--severity critical|major|minor`, `--text TEXT` (all required)
  - `drift`: `--repo PATH` (required)
- [ ] Implement `load_ledger(repo: Path) -> dict` — creates `.noesis/` dir and default ledger if absent.
- [ ] Implement `save_ledger(repo: Path, ledger: dict)` — writes atomically (write to `.tmp`, rename).
- [ ] Implement `next_unknown_id(ledger) -> str` — returns `"U{n}"` and increments `ledger["next_id"]`.

**Relevant Context:**
- Ledger lives at `<repo>/.noesis/ledger.json`.
- The ledger must survive across multiple `check` runs without duplicating unknowns for the same `category + target_file`.

**Status:** `[ ] pending`

---

## Sub-Task 2 — Evidence Collectors

**Intent:** Implement the six evidence collectors as pure functions that accept `(repo, target_file, symbol)` and return structured lists. Each collector is independently testable.

**Expected Outcomes:**
- `collect_refs(repo, target_file, symbol)` — returns `[{type, claim, source}]` with `type` either `"direct"` or `"indirect"`.
- `collect_history(repo, target_file)` — returns `[{hash, date, author, message}]`.
- `collect_intent(history)` — accepts the history list; returns the subset whose message matches the intent keywords (case-insensitive): `legal, regulation, compliance, required, workaround, hotfix, do not remove, don't remove, security, must`.
- `collect_cochange(repo, target_file, history)` — accepts the history list, runs `git show` per commit, counts co-occurrences. Returns `[{file, count}]` for files appearing in 2+ shared commits, sorted descending by count.
- `collect_tests(repo, target_file, symbol)` — searches `test_*.py` and `*_test.py` files for the module name or symbol name. Returns list of matching `{file, line, snippet}` items (empty list = no test coverage).
- `collect_riskhist(history)` — counts commits whose message contains `fix`, `revert`, or `bug` (case-insensitive). Returns `{"count": n, "commits": [...hashes]}`.

**Todo List:**
- [ ] Implement `collect_refs`: walk every `.py`, `.yaml`, `.yml`, `.json`, `.ini`, `.toml`, `.md` under `repo`; classify each match as `direct` (import/call in `.py`) or `indirect` (non-Python file, or string literal in `.py`). Skip the `.noesis/` folder itself.
- [ ] Implement `collect_history`: run `git log --follow --pretty=format:"%H|%ad|%an|%s" -- <file>` via `subprocess.run`; parse each line into a dict. Return `[]` on error or empty output.
- [ ] Implement `collect_intent`: iterate history list; use `re.search` with a compiled pattern for the keywords. Return matching entries.
- [ ] Implement `collect_cochange`: for each hash in history, run `git show --name-only --pretty=format: <hash>`; use `collections.Counter` to count co-occurrences; return files with count ≥ 2 sorted by count descending.
- [ ] Implement `collect_tests`: derive `module_name` from `target_file` stem. `glob` `test_*.py` and `*_test.py` under repo; `grep` each for `module_name` or `symbol`.
- [ ] Implement `collect_riskhist`: iterate history; count messages matching `fix|revert|bug`.

**Relevant Context:**
- `direct` ref in Python: an `import` statement or a bare function/class call (not inside a string literal). Use simple regex: a line that starts with `import` or `from ... import`, or contains `symbol(` or `symbol.` outside of a string.
- `indirect` ref: the symbol name appears in a non-Python file, or appears inside a Python string literal (`"..."` / `'...'`).
- For `collect_refs`, skip `.git/` and `.noesis/`.

**Status:** `[ ] pending`

---

## Sub-Task 3 — Unknown Generation

**Intent:** After all collectors run, translate their results into the `unknowns` list. Existing open unknowns for the same `(category, target_file)` must not be duplicated.

**Expected Outcomes:**
- `generate_unknowns(ledger, target_file, refs, intent_commits, cochange_files, tests_found, riskhist, history)` adds new unknown entries to `ledger["unknowns"]` and returns the updated ledger.
- Rules applied in order:
  1. Each `indirect` ref → `hidden_caller` / critical
  2. Each intent-flagged commit → `intent` / critical
  3. Each cochange file → `coupling` / major
  4. Empty tests list → `no_safety_net` / major
  5. `riskhist.count >= 2` → `fragile_area` / minor
  6. Empty history → `no_history` / major
- Each unknown: `{id, category, severity, status: "open", evidence: [], attempts: 0, next_steps, target_file}`.
- Deduplication key: `(category, target_file)` — skip if an open unknown for that pair already exists.

**Todo List:**
- [ ] Implement `generate_unknowns(...)` with the six rules above.
- [ ] Use `next_unknown_id(ledger)` to assign IDs.
- [ ] Store `target_file` on each unknown to enable dedup and footprint tracking.
- [ ] Write a helper `_unknown_exists(ledger, category, target_file)` that checks for open duplicates.

**Relevant Context:**
- `next_steps` wording must match the spec exactly (references `<source>`, `<hash>`, `<file>` by substituting actual values).

**Status:** `[ ] pending`

---

## Sub-Task 4 — Verdict Logic and Report Printer

**Intent:** Implement the verdict computation and the human-readable report printed to stdout on every `check` run.

**Expected Outcomes:**
- `compute_verdict(unknowns)` returns one of `"PROCEED"`, `"INVESTIGATE_MORE"`, or `"STOP_AND_ASK"`.
  - Any open critical with attempts < 3 → `INVESTIGATE_MORE` (exit 1)
  - Any open critical with attempts ≥ 3 → `STOP_AND_ASK` (exit 2)
  - All criticals resolved → `PROCEED` (exit 0)
- `print_report(change, target, unknowns, verdict)` prints the full structured report to stdout.
  - Unknowns ordered: critical → major → minor.
  - PROCEED verdict: append GUARDRAILS section listing open major/minor.
  - STOP_AND_ASK: append QUESTIONS FOR A HUMAN section.
- `cmd_check(args)` orchestrates: run collectors → generate unknowns → save ledger → compute verdict → print report → `sys.exit(code)`.
- Ledger `footprint` is updated to contain: `target_file` + all indirect-ref sources + all resolved cochange files.

**Todo List:**
- [ ] Implement `compute_verdict(unknowns) -> tuple[str, int]` returning `(verdict_string, exit_code)`.
- [ ] Implement `print_report(change, target, unknowns, verdict)`.
- [ ] Implement `cmd_check(args)` tying collectors → generate → save → verdict → report → exit.
- [ ] Update `ledger["footprint"]` after generating unknowns.

**Relevant Context:**
- Exit codes: `PROCEED=0`, `INVESTIGATE_MORE=1`, `STOP_AND_ASK=2`.
- Report separator line is `=` × 64.
- Questions section rephrases each stuck critical's `next_steps` as a direct question (append "?" and re-frame in second person).

**Status:** `[ ] pending`

---

## Sub-Task 5 — Resolve, Add-Unknown, and Drift Commands

**Intent:** Implement the three remaining commands that mutate or query the ledger.

**Expected Outcomes:**
- `cmd_resolve(args)`: loads ledger, finds unknown by ID, appends evidence entry, infers `type` from source format, re-checks resolution bar, saves.
  - Source type inference: `file:line` pattern → `"code"`; 7–40 hex chars → `"history"`; contains `"test"` → `"test"`; ends in `.md` → `"doc"`.
  - Critical: resolved when evidence list has 2+ entries with **different** type values; otherwise keep open, increment `attempts`, print why.
  - Major/minor: resolved with 1 entry.
- `cmd_add_unknown(args)`: appends a manually crafted unknown (same schema) to the ledger; assigns next ID; saves.
- `cmd_drift(args)`: reads `ledger["footprint"]`; runs `git diff --name-only` in `--repo`; compares sets; exits 2 with `DRIFT_DETECTED` list if any changed file is outside the footprint; exits 0 with `NO DRIFT` otherwise.

**Todo List:**
- [ ] Implement `infer_source_type(source: str) -> str`.
- [ ] Implement `cmd_resolve(args)`.
- [ ] Implement `cmd_add_unknown(args)`.
- [ ] Implement `cmd_drift(args)`.
- [ ] Wire all four commands into `main()` dispatch.

**Relevant Context:**
- Resolution bar for critical unknowns requires diversity of evidence types, not just quantity.
- `git diff --name-only` with no extra args reports working-tree changes vs HEAD; this is appropriate for drift detection.

**Status:** `[ ] pending`

---

## Sub-Task 6 — Test Suite

**Intent:** Write `test_noesis.py` using pytest, covering every collector and all verdict paths, using temporary git repos for isolation.

**Expected Outcomes:**
- All tests pass with `pytest test_noesis.py`.
- Tests use `tempfile.mkdtemp()` + `subprocess` `git init` / `git add` / `git commit` to create controlled repos.
- Coverage:
  - `refs` finds an indirect reference in a YAML file.
  - `intent` catches a commit message containing a flagged keyword.
  - `cochange` counts correctly (file appearing in 2 commits returns count=2).
  - Verdict `INVESTIGATE_MORE` with one open critical unknown (0 attempts).
  - Verdict `PROCEED` when all criticals are resolved.
  - Verdict `STOP_AND_ASK` after attempts ≥ 3 on a critical.
  - `drift` detects an out-of-footprint changed file.

**Todo List:**
- [ ] Create a `make_repo(path, files)` helper that inits a git repo and makes one initial commit.
- [ ] Write `test_refs_indirect` — YAML file references the symbol.
- [ ] Write `test_intent_keywords` — commit message contains "security".
- [ ] Write `test_cochange_count` — two commits each touch target file + same other file.
- [ ] Write `test_verdict_investigate_more` — ledger has one open critical, 0 attempts.
- [ ] Write `test_verdict_proceed` — all criticals resolved.
- [ ] Write `test_verdict_stop_and_ask` — open critical with attempts=3.
- [ ] Write `test_drift_detected` — footprint set, then a file outside it is modified.

**Relevant Context:**
- Import `noesis` functions directly; tests call the collector/verdict functions, not the CLI subprocess.
- Use `pytest` fixtures or plain helper functions for repo setup.
- Keep total line count well under 300 to leave headroom for `noesis.py` to stay ≤ 500 lines.

**Status:** `[ ] pending`

---

## Notes for Implementation

- **Line budget:** `noesis.py` ≤ 500 lines. Favour conciseness; no docstrings beyond one-liners where needed.
- **`subprocess.run` pattern:** always pass `capture_output=True, text=True, cwd=repo` and check `returncode` before using `stdout`.
- **Footprint update:** after each `check`, overwrite `ledger["footprint"]` with the union of `target_file`, indirect ref sources, and any cochange files whose unknowns are resolved.
- **No global state** in collectors — all state passed via arguments or returned values.
- **Atomic ledger writes:** write to `ledger.json.tmp`, then `os.replace` to `ledger.json`.
