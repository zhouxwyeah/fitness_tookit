# AGENTS.md - fitness_toolkit

> Personal fitness data sync tool: COROS → Garmin China

---

## COMMANDS

```bash
# Setup
source .venv/bin/activate
pip install -r requirements.txt

# Run
python -m fitness_toolkit web              # Web UI at http://localhost:5000
python -m fitness_toolkit --help           # CLI help

# Testing
pytest                                     # All tests
pytest tests/test_crypto.py                # Single test file
pytest tests/test_crypto.py::test_encrypt_decrypt_roundtrip  # Single test
pytest -k "transfer"                       # Tests matching pattern
pytest -v --tb=short                       # Verbose with short tracebacks

# Linting & Formatting
ruff check .                               # Lint all files
ruff check fitness_toolkit/                # Lint source only
ruff check tests/                          # Lint tests only
ruff check . --fix                         # Auto-fix issues
black .                                    # Format all files
black --check .                            # Check formatting without changes
```

---

## CODE STYLE

### Imports
- **Order**: stdlib → third-party → local (ruff I sorts automatically)
- **Style**: Use `from x import y` for specific imports
- **Example**:
  ```python
  import logging
  from datetime import date
  from pathlib import Path
  from typing import Optional

  import requests
  from flask import Flask

  from fitness_toolkit.config import Config
  ```

### Formatting
- **Line length**: 88 characters (black/ruff default)
- **Quotes**: Double quotes for strings
- **Trailing commas**: Use in multi-line structures
- **Tool**: black for formatting, ruff for linting

### Naming Conventions
| Type | Convention | Example |
|------|------------|---------|
| Modules | `snake_case.py` | `account_service.py` |
| Classes | `PascalCase` | `AccountService` |
| Functions | `snake_case()` | `get_account()` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RETRY_COUNT` |
| Private | `_leading_underscore` | `_internal_helper()` |
| Type variables | `PascalCase` | `T`, `ResponseType` |

### Type Hints
- **Required** for all function signatures
- **Use**: `Optional[X]` or `X | None` for nullable types
- **Use**: `list[X]`, `dict[K, V]` instead of `List`, `Dict` (Python 3.10+)
- **Example**:
  ```python
  def download_activity(
      activity_id: str,
      format: str,
      save_path: Path,
  ) -> Optional[Path]:
  ```

### Error Handling
- **Never** use bare `except:` - always catch specific exceptions
- **Log** errors with context before raising
- **Use** `raise ... from err` for exception chaining
- **Example**:
  ```python
  try:
      result = risky_operation()
  except ValueError as e:
      logger.error(f"Invalid input: {e}")
      raise TransferError("Download failed") from e
  ```

### Documentation
- **Docstrings**: Use triple quotes for modules, classes, public functions
- **Style**: Google or NumPy style (be consistent within file)
- **Comments**: Explain "why", not "what" (code should be self-explanatory)

---

## PROJECT STRUCTURE

```
fitness_toolkit/
├── __main__.py            # Entry: python -m fitness_toolkit
├── cli.py                 # Click CLI commands
├── config.py              # Config + .env support
├── crypto.py              # Fernet password encryption
├── database.py            # SQLite (accounts, history, tasks)
├── logger.py              # Module loggers → logs/
├── clients/               # Platform API clients
│   ├── base.py            # BaseClient ABC
│   ├── garmin.py          # Garmin China via garth
│   └── coros.py           # COROS API
├── services/              # Business logic
│   ├── account.py         # Account CRUD
│   ├── download.py        # Download activities
│   ├── transfer.py        # COROS→Garmin sync
│   └── scheduler.py       # APScheduler tasks
└── web/                   # Flask app
    ├── app.py             # API routes + Alpine.js UI
    └── templates/         # Jinja2 (single index.html)
```

---

## KEY DESIGN PRINCIPLES

### Personal Tool Mode
- **One account per platform**: `platform` is primary key in `accounts` table
- **Platform-based CLI**: `download coros` not `download --account-id 1`
- **No multi-tenancy**: Single user, local SQLite
- **Local only**: Web binds to `127.0.0.1:5000`, never expose to `0.0.0.0`

### Security
- **Passwords**: Encrypted with Fernet before DB storage
- **Key**: Store in `.env` as `FITNESS_ENCRYPTION_KEY`
- **Generate**: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- **Logging**: Never log passwords/tokens - use `***` placeholder

### Transfer Flow (COROS → Garmin)
1. Download FIT from COROS (not TCX - extension compatibility issues)
2. Upload FIT to Garmin via `garth.client.post("connectapi", "/upload-service/upload")`
3. Handle 409 Conflict or code 202 = duplicate (skip, not error)

---

## TESTING GUIDELINES

### Test Structure
- **Location**: `tests/test_*.py` (no `conftest.py`)
- **Naming**: `test_<function_name>()` or `test_<class>_<method>()`
- **Style**: Simple pytest functions, avoid complex fixtures

### Mocking
- **Always** mock external APIs (COROS, Garmin)
- **Use**: `pytest-mock` or `unittest.mock`
- **Example**:
  ```python
  def test_transfer_api_success(client, monkeypatch):
      mock_service = MagicMock()
      mock_service.transfer.return_value = {"total": 3, "uploaded": 2}
      monkeypatch.setattr("fitness_toolkit.web.app.TransferService", lambda: mock_service)
      # ... test code
  ```

### Database Testing
- **Use** temporary databases (don't pollute `data/fitness.db`)
- **Mock** `Config.DATABASE_PATH` to point to temp file
- **Cleanup** test files after each test

---

## GIT COMMITS

Use conventional commits format:

```
feat: add Garmin client authentication
fix: handle token refresh failure
test: add crypto module tests
docs: update documentation
refactor: simplify download service
chore: update dependencies
```

---

## ANTI-PATTERNS

| Pattern | Alternative |
|---------|-------------|
| Bare `except:` | `except Exception:` or specific |
| Real API calls in tests | `pytest-mock` |
| Hardcoded credentials | `.env` + Fernet |
| `as any` / type suppression | Fix the types |
| Expose web to `0.0.0.0` | `127.0.0.1` only |
| Print instead of logging | `logging` module |

---

## EXTERNAL LIBS

| Library | Purpose |
|---------|---------|
| garth | Garmin Connect API |
| Click | CLI framework |
| Flask | Web framework |
| APScheduler | Task scheduling |
| cryptography | Fernet encryption |
