#!/usr/bin/env python3
"""
Livia MCP Streaming Processor
-----------------------------
Processamento de streaming para MCPs do Zapier com configurações específicas por serviço.
"""

import logging
import re
from typing import Optional, List
from openai import OpenAI

from .config import ZAPIER_MCPS, count_tokens

logger = logging.getLogger(__name__)


async def process_message_with_zapier_mcp_streaming(mcp_key: str, message: str, image_urls: Optional[List[str]] = None, stream_callback=None) -> dict:
    """
    Generic function to process message using OpenAI Responses API with any Zapier Remote MCP with streaming support.

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

    logger.info(f"Processing message with {mcp_config['name']} (STREAMING)")
    logger.info(f"MCP URL: {mcp_config['url']}")
    logger.info(f"MCP Server Label: {mcp_config['server_label']}")
    logger.info(f"Input message: {message}")

    try:
        # Special handling for individual MCPs with detailed logging
        stream = _create_mcp_stream(mcp_config, input_data, client)

        # Process streaming response with detailed logging
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
                    logger.info("MCP streaming response completed")
                elif event.type == "error":
                    error_details = {
                        "type": getattr(event, 'type', 'unknown'),
                        "message": getattr(event, 'message', str(event)),
                        "code": getattr(event, 'code', None),
                        "details": getattr(event, 'details', None)
                    }
                    errors_encountered.append(error_details)
                    logger.error(f"MCP DETAILED ERROR: {error_details}")
                elif hasattr(event, 'type') and 'tool_call' in event.type:
                    tool_call_info = {
                        "type": event.type,
                        "tool_name": getattr(event, 'name', 'unknown'),
                        "arguments": getattr(event, 'arguments', {}),
                        "output": getattr(event, 'output', None),
                        "error": getattr(event, 'error', None)
                    }
                    # --- FILE NAMES for file_search ---
                    if tool_call_info["tool_name"].lower() == "file_search":
                        output = tool_call_info.get("output", "")
                        # Try to extract file names from output: e.g., "Arquivo encontrado: nome_do_arquivo.pdf"
                        file_names = re.findall(r"Arquivo[s]?:?\s*([^\n,]+)", str(output), re.IGNORECASE)
                        if not file_names:
                            # Try to extract pdf/doc/docx/xlsx/names from output string
                            file_names = re.findall(r"[\w\-\_]+\.(?:pdf|docx?|xlsx?|pptx?)", str(output), re.IGNORECASE)
                        tool_call_info["file_names"] = file_names if file_names else []
                    tool_calls_made.append(tool_call_info)
                    logger.info(f"MCP TOOL CALL: {tool_call_info}")

        logger.info(f"MCP STREAMING SUMMARY:")
        logger.info(f"   - Response length: {len(full_response)} chars")
        logger.info(f"   - Tool calls made: {len(tool_calls_made)}")
        logger.info(f"   - Errors encountered: {len(errors_encountered)}")

        if tool_calls_made:
            logger.info(f"TOOL CALLS DETAILS:")
            for i, call in enumerate(tool_calls_made, 1):
                logger.info(f"   {i}. {call['tool_name']}: {call.get('error', 'SUCCESS')}")

        if errors_encountered:
            logger.error(f"ERROR DETAILS:")
            for i, error in enumerate(errors_encountered, 1):
                logger.error(f"   {i}. {error['message']} (Code: {error.get('code', 'N/A')})")

        logger.info(f"MCP Final Response: {full_response}")

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
        error_message = str(e)
        logger.error(f"Error calling {mcp_config['name']} with streaming: {e}")

        # Special handling for Gmail context window exceeded
        if mcp_config["server_label"] == "zapier-mcpgmail" and "context_length_exceeded" in error_message:
            logger.warning("Gmail MCP context window exceeded, trying with simplified request")
            try:
                # Retry with more restrictive search and summarization (non-streaming fallback)
                simplified_response = client.responses.create(
                    model="gpt-4o",
                    input="Busque apenas o último email recebido na caixa de entrada e faça um resumo muito breve",
                    # ⚠️
                    instructions=(
                        "You are Livia, an intelligent AI assistant. Search for the latest email in inbox using 'in:inbox' operator.\n"
                        "CRITICAL: Return only a 2-sentence summary in Portuguese.\n"
                        "Format: 'Último email de [sender] com assunto \"[subject]\". [Brief summary].'\n"
                        "NEVER return full email content - only essential information."
                    ),
                    tools=[
                        {
                            "type": "mcp",
                            "server_label": mcp_config["server_label"],
                            "server_url": mcp_config["url"],
                            "require_approval": "never",
                            "headers": {
                                "Authorization": f"Bearer {mcp_config['api_key']}"
                            }
                        }
                    ]
                )
                return {"text": simplified_response.output_text or "Não foi possível acessar os emails no momento.", "tools": []}
            except Exception as retry_error:
                logger.error(f"Gmail MCP retry also failed: {retry_error}")
                return {"text": "Não foi possível acessar os emails do Gmail no momento. O email pode ser muito grande para processar. Tente ser mais específico na busca.", "tools": []}

        raise


def _create_mcp_stream(mcp_config: dict, input_data, client):
    """Create appropriate MCP stream based on service type."""
    server_label = mcp_config["server_label"]
    
    if server_label == "zapier-mcpeverhour":
        return _create_everhour_stream(mcp_config, input_data, client)
    elif server_label == "zapier-mcpgmail":
        return _create_gmail_stream(mcp_config, input_data, client)
    elif server_label == "zapier-mcpasana":
        return _create_asana_stream(mcp_config, input_data, client)
    elif server_label == "zapier-mcpgooglecalendar":
        return _create_calendar_stream(mcp_config, input_data, client)
    elif server_label == "zapier-mcpslack":
        return _create_slack_stream(mcp_config, input_data, client)
    else:
        return _create_generic_stream(mcp_config, input_data, client)

# ⚠️
def _create_everhour_stream(mcp_config: dict, input_data, client):
    """Create Everhour-specific stream with detailed instructions."""
    return client.responses.create(
        model="gpt-4o",
        input=input_data,
        instructions=(
            "You are Livia, an intelligent AI assistant with Everhour MCP access.\n\n"
            "EVERHOUR AVAILABLE COMMANDS:\n"
            "SEARCH & FIND:\n"
            "- everhour_find_internal_project\n"
            "- everhour_find_project\n"
            "- everhour_find_section\n"
            "- everhour_find_member\n"
            "- everhour_find_task\n\n"
            "CREATE & MANAGE:\n"
            "- everhour_create_client\n"
            "- everhour_create_project\n"
            "- everhour_create_section\n"
            "- everhour_create_task\n\n"
            "TIME TRACKING:\n"
            "- everhour_start_timer\n"
            "- everhour_stop_timer\n"
            "- everhour_add_time\n\n"
            "TIME TRACKING WORKFLOW (MANDATORY STEPS):\n"
            "- Step 1: Use everhour_find_project to find project\n"
            "- Step 2: Use everhour_find_task to find specific task by name\n"
            "- Step 3: If task not found, use everhour_list_tasks for project to see all tasks\n"
            "- Step 4: ONLY if task doesn't exist, create with everhour_create_task\n"
            "- Step 5: Use everhour_add_time with exact task ID\n"
            "- Time format: 1h, 2h, 30m (examples: '2h', '1.5h', '30m')\n\n"
            "CRITICAL RULE: NEVER create a task without first searching for existing tasks!\n"
            "Always use everhour_find_task AND everhour_list_tasks before creating new tasks.\n\n"
            "DATE & TIME HANDLING (Timezone: America/Sao_Paulo):\n"
            "- 'hoje' / 'today' = current date in Brazil timezone\n"
            "- 'ontem' / 'yesterday' = previous day\n"
            "- 'esta semana' / 'this week' = current week range\n"
            "- Always convert relative dates to YYYY-MM-DD format\n"
            "- Current date reference: use system date in Brazil timezone\n"
            "- For time entries, be precise with dates as this affects timesheet accuracy\n\n"
            "FALLBACK STRATEGY:\n"
            "If everhour_find_task returns {{}}, try everhour_list_tasks to find available tasks\n\n"
            "RESPONSE FORMAT:\n"
            "SUCCESS: 'Tempo adicionado com sucesso! [time] na task [task_name] ([task_id])'\n"
            "ERROR: 'Erro: [details]'\n\n"
            "GOAL: Add time efficiently and provide clear feedback in Portuguese."
        ),
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
        stream=True
    )

# ⚠️
def _create_gmail_stream(mcp_config: dict, input_data, client):
    """Create Gmail-specific stream with optimized search."""
    return client.responses.create(
        model="gpt-4o",
        input=input_data,
        instructions=(
            "You are Livia, an intelligent AI assistant. Use Gmail tools to search and read emails.\n\n"
            "STEP-BY-STEP APPROACH:\n"
            "1. First: Use gmail_search_emails tool with search string 'in:inbox'\n"
            "2. Then: Use gmail_get_email tool to read the first email from results\n"
            "3. Finally: Summarize the email content\n\n"
            "SEARCH EXAMPLES:\n"
            "- For latest emails: 'in:inbox'\n"
            "- For unread emails: 'is:unread'\n"
            "- For recent emails: 'newer_than:1d'\n"
            "- Combined: 'in:inbox newer_than:1d'\n\n"
            "RESPONSE FORMAT (Portuguese):\n"
            "Último Email Recebido:\n"
            "De: [sender name and email]\n"
            "Assunto: [subject line]\n"
            "Data: [date received]\n"
            "Resumo: [Brief 2-3 sentence summary of main content]\n\n"
            "IMPORTANT:\n"
            "- Always use gmail_search_emails first to find emails\n"
            "- Then use gmail_get_email to read the specific email\n"
            "- Summarize content - don't return full email text\n"
            "- If search fails, try simpler search terms\n\n"
            "GOAL: Find and summarize the user's latest email efficiently."
        ),
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
        stream=True
    )

# ⚠️
def _create_asana_stream(mcp_config: dict, input_data, client):
    """Create Asana-specific stream."""
    return client.responses.create(
        model="gpt-4o",
        input=input_data,
        instructions=(
            f"You are Livia, an intelligent AI assistant with {mcp_config['name']} access.\n\n"
            "ASANA PROJECT MANAGEMENT:\n"
            "- Sequential search: workspace→project→task\n"
            "- Always include ALL IDs/numbers from responses\n"
            "- Limit 4 results, Portuguese responses\n"
            "- Example: 'Found project [ProjectName] (ev:123) with task [TaskName] (ev:456)'\n"
            "- For task creation: use exact project names and descriptions\n"
            "- ALWAYS log detailed information about API calls and responses\n\n"
            "GOAL: Manage projects and tasks efficiently with detailed feedback."
        ),
        tools=[
            {
                "type": "mcp",
                "server_label": mcp_config["server_label"],
                "server_url": mcp_config["url"],
                "require_approval": "never",
                "headers": {
                    "Authorization": f"Bearer {mcp_config['api_key']}"
                }
            }
        ],
        stream=True
    )

# ⚠️
def _create_calendar_stream(mcp_config: dict, input_data, client):
    """Create Google Calendar-specific stream."""
    return client.responses.create(
        model="gpt-4o",
        input=input_data,
        instructions=(
            "You are Livia, an intelligent AI assistant. Use Google Calendar tools to search and manage events.\n\n"
            "Search Strategy:\n"
            "- Try these tools in order: gcalendar_find_events, gcalendar_search_events, google_calendar_find_events\n"
            "- Use dynamic date parameters: start_date='today', end_date='next week'\n"
            "- Default range: today to next 7 days (calculated dynamically)\n"
            "- Timezone: America/Sao_Paulo\n"
            "- If no events found, try a broader date range\n\n"
            "Response Format (Portuguese):\n"
            "Eventos no Google Calendar:\n"
            "1. [Nome do Evento]\n"
            "   - Data: [data]\n"
            "   - Horário: [hora início] às [hora fim]\n"
            "   - Link: [link se disponível]\n\n"
            "IMPORTANT: Always search with explicit date ranges"
        ),
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
        stream=True
    )

# ⚠️
def _create_slack_stream(mcp_config: dict, input_data, client):
    """Create Slack-specific stream."""
    return client.responses.create(
        model="gpt-4o",
        input=input_data,
        instructions=(
            "You are Livia, an intelligent AI assistant with full Slack access. You can now send direct messages and channel messages using available tools like slack_send_direct_message and slack_send_channel_message.\n"
            "For finding messages: Use slack_find_message with 'in:channel-name' format. Sort by timestamp desc. Try different channel name variations if needed.\n"
            "For sending messages: Use appropriate send tools when requested.\n"
            "Return: For finds - user, timestamp, message content, permalink, summary in Portuguese. For sends - confirmation of message sent."
        ),
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
        stream=True
    )

# ⚠️
def _create_generic_stream(mcp_config: dict, input_data, client):
    """Create generic MCP stream for other services."""
    return client.responses.create(
        model="gpt-4o",
        input=input_data,
        instructions=(
            f"You are Livia, an intelligent AI assistant with {mcp_config['name']} access. Sequential search: workspace→project→task.\n"
            "Always include ALL IDs/numbers from responses. Limit 4 results. Portuguese responses.\n"
            "Example: 'Found project [ProjectName] (ev:123) with task [TaskName] (ev:456)'"
        ),
        tools=[
            {
                "type": "mcp",
                "server_label": mcp_config["server_label"],
                "server_url": mcp_config["url"],
                "require_approval": "never",
                "headers": {
                    "Authorization": f"Bearer {mcp_config['api_key']}"
                }
            }
        ],
        stream=True
    )
