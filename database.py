import sqlite3
from pathlib import Path
from config import get_base_dir

DB_PATH = get_base_dir() / "studybuddy_history.db"

def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                sender TEXT NOT NULL,
                content TEXT NOT NULL,
                is_error INTEGER DEFAULT 0
            )
        """)
        conn.commit()

def save_message(sender: str, content: str, is_error: bool = False) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO messages (sender, content, is_error) VALUES (?, ?, ?)",
                (sender, content, 1 if is_error else 0)
            )
            conn.commit()
    except Exception as e:
        print(f"Error saving chat history: {e}")

def load_recent_messages(limit: int = 40) -> list[dict]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT sender, content, is_error 
                FROM messages 
                ORDER BY id DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [
                {"sender": r[0], "content": r[1], "is_error": bool(r[2])}
                for r in reversed(rows)
            ]
    except Exception as e:
        print(f"Error loading chat history: {e}")
        return []

def clear_all_history() -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages")
            conn.commit()
    except Exception as e:
        print(f"Error clearing chat history: {e}")
