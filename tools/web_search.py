#!/usr/bin/env python3

import logging
from agents import WebSearchTool as OpenAIWebSearchTool

logger = logging.getLogger(__name__)


class WebSearchTool:

    def __init__(self, search_context_size: str = "medium"):
        self.tool = OpenAIWebSearchTool(search_context_size=search_context_size)
        logger.info(f"WebSearchTool inicializada com tamanho de contexto: {search_context_size}")
        return self.tool
