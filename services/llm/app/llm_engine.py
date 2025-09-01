"""LLM engine with multiple provider support"""

import asyncio
import json
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
import structlog
import openai
import anthropic
import google.generativeai as genai
import httpx

from .config import settings
from .models import GenerationResponse, ToolCall, ChatMessage, ModelInfo

logger = structlog.get_logger(__name__)

class LLMEngine:
    """Multi-provider LLM engine"""
    
    def __init__(self):
        self.providers = {}
        self.tokenizers = {}
        self.active_sessions = {}
        self.total_generations = 0
        self.generation_times = []
        self.total_tokens_generated = 0
        self.cache = {}
        self.cache_hits = 0
        
    async def initialize(self):
        """Initialize LLM providers"""
        try:
            # Initialize OpenAI
            if settings.openai_api_key:
                self.providers["openai"] = openai.AsyncOpenAI(
                    api_key=settings.openai_api_key
                )
                logger.info("OpenAI provider initialized")
            
            # Initialize Anthropic
            if settings.anthropic_api_key:
                self.providers["anthropic"] = anthropic.AsyncAnthropic(
                    api_key=settings.anthropic_api_key
                )
                logger.info("Anthropic provider initialized")
            
            # Initialize Google Gemini
            if settings.google_api_key:
                genai.configure(api_key=settings.google_api_key)
                self.providers["google"] = genai
                logger.info("Google Gemini provider initialized")
            
            # Initialize local models if enabled
            if settings.enable_local_models:
                await self._initialize_local_models()
            
            logger.info("LLM engine initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize LLM engine", error=str(e))
            raise
    
    async def _initialize_local_models(self):
        """Initialize local models"""
        try:
            # Lazy imports to avoid heavy dependencies unless local models are enabled
            from transformers import AutoTokenizer, AutoModelForCausalLM
            import torch

            loop = asyncio.get_event_loop()
            
            # Load tokenizer
            self.tokenizers["local"] = await loop.run_in_executor(
                None,
                lambda: AutoTokenizer.from_pretrained(settings.local_model_name)
            )
            
            # Load model
            model = await loop.run_in_executor(
                None,
                lambda: AutoModelForCausalLM.from_pretrained(
                    settings.local_model_name,
                    torch_dtype=torch.float16,
                    device_map="auto"
                )
            )
            
            self.providers["local"] = model
            logger.info("Local model initialized", model=settings.local_model_name)
            
        except Exception as e:
            logger.error("Failed to initialize local models", error=str(e))
    
    async def generate(
        self,
        prompt: str,
        context: str = "",
        entities: List[Dict[str, Any]] = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
        tools: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None,
        model: str = "default"
    ) -> GenerationResponse:
        """Generate text using LLM"""
        start_time = datetime.utcnow()
        
        try:
            # Validate input
            if len(prompt) > settings.max_prompt_length:
                raise ValueError(f"Prompt too long: {len(prompt)} characters")
            
            # Check cache
            cache_key = self._generate_cache_key(prompt, context, max_tokens, temperature, model)
            if cache_key in self.cache:
                cached_result = self.cache[cache_key]
                if datetime.utcnow() - cached_result["timestamp"] < timedelta(hours=settings.cache_ttl_hours):
                    self.cache_hits += 1
                    return cached_result["response"]
            
            # Select provider and model
            provider, model_name = self._select_provider_and_model(model)
            
            # Build full prompt
            full_prompt = self._build_prompt(prompt, context, entities or [])
            
            # Generate response
            response = await self._generate_with_provider(
                provider=provider,
                model=model_name,
                prompt=full_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                tools=tools
            )
            
            # Calculate metrics
            generation_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Create response object
            result = GenerationResponse(
                text=response["text"],
                model=model_name,
                tokens_used=response.get("tokens_used", 0),
                generation_time_ms=generation_time,
                confidence=response.get("confidence", 0.8),
                tool_calls=response.get("tool_calls", []),
                session_id=session_id
            )
            
            # Cache result
            self.cache[cache_key] = {
                "response": result,
                "timestamp": datetime.utcnow()
            }
            
            # Update metrics
            self.total_generations += 1
            self.generation_times.append(generation_time)
            self.total_tokens_generated += result.tokens_used
            
            if len(self.generation_times) > 1000:
                self.generation_times = self.generation_times[-1000:]
            
            logger.info("Text generation completed",
                       model=model_name,
                       tokens=result.tokens_used,
                       generation_time_ms=generation_time)
            
            return result
            
        except Exception as e:
            logger.error("Text generation failed", error=str(e))
            raise
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "default",
        temperature: float = 0.7,
        max_tokens: int = 500,
        tools: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Chat completion with conversation history"""
        try:
            provider, model_name = self._select_provider_and_model(model)
            
            if provider == "openai":
                return await self._openai_chat_completion(
                    messages, model_name, temperature, max_tokens, tools
                )
            elif provider == "anthropic":
                return await self._anthropic_chat_completion(
                    messages, model_name, temperature, max_tokens, tools
                )
            else:
                # Convert to single prompt for other providers
                prompt = self._messages_to_prompt(messages)
                response = await self.generate(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    tools=tools,
                    session_id=session_id,
                    model=model
                )
                
                return {
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": response.text
                        }
                    }],
                    "usage": {
                        "total_tokens": response.tokens_used
                    }
                }
                
        except Exception as e:
            logger.error("Chat completion failed", error=str(e))
            raise
    
    async def _generate_with_provider(
        self,
        provider: str,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Generate with specific provider"""
        
        try:
            if provider == "openai":
                return await self._generate_openai(model, prompt, max_tokens, temperature, tools)
            elif provider == "anthropic":
                return await self._generate_anthropic(model, prompt, max_tokens, temperature, tools)
            elif provider == "google":
                return await self._generate_google(model, prompt, max_tokens, temperature, tools)
            elif provider == "local":
                return await self._generate_local(model, prompt, max_tokens, temperature)
            else:
                raise ValueError(f"Unknown provider: {provider}")
        except Exception as e:
            logger.warning(f"Provider {provider} failed, using fallback response", error=str(e))
            return await self._generate_fallback(prompt, max_tokens)
    
    async def _generate_openai(
        self,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Generate with OpenAI"""
        try:
            client = self.providers["openai"]
            
            messages = [{"role": "user", "content": prompt}]
            
            kwargs = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            
            if tools and settings.enable_tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            
            response = await client.chat.completions.create(**kwargs)
            
            message = response.choices[0].message
            
            # Extract tool calls if any
            tool_calls = []
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tool_call in message.tool_calls:
                    tool_calls.append(ToolCall(
                        name=tool_call.function.name,
                        arguments=json.loads(tool_call.function.arguments),
                        call_id=tool_call.id
                    ))
            
            return {
                "text": message.content or "",
                "tokens_used": response.usage.total_tokens,
                "confidence": 0.9,
                "tool_calls": tool_calls
            }
            
        except Exception as e:
            logger.error("OpenAI generation failed", error=str(e))
            raise
    
    async def _generate_anthropic(
        self,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Generate with Anthropic"""
        try:
            client = self.providers["anthropic"]
            
            kwargs = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}]
            }
            
            if tools and settings.enable_tools:
                kwargs["tools"] = tools
            
            response = await client.messages.create(**kwargs)
            
            # Extract tool calls if any
            tool_calls = []
            text_content = ""
            
            for content in response.content:
                if content.type == "text":
                    text_content += content.text
                elif content.type == "tool_use":
                    tool_calls.append(ToolCall(
                        name=content.name,
                        arguments=content.input,
                        call_id=content.id
                    ))
            
            return {
                "text": text_content,
                "tokens_used": response.usage.input_tokens + response.usage.output_tokens,
                "confidence": 0.9,
                "tool_calls": tool_calls
            }
            
        except Exception as e:
            logger.error("Anthropic generation failed", error=str(e))
            raise
    
    async def _generate_google(
        self,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Generate with Google Gemini"""
        try:
            # Initialize model
            gemini_model = genai.GenerativeModel(model)
            
            # Configure generation
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
                top_p=settings.top_p
            )
            
            # Generate response
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: gemini_model.generate_content(
                    prompt,
                    generation_config=generation_config
                )
            )
            
            # Extract content
            text_content = response.text if response.text else ""
            
            # Estimate token usage (Gemini doesn't provide exact counts)
            estimated_tokens = len(text_content.split()) * 1.3  # Rough estimate
            
            return {
                "text": text_content,
                "tokens_used": int(estimated_tokens),
                "confidence": 0.9,
                "tool_calls": []  # Tool calling not implemented for Gemini yet
            }
            
        except Exception as e:
            logger.error("Google Gemini generation failed", error=str(e))
            raise
    
    async def _generate_fallback(
        self,
        prompt: str,
        max_tokens: int
    ) -> Dict[str, Any]:
        """Generate fallback response when all providers fail"""
        
        # Simple rule-based responses for common scenarios
        prompt_lower = prompt.lower()
        
        if "document" in prompt_lower and "upload" in prompt_lower:
            response_text = "Hello! I see you've uploaded a document. I'm excited to help you learn from this material. Let me analyze it and then we can start our conversation. What would you like to explore about this content?"
        elif "hello" in prompt_lower or "hi" in prompt_lower:
            response_text = "Hello! I'm your AI assistant. How can I help you today?"
        elif "question" in prompt_lower or "?" in prompt:
            response_text = "That's an interesting question! Based on the context provided, I can help you explore this topic further. Could you tell me more about what specific aspect you'd like to focus on?"
        elif "explain" in prompt_lower or "tell me" in prompt_lower:
            response_text = "I'd be happy to explain that for you! From what I understand, this is an important topic that we can explore together. What particular aspect would you like me to focus on?"
        else:
            response_text = "I understand you're looking for information about this topic. While I'm currently running in fallback mode, I can still help you explore the content you've shared. What specific questions do you have?"
        
        # Estimate token usage
        estimated_tokens = len(response_text.split()) * 1.3
        
        return {
            "text": response_text,
            "tokens_used": int(estimated_tokens),
            "confidence": 0.7,
            "tool_calls": []
        }
    
    async def _generate_local(
        self,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float
    ) -> Dict[str, Any]:
        """Generate with local model"""
        try:
            # Ensure torch is available when generating locally
            import torch
            tokenizer = self.tokenizers["local"]
            model_obj = self.providers["local"]
            
            loop = asyncio.get_event_loop()
            
            def generate():
                inputs = tokenizer.encode(prompt, return_tensors="pt")
                
                with torch.no_grad():
                    outputs = model_obj.generate(
                        inputs,
                        max_new_tokens=max_tokens,
                        temperature=temperature,
                        do_sample=True,
                        pad_token_id=tokenizer.eos_token_id
                    )
                
                response = tokenizer.decode(outputs[0], skip_special_tokens=True)
                # Remove the original prompt from response
                response = response[len(prompt):].strip()
                
                return response
            
            text = await loop.run_in_executor(None, generate)
            
            return {
                "text": text,
                "tokens_used": len(tokenizer.encode(text)),
                "confidence": 0.8,
                "tool_calls": []
            }
            
        except Exception as e:
            logger.error("Local model generation failed", error=str(e))
            raise
    
    async def _openai_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """OpenAI chat completion"""
        client = self.providers["openai"]
        
        kwargs = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        
        if tools and settings.enable_tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        
        response = await client.chat.completions.create(**kwargs)
        return response.model_dump()
    
    async def _anthropic_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Anthropic chat completion"""
        client = self.providers["anthropic"]
        
        # Convert messages format
        anthropic_messages = []
        for msg in messages:
            if msg["role"] != "system":
                anthropic_messages.append(msg)
        
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": anthropic_messages
        }
        
        if tools and settings.enable_tools:
            kwargs["tools"] = tools
        
        response = await client.messages.create(**kwargs)
        
        # Convert to OpenAI format
        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": response.content[0].text if response.content else ""
                }
            }],
            "usage": {
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens
            }
        }
    
    def _select_provider_and_model(self, model: str) -> tuple[str, str]:
        """Select provider and model"""
        if model == "default":
            model = settings.default_model
        
        # Map models to providers
        if model.startswith("gpt"):
            return "openai", model
        elif model.startswith("claude"):
            return "anthropic", model
        elif model.startswith("gemini") or model in ["gemini-1.5-flash", "gemini-2.0-flash"]:
            return "google", model
        elif model in ["llama", "mistral", "codellama"]:
            return "local", model
        else:
            # Default to configured provider
            return settings.default_provider, model
    
    def _build_prompt(self, prompt: str, context: str, entities: List[Dict[str, Any]]) -> str:
        """Build full prompt with context and entities"""
        parts = []
        
        if context:
            parts.append(f"Context: {context}")
        
        if entities:
            entity_text = ", ".join([f"{e.get('label', '')}: {e.get('text', '')}" for e in entities])
            parts.append(f"Entities: {entity_text}")
        
        parts.append(f"Request: {prompt}")
        
        return "\n\n".join(parts)
    
    def _messages_to_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Convert messages to single prompt"""
        prompt_parts = []
        
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            
            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
        
        return "\n\n".join(prompt_parts)
    
    def _generate_cache_key(
        self,
        prompt: str,
        context: str,
        max_tokens: int,
        temperature: float,
        model: str
    ) -> str:
        """Generate cache key"""
        import hashlib
        
        key_string = f"{prompt}|{context}|{max_tokens}|{temperature}|{model}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    async def get_available_models(self) -> List[ModelInfo]:
        """Get available models"""
        models = []
        
        # OpenAI models
        if "openai" in self.providers:
            models.extend([
                ModelInfo(
                    model_id="gpt-4",
                    name="GPT-4",
                    provider="openai",
                    max_tokens=8192,
                    supports_tools=True,
                    supports_streaming=True,
                    cost_per_token=0.00003
                ),
                ModelInfo(
                    model_id="gpt-3.5-turbo",
                    name="GPT-3.5 Turbo",
                    provider="openai",
                    max_tokens=4096,
                    supports_tools=True,
                    supports_streaming=True,
                    cost_per_token=0.000002
                )
            ])
        
        # Anthropic models
        if "anthropic" in self.providers:
            models.extend([
                ModelInfo(
                    model_id="claude-3-opus-20240229",
                    name="Claude 3 Opus",
                    provider="anthropic",
                    max_tokens=4096,
                    supports_tools=True,
                    supports_streaming=True,
                    cost_per_token=0.000015
                ),
                ModelInfo(
                    model_id="claude-3-sonnet-20240229",
                    name="Claude 3 Sonnet",
                    provider="anthropic",
                    max_tokens=4096,
                    supports_tools=True,
                    supports_streaming=True,
                    cost_per_token=0.000003
                )
            ])
        
        # Local models
        if "local" in self.providers:
            models.append(ModelInfo(
                model_id=settings.local_model_name,
                name=settings.local_model_name,
                provider="local",
                max_tokens=2048,
                supports_tools=False,
                supports_streaming=False,
                cost_per_token=0.0
            ))
        
        return models
    
    async def health_check(self) -> Dict[str, str]:
        """Check health of LLM providers - lightweight check without API calls"""
        health = {}
        
        for provider_name, provider in self.providers.items():
            try:
                if provider_name == "openai":
                    # Check if client is initialized and has API key
                    health[provider_name] = "ready" if provider and hasattr(provider, 'api_key') else "not_configured"
                elif provider_name == "anthropic":
                    # Check if client is initialized
                    health[provider_name] = "ready" if provider else "not_configured"
                elif provider_name == "google":
                    # Check if Google client is configured
                    health[provider_name] = "ready" if provider else "not_configured"
                elif provider_name == "local":
                    # Check if model is loaded
                    health[provider_name] = "ready" if provider else "not_loaded"
                else:
                    health[provider_name] = "unknown"
            except Exception as e:
                health[provider_name] = f"error: {str(e)}"
        
        return health
    
    def get_average_generation_time(self) -> float:
        """Get average generation time"""
        if not self.generation_times:
            return 0.0
        return sum(self.generation_times) / len(self.generation_times)
    
    def get_cache_hit_rate(self) -> float:
        """Get cache hit rate"""
        if self.total_generations == 0:
            return 0.0
        return self.cache_hits / self.total_generations
    
    def get_cache_size(self) -> int:
        """Get cache size"""
        return len(self.cache)
    
    async def clear_cache(self):
        """Clear cache"""
        self.cache.clear()
        self.cache_hits = 0
        logger.info("LLM cache cleared")
