import os, sys
import logging
import traceback
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand,constants
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler, ContextTypes
import anthropic
from typing import Dict, List, Any
import xml.etree.ElementTree as ET
import PyPDF2
import docx
import tempfile
from asyncio import sleep


# Conversation states
MODEL_SELECTION, CONVERSATION, ASSISTANT_SELECTION = range(3)

# Configuration and Environment Variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
ALLOWED_USERS = os.getenv('ALLOWED_USERS', '').split(',')

# Setup logging
# LOG_DIR = '/app/logs'
# os.makedirs(LOG_DIR, exist_ok=True)

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # # File Handler with Rotation
    # log_file_path = os.path.join(LOG_DIR, 'bot.log')
    # file_handler = RotatingFileHandler(
    #     log_file_path,
    #     maxBytes=10*1024*1024,  # 10 MB
    #     backupCount=5
    # )
    # file_handler.setLevel(logging.DEBUG)
    # file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # file_handler.setFormatter(file_formatter)
    # logger.addHandler(file_handler)

    # Create formatters
    std_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Create handlers
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(std_formatter)
    stdout_handler.setLevel(logging.INFO)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(std_formatter)
    stderr_handler.setLevel(logging.ERROR)

    # Add handlers to the logger
    logger.addHandler(stdout_handler)
    logger.addHandler(stderr_handler)

    return logger

logger = setup_logging()
#load_dotenv()

# Utility to avoid wrapping entire responses in code blocks
def strip_outer_code_block(text: str) -> str:
    """Remove a surrounding triple backtick block if it encloses the entire text."""
    stripped = text.strip()
    if stripped.startswith('```') and stripped.endswith('```') and stripped.count('```') == 2:
        # Drop first and last line containing the backticks
        body = stripped.split('\n')
        return '\n'.join(body[1:-1])
    return text

# Assistant Configurations Loader
class AssistantConfigLoader:
    @staticmethod
    def load_assistants(config_path='assistants_mode.xml'):
        """
        Load assistant configurations from XML
        """
        assistants = {}
        try:
            tree = ET.parse(config_path)
            root = tree.getroot()
            
            for assistant in root.findall('assistant'):
                name = assistant.get('name')
                prompt = assistant.find('prompt').text.strip()
                description = assistant.find('description').text.strip()
                
                assistants[name] = {
                    'name': name,
                    'prompt': prompt,
                    'description': description
                }
            
            return assistants
        except Exception as e:
            logger.error(f"Error loading assistant configurations: {e}")
            return {}

# Session management and configuration
class UserSession:
    def __init__(self, user_id):
        self.user_id = user_id
        self.conversation_history: List[Dict] = []
        self.current_model = os.getenv('DEFAULT_CLAUDE_MODEL', 'claude-3-5-sonnet-20241022')
        self.current_assistant = 'default'
        self.token_usage = 0

# Limit the number of conversation exchanges stored per user
MAX_HISTORY_LENGTH = 10

# Global session storage
user_sessions: Dict[int, UserSession] = {}

# Available Claude models
CLAUDE_MODELS = {
    'Haiku-3-5': 'claude-3-5-haiku-latest',
    'Sonnet-3-7': 'claude-3-7-sonnet-latest',
    'Sonnet-4': 'claude-sonnet-4-20250514',
    'Opus-4': 'claude-opus-4-20250514'
}

# Fetch available models from Anthropic API
def fetch_available_models() -> List[str]:
    """Retrieve list of Claude models via the API."""
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        models = client.models.list()
        names = [m.name for m in models]
        logger.info("Available models: %s", ", ".join(names))
        return names
    except Exception as e:
        logger.error(f"Failed to fetch models list: {e}")
        return []

# Obtain available model list at startup for reference
AVAILABLE_MODEL_NAMES = fetch_available_models()

# Load Assistant Configurations
ASSISTANTS = AssistantConfigLoader.load_assistants()

def get_or_create_session(user_id: int) -> UserSession:
    """Get or create a user session."""
    if user_id not in user_sessions:
        user_sessions[user_id] = UserSession(user_id)
    return user_sessions[user_id]

async def start_command(update: Update, context):
    """Handle the /start command."""
    user_id = update.effective_user.id
    session = get_or_create_session(user_id)
    
    # Reset conversation history
    session.conversation_history = []
    
    await update.message.reply_text(
        "Hi! I'm a Claude-powered Telegram bot. Available commands:\n"
        "/new - Start new conversation\n"
        "/model - Change AI model\n"
        "/assistant - Change assistant mode\n"
        "/usage - Check token usage\n"
        "/summarize - Summarize conversation\n"
        "/sentiment - Analyze sentiment\n"
        "/translate - Translate text\n"
        "/explain - Explain code\n"
        "/uploaddoc - Upload docx or pdf command\n"
        "/docquery - Query the doc uploaded"
    )


