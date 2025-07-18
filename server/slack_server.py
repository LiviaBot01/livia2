#!/usr/bin/env python3
"""
Slack Server
------------
Classe principal do servidor Slack Socket Mode refatorada.
"""

import os
import logging
import ssl
import certifi
import asyncio
import signal
import sys
import aiohttp
from typing import Optional
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from slack_bolt.app.async_app import AsyncApp
from slack_sdk.web.async_client import AsyncWebClient

from .config import set_global_agent
from .utils import log_startup
from .event_handlers import EventHandlers
from .message_processor import MessageProcessor

logger = logging.getLogger(__name__)


class SlackSocketModeServer:
    """
   Classe principal do servidor Slack Socket Mode
    
    Gerencia toda a conexão com o Slack, processamento de eventos e
    ciclo de vida do bot Livia. Esta é a espinha dorsal da comunicação.
    CRÍTICO: Falhas aqui desconectam o bot do Slack completamente!
    """
    
    def __init__(self):
        """
        🔧 Inicializa o servidor sem validação (feita no start)
        
        Configuração lazy loading - validação e inicialização real
        acontecem apenas quando o servidor é efetivamente iniciado.
        """
        self._shutdown_event = asyncio.Event()  # 🚦 Controle de desligamento gracioso
        self.app = None  # 📱 App Slack (inicializado depois)
        self.socket_mode_handler = None  # 🔌 Handler de conexão WebSocket
        self.message_processor = None  # 💬 Processador de mensagens
        self.event_handlers = None  # 🎯 Manipuladores de eventos
    
    def _validate_environment(self):
        """
        🔍 Verifica se as variáveis de ambiente necessárias estão presentes
        
        CRÍTICO: Sem essas variáveis, o bot não consegue se conectar ao Slack!
        Falha rápida é melhor que falha silenciosa.
        """
        required_vars = ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_TEAM_ID"]
        missing_vars = [var for var in required_vars if var not in os.environ]

        if missing_vars:
            logger.error(f"Missing required environment variables: {missing_vars}")
            raise ValueError(f"Missing required environment variables: {missing_vars}")
        
        logger.info("✅ All required Slack environment variables are present")
    
    def _initialize_slack_app(self):
        """
        📱 Inicializa o Slack App após validação das variáveis de ambiente
        
        Configura SSL, cliente web assíncrono, handlers de eventos e
        manipuladores de sinal para desligamento gracioso.
        CRÍTICO: Configuração SSL incorreta pode causar falhas de conexão!
        """

        # 🔒 Configuração SSL robusta com fallback
        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            logger.info(f"Usando CA bundle do certifi: {certifi.where()}")
        except Exception as e:
            logger.error(f"Erro ao criar contexto SSL usando certifi: {e}", exc_info=True)
            ssl_context = ssl.create_default_context()
            logger.warning("Voltando para contexto SSL padrão.")

        async_web_client = AsyncWebClient(
            token=os.environ["SLACK_BOT_TOKEN"],
            ssl=ssl_context
        )

        self.app = AsyncApp(
            client=async_web_client,
            logger=logging.getLogger("slack_bolt_disabled")  # Usar um logger desabilitado
        )

        # Manter logs do Slack visíveis para debugging (comentar/desabilitar critical level)
        self.app.logger.setLevel(logging.INFO)
        # self.app.logger.disabled = True

        # Configurar AsyncSocketModeHandler
        self.socket_mode_handler = AsyncSocketModeHandler(
            self.app,
            os.environ["SLACK_APP_TOKEN"]
        )

        # Registrar configuração de segurança
        # Usar logging visual para inicialização
        

        # Configurar manipuladores de eventos
        self._setup_event_handlers()
        
        # Configurar desligamento gracioso
        self._setup_signal_handlers()

    def _setup_event_handlers(self):
        """
        🎯 Configura os handlers de eventos usando a classe EventHandlers
        
        Conecta o processamento de mensagens aos eventos do Slack.
        ⚠️ CRÍTICO: Sem handlers, o bot não responde a mensagens!
        """
        # 💬 Criar processador de mensagens (core do bot)
        message_processor = MessageProcessor(self.app.client)
        
        # 🎯 Criar e configurar manipuladores de eventos
        event_handlers = EventHandlers(self.app, message_processor)
        event_handlers.setup_event_handlers()
        
        self.message_processor = message_processor
        self.event_handlers = event_handlers
    
    def _setup_signal_handlers(self):
        """
        🚦 Configurar manipuladores de sinal para desligamento 
        
        Captura SIGINT (Ctrl+C) e SIGTERM para desligamento limpo.
       🚨GUARDRAIL: Evita corrupção de dados e conexões órfãs.
        """
        def signal_handler(signum, frame):
            logger.info(f"Sinal {signum} recebido, iniciando desligamento gracioso...")
            self._shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def start_async(self):
        """
        🚀 Inicia o servidor Socket Mode de forma assíncrona
        
        Sequência de inicialização:
        1. Valida variáveis de ambiente
        2. Inicializa app Slack
        3. Inicia handler Socket Mode
        4. Monitora conexão e sinais de desligamento
        
        CRÍTICO: Esta função mantém o bot vivo - falhas aqui derrubam tudo!
        """
        try:            
            # CRÍTICO: Validar variáveis de ambiente primeiro
            self._validate_environment()
            
            # 📱 Inicializar App Slack se ainda não foi feito
            if self.app is None:
                self._initialize_slack_app()
            
            # 🔌 Iniciar o manipulador em segundo plano com tratamento robusto de erros
            
            try:
                handler_task = asyncio.create_task(self.socket_mode_handler.start_async())
            except TypeError as e:
                if "string argument without an encoding" in str(e):
                    #🚨GUARDRAIL: Erro conhecido de encoding no WebSocket ping
                    
                    await asyncio.sleep(1)  # Pequena pausa antes de continuar
                    
                    handler_task = asyncio.create_task(self.socket_mode_handler.start_async())
                else:
                    raise
            
            
            
            # 🚦 Aguardar sinal de desligamento ou conclusão do manipulador
            done, pending = await asyncio.wait(
                [handler_task, asyncio.create_task(self._shutdown_event.wait())],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # 🧹 Cancelar tarefas pendentes para limpeza
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # Verificar se a tarefa do manipulador foi concluída com erro
            if handler_task in done:
                try:
                    await handler_task
                except Exception as e:
                    logger.error(f"Tarefa do manipulador falhou: {e}")
                    raise
                    
        except Exception as e:
            logger.error(f"Erro ao iniciar servidor Slack: {e}", exc_info=True)
            raise
    
    async def stop_async(self):
        """
        🛑 Para o servidor Slack de forma graciosa
        
        Desligamento limpo para evitar conexões órfãs e corrupção de dados.
       🚨GUARDRAIL: Sempre tenta fechar conexões adequadamente.
        """
        try:
            logger.info("Parando servidor Slack Socket Mode...")
            self._shutdown_event.set()
            
            if self.socket_mode_handler:
                await self.socket_mode_handler.close_async()
                logger.info("Manipulador Slack fechado com sucesso")
            
            logger.info("Servidor Slack Socket Mode parado graciosamente")
                
        except Exception as e:
            logger.error(f"Erro durante desligamento do servidor: {e}")
            raise


# --- Funções de Inicialização e Limpeza do Agente ---
async def initialize_agent():
    """
    🤖 Inicializa o agente Livia com todas as ferramentas e MCPs
    
    Cria o agente principal com ferramentas integradas (web search, file search)
    e servidores MCP para integrações externas (Zapier, etc.).
    CRÍTICO: Sem agente, o bot não consegue processar mensagens!
    """
    logger.info("Inicializando Agente Livia (usando API Slack direta)...")

    try:
        from agent.creator import create_agent_with_mcp_servers
        agent = await create_agent_with_mcp_servers()
        set_global_agent(agent)  #🚨Define agente globalmente para acesso
        logger.info("Agente Livia inicializado com sucesso")
    except Exception as e:
        logger.error(f"Falha ao inicializar agente: {e}", exc_info=True)
        await cleanup_agent()
        raise


async def cleanup_agent():
    """
    🧹 Limpa os recursos do agente
    
    Libera recursos e conexões do agente para evitar vazamentos.
   🚨GUARDRAIL: Sempre limpa recursos mesmo em caso de erro.
    """
    logger.info("Limpando recursos do agente Livia...")

    # 🗑️ Por enquanto, apenas redefinir o agente global
    # TODO: Adicionar limpeza de MCPs e conexões quando necessário
    set_global_agent(None)
    logger.info("Limpeza do agente concluída.")


# --- Lógica Principal de Execução ---
async def async_main():
    """
    🎯 Ponto de entrada assíncrono principal
    
    Orquestra a inicialização completa do sistema:
    1. Inicializa agente Livia
    2. Cria servidor Slack
    3. Inicia conexão e aguarda eventos
    4. Limpa recursos no final
    
    CRÍTICO: Esta é a função principal - falhas aqui impedem o bot de funcionar!
    """
    logger.info("Iniciando Chatbot Livia Slack...")

    # Validação de ambiente será feita por SlackSocketModeServer.start_async()

    try:
        # 🤖 Inicializar o agente primeiro (dependência crítica)
        await initialize_agent()
        
        # 🚀 Criar e iniciar o servidor
        server = SlackSocketModeServer()
        await server.start_async()
        
    except KeyboardInterrupt:
        logger.info("Desligamento solicitado pelo usuário.")
    except Exception as e:
        logger.error(f"Erro na execução principal: {e}", exc_info=True)
    finally:
        # 🧹 Limpar recursos sempre (mesmo em caso de erro)
        await cleanup_agent()
        logger.info("Desligamento do Chatbot Livia Slack concluído.")


def main():
    """
    Ponto de entrada síncrono principal
    
    Wrapper síncrono que executa a função assíncrona principal.
    CRÍTICO: Esta é a função chamada quando o script é executado!
    """
    import asyncio
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Desligamento solicitado pelo usuário.")
    except Exception as e:
        logger.error(f"Erro no main: {e}", exc_info=True)


if __name__ == "__main__":
    main()
