#!/usr/bin/env python3

import asyncio
import logging
from typing import List, Optional

from agents import Agent, WebSearchTool, FileSearchTool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from .config import (
    get_agent_instructions,
    generate_enhanced_zapier_tools_description
)
from .guardrails import professional_content_guardrail


async def create_agent_with_mcp_servers():
    """
   🚨Cria o agente principal Livia com ferramentas e guardrails de segurança
    
    Configura:
    - Instruções personalizadas para comportamento profissional
    - Ferramentas de busca web integradas
    - Guardrails para filtrar conteúdo inadequado
    
    ⚠️ CRÍTICO: O guardrail é essencial para manter conversas profissionais!
    """
    logger.info("Creating Livia - the Slack Chatbot Agent...")
    
    # Gera descrição das ferramentas MCP disponíveis
    zapier_tools_description = generate_enhanced_zapier_tools_description()
    
    # Define ferramentas básicas do agente
    tools = [
        WebSearchTool()  # Busca em tempo real na internet
    ]
    
    # Cria agente com configurações de segurança
    agent = Agent(
        name="Livia",
        instructions=get_agent_instructions(zapier_tools_description),
        model="gpt-4o",
        tools=tools,
        input_guardrails=[professional_content_guardrail]  #🚨Guardrail de entrada
    )
    
    logger.info("⚠️ Agent 'Livia' created with professional content guardrail.")
    return agent


async def create_agent():
    """
   Função wrapper para criação padrão do agente Livia
    
    Simplifica a criação do agente usando configurações padrão.
    Utiliza internamente create_agent_with_mcp_servers().
    """
    return await create_agent_with_mcp_servers()


async def create_agent_with_vector_store(vector_store_id: str):
    """
    Cria agente Livia com capacidade de busca em arquivos específicos
    
    Adiciona FileSearchTool para buscar em documentos indexados em vector store.
    Útil para consultas em bases de conhecimento específicas.
    
    Args:
        vector_store_id: ID do vector store da OpenAI com documentos indexados
    
    CRÍTICO: Vector store deve existir e estar acessível!
    """
    print(f"create_agent_with_vector_store called with vector_store_id: {vector_store_id}")
    logger.info(f"Creating agent with custom vector store: {vector_store_id}")
    
    try:
        # Gera descrição das ferramentas MCP
        zapier_tools_description = generate_enhanced_zapier_tools_description()
        
        # Define ferramentas incluindo busca em arquivos
        tools = [
            WebSearchTool(),  # Busca web
            FileSearchTool(vector_store_ids=[vector_store_id])  # Busca em documentos
        ]
        print(f"Tools created: {[type(tool).__name__ for tool in tools]}")

        # Cria agente com ferramentas expandidas
        agent = Agent(
            name="Livia",
            instructions=get_agent_instructions(zapier_tools_description),
            model="gpt-4o",
            tools=tools,
            input_guardrails=[professional_content_guardrail]  #🚨Guardrail de entrada
        )
        
        print(f"Agent created successfully: {agent is not None}")
        logger.info(f"Agent created with vector store: {vector_store_id}")
        return agent
    except Exception as e:
        print(f"Error creating agent: {e}")
        logger.error(f"Error creating agent with vector store: {e}")
        return None
