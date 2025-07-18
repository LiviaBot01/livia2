#!/usr/bin/env python3
"""
Livia MCP Processa as Mensagens
---------------------------
Processamento de mensagens usando MCPs do Zapier via OpenAI Responses API.
Inclui structured outputs, multi-turn execution e streaming.
"""

import logging
import re
from typing import Optional, List
from openai import OpenAI

from .config import ZAPIER_MCPS, count_tokens

logger = logging.getLogger(__name__)


async def process_message_with_structured_output(mcp_key: str, message: str, image_urls: Optional[List[str]] = None, stream_callback=None) -> dict:
    """
    Process message using OpenAI Responses API with Structured Outputs for reliable JSON schema adherence.
    Always uses streaming internally.

    Args:
        mcp_key: Key for the Zapier MCP to use
        message: User message to process
        image_urls: Optional list of image URLs
        stream_callback: Optional callback for streaming updates

    Returns:
        Dict: {"text": ..., "structured_data": {...}, "tools": [...]}
    """
    if mcp_key not in ZAPIER_MCPS:
        raise ValueError(f"Unknown MCP key: {mcp_key}. Available: {list(ZAPIER_MCPS.keys())}")

    mcp_config = ZAPIER_MCPS[mcp_key]
    client = OpenAI()

    # Get appropriate schema for this MCP operation
    schema_type = {
        "mcpEverhour": "everhour",
        "mcpAsana": "asana",
        "mcpGmail": "gmail",
        "mcpGoogleDocs": "file_search",
        "mcpGoogleSheets": "file_search",
        "mcpGoogleCalendar": "gmail",  # Similar structure
        "mcpSlack": "gmail"  # Similar structure
    }.get(mcp_key, "unified")

    # Prepare input data with optional images
    if image_urls:
        input_content = [{"type": "input_text", "text": message}]
        for image_url in image_urls:
            input_content.append({
                "type": "input_image",
                "image_url": image_url,
                "detail": "low"
            })
        input_data = input_content
    else:
        input_data = message

    logger.info(f"Processing message with {mcp_config['name']} using Structured Outputs")
    logger.info(f"Schema type: {schema_type}")
    logger.info("Always using streaming internally")
    
    # Create dummy callback if none provided
    if not stream_callback:
        async def dummy_callback(delta_text: str, full_text: str):
            pass
        stream_callback = dummy_callback

    try:
        # Create the API call (structured outputs temporarily disabled due to API compatibility)
        api_params = {
            "model": "gpt-4o-2024-08-06",  # Required for Structured Outputs
            "input": input_data,
            "instructions": f"You are Livia, an intelligent AI assistant with {mcp_config['name']} access. Provide structured responses following the schema.",
            "tools": [
                {
                    "type": "mcp",
                    "server_label": mcp_config["server_label"],
                    "server_url": mcp_config["url"],
                    "require_approval": "never",
                    "headers": {
                        "Authorization": f"Bearer {mcp_config['api_key'].strip()}"
                    }
                }
            ]
            # Note: text_format parameter removed as it's not supported in Responses API
        }

        # Always use streaming
        api_params["stream"] = True

        response = client.responses.create(**api_params)

        # Handle streaming response
        full_response = ""
        structured_data = None

        for event in response:
            if hasattr(event, 'type'):
                if event.type == "response.output_text.delta":
                    delta_text = getattr(event, 'delta', '')
                    if delta_text:
                        full_response += delta_text
                        # Call stream callback
                        await stream_callback(delta_text, full_response)
                elif event.type == "response.completed":
                    # Structured output streaming completed
                    logger.info("Structured output streaming completed")
                    # Extract structured data if available
                    if hasattr(event, 'output_parsed'):
                        structured_data = event.output_parsed.model_dump() if hasattr(event.output_parsed, 'model_dump') else event.output_parsed

        return {
            "text": full_response or "No response generated.",
            "structured_data": structured_data,
            "tools": []
        }

    except Exception as e:
        logger.error(f"Error with structured output for {mcp_config['name']}: {e}")
        # Fallback to regular processing
        logger.info("Falling back to regular MCP processing")
        return await process_message_with_zapier_mcp_streaming(mcp_key, message, image_urls, None)


