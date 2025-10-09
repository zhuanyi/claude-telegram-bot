# Claude Telegram Bot (Modular Edition)

A sophisticated, modular Telegram bot powered by Anthropic's Claude AI with advanced features including dynamic model management, document processing, and multiple assistant modes.

## 🚀 Features

### Core Functionality
- **Dynamic Model Management**: Automatic discovery and caching of available Claude models
- **Conversation Context**: Maintains conversation history for natural interactions
- **Multiple Assistant Modes**: Configurable AI personalities and system prompts
- **Document Processing**: Upload and query PDF/DOCX documents
- **Streaming Responses**: Real-time response generation with typing indicators

### Advanced Features
- **Sentiment Analysis**: Analyze emotional tone of conversations
- **Text Translation**: Multi-language translation capabilities
- **Code Explanation**: Detailed code analysis and explanations
- **Conversation Summarization**: Generate concise summaries of chat history
- **Rate Limiting**: Built-in protection against abuse
- **User Authorization**: Configurable user access control

### Technical Features
- **Modular Architecture**: Clean separation of concerns with dedicated modules
- **Comprehensive Logging**: Detailed logging with rotation support
- **Error Handling**: Robust error handling with user-friendly messages
- **Configuration Management**: Environment-based configuration
- **Model Prioritization**: Automatic preference for 'latest' model versions

## 📁 Project Structure

```
claude-telegram-bot-multiple/
├── src/bot/                    # Main bot package
│   ├── __init__.py            # Package initialization
│   ├── config.py              # Configuration management
│   ├── model_manager.py       # Dynamic model discovery & caching
│   ├── session_manager.py     # User session & conversation handling
│   ├── handlers.py            # Command handlers & message processing
│   ├── utils.py               # Utility functions & helpers
│   └── main.py                # Main application logic
├── main.py                    # Entry point script
├── requirements.txt           # Python dependencies
├── README.md                  # Project documentation
└── assistants_mode.xml        # Assistant configurations (optional)
```

## 🛠️ Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd claude-telegram-bot-multiple
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**:
   Create a `.env` file or set the following environment variables:
   ```bash
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   ANTHROPIC_API_KEY=your_anthropic_api_key
   
   # Optional configuration
   ALLOWED_USERS=user1,user2,user3  # Comma-separated user IDs
   DEFAULT_CLAUDE_MODEL=claude-3-5-sonnet-latest
   MAX_HISTORY_LENGTH=10
   MODEL_CACHE_DURATION_HOURS=1
   LOG_LEVEL=INFO
   ENABLE_FILE_LOGGING=false
   LOG_DIRECTORY=./logs
   ```

## 🚀 Usage

### Running the Bot

```bash
python main.py
```

### Available Commands

| Command | Description |
|---------|-------------|
| `/start` | Display welcome message and command list |
| `/new` | Start a new conversation (clears history) |
| `/model` | Select from available Claude models |
| `/assistant` | Choose assistant personality mode |
| `/usage` | View session statistics and current settings |
| `/refresh_models` | Manually refresh available models from API |
| `/summarize` | Generate conversation summary |
| `/sentiment [text]` | Analyze sentiment of text or last message |
| `/translate <language> <text>` | Translate text to target language |
| `/explain <language> <code>` | Explain code in specified language |
| `/uploaddoc` | Instructions for document upload |
| `/docquery <question>` | Query uploaded document |

### Document Processing

1. Use `/uploaddoc` to get upload instructions
2. Send a PDF or DOCX file to the bot
3. Use `/docquery <your question>` to analyze the document

### Assistant Modes

Create an `assistants_mode.xml` file to define custom assistant personalities:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<assistants>
    <assistant name="coder">
        <description>Programming expert</description>
        <prompt>You are an expert programmer skilled in multiple languages...</prompt>
    </assistant>
    <assistant name="writer">
        <description>Creative writing assistant</description>
        <prompt>You are a creative writing assistant...</prompt>
    </assistant>
