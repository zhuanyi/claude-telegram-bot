"""
Command handlers for the Claude Telegram Bot.

This module contains all the command handlers and message processing logic
for the Telegram bot, including conversation handling, model selection,
and advanced features.
"""

import logging
import traceback
from typing import Dict, Any
import aiohttp
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import ContextTypes, ConversationHandler
import anthropic

from .config import BotConfig, ConversationStates, STREAMING_UPDATE_FREQUENCY
from .session_manager import SessionManager
from .model_manager import ModelManager
from .database import DatabaseManager
from .utils import (
    strip_outer_code_block, validate_document_type, extract_document_text,
    create_temp_file, cleanup_temp_file, safe_format_exception, log_error_with_context,
    telegram_retry
)


logger = logging.getLogger(__name__)


class BotHandlers:
    """
    Container class for all bot command handlers.
    
    This class encapsulates all the command handlers and provides
    a clean interface for registering them with the Telegram bot.
    """
    
    def __init__(self, config: BotConfig, session_manager: SessionManager, 
                 model_manager: ModelManager, db_manager: DatabaseManager):
        """
        Initialize the handlers.
        
        Args:
            config: Bot configuration
            session_manager: Session manager instance
            model_manager: Model manager instance
            db_manager: Database manager instance
        """
        self.config = config
        self.session_manager = session_manager
        self.model_manager = model_manager
        self.db_manager = db_manager
    
    def is_user_authorized(self, user_id: int) -> bool:
        """Check if a user is authorized to use the bot."""
        if not self.config.allowed_users:
            return True  # No restrictions if no allowed users specified
        return int(user_id) in self.config.allowed_users
    
    @telegram_retry(max_retries=3, base_delay=1.0)
    async def _send_message_with_retry(self, update: Update, text: str, **kwargs) -> Any:
        """Send a message with automatic retry on rate limit errors."""
        return await update.message.reply_text(text, **kwargs)
    
    @telegram_retry(max_retries=3, base_delay=1.0)
    async def _edit_message_with_retry(self, message, text: str, **kwargs) -> Any:
        """Edit a message with automatic retry on rate limit errors."""
        return await message.edit_text(text, **kwargs)
    
    @telegram_retry(max_retries=3, base_delay=1.0)
    async def _send_chat_action_with_retry(self, context, chat_id: int, action) -> Any:
        """Send chat action with automatic retry on rate limit errors."""
        return await context.bot.send_chat_action(chat_id=chat_id, action=action)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /start command."""
        user_id = update.effective_user.id
        
        if not self.is_user_authorized(user_id):
            await update.message.reply_text("⚠️ Unauthorized access")
            return
        
        user = update.effective_user
        session = self.session_manager.get_or_create_session(
            user_id, user.username, user.first_name, user.last_name
        )
        self.session_manager.clear_conversation_history(user_id)
        
        await update.message.reply_text(
            "🤖 Hi\\! I'm a Claude\\-powered Telegram bot\\.\n\n"
            "📋 *Available Commands:*\n"
            "/new \\- Start new conversation\n"
            "/model \\- Change AI model\n"
            "/assistant \\- Change assistant mode\n"
            "/usage \\- Check token usage\n"
            "/status \\- Check Claude API status\n"
            "/refresh\\_models \\- Refresh available models\n"
            "/summarize \\- Summarize conversation\n"
            "/sentiment \\- Analyze sentiment\n"
            "/translate \\- Translate text\n"
            "/explain \\- Explain code\n"
            "/uploaddoc \\- Upload document\n"
            "/docquery \\- Query uploaded document\n\n"
            "💬 Just send me a message to start chatting\\!",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    async def new_session_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Start a new conversation session."""
        user_id = update.effective_user.id
        
        if not self.is_user_authorized(user_id):
            await update.message.reply_text("⚠️ Unauthorized access")
            return
        
        user = update.effective_user
        session = self.session_manager.get_or_create_session(
            user_id, user.username, user.first_name, user.last_name
        )
        self.session_manager.clear_conversation_history(user_id)
        
        await update.message.reply_text(
            "🔄 Started a new conversation session. Previous context has been cleared."
        )
    
    async def refresh_models_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Manually refresh the available models from the API."""
        user_id = update.effective_user.id

        if not self.is_user_authorized(user_id):
            await update.message.reply_text("⚠️ Unauthorized access")
            return

        # Show processing message
        processing_msg = await self._send_message_with_retry(update, "🔍 Refreshing model list\\.\\.\\.")

        try:
            # Clear cache to force refresh
            self.model_manager.clear_cache()

            # Fetch fresh models (this will update the cache internally)
            models = self.model_manager.fetch_available_models()

            if not models:
                await self._edit_message_with_retry(
                    processing_msg,
                    "❌ No models found\\. Please try again later\\.",
                    parse_mode=constants.ParseMode.MARKDOWN_V2
                )
                return

            # Escape model names for Markdown V2
            escaped_names = [self._escape_md_v2(name) for name in models.keys()]
            model_list = "\n".join([f"• {name}" for name in escaped_names])

            # Verify cache was updated
            cache_status = "✅ Valid" if self.model_manager.is_cache_valid() else "❌ Expired"

            await self._edit_message_with_retry(
                processing_msg,
                f"🔄 *Refreshed model list\\!*\n\n"
                f"📊 *Found {len(models)} available models:*\n{model_list}\n\n"
                f"🔄 *Cache Status:* {cache_status}",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            log_error_with_context(logger, "Error refreshing models", e)
            error_str = self._escape_md_v2(str(e)[:100])
            await self._edit_message_with_retry(
                processing_msg,
                f"❌ *Failed to refresh models*\n\nError: {error_str}",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Query and display Claude API status information."""
        user_id = update.effective_user.id
        
        if not self.is_user_authorized(user_id):
            await update.message.reply_text("⚠️ Unauthorized access")
            return
        
        # Show processing message
        processing_msg = await self._send_message_with_retry(update, "🔍 Checking Claude API status\\.\\.\\.")

        try:
            # Query Claude API status endpoint
            async with aiohttp.ClientSession() as session:
                headers = {
                    'x-api-key': self.config.anthropic_api_key,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json'
                }
                
                async with session.get('https://api.anthropic.com/v1/models', headers=headers) as response:
                    if response.status == 200:
                        api_status = "🟢 *Online*"
                        response_time = response.headers.get('x-response-time', 'N/A')
                    elif response.status == 429:
                        api_status = "🟡 *Rate Limited*"
                        response_time = "N/A"
                    elif response.status >= 500:
                        api_status = "🔴 *Server Issues*"
                        response_time = "N/A"
                    else:
                        api_status = f"🟡 *Status {response.status}*"
                        response_time = "N/A"
                
                # Get available models
                try:
                    available_models = self.model_manager.fetch_available_models()
                    models_status = f"✅ *{len(available_models)} models available*"
                    escaped_names = [self._escape_md_v2(name) for name in list(available_models.keys())[:10]]
                    model_list = "\n".join([f"• {name}" for name in escaped_names])
                    if len(available_models) > 10:
                        more_count = len(available_models) - 10
                        model_list += f"\n• \\.\\.\\. and {more_count} more"
                except Exception as e:
                    models_status = "❌ *Failed to fetch models*"
                    error_str = self._escape_md_v2(str(e)[:100])
                    model_list = f"Error: {error_str}"

                # Get current session info
                user = update.effective_user
                user_session = self.session_manager.get_or_create_session(
                    user_id, user.username, user.first_name, user.last_name
                )
                current_model = self._escape_md_v2(
                    self.model_manager.get_model_display_name(user_session.current_model)
                )
                assistant_name = self._escape_md_v2(user_session.current_assistant)

                # Get cache status
                cache_status = "✅ *Valid*" if self.model_manager.is_cache_valid() else "❌ *Expired*"

                status_message = (
                    f"📊 *Claude API Status Report*\n\n"
                    f"🌐 *API Status:* {api_status}\n"
                    f"⏱️ *Response Time:* {response_time}ms\n\n"
                    f"🤖 *Models Status:* {models_status}\n"
                    f"🔄 *Models Cache:* {cache_status}\n\n"
                    f"👤 *Your Current Settings:*\n"
                    f"• *Model:* {current_model}\n"
                    f"• *Assistant:* {assistant_name}\n\n"
                    f"📋 *Available Models:*\n{model_list}"
                )
                
                await self._edit_message_with_retry(
                    processing_msg, 
                    status_message,
                    parse_mode=constants.ParseMode.MARKDOWN_V2
                )
                
        except aiohttp.ClientError as e:
            error_str = self._escape_md_v2(str(e))
            await self._edit_message_with_retry(
                processing_msg,
                f"❌ *Network Error*\n\nFailed to connect to Claude API:\n`{error_str}`",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            log_error_with_context(logger, "Error in status command", e)
            error_msg = safe_format_exception(e)
            await self._edit_message_with_retry(
                processing_msg,
                f"❌ *Error checking status:* {error_msg}"
            )
    
    async def model_selection_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Allow user to select Claude model dynamically from API."""
        user_id = update.effective_user.id
        
        if not self.is_user_authorized(user_id):
            await update.message.reply_text("⚠️ Unauthorized access")
            return ConversationHandler.END
        
        try:
            # Get available models
            available_models = self.model_manager.fetch_available_models()
            
            if not available_models:
                await update.message.reply_text("❌ No models available\\. Please try again later\\.")
                return ConversationHandler.END
            
            # Create keyboard dynamically
            keyboard = []
            row = []
            for i, (display_name, model_id) in enumerate(available_models.items(), 1):
                button = InlineKeyboardButton(
                    display_name, 
                    callback_data=f'model_{model_id}'
                )
                row.append(button)
                
                # Create new row every 2 buttons
                if i % 2 == 0:
                    keyboard.append(row)
                    row = []
            
            # Add remaining buttons if any
            if row:
                keyboard.append(row)
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "🤖 *Select a Claude AI model:*",
                reply_markup=reply_markup,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return ConversationStates.MODEL_SELECTION
            
        except Exception as e:
            log_error_with_context(logger, "Error in model selection", e)
            await update.message.reply_text("❌ Error loading models\\. Please try again later\\.")
            return ConversationHandler.END
    
    async def model_button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle model selection via inline button."""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        
        if not self.is_user_authorized(user_id):
            await query.edit_message_text("⚠️ Unauthorized access")
            return ConversationHandler.END
        
        try:
            user = update.effective_user
            session = self.session_manager.get_or_create_session(
                user_id, user.username, user.first_name, user.last_name
            )
            
            # Extract selected model ID
            model_id = query.data.replace('model_', '')
            session.current_model = model_id
            
            # Update preferences in database
            self.session_manager.update_user_preferences(user_id, model=model_id)
            
            # Get display name for confirmation and escape for Markdown V2 (handles parentheses)
            raw_display_name = self.model_manager.get_model_display_name(model_id)
            display_name = self._escape_md_v2(raw_display_name)
            await query.edit_message_text(
                f"✅ *Model changed to {display_name}*\n\n"
                "You can now continue your conversation\\.",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return ConversationHandler.END
            
        except Exception as e:
            log_error_with_context(logger, "Error in model selection callback", e)
            await query.edit_message_text("❌ Error changing model\\. Please try again\\.")
            return ConversationHandler.END
    
    async def usage_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Check token usage and provide detailed cost information."""
        user_id = update.effective_user.id
        
        if not self.is_user_authorized(user_id):
            await update.message.reply_text("⚠️ Unauthorized access")
            return
        
        user = update.effective_user
        session = self.session_manager.get_or_create_session(
            user_id, user.username, user.first_name, user.last_name
        )
        display_name = self._escape_md_v2(
            self.model_manager.get_model_display_name(session.current_model)
        )

        # Get usage statistics from database
        usage_stats = self.db_manager.get_user_usage_stats(user_id, days=30)
        session_stats = session.get_context_summary()
        cache_status = "✅ Valid" if self.model_manager.is_cache_valid() else "❌ Expired"
        
        # Format numbers with commas
        total_tokens_str = f"{usage_stats['total_tokens']:,}".replace(',', '\\,')
        input_tokens_str = f"{usage_stats['total_input_tokens']:,}".replace(',', '\\,')
        output_tokens_str = f"{usage_stats['total_output_tokens']:,}".replace(',', '\\,')
        cost_str = f"{usage_stats['total_cost']:.4f}".replace('.', '\\.')

        # Prepare document info
        if session_stats['has_document']:
            doc_filename = self._escape_md_v2(session_stats['document_filename'])
            doc_info = f'✅ {doc_filename}'
        else:
            doc_info = '❌ None'
        assistant_name = self._escape_md_v2(session.current_assistant)

        await update.message.reply_text(
            f"📊 *Usage Statistics \\(Last 30 Days\\):*\n\n"
            f"🤖 *Current Model:* {display_name}\n"
            f"🎭 *Assistant:* {assistant_name}\n"
            f"💬 *Session Turns:* {session_stats['conversation_turns']}\n\n"
            f"📈 *API Usage:*\n"
            f"• *Total Requests:* {usage_stats['total_requests']}\n"
            f"• *Total Tokens:* {total_tokens_str}\n"
            f"• *Input Tokens:* {input_tokens_str}\n"
            f"• *Output Tokens:* {output_tokens_str}\n"
            f"💰 *Estimated Cost:* ${cost_str}\n\n"
            f"📄 *Document:* {doc_info}\n"
            f"🔄 *Models Cache:* {cache_status}",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    async def assistant_selection_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Allow user to select an assistant mode."""
        user_id = update.effective_user.id
        
        if not self.is_user_authorized(user_id):
            await update.message.reply_text("⚠️ Unauthorized access")
            return ConversationHandler.END
        
        try:
            # Get available assistants
            assistants = self.session_manager.get_available_assistants()
            
            if not assistants:
                await update.message.reply_text("❌ No assistants available\\.")
                return ConversationHandler.END
            
            # Create dynamic keyboard based on loaded assistants
            keyboard = []
            row = []
            for i, (name, details) in enumerate(assistants.items(), 1):
                button = InlineKeyboardButton(
                    f"{name} - {details['description']}", 
                    callback_data=f'assistant_{name}'
                )
                row.append(button)
                
                # Create new row every 2 buttons or at the end
                if i % 2 == 0 or i == len(assistants):
                    keyboard.append(row)
                    row = []
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "🎭 *Select an Assistant Mode:*",
                reply_markup=reply_markup,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return ConversationStates.ASSISTANT_SELECTION
            
        except Exception as e:
            log_error_with_context(logger, "Error in assistant selection", e)
            await update.message.reply_text("❌ Error loading assistants\\. Please try again later\\.")
            return ConversationHandler.END
    
    async def assistant_button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle assistant selection via inline button."""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        
        if not self.is_user_authorized(user_id):
            await query.edit_message_text("⚠️ Unauthorized access")
            return ConversationHandler.END
        
        try:
            user = update.effective_user
            session = self.session_manager.get_or_create_session(
                user_id, user.username, user.first_name, user.last_name
            )
            
            # Extract selected assistant
            selected_assistant = query.data.split('_')[1]
            session.current_assistant = selected_assistant
            
            # Update preferences in database
            self.session_manager.update_user_preferences(user_id, assistant=selected_assistant)
            
            assistant_config = self.session_manager.get_assistant_config(selected_assistant)
            description = self._escape_md_v2(assistant_config.get('description', 'No description'))
            escaped_assistant = self._escape_md_v2(selected_assistant)
            await query.edit_message_text(
                f"✅ *Assistant mode changed to {escaped_assistant}*\n\n"
                f"📝 *Description:* {description}\n\n"
                "You can now continue your conversation\\.",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return ConversationHandler.END
            
        except Exception as e:
            log_error_with_context(logger, "Error in assistant selection callback", e)
            await query.edit_message_text("❌ Error changing assistant\\. Please try again\\.")
            return ConversationHandler.END
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming messages with conversation context."""
        user_id = update.effective_user.id
        user_message = update.message.text
        
        if not self.is_user_authorized(user_id):
            await update.message.reply_text("⚠️ Unauthorized access")
            return
        
        # Get or create user session
        user = update.effective_user
        session = self.session_manager.get_or_create_session(
            user_id, user.username, user.first_name, user.last_name
        )
        
        # Show typing indicator
        await self._send_chat_action_with_retry(
            context, 
            update.effective_chat.id, 
            constants.ChatAction.TYPING
        )
        
        try:
            # Initialize Anthropic client
            client = anthropic.AsyncAnthropic(api_key=self.config.anthropic_api_key)
            
            # Get assistant prompt
            assistant_config = self.session_manager.get_assistant_config(session.current_assistant)
            system_prompt = assistant_config.get('prompt', 'You are a helpful AI assistant.')
            
            # Prepare messages with conversation history
            messages = session.conversation_history + [
                {"role": "user", "content": user_message}
            ]
            
            # Create initial message
            message = await self._send_message_with_retry(update, "⌛ Generating response...")
            full_response = ""
            last_sent_content = "⌛ Generating response..."
            
            # Generate response using Claude with streaming
            input_tokens = 0
            output_tokens = 0
            
            async with client.messages.stream(
                model=session.current_model,
                system=system_prompt,
                max_tokens=1000,
                messages=messages
            ) as stream:
                # Iterate through stream events
                async for event in stream:
                    if event.type == "message_start":
                        # Track input tokens
                        if hasattr(event.message, 'usage'):
                            input_tokens = event.message.usage.input_tokens
                    elif event.type == "content_block_delta":
                        if event.delta.text:
                            full_response += event.delta.text
                            # Update message periodically for smoothness
                            if len(full_response) % STREAMING_UPDATE_FREQUENCY == 0:
                                new_content = full_response[:4000]  # Telegram limit
                                # Only edit if content has changed
                                if new_content != last_sent_content:
                                    try:
                                        await self._edit_message_with_retry(message, new_content)
                                        last_sent_content = new_content
                                    except Exception:
                                        pass  # Ignore edit errors during streaming
                                    
                                    # Maintain typing indicator
                                    await self._send_chat_action_with_retry(
                                        context,
                                        update.effective_chat.id,
                                        constants.ChatAction.TYPING
                                    )
                    elif event.type == "message_delta":
                        # Track output tokens
                        if hasattr(event.delta, 'usage'):
                            output_tokens = event.delta.usage.output_tokens
            
            # Remove wrapping code block if the entire reply is fenced
            formatted_response = strip_outer_code_block(full_response)
            
            # Estimate tokens if not provided by API
            if input_tokens == 0:
                input_tokens = len(' '.join([msg['content'] for msg in messages])) // 4  # Rough estimate
            if output_tokens == 0:
                output_tokens = len(formatted_response) // 4  # Rough estimate
            
            # Record API usage in database
            try:
                self.db_manager.record_api_usage(
                    telegram_user_id=user_id,
                    model_used=session.current_model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    request_type='chat'
                )
            except Exception as e:
                logger.warning(f"Failed to record API usage: {e}")
            
            # Update conversation history in database
            self.session_manager.save_conversation_turn(
                user_id=user_id,
                user_message=user_message,
                assistant_response=formatted_response,
                model_used=session.current_model,
                assistant_used=session.current_assistant
            )
            
            # Update in-memory session
            session.add_conversation_turn(
                user_message, 
                formatted_response, 
                self.config.max_history_length
            )
            
            # Display final response
            final_content = formatted_response[:4000]  # Telegram limit
            if final_content != last_sent_content:
                await self._edit_safe_markdown(message, final_content)

        except Exception as e:
            log_error_with_context(logger, "Error in message handling", e)
            error_msg = safe_format_exception(e)
            await self._edit_message_with_retry(message, f"❌ Error: {error_msg}")

    async def summarize_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Summarize the previous conversation."""
        user_id = update.effective_user.id
        
        if not self.is_user_authorized(user_id):
            await update.message.reply_text("⚠️ Unauthorized access")
            return
        
        session = self.session_manager.get_or_create_session(user_id)
        
        # Check if there's a conversation history to summarize
        if not session.conversation_history:
            await update.message.reply_text("❌ No conversation history to summarize\\.")
            return
        
        try:
            client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
            
            # Combine conversation history into a single text
            conversation_text = "\n".join([
                f"{msg['role'].capitalize()}: {msg['content']}" 
                for msg in session.conversation_history
            ])
            
            # Generate summary
            response = client.messages.create(
                model=session.current_model,
                max_tokens=300,
                messages=[
                    {
                        "role": "user",
                        "content": f"Please provide a concise summary of the following conversation:\n\n{conversation_text}"
                    }
                ]
            )
            
            summary = response.content[0].text
            await self._send_safe_markdown(update, f"📋 *Conversation Summary:*\n\n{summary}")

        except Exception as e:
            log_error_with_context(logger, "Summarization error", e)
            await update.message.reply_text("❌ Could not generate summary\\.")

    async def analyze_sentiment_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Perform sentiment analysis on the previous conversation or provided text."""
        user_id = update.effective_user.id
        
        if not self.is_user_authorized(user_id):
            await update.message.reply_text("⚠️ Unauthorized access")
            return
        
        session = self.session_manager.get_or_create_session(user_id)
        
        # Check for text to analyze (either from args or conversation history)
        text_to_analyze = " ".join(context.args) if context.args else (
            session.conversation_history[-1]['content'] if session.conversation_history else None
        )
        
        if not text_to_analyze:
            await update.message.reply_text(
                "❌ Please provide text to analyze or have an active conversation\\.\n\n"
                "*Usage:* `/sentiment <text to analyze>`",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return
        
        try:
            client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
            
            response = client.messages.create(
                model=session.current_model,
                max_tokens=200,
                messages=[
                    {
                        "role": "user",
                        "content": f"""Perform a detailed sentiment analysis on the following text:

Text: {text_to_analyze}

Please provide:
1. Overall sentiment (Positive/Negative/Neutral)
2. Emotional tone
3. Key emotional indicators
4. Brief explanation of the sentiment assessment"""
                    }
                ]
            )
            
            sentiment_analysis = response.content[0].text
            await self._send_safe_markdown(update, f"🎭 *Sentiment Analysis:*\n\n{sentiment_analysis}")

        except Exception as e:
            log_error_with_context(logger, "Sentiment analysis error", e)
            await update.message.reply_text("❌ Could not perform sentiment analysis\\.")

    async def translate_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Translate text to a specified language."""
        user_id = update.effective_user.id
        
        if not self.is_user_authorized(user_id):
            await update.message.reply_text("⚠️ Unauthorized access")
            return
        
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ *Usage:* `/translate <target_language> <text>`\n\n"
                "*Example:* `/translate Spanish Hello, how are you?`",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return
        
        session = self.session_manager.get_or_create_session(user_id)
        target_language = context.args[0]
        text_to_translate = " ".join(context.args[1:])
        
        try:
            client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
            
            response = client.messages.create(
                model=session.current_model,
                max_tokens=300,
                messages=[
                    {
                        "role": "user",
                        "content": f"""Translate the following text to {target_language}:

Original Text: {text_to_translate}

Please provide:
1. The translated text
2. A brief note about any cultural nuances or contextual considerations"""
                    }
                ]
            )
            
            translation = response.content[0].text
            escaped_language = target_language.replace('_', '\\_')
            await self._send_safe_markdown(update, f"🌍 *Translation to {escaped_language}:*\n\n{translation}");

        except Exception as e:
            log_error_with_context(logger, "Translation error", e)
            await update.message.reply_text("❌ Could not perform translation\\.")

    async def code_explain_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Explain a piece of code or provide code-related assistance."""
        user_id = update.effective_user.id
        
        if not self.is_user_authorized(user_id):
            await update.message.reply_text("⚠️ Unauthorized access")
            return
        
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ *Usage:* `/explain <programming_language> <code>`\n\n"
                "*Example:* `/explain Python def fibonacci(n):`",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return
        
        session = self.session_manager.get_or_create_session(user_id)
        language = context.args[0]
        code_to_explain = " ".join(context.args[1:])
        
        try:
            client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
            
            response = client.messages.create(
                model=session.current_model,
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": f"""Provide a detailed explanation of the following {language} code:

Code:
{code_to_explain}

Please explain:
1. What the code does
2. How it works line by line
3. Time and space complexity
4. Potential improvements or best practices"""
                    }
                ]
            )
            
            code_explanation = response.content[0].text
            escaped_language = language.replace('_', '\\_')
            await self._send_safe_markdown(update, f"💻 *Code Explanation \\({escaped_language}\\):*\n\n{code_explanation}");

        except Exception as e:
            log_error_with_context(logger, "Code explanation error", e)
            await update.message.reply_text("❌ Could not explain the code\\.")

    async def upload_document_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle document upload command."""
        user_id = update.effective_user.id
        
        if not self.is_user_authorized(user_id):
            await update.message.reply_text("⚠️ Unauthorized access")
            return
        
        await update.message.reply_text(
            "📄 *Document Upload*\n\n"
            "Upload a PDF or Word document, and I'll help you analyze it\\! "
            "After uploading, you can ask questions about the document using `/docquery`\\.\n\n"
            "*Supported formats:* PDF, DOCX",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Process uploaded document and store its contents."""
        user_id = update.effective_user.id
        document = update.message.document
        
        if not self.is_user_authorized(user_id):
            await update.message.reply_text("⚠️ Unauthorized access")
            return
        
        # Validate file type
        if not validate_document_type(document.file_name):
            escaped_filename = self._escape_md_v2(document.file_name)
            await update.message.reply_text(
                f"❌ *Unsupported file type*\n\n"
                f"Please upload only PDF or Word documents\\.\n"
                f"*Received:* {escaped_filename}",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return
        
        try:
            # Show processing message
            processing_msg = await update.message.reply_text("⏳ Processing document\\.\\.\\.")

            # Download the file
            file = await context.bot.get_file(document.file_id)
            temp_filename = create_temp_file(
                suffix=('.' + document.file_name.split('.')[-1])
            )

            # Download file content and write to temporary file
            file_content = await file.download_as_bytearray()
            with open(temp_filename, 'wb') as f:
                f.write(file_content)
            
            # Extract text
            text = extract_document_text(temp_filename, document.file_name)
            
            # Clean up temporary file
            cleanup_temp_file(temp_filename)
            
            # Store document context in session and database
            user = update.effective_user
            session = self.session_manager.get_or_create_session(
                user_id, user.username, user.first_name, user.last_name
            )
            session.set_document_context(document.file_name, text)
            
            # Save document to database
            self.db_manager.save_document(
                telegram_user_id=user_id,
                filename=document.file_name,
                file_size=document.file_size,
                file_type=document.file_name.split('.')[-1].lower(),
                content_preview=text
            )
            
            escaped_filename = self._escape_md_v2(document.file_name)
            # Update processing message
            await processing_msg.edit_text(
                f"✅ *Document processed successfully\\!*\n\n"
                f"📄 *File:* {escaped_filename}\n"
                f"📊 *Size:* {len(text)} characters\n\n"
                f"You can now ask questions about the document using `/docquery <your question>`",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            
        except Exception as e:
            log_error_with_context(logger, "Document upload error", e)
            error_msg = safe_format_exception(e)
            await processing_msg.edit_text(f"❌ *Error processing document:* {error_msg}")

    async def document_query_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Allow querying the uploaded document using Claude."""
        user_id = update.effective_user.id
        
        if not self.is_user_authorized(user_id):
            await update.message.reply_text("⚠️ Unauthorized access")
            return
        
        user = update.effective_user
        session = self.session_manager.get_or_create_session(
            user_id, user.username, user.first_name, user.last_name
        )
        
        # Check if a document is uploaded (check both session and database)
        active_doc = self.db_manager.get_active_document(user_id)
        if not session.document_context and not active_doc:
            await update.message.reply_text(
                "❌ *No document uploaded*\n\n"
                "Please upload a document first using the file upload feature\\.",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return
        
        # Use database document if session doesn't have one
        if not session.document_context and active_doc:
            session.set_document_context(active_doc.filename, active_doc.content_preview or "")
        
        # Check if query is provided
        query = " ".join(context.args) if context.args else None
        if not query:
            await update.message.reply_text(
                "❌ *Usage:* `/docquery <your question about the document>`\n\n"
                "*Example:* `/docquery What is the main topic of this document?`",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return
        
        try:
            # Initialize Anthropic client
            client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
            
            # Prepare the query with document context
            full_context = (
                f"Document: {session.document_context.filename}\n\n"
                f"Document Text: {session.document_context.text}\n\n"
                f"Question: {query}"
            )
            
            # Generate response
            response = client.messages.create(
                model=session.current_model,
                max_tokens=1000,
                messages=[
                    {
                        "role": "user",
                        "content": full_context
                    }
                ]
            )
            
            # Send Claude's analysis
            analysis = response.content[0].text
            # Send header with formatting, then chunk the body
            await self._send_safe_markdown(update, "📄 *Document Analysis:*")
            await self._send_long_markdown(update, analysis)

        except Exception as e:
            log_error_with_context(logger, "Document query error", e)
            error_msg = safe_format_exception(e)
            await update.message.reply_text(f"❌ *Error querying document:* {error_msg}")

    def _escape_md_v2(self, text: str) -> str:
        # Escape Telegram Markdown V2 special characters safely
        if text is None:
            return ""
        # Order matters: escape backslash first
        escaped = text.replace('\\', '\\\\')
        for ch in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
            escaped = escaped.replace(ch, '\\' + ch)
        return escaped

    async def _send_safe_markdown(self, update: Update, text: str) -> None:
        """Send text as Markdown V2, fallback to plain text if parsing fails."""
        try:
            await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.warning(f"Markdown V2 parsing failed, sending as plain text: {e}")
            try:
                await update.message.reply_text(text)
            except Exception as e2:
                logger.error(f"Failed to send message as plain text: {e2}")

    async def _edit_safe_markdown(self, message, text: str) -> None:
        """Edit message as Markdown V2, fallback to plain text if parsing fails."""
        try:
            await message.edit_text(text, parse_mode=constants.ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.warning(f"Markdown V2 parsing failed, editing as plain text: {e}")
            try:
                await message.edit_text(text)
            except Exception as e2:
                logger.error(f"Failed to edit message as plain text: {e2}")

    async def _send_long_markdown(self, update: Update, text: str, chunk_size: int = 3800) -> None:
        """
        Send a long message by splitting into safe chunks with Markdown V2 fallback.
        chunk_size < 4096 to leave room for prefix/newlines.
        """
        if not text:
            return
        # Split at newline boundaries when possible to avoid breaking formatting
        start = 0
        length = len(text)
        while start < length:
            end = min(start + chunk_size, length)
            # try to break at last newline before end
            newline_pos = text.rfind('\n', start, end)
            if newline_pos != -1 and newline_pos > start:
                end = newline_pos + 1
            chunk = text[start:end]
            await self._send_safe_markdown(update, chunk)
            start = end

