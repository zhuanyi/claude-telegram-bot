"""
Main module for the Claude Telegram Bot.

This module contains the main application logic, including bot setup,
handler registration, and the main entry point for the application.
"""

import logging
import sys
from typing import List

from telegram import BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler

from .config import BotConfig, ConversationStates
from .database import DatabaseManager
from .session_manager import SessionManager
from .model_manager import ModelManager
from .handlers import BotHandlers
from .utils import setup_logging, log_error_with_context


logger = logging.getLogger(__name__)


class ClaudeTelegramBot:
    """
    Main bot application class.
    
    This class orchestrates all the components of the bot including
    configuration, session management, model management, and handler setup.
    """
    
    def __init__(self, config: BotConfig):
        """
        Initialize the bot with configuration.
        
        Args:
            config: Bot configuration instance
        """
        self.config = config
        self.db_manager = DatabaseManager(config.database_path)
        self.session_manager = SessionManager(config, self.db_manager)
        self.model_manager = ModelManager(config)
        self.handlers = BotHandlers(config, self.session_manager, self.model_manager, self.db_manager)
        self.application = None
        
        # Initialize models on startup
        self._initialize_models()
    
    def _initialize_models(self) -> None:
        """Initialize and cache available models on startup."""
        try:
            logger.info("Initializing available models...")
            models = self.model_manager.fetch_available_models()
            logger.info(f"Successfully loaded {len(models)} models: {list(models.keys())}")
        except Exception as e:
            log_error_with_context(logger, "Failed to initialize models", e)
            logger.warning("Bot will continue with fallback models")
    
    def _create_conversation_handlers(self) -> List[ConversationHandler]:
        """Create conversation handlers for the bot."""
        # Model selection conversation handler
        model_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('model', self.handlers.model_selection_command)],
            states={
                ConversationStates.MODEL_SELECTION: [
                    CallbackQueryHandler(self.handlers.model_button_callback)
                ]
            },
            fallbacks=[CommandHandler('start', self.handlers.start_command)]
        )
        
        # Assistant selection conversation handler
        assistant_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('assistant', self.handlers.assistant_selection_command)],
            states={
                ConversationStates.ASSISTANT_SELECTION: [
                    CallbackQueryHandler(self.handlers.assistant_button_callback)
                ]
            },
            fallbacks=[CommandHandler('start', self.handlers.start_command)]
        )
        
        return [model_conv_handler, assistant_conv_handler]
    
    def _register_handlers(self) -> None:
        """Register all command and message handlers."""
        # Basic command handlers
        self.application.add_handler(CommandHandler('start', self.handlers.start_command))
        self.application.add_handler(CommandHandler('new', self.handlers.new_session_command))
        self.application.add_handler(CommandHandler('usage', self.handlers.usage_command))
        self.application.add_handler(CommandHandler('refresh_models', self.handlers.refresh_models_command))
        self.application.add_handler(CommandHandler('status', self.handlers.status_command))
        
        # Conversation handlers
        conversation_handlers = self._create_conversation_handlers()
        for handler in conversation_handlers:
            self.application.add_handler(handler)
        
        # Advanced feature command handlers
        self.application.add_handler(CommandHandler('summarize', self.handlers.summarize_command))
        self.application.add_handler(CommandHandler('sentiment', self.handlers.analyze_sentiment_command))
        self.application.add_handler(CommandHandler('translate', self.handlers.translate_command))
        self.application.add_handler(CommandHandler('explain', self.handlers.code_explain_command))
        
        # Document handling
        self.application.add_handler(CommandHandler('uploaddoc', self.handlers.upload_document_command))
        self.application.add_handler(
            MessageHandler(filters.Document.PDF | filters.Document.DOCX, self.handlers.handle_document)
        )
        self.application.add_handler(CommandHandler('docquery', self.handlers.document_query_command))
        
        # General message handler (should be last)
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.handle_message)
        )
    
    async def _set_bot_commands(self, application=None) -> None:
        """Set up the bot command menu."""
        commands = [
            BotCommand("start", "🚀 Display list of commands"),
            BotCommand("new", "🔄 Start new conversation"),
            BotCommand("model", "🤖 Change AI model"),
            BotCommand("assistant", "🎭 Change assistant mode"),
            BotCommand("usage", "📊 Check session usage"),
            BotCommand("status", "🔍 Check Claude API status"),
            BotCommand("refresh_models", "🔄 Refresh available models"),
            BotCommand("summarize", "📋 Summarize conversation"),
            BotCommand("sentiment", "🎭 Analyze sentiment"),
            BotCommand("translate", "🌍 Translate text"),
            BotCommand("explain", "💻 Explain code"),
            BotCommand("uploaddoc", "📄 Upload document"),
            BotCommand("docquery", "❓ Query uploaded document")
        ]
        
        try:
            await self.application.bot.set_my_commands(commands)
            logger.info("Bot commands set successfully")
        except Exception as e:
            log_error_with_context(logger, "Failed to set bot commands", e)
    
    def create_application(self) -> Application:
        """Create and configure the Telegram application."""
        # Create the Application
        self.application = Application.builder().token(self.config.telegram_bot_token).build()
        
        # Register handlers
        self._register_handlers()
        
        # Add post_init hook to set commands after bot starts
        self.application.post_init = self._set_bot_commands
        
        logger.info("Bot application created and configured successfully")
        return self.application
    
    def run(self) -> None:
        """Run the bot application."""
        try:
            # Create application if not already created
            if not self.application:
                self.create_application()
            
            # Log startup information
            logger.info("=" * 50)
            logger.info("Starting Claude Telegram Bot")
            logger.info("=" * 50)
            logger.info(f"Bot configuration:")
            logger.info(f"  - Default model: {self.config.default_claude_model}")
            logger.info(f"  - Max history length: {self.config.max_history_length}")
            logger.info(f"  - Model cache duration: {self.config.model_cache_duration_hours}h")
            logger.info(f"  - Database path: {self.config.database_path}")
            logger.info(f"  - Allowed users: {len(self.config.allowed_users) if self.config.allowed_users else 'All'}")
            logger.info(f"  - Available assistants: {len(self.session_manager.get_available_assistants())}")
            
            # Start the bot
            logger.info("Bot is starting...")
            self.application.run_polling(drop_pending_updates=True)
            
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            log_error_with_context(logger, "Fatal error during bot execution", e)
            raise
    
    def stop(self) -> None:
        """Stop the bot application."""
        if self.application:
            try:
                self.application.stop_running()
                logger.info("Bot stopped successfully")
            except Exception as e:
                log_error_with_context(logger, "Error stopping bot", e)
    
    def get_stats(self) -> dict:
        """Get bot statistics."""
        try:
            session_stats = self.session_manager.get_session_stats()
            model_stats = {
                'cache_valid': self.model_manager.is_cache_valid(),
                'available_models': len(self.model_manager.fetch_available_models())
            }
            
            return {
                'session_stats': session_stats,
                'model_stats': model_stats,
                'database_path': self.config.database_path,
                'config': {
                    'default_model': self.config.default_claude_model,
                    'max_history': self.config.max_history_length,
                    'cache_duration': self.config.model_cache_duration_hours
                }
            }
        except Exception as e:
            log_error_with_context(logger, "Error getting bot stats", e)
            return {}


def main() -> None:
    """Main entry point for the application."""
    try:
        # Load configuration
        config = BotConfig.from_environment()
        config.validate()
        
        # Setup logging
        setup_logging(config)
        
        # Create and run bot
        bot = ClaudeTelegramBot(config)
        bot.run()
        
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()