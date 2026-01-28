"""Database module for SQLite operations."""

import sqlite3
import logging
from pathlib import Path

from fitness_toolkit.config import Config

logger = logging.getLogger(__name__)


def get_connection():
    """Get a database connection with WAL mode enabled."""
    Config.ensure_directories()
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Initialize the database with required tables."""
    Config.ensure_directories()
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Accounts table - platform as primary key (one account per platform)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                platform TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                password_encrypted TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Download history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS download_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                activity_id TEXT NOT NULL,
                activity_type TEXT,
                file_path TEXT,
                file_format TEXT,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Sync tasks table - platform as primary key
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_tasks (
                platform TEXT PRIMARY KEY,
                enabled BOOLEAN DEFAULT 0,
                cron_expression TEXT,
                file_format TEXT DEFAULT 'tcx',
                activity_types TEXT,
                last_run TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        logger.info("Database initialized successfully")


# Account operations
def save_account(platform, email, password_encrypted):
    """Save or update account for a platform."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO accounts (platform, email, password_encrypted) 
               VALUES (?, ?, ?)
               ON CONFLICT(platform) DO UPDATE SET
               email=excluded.email,
               password_encrypted=excluded.password_encrypted,
               updated_at=CURRENT_TIMESTAMP""",
            (platform, email, password_encrypted)
        )
        conn.commit()


def get_account(platform):
    """Get account by platform name."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts WHERE platform = ?", (platform,))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_accounts():
    """List all configured accounts."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts ORDER BY platform")
        return [dict(row) for row in cursor.fetchall()]


def delete_account(platform):
    """Delete account for a platform."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM accounts WHERE platform = ?", (platform,))
        conn.commit()
        return cursor.rowcount > 0


def has_account(platform):
    """Check if platform has a configured account."""
    return get_account(platform) is not None


# Download history operations
def add_download_history(platform, activity_id, activity_type, file_path, file_format):
    """Add a download history record."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO download_history 
               (platform, activity_id, activity_type, file_path, file_format) 
               VALUES (?, ?, ?, ?, ?)""",
            (platform, activity_id, activity_type, file_path, file_format)
        )
        conn.commit()


def get_download_history(platform=None):
    """Get download history, optionally filtered by platform."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if platform:
            cursor.execute(
                "SELECT * FROM download_history WHERE platform = ? ORDER BY downloaded_at DESC",
                (platform,)
            )
        else:
            cursor.execute("SELECT * FROM download_history ORDER BY downloaded_at DESC")
        return [dict(row) for row in cursor.fetchall()]


# Sync task operations
def save_sync_task(platform, enabled, cron_expression, file_format='tcx', activity_types=None):
    """Save or update sync task for a platform."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO sync_tasks (platform, enabled, cron_expression, file_format, activity_types) 
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(platform) DO UPDATE SET
               enabled=excluded.enabled,
               cron_expression=excluded.cron_expression,
               file_format=excluded.file_format,
               activity_types=excluded.activity_types,
               updated_at=CURRENT_TIMESTAMP""",
            (platform, enabled, cron_expression, file_format, activity_types)
        )
        conn.commit()


def get_sync_task(platform):
    """Get sync task for a platform."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sync_tasks WHERE platform = ?", (platform,))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_sync_tasks():
    """List all sync tasks."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sync_tasks ORDER BY platform")
        return [dict(row) for row in cursor.fetchall()]


def delete_sync_task(platform):
    """Delete sync task for a platform."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sync_tasks WHERE platform = ?", (platform,))
        conn.commit()
        return cursor.rowcount > 0
