#!/usr/bin/env python3

import os
import sys
import asyncio
import logging
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def load_env_file():
    """
    Carrega variáveis de ambiente do arquivo .env de forma segura
    
    Esta função substitui python-dotenv para evitar conflitos de dependência.
    Lê o arquivo .env linha por linha e define as variáveis no ambiente.
    
    CRÍTICO: Nunca commitar o arquivo .env no repositório!
    """
    env_path = project_root / '.env'
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Remove quotes if present
                    value = value.strip('"\'')
                    os.environ[key] = value
    else:
        pass  # Nada a fazer se .env não existir


load_env_file()


def check_environment():
    """
    Valida se todas as variáveis de ambiente críticas estão definidas
    
    CRÍTICO: Sem essas variáveis o bot não consegue funcionar!
    - OPENAI_API_KEY: Para comunicação com a API da OpenAI
    - SLACK_BOT_TOKEN: Token do bot para enviar mensagens
    - SLACK_APP_TOKEN: Token para Socket Mode (conexão em tempo real)
    """
    required_vars = [
        "OPENAI_API_KEY",
        "SLACK_BOT_TOKEN", 
        "SLACK_APP_TOKEN"
    ]
    
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        print("❌ Missing required environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\n📝 Please set these variables in your .env or .envrc file")
        sys.exit(1)


def setup_logging():
    """
   Configura sistema de logs com níveis apropriados para produção
    
    Define logs apenas para arquivo (livia.log) e suprime logs verbosos
    de bibliotecas externas para manter saída limpa no terminal.
    
    Níveis disponíveis: DEBUG, INFO, WARNING, ERROR
    """
    log_level = os.environ.get("LIVIA_LOG_LEVEL", "WARNING").upper()
    
    logging.basicConfig(
        level=getattr(logging, log_level, logging.WARNING),
        format='%(message)s',
        handlers=[
            logging.FileHandler('livia.log', mode='a')
        ]
    )
    # Suprime logs verbosos de bibliotecas externas
    logging.getLogger('slack_bolt').setLevel(logging.ERROR)
    logging.getLogger('slack_sdk').setLevel(logging.ERROR)
    logging.getLogger('urllib3').setLevel(logging.ERROR)
    logging.getLogger('httpx').setLevel(logging.ERROR)
    logging.getLogger('openai').setLevel(logging.ERROR)
    logging.getLogger('agents').setLevel(logging.ERROR)
    logging.getLogger('asyncio').setLevel(logging.ERROR)
    logging.getLogger('slack_bolt_disabled').setLevel(logging.ERROR)


async def async_main():
    """
   Função principal assíncrona que inicializa todo o sistema Livia
    
    Sequência de inicialização:
    1. Valida variáveis de ambiente críticas
    2. Configura sistema de logs
    3. Inicializa agente IA com guardrails
    4. Inicia servidor Slack Socket Mode
    
    CRÍTICO: Qualquer falha aqui impede o bot de funcionar!
    """
    print("🚀 INICIANDO...")
    
    print("✅ Credenciais:")
    print(f'OPENAI_API_KEY="{os.environ.get("OPENAI_API_KEY", "")[:10]}..."')
    print(f'SLACK_BOT_TOKEN="{os.environ.get("SLACK_BOT_TOKEN", "")[:10]}..."')
    print(f'SLACK_APP_TOKEN="{os.environ.get("SLACK_APP_TOKEN", "")[:10]}..."')
    print(f'SLACK_TEAM_ID="{os.environ.get("SLACK_TEAM_ID", "")[:10]}..."')
    
    check_environment()
    
    setup_logging()

    
    try:
        from server.slack_server import SlackSocketModeServer, initialize_agent
        
        await initialize_agent()
        
        server = SlackSocketModeServer()
        
        print("✅ Livia iniciada com sucesso")
        await server.start_async()
        
    
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.error(f"💥 Fatal error: {e}", exc_info=True)
        sys.exit(1)


def main():
    """
   Ponto de entrada principal do sistema Livia
    
    Wrapper síncrono que executa a função assíncrona principal.
    Trata interrupções do usuário (Ctrl+C) de forma elegante.
    """
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"💥 Failed to start Livia: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()