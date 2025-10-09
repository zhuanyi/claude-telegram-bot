"""
Utility functions for the Claude Telegram Bot.

This module contains various utility functions for text processing,
document handling, logging setup, and other common operations.
"""

import os
import sys
import logging
import tempfile
import traceback
import asyncio
import re
from typing import Optional, List, Callable, Any
from functools import wraps
from logging.handlers import RotatingFileHandler

import PyPDF2
import docx
from telegram.error import RetryAfter, TimedOut, NetworkError

from .config import BotConfig, SUPPORTED_DOCUMENT_EXTENSIONS


def setup_logging(config: BotConfig) -> logging.Logger:
    """
    Set up logging configuration for the bot.
    
    Args:
        config: Bot configuration containing logging settings
        
    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Error handler to stderr
    error_handler = logging.StreamHandler(sys.stderr)
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)
    
    # File handler (if enabled)
    if config.enable_file_logging:
        try:
            os.makedirs(config.log_directory, exist_ok=True)
            log_file_path = os.path.join(config.log_directory, 'bot.log')
            
            file_handler = RotatingFileHandler(
                log_file_path,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            
            logger.info(f"File logging enabled: {log_file_path}")
        except Exception as e:
            logger.error(f"Failed to set up file logging: {e}")
    
    return logger


def strip_outer_code_block(text: str) -> str:
    """
    Remove a surrounding triple backtick block if it encloses the entire text.
    
    This utility helps clean up responses that might be unnecessarily wrapped
    in code blocks, providing a cleaner user experience.
    
    Args:
        text: The text to process
        
    Returns:
        Text with outer code block removed if applicable
    """
    stripped = text.strip()
    if stripped.startswith('```') and stripped.endswith('```') and stripped.count('```') == 2:
        # Drop first and last line containing the backticks
        body = stripped.split('\n')
        if len(body) > 2:
            return '\n'.join(body[1:-1])
    return text


def validate_document_type(filename: str) -> bool:
    """
    Validate if a document type is supported.
    
    Args:
        filename: The filename to validate
        
    Returns:
        True if the document type is supported, False otherwise
    """
    return filename.lower().endswith(SUPPORTED_DOCUMENT_EXTENSIONS)


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text from a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Extracted text content
        
    Raises:
        Exception: If text extraction fails
    """
    text_pages = []
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_pages.append(page_text)
        
        extracted_text = "\n".join(text_pages)
        if not extracted_text.strip():
            raise Exception("No text content found in PDF")
        
        return extracted_text
        
    except Exception as e:
        logging.error(f"PDF text extraction error: {e}")
        raise Exception(f"Could not extract text from PDF: {str(e)}")


def extract_text_from_docx(docx_path: str) -> str:
    """
    Extract text from a Word document.
    
    Args:
        docx_path: Path to the DOCX file
        
    Returns:
        Extracted text content
        
    Raises:
        Exception: If text extraction fails
    """
    try:
        doc = docx.Document(docx_path)
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        
        extracted_text = "\n".join(paragraphs)
        if not extracted_text.strip():
            raise Exception("No text content found in document")
        
        return extracted_text
        
    except Exception as e:
        logging.error(f"DOCX text extraction error: {e}")
        raise Exception(f"Could not extract text from Word document: {str(e)}")


def extract_document_text(file_path: str, filename: str) -> str:
    """
    Extract text from a document file based on its type.
    
    Args:
        file_path: Path to the document file
        filename: Original filename (used to determine file type)
        
    Returns:
        Extracted text content
        
    Raises:
        ValueError: If document type is not supported
        Exception: If text extraction fails
    """
    if not validate_document_type(filename):
        raise ValueError(f"Unsupported document type: {filename}")
    
    if filename.lower().endswith('.pdf'):
        return extract_text_from_pdf(file_path)
    elif filename.lower().endswith('.docx'):
        return extract_text_from_docx(file_path)
    else:
        raise ValueError(f"Unsupported document type: {filename}")


def create_temp_file(suffix: str) -> str:
    """
    Create a temporary file and return its path.
    
    Args:
        suffix: File suffix (e.g., '.pdf', '.docx')
        
    Returns:
        Path to the created temporary file
    """
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_file.close()
    return temp_file.name