def detect_zapier_mcp_needed(message: str) -> Optional[str]:
    """
    Detect which Zapier MCP is needed based on message keywords.
    Detecta qual MCP do Zapier é necessário com base nas palavras-chave da mensagem.

    Args:
        message: Mensagem do usuário para análise

    Returns:
        Chave do MCP se detectada, None caso contrário
    """
    message_lower = message.lower()

    # Ordem de prioridade: Serviços mais específicos primeiro para evitar conflitos
    priority_order = ["mcpEverhour", "mcpAsana", "mcpGmail", "mcpGoogleDocs", "mcpGoogleSheets", "mcpGoogleCalendar", "mcpSlack", "google_drive"]

    detected_mcps = []
    for mcp_key in priority_order:
        if mcp_key in ZAPIER_MCPS:
            mcp_config = ZAPIER_MCPS[mcp_key]
            detected_keywords = [kw for kw in mcp_config['keywords'] if kw in message_lower]
            if detected_keywords:
                detected_mcps.append(f"{mcp_key}: {detected_keywords}")
                print(f"Detected {mcp_config['name']} keywords: {detected_keywords}")  # Mantido essencial
                logger.info(f"Detected {mcp_config['name']} keywords in message: {detected_keywords}")
                logger.info(f"Routing to MCP: {mcp_key}")
                return mcp_key


    if detected_mcps:
        print(f"MCP Detections: {'; '.join(detected_mcps)}")  # Linha consolidada
    else:
        print("No MCP detected for this message")  # Mantido essencial
    return None


