# 🤖 Livia - Advanced Agentic Slack Chatbot

Livia é um chatbot inteligente para Slack que utiliza OpenAI Agents SDK com capacidades avançadas de processamento de texto, imagens, áudio e integração com múltiplas ferramentas via MCP (Model Context Protocol). Esta é a primeira versão estável, com correções de erros de sintaxe e indentação, remoção de mensagens de log verbosas para uma saída de terminal limpa e melhorias na inicialização para exibir apenas credenciais essenciais e confirmações de sucesso.

## ✨ Funcionalidades

- 🧠 **IA Avançada**: Powered by gpt-4o com streaming de respostas em tempo real
- 🛡️ **Guardrails de Segurança**: Sistema de filtros para manter conversas profissionais
- 🔍 **Busca Web**: Pesquisas em tempo real na internet
- 🖼️ **Geração de Imagens**: Criação e edição de imagens com DALL-E
- 🎵 **Transcrição de Áudio**: Conversão de áudio para texto
- 📁 **Busca em Arquivos**: Sistema de busca vetorial em documentos
- 🔗 **Integrações MCP**: Everhour, Asana, Gmail, Google Calendar, Slack
- 💭 **Modo Pensamento**: Processamento isolado com modelo o3 via comando `+think`

## 🚀 Instalação

### Pré-requisitos

Para começar, você precisa de:
- Python 3.11 ou superior (baixe em python.org se necessário)
- Conta no Slack com permissões para criar apps (crie uma conta gratuita em slack.com)
- Chave de API da OpenAI (obtenha em platform.openai.com)
- Tokens de acesso para integrações (opcional, como Asana ou Gmail)

### 1. Clone o repositório

Abra o terminal e execute:

```bash
git clone <repository-url>
cd livia2
```

Isso copia o código para sua máquina.

### 2. Instale as dependências

```bash
pip install -r requirements.txt
```

Isso instala todas as bibliotecas necessárias, como slack-bolt e openai.

### 3. Configure as variáveis de ambiente

Variáveis de ambiente são como configurações secretas. Exporte-as no terminal:

```bash
export OPENAI_API_KEY="sua-chave-openai"
export SLACK_BOT_TOKEN="seu-token-bot"
export SLACK_APP_TOKEN="seu-app-token"
export SLACK_TEAM_ID="seu-team-id"
```

Para integrações opcionais, adicione credenciais semelhantes. Elas são essenciais para o bot funcionar sem expor segredos.

## ⚙️ Configuração do Slack

### 1. Criar um Slack App

