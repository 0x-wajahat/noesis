# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project

**noesis** is a Python 3 CLI (standard library only) that decides whether a coding agent has enough evidence about a codebase to safely make a requested change — before editing anything. It collects references, git history, intent-flagged commits, co-change patterns, test coverage, and bug/revert history, turns gaps into tracked "unknowns," and returns a verdict: `PROCEED`, `INVESTIGATE_MORE`, or `STOP_AND_ASK`. State is kept in `.noesis/ledger.json`.

## MANDATORY: Safety check before editing

Every agent operating in this repo, in **any mode that can write files**, must follow the workflow defined in [`.bob/rules/noesis-check.md`](.bob/rules/noesis-check.md) before editing any file:

- Run `python noesis.py check` **before** making any edit.
- Run `python noesis.py drift` **after** any edit.

This is not optional tooling — it is the actual subject of this repository. If `noesis.py` cannot be found or fails to run, **stop and tell the human**. Do not proceed on the assumption that "no tooling is configured yet."

## Commands

```
# Assess whether a change is safe to make
python noesis.py check --repo PATH --change "description of change" --target FILE[:SYMBOL]

# Supply evidence to resolve an open unknown
python noesis.py resolve <unknown_id> --evidence "what you found" --source "file:line or commit hash"

# Register a risk the tool missed
python noesis.py add-unknown --category "category" --severity critical|major|minor --text "description"

# Detect edits outside the approved footprint
python noesis.py drift --repo PATH
```