async def process_message_with_enhanced_multiturn_mcp(mcp_key: str, message: str, image_urls: Optional[List[str]] = None, stream_callback=None) -> dict:
    """
    Enhanced multi-turn execution for Zapier MCPs using Responses API.
    Implements manual multi-turn loops for complex workflows like Everhour time tracking.

    Args:
        mcp_key: Key for the Zapier MCP to use
        message: User message to process
        image_urls: Optional list of image URLs
        stream_callback: Optional callback for streaming updates

    Returns:
        Dict: {"text": ..., "tools": [...]}
    """
    if mcp_key not in ZAPIER_MCPS:
        raise ValueError(f"Unknown MCP key: {mcp_key}. Available: {list(ZAPIER_MCPS.keys())}")

    mcp_config = ZAPIER_MCPS[mcp_key]
    client = OpenAI()

    # Prepare input data with optional images
    if image_urls:
        input_content = [{"type": "input_text", "text": message}]
        for image_url in image_urls:
            input_content.append({
                "type": "input_image",
                "image_url": image_url,
                "detail": "low"
            })
        input_data = input_content
    else:
        input_data = message

    logger.info(f"Enhanced Multi-Turn Processing with {mcp_config['name']}")
    logger.info(f"Original message: {message}")

    # ⚠️ Enhanced instructions for multi-turn execution with Everhour-specific strategies
    enhanced_instructions = f"""You are Livia, an intelligent AI assistant with {mcp_config['name']} access.

MULTI-TURN EXECUTION STRATEGY:
1. ANALYZE the user request to identify all required steps
2. EXECUTE each step sequentially using available tools
3. CONTINUE until the complete workflow is finished
4. RESPOND only when the entire task is completed

FOR EVERHOUR WORKFLOWS - ENHANCED STRATEGY:

AVAILABLE EVERHOUR COMMANDS:
SEARCH & FIND: everhour_find_internal_project, everhour_find_project, everhour_find_section, everhour_find_member, everhour_find_task
CREATE & MANAGE: everhour_create_client, everhour_create_project, everhour_create_section, everhour_create_task
TIME TRACKING: everhour_start_timer, everhour_stop_timer, everhour_add_time

WORKFLOW STEPS:
- Step 1: Use everhour_find_project to find the project
- Step 2: Try everhour_find_task to find the specific task
- Step 3: IF TASK NOT FOUND: Try everhour_list_tasks for the project to see available tasks
- Step 4: IF STILL NOT FOUND: Try everhour_add_time directly with project ID as taskId (fallback)
- Step 5: Confirm success with details

EVERHOUR TASK SEARCH FALLBACK:
If everhour_find_task returns empty results ({{}}), try these alternatives:
1. Use everhour_list_tasks with the project ID to see all available tasks
2. Look for similar task names in the list
3. Use the most appropriate task ID found in the search results
4. If no specific task is found, use the project ID as taskId for general time tracking

DATE HANDLING (Timezone: America/Sao_Paulo):
- 'hoje'/'today' = current date in Brazil timezone
- 'ontem'/'yesterday' = previous day
- 'esta semana'/'this week' = current week range
- Always convert relative dates to YYYY-MM-DD format
- Be precise with dates as this affects timesheet accuracy
- Never hardcode specific dates - always use relative date references
- Let the system determine actual dates at runtime based on current context

FOR OTHER WORKFLOWS:
- Break down complex requests into sequential tool calls
- Use results from previous calls to inform next steps
- Don't stop until the complete workflow is finished

CRITICAL RULES:
1. You MUST use everhour tools - never respond without calling tools
2. Do NOT respond to user until ALL required steps are completed
3. Continue calling tools until the entire workflow is finished
4. If you know the task ID directly, use everhour_add_time immediately

REQUIRED ACTIONS FOR TIME TRACKING (Timezone: America/Sao_Paulo):
- ALWAYS call everhour_add_time tool with appropriate parameters:
  - taskId: (use the task ID found through search or project ID as fallback)
  - time: (user-specified time or default duration)
  - date: "today"  # use dynamic date reference in Brazil timezone
  - comment: "Time added via Livia"
- DATE CONVERSION EXAMPLES:
  - "hoje" → current date in YYYY-MM-DD format (Brazil timezone)
  - "ontem" → yesterday's date in YYYY-MM-DD format
  - "segunda-feira" → date of this/next Monday
  - Always convert relative dates to precise YYYY-MM-DD format

RESPONSE FORMAT:
SUCCESS: 'Tempo adicionado com sucesso! [time] na task [task_name] ([task_id])'
ERROR: 'Erro: [specific error details]'

GOAL: Complete the entire multi-step workflow before responding to user.
"""

    try:
        # Create enhanced multi-turn API call with FORCED tool usage
        stream = client.responses.create(
            model="gpt-4o",
            input=input_data,
            instructions=enhanced_instructions,
            tools=[
                {
                    "type": "mcp",
                    "server_label": mcp_config["server_label"],
                    "server_url": mcp_config["url"],
                    "require_approval": "never",
                    "headers": {
                        "Authorization": f"Bearer {mcp_config['api_key'].strip()}"
                    }
                }
            ],
            tool_choice="required",  # FORCE tool usage - don't allow text-only responses
            stream=True
        )

        # Process streaming response with enhanced logging
        full_response = ""
        tool_calls_made = []
        errors_encountered = []

        for event in stream:
            if hasattr(event, 'type'):
                if event.type == "response.output_text.delta":
                    delta_text = getattr(event, 'delta', '')
                    if delta_text:
                        full_response += delta_text
                        # Call stream callback if provided
                        if stream_callback:
                            await stream_callback(delta_text, full_response)
                elif event.type == "response.completed":
                    logger.info("Enhanced Multi-Turn MCP streaming response completed")
                elif event.type == "error":
                    error_details = {
                        "type": getattr(event, 'type', 'unknown'),
                        "message": getattr(event, 'message', str(event)),
                        "code": getattr(event, 'code', None),
                        "details": getattr(event, 'details', None)
                    }
                    errors_encountered.append(error_details)
                    logger.error(f"Enhanced Multi-Turn MCP ERROR: {error_details}")
                elif hasattr(event, 'type') and 'tool_call' in event.type:
                    tool_call_info = {
                        "type": event.type,
                        "tool_name": getattr(event, 'name', getattr(event, 'tool_name', mcp_key)),  # Usar mcp_key em vez de 'mcp_unknown'
                        "arguments": getattr(event, 'arguments', {}),
                        "output": getattr(event, 'output', None),
                        "error": getattr(event, 'error', None)
                    }
                    tool_calls_made.append(tool_call_info)
                    logger.info(f"Enhanced Multi-Turn TOOL CALL: {tool_call_info}")

        logger.info(f"Enhanced Multi-Turn SUMMARY:")
        logger.info(f"   - Response length: {len(full_response)} chars")
        logger.info(f"   - Tool calls made: {len(tool_calls_made)}")
        logger.info(f"   - Errors encountered: {len(errors_encountered)}")

        if tool_calls_made:
            logger.info(f"MULTI-TURN TOOL SEQUENCE:")
            for i, call in enumerate(tool_calls_made, 1):
                logger.info(f"   {i}. {call['tool_name']}: {call.get('error', 'SUCCESS')}")

        logger.info(f"Enhanced Multi-Turn Final Response: {full_response}")

        # Calculate token usage
        input_tokens = count_tokens(str(message), "gpt-4o-mini")
        output_tokens = count_tokens(full_response or "", "gpt-4o-mini")
        token_usage = {
            "input": input_tokens,
            "output": output_tokens,
            "total": input_tokens + output_tokens,
        }

        return {"text": full_response or "No response generated.", "tools": tool_calls_made, "token_usage": token_usage}

    except Exception as e:
        logger.error(f"Enhanced Multi-Turn MCP processing failed: {e}", exc_info=True)
        # Fallback to regular MCP processing
        logger.info("Falling back to regular MCP processing")
        return await process_message_with_zapier_mcp_streaming(mcp_key, message, image_urls, stream_callback)


def get_available_zapier_mcps() -> dict:
    """
    Get information about all available Zapier MCPs.

    Returns:
        Dictionary with MCP information for debugging/monitoring
    """
    return {
        mcp_key: {
            "name": config["name"],
            "description": config["description"],
            "keywords": config["keywords"]
        }
        for mcp_key, config in ZAPIER_MCPS.items()
    }
