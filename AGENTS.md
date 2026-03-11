# Repository Guidelines

## Project Structure & Module Organization
This repository is currently a minimal Python project:
- `daily_monitor.py`: main entry script for daily commodity monitoring logic.
- `requirements.txt`: Python dependency list.
- `README.md`: project overview.

When adding features, keep business logic out of the top-level script. Prefer moving reusable code into `src/commodity_monitor/` and placing tests in `tests/`. Keep sample inputs or fixtures in `assets/` only if needed.

## Build, Test, and Development Commands
- `python -m venv .venv`: create a local virtual environment.
- `.venv\Scripts\Activate.ps1`: activate the environment in PowerShell.
- `pip install -r requirements.txt`: install dependencies.
- `python daily_monitor.py`: run the monitor locally.
- `pytest -q`: run tests (after tests are added).

If you add linting/formatting tools, document and run them before opening a PR.

## Coding Style & Naming Conventions
Follow Python 3 conventions (PEP 8):
- 4-space indentation, no tabs.
- `snake_case` for functions, variables, and module names.
- `PascalCase` for classes.
- `UPPER_SNAKE_CASE` for constants.

Prefer small, single-purpose functions with clear docstrings for non-trivial behavior. Add type hints for new or modified functions.

## Testing Guidelines
Use `pytest` for unit and integration tests:
- Place tests under `tests/`.
- Name files `test_*.py`.
- Mirror source naming (example: `tests/test_daily_monitor.py`).

Focus coverage on parsing, scheduling/date handling, and external data-fetch behavior (mock network calls where possible).

## Commit & Pull Request Guidelines
Current commit history uses short imperative messages (examples: `Create requirements.txt`, `Create daily_monitor.py`). Keep this style:
- Format: `<Verb> <object>` (example: `Add retry for price fetch`).
- One logical change per commit.

PRs should include:
- A brief summary of what changed and why.
- Local verification steps (commands run and results).
- Linked issue/ticket when applicable.

## Security & Configuration Tips
Do not commit API keys or secrets. Use environment variables (for example, `os.getenv`) and keep local-only config files out of version control.
