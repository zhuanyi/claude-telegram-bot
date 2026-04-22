"""
Model management module for the Claude Telegram Bot.

This module handles dynamic model discovery, caching, and display name generation
for Anthropic's Claude API models.
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any

import anthropic

from .config import BotConfig, CURRENT_MODEL_PATTERNS


logger = logging.getLogger(__name__)


class ModelManager:
    """
    Manages Claude AI models with dynamic discovery and caching.
    
    This class provides:
    - Automatic model discovery from Anthropic API
    - Intelligent caching with configurable duration
    - Dynamic display name generation
    - Prioritization of 'latest' versions over dated models
    """
    
    def __init__(self, config: BotConfig):
        """
        Initialize the model manager.
        
        Args:
            config: Bot configuration containing API key and cache settings
        """
        self.api_key = config.anthropic_api_key
        self.cache_duration = timedelta(hours=config.model_cache_duration_hours)
        self.models_cache: Dict[str, str] = {}
        self.cache_timestamp: Optional[datetime] = None
        
    def is_cache_valid(self) -> bool:
        """Check if the model cache is still valid."""
        if not self.cache_timestamp:
            return False
        return datetime.now() - self.cache_timestamp < self.cache_duration
    
    def fetch_available_models(self) -> Dict[str, str]:
        """
        Retrieve list of Claude models via the API with caching.

        Returns:
            Dict mapping display names to model IDs
        """
        if self.is_cache_valid() and self.models_cache:
            logger.info("Using cached model list")
            return self.models_cache

        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            models = client.models.list()

            # Log all models from API for debugging
            all_model_ids = [model.id for model in models]
            logger.info(f"Raw models from API: {all_model_ids}")

            # Filter only current generation Claude models
            raw_models = {}
            for model in models:
                model_id = model.id
                if self._is_current_model(model_id):
                    raw_models[model_id] = model_id
                else:
                    logger.debug(f"Filtered out model: {model_id}")

            logger.info(f"Models after filtering: {list(raw_models.keys())}")

            # Process models to prioritize 'latest' versions and create display names
            claude_models = self._process_and_prioritize_models(raw_models)

            # Update cache
            self.models_cache = claude_models
            self.cache_timestamp = datetime.now()

            logger.info(f"Fetched {len(claude_models)} Claude models from API")
            return claude_models

        except Exception as e:
            logger.error(f"Failed to fetch models from API: {e}")
            return self._get_fallback_models()
    
    def clear_cache(self) -> None:
        """Clear the model cache to force refresh on next fetch."""
        self.models_cache = {}
        self.cache_timestamp = None
        logger.info("Model cache cleared")
    
    def get_model_display_name(self, model_id: str) -> str:
        """
        Get the display name for a specific model ID.
        
        Args:
            model_id: The model ID to get display name for
            
        Returns:
            User-friendly display name for the model
        """
        models = self.fetch_available_models()
        for display_name, cached_id in models.items():
            if cached_id == model_id:
                return display_name
        return self._create_dynamic_display_name(model_id)
    
    def _is_current_model(self, model_id: str) -> bool:
        """Check if a model ID represents a current generation Claude model."""
        return any(pattern in model_id for pattern in CURRENT_MODEL_PATTERNS)
    
    def _get_fallback_models(self) -> Dict[str, str]:
        """Return a fallback set of models when API fails."""
        fallback_models = {
            'Haiku 3.5 (Latest)': 'claude-3-5-haiku-latest',
            'Sonnet 3.7 (Latest)': 'claude-3-7-sonnet-latest',
            'Sonnet 4': 'claude-sonnet-4-20250514',
            'Opus 4': 'claude-opus-4-20250514'
        }
        logger.info("Using fallback model list")
        return fallback_models
    
    def _process_and_prioritize_models(self, raw_models: Dict[str, str]) -> Dict[str, str]:
        """
        Process models to prioritize 'latest' versions and create display names.
        
        Args:
            raw_models: Dictionary of raw model IDs
            
        Returns:
            Dictionary mapping display names to model IDs
        """
        # Group models by base type (haiku, sonnet, opus)
        model_groups = {}
        
        for model_id in raw_models.keys():
            base_type = self._extract_base_type(model_id)
            if base_type not in model_groups:
                model_groups[base_type] = []
            model_groups[base_type].append(model_id)
        
        # Prioritize 'latest' versions and create final mapping
        final_models = {}
        
        for base_type, models in model_groups.items():
            # Sort to prioritize 'latest' versions first
            sorted_models = sorted(models, key=lambda x: (
                'latest' not in x,  # 'latest' models first
                x  # Then alphabetically
            ))
            
            # For each base type, prefer 'latest' version if available
            latest_model = None
            dated_models = []
            
            for model in sorted_models:
                if 'latest' in model:
                    latest_model = model
                else:
                    dated_models.append(model)
            
            # Add the latest model if available
            if latest_model:
                display_name = self._create_dynamic_display_name(latest_model)
                final_models[display_name] = latest_model
            
            # Add dated models only if no latest version exists, or add a few recent ones
            if not latest_model:
                for model in dated_models[:2]:  # Limit to 2 most recent dated versions
                    display_name = self._create_dynamic_display_name(model)
                    final_models[display_name] = model
        
        return final_models
    
    def _extract_base_type(self, model_id: str) -> str:
        """
        Extract base model type from model ID.

        Args:
            model_id: The model ID to extract base type from

        Returns:
            Base model type (e.g., 'haiku-4', 'sonnet-4-5', 'opus-4')
        """
        # Remove 'claude-' prefix and extract base type
        clean_id = model_id.replace('claude-', '')

        # Handle different naming patterns
        if 'haiku' in clean_id:
            if '4' in clean_id or 'haiku-4' in clean_id:
                return 'haiku-4'
            else:
                return 'haiku'
        elif 'sonnet' in clean_id:
            if '4-5' in clean_id or 'sonnet-4-5' in clean_id:
                return 'sonnet-4-5'
            elif '3-5' in clean_id:
                return 'sonnet-3-5'
            elif '3-7' in clean_id:
                return 'sonnet-3-7'
            elif '4' in clean_id or 'sonnet-4' in clean_id:
                return 'sonnet-4'
            else:
                return 'sonnet'
        elif 'opus' in clean_id:
            if '4' in clean_id or 'opus-4' in clean_id:
                return 'opus-4'
            else:
                return 'opus'
        else:
            return 'unknown'
    
    def _create_dynamic_display_name(self, model_id: str) -> str:
        """
        Create a user-friendly display name from model ID dynamically.

        Args:
            model_id: The model ID to create display name for

        Returns:
            User-friendly display name
        """
        # Remove 'claude-' prefix
        clean_id = model_id.replace('claude-', '')

        # Handle different patterns
        if 'latest' in clean_id:
            # For 'latest' versions
            if '3-5-haiku' in clean_id:
                return 'Haiku 3.5 (Latest)'
            elif '3-5-sonnet' in clean_id:
                return 'Sonnet 3.5 (Latest)'
            elif '3-7-sonnet' in clean_id:
                return 'Sonnet 3.7 (Latest)'
            elif 'sonnet-4-5' in clean_id or '4-5-sonnet' in clean_id:
                return 'Sonnet 4.5 (Latest)'
            elif 'sonnet-4' in clean_id:
                return 'Sonnet 4 (Latest)'
            elif 'haiku-4' in clean_id or '4-haiku' in clean_id:
                return 'Haiku 4 (Latest)'
            elif 'opus-4' in clean_id:
                return 'Opus 4 (Latest)'

        # Handle dated versions
        if 'haiku' in clean_id:
            version = self._extract_version(clean_id)
            date_str = self._format_date_from_id(clean_id)
            return f'Haiku {version} ({date_str})'
        elif 'sonnet' in clean_id:
            if 'sonnet-4-5' in clean_id or '4-5-sonnet' in clean_id:
                date_str = self._format_date_from_id(clean_id)
                return f'Sonnet 4.5 ({date_str})'
            elif 'sonnet-4' in clean_id:
                date_str = self._format_date_from_id(clean_id)
                return f'Sonnet 4 ({date_str})'
            else:
                version = self._extract_version(clean_id)
                date_str = self._format_date_from_id(clean_id)
                return f'Sonnet {version} ({date_str})'
        elif 'opus' in clean_id:
            if 'opus-4' in clean_id:
                date_str = self._format_date_from_id(clean_id)
                return f'Opus 4 ({date_str})'
            else:
                version = self._extract_version(clean_id)
                date_str = self._format_date_from_id(clean_id)
                return f'Opus {version} ({date_str})'

        # Fallback: capitalize and replace hyphens
        return clean_id.replace('-', ' ').title()
    
    def _extract_version(self, clean_id: str) -> str:
        """Extract version number from model ID."""
        if '4-5' in clean_id:
            return '4.5'
        elif '3-5' in clean_id:
            return '3.5'
        elif '3-7' in clean_id:
            return '3.7'
        elif '4' in clean_id:
            return '4'
        else:
            return '3'
    
    def _format_date_from_id(self, model_id: str) -> str:
        """
        Format date from model ID (e.g., 20250514 -> May 2025).
        
        Args:
            model_id: Model ID containing date information
            
        Returns:
            Formatted date string
        """
        # Look for date pattern YYYYMMDD
        date_match = re.search(r'(\d{8})', model_id)
        if date_match:
            date_str = date_match.group(1)
            year = date_str[:4]
            month = date_str[4:6]
            
            # Convert month number to name
            month_names = {
                '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr',
                '05': 'May', '06': 'Jun', '07': 'Jul', '08': 'Aug',
                '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec'
            }
            
            month_name = month_names.get(month, month)
            return f'{month_name} {year}'
        
        # Look for date pattern YYYYMM
        date_match = re.search(r'(\d{6})', model_id)
        if date_match:
            date_str = date_match.group(1)
            year = date_str[:4]
            month = date_str[4:6]
            
            month_names = {
                '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr',
                '05': 'May', '06': 'Jun', '07': 'Jul', '08': 'Aug',
                '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec'
            }
            
            month_name = month_names.get(month, month)
            return f'{month_name} {year}'
        
        return 'Current'