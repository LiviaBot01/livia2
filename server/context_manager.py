#!/usr/bin/env python3
"""
Context Manager
---------------
Gerenciamento de contexto e histórico de threads do Slack.
Inclui controle de janela de contexto e busca de histórico.
"""

import logging
from typing import Optional, List, Dict, Any

from .utils import count_tokens, get_model_context_limits
from .config import SHOW_DEBUG_LOGS

logger = logging.getLogger(__name__)


class ContextManager:
    """Gerencia contexto de conversas e histórico de threads."""
    
    def __init__(self, app_client):
        self.app_client = app_client
    
    def manage_context_window(self, messages: list, model: str, max_tokens_for_response: int = 4000) -> list:
        """
        Remove mensagens antigas automaticamente quando contexto fica muito cheio.
        Mantém sempre as mensagens mais recentes + margem para resposta.
        """
        if not messages:
            return messages

        context_limits = get_model_context_limits()
        context_limit = context_limits.get(model, 128000)
        max_context_tokens = context_limit - max_tokens_for_response - 1000  # Margem de segurança

        # Calcular tokens das mensagens (do mais recente para o mais antigo)
        messages_with_tokens = []
        total_tokens = 0

        for msg in reversed(messages):  # Começar pelas mais recentes
            msg_text = f"[{msg.get('username', 'User')}]: {msg.get('text', '')}"
            msg_tokens = count_tokens(msg_text, model)

            if total_tokens + msg_tokens <= max_context_tokens:
                messages_with_tokens.insert(0, msg)  # Inserir no início para manter ordem
                total_tokens += msg_tokens
            else:
                # Contexto cheio, parar de adicionar mensagens antigas
                break

        removed_count = len(messages) - len(messages_with_tokens)
        if removed_count > 0:
            logger.info(f"🧹 Context management: Removed {removed_count} old messages to fit context window")
            logger.info(f"📊 Keeping {len(messages_with_tokens)} recent messages ({total_tokens} tokens)")

        return messages_with_tokens

    async def fetch_thread_history(self, channel_id: str, thread_ts: str, model: str = "gpt-4o") -> Optional[str]:
        """Busca e formata o histórico da thread com gerenciamento automático de contexto."""
        try:
            if SHOW_DEBUG_LOGS:
                logger.debug(f"Buscando histórico para thread {channel_id}/{thread_ts}...")

            # Get thread replies (aumentar limite para pegar mais histórico)
            response = await self.app_client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=100  # Buscar mais mensagens, depois filtrar por contexto
            )

            if not response["ok"]:
                logger.warning(f"Erro ao buscar histórico da thread: {response.get('error', 'Erro desconhecido')}")
                return None

            messages = response.get("messages", [])
            if not messages:
                return None

            # Preparar mensagens com informações de usuário
            formatted_messages = []
            for msg in messages:
                user_id = msg.get("user", "Desconhecido")
                text = msg.get("text", "")

                # Get user info for better formatting
                try:
                    user_info = await self.app_client.users_info(user=user_id)
                    username = user_info["user"]["display_name"] or user_info["user"]["real_name"] or user_id
                except:
                    username = user_id

                formatted_messages.append({
                    "username": username,
                    "text": text,
                    "ts": msg.get("ts", "")
                })

            # Aplicar gerenciamento de contexto (manter mensagens mais recentes)
            managed_messages = self.manage_context_window(formatted_messages, model)

            # Format the final thread history
            formatted_history = "Histórico da Thread:\n"
            for msg in managed_messages:
                formatted_history += f"[{msg['username']}]: {msg['text']}\n"

            return formatted_history

        except Exception as e:
            logger.error(f"Erro ao buscar histórico da thread: {e}", exc_info=True)
            return None

    def check_context_limit(self, thread_key: str, total_tokens: int, model: str) -> tuple[bool, str]:
        """
        Verifica se a conversa está próxima do limite de contexto.
        
        Returns:
            tuple: (is_at_limit, warning_message)
        """
        from .utils import get_thread_token_usage
        
        thread_token_usage = get_thread_token_usage()
        context_limits = get_model_context_limits()
        
        thread_token_usage[thread_key] += total_tokens
        context_limit = context_limits.get(model, 128000)
        percent = (thread_token_usage[thread_key] / context_limit) * 100

        # Add memory limit warning only when reaching limit (100%+)
        if percent >= 100:
            warning_message = "\n\n⚠️ Você chegou no limite de memória, comece uma nova conversa."
            return True, warning_message
        
        return False, ""

    def extract_user_info_from_message(self, message: Dict[str, Any]) -> Dict[str, str]:
        """
        Extrai informações do usuário de uma mensagem do Slack.
        
        Args:
            message: Mensagem do Slack
            
        Returns:
            Dict com informações do usuário
        """
        user_id = message.get("user", "Desconhecido")
        
        return {
            "user_id": user_id,
            "username": user_id,  # Will be updated with real name if available
            "text": message.get("text", ""),
            "ts": message.get("ts", "")
        }

    async def get_user_display_name(self, user_id: str) -> str:
        """
        Busca o nome de exibição do usuário via API do Slack.
        
        Args:
            user_id: ID do usuário no Slack
            
        Returns:
            Nome de exibição do usuário
        """
        try:
            user_info = await self.app_client.users_info(user=user_id)
            if user_info["ok"]:
                user_data = user_info["user"]
                return user_data.get("display_name") or user_data.get("real_name") or user_id
        except Exception as e:
            logger.warning(f"Erro ao buscar informações do usuário {user_id}: {e}")
        
        return user_id

    def format_thread_history(self, messages: List[Dict[str, Any]]) -> str:
        """
        Formata o histórico da thread para uso como contexto.
        
        Args:
            messages: Lista de mensagens formatadas
            
        Returns:
            String formatada do histórico
        """
        if not messages:
            return ""
        
        formatted_history = "Histórico da Thread:\n"
        for msg in messages:
            username = msg.get('username', 'User')
            text = msg.get('text', '')
            formatted_history += f"[{username}]: {text}\n"
        
        return formatted_history
