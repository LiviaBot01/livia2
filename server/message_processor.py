#!/usr/bin/env python3

import logging
import os
import asyncio
from typing import List, Optional, Dict, Any

from .config import (
    get_global_agent, get_agent_semaphore, is_channel_allowed,
    SHOW_DEBUG_LOGS, get_bot_user_id
)
from .context_manager import ContextManager
from .streaming_processor import StreamingProcessor
from tools.document_processor import DocumentProcessor
from .utils import (
    get_user_friendly_error_message, should_retry_error,
    log_bot_response, count_tokens
)
from slack_formatter import format_message_for_slack
from tools import ImageProcessor, image_generator
from agent.creator import create_agent, create_agent_with_vector_store

logger = logging.getLogger(__name__)




class MessageProcessor:
    """Processador principal de mensagens do Livia
    
    Gerencia todo o fluxo de processamento de mensagens recebidas do Slack,
    incluindo contexto, streaming, documentos, áudio e imagens.
    Aplica guardrails de segurança e controle de acesso por canal.
    """
    
    def __init__(self, app_client):
        """Inicializa o processador com componentes essenciais
        
        Args:
            app_client: Cliente do Slack para comunicação com a API
        """
        self.app_client = app_client
        self.context_manager = ContextManager(app_client)  #🚨Gerencia histórico e contexto
        self.streaming_processor = StreamingProcessor()    #🚨Processa respostas em tempo real
        self.bot_user_id = get_bot_user_id()              #🚨ID do bot para filtrar mensagens
        self.document_processor = DocumentProcessor()      #🚨Processa documentos enviados
        self.thread_vector_stores = {}                    # Cache de vector stores por thread
    
    async def process_message(
        self,
        text: str,
        say,
        client,
        channel_id: str,
        thread_ts_for_reply: Optional[str] = None,
        image_urls: Optional[List[str]] = None,
        audio_files: Optional[List[dict]] = None,
        document_files: Optional[List[dict]] = None,
        use_thread_history: bool = True,
        user_id: str = None,
        model_override: Optional[str] = None,
    ):
        """Função principal de processamento de mensagens
        
        Orquestra todo o fluxo: validação de canal, processamento de mídia,
        aplicação de contexto, execução do agente e resposta com streaming.
        
        ⚠️ CRÍTICO: Valida permissões de canal antes de processar
       🚨Aplica guardrails de conteúdo e controle de acesso
        
        Args:
            text: Texto da mensagem do usuário
            say: Função para enviar respostas ao Slack
            client: Cliente Slack para operações avançadas
            channel_id: ID do canal onde a mensagem foi enviada
            thread_ts_for_reply: Timestamp da thread (se aplicável)
            image_urls: URLs de imagens anexadas
            audio_files: Arquivos de áudio para transcrição
            document_files: Documentos para processamento
            use_thread_history: Se deve incluir histórico da thread
            user_id: ID do usuário que enviou a mensagem
            model_override: Modelo específico a usar (opcional)
        """
        
        
        #🚨Cria uma instância local do agente para este processamento
        current_agent = await create_agent()
        if model_override:
            current_agent.model = model_override

        # CRÍTICO: Verifica se o agente está pronto antes de processar
        if not current_agent:
            logger.error("Livia agent not ready.")
            await say(text="Livia is starting up, please wait.", channel=channel_id, thread_ts=thread_ts_for_reply)
            return

        model_name = current_agent.model
        original_channel_id = channel_id
        #🚨GUARDRAIL: Verifica se o canal tem permissão para usar o bot
        if not await is_channel_allowed(channel_id, user_id or "unknown", self.app_client):
            return

        #🚨GUARDRAIL: Filtra mensagens automáticas para evitar loops infinitos
        if text and any(phrase in text.lower() for phrase in [
            "encontrei o arquivo", "você pode acessá-lo", "estou à disposição",
            "não consegui encontrar", "vou procurar", "aqui está"
        ]):
            return

        # Prepara o contexto inicial com o texto da mensagem
        context_input = text

        #🚨Processa arquivos de áudio usando Whisper para transcrição
        if audio_files:
            transcriptions = []
            for audio_file in audio_files:
                transcription = await self._transcribe_audio_file(audio_file)
                if transcription:
                    transcriptions.append(f"🎵 **Áudio '{audio_file['name']}'**: {transcription}")
                else:
                    transcriptions.append(f"❌ **Erro ao transcrever áudio '{audio_file['name']}'**")
            if transcriptions:
                if text:
                    context_input = f"{text}\n\n" + "\n\n".join(transcriptions)
                else:
                    context_input = "\n\n".join(transcriptions)

        document_summary = None
        if document_files:
            doc_result = await self._process_document_files(document_files, client, say, channel_id, thread_ts_for_reply)
            document_summary = doc_result.get('summary') if doc_result else None
            vector_store_id = doc_result.get('vector_store_id') if doc_result else None
            if vector_store_id:
                current_agent = await create_agent_with_vector_store(vector_store_id)
            if document_summary:
                if context_input:
                    context_input = f"{context_input}\n\n{document_summary}"
                else:
                    context_input = document_summary
                logger.info(f"✅ Document processing completed. Vector store ID: {self.current_vector_store_id}")
            else:
                logger.warning("❌ Document processing failed or returned no summary")
                if not context_input.strip():
                    context_input = "O usuário enviou documentos, mas houve erro no processamento."

        if use_thread_history and thread_ts_for_reply:
            full_history = await self.context_manager.fetch_thread_history(
                channel_id, thread_ts_for_reply, model_name
            )
            if full_history:
                context_input = full_history + f"\n\nLatest message: {context_input}"

        agent_semaphore = get_agent_semaphore()
        async with agent_semaphore:
            thinking_msg = await say(
                text=":hourglass_flowing_sand: Pensando...", 
                channel=original_channel_id, 
                thread_ts=thread_ts_for_reply
            )
            message_ts = thinking_msg.get("ts")

            initial_tags = self.streaming_processor.get_initial_cumulative_tags(
                text, audio_files, image_urls, model_name
            )
            
            header_prefix = self.streaming_processor.format_tags_display(initial_tags) + "\n\n"

            try:
                if "ImageGen" in initial_tags:
                    await self._handle_image_generation(text, say, original_channel_id, thread_ts_for_reply)
                    return

                processed_image_urls = []
                if image_urls:
                    processed_image_urls = await ImageProcessor.process_image_urls(image_urls)
                else:
                    if SHOW_DEBUG_LOGS:
                        logger.info("No images detected in this message")

                stream_callback = await self.streaming_processor.create_stream_callback(
                    self.app_client, original_channel_id, message_ts, header_prefix,
                    audio_files, processed_image_urls, text, model_name
                )

                from agent.processor import process_message
                response = await process_message(current_agent, context_input, processed_image_urls, stream_callback)
                text_resp = response.get("text") if isinstance(response, dict) else str(response)
                tool_calls = response.get("tools") if isinstance(response, dict) else []
                structured_data = response.get("structured_data") if isinstance(response, dict) else None

                final_cumulative_tags = await self.streaming_processor.detect_tools_and_model(
                    tool_calls, text_resp, processed_image_urls, audio_files,
                    text, model_name, vector_store_id if 'vector_store_id' in locals() else None
                )
                header_prefix_final = self.streaming_processor.format_tags_display(final_cumulative_tags) + "\n\n"

                token_info = response.get("token_usage", {}) if isinstance(response, dict) else {}
                input_tokens = token_info.get("input", count_tokens(context_input))
                output_tokens = token_info.get("output", count_tokens(text_resp))
                total_tokens = input_tokens + output_tokens
                thread_key = thread_ts_for_reply or original_channel_id
                
                is_at_limit, memory_warning = self.context_manager.check_context_limit(
                    thread_key, total_tokens, model_name
                )

                text_with_footer = text_resp + memory_warning
                
                tools_used = []
                if "`⛭" in header_prefix_final:
                    import re
                    tool_matches = re.findall(r'`⛭([^`]+)`', header_prefix_final)
                    tools_used = tool_matches
                
                try:
                    formatted_response = header_prefix_final + format_message_for_slack(text_with_footer)
                    
                    await self.app_client.chat_update(
                        channel=original_channel_id,
                        ts=message_ts,
                        text=formatted_response
                    )
                except Exception as final_update_error:
                    await say(text=formatted_response, channel=original_channel_id, thread_ts=thread_ts_for_reply)

                if SHOW_DEBUG_LOGS:
                    tools_used = None
                    if "`" in formatted_response:
                        import re
                        tools_match = re.findall(r'`([^`]+)`', formatted_response)
                        if tools_match:
                            tools_used = " ".join(tools_match)
                    log_bot_response(formatted_response, tools_used)

            except Exception as e:
                logger.error(f"Error during Livia agent streaming processing: {e}", exc_info=True)

                user_error_msg = get_user_friendly_error_message(e)

                retry_count = getattr(self, '_retry_count', 0)
                max_retries = 3
                
                if should_retry_error(e) and retry_count < max_retries:
                    self._retry_count = retry_count + 1
                    backoff_time = min(2 ** retry_count, 10)  # Exponential backoff, max 10s
                    
                    logger.info(f"🔄 Retrying ({self._retry_count}/{max_retries}) due to temporary error: {type(e).__name__}")
                    logger.info(f"⏱️ Waiting {backoff_time}s before retry")
                    
                    await asyncio.sleep(backoff_time)

                    try:
                        return await self.process_and_respond_streaming(
                            text, say, channel_id, thread_ts_for_reply,
                            image_urls, audio_files, use_thread_history, user_id
                        )
                    except Exception as retry_error:
                        logger.error(f"Retry {self._retry_count} failed: {retry_error}")
                        user_error_msg = get_user_friendly_error_message(retry_error)
                    finally:
                        if hasattr(self, '_retry_count'):
                            delattr(self, '_retry_count')

                try:
                    if 'message_ts' in locals():
                        await self.app_client.chat_update(
                            channel=original_channel_id,
                            ts=message_ts,
                            text=user_error_msg
                        )
                    else:
                        await say(text=user_error_msg, channel=original_channel_id, thread_ts=thread_ts_for_reply)
                except:
                    await say(text="Erro: Falha na comunicação. Se persistir entre em contato com: <@U046LTU4TT5>", channel=original_channel_id, thread_ts=thread_ts_for_reply)

    async def _handle_image_generation(self, text: str, say, channel_id: str, thread_ts: Optional[str]):
        """Gera imagens usando DALL-E baseado no prompt do usuário
        
        Processa solicitações de geração de imagem com feedback em tempo real
        e tratamento de erros robusto.
        
        Args:
            text: Prompt para geração da imagem
            say: Função para enviar mensagens ao Slack
            channel_id: ID do canal
            thread_ts: Timestamp da thread (opcional)
        """
        try:
            result = await image_generator.generate_image_with_progress(
                prompt=text,
                say=say,
                channel=channel_id,
                thread_ts=thread_ts
            )

        except Exception as e:
            logger.error(f"Error in image generation: {e}")
            await say(
                text=f"Erro na geração de imagem: {str(e)}", 
                channel=channel_id, 
                thread_ts=thread_ts
            )

    async def _process_document_files(self, document_files: List[dict], client, say, channel_id: str, thread_ts: Optional[str]) -> Optional[dict]:
        """Processa documentos enviados pelo usuário
        
        # Esta função está funcional 100% para upload, mas precisa de ajustes para file search. Não alterar sem revisão.
        """
        """Processa documentos enviados pelo usuário
        
        Faz upload para OpenAI, cria/atualiza vector stores para busca
        e configura o agente temporariamente com FileSearchTool.
        
        ⚠️ CRÍTICO: Gerencia vector stores por thread para isolamento
       🚨Aplica processamento seguro de arquivos
        
        Args:
            document_files: Lista de arquivos de documento
            client: Cliente Slack
            say: Função para enviar mensagens
            channel_id: ID do canal
            thread_ts: Timestamp da thread
            
        Returns:
            Resumo do processamento ou None se falhou
        """
        try:
            if not document_files:
                return None
            
            status_msg = await say(
                text="📄 Processando documentos...",
                channel=channel_id,
                thread_ts=thread_ts
            )
            
            slack_token = os.environ.get("SLACK_BOT_TOKEN")
            uploaded_files = await self.document_processor.upload_to_openai(
                document_files, slack_token
            )
            
            if uploaded_files:
                file_search_files = uploaded_files
                
                vector_store_id = None
                context_messages = []
                
                if file_search_files:
                    thread_key = f"{channel_id}_{thread_ts or 'main'}"
                    existing_vector_store_id = self.thread_vector_stores.get(thread_key)
                    
                    if existing_vector_store_id:
                        vector_store_id = await self.document_processor.add_files_to_existing_vector_store(
                            existing_vector_store_id, file_search_files
                        )
                        logger.info(f"📁 Arquivos adicionados ao vector store existente: {existing_vector_store_id}")
                    else:
                        vector_store_id = await self.document_processor.create_vector_store_with_files(
                            file_search_files, f"Documentos - {channel_id}"
                        )
                        if vector_store_id:
                            self.thread_vector_stores[thread_key] = vector_store_id
                            logger.info(f"📁 Novo vector store criado para thread: {vector_store_id}")
                    
                    if vector_store_id:
                        print(f"Vector store created/found: {vector_store_id}")
                        await self._create_temporary_agent_with_vector_store(vector_store_id)
                        print(f"current_vector_store_id after agent creation: {self.current_vector_store_id}")
                        
                        file_search_names = [f["name"] for f in file_search_files]
                        context_messages.append(f"📄 {len(file_search_files)} documento(s) processado(s) para busca: {', '.join(file_search_names)}")
                    else:
                        print(f"No vector_store_id created - file_search_files: {len(file_search_files) if file_search_files else 0}")
                
                summary = self.document_processor.format_upload_summary(uploaded_files)
                
                await client.chat_update(
                    channel=channel_id,
                    ts=status_msg["ts"],
                    text=summary
                )
                
                if context_messages:
                    return {'summary': ' '.join(context_messages) + ' Os arquivos estão prontos para análise.', 'vector_store_id': vector_store_id}
                else:
                    return f"📄 {len(uploaded_files)} arquivo(s) processado(s) e pronto(s) para análise."
            else:
                await client.chat_update(
                    channel=channel_id,
                    ts=status_msg["ts"],
                    text="❌ Não foi possível processar os documentos enviados."
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing documents: {e}")
            if 'status_msg' in locals():
                try:
                    await client.chat_update(
                        channel=channel_id,
                        ts=status_msg["ts"],
                        text="❌ Erro interno ao processar documentos."
                    )
                except:
                    pass
            return None


    async def _transcribe_audio_file(self, audio_file: Dict[str, Any]) -> Optional[str]:
        """Transcreve arquivos de áudio usando Whisper da OpenAI
        
        # Esta função está funcional 100%. Não alterar sem revisão.
        """
        """Transcreve arquivos de áudio usando Whisper da OpenAI
        
        Baixa o arquivo do Slack, salva temporariamente e envia para
        transcrição usando o modelo Whisper em português.
        
        CRÍTICO: Gerencia arquivos temporários e tokens de acesso
        
        Args:
            audio_file: Dicionário com informações do arquivo de áudio
            
        Returns:
            Texto transcrito ou mensagem de erro
        """
        try:
            import os
            import tempfile
            import httpx
            from openai import AsyncOpenAI
            
            file_name = audio_file.get('name', 'unknown_audio')
            file_url = audio_file.get('url')
            file_type = audio_file.get('mimetype', 'audio/unknown')
            duration_ms = audio_file.get('duration_ms', 0)
            duration_sec = duration_ms / 1000 if duration_ms else 0
            
            if not file_url:
                logger.warning(f"No URL found for audio file: {file_name}")
                return f"[Erro: URL do arquivo de áudio não encontrada]"
            
            # CRÍTICO: Verifica se o token do Slack está configurado
            slack_token = os.environ.get("SLACK_BOT_TOKEN")
            if not slack_token:
                logger.error("SLACK_BOT_TOKEN not found")
                return f"[Erro: Token do Slack não configurado]"
            
            headers = {"Authorization": f"Bearer {slack_token}"}
            
            async with httpx.AsyncClient() as client:
                response = await client.get(file_url, headers=headers)
                if response.status_code != 200:
                    logger.error(f"Failed to download audio file: {response.status_code}")
                    return f"[Erro ao baixar arquivo de áudio: {response.status_code}]"
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.m4a') as temp_file:
                    temp_file.write(response.content)
                    temp_file_path = temp_file.name
            
            try:
                #🚨Usa Whisper da OpenAI para transcrição em português
                openai_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
                
                with open(temp_file_path, 'rb') as audio_file_obj:
                    transcript = await openai_client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file_obj,
                        language="pt",  #🚨Força idioma português
                        response_format="text"
                    )
                
                transcription_text = transcript.strip() if isinstance(transcript, str) else transcript.text.strip()
                return transcription_text
                
            finally:
                #🚨Limpa arquivo temporário para segurança
                try:
                    os.unlink(temp_file_path)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup temp file: {cleanup_error}")
                    
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            return f"[Erro na transcrição: {str(e)}]"

    async def process_think_message(
        self,
        message: str,
        channel_id: str,
        user_id: str,
        thread_ts: str,
        say,
        client,
        improve_prompt: bool = False,
        thread_history: list = None
    ):
        """Processa mensagens de análise profunda usando agente especializado
        
        Opcionalmente melhora o prompt usando contexto da conversa,
        depois executa análise detalhada com agente dedicado.
        
       🚨Aplica guardrails de conteúdo profissional
        CRÍTICO: Pode gerar respostas longas que precisam ser divididas
        
        Args:
            message: Prompt para análise
            channel_id: ID do canal
            user_id: ID do usuário
            thread_ts: Timestamp da thread
            say: Função para enviar mensagens
            client: Cliente Slack
            improve_prompt: Se deve melhorar o prompt usando contexto
            thread_history: Histórico da conversa para contexto
        """
        try:
            from agents import Agent, Runner, InputGuardrailTripwireTriggered
            
            final_prompt = message
            
            #Melhora o prompt usando contexto da conversa se solicitado
            if improve_prompt and thread_history:
                print(f"[DEBUG] Iniciando reformulação do prompt: {message}")
                
                # Agente especializado em melhorar prompts para análise
                improvement_agent = Agent(
                    name="PromptImprover",
                    model="gpt-4o",
                    instructions="""
Você é um especialista em reformular prompts para análise profunda.

Sua tarefa:
1. Reformule o prompt original deixando-o mais claro, organizado e direto
2. Use o contexto da conversa para entender melhor o que o usuário quer analisar
3. Mantenha o idioma original do prompt
4. Responda APENAS com o prompt reformulado, sem explicações adicionais
5. Torne o prompt mais específico e direcionado para análise profunda
"""
                )
                
                context = "\n".join([
                    f"Usuário: {msg.get('text', '')}" if msg.get('user') != self.bot_user_id 
                    else f"Livia: {msg.get('text', '')}"
                    for msg in thread_history[-10:]
                ])
                
                improvement_input = f"Contexto da conversa:\n{context}\n\nPrompt original para reformular:\n{message}"
                
                try:
                    improvement_result = await Runner.run(
                        improvement_agent,
                        input=improvement_input,
                        max_turns=1
                    )
                except InputGuardrailTripwireTriggered:
                    #🚨GUARDRAIL: Bloqueia conteúdo inadequado na melhoria do prompt
                    await say(
                        text="⚠️ Desculpe, mas não posso processar esse tipo de conteúdo em um ambiente profissional.",
                        thread_ts=thread_ts
                    )
                    return
                
                final_prompt = improvement_result.final_output.strip()
                print(f"[DEBUG] Prompt reformulado: {final_prompt}")
            
            print(f"[DEBUG] Iniciando análise profunda com o3: {final_prompt}")
            
            # Atualiza mensagem para mostrar que está processando
            if client:
                await client.chat_update(
                    channel=channel_id,
                    ts=thread_ts,
                    text=":brain: Analisando cuidadosamente..."
                )
            
            #Agente especializado em análise profunda e detalhada
            o3_agent = Agent(
                name="DeepThinking",
                model="o3",
                instructions="""
Você é um assistente especializado em análise profunda. Forneça análises abrangentes, detalhadas e bem estruturadas.

Diretrizes:
- Seja detalhado e completo na análise
- Use estrutura clara com tópicos e subtópicos
- Forneça insights acionáveis
- Responda sempre no mesmo idioma da pergunta
- Seja objetivo mas abrangente
"""
            )
            
            try:
                result = await Runner.run(
                    o3_agent,
                    input=final_prompt,
                    max_turns=1
                )
            except InputGuardrailTripwireTriggered:
                #🚨GUARDRAIL: Bloqueia conteúdo inadequado na análise principal
                await say(
                    text="⚠️ Desculpe, mas não posso analisar esse tipo de conteúdo em um ambiente profissional.",
                    thread_ts=thread_ts
                )
                return
            
            final_response = result.final_output
            print(f"[DEBUG] Resposta do o3 (tamanho: {len(final_response)} chars)")
            
            # CRÍTICO: Divide mensagens longas para evitar limite do Slack
            if len(final_response) > 3000:
                parts = self._split_long_message(final_response, max_length=3000)
                
                first_msg = await say(
                    text=parts[0],
                    thread_ts=thread_ts
                )
                
                # Envia partes restantes sequencialmente
                for part in parts[1:]:
                    await say(
                        text=part,
                        thread_ts=thread_ts
                    )
            else:
                await say(
                    text=final_response,
                    thread_ts=thread_ts
                )
            
        except Exception as e:
            logger.error(f"Error in process_think_message: {e}", exc_info=True)
            await say(
                text=f"Erro ao processar análise: {str(e)}",
                thread_ts=thread_ts
            )
    
    def _split_long_message(self, message: str, max_length: int = 3000) -> List[str]:
        """Divide mensagens longas respeitando estrutura de parágrafos
        
        Tenta manter parágrafos inteiros quando possível, senão divide
        por sentenças e como último recurso por caracteres.
        
        CRÍTICO: Necessário para respeitar limites do Slack
        
        Args:
            message: Mensagem a ser dividida
            max_length: Tamanho máximo de cada parte
            
        Returns:
            Lista de partes da mensagem
        """
        if len(message) <= max_length:
            return [message]
        
        parts = []
        current_part = ""
        
        paragraphs = message.split('\n\n')
        
        for paragraph in paragraphs:
            if len(current_part) + len(paragraph) + 2 > max_length:
                if current_part:
                    parts.append(current_part.strip())
                    current_part = paragraph
                else:
                    sentences = paragraph.split('. ')
                    for sentence in sentences:
                        if len(current_part) + len(sentence) + 2 > max_length:
                            if current_part:
                                parts.append(current_part.strip())
                                current_part = sentence
                            else:
                                while len(sentence) > max_length:
                                    parts.append(sentence[:max_length])
                                    sentence = sentence[max_length:]
                                current_part = sentence
                        else:
                            current_part += sentence + '. '
            else:
                current_part += paragraph + '\n\n'
        
        if current_part.strip():
            parts.append(current_part.strip())
        
        return parts
