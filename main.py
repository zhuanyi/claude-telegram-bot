#!/usr/bin/env python3
"""
Entry point for the Claude Telegram Bot application.

This script serves as the main entry point for running the bot application.
It imports and executes the main function from the bot package.
"""

import sys
import os
from dotenv import load_dotenv

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from bot.main import main

if __name__ == '__main__':
    load_dotenv()
    main()