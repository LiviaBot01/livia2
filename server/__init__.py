#!/usr/bin/env python3
"""
Server Module
-------------
Módulo do servidor Slack refatorado em componentes menores.
"""

# Import main classes and functions from submodules
from .config import (
    is_channel_allowed,
    get_global_agent,
    set_global_agent,
    get_agent_semaphore,
    get_processed_messages,
    get_bot_user_id,
    get_prompt_cache,
    get_security_config
)

from .utils import (
    count_tokens,
    get_user_friendly_error_message,
    should_retry_error,
    log_startup,
    log_message_received,
    log_bot_response,
    log_error,
    get_thread_token_usage,
    get_model_context_limits
)

from .context_manager import ContextManager

from .streaming_processor import StreamingProcessor

from .event_handlers import EventHandlers

from .message_processor import MessageProcessor

from .slack_server import (
    SlackSocketModeServer,
    initialize_agent,
    cleanup_agent,
    async_main,
    main
)

# Export all main functions for backward compatibility
__all__ = [
    # Configuration
    'is_channel_allowed',
    'get_global_agent',
    'set_global_agent',
    'get_agent_semaphore',
    'get_processed_messages',
    'get_bot_user_id',
    'get_prompt_cache',
    'get_security_config',
    
    # Utilities
    'count_tokens',
    'get_user_friendly_error_message',
    'should_retry_error',
    'log_startup',
    'log_message_received',
    'log_bot_response',
    'log_error',
    'get_thread_token_usage',
    'get_model_context_limits',
    
    # Core classes
    'ContextManager',
    'StreamingProcessor',
    'EventHandlers',
    'MessageProcessor',
    'SlackSocketModeServer',
    
    # Main functions
    'initialize_agent',
    'cleanup_agent',
    'async_main',
    'main'
]