def cleanup_temp_file(file_path: str) -> None:
    """
    Clean up a temporary file.
    
    Args:
        file_path: Path to the temporary file to clean up
    """
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
    except Exception as e:
        logging.warning(f"Failed to cleanup temporary file {file_path}: {e}")


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate text to a maximum length with optional suffix.
    
    Args:
        text: Text to truncate
        max_length: Maximum length allowed
        suffix: Suffix to add if text is truncated
        
    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def chunk_text(text: str, chunk_size: int, overlap: int = 0) -> List[str]:
    """
    Split text into chunks of specified size with optional overlap.
    
    Args:
        text: Text to chunk
        chunk_size: Size of each chunk
        overlap: Number of characters to overlap between chunks
        
    Returns:
        List of text chunks
    """
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start = end - overlap
        
        if start >= len(text):
            break
    
    return chunks


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename by removing or replacing problematic characters.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove or replace problematic characters
    import re
    
    # Replace problematic characters with underscores
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Remove multiple consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    
    # Remove leading/trailing underscores and dots
    sanitized = sanitized.strip('_.')
    
    # Ensure filename is not empty
    if not sanitized:
        sanitized = "unnamed_file"
    
    return sanitized


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted size string
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def safe_format_exception(e: Exception) -> str:
    """
    Safely format an exception for user display.
    
    Args:
        e: Exception to format
        
    Returns:
        User-friendly error message
    """
    error_msg = str(e)
    if not error_msg:
        error_msg = type(e).__name__
    
    # Avoid exposing sensitive information
    if "api" in error_msg.lower() or "key" in error_msg.lower():
        return "API communication error"
    
    return error_msg


def log_error_with_context(logger: logging.Logger, message: str, exception: Exception) -> None:
    """
    Log an error with full context and traceback.
    
    Args:
        logger: Logger instance
        message: Error message
        exception: Exception that occurred
    """
    logger.error(f"{message}: {exception}")
    logger.error(f"Exception type: {type(exception).__name__}")
    logger.error(f"Traceback:\n{traceback.format_exc()}")


def telegram_retry(max_retries: int = 3, base_delay: float = 1.0):
    """
    Decorator for automatic retry on Telegram API errors with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds for exponential backoff
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except RetryAfter as e:
                    if attempt < max_retries:
                        # Telegram tells us exactly how long to wait
                        wait_time = float(e.retry_after)
                        logging.warning(f"Flood control exceeded. Retrying in {wait_time} seconds (attempt {attempt + 1}/{max_retries + 1})")
                        await asyncio.sleep(wait_time)
                        last_exception = e
                        continue
                    else:
                        logging.error(f"Max retries exceeded for flood control: {e}")
                        raise e
                except (TimedOut, NetworkError) as e:
                    if attempt < max_retries:
                        # Use exponential backoff for network errors
                        wait_time = base_delay * (2 ** attempt)
                        logging.warning(f"Network error, retrying in {wait_time} seconds (attempt {attempt + 1}/{max_retries + 1}): {e}")
                        await asyncio.sleep(wait_time)
                        last_exception = e
                        continue
                    else:
                        logging.error(f"Max retries exceeded for network error: {e}")
                        raise e
                except Exception as e:
                    # Don't retry for other types of exceptions
                    raise e
            
            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


class RateLimiter:
    """
    Simple rate limiter for API calls or user actions.
    
    This class provides basic rate limiting functionality to prevent
    abuse or excessive API usage.
    """
    
    def __init__(self, max_requests: int, time_window: int):
        """
        Initialize the rate limiter.
        
        Args:
            max_requests: Maximum number of requests allowed
            time_window: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = {}
    
    def is_allowed(self, key: str) -> bool:
        """
        Check if a request is allowed for the given key.
        
        Args:
            key: Identifier for the request (e.g., user ID)
            
        Returns:
            True if request is allowed, False otherwise
        """
        import time
        
        current_time = time.time()
        
        # Clean up old requests
        if key in self.requests:
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if current_time - req_time < self.time_window
            ]
        else:
            self.requests[key] = []
        
        # Check if limit is exceeded
        if len(self.requests[key]) >= self.max_requests:
            return False
        
        # Add current request
        self.requests[key].append(current_time)
        return True
    
    def get_remaining_requests(self, key: str) -> int:
        """
        Get the number of remaining requests for a key.
        
        Args:
            key: Identifier for the request
            
        Returns:
            Number of remaining requests
        """
        import time
        
        current_time = time.time()
        
        if key in self.requests:
            active_requests = [
                req_time for req_time in self.requests[key]
                if current_time - req_time < self.time_window
            ]
            return max(0, self.max_requests - len(active_requests))
        
        return self.max_requests