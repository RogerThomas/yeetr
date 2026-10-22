# AGENTS.md

## Project

`yeetr` is a tiny, typed, signature-driven CLI runner. A function's signature defines the CLI: positional params become positional args, keyword-only params (after `*`) become `--options`. The PyPI distribution and import package are both `yeetr`; the installed CLI command is `yeet`. See `README.md` for usage and `docs/` for the full guide.

## Layout

- `yeetr/` — library source.
  - `_runner.py` — builds an `argparse.ArgumentParser` from a function signature and executes it (`run`).
  - `_metadata.py` — defines `Arg` and `Opt`, the `Annotated` metadata objects.
  - `_cli.py` — the `yeet` entry point (discovers and runs a function in a file).
- `tests/` — pytest suite.
- `scripts/` — `#!yeet` helper scripts (docs build, next release version).
- `docs/` — documentation site (Zensical / Material), built via `scripts/build_docs.py`.
- `main.py` — kitchen-sink example.
- `style-guide.md` — project-specific Python conventions. **Read this before writing code.**
- `release-strategy.md` — how releases work (tag-based, CI-driven).

## Commands

- `uv sync` — install deps.
- `uv run ruff check` — lint. `uv run ruff format` — format.
- `uv run pyright` — type-check (strict mode).
- `uv run pytest` — run tests.
- `task check` — quality gate (lock check + pre-commit: ruff, pyright, deptry, pylint).
- `task test` — tests with coverage.
- `task docs` — build and serve the docs locally. `task docs-test` — strict docs build.
- `task release` — cut a release (dispatches the CI release workflow; nothing runs locally).

## Conventions

- Python 3.13+ (tested on 3.13, 3.14, and 3.15), strict Pyright, ruff line-length 100.
- Follow `style-guide.md`. Notably: prefer `@dataclass`, place private functions before callers, don't test private functions, avoid module-level globals.
- No comments unless explicitly requested.
- Keep the public API surface minimal — only `Arg`, `Opt`, `YeetrError`, and `run` are exported from `yeetr`.
- Versioning is CalVer, derived from the git tag via `hatch-vcs`. There is no version field to bump — a release is just a pushed tag.

## Before finishing a change

Run `uv run ruff check`, `uv run pyright`, and `uv run pytest` (or `task check && task test`). If you touched docs, run `task docs-test`.

## Acknowledgement

Before starting any work, the agent must explicitly mention to the user that it has read `AGENTS.md`.
