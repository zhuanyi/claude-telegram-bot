"""
Session management module for the Claude Telegram Bot.

This module handles user sessions, conversation history, and assistant configurations.
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import xml.etree.ElementTree as ET

from .config import BotConfig, DEFAULT_ASSISTANT_CONFIG_PATH
from .database import DatabaseManager, User, Conversation


logger = logging.getLogger(__name__)


@dataclass
class DocumentContext:
    """Context for uploaded documents."""
    filename: str
    text: str
    upload_timestamp: float = field(default_factory=lambda: __import__('time').time())


@dataclass
class UserSession:
    """
    Represents a user session with conversation history and settings.
    
    This class encapsulates all user-specific state including:
    - Conversation history for context awareness
    - Current model and assistant preferences
    - Document context for uploaded files
    - Usage statistics
    """
    
    user_id: int
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    current_model: str = field(default='claude-3-5-sonnet-latest')
    current_assistant: str = field(default='default')
    token_usage: int = field(default=0)
    document_context: Optional[DocumentContext] = field(default=None)
    
    def add_conversation_turn(self, user_message: str, assistant_response: str, max_history: int) -> None:
        """
        Add a conversation turn to the history.
        
        Args:
            user_message: The user's message
            assistant_response: The assistant's response
            max_history: Maximum number of conversation turns to keep
        """
        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": assistant_response})
        
        # Trim history if it exceeds max length
        if len(self.conversation_history) > max_history:
            self.conversation_history = self.conversation_history[-max_history:]
    
    def clear_conversation_history(self) -> None:
        """Clear the conversation history."""
        self.conversation_history = []
        logger.info(f"Cleared conversation history for user {self.user_id}")
    
    def set_document_context(self, filename: str, text: str) -> None:
        """
        Set document context for the session.
        
        Args:
            filename: Name of the uploaded document
            text: Extracted text from the document
        """
        self.document_context = DocumentContext(filename=filename, text=text)
        logger.info(f"Set document context for user {self.user_id}: {filename}")
    
    def clear_document_context(self) -> None:
        """Clear the document context."""
        self.document_context = None
        logger.info(f"Cleared document context for user {self.user_id}")
    
    def get_context_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the current session context.
        
        Returns:
            Dictionary containing session summary information
        """
        return {
            'user_id': self.user_id,
            'current_model': self.current_model,
            'current_assistant': self.current_assistant,
            'conversation_turns': len(self.conversation_history) // 2,
            'token_usage': self.token_usage,
            'has_document': self.document_context is not None,
            'document_filename': self.document_context.filename if self.document_context else None
        }


class AssistantConfigLoader:
    """
    Loads and manages assistant configurations from XML files.
    
    This class handles parsing assistant configurations that define
    different AI assistant personas and their system prompts.
    """
    
    @staticmethod
    def load_assistants(config_path: str = DEFAULT_ASSISTANT_CONFIG_PATH) -> Dict[str, Dict[str, str]]:
        """
        Load assistant configurations from XML file.
        
        Args:
            config_path: Path to the XML configuration file
            
        Returns:
            Dictionary mapping assistant names to their configurations
        """
        assistants = {}
        try:
            tree = ET.parse(config_path)
            root = tree.getroot()
            
            for assistant in root.findall('assistant'):
                name = assistant.get('name')
                prompt_elem = assistant.find('prompt')
                description_elem = assistant.find('description')
                
                if name and prompt_elem is not None and description_elem is not None:
                    assistants[name] = {
                        'name': name,
                        'prompt': prompt_elem.text.strip() if prompt_elem.text else '',
                        'description': description_elem.text.strip() if description_elem.text else ''
                    }
                else:
                    logger.warning(f"Incomplete assistant configuration for: {name}")
            
            logger.info(f"Loaded {len(assistants)} assistant configurations")
            return assistants
            
        except FileNotFoundError:
            logger.warning(f"Assistant configuration file not found: {config_path}")
            return {}
        except ET.ParseError as e:
            logger.error(f"Error parsing assistant configuration XML: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error loading assistant configurations: {e}")
            return {}


