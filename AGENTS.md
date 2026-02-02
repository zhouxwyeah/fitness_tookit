# AGENTS.md - fitness_toolkit

> Personal fitness data sync tool: COROS → Garmin China

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
pytest tests/test_transfer_queue.py::TestTransferQueueService::test_create_job  # Class method
pytest -k "transfer"                       # Tests matching pattern
pytest -v --tb=short                       # Verbose with short tracebacks

# Linting & Formatting
ruff check .                               # Lint all files
ruff check . --fix                         # Auto-fix issues
black .                                    # Format all files
black --check .                            # Check formatting only
```

## CODE STYLE

### Imports
- **Order**: stdlib → third-party → local (ruff I sorts automatically)
- **Style**: Use `from x import y` for specific imports
```python
import logging
from datetime import datetime
from typing import Any, Optional

import requests
from flask import Flask, jsonify

from fitness_toolkit.config import Config
from fitness_toolkit.services.transfer_queue import TransferQueueService
```

### Formatting
- **Line length**: 88 characters (black/ruff default)
- **Quotes**: Double quotes for strings
- **Trailing commas**: Use in multi-line structures
- **Tools**: black for formatting, ruff for linting

### Naming Conventions
| Type | Convention | Example |
|------|------------|---------|
| Modules | `snake_case.py` | `transfer_queue.py` |
| Classes | `PascalCase` | `TransferQueueService` |
| Functions | `snake_case()` | `get_account()` |
| Constants | `UPPER_SNAKE_CASE` | `JOB_STATUS_PENDING` |
| Private | `_leading_underscore` | `_internal_helper()` |

### Type Hints (Required)
```python
def create_job(
    self,
    start_date: str,
    end_date: str,
    activities: list[dict[str, Any]],
    sport_types: Optional[list[str]] = None,
) -> int:
```
- Use `X | None` or `Optional[X]` for nullable types
- Use `list[X]`, `dict[K, V]` (Python 3.10+ style)

### Error Handling
```python
try:
    result = risky_operation()
except ValueError as e:
    logger.error(f"Invalid input: {e}")
    raise TransferError("Download failed") from e
```
- **Never** use bare `except:` - always catch specific exceptions
- **Log** errors with context before raising
- **Use** `raise ... from err` for exception chaining

### Documentation
- **Docstrings**: Google style for modules, classes, public functions
- **Comments**: Explain "why", not "what"

## PROJECT STRUCTURE

```
fitness_toolkit/
├── __main__.py            # Entry: python -m fitness_toolkit
├── cli.py                 # Click CLI commands
├── config.py              # Config + .env support
├── crypto.py              # Fernet password encryption
├── database.py            # SQLite operations
├── clients/               # Platform API clients
│   ├── coros.py           # COROS API
│   └── garmin.py          # Garmin China via garth
├── services/              # Business logic
│   ├── account.py         # Account CRUD
│   ├── transfer.py        # Sync transfer (legacy)
│   ├── transfer_queue.py  # Async job queue
│   ├── transfer_worker.py # Background worker
│   └── transfer_settings.py # Settings + templates
└── web/
    ├── app.py             # Flask API routes
    └── templates/         # Alpine.js UI (index.html)
```

## TESTING GUIDELINES

### Test Structure
- **Location**: `tests/test_*.py`
- **Naming**: `test_<function>()` or `Test<Class>::test_<method>()`
- **Fixtures**: Use `pytest.fixture` with `tmp_path` for temp files

### Database Testing Pattern
```python
@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Set up temp database."""
    db_file = tmp_path / "test_fitness.db"
    monkeypatch.setattr("fitness_toolkit.config.Config.DATABASE_PATH", db_file)
    monkeypatch.setattr("fitness_toolkit.database.Config.DATABASE_PATH", db_file)
    init_db()
    return db_file
```

### Mocking External APIs
```python
def test_transfer_api_success(client, monkeypatch):
    mock_service = MagicMock()
    mock_service.transfer.return_value = {"total": 3, "uploaded": 2}
    monkeypatch.setattr("fitness_toolkit.web.app.TransferService", lambda: mock_service)
```

## KEY DESIGN PRINCIPLES

- **One account per platform**: `platform` is primary key
- **Local only**: Web binds to `127.0.0.1:5000`, never `0.0.0.0`
- **Passwords**: Fernet encrypted, key in `.env` as `FITNESS_ENCRYPTION_KEY`
- **Logging**: Never log passwords/tokens - use `***` placeholder

### Transfer Flow (COROS → Garmin)
1. Create job via `TransferQueueService.create_job()`
2. Worker downloads FIT from COROS (not TCX)
3. Upload to Garmin via garth
4. Handle 409/202 = duplicate (skip, not error)

## GIT COMMITS

```
feat: add async transfer job queue
fix: handle token refresh failure
test: add transfer worker tests
refactor: simplify download service
```

## ANTI-PATTERNS

| Avoid | Use Instead |
|-------|-------------|
| Bare `except:` | `except Exception:` or specific |
| Real API calls in tests | `pytest-mock` / `monkeypatch` |
| Hardcoded credentials | `.env` + Fernet |
| `print()` for debugging | `logging` module |
| Expose web to `0.0.0.0` | `127.0.0.1` only |