1. Acesse [api.slack.com/apps](https://api.slack.com/apps)
2. Clique em "Create New App" → "From scratch"
3. Nomeie o app (ex: "Livia") e selecione seu workspace

### 2. Configurar Permissões

Em **OAuth & Permissions**, adicione estes Bot Token Scopes (permitem que o bot leia e escreva mensagens):

```
app_mentions:read
channels:history
channels:read
chat:write
files:read
files:write
reactions:read
reactions:write
users:read
users:read.email
```

### 3. Configurar Socket Mode

1. Vá em **Socket Mode** e ative
2. Gere um App-Level Token com escopo `connections:write`
3. Copie o token (começa com `xapp-`)

Isso permite comunicação em tempo real.

### 4. Configurar Event Subscriptions

Em **Event Subscriptions**, adicione estes eventos (para o bot reagir a menções e mensagens):

```
app_mention
message.channels
reaction_added
```

### 5. Instalar o App

1. Vá em **Install App** e instale no workspace
2. Copie o Bot User OAuth Token (começa com `xoxb-`)

Agora o app está pronto no Slack!

## 🏃‍♂️ Executando

Ao executar, o terminal mostrará apenas credenciais mascaradas (para segurança) e mensagens de sucesso como "Livia iniciada com sucesso" e "Conectada ao Slack", sem logs desnecessários.

### Modo Desenvolvimento

```bash
python livia.py
```

Ideal para testes, com saída limpa.

### Modo Produção

```bash
# Com logs detalhados (se precisar depurar)
LOG_LEVEL=INFO python livia.py

# Em background (roda sem terminal aberto)
nohup python livia.py > livia.log 2>&1 &
```

Verifique livia.log para qualquer saída.

## 📖 Como Usar

### Comandos Básicos

- **Mencionar o bot**: `@Livia sua pergunta aqui` - O bot responde em threads para organização.
- **Busca web**: `@Livia pesquise sobre IA generativa` - Retorna resultados da internet.
- **Gerar imagem**: `@Livia crie uma imagem de um gato astronauta` - Usa DALL-E para criar imagens.
- **Modo pensamento**: `+think` (abre modal para processamento isolado)

### Integrações MCP

Essas conectam Livia a outros apps:
- **Asana**: `@Livia quais são minhas tarefas no Asana?`
- **Gmail**: `@Livia verifique emails de hoje`
- **Calendar**: `@Livia qual minha agenda para amanhã?`
- **Everhour**: `@Livia quanto tempo trabalhei hoje?`

## 🛡️ Segurança

### Guardrails Implementados

Filtros automáticos bloqueiam:
- Conteúdo sexual ou adulto
- Violência ou ameaças
- Informações pessoais sensíveis
- Discussões políticas ou religiosas
- Referências a drogas ou álcool

Mantenha conversas profissionais!

### Desenvolvimento Seguro

- Canal restrito durante desenvolvimento (`DEVELOPMENT_CHANNEL`)
- Variáveis de ambiente protegidas (não commit no git)
- Logs configuráveis para não expor dados sensíveis

## 📁 Estrutura do Projeto

Aqui está a organização dos arquivos para você navegar facilmente:

```
livia2/
├── README.md                # Este arquivo de instruções
├── agent/                   # Lógica principal da IA
│   ├── __init__.py
│   ├── config.py            # Configurações da IA
│   ├── creator.py           # Cria agentes OpenAI
│   ├── guardrails.py        # Filtros de segurança
│   ├── mcp_processor.py     # Processa integrações MCP
│   ├── mcp_streaming.py     # Streaming para MCP
│   └── processor.py         # Processador de mensagens
├── livia.py                 # Script principal para rodar o bot
├── pyproject.toml           # Configurações do projeto Python
├── requirements.txt         # Lista de dependências
├── server/                  # Servidor Slack
│   ├── __init__.py
│   ├── config.py            # Configurações do servidor
│   ├── context_manager.py   # Gerencia contexto de conversas
│   ├── event_handlers.py    # Manipula eventos do Slack
│   ├── message_processor.py # Processa mensagens recebidas
│   ├── slack_server.py      # Inicia o servidor Socket Mode
│   ├── streaming_processor.py # Streaming de respostas
│   └── utils.py             # Funções utilitárias
├── slack_formatter.py       # Formata mensagens para Slack
└── tools/                   # Ferramentas adicionais
    ├── __init__.py
    ├── document_processor.py # Processa documentos
    ├── image_generation.py   # Gera imagens
    ├── mcp/                  # Integrações MCP
    │   ├── __init__.py
    │   ├── cache_manager.py  # Gerencia cache
    │   └── zapier_mcps.py    # Integra com Zapier
    ├── structured_schemas.py # Esquemas estruturados
    ├── thinking_agent.py     # Modo pensamento
    └── web_search.py         # Busca web
```

## 🔧 Troubleshooting

Versão otimizada com correções de sintaxe e indentação em livia.py e slack_server.py. Saída do terminal agora é minimalista.

### Problemas Comuns

**Erro: "No module named 'regex'"**
```bash
pip install regex
```

**Bot não responde no Slack**
- Verifique se o bot foi mencionado na primeira mensagem da thread
- Confirme se está no canal correto (desenvolvimento)
- Verifique os logs em `livia.log` para erros

**Erro de autenticação**
- Confirme se os tokens estão corretos (veja seção de configuração)
- Verifique permissões do app no Slack

**Script para sozinho**
- Certifique-se de que todas variáveis de ambiente estão setadas
- Rode com LOG_LEVEL=DEBUG para mais detalhes

### Logs

Para debug detalhado:
```bash
LOG_LEVEL=DEBUG python livia.py
```

## 🤝 Contribuindo

1. Fork o projeto (crie uma cópia no GitHub)
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request no GitHub

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo `LICENSE` para mais detalhes.

## 📞 Suporte

Para suporte técnico, entre em contato com <@U046LTU4TT5> no Slack.

---

**Desenvolvido com ❤️ usando OpenAI Agents SDK e Slack Bolt**