class SessionManager:
    """
    Manages user sessions and assistant configurations with database persistence.
    
    This class provides a centralized way to manage user sessions,
    including creation, retrieval, and cleanup of user data, now with
    database persistence for conversation history and user preferences.
    """
    
    def __init__(self, config: BotConfig, db_manager: DatabaseManager):
        """
        Initialize the session manager.
        
        Args:
            config: Bot configuration
            db_manager: Database manager instance
        """
        self.config = config
        self.db_manager = db_manager
        self.user_sessions: Dict[int, UserSession] = {}
        self.assistants = AssistantConfigLoader.load_assistants()
        
        # Add default assistant if none are loaded
        if not self.assistants:
            self.assistants = {
                'default': {
                    'name': 'default',
                    'prompt': 'You are a helpful AI assistant.',
                    'description': 'General purpose AI assistant'
                }
            }
    
    def get_or_create_session(self, user_id: int, username: str = None, 
                            first_name: str = None, last_name: str = None) -> UserSession:
        """
        Get or create a user session with database persistence.
        
        Args:
            user_id: Telegram user ID
            username: Telegram username
            first_name: User's first name
            last_name: User's last name
            
        Returns:
            UserSession instance for the user
        """
        if user_id not in self.user_sessions:
            # Get or create user in database
            db_user = self.db_manager.create_or_update_user(
                telegram_user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            
            # Load conversation history from database
            conversation_history = self._load_conversation_history(user_id)
            
            # Create session with database data
            self.user_sessions[user_id] = UserSession(
                user_id=user_id,
                conversation_history=conversation_history,
                current_model=db_user.current_model,
                current_assistant=db_user.current_assistant
            )
            
            # Load active document if exists
            active_doc = self.db_manager.get_active_document(user_id)
            if active_doc:
                self.user_sessions[user_id].set_document_context(
                    active_doc.filename, 
                    active_doc.content_preview or ""
                )
            
            logger.info(f"Created new session for user {user_id}")
        
        return self.user_sessions[user_id]
    
    def get_session(self, user_id: int) -> Optional[UserSession]:
        """
        Get an existing user session.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            UserSession instance or None if not found
        """
        return self.user_sessions.get(user_id)
    
    def _load_conversation_history(self, user_id: int) -> List[Dict[str, str]]:
        """
        Load conversation history from database.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            List of conversation messages
        """
        db_conversations = self.db_manager.get_conversation_history(
            user_id, limit=self.config.max_history_length
        )
        
        conversation_history = []
        for conv in db_conversations:
            conversation_history.append({
                "role": conv.role,
                "content": conv.content
            })
        
        return conversation_history
    
    def save_conversation_turn(self, user_id: int, user_message: str, 
                             assistant_response: str, model_used: str, 
                             assistant_used: str) -> None:
        """
        Save a conversation turn to the database.
        
        Args:
            user_id: Telegram user ID
            user_message: User's message
            assistant_response: Assistant's response
            model_used: Model used for the response
            assistant_used: Assistant mode used
        """
        # Get database user ID
        db_user = self.db_manager.get_user_by_telegram_id(user_id)
        if not db_user:
            logger.error(f"User {user_id} not found in database")
            return
        
        # Save user message
        self.db_manager.add_conversation(
            user_id=db_user.id,
            role='user',
            content=user_message,
            model_used=model_used,
            assistant_used=assistant_used
        )
        
        # Save assistant response
        self.db_manager.add_conversation(
            user_id=db_user.id,
            role='assistant',
            content=assistant_response,
            model_used=model_used,
            assistant_used=assistant_used
        )
    
    def update_user_preferences(self, user_id: int, model: str = None, 
                              assistant: str = None) -> None:
        """
        Update user preferences in the database.
        
        Args:
            user_id: Telegram user ID
            model: New model preference
            assistant: New assistant preference
        """
        self.db_manager.update_user_preferences(user_id, model, assistant)
        
        # Update in-memory session if exists
        if user_id in self.user_sessions:
            if model:
                self.user_sessions[user_id].current_model = model
            if assistant:
                self.user_sessions[user_id].current_assistant = assistant
    
    def delete_session(self, user_id: int) -> bool:
        """
        Delete a user session from memory (database data remains).
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if session was deleted, False if not found
        """
        if user_id in self.user_sessions:
            del self.user_sessions[user_id]
            logger.info(f"Deleted in-memory session for user {user_id}")
            return True
        return False
    
    def clear_conversation_history(self, user_id: int) -> None:
        """
        Clear conversation history for a user in both memory and database.
        
        Args:
            user_id: Telegram user ID
        """
        # Clear from database
        self.db_manager.clear_conversation_history(user_id)
        
        # Clear from memory session if exists
        if user_id in self.user_sessions:
            self.user_sessions[user_id].clear_conversation_history()
        
        logger.info(f"Cleared conversation history for user {user_id}")
    
    def get_assistant_config(self, assistant_name: str) -> Dict[str, str]:
        """
        Get configuration for a specific assistant.
        
        Args:
            assistant_name: Name of the assistant
            
        Returns:
            Assistant configuration dictionary
        """
        return self.assistants.get(assistant_name, self.assistants.get('default', {
            'name': 'default',
            'prompt': 'You are a helpful AI assistant.',
            'description': 'General purpose AI assistant'
        }))
    
    def get_available_assistants(self) -> Dict[str, Dict[str, str]]:
        """
        Get all available assistant configurations.
        
        Returns:
            Dictionary of all assistant configurations
        """
        return self.assistants.copy()
    
    def reload_assistants(self) -> None:
        """Reload assistant configurations from file."""
        self.assistants = AssistantConfigLoader.load_assistants()
        logger.info("Reloaded assistant configurations")
    
    def get_session_count(self) -> int:
        """Get the number of active sessions."""
        return len(self.user_sessions)
    
    def get_session_stats(self) -> Dict[str, Any]:
        """
        Get statistics about all sessions from database.
        
        Returns:
            Dictionary containing session statistics
        """
        # Get stats from database for more accurate data
        with self.db_manager.get_connection() as conn:
            # Total users
            total_users = conn.execute("SELECT COUNT(*) FROM users WHERE is_active = 1").fetchone()[0]
            
            # Total conversations (count pairs of user/assistant messages)
            total_conversations = conn.execute(
                "SELECT COUNT(*) / 2 FROM conversations"
            ).fetchone()[0]
            
            # Active documents
            active_documents = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE is_active = 1"
            ).fetchone()[0]
            
            # Total API requests
            total_requests = conn.execute(
                "SELECT COUNT(*) FROM api_usage"
            ).fetchone()[0]
            
            # Total cost
            total_cost = conn.execute(
                "SELECT COALESCE(SUM(estimated_cost), 0) FROM api_usage"
            ).fetchone()[0]
        
        return {
            'total_users': total_users,
            'active_sessions': len(self.user_sessions),
            'total_conversations': int(total_conversations),
            'active_documents': active_documents,
            'total_api_requests': total_requests,
            'total_estimated_cost': round(total_cost, 4)
        }
    
    def cleanup_expired_sessions(self, max_age_hours: int = 24) -> int:
        """
        Clean up expired sessions based on inactivity.
        
        Args:
            max_age_hours: Maximum age in hours before session cleanup
            
        Returns:
            Number of sessions cleaned up
        """
        # This is a placeholder for future implementation
        # In a real implementation, you'd track last activity timestamps
        # and remove sessions that haven't been used recently
        logger.info("Session cleanup not implemented yet")
        return 0