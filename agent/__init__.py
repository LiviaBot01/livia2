#!/usr/bin/env python3
"""
Livia Agent Module
------------------
Módulo principal do agente Livia refatorado em componentes menores.
"""

# Import main functions from submodules
from .config import (
    count_tokens,
    MCP_AVAILABLE,
    ZAPIER_MCPS,
    get_agent_instructions,
    generate_enhanced_zapier_tools_description
)

from .creator import (
    create_agent_with_mcp_servers,
    create_agent
)

from .processor import (
    process_message,
    extract_tool_calls_from_response
)

from .mcp_processor import (
    detect_zapier_mcp_needed,
    get_available_zapier_mcps,
    process_message_with_structured_output,
    process_message_with_enhanced_multiturn_mcp
)

from .mcp_streaming import (
    process_message_with_zapier_mcp_streaming
)

# Export all main functions for backward compatibility
__all__ = [
    # Configuration
    'count_tokens',
    'MCP_AVAILABLE', 
    'ZAPIER_MCPS',
    'get_agent_instructions',
    'generate_enhanced_zapier_tools_description',
    
    # Agent creation
    'create_agent_with_mcp_servers',
    'create_agent',
    
    # Message processing
    'process_message',
    'extract_tool_calls_from_response',
    
    # MCP processing
    'detect_zapier_mcp_needed',
    'get_available_zapier_mcps',
    'process_message_with_structured_output',
    'process_message_with_enhanced_multiturn_mcp',
    'process_message_with_zapier_mcp_streaming'
]
