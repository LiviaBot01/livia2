#!/usr/bin/env python3
"""
Server Utilities
----------------
Utilitários e funções auxiliares para o servidor Slack.
Inclui contagem de tokens, tratamento de erros e logging.
"""

import logging
import tiktoken
from typing import Dict, Any, Optional, List
from collections import defaultdict

# Error handling imports
import openai
from openai import APIError, APITimeoutError, RateLimitError, APIConnectionError
import time

# Configura logger limpo customizado apenas para interações do bot
clean_logger = logging.getLogger("livia_clean")
clean_logger.setLevel(logging.INFO)
clean_handler = logging.StreamHandler()
clean_handler.setFormatter(logging.Formatter("%(message)s"))
clean_logger.addHandler(clean_handler)
clean_logger.propagate = False

# Token usage tracking per thread/channel
thread_token_usage = defaultdict(int)
MODEL_CONTEXT_LIMITS = {
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
}


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Return token count for text using tiktoken."""
    try:
        enc = tiktoken.encoding_for_model(model)
    except Exception:
        enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def get_user_friendly_error_message(error: Exception) -> str:
    """
    Retorna mensagens de erro fixas para evitar gasto de tokens.
    Todas as mensagens seguem o padrão: "Erro: xxx. Se persistir entre em contato com: <@U046LTU4TT5>"
    """
    error_str = str(error).lower()

    # OpenAI API specific errors
    if isinstance(error, APITimeoutError):
        return "Erro: Timeout na API. Se persistir entre em contato com: <@U046LTU4TT5>"

    elif isinstance(error, RateLimitError):
        return "Erro: Limite de requisições atingido. Se persistir entre em contato com: <@U046LTU4TT5>"

    elif isinstance(error, APIConnectionError):
        return "Erro: Falha de conexão com OpenAI. Se persistir entre em contato com: <@U046LTU4TT5>"

    elif isinstance(error, APIError):
        if "context_length_exceeded" in error_str or "token" in error_str:
            return "Erro: Conversa muito longa. Comece uma nova thread."
        elif "model" in error_str and "not found" in error_str:
            return "Erro: Modelo indisponível. Se persistir entre em contato com: <@U046LTU4TT5>"
        else:
            return "Erro: API OpenAI. Se persistir entre em contato com: <@U046LTU4TT5>"

    # Network and connection errors
    elif "timeout" in error_str or "timed out" in error_str:
        return "Erro: Timeout na operação. Se persistir entre em contato com: <@U046LTU4TT5>"

    elif "connection" in error_str or "network" in error_str:
        return "Erro: Problema de rede. Se persistir entre em contato com: <@U046LTU4TT5>"

    elif "ssl" in error_str or "certificate" in error_str:
        return "Erro: Certificado SSL. Se persistir entre em contato com: <@U046LTU4TT5>"

    # Slack API errors
    elif "slack" in error_str:
        if "rate_limited" in error_str:
            return "Erro: Limite do Slack atingido. Se persistir entre em contato com: <@U046LTU4TT5>"
        elif "channel_not_found" in error_str:
            return "Erro: Canal não encontrado. Se persistir entre em contato com: <@U046LTU4TT5>"
        else:
            return "Erro: API do Slack. Se persistir entre em contato com: <@U046LTU4TT5>"

    # Memory and resource errors
    elif "memory" in error_str or "out of" in error_str:
        return "Erro: Recursos insuficientes. Se persistir entre em contato com: <@U046LTU4TT5>"

    # Permission errors
    elif "permission" in error_str or "unauthorized" in error_str or "forbidden" in error_str:
        return "Erro: Sem permissão. Se persistir entre em contato com: <@U046LTU4TT5>"

    # Generic fallback
    else:
        return "Erro: Falha inesperada. Se persistir entre em contato com: <@U046LTU4TT5>"


def should_retry_error(error: Exception) -> bool:
    """
    Determina se um erro deve ser tentado novamente automaticamente.
    """
    error_str = str(error).lower()

    # Retry for temporary issues
    retry_conditions = [
        isinstance(error, (APITimeoutError, APIConnectionError)),
        "timeout" in error_str,
        "connection" in error_str,
        "network" in error_str,
        "rate_limited" in error_str,
        "temporarily unavailable" in error_str,
        "service unavailable" in error_str
    ]

    return any(retry_conditions)


# 🎨 Funções de logging visual para terminal limpo
def log_startup():
    clean_logger.info("LIVIA - INICIADA COM SUCESSO")
    clean_logger.info("Aguardando mensagens...")
    clean_logger.info("")


def log_message_received(user_id, channel_id, text):
    print(f"NOVA MENSAGEM\n   Usuário: {user_id}\n   Canal: {channel_id}\n   Texto: {text}")


def log_bot_response(response_text, tools_used=None):
    print(response_text)


def log_error(error_msg):
    clean_logger.info("❌ ERRO:")
    clean_logger.info(f"   {error_msg}")
    clean_logger.info("")


def get_thread_token_usage():
    """Get the current thread token usage dictionary."""
    return thread_token_usage


def get_model_context_limits():
    """Get the model context limits dictionary."""
    return MODEL_CONTEXT_LIMITS
