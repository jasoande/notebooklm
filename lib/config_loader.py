"""
Configuration Loader
Loads and validates YAML configuration
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml
except ImportError:
    logging.error("PyYAML not installed. Run: pip install pyyaml")
    raise


class ConfigLoader:
    """
    Loads and provides access to configuration
    """

    def __init__(self, config_path: Path):
        """
        Args:
            config_path: Path to config.yaml
        """
        self.config_path = config_path
        self.config: Dict[str, Any] = {}

        self.load()

    def load(self) -> None:
        """Load configuration from YAML file"""
        if not self.config_path.exists():
            logging.error(f"Config file not found: {self.config_path}")
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        try:
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)

            logging.info(f"Configuration loaded from {self.config_path}")

        except Exception as e:
            logging.error(f"Failed to load configuration: {e}")
            raise

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation

        Args:
            key_path: Dot-separated path (e.g., 'rate_limiting.requests_per_minute')
            default: Default value if not found

        Returns:
            Configuration value

        Example:
            config.get('rate_limiting.requests_per_minute', 20)
        """
        keys = key_path.split('.')
        value = self.config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def get_required(self, key_path: str) -> Any:
        """
        Get required configuration value

        Args:
            key_path: Dot-separated path

        Returns:
            Configuration value

        Raises:
            ValueError: If key not found
        """
        value = self.get(key_path)
        if value is None:
            raise ValueError(f"Required configuration missing: {key_path}")
        return value

    def get_section(self, section: str) -> Dict[str, Any]:
        """
        Get entire configuration section

        Args:
            section: Section name

        Returns:
            Section dict or empty dict
        """
        return self.config.get(section, {})

    def validate(self) -> bool:
        """
        Validate configuration has required fields

        Returns:
            True if valid

        Raises:
            ValueError: If validation fails
        """
        required_sections = [
            'rate_limiting',
            'delays',
            'retry',
            'logging'
        ]

        for section in required_sections:
            if section not in self.config:
                raise ValueError(f"Required configuration section missing: {section}")

        # Validate specific fields
        rate_limiting = self.config.get('rate_limiting', {})
        if not isinstance(rate_limiting.get('requests_per_minute'), (int, float)):
            raise ValueError("rate_limiting.requests_per_minute must be a number")

        logging.info("Configuration validation passed")
        return True
