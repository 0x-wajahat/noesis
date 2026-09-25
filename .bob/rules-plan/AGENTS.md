# AGENTS.md (Plan mode)

This file provides guidance to agents when working with code in this repository.

## Architectural Starting Point

The repo is a blank Python project. Any architecture you design will be the first architecture — there are no existing patterns to preserve or conform to.

## Constraints Implied by `.gitignore`

- `marimo/` and `streamlit/` entries suggest the project *may* involve a notebook or web UI layer — confirm intent before choosing an architecture.
- `celerybeat`, `rabbitmq`, `activemq`, `redis` entries in `.gitignore` hint at possible async/queue work — these are pre-emptive ignores in the standard Python template, not confirmed requirements.
- No monorepo tooling (no `nx`, `turbo`, `lerna`) — plan as a single-package repo unless scope demands otherwise.

## Recommended First Step Before Planning

Clarify with the user: package manager choice (`uv` recommended), whether a UI framework is needed, and the core domain/purpose of "noesis".
