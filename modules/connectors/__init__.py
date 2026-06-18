"""
Módulo de Conectores da Atena
Permite integração com serviços externos como WhatsApp, Discord, Telegram, etc.
"""

from .base_connector import BaseConnector, ConnectorConfig, Message
from .whatsapp_connector import WhatsAppConnector
from .discord_connector import DiscordConnector
from .telegram_connector import TelegramConnector
from .connector_manager import ConnectorManager

__all__ = [
    'BaseConnector',
    'ConnectorConfig',
    'Message',
    'WhatsAppConnector',
    'DiscordConnector',
    'TelegramConnector',
    'ConnectorManager',
]
