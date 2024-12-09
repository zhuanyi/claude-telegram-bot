import asyncio
import os
from typing import Dict, Any

import anthropic
import telebot
import speech_recognition as sr
from telebot.types import Message
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Configuration and Environment Variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')
ALLOWED_USERS = os.getenv('ALLOWED_USERS', '').split(',')


class ClaudeTelegramBot:
    def __init__(self):
        # Initialize Anthropic Claude Client
        self.claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

        # Initialize Telegram Bot
        self.bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

        # Chat modes configuration
        self.chat_modes = self._load_chat_modes()

        # User conversation states
        self.user_states: Dict[int, Dict[str, Any]] = {}

    def _load_chat_modes(self):
        # Load predefined chat modes from YAML or JSON
        return {
            'assistant': {
                'name': '👩🏼‍🎓 Assistant',
                'prompt': 'You are a helpful AI assistant.'
            },
            'code_assistant': {
                'name': '👩🏼‍💻 Code Assistant',
                'prompt': 'You are an expert programming assistant focusing on code help.'
            },
            # Add more chat modes as needed
        }

    async def start_streaming_response(self, message: Message, prompt: str, chat_mode: str = 'assistant'):
        """Stream Claude's response in real-time"""
        try:
            # Use Claude 3 API for streaming
            stream = self.claude_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
                stream=True
            )

            # Send initial response message
            response_message = self.bot.send_message(message.chat.id, "Typing...")

            # Accumulate full response
            full_response = ""
            for chunk in stream:
                if chunk.type == "content_block_delta":
                    delta = chunk.delta.text
                    full_response += delta

                    # Update message every few characters to simulate typing
                    if len(full_response) % 10 == 0:
                        self.bot.edit_message_text(
                            chat_id=message.chat.id,
                            message_id=response_message.message_id,
                            text=full_response
                        )

            # Final update with complete response
            self.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=response_message.message_id,
                text=full_response
            )

        except Exception as e:
            self.bot.reply_to(message, f"Error: {str(e)}")

    def handle_voice_message(self, message: Message):
        """Convert voice message to text using speech recognition"""
        try:
            # Download voice file
            voice_file = self.bot.get_file(message.voice.file_id)
            downloaded_file = self.bot.download_file(voice_file.file_path)

            # Use speech recognition to convert to text
            recognizer = sr.Recognizer()
            with sr.AudioFile(downloaded_file) as source:
                audio = recognizer.record(source)

            text = recognizer.recognize_google(audio)

            # Process transcribed text
            self.start_streaming_response(message, text)

        except Exception as e:
            self.bot.reply_to(message, f"Speech recognition error: {str(e)}")

    def setup_handlers(self):
        """Set up Telegram bot message handlers"""

        @self.bot.message_handler(commands=['start', 'help'])
        def send_welcome(message):
            welcome_text = """
            Welcome to Claude AI Telegram Bot! 
            Available modes:
            👩🏼‍🎓 Assistant
            👩🏼‍💻 Code Assistant

            Use /mode to switch modes
            """
            self.bot.reply_to(message, welcome_text)

        @self.bot.message_handler(commands=['mode'])
        def change_mode(message):
            # Implement mode selection logic
            modes_keyboard = telebot.types.ReplyKeyboardMarkup(row_width=2)
            for mode_key, mode_info in self.chat_modes.items():
                modes_keyboard.add(telebot.types.KeyboardButton(mode_info['name']))

            self.bot.send_message(
                message.chat.id,
                "Select Chat Mode:",
                reply_markup=modes_keyboard
            )

        @self.bot.message_handler(content_types=['voice'])
        def handle_voice(message):
            self.handle_voice_message(message)

        @self.bot.message_handler(func=lambda message: True)
        def handle_message(message):
            # Implement user authorization if needed
            if ALLOWED_USERS and str(message.from_user.id) not in ALLOWED_USERS:
                self.bot.reply_to(message, "Unauthorized access")
                return

            # Determine current chat mode
            current_mode = self.user_states.get(
                message.from_user.id,
                {'mode': 'assistant'}
            )['mode']

            # Get corresponding system prompt
            system_prompt = self.chat_modes.get(
                current_mode,
                self.chat_modes['assistant']
            )['prompt']

            # Start streaming response
            self.start_streaming_response(message, message.text)

    def run(self):
        """Start the Telegram bot"""
        self.setup_handlers()
        self.bot.polling(none_stop=True)


def main():
    bot = ClaudeTelegramBot()
    bot.run()


if __name__ == '__main__':
    main()