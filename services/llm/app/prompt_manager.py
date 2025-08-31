"""Prompt management and templates for LLM service"""

import asyncio
from typing import Dict, Any, List, Optional
import structlog
from jinja2 import Template

from .config import settings

logger = structlog.get_logger(__name__)

class PromptManager:
    """Manage prompts and templates for different use cases"""
    
    def __init__(self):
        self.templates = {}
        
    async def load_templates(self):
        """Load prompt templates"""
        try:
            # Intent analysis template
            self.templates["intent_analysis"] = Template("""
You are an AI assistant analyzing user intent and context. 

User Input: "{{ text }}"
{% if context %}
Context: {{ context }}
{% endif %}
{% if entities %}
Entities: {% for entity in entities %}{{ entity.label }}: {{ entity.text }}{% if not loop.last %}, {% endif %}{% endfor %}
{% endif %}

Analyze the user's intent and provide:
1. Primary intent (greeting, question, request, booking, complaint, etc.)
2. Confidence level (0.0-1.0)
3. Key entities and their significance
4. Suggested response approach
5. Any follow-up questions needed

Respond in JSON format with clear, actionable insights.
""")
            
            # Summarization template
            self.templates["summarization"] = Template("""
Please summarize the following text in a {{ style }} manner, keeping it under {{ max_length }} characters:

{{ text }}

Focus on the key points and main ideas. Make the summary clear and informative.
""")
            
            # Translation template
            self.templates["translation"] = Template("""
Translate the following text from {{ source_language }} to {{ target_language }}:

{{ text }}

{% if preserve_formatting %}
Preserve the original formatting, structure, and any special characters.
{% endif %}

Provide only the translation without additional commentary.
""")
            
            # Conversation template
            self.templates["conversation"] = Template("""
You are a helpful, knowledgeable AI assistant. You provide accurate, relevant, and engaging responses.

{% if context %}
Context: {{ context }}
{% endif %}

{% if entities %}
Relevant entities: {% for entity in entities %}{{ entity.label }}: {{ entity.text }}{% if not loop.last %}, {% endif %}{% endfor %}
{% endif %}

User: {{ prompt }}

Respond naturally and helpfully. If you need additional information, ask clarifying questions.
""")
            
            # Tool calling template
            self.templates["tool_calling"] = Template("""
You are an AI assistant with access to various tools. Analyze the user's request and determine if any tools should be used.

Available tools:
{% for tool in tools %}
- {{ tool.name }}: {{ tool.description }}
{% endfor %}

User request: {{ prompt }}
{% if context %}
Context: {{ context }}
{% endif %}

If tools are needed, call them appropriately. Otherwise, provide a direct response.
""")
            
            # Code generation template
            self.templates["code_generation"] = Template("""
You are an expert programmer. Generate clean, well-documented code based on the user's requirements.

Requirements: {{ prompt }}
{% if language %}
Programming language: {{ language }}
{% endif %}
{% if framework %}
Framework/Library: {{ framework }}
{% endif %}

Provide:
1. Clean, readable code
2. Appropriate comments
3. Error handling where needed
4. Brief explanation of the approach
""")
            
            # Question answering template
            self.templates["question_answering"] = Template("""
Answer the following question accurately and comprehensively:

Question: {{ question }}
{% if context %}
Context: {{ context }}
{% endif %}
{% if knowledge_base %}
Relevant information: {{ knowledge_base }}
{% endif %}

Provide a clear, well-structured answer. If you're uncertain about any aspect, indicate that clearly.
""")
            
            logger.info("Prompt templates loaded", count=len(self.templates))
            
        except Exception as e:
            logger.error("Failed to load prompt templates", error=str(e))
            raise
    
    async def get_intent_analysis_prompt(
        self,
        text: str,
        context: Optional[str] = None,
        entities: List[Dict[str, Any]] = None
    ) -> str:
        """Get intent analysis prompt"""
        template = self.templates["intent_analysis"]
        return template.render(
            text=text,
            context=context,
            entities=entities or []
        )
    
    async def get_summarization_prompt(
        self,
        text: str,
        max_length: int = 200,
        style: str = "concise"
    ) -> str:
        """Get summarization prompt"""
        template = self.templates["summarization"]
        return template.render(
            text=text,
            max_length=max_length,
            style=style
        )
    
    async def get_translation_prompt(
        self,
        text: str,
        source_language: str,
        target_language: str,
        preserve_formatting: bool = True
    ) -> str:
        """Get translation prompt"""
        template = self.templates["translation"]
        return template.render(
            text=text,
            source_language=source_language,
            target_language=target_language,
            preserve_formatting=preserve_formatting
        )
    
    async def get_conversation_prompt(
        self,
        prompt: str,
        context: Optional[str] = None,
        entities: List[Dict[str, Any]] = None
    ) -> str:
        """Get conversation prompt"""
        template = self.templates["conversation"]
        return template.render(
            prompt=prompt,
            context=context,
            entities=entities or []
        )
    
    async def get_tool_calling_prompt(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        context: Optional[str] = None
    ) -> str:
        """Get tool calling prompt"""
        template = self.templates["tool_calling"]
        return template.render(
            prompt=prompt,
            tools=tools,
            context=context
        )
    
    async def get_code_generation_prompt(
        self,
        prompt: str,
        language: Optional[str] = None,
        framework: Optional[str] = None
    ) -> str:
        """Get code generation prompt"""
        template = self.templates["code_generation"]
        return template.render(
            prompt=prompt,
            language=language,
            framework=framework
        )
    
    async def get_question_answering_prompt(
        self,
        question: str,
        context: Optional[str] = None,
        knowledge_base: Optional[str] = None
    ) -> str:
        """Get question answering prompt"""
        template = self.templates["question_answering"]
        return template.render(
            question=question,
            context=context,
            knowledge_base=knowledge_base
        )
    
    async def create_custom_prompt(
        self,
        template_string: str,
        variables: Dict[str, Any]
    ) -> str:
        """Create custom prompt from template string"""
        try:
            template = Template(template_string)
            return template.render(**variables)
        except Exception as e:
            logger.error("Custom prompt creation failed", error=str(e))
            raise
    
    def get_available_templates(self) -> List[str]:
        """Get list of available templates"""
        return list(self.templates.keys())
