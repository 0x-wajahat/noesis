# AGENTS.md (Agent mode)

This file provides guidance to agents when working with code in this repository.

## Critical Setup Note

The repo has **no source files yet**. Before writing any code:
1. Choose and configure a package manager (`uv` is preferred per `.gitignore` — run `uv init` or add a `pyproject.toml`).
2. Add `ruff` and `mypy` as dev dependencies — both are already accounted for in `.gitignore`.
3. Place tests co-located with source or under a `tests/` directory; configure `pytest` in `pyproject.toml`.

## Coding Conventions (establish from day one)

- Use `ruff` for both linting and formatting (replaces `black` + `isort`); configure via `[tool.ruff]` in `pyproject.toml`.
- Use `mypy` in strict mode (`--strict`) from the start to avoid retrofitting types later.
- No `requirements.txt` — all dependencies must go in `pyproject.toml` (uv/poetry/pdm all support this).
