#!/usr/bin/env python3
"""
Livia Agent Message Processor
-----------------------------
Processamento principal de mensagens do agente Livia.
Inclui roteamento para MCPs e execução unificada.
"""

import logging
import re
from typing import Optional, List
from agents import Agent, Runner, InputGuardrailTripwireTriggered
from openai.types.responses import ResponseTextDeltaEvent

from .config import ZAPIER_MCPS
from .mcp_processor import (
    detect_zapier_mcp_needed,
    process_message_with_enhanced_multiturn_mcp,
    process_message_with_structured_output
)
from .mcp_streaming import process_message_with_zapier_mcp_streaming

logger = logging.getLogger(__name__)


async def process_message(agent: Agent, message: str, image_urls: Optional[List[str]] = None, stream_callback=None) -> dict:
    """
   Função principal de processamento de mensagens do agente Livia
    
    Esta é a função central que coordena todo o processamento de mensagens,
    incluindo detecção de MCPs, processamento de imagens e streaming de respostas.
    CRÍTICO: Esta função é o coração do sistema - falhas aqui afetam toda a experiência!
    
    Fluxo de processamento:
    1. Detecta se precisa de MCP específico (Zapier integrations)
    2. Processa imagens se fornecidas (visão computacional)
    3. Executa agente com streaming em tempo real
    4. Aplica guardrails de segurança profissional
    5. Retorna resposta estruturada

    Args:
        agent: Instância do agente OpenAI configurado
        message: Mensagem do usuário para processar
        image_urls: URLs opcionais de imagens para processamento de visão
        stream_callback: Callback opcional para atualizações em tempo real

    Returns:
        Dict: {"text": resposta, "tools": ferramentas_usadas, "token_usage": uso_tokens}
        
    CRÍTICO: Sempre retorna dict estruturado mesmo em caso de erro!
    """
    logger.info(f"Processing message: {message[:100]}{'...' if len(message) > 100 else ''}")
    
    logger.info("Processing message with gpt-4o")

    # 🔍 Detecta se precisa de MCP específico baseado em palavras-chave
    mcp_key = detect_zapier_mcp_needed(message)
    
    if mcp_key:
        logger.info(f"Detected MCP needed: {mcp_key}")
        
        # Remover fallbacks desnecessários para forçar uso de MCP
        try:
            return await process_message_with_enhanced_multiturn_mcp(
                mcp_key, message, image_urls, stream_callback
            )
        except Exception as e:
            logger.error(f"Enhanced multi-turn MCP failed: {e}")
            # 🔄 Fallback: processamento MCP regular com streaming
            try:
                return await process_message_with_zapier_mcp_streaming(
                    mcp_key, message, image_urls, stream_callback
                )
            except Exception as e2:
                logger.error(f"Regular MCP processing also failed: {e2}")
                # 🔄 Fallback final: processamento nativo do Agents SDK
                logger.info("Falling back to native Agents SDK processing")

    # Use native Agents SDK with streaming
    try:
        model_used = agent.model
        logger.info(f"🤖 AGENT PROCESSING - Model: {model_used}")
        logger.info(f"📝 Message: {message[:100]}{'...' if len(message) > 100 else ''}")
        
        # 🔧 Prepara input para o agente (texto + imagens opcionais)
        if image_urls:
            logger.info(f"🖼️ Processing {len(image_urls)} images with {model_used}")
            for i, url in enumerate(image_urls):
                logger.info(f"   Image {i+1}: {url[:80]}{'...' if len(url) > 80 else ''}")
            
            # CRÍTICO: Formato específico do OpenAI Agents SDK para processamento de visão
            # Estrutura multimodal: texto + imagens em formato padronizado
            content_items = [{"type": "input_text", "text": message}]
            for image_url in image_urls:
                content_items.append({
                    "type": "input_image",
                    "image_url": image_url,
                    "detail": "low"  #🚨Otimização: detail=low para economia de tokens
                })
            
            agent_input = [{
                "role": "user",
                "content": content_items
            }]
            logger.info(f"🔍 Vision input prepared: message + {len(image_urls)} images")
        else:
            agent_input = message
            logger.info(f"💬 Text-only input prepared as string")

        # Create dummy callback if none provided (always use streaming internally)
        if not stream_callback:
            async def dummy_callback(delta_text: str, full_text: str, tool_calls_detected=None):
                pass
            stream_callback = dummy_callback

        # Always use streaming execution with OpenAI Agents SDK API
        full_response = ""
        tool_calls = []

        # Use run_streamed() which returns RunResultStreaming
        # ⚠️ CRÍTICO: Execução do agente com captura de guardrails de segurança
        try:
            result = Runner.run_streamed(agent, agent_input)
        except InputGuardrailTripwireTriggered as e:
            #🚨GUARDRAIL ACIONADO: Conteúdo bloqueado por segurança profissional
            logger.warning(f"🚫 Guardrail triggered: Content blocked for professional environment")
            return {
                "text": "⚠️ Desculpe, mas não posso responder a esse tipo de conteúdo em um ambiente profissional. Por favor, mantenha as conversas relacionadas ao trabalho e produtividade.",
                "tools": [],
                "token_usage": {"input": 0, "output": 0, "total": 0}
            }

        # 🔄 Processamento de eventos de streaming em tempo real
        async for event in result.stream_events():
            if event.type == "raw_response_event":
                # 📝 Processa eventos de texto token por token (streaming de resposta)
                if isinstance(event.data, ResponseTextDeltaEvent) and event.data.delta:
                    delta_text = event.data.delta
                    full_response += delta_text
                    await stream_callback(delta_text, full_response, tool_calls)
                elif hasattr(event.data, 'delta') and event.data.delta:
                    # 🔄 Fallback para outros tipos de eventos delta
                    delta_text = event.data.delta
                    full_response += delta_text
                    await stream_callback(delta_text, full_response, tool_calls)
            elif event.type == "run_item_stream_event":
                # 🔧 Processa eventos de alto nível (chamadas de ferramentas, mensagens, etc)
                if event.item.type == "tool_call_item":
                    tool_name = getattr(event.item, 'name', 'unknown')
                    print(f"tool_call_item detected - name: {tool_name}")
                    # 📊 Registra início de chamada de ferramenta
                    tool_info = {
                        "tool_name": tool_name,
                        "arguments": getattr(event.item, 'arguments', {}),
                        "type": "tool_call_started"
                    }
                    tool_calls.append(tool_info)
                    await stream_callback("", full_response, tool_calls)
                elif event.item.type == "file_search_call":
                    print(f"file_search_call detected!")
                    # 📁 Registra chamada de busca em arquivos
                    tool_info = {
                        "tool_name": "file_search",
                        "arguments": {},
                        "type": "file_search_call"
                    }
                    tool_calls.append(tool_info)
                    await stream_callback("", full_response, tool_calls)
                elif event.item.type == "tool_call_output_item":
                    # ✅ Atualiza última chamada de ferramenta com informações de conclusão
                    if tool_calls:
                        tool_calls[-1].update({
                            "output": getattr(event.item, 'output', None),
                            "type": "tool_call_completed"
                        })

        # After streaming is complete, access final data directly from RunResultStreaming
        # The final_output and other properties are available directly on the result object

        # Log final response details
        final_text = full_response or str(result.final_output) if result.final_output else "No response generated."
        logger.info(f"✅ RESPONSE COMPLETE - Model: {agent.model}")
        logger.info(f"📤 Response length: {len(final_text)} chars")
        logger.info(f"🔧 Tools used: {len(tool_calls)} ({[t.get('tool_name', 'unknown') for t in tool_calls]})")
        logger.info(f"💬 Response preview: {final_text[:150]}{'...' if len(final_text) > 150 else ''}")
        
        return {
            "text": final_text,
            "tools": tool_calls,
            "token_usage": {"input": 0, "output": 0, "total": 0}  # Token usage not directly available in streaming mode
        }
            
    except Exception as e:
        logger.error(f"Native Agents SDK processing failed: {e}", exc_info=True)
        
        # Fallback final - retorna mensagem amigável de erro
        # ⚠️ CRÍTICO: Nunca expor detalhes técnicos ao usuário!
        error_msg = f"Erro no processamento da mensagem: {str(e)}"
        if "rate_limit" in str(e).lower():
            error_msg = "Muitas solicitações simultâneas. Tente novamente em alguns instantes."
        elif "timeout" in str(e).lower():
            error_msg = "Timeout na resposta. Tente novamente com uma mensagem mais simples."
        elif "connection" in str(e).lower():
            error_msg = "Erro de conexão. Tente novamente em alguns instantes."
        
        return {
            "text": error_msg,
            "tools": [],
            "token_usage": {"input": 0, "output": 0, "total": 0}
        }


