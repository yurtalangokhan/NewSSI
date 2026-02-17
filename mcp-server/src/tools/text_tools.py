"""
Text Processing Tools Category.
Provides tools for text analysis and transformation.
"""

import json
from typing import Any

from ..core.base import BaseToolCategory


class TextTools(BaseToolCategory):
    """Text processing and analysis tools."""
    
    @property
    def name(self) -> str:
        return "text_processing"
    
    @property
    def description(self) -> str:
        return "Text analysis and transformation utilities"
    
    @property
    def label(self) -> str:
        return "Text Processing"
    
    def register_tools(self, mcp: Any) -> None:
        """Register all text processing tools with MCP."""
        
        @mcp.tool()
        def text_analysis(text: str) -> str:
            """
            Analyze text and return statistics.
            
            Args:
                text: The text to analyze
            
            Returns:
                Text statistics including word count, character count, etc.
            """
            words = text.split()
            sentences = text.replace("!", ".").replace("?", ".").split(".")
            sentences = [s.strip() for s in sentences if s.strip()]
            
            stats = {
                "character_count": len(text),
                "word_count": len(words),
                "sentence_count": len(sentences),
                "average_word_length": round(sum(len(w) for w in words) / len(words), 2) if words else 0,
                "average_sentence_length": round(len(words) / len(sentences), 2) if sentences else 0,
            }
            
            return json.dumps(stats, indent=2)
        
        @mcp.tool()
        def translate_text(text: str, target_language: str = "en") -> str:
            """
            Placeholder for text translation.
            Note: This is a demo tool. In production, connect to a translation API.
            
            Args:
                text: Text to translate
                target_language: Target language code (e.g., 'en', 'tr', 'de')
            
            Returns:
                Translation note (actual translation requires API integration)
            """
            return f"Translation to '{target_language}' requested for: '{text[:100]}...'\n\nNote: Connect to a translation API (Google Translate, DeepL, etc.) for actual translation."
