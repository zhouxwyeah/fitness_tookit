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

        # Operation history table for download/transfer logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS operation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_type TEXT NOT NULL,
                platform TEXT,
                start_date TEXT,
                end_date TEXT,
                total INTEGER DEFAULT 0,
                success INTEGER DEFAULT 0,
                skipped INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Transfer settings table (singleton row, id=1)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transfer_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                settings_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Transfer jobs table - async transfer jobs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transfer_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL DEFAULT 'pending',
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                sport_types TEXT,
                settings_snapshot TEXT NOT NULL,
                total_items INTEGER DEFAULT 0,
                completed_items INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                skipped_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)

        # Transfer items table - individual activities within a job
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transfer_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                label_id TEXT NOT NULL,
                sport_type INTEGER,
                activity_name TEXT,
                activity_time TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                retry_count INTEGER DEFAULT 0,
                local_path TEXT,
                garmin_id TEXT,
                error_message TEXT,
                metadata_status TEXT DEFAULT 'pending',
                metadata_error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES transfer_jobs(id) ON DELETE CASCADE
            )
        """)

        # Create indices for efficient queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transfer_jobs_status 
            ON transfer_jobs(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transfer_items_job_id 
            ON transfer_items(job_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transfer_items_status 
            ON transfer_items(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transfer_items_job_status 
            ON transfer_items(job_id, status)
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


def save_operation_history(operation_type, platform, start_date, end_date, total, success, skipped, failed, details=None):
    """Save an operation history record."""
    import json
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO operation_history 
               (operation_type, platform, start_date, end_date, total, success, skipped, failed, details)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (operation_type, platform, start_date, end_date, total, success, skipped, failed, 
             json.dumps(details) if details else None)
        )
        conn.commit()
        return cursor.lastrowid


def get_operation_history(operation_type=None, limit=50):
    """Get operation history, optionally filtered by type."""
    import json
    with get_connection() as conn:
        cursor = conn.cursor()
        if operation_type:
            cursor.execute(
                "SELECT * FROM operation_history WHERE operation_type = ? ORDER BY created_at DESC LIMIT ?",
                (operation_type, limit)
            )
        else:
            cursor.execute("SELECT * FROM operation_history ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            if row.get('details'):
                row['details'] = json.loads(row['details'])
        return rows


def delete_operation_history(record_id: int) -> bool:
    """Delete a single operation history record by ID.

    Args:
        record_id: The ID of the record to delete

    Returns:
        True if deleted, False if not found
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM operation_history WHERE id = ?", (record_id,))
        conn.commit()
        return cursor.rowcount > 0


# Transfer settings operations (singleton row with id=1)
def get_transfer_settings() -> "dict | None":
    """Get transfer settings. Returns None if not initialized."""
    import json
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT settings_json FROM transfer_settings WHERE id = 1")
        row = cursor.fetchone()
        if row:
            return json.loads(row["settings_json"])
        return None


def save_transfer_settings(settings: dict) -> None:
    """Save transfer settings (upsert singleton row)."""
    import json
    settings_json = json.dumps(settings, ensure_ascii=False)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO transfer_settings (id, settings_json)
               VALUES (1, ?)
               ON CONFLICT(id) DO UPDATE SET
               settings_json = excluded.settings_json,
               updated_at = CURRENT_TIMESTAMP""",
            (settings_json,)
        )
        conn.commit()
