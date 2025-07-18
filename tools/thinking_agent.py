#!/usr/bin/env python3
"""
Thinking Agent Tool - Agente o3 como ferramenta
---------------------------------------------------
Implementa um agente especializado em análise profunda usando o modelo o3
como ferramenta do agente principal Livia.
"""

import logging
from typing import Optional
from agents import Agent, function_tool, Runner, InputGuardrailTripwireTriggered

logger = logging.getLogger(__name__)

# ⚠️ Agente especializado em thinking com o3
thinking_agent = Agent(
    name="ThinkingAgent",
    model="o3",
    instructions="""
<identity>
You are a specialized thinking agent focused on deep analysis, problem-solving, and strategic reasoning.
</identity>

<thinking_style>
- Provide COMPREHENSIVE, DETAILED analysis - do NOT be brief or concise
- Provide actionable insights and comprehensive recommendations
- Give COMPLETE responses - the user expects full analysis from a expert.
</thinking_style>

<analysis_framework>
1. UNDERSTAND: Clarify the problem/question thoroughly
2. ANALYZE: Break down into key components with detailed examination
3. EXPLORE: Consider different angles and approaches comprehensively
4. SYNTHESIZE: Combine insights into coherent, complete analysis
5. RECOMMEND: Provide clear, actionable next steps with full justification
</analysis_framework>

<response_format>
- Always respond in the same language as the input
- Use clear structure with headers and bullet points
- Provide specific, actionable recommendations with full explanations
- Include complete reasoning behind all conclusions
- Be comprehensive and thorough - this is deep thinking, not brief responses
- Give the user the full value of an expert reasoning capabilities
</response_format>
"""
)

@function_tool
async def deep_thinking_analysis(query: str) -> str:
    """
    Performs deep analysis using the specialized o3 thinking agent.

    Use this tool when users request:
    - Deep analysis or thinking (+think, thinking, análise profunda)
    - Problem-solving and strategic reasoning
    - Brainstorming and creative solutions
    - Complex decision-making support
    - Step-by-step breakdown of problems

    Args:
        query: The question, problem, or topic to analyze deeply

    Returns:
        Comprehensive analysis and recommendations from the thinking agent
    """
    try:
        logger.info(f"🧠 Deep thinking analysis requested: {query[:100]}...")

        # Run the specialized thinking agent (regular run for now)
        try:
            result = await Runner.run(
                thinking_agent,
                input=f"Provide comprehensive deep analysis for: {query}",
                max_turns=3  # Allow some back-and-forth for complex analysis
            )
        except InputGuardrailTripwireTriggered:
            logger.warning(f"🚫 Guardrail triggered for thinking analysis: {query[:50]}...")
            return "⚠️ Desculpe, mas não posso analisar esse tipo de conteúdo em um ambiente profissional. Por favor, mantenha as análises relacionadas ao trabalho e produtividade."

        # Get the full response
        full_response = result.final_output

        # Check if response contains reasoning traces (o3 models sometimes include them)
        reasoning_trace = ""
        if "Reasoning" in full_response and "──────" in full_response:
            # Try to extract reasoning section
            parts = full_response.split("──────")
            if len(parts) > 1:
                # Look for reasoning content
                for part in parts:
                    if "UNDERSTANDING" in part or "ANALYZING" in part or "EXPLORING" in part:
                        reasoning_trace = part.strip()
                        break

        # Format response with reasoning if available
        if reasoning_trace:
            # Remove reasoning from main response and format separately
            clean_response = full_response.replace(reasoning_trace, "").replace("──────", "").strip()
            formatted_response = f"```\n{reasoning_trace}\n```\n\n{clean_response}"
            logger.info(f"🧠 Deep thinking analysis completed with reasoning: {len(formatted_response)} characters")
        else:
            formatted_response = full_response
            logger.info(f"🧠 Deep thinking analysis completed: {len(formatted_response)} characters")

        return formatted_response

    except Exception as e:
        logger.error(f"Error in deep thinking analysis: {e}")
        return f"Erro na análise profunda: {str(e)}. Tente novamente ou reformule a pergunta."

def get_thinking_tool():
    """Returns the thinking agent as a tool for the main Livia agent."""
    return deep_thinking_analysis

# Keywords that trigger the thinking tool
THINKING_KEYWORDS = [
    "+think"
]

def should_use_thinking_tool(message: str) -> bool:
    """
    Determines if the message should trigger the thinking tool.
    
    Args:
        message: User message to analyze
        
    Returns:
        True if thinking tool should be used, False otherwise
    """
    message_lower = message.lower()
    
    # Check for explicit thinking keywords
    for keyword in THINKING_KEYWORDS:
        if keyword in message_lower:
            logger.info(f"Thinking tool triggered by keyword: {keyword}")
            return True
    
    # Check for question patterns that suggest deep analysis
    analysis_patterns = [
        "como posso", "qual a melhor", "me ajude a", "preciso de uma estratégia",
        "como resolver", "qual seria", "me dê insights", "analise esta situação"
    ]
    
    for pattern in analysis_patterns:
        if pattern in message_lower:
            logger.info(f"Thinking tool triggered by analysis pattern: {pattern}")
            return True
    
    return False