</assistants>
```

## 🏗️ Architecture

### Core Components

1. **Config Module** (`config.py`): Centralized configuration management
2. **Model Manager** (`model_manager.py`): Dynamic model discovery and caching
3. **Session Manager** (`session_manager.py`): User session and conversation handling
4. **Handlers** (`handlers.py`): Command processing and message handling
5. **Utils** (`utils.py`): Common utilities and helper functions
6. **Main** (`main.py`): Application orchestration and startup

### Key Design Patterns

- **Dependency Injection**: Components receive dependencies through constructors
- **Single Responsibility**: Each module has a focused, well-defined purpose
- **Factory Pattern**: Dynamic creation of handlers and managers
- **Strategy Pattern**: Pluggable assistant modes and model selection
- **Observer Pattern**: Event-driven message handling

### Data Flow

1. **Message Reception**: Telegram updates received by handlers
2. **Authorization**: User permissions checked against configuration
3. **Session Management**: User session retrieved/created
4. **Model Selection**: Current model determined from session
5. **Processing**: Message processed with appropriate context
6. **Response**: Formatted response sent back to user

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (required) | - |
| `ANTHROPIC_API_KEY` | Anthropic API key (required) | - |
| `ALLOWED_USERS` | Comma-separated user IDs | All users |
| `DEFAULT_CLAUDE_MODEL` | Default model to use | `claude-3-5-sonnet-latest` |
| `MAX_HISTORY_LENGTH` | Max conversation turns to remember | `10` |
| `MODEL_CACHE_DURATION_HOURS` | Model cache lifetime | `1` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `ENABLE_FILE_LOGGING` | Enable file logging | `false` |
| `LOG_DIRECTORY` | Log file directory | `./logs` |

### Model Management

The bot automatically discovers available Claude models and prioritizes 'latest' versions:

- **Dynamic Discovery**: Fetches models from Anthropic API
- **Intelligent Caching**: Reduces API calls with configurable cache duration
- **Version Prioritization**: Prefers 'latest' versions over dated releases
- **Fallback Support**: Uses hardcoded models if API fails

## 🧪 Development

### Code Structure

The codebase follows Python best practices:

- **Type Hints**: Full type annotations for better IDE support
- **Docstrings**: Comprehensive documentation for all functions
- **Error Handling**: Proper exception handling with logging
- **Async/Await**: Asynchronous programming for better performance
- **PEP 8**: Consistent code formatting

### Adding New Features

1. **New Command**: Add handler to `handlers.py` and register in `main.py`
2. **New Configuration**: Add to `config.py` and update environment variables
3. **New Utility**: Add to `utils.py` with proper documentation
4. **New Model Feature**: Extend `model_manager.py` with new functionality

### Testing

```bash
# Install development dependencies
pip install pytest pytest-asyncio black flake8 mypy

# Run tests (when implemented)
pytest tests/

# Code formatting
black src/

# Linting
flake8 src/

# Type checking
mypy src/
```

## 🔒 Security Considerations

- **API Key Protection**: Never commit API keys to version control
- **User Authorization**: Configure allowed users to prevent abuse
- **Rate Limiting**: Built-in protection against excessive requests
- **Input Validation**: Sanitization of user inputs and file uploads
- **Error Handling**: Sensitive information not exposed in error messages

## 📊 Monitoring & Logging

- **Structured Logging**: Comprehensive logging with configurable levels
- **Error Tracking**: Detailed error reporting with stack traces
- **Performance Monitoring**: Session and model cache statistics
- **Usage Analytics**: Built-in usage tracking per user

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes following the existing code style
4. Add tests for new functionality
5. Update documentation
6. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues and questions:

1. Check the existing documentation
2. Review the logs for error messages
3. Ensure all environment variables are set correctly
4. Verify API keys are valid and have sufficient credits

## 🔄 Changelog

### Version 2.0.0
- Complete modular rewrite with proper separation of concerns
- Dynamic model management with API-based discovery
- Enhanced error handling and logging
- Improved configuration management
- Better documentation and code structure
- Added comprehensive type hints and docstrings

### Version 1.0.0
- Initial monolithic implementation
- Basic Claude integration
- Document processing capabilities
- Assistant modes support