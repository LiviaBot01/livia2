#!/usr/bin/env python3
"""
Server Configuration
--------------------
Configurações de segurança e variáveis globais do servidor Slack.
"""

import os
import logging
import asyncio
import math
from typing import Set

# OpenAI Traces Configuration for observability
if os.environ.get("OPENAI_ENABLE_TRACES", "false").lower() == "true":
    try:
        import openai
        # Enable OpenAI traces for better observability
        openai.log = "debug" if os.environ.get("OPENAI_LOG_LEVEL") == "debug" else "info"
        logging.info("✅ OpenAI Traces enabled for observability")
    except Exception as e:
        logging.warning(f"⚠️ Failed to enable OpenAI traces: {e}")

# Variáveis Globais
agent = None  # Agente OpenAI principal

# Semáforo de concorrência para múltiplos usuários
try:
    max_concurrency = int(os.environ.get("LIVIA_MAX_CONCURRENCY", "5"))
    if max_concurrency < 1:
        raise ValueError
except Exception:
    logging.warning("Invalid LIVIA_MAX_CONCURRENCY, falling back to 5")
    max_concurrency = 5

agent_semaphore = asyncio.Semaphore(max_concurrency)
processed_messages = set()  # Cache de mensagens processadas
bot_user_id = "U057233T98A"  # ID do bot no Slack - IMPORTANTE para detectar menções

# Sistema de cache de prompts para reduzir custos de API em consultas repetidas
prompt_cache = {}
PROMPT_CACHE_LIMIT = 100  # Maximum cached responses before cleanup

# Unified Agents SDK configuration - all MCPs now use native multi-turn execution
logging.info("Using unified Agents SDK with native multi-turn execution for all MCPs")

# Livia configuration - responds to @mentions in any channel and DMs
ALLOWED_CHANNELS = set()  # Empty means any channel is allowed when mentioned
DEVELOPMENT_MODE = False  # Production mode - allow all channels
ALLOWED_USERS = set()     # Empty means any user can interact

# Security flags
SHOW_DEBUG_LOGS = True    # Show detailed security logs
SHOW_SECURITY_BLOCKS = True  # Show when messages are blocked
ALLOWED_DM_CHANNELS = set()  # Empty means DMs are allowed

# Enhanced logging configuration
LOGGING_LEVEL = os.environ.get("LIVIA_LOG_LEVEL", "WARNING").upper()  # Reduced default level
logging.basicConfig(
    level=getattr(logging, LOGGING_LEVEL, logging.WARNING),
    format='%(asctime)s - %(message)s'  # Simplified format
)

# Suppress noisy loggers
logging.getLogger('slack_bolt').setLevel(logging.ERROR)
logging.getLogger('slack_sdk').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)
logging.getLogger('httpx').setLevel(logging.ERROR)
logging.getLogger('openai').setLevel(logging.ERROR)
logging.getLogger('agents').setLevel(logging.ERROR)

# 🔇 LOG LIMPO: Exibe apenas interações essenciais
SHOW_SECURITY_BLOCKS = True        # Set to True to see all security blocks in terminal
SHOW_DEBUG_LOGS = True             # Set to True to see debug logs
SHOW_AGENT_LOGS = False             # Set to True to see detailed agent logs


async def is_channel_allowed(channel_id: str, user_id: str, app_client) -> bool:
    """
    Verifica se um canal/usuário tem permissão para usar o bot.
    Permite DMs e menções em qualquer canal.
    
    Args:
        channel_id: ID do canal do Slack
        user_id: ID do usuário do Slack
        app_client: Cliente do Slack para verificar informações do canal
    
    Returns:
        bool: True se permitido, False caso contrário
    """
    logging.info(f"🔍 SECURITY CHECK: channel={channel_id}, user={user_id}")
    
    try:
        # Verificar se é DM
        channel_info = await app_client.conversations_info(channel=channel_id)
        if channel_info["ok"] and channel_info["channel"]["is_im"]:
            logging.info(f"✅ DM channel {channel_id} allowed")
            ALLOWED_DM_CHANNELS.add(channel_id)  # Cache DM channel ID
            return True
        
        # Se não é DM, é um canal público/privado - permitido quando mencionado
        logging.info(f"✅ Channel {channel_id} allowed (requires @mention)")
        return True
        
    except Exception as e:
        logging.error(f"❌ Error checking channel info: {e}")
        return False


def get_global_agent():
    """Get the global agent instance."""
    return agent


def set_global_agent(new_agent):
    """Set the global agent instance."""
    global agent
    agent = new_agent


def get_agent_semaphore():
    """Get the agent semaphore for concurrency control."""
    return agent_semaphore


def get_processed_messages():
    """Get the processed messages cache."""
    return processed_messages


def get_bot_user_id():
    """Get the bot user ID."""
    return bot_user_id


def get_prompt_cache():
    """Get the prompt cache dictionary."""
    return prompt_cache


def get_security_config():
    """Get security configuration."""
    return {
        "allowed_channels": ALLOWED_CHANNELS,
        "development_mode": DEVELOPMENT_MODE,
        "allowed_users": ALLOWED_USERS,
        "allowed_dm_channels": ALLOWED_DM_CHANNELS,
        "show_security_blocks": SHOW_SECURITY_BLOCKS,
        "show_debug_logs": SHOW_DEBUG_LOGS,
        "show_agent_logs": SHOW_AGENT_LOGS
    }
