# AGENTS.md - Coding Guidelines for fitness_toolkit

> Guidelines for AI coding agents working on this Python fitness data synchronization project.

**Tech Stack**: Python 3.10+, Flask, SQLite, Click, python-dotenv, garth

---

## Build & Development Commands

```bash
# Setup (use .venv)
source .venv/bin/activate
pip install -r requirements.txt

# Run CLI
python -m fitness_toolkit --help
python -m fitness_toolkit config show
python -m fitness_toolkit download garmin --start 2024-01-01 --end 2024-01-31

# Run Web UI
python -m fitness_toolkit web

# Testing
pytest                           # Run all tests
pytest tests/test_crypto.py     # Run single test file
pytest -k test_name             # Run specific test by name
pytest tests/test_crypto.py::test_encrypt_decrypt_roundtrip  # Run single test

# Linting & Formatting
ruff check .                    # Check code style
ruff check --fix .              # Fix auto-fixable issues
black .                         # Format code

# Database
sqlite3 data/fitness.db ".tables"
sqlite3 data/fitness.db ".schema accounts"
```

---

## Code Style Guidelines

### Python Style
- **Formatter**: `black` (88 character line length)
- **Linter**: `ruff` with rules: E, F, I, N, W, UP, B, C4, SIM
- **Quotes**: Double quotes for strings
- **Target**: Python 3.10+

### Imports (sorted: stdlib → third-party → local)
```python
# Standard library
import hashlib
import logging
from datetime import datetime
from pathlib import Path

# Third-party
import click
import requests
from cryptography.fernet import Fernet

# Local modules
from fitness_toolkit.config import Config
from fitness_toolkit.crypto import encrypt_password
```

### Naming Conventions
| Type | Convention | Example |
|------|------------|---------|
| Modules | `snake_case` | `garmin_client.py` |
| Classes | `PascalCase` | `GarminClient` |
| Functions | `snake_case` | `download_activity()` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RETRY_COUNT` |
| Private | `_leading_underscore` | `_internal_helper()` |

### Type Hints
Use type hints for all function parameters and return values:
```python
from typing import Optional, List, Dict, Any
from pathlib import Path

def download_activity(
    activity_id: str,
    format: str,
    save_path: Path,
    retry_count: int = 3
) -> Optional[Path]:
    ...
```

### Error Handling
- Use specific exceptions, not bare `except:`
- Log errors with context before raising
- Implement retry with exponential backoff
- **Never log sensitive data (passwords, tokens)**

```python
import logging

logger = logging.getLogger(__name__)

def api_call_with_retry():
    for attempt in range(MAX_RETRY_COUNT):
        try:
            return make_api_call()
        except requests.RequestException as e:
            logger.warning(f"API call failed (attempt {attempt + 1}): {e}")
            if attempt < MAX_RETRY_COUNT - 1:
                time.sleep(2 ** attempt)
            else:
                raise
```

### Logging
- Use module-level loggers: `logger = logging.getLogger(__name__)`
- Log to `logs/` directory
- **NEVER log passwords, tokens, or sensitive credentials**

---

## Project Structure

```
fitness_toolkit/
├── __init__.py            # Package init
├── __main__.py            # Entry point for python -m
├── cli.py                 # Click CLI implementation
├── config.py              # Configuration (supports .env)
├── crypto.py              # Password encryption (Fernet)
├── database.py            # SQLite operations
├── logger.py              # Logging configuration
├── clients/               # Platform API clients
│   ├── base.py
│   ├── garmin.py          # Uses garth library
│   └── coros.py
├── services/              # Business logic
│   ├── account.py         # One account per platform
│   ├── download.py
│   └── scheduler.py
└── web/                   # Flask web app
    ├── app.py
    └── templates/
```

---

## Key Design Principles

### Personal Tool Mode
- **One account per platform**: Garmin and COROS each have only one account
- **Platform-based CLI**: Commands use `garmin`/`coros` instead of account IDs
- **Simplified workflow**: `fitness download garmin` not `fitness download --account 1`

### Security
- Encrypt passwords using Fernet
- Store encryption key in `.env` file (FITNESS_ENCRYPTION_KEY)
- Use parameterized SQL queries
- Bind web only to `localhost:5000`
- Never commit `.env` files

---

## Testing Guidelines

```python
# tests/test_crypto.py
import pytest
from fitness_toolkit.crypto import encrypt_password, decrypt_password

def test_encrypt_decrypt_roundtrip():
    password = "test_password_123"
    encrypted = encrypt_password(password)
    decrypted = decrypt_password(encrypted)
    assert decrypted == password
```

- Never call real APIs in tests (use `pytest-mock`)
- Use fixtures in `conftest.py`
- Clean up test files after each test

---

## Git Commit Messages

Follow conventional commits:

```
feat: add Garmin client authentication
fix: handle token refresh failure
test: add crypto module tests
docs: update API documentation
refactor: simplify download service
chore: update dependencies
```

---

## Environment Variables

Create `.env` file:

```bash
# Required: Encryption key for password storage
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FITNESS_ENCRYPTION_KEY=your-generated-key-here

# Optional
LOG_LEVEL=INFO
```

---

## External References

- **Garmin API**: https://github.com/matin/garth (use `garth.connectapi()`)
- **Click**: https://click.palletsprojects.com/
- **Flask**: https://flask.palletsprojects.com/
- **pytest**: https://docs.pytest.org/

---

*Last updated: 2025-01-28*