def extract_tool_calls_from_response(response_text: str) -> List[dict]:
    """
    🔍 Extrai informações de chamadas de ferramentas do texto de resposta
    
    Função auxiliar que analisa o texto da resposta para identificar
    quais ferramentas foram utilizadas, útil para logging e debugging.
    
    Args:
        response_text: Texto da resposta para analisar
        
    Returns:
        Lista de dicionários com informações das ferramentas detectadas
        
    📊 Usado principalmente para métricas e debugging
    """
    tool_calls = []
    
    # Look for common tool indicators in the response
    if "web search" in response_text.lower() or "search" in response_text.lower():
        tool_calls.append({"tool_name": "web_search", "type": "inferred"})
    
    if "file search" in response_text.lower() or "document" in response_text.lower():
        tool_calls.append({"tool_name": "file_search", "type": "inferred"})
    
    if "image" in response_text.lower() and ("generat" in response_text.lower() or "creat" in response_text.lower()):
        tool_calls.append({"tool_name": "image_generation", "type": "inferred"})
    
    # Look for MCP indicators
    for mcp_key, mcp_config in ZAPIER_MCPS.items():
        for keyword in mcp_config.get('keywords', []):
            if keyword in response_text.lower():
                tool_calls.append({"tool_name": f"mcp_{mcp_key}", "type": "inferred"})
                break
    
    return tool_calls
