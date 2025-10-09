"""
Database module for the Claude Telegram Bot.

This module provides database models, connection management, and data access
methods for storing user preferences, chat history, API usage, and cost tracking.
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class User:
    """User model for database storage."""
    telegram_user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    current_model: str = 'claude-3-5-sonnet-latest'
    current_assistant: str = 'General Assistant'
    is_active: bool = True
    max_history_length: int = 10
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Conversation:
    """Conversation message model for database storage."""
    user_id: int
    role: str  # 'user' or 'assistant'
    content: str
    model_used: Optional[str] = None
    assistant_used: Optional[str] = None
    token_count: int = 0
    id: Optional[int] = None
    created_at: Optional[datetime] = None


@dataclass
class ApiUsage:
    """API usage tracking model."""
    user_id: int
    model_used: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    request_type: str = 'chat'
    id: Optional[int] = None
    created_at: Optional[datetime] = None


@dataclass
class Document:
    """Document upload model."""
    user_id: int
    filename: str
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    content_preview: Optional[str] = None
    is_active: bool = True
    id: Optional[int] = None
    upload_timestamp: Optional[datetime] = None


class DatabaseManager:
    """
    Manages SQLite database operations for the Claude Telegram Bot.
    
    Provides methods for user management, conversation storage, API usage tracking,
    and document management with automatic database initialization.
    """
    
    # Claude model pricing (per 1M tokens)
    MODEL_PRICING = {
        'claude-3-5-haiku-latest': {'input': 0.80, 'output': 4.00},
        'claude-3-5-haiku-20241022': {'input': 0.80, 'output': 4.00},
        'claude-3-5-sonnet-latest': {'input': 3.00, 'output': 15.00},
        'claude-3-5-sonnet-20241022': {'input': 3.00, 'output': 15.00},
        'claude-3-7-sonnet-latest': {'input': 3.00, 'output': 15.00},
        'claude-sonnet-4-20250514': {'input': 15.00, 'output': 75.00},
        'claude-opus-4-20250514': {'input': 15.00, 'output': 75.00},
    }
    
    def __init__(self, db_path: str = "bot_data.db"):
        """
        Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.init_database()
    
    def get_connection(self) -> sqlite3.Connection:
        """Get a database connection with proper configuration."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    
    def init_database(self) -> None:
        """Initialize database with schema if it doesn't exist."""
        with self.get_connection() as conn:
            # Create tables
            self._create_tables(conn)
            # Create indexes
            self._create_indexes(conn)
            # Create triggers
            self._create_triggers(conn)
            
        logger.info(f"Database initialized at {self.db_path}")
    
    def _create_tables(self, conn: sqlite3.Connection) -> None:
        """Create database tables."""
        
        # Users table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                current_model TEXT DEFAULT 'claude-3-5-sonnet-latest',
                current_assistant TEXT DEFAULT 'General Assistant',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                max_history_length INTEGER DEFAULT 10
            )
        """)
        
        # Conversations table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                model_used TEXT,
                assistant_used TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                token_count INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        
        # API usage table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                model_used TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                estimated_cost REAL DEFAULT 0.0,
                request_type TEXT DEFAULT 'chat',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        
        # Documents table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                file_size INTEGER,
                file_type TEXT,
                content_preview TEXT,
                upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        
        # User sessions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_data TEXT,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
    
    def _create_indexes(self, conn: sqlite3.Connection) -> None:
        """Create database indexes for performance."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations (user_id)",
            "CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations (created_at)",
            "CREATE INDEX IF NOT EXISTS idx_api_usage_user_id ON api_usage (user_id)",
            "CREATE INDEX IF NOT EXISTS idx_api_usage_created_at ON api_usage (created_at)",
            "CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents (user_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions (user_id)",
        ]
        
        for index_sql in indexes:
            conn.execute(index_sql)
    
    def _create_triggers(self, conn: sqlite3.Connection) -> None:
        """Create database triggers."""
        
        # Update timestamp trigger
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS update_users_timestamp 
                AFTER UPDATE ON users
                FOR EACH ROW
            BEGIN
                UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
            END
        """)
        
        # Cleanup old conversations trigger
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS cleanup_old_conversations
                AFTER INSERT ON conversations
                FOR EACH ROW
            BEGIN
                DELETE FROM conversations 
                WHERE user_id = NEW.user_id 
                AND id NOT IN (
                    SELECT id FROM conversations 
                    WHERE user_id = NEW.user_id 
                    ORDER BY created_at DESC 
                    LIMIT (SELECT max_history_length FROM users WHERE id = NEW.user_id)
                );
            END
        """)
    
    # User management methods
    def create_or_update_user(self, telegram_user_id: int, **kwargs) -> User:
        """Create a new user or update existing user."""
        with self.get_connection() as conn:
            # Check if user exists
            existing = conn.execute(
                "SELECT * FROM users WHERE telegram_user_id = ?",
                (telegram_user_id,)
            ).fetchone()
            
            if existing:
                # Update existing user
                update_fields = []
                update_values = []
                for key, value in kwargs.items():
                    if hasattr(User, key):
                        update_fields.append(f"{key} = ?")
                        update_values.append(value)
                
                if update_fields:
                    update_values.append(telegram_user_id)
                    conn.execute(
                        f"UPDATE users SET {', '.join(update_fields)} WHERE telegram_user_id = ?",
                        update_values
                    )
                
                # Fetch updated user
                row = conn.execute(
                    "SELECT * FROM users WHERE telegram_user_id = ?",
                    (telegram_user_id,)
                ).fetchone()
            else:
                # Create new user
                user_data = {
                    'telegram_user_id': telegram_user_id,
                    **kwargs
                }
                
                placeholders = ', '.join(['?' for _ in user_data])
                columns = ', '.join(user_data.keys())
                values = list(user_data.values())
                
                cursor = conn.execute(
                    f"INSERT INTO users ({columns}) VALUES ({placeholders})",
                    values
                )
                
                # Fetch created user
                row = conn.execute(
                    "SELECT * FROM users WHERE id = ?",
                    (cursor.lastrowid,)
                ).fetchone()
            
            return self._row_to_user(row)
    
    def get_user_by_telegram_id(self, telegram_user_id: int) -> Optional[User]:
        """Get user by Telegram user ID."""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE telegram_user_id = ?",
                (telegram_user_id,)
            ).fetchone()
            
            return self._row_to_user(row) if row else None
    
    def update_user_preferences(self, telegram_user_id: int, model: str = None, assistant: str = None) -> None:
        """Update user preferences."""
        with self.get_connection() as conn:
            updates = []
            values = []
            
            if model:
                updates.append("current_model = ?")
                values.append(model)
            if assistant:
                updates.append("current_assistant = ?")
                values.append(assistant)
            
            if updates:
                values.append(telegram_user_id)
                conn.execute(
                    f"UPDATE users SET {', '.join(updates)} WHERE telegram_user_id = ?",
                    values
                )
    
    # Conversation management methods
    def add_conversation(self, user_id: int, role: str, content: str, 
                        model_used: str = None, assistant_used: str = None, 
                        token_count: int = 0) -> Conversation:
        """Add a conversation message."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO conversations (user_id, role, content, model_used, assistant_used, token_count)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, role, content, model_used, assistant_used, token_count))
            
            # Fetch created conversation
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?",
                (cursor.lastrowid,)
            ).fetchone()
            
            return self._row_to_conversation(row)
    
    def get_conversation_history(self, telegram_user_id: int, limit: int = None) -> List[Conversation]:
        """Get conversation history for a user."""
        with self.get_connection() as conn:
            query = """
                SELECT c.* FROM conversations c
                JOIN users u ON c.user_id = u.id
                WHERE u.telegram_user_id = ?
                ORDER BY c.created_at DESC
            """
            
            params = [telegram_user_id]
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_conversation(row) for row in reversed(rows)]
    
    def clear_conversation_history(self, telegram_user_id: int) -> None:
        """Clear conversation history for a user."""
        with self.get_connection() as conn:
            conn.execute("""
                DELETE FROM conversations 
                WHERE user_id = (SELECT id FROM users WHERE telegram_user_id = ?)
            """, (telegram_user_id,))
    
    # API usage tracking methods
    def record_api_usage(self, telegram_user_id: int, model_used: str, 
                        input_tokens: int, output_tokens: int, 
                        request_type: str = 'chat') -> ApiUsage:
        """Record API usage and calculate cost."""
        total_tokens = input_tokens + output_tokens
        estimated_cost = self.calculate_cost(model_used, input_tokens, output_tokens)
        
        with self.get_connection() as conn:
            # Get user ID
            user_row = conn.execute(
                "SELECT id FROM users WHERE telegram_user_id = ?",
                (telegram_user_id,)
            ).fetchone()
            
            if not user_row:
                raise ValueError(f"User {telegram_user_id} not found")
            
            user_id = user_row['id']
            
            cursor = conn.execute("""
                INSERT INTO api_usage (user_id, model_used, input_tokens, output_tokens, 
                                     total_tokens, estimated_cost, request_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, model_used, input_tokens, output_tokens, 
                  total_tokens, estimated_cost, request_type))
            
            # Fetch created record
            row = conn.execute(
                "SELECT * FROM api_usage WHERE id = ?",
                (cursor.lastrowid,)
            ).fetchone()
            
            return self._row_to_api_usage(row)
    
    def get_user_usage_stats(self, telegram_user_id: int, days: int = 30) -> Dict[str, Any]:
        """Get usage statistics for a user."""
        with self.get_connection() as conn:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            row = conn.execute("""
                SELECT 
                    COUNT(a.id) as total_requests,
                    SUM(a.total_tokens) as total_tokens,
                    SUM(a.estimated_cost) as total_cost,
                    SUM(a.input_tokens) as total_input_tokens,
                    SUM(a.output_tokens) as total_output_tokens
                FROM users u
                LEFT JOIN api_usage a ON u.id = a.user_id
                WHERE u.telegram_user_id = ? AND a.created_at >= ?
                GROUP BY u.id
            """, (telegram_user_id, cutoff_date)).fetchone()
            
            if row:
                return {
                    'total_requests': row['total_requests'] or 0,
                    'total_tokens': row['total_tokens'] or 0,
                    'total_cost': round(row['total_cost'] or 0, 4),
                    'total_input_tokens': row['total_input_tokens'] or 0,
                    'total_output_tokens': row['total_output_tokens'] or 0,
                    'days': days
                }
            else:
                return {
                    'total_requests': 0,
                    'total_tokens': 0,
                    'total_cost': 0.0,
                    'total_input_tokens': 0,
                    'total_output_tokens': 0,
                    'days': days
                }
    
    def calculate_cost(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate estimated cost for API usage."""
        pricing = self.MODEL_PRICING.get(model_id)
        if not pricing:
            # Use default pricing for unknown models
            pricing = {'input': 3.00, 'output': 15.00}
        
        input_cost = (input_tokens / 1_000_000) * pricing['input']
        output_cost = (output_tokens / 1_000_000) * pricing['output']
        
        return input_cost + output_cost
    
    # Document management methods
    def save_document(self, telegram_user_id: int, filename: str, 
                     file_size: int = None, file_type: str = None, 
                     content_preview: str = None) -> Document:
        """Save document information."""
        with self.get_connection() as conn:
            # Get user ID
            user_row = conn.execute(
                "SELECT id FROM users WHERE telegram_user_id = ?",
                (telegram_user_id,)
            ).fetchone()
            
            if not user_row:
                raise ValueError(f"User {telegram_user_id} not found")
            
            user_id = user_row['id']
            
            # Deactivate previous documents
            conn.execute(
                "UPDATE documents SET is_active = 0 WHERE user_id = ?",
                (user_id,)
            )
            
            # Create preview (first 500 chars)
            if content_preview and len(content_preview) > 500:
                content_preview = content_preview[:500] + "..."
            
            cursor = conn.execute("""
                INSERT INTO documents (user_id, filename, file_size, file_type, content_preview)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, filename, file_size, file_type, content_preview))
            
            # Fetch created document
            row = conn.execute(
                "SELECT * FROM documents WHERE id = ?",
                (cursor.lastrowid,)
            ).fetchone()
            
            return self._row_to_document(row)
    
    def get_active_document(self, telegram_user_id: int) -> Optional[Document]:
        """Get active document for a user."""
        with self.get_connection() as conn:
            row = conn.execute("""
                SELECT d.* FROM documents d
                JOIN users u ON d.user_id = u.id
                WHERE u.telegram_user_id = ? AND d.is_active = 1
                ORDER BY d.upload_timestamp DESC
                LIMIT 1
            """, (telegram_user_id,)).fetchone()
            
            return self._row_to_document(row) if row else None
    
    # Helper methods for converting database rows to objects
    def _row_to_user(self, row: sqlite3.Row) -> User:
        """Convert database row to User object."""
        return User(
            id=row['id'],
            telegram_user_id=row['telegram_user_id'],
            username=row['username'],
            first_name=row['first_name'],
            last_name=row['last_name'],
            current_model=row['current_model'],
            current_assistant=row['current_assistant'],
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
            updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None,
            is_active=bool(row['is_active']),
            max_history_length=row['max_history_length']
        )
    
    def _row_to_conversation(self, row: sqlite3.Row) -> Conversation:
        """Convert database row to Conversation object."""
        return Conversation(
            id=row['id'],
            user_id=row['user_id'],
            role=row['role'],
            content=row['content'],
            model_used=row['model_used'],
            assistant_used=row['assistant_used'],
            token_count=row['token_count'],
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
        )
    
    def _row_to_api_usage(self, row: sqlite3.Row) -> ApiUsage:
        """Convert database row to ApiUsage object."""
        return ApiUsage(
            id=row['id'],
            user_id=row['user_id'],
            model_used=row['model_used'],
            input_tokens=row['input_tokens'],
            output_tokens=row['output_tokens'],
            total_tokens=row['total_tokens'],
            estimated_cost=row['estimated_cost'],
            request_type=row['request_type'],
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
        )
    
    def _row_to_document(self, row: sqlite3.Row) -> Document:
        """Convert database row to Document object."""
        return Document(
            id=row['id'],
            user_id=row['user_id'],
            filename=row['filename'],
            file_size=row['file_size'],
            file_type=row['file_type'],
            content_preview=row['content_preview'],
            is_active=bool(row['is_active']),
            upload_timestamp=datetime.fromisoformat(row['upload_timestamp']) if row['upload_timestamp'] else None
        )