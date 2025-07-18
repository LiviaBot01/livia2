#!/usr/bin/env python3
"""
Event Handlers
--------------
Handlers de eventos do Slack para o bot Livia.
Inclui processamento de mensagens, áudio, imagens e shortcuts.
"""

import logging
import re
from typing import List, Optional, Dict, Any

from .config import (
    is_channel_allowed, get_bot_user_id, get_processed_messages,
    SHOW_DEBUG_LOGS, get_global_agent
)
from .utils import log_message_received, log_error
from .message_processor import MessageProcessor
from tools.document_processor import DocumentProcessor

logger = logging.getLogger(__name__)


class EventHandlers:
    """Gerencia todos os handlers de eventos do Slack."""
    
    def __init__(self, app, message_processor: MessageProcessor):
        self.app = app
        self.message_processor = message_processor
        self.bot_user_id = get_bot_user_id()
        self.processed_messages = get_processed_messages()
        self.document_processor = DocumentProcessor()
        
        # Clear processed messages cache on startup to avoid stale entries
        self.processed_messages.clear()
        logger.info("🧹 Cleared processed messages cache on startup")
    
    def setup_event_handlers(self):
        """Configura todos os handlers de eventos."""
        self.app.event("message")(self.handle_message_events)
        self.app.event("app_mention")(self.handle_app_mention_events)
        self.app.action("static_select-action")(self.handle_think_selection)
    
    async def handle_message_events(self, event, say, client):
        """
        Processa eventos de mensagem em threads do Slack.
        Responde a mensagens em threads onde o bot já foi mencionado.
        """
        try:
            logger.info(f"📬 DM (MESSAGE) EVENT RECEIVED: {event}")

            channel_id = event.get("channel")
            user_id = event.get("user")
            text = event.get("text", "")
            ts = event.get("ts")

            # Security check - only DMs are processed here
            if not await self._is_dm_channel(channel_id, client):
                logger.info(f"⏭️ Skipping non-DM channel {channel_id}")
                return

            # Skip bot's own messages
            if user_id == self.bot_user_id:
                return

            # Use the message 'ts' as the 'thread_ts' for DMs
            thread_ts_for_reply = ts

            # Skip if message already processed
            message_key = f"{channel_id}_{ts}_{user_id}"
            if message_key in self.processed_messages:
                return
            self.processed_messages.add(message_key)

            # Clean terminal logging
            log_message_received(user_id, channel_id, text)

            # Process the message
            await self.message_processor.process_message(
                text=text,
                say=say,
                client=client,
                channel_id=channel_id,
                thread_ts_for_reply=thread_ts_for_reply,
                image_urls=self._extract_image_urls(event),
                audio_files=await self._extract_audio_files(event, client),
                document_files=await self.document_processor.extract_document_files(event, client),
                use_thread_history=False,  # DMs don't need thread history
                user_id=user_id
            )

        except Exception as e:
            logger.error(f"Error in handle_message_events: {e}", exc_info=True)
            log_error(f"Erro no processamento de mensagem: {str(e)}")

    async def _is_dm_channel(self, channel_id: str, client) -> bool:
        """Verifica se um canal é DM."""
        try:
            channel_info = await client.conversations_info(channel=channel_id)
            return channel_info["ok"] and channel_info["channel"]["is_im"]
        except Exception as e:
            logger.error(f"Error checking if channel {channel_id} is DM: {e}")
            return False
    async def handle_app_mention_events(self, event, say, client):
        """
        Processa eventos de menção (@livia) no Slack.
        Este handler garante que o bot responda quando mencionado em mensagens diretas ou threads.
        """
        try:
            logger.info(f"🎯 APP MENTION EVENT RECEIVED: {event}")
            
            # Extract event details
            channel_id = event.get("channel")
            user_id = event.get("user")
            text = event.get("text", "")
            ts = event.get("ts")
            thread_ts = event.get("thread_ts")
            
            logger.info(f"📋 Mention details: channel={channel_id}, user={user_id}, ts={ts}, thread_ts={thread_ts}, text='{text}'")
            
            # Early validation
            if not all([channel_id, user_id, ts]):
                logger.warning(f"❌ Missing essential data in mention: channel_id={channel_id}, user_id={user_id}, ts={ts}")
                return
            
            # Skip if no agent
            agent = get_global_agent()
            if not agent:
                logger.warning("❌ No global agent available for mention")
                return

            # Skip bot's own mentions
            if user_id == self.bot_user_id:
                logger.info(f"⏭️ Skipping bot's own mention (bot_id={self.bot_user_id})")
                return

            # Skip DMs - they are handled by handle_message_events
            if await self._is_dm_channel(channel_id, client):
                logger.info(f"⏭️ Skipping DM channel {channel_id} - handled by message handler")
                return

            # Skip if already processed
            message_key = f"{channel_id}_{ts}_{user_id}"
            if message_key in self.processed_messages:
                logger.info(f"⏭️ Message already processed: {message_key}")
                return
            
            # Add to processed messages
            self.processed_messages.add(message_key)
            
            if len(self.processed_messages) > 10000:
                old_messages = list(self.processed_messages)[:1000]
                for old_msg in old_messages:
                    self.processed_messages.discard(old_msg)

            log_message_received(user_id, channel_id, text)

            # Auto-start new thread for direct mentions
            thread_ts_for_reply = thread_ts or ts

            # Extract files
            image_urls = self._extract_image_urls(event)
            audio_files = await self._extract_audio_files(event, client)
            document_files = await self.document_processor.extract_document_files(event, client)

            # Check for +think command
            clean_text = re.sub(f"<@{self.bot_user_id}>", "", text).strip()
            
            if clean_text.strip().startswith("+think"):
                await self._handle_think_command(clean_text, channel_id, user_id, thread_ts_for_reply, say, client)
                return

            # Process the message normally
            await self.message_processor.process_message(
                text=clean_text,
                say=say,
                client=client,
                channel_id=channel_id,
                thread_ts_for_reply=thread_ts_for_reply,
                image_urls=image_urls,
                audio_files=audio_files,
                document_files=document_files,
                use_thread_history=True,
                user_id=user_id
            )

        except Exception as e:
            logger.error(f"Error in handle_app_mention_events: {e}", exc_info=True)
            log_error(f"Erro no processamento de menção: {str(e)}")

    async def handle_think_selection(self, ack, body, client, say):
        """
        Handle the selection from the think improvement button.
        """
        try:
            await ack()
            
            # Get selection value
            selected_value = body["actions"][0]["selected_option"]["value"]
            channel_id = body["channel"]["id"]
            user_id = body["user"]["id"]
            message_ts = body["message"]["ts"]
            
            # Security check
            if not await is_channel_allowed(channel_id, user_id, client):
                return

            # Get the original think message from the stored context
            original_message = getattr(self, '_pending_think_message', None)
            thread_history = getattr(self, '_pending_think_history', [])
            
            if not original_message:
                await client.chat_update(
                    channel=channel_id,
                    ts=message_ts,
                    text="❌ Sessão expirada. Tente novamente com +think."
                )
                return

            # Determine if we should improve the prompt
            improve_prompt = selected_value == "value-0"  # SIM - melhorar prompt
            
            # Update message to show processing is starting
            if improve_prompt:
                await client.chat_update(
                    channel=channel_id,
                    ts=message_ts,
                    text="✨ Reformulando prompt..."
                )
            else:
                await client.chat_update(
                    channel=channel_id,
                    ts=message_ts,
                    text="🧠 Analisando profundamente..."
                )

            # Process with the new sequential flow
            await self.message_processor.process_think_message(
                original_message,
                channel_id=channel_id,
                user_id=user_id,
                thread_ts=message_ts,
                say=say,
                client=client,
                improve_prompt=improve_prompt,
                thread_history=thread_history if improve_prompt else None
            )
            
            # Clean up stored context
            self._pending_think_message = None
            self._pending_think_history = []

        except Exception as e:
            logger.error(f"Error in handle_think_selection: {e}", exc_info=True)
            await client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text="❌ Erro ao processar seleção. Tente novamente."
            )



    async def _handle_think_command(self, text: str, channel_id: str, user_id: str, thread_ts: str, say, client):
        """
        Handle +think command by showing improvement selection button.
        """
        try:
            # Extract the think message (remove +think prefix)
            think_message = text[6:].strip()  # Remove "+think" and whitespace
            
            if not think_message:
                await say("Por favor, forneça uma mensagem após o comando +think.", thread_ts=thread_ts)
                return

            # Get thread history for context
            thread_history = await self._get_thread_history(channel_id, thread_ts, client)
            
            # Store the message and history for later use
            self._pending_think_message = think_message
            self._pending_think_history = thread_history
            
            # Send the selection button
            await say(
                text="Quer que eu melhore seu prompt antes de enviar?",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "Quer que eu melhore seu prompt antes de enviar?"
                        },
                        "accessory": {
                            "type": "static_select",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "...",
                                "emoji": True
                            },
                            "options": [
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "SIM ⚠️",
                                        "emoji": True
                                    },
                                    "value": "value-0"
                                },
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Não 🚫",
                                        "emoji": True
                                    },
                                    "value": "value-1"
                                }
                            ],
                            "action_id": "static_select-action"
                        }
                    }
                ],
                thread_ts=thread_ts
            )
            
        except Exception as e:
            logger.error(f"Error in _handle_think_command: {e}", exc_info=True)
            await say("Erro ao processar comando +think.", thread_ts=thread_ts)

    async def _get_thread_history(self, channel_id: str, thread_ts: str, client) -> List[Dict]:
        """
        Get the conversation history from the thread.
        """
        try:
            response = await client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=20
            )
            return response.get("messages", [])
        except Exception as e:
            logger.error(f"Error getting thread history: {e}")
            return []

    def _extract_image_urls(self, event: Dict[str, Any]) -> List[str]:
        """Extract image URLs from Slack message event."""
        image_urls = []
        
        # Check for files in the message
        files = event.get("files", [])
        for file_info in files:
            if file_info.get("mimetype", "").startswith("image/"):
                # Use the URL that doesn't require authentication if available
                url = file_info.get("url_private") or file_info.get("permalink")
                if url:
                    image_urls.append(url)
        
        # Check for image URLs in text (enhanced URL detection)
        text = event.get("text", "")
        
        # Pattern for image URLs (more comprehensive)
        url_patterns = [
            r'https?://[^\s<>]+\.(?:jpg|jpeg|png|gif|webp|bmp|tiff)(?:\?[^\s<>]*)?',  # Direct image URLs
            r'https?://[^\s<>]*(?:imgur|flickr|instagram|twitter|facebook|ichef\.bbci)[^\s<>]*',   # Image hosting sites including BBC
            r'https?://[^\s<>]*\.(?:com|org|net|co\.uk)/[^\s<>]*\.(?:jpg|jpeg|png|gif|webp)', # Images on websites
            r'https?://ichef\.bbci\.co\.uk/[^\s<>]*',  # BBC image URLs specifically
        ]
        
        for pattern in url_patterns:
            found_urls = re.findall(pattern, text, re.IGNORECASE)
            for url in found_urls:
                # Clean up URL (remove trailing punctuation)
                url = re.sub(r'[.,;!?]+$', '', url)
                if url not in image_urls:
                    image_urls.append(url)
                    logger.info(f"Found image URL in text: {url}")
        
        return image_urls

    async def _extract_audio_files(self, event: Dict[str, Any], client) -> List[Dict[str, Any]]:
        """Extract audio files from Slack message event."""
        audio_files = []
        
        files = event.get("files", [])
        for file_info in files:
            mimetype = file_info.get("mimetype", "")
            if mimetype.startswith("audio/") or file_info.get("name", "").lower().endswith(('.mp3', '.wav', '.m4a', '.ogg', '.flac')):
                try:
                    # Get file information directly from the event data
                    file_id = file_info.get("id")
                    file_url = file_info.get("url_private")
                    
                    if file_url and file_id:
                        # No need to make an additional API call, we already have the file info
                        audio_files.append({
                            "id": file_id,
                            "name": file_info.get("name", "audio_file"),
                            "url": file_url,
                            "mimetype": mimetype,
                            "size": file_info.get("size", 0),
                            "duration_ms": file_info.get("duration_ms", 0)
                        })
                except Exception as e:
                    logger.error(f"Error processing audio file: {e}")
        
        return audio_files

    async def _transcribe_audio_file(self, audio_file: Dict[str, Any]) -> Optional[str]:
        """Transcribe audio file using OpenAI Whisper."""
        try:
            # This would need to be implemented with actual audio transcription
            # For now, return a placeholder
            logger.info(f"Audio transcription not yet implemented for {audio_file['name']}")
            return f"[Áudio: {audio_file['name']} - Transcrição não implementada]"
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            return None
