# Noesis

An AI safety layer for coding agents that knows when to stop and investigate instead of guessing.

## Related repository
The sandbox codebase used to build and validate Noesis is here: **https://github.com/0x-wajahat/test-noesis.git**
It contains deliberately planted "traps" (hidden dependencies, config-driven calls, commit history explaining non-obvious code) that Noesis is tested against.

## Problem

Coding agents can confidently make changes to code they don't fully understand. A function that looks unused might be called dynamically from a config file. A rounding calculation that looks like a bug might exist because of a legal requirement documented only in a commit message from months ago. Nothing in the current code tells the agent this — and a shallow agent edits anyway.

## What Noesis does

Noesis sits between a change request and the actual edit. Instead of letting an agent act immediately, it:

1. **Collects evidence** from the codebase and its git history — not just the current file, but how it's referenced, what past commits say about it, and what other files change alongside it.
2. **Generates a list of unknowns** — specific things that would make the change unsafe if guessed wrong.
3. **Requires evidence to resolve each unknown** — a critical unknown needs at least 2 independent pieces of evidence (e.g. a code reference AND a commit message) before it's considered resolved. A vague "looks fine" is not accepted.
4. **Reaches a verdict**:
   - `PROCEED` — all critical unknowns resolved, safe to edit (remaining minor/major unknowns are listed as guardrails to watch)
   - `INVESTIGATE_MORE` — open critical unknowns remain; here's exactly what to check next
   - `STOP_AND_ASK` — after repeated failed attempts to resolve, stop and ask a human, with specific questions
5. **Checks for drift** after editing — did the agent only touch what it predicted it would?

This is enforced through a Bob project rule: before editing any file, Bob must run Noesis's `check` command and follow its verdict.

## How it works internally

Noesis is a single Python 3 CLI (`noesis.py`), standard library only, with these evidence collectors:

- **refs** — searches code and config files for the target symbol, distinguishing direct calls from indirect references (e.g. a name used inside a YAML config, resolved dynamically at runtime)
- **history** — reads git log for the target file
- **intent** — flags commits whose messages suggest deliberate, non-obvious reasoning (e.g. "required by regulation")
- **cochange** — finds files that consistently change together with the target, revealing hidden coupling
- **tests** — checks whether any test covers the target
- **riskhist** — flags files with a history of bug fixes or reverts

State is stored in `.noesis/ledger.json` inside the target repo.

## How to run it

```bash
python noesis.py check --repo <path> --change "<description>" --target <file>:<symbol>
python noesis.py resolve <unknown_id> --evidence "<text>" --source <file:line or commit hash>
python noesis.py add-unknown --category <text> --severity critical|major|minor --text "<text>"
python noesis.py drift --repo <path>
```

## Results

We tested Noesis against `test-noesis`, a sandbox codebase with planted traps:

| Test | What it checked | Result |
|---|---|---|
| Fresh check on an unused-looking function | Detects config-driven hidden caller + relevant commit history | Correctly flagged both, verdict `INVESTIGATE_MORE` |
| Resolving a critical unknown with 1 evidence type | Enforces the 2-type evidence requirement | Correctly stayed open |
| Resolving with 2 evidence types | Evidence bar met, unknown resolves | Resolved, no duplicate unknown created on re-check |
| Resolving all critical unknowns | Verdict flips appropriately |  `PROCEED`, remaining unknowns shown as guardrails |
| 3 failed resolution attempts | Escalates to asking a human | `STOP_AND_ASK` with specific questions printed |
| A hidden sentinel value (`-1` meaning "grace period") passed through an ordinary function call | Detects semantically dangerous arguments, not just structurally hidden references |  Missed — see Limitations |

## Built with IBM Bob

Bob IDE was used throughout: Plan mode to design `noesis.py` before implementation, Code mode to build and iteratively fix it (including a duplicate-unknown bug found during testing), `/init` to generate project context, and Bob's rules feature to enforce Noesis as a gate before code edits. See `bob_sessions/` for task summary screenshots from each team member.

## Limitations

- Noesis detects hidden callers through indirect references (config/string-based lookups) and intent through commit-message keywords. It does **not** currently detect semantically significant argument values passed through ordinary, structurally visible function calls (e.g. a sentinel value like `-1` meaning "skip this case"). This was found during our own testing and is a direction for future work — likely requiring call-site argument tracking as a new evidence collector.
- The Bob rule enforcing Noesis is an instruction, not a hard lock — Bob can, in principle, ignore it. We treat this as something to measure, not assume away.
- Intent detection is currently keyword-based; it can produce false positives (flagging an unrelated but keyword-matching commit) as well as false negatives (missing anything not scoped to file-level history for the exact symbol).
- Testing so far covers a small, deliberately constructed sandbox repo. Testing against real open-source repositories with real historical reverts is a natural next step to strengthen confidence.

## Team

- AbdurRehman Danish
- Aarez Absar
- Izaan Ahmad
- Muhammad Wajahat
