#!/usr/bin/env python3
"""
⚠️ Guardrails para filtrar conteúdo inadequado para ambiente profissional
"""

from pydantic import BaseModel
from agents import (
    Agent,
    GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered,
    RunContextWrapper,
    Runner,
    TResponseInputItem,
    input_guardrail,
)
from typing import Union


class ProfessionalContentOutput(BaseModel):
    """
   Modelo estruturado para análise de conteúdo profissional
    
    Define o formato de resposta do agente guardrail para garantir
    análises consistentes e estruturadas do conteúdo.
    """
    is_inappropriate: bool  # True se conteúdo for inadequado
    category: str  # "sexual", "violence", "harassment", "personal", "off_topic", "safe"
    reasoning: str  # Explicação da decisão
    confidence_score: float  # Nível de confiança (0.0 a 1.0)


#⚠️Agente especializado em detectar conteúdo inadequado para ambiente corporativo
# CRÍTICO: Este agente é a primeira linha de defesa contra conteúdo inadequado!
guardrail_agent = Agent(
    name="Guardrail",
    instructions="""
    VOCÊ É UM FILTRO DE SEGURANÇA CRÍTICO para ambiente corporativo profissional.
    
   MISSÃO: Analise se a mensagem contém conteúdo INADEQUADO para um ambiente de trabalho:
    
    ❌ BLOQUEAR RIGOROSAMENTE:
    - Conteúdo sexual, erótico ou pornográfico
    - Violência, ameaças ou discurso de ódio
    - Assédio, bullying ou discriminação
    - Assuntos muito pessoais (relacionamentos íntimos, problemas familiares)
    - Tópicos completamente fora do contexto profissional (receitas, fofocas, entretenimento)
    - Linguagem ofensiva ou palavrões
    - Piadas inadequadas ou humor inapropriado
    - Referências a drogas, álcool ou substâncias
    - Discussões políticas ou religiosas controversas
    
    ✅ PERMITIR:
    - Perguntas sobre trabalho, projetos, tarefas
    - Discussões técnicas e profissionais
    - Solicitações de ferramentas (Asana, Gmail, Calendar, etc.)
    - Conversas cordiais e respeitosas, incluindo saudações simples como 'oi', 'olá', 'bom dia'
    - Dúvidas sobre processos e procedimentos
    - Colaboração e comunicação de equipe
    - Mensagens curtas ou vazias (trate como seguras se não houver conteúdo inadequado)
    
   Seja rigoroso mas justo. Considere o contexto profissional brasileiro.
   PARA MENSAGENS CURTAS, SAUDAÇÕES OU VAZIAS: Sempre defina is_inappropriate como False, category como 'safe', confidence_score como 0.0 e reasoning como 'Mensagem curta ou saudação neutra - considerada segura'.
   Somente defina is_inappropriate como True se houver conteúdo EXPLICITAMENTE inadequado, independentemente do comprimento.
EM CASO DE DÚVIDA, PREFIRA PERMITIR se for mensagem curta ou saudação, mas BLOQUEIE conteúdo claramente inadequado!
    """,

    output_type=ProfessionalContentOutput,
)


@input_guardrail
async def professional_content_guardrail(
    ctx: RunContextWrapper[None], 
    agent: Agent, 
    input: Union[str, list[TResponseInputItem]]
) -> GuardrailFunctionOutput:
    """
   ⚠️ Guardrail de entrada para filtrar conteúdo inadequado
    
    Args:
        ctx: Contexto de execução
        agent: Agente que receberá o input
        input: Mensagem do usuário para análise
        
    Returns:
        GuardrailFunctionOutput com resultado da análise
        
    Raises:
        InputGuardrailTripwireTriggered: Se conteúdo inadequado for detectado
    """
    
    #Converte input para string se necessário (suporta múltiplos formatos)
    if isinstance(input, list):
        # Extrai texto de mensagens complexas (texto, imagens, etc.)
        text_content = ""
        for item in input:
            if hasattr(item, 'text'):
                text_content += item.text + " "
            elif isinstance(item, str):
                text_content += item + " "
        input_text = text_content.strip()
    else:
        input_text = str(input)
    
    # CRÍTICO: Executa análise com o agente guardrail especializado
    result = await Runner.run(
        guardrail_agent, 
        f"Analise esta mensagem para ambiente profissional: {input_text}",
        context=ctx.context
    )
    
    analysis = result.final_output
    
    # Log detalhado da análise para debugging e auditoria
    print(f"⚠️ Guardrail: Inadequado: {analysis.is_inappropriate} | Categoria: {analysis.category} | Confiança: {analysis.confidence_score} | Razão: {analysis.reasoning}")
    # CRÍTICO: Tripwire acionado apenas com alta confiança (>0.7)
    return GuardrailFunctionOutput(
        output_info=analysis,
        tripwire_triggered=analysis.is_inappropriate and analysis.confidence_score > 0.7
    )


def get_inappropriate_content_response(category: str) -> str:
    """
   ⚠️Retorna mensagem educativa baseada no tipo de conteúdo inadequado
    
    Fornece feedback específico e construtivo para cada categoria de conteúdo
    inadequado, ajudando o usuário a entender os limites profissionais.
    
    Args:
        category: Categoria do conteúdo inadequado detectado
        
    Returns:
        Mensagem de resposta educativa para o usuário
        
    ⚠️ CRÍTICO: Mensagens devem ser respeitosas mas firmes!
    """
    
    #⚠️Respostas categorizadas para diferentes tipos de conteúdo inadequado
    responses = {
        "sexual": "⚠️ Esta mensagem contém conteúdo inadequado para o ambiente profissional. Por favor, mantenha as conversas focadas em tópicos de trabalho.",
        "violence": "⚠️ Não posso processar mensagens com conteúdo violento ou ameaçador. Vamos manter um ambiente respeitoso.",
        "harassment": "⚠️ Este tipo de linguagem não é apropriada para o ambiente de trabalho. Por favor, seja respeitoso.",
        "personal": "⚠️ Este assunto parece muito pessoal para o contexto profissional. Como posso ajudar com questões de trabalho?",
        "off_topic": "⚠️ Vamos focar em tópicos relacionados ao trabalho. Como posso ajudar com suas tarefas profissionais?",
        "default": "⚠️ Esta mensagem não é apropriada para o ambiente profissional. Por favor, reformule sua pergunta focando em tópicos de trabalho."
    }
    
    return responses.get(category, responses["default"])