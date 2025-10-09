"""
Configuration module for the Claude Telegram Bot.

This module handles environment variables, constants, and configuration settings
for the bot application.
"""

import os
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class BotConfig:
    """Configuration class for the Claude Telegram Bot."""
    
    # Required API keys
    telegram_bot_token: str
    anthropic_api_key: str
    
    # Optional configuration
    allowed_users: List[str]
    default_claude_model: str
    max_history_length: int
    model_cache_duration_hours: int
    
    # Logging configuration
    log_level: str
    enable_file_logging: bool
    log_directory: str
    
    # Database configuration
    database_path: str
    
    @classmethod
    def from_environment(cls) -> 'BotConfig':
        """Create configuration from environment variables."""
        telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        anthropic_key = os.getenv('ANTHROPIC_API_KEY')
        
        if not telegram_token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
        if not anthropic_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        
        allowed_users_str = os.getenv('ALLOWED_USERS', '')
        allowed_users = [user.strip() for user in allowed_users_str.split(',') if user.strip()]
        
        return cls(
            telegram_bot_token=telegram_token,
            anthropic_api_key=anthropic_key,
            allowed_users=allowed_users,
            default_claude_model=os.getenv('DEFAULT_CLAUDE_MODEL', 'claude-3-5-sonnet-latest'),
            max_history_length=int(os.getenv('MAX_HISTORY_LENGTH', '10')),
            model_cache_duration_hours=int(os.getenv('MODEL_CACHE_DURATION_HOURS', '1')),
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            enable_file_logging=os.getenv('ENABLE_FILE_LOGGING', 'False').lower() == 'true',
            log_directory=os.getenv('LOG_DIRECTORY', './logs'),
            database_path=os.getenv('DATABASE_PATH', 'bot_data.db')
        )
    
    def validate(self) -> None:
        """Validate configuration values."""
        if not self.telegram_bot_token:
            raise ValueError("Telegram bot token cannot be empty")
        if not self.anthropic_api_key:
            raise ValueError("Anthropic API key cannot be empty")
        if self.max_history_length < 1:
            raise ValueError("Max history length must be at least 1")
        if self.model_cache_duration_hours < 0:
            raise ValueError("Model cache duration cannot be negative")


# Conversation states
class ConversationStates:
    """Constants for conversation states."""
    MODEL_SELECTION = 0
    CONVERSATION = 1
    ASSISTANT_SELECTION = 2


# Default assistant configuration path
DEFAULT_ASSISTANT_CONFIG_PATH = 'assistants_mode.xml'

# Supported document types
SUPPORTED_DOCUMENT_EXTENSIONS = ('.pdf', '.docx')

# Model filtering patterns
CURRENT_MODEL_PATTERNS = [
    'claude-3-5', 'claude-3-7', 'claude-4', 
    'claude-sonnet-4', 'claude-opus-4'
]

# Telegram message limits
TELEGRAM_MAX_MESSAGE_LENGTH = 4096
TELEGRAM_MAX_CAPTION_LENGTH = 1024

# Response update frequency for streaming
STREAMING_UPDATE_FREQUENCY = 3  # Update every N characters