async def new_session_command(update: Update, context):
    """Start a new conversation session."""
    user_id = update.effective_user.id
    session = get_or_create_session(user_id)

    # Clear conversation history
    session.conversation_history = []

    await update.message.reply_text("Started a new conversation session. Previous context has been cleared.")


async def model_selection_command(update: Update, context):
    """Allow user to select Claude model."""
    keyboard = [
        [
            InlineKeyboardButton("Haiku 3.5 (Fastest, Cheap)", callback_data='model_haiku-3-5'),
            InlineKeyboardButton("Sonnet 3.7 (Most intelligent)", callback_data='model_sonnet-3-7'),
        ],
        [
            InlineKeyboardButton("Sonnet 4 (Most Capable)", callback_data='model_sonnet-4'),
            InlineKeyboardButton("Opus 4 (Most Capable)", callback_data='model_opus-4')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Select a Claude AI model:",
        reply_markup=reply_markup
    )
    return MODEL_SELECTION

async def model_button_callback(update: Update, context):
    """Handle model selection via inline button."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    session = get_or_create_session(user_id)

    # Extract selected model
    selected_model = query.data.split('_')[1]
    model_key = selected_model.capitalize()
    session.current_model = CLAUDE_MODELS.get(model_key, CLAUDE_MODELS['Haiku-3-5'])

    display_name = model_key.replace('-', ' ')

    await query.edit_message_text(
        f"Model changed to {display_name}. "
        "You can now continue your conversation."
    )
    return ConversationHandler.END


async def usage_command(update: Update, context):
    """Check token usage and provide information."""
    user_id = update.effective_user.id
    session = get_or_create_session(user_id)

    await update.message.reply_text(
        f"Current Session Details:\n"
        f"• Current Model: {session.current_model}\n"
        f"• Tokens Used: {session.token_usage}"
    )

async def assistant_selection_command(update: Update, context):
    """Allow user to select an assistant mode."""
    # Create dynamic keyboard based on loaded assistants
    keyboard = []
    row = []
    for i, (name, details) in enumerate(ASSISTANTS.items(), 1):
        button = InlineKeyboardButton(
            f"{name} - {details['description']}", 
            callback_data=f'assistant_{name}'
        )
        row.append(button)
        
        # Create new row every 2 buttons or at the end
        if i % 2 == 0 or i == len(ASSISTANTS):
            keyboard.append(row)
            row = []
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Select an Assistant Mode:", 
        reply_markup=reply_markup
    )
    return ASSISTANT_SELECTION

async def assistant_button_callback(update: Update, context):
    """Handle assistant selection via inline button."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    session = get_or_create_session(user_id)
    
    # Extract selected assistant
    selected_assistant = query.data.split('_')[1]
    session.current_assistant = selected_assistant
    
    assistant_details = ASSISTANTS.get(selected_assistant, {})
    
    await query.edit_message_text(
        f"Assistant mode changed to {selected_assistant}. "
        f"Description: {assistant_details.get('description', 'No description')}\n"
        "You can now continue your conversation."
    )
    return ConversationHandler.END


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages with conversation context."""
    user_id = update.effective_user.id
    user_message = update.message.text

    # Implement user authorization if needed
    if ALLOWED_USERS and str(user_id) not in ALLOWED_USERS:
        await update.message.reply_text("Unauthorized access")
        return
    
    # Get or create user session
    session = get_or_create_session(user_id)
    
    # Validate environment variables
    anthropic_key = os.getenv('ANTHROPIC_API_KEY')
    if not anthropic_key:
        await update.message.reply_text("Bot configuration error: Anthropic API key missing")
        return

    # Show typing indicator
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, 
        action=constants.ChatAction.TYPING
    )

    try:
        # Initialize Anthropic client
        client = anthropic.AsyncAnthropic(api_key=anthropic_key)

        # Get assistant prompt if exists
        assistant_details = ASSISTANTS.get(session.current_assistant, {})
        system_prompt = assistant_details.get('prompt', 'You are a helpful AI assistant.')

        # Prepare messages with conversation history and system prompt
        messages = session.conversation_history + [
            {"role": "user", "content": user_message}
        ]

        # Create initial message
        message = await update.message.reply_text("⌛ Generating response...")
        full_response = ""
        # Generate response using Claude
        async with client.messages.stream(
            model=session.current_model,
            system=system_prompt,
            max_tokens=1000,
            messages=messages
        )as stream:
            # Iterate through stream events correctly
            async for event in stream:
                if event.type == "content_block_delta":
                    if event.delta.text:
                        full_response += event.delta.text
                        # Update message every 3 characters for smoothness
                        if len(full_response) % 3 == 0:
                            await message.edit_text(full_response)
                            # Maintain typing indicator
                            await context.bot.send_chat_action(
                                chat_id=update.effective_chat.id,
                                action=constants.ChatAction.TYPING
                            )
        # Remove wrapping code block if the entire reply is fenced
        formatted_response = strip_outer_code_block(full_response)

        # Update conversation history for context awareness
        session.conversation_history.append({"role": "user", "content": user_message})
        session.conversation_history.append({"role": "assistant", "content": formatted_response})
        if len(session.conversation_history) > MAX_HISTORY_LENGTH:
            session.conversation_history = session.conversation_history[-MAX_HISTORY_LENGTH:]

        # Display response with original formatting so that only code or
        # formulas appear in blocks while normal text remains plain
        await message.edit_text(
            formatted_response,
            parse_mode=constants.ParseMode.MARKDOWN
        )

    except Exception as e:
        logger.error(f"Error in message handling: {e}")
        logger.error(traceback.format_exc())
        await message.edit_text(f"⚠️ Error: An error occurred while processing your message. {str(e)}")

# Include previously defined advanced feature commands
async def summarize_command(update: Update, context):
    """Summarize the previous conversation."""
    user_id = update.effective_user.id
    session = get_or_create_session(user_id)
    
    # Check if there's a conversation history to summarize
    if not session.conversation_history:
        await update.message.reply_text("No conversation history to summarize.")
        return
    
    try:
        client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        
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
        await update.message.reply_text("Conversation Summary:\n" + summary)
    
    except Exception as e:
        logger.error(f"Summarization error: {e}")
        await update.message.reply_text("Could not generate summary.")

async def analyze_sentiment_command(update: Update, context):
    """Perform sentiment analysis on the previous conversation or provided text."""
    user_id = update.effective_user.id
    session = get_or_create_session(user_id)
    
    # Check for text to analyze (either from args or conversation history)
    text_to_analyze = " ".join(context.args) if context.args else (
        session.conversation_history[-1]['content'] if session.conversation_history else None
    )
    
    if not text_to_analyze:
        await update.message.reply_text("Please provide text to analyze or have an active conversation.")
        return
    
    try:
        client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        
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
        await update.message.reply_text("Sentiment Analysis:\n" + sentiment_analysis)
    
    except Exception as e:
        logger.error(f"Sentiment analysis error: {e}")
        await update.message.reply_text("Could not perform sentiment analysis.")

async def translate_command(update: Update, context):
    """Translate text to a specified language."""
    user_id = update.effective_user.id
    session = get_or_create_session(user_id)
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /translate <target_language> <text>\n"
            "Example: /translate Spanish Hello, how are you?"
        )
        return
    
    target_language = context.args[0]
    text_to_translate = " ".join(context.args[1:])
    
    try:
        client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        
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
        await update.message.reply_text(f"Translation to {target_language}:\n{translation}")
    
    except Exception as e:
        logger.error(f"Translation error: {e}")
        await update.message.reply_text("Could not perform translation.")

async def code_explain_command(update: Update, context):
    """Handle incoming messages with conversation context."""
    user_id = update.effective_user.id
    # Get or create user session
    session = get_or_create_session(user_id)

    """Explain a piece of code or provide code-related assistance."""
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /explain <programming_language> <code>\n"
            "Example: /explain Python def fibonacci(n):"
        )
        return
    
    language = context.args[0]
    code_to_explain = " ".join(context.args[1:])
    
    try:
        client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        
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
        await update.message.reply_text(f"Code Explanation ({language}):\n{code_explanation}")
    
    except Exception as e:
        logger.error(f"Code explanation error: {e}")
        await update.message.reply_text("Could not explain the code.")


async def upload_document_command(update: Update, context):
    """
    Handle document upload command.
    Instructs user on how to upload a document.
    """
    await update.message.reply_text(
        "Upload a PDF or Word document, and I'll help you analyze it! "
        "After uploading, you can ask questions about the document."
    )


async def handle_document(update: Update, context):
    """
    Process uploaded document and store its contents.
    Supports PDF and DOCX files.
    """
    user_id = update.effective_user.id
    document = update.document

    # Validate file type
    if not document.file_name.lower().endswith(('.pdf', '.docx')):
        await update.message.reply_text(
            "Please upload only PDF or Word documents."
        )
        return

    try:
        # Download the file
        file = await context.bot.get_file(document.file_id)

        # Create a temporary file to store the document
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(document.file_name)[1]) as temp_file:
            await file.download_to_file(temp_file.name)
            temp_filename = temp_file.name

        # Extract text based on file type
        if document.file_name.lower().endswith('.pdf'):
            text = extract_text_from_pdf(temp_filename)
        else:
            text = extract_text_from_docx(temp_filename)

        # Remove temporary file
        os.unlink(temp_filename)

        # Store document context for the user
        session = get_or_create_session(user_id)
        session.document_context = {
            'filename': document.file_name,
            'text': text
        }

        # Provide feedback and instructions
        await update.message.reply_text(
            f"Document '{document.file_name}' uploaded successfully! "
            "You can now ask questions about the document. "
            "Use /docquery to ask a specific question."
        )

    except Exception as e:
        logger.error(f"Document upload error: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(
            "An error occurred while processing the document. Please try again."
        )


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text from a PDF file.
    """
    text = []
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text.append(page.extract_text())
        return "\n".join(text)
    except Exception as e:
        logger.error(f"PDF text extraction error: {e}")
        return "Could not extract text from PDF"


def extract_text_from_docx(docx_path: str) -> str:
    """
    Extract text from a Word document.
    """
    try:
        doc = docx.Document(docx_path)
        return "\n".join([para.text for para in doc.paragraphs if para.text])
    except Exception as e:
        logger.error(f"DOCX text extraction error: {e}")
        return "Could not extract text from Word document"


async def document_query_command(update: Update, context):
    """
    Allow querying the uploaded document using Claude.
    """
    user_id = update.effective_user.id
    session = get_or_create_session(user_id)

    # Check if a document is uploaded
    if not hasattr(session, 'document_context') or not session.document_context:
        await update.message.reply_text(
            "Please upload a document first using a file upload."
        )
        return

    # Check if query is provided
    query = " ".join(context.args) if context.args else None
    if not query:
        await update.message.reply_text(
            "Usage: /docquery <your question about the document>\n"
            "Example: /docquery What is the main topic of this document?"
        )
        return

    try:
        # Initialize Anthropic client
        client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        # Prepare the query with document context
        full_context = (
            f"Document: {session.document_context['filename']}\n\n"
            f"Document Text: {session.document_context['text']}\n\n"
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
        await update.message.reply_text(analysis)

    except Exception as e:
        logger.error(f"Document query error: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(
            "An error occurred while querying the document."
        )


def main():
    """Start the bot with advanced handlers."""
    try:
        logger.info("Starting bot...")
        # Validate Telegram token
        telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not telegram_token:
            logger.critical("TELEGRAM_BOT_TOKEN is not set!")
            raise ValueError("Telegram Bot Token is required")

        # Create the Application
        application = Application.builder().token(telegram_token).build()

        # Conversation handlers
        model_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('model', model_selection_command)],
            states={
                MODEL_SELECTION: [
                    CallbackQueryHandler(model_button_callback)
                ]
            },
            fallbacks=[CommandHandler('start', start_command)]
        )

        assistant_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('assistant', assistant_selection_command)],
            states={
                ASSISTANT_SELECTION: [
                    CallbackQueryHandler(assistant_button_callback)
                ]
            },
            fallbacks=[CommandHandler('start', start_command)]
        )

        # Register handlers
        application.add_handler(CommandHandler('start', start_command))
        application.add_handler(CommandHandler('new', new_session_command))
        application.add_handler(CommandHandler('usage', usage_command))
        application.add_handler(model_conv_handler)
        application.add_handler(assistant_conv_handler)
        
        # Advanced feature commands
        application.add_handler(CommandHandler('summarize', summarize_command))
        application.add_handler(CommandHandler('sentiment', analyze_sentiment_command))
        application.add_handler(CommandHandler('translate', translate_command))
        application.add_handler(CommandHandler('explain', code_explain_command))

        # Update UserSession to include document context
        application.add_handler(CommandHandler('uploaddoc', upload_document_command))
        application.add_handler(MessageHandler(filters.Document.PDF | filters.Document.DOCX, handle_document))
        application.add_handler(CommandHandler('docquery', document_query_command))

        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        )

        # add command hints
        commands = [
            BotCommand("start", "Display list of commands"),
            BotCommand("new", "Start new conversation"),
            BotCommand("model", "Change AI model"),
            BotCommand("assistant", "Change assistant mode"),
            BotCommand("usage", "Check token usage"),
            BotCommand("summarize", "Summarize conversation"),
            BotCommand("sentiment", "Analyze sentiment"),
            BotCommand("translate", "Translate text"),
            BotCommand("explain", "Explain code"),
            BotCommand("uploaddoc", "Upload docx or pdf command"),
            BotCommand("docquery", "Query the doc uploaded")
            ]
        application.bot.set_my_commands(commands)
        # Start the bot
        logger.info("Starting Enhanced Claude Telegram Bot...")
        application.run_polling(drop_pending_updates=True)

    except Exception as e:
        logger.critical(f"Fatal error starting bot: {e}")
        logger.critical(traceback.format_exc())

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logger.error(f"Startup error: {str(e)}")
        logger.error(traceback.format_exc())
