"""Intent classification engine with transformer models"""

import asyncio
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import structlog
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
import torch
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

from .config import settings
from .models import IntentResult, IntentAlternative, SessionContext

logger = structlog.get_logger(__name__)

class IntentClassifier:
    """Intent classification with contextual understanding"""
    
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.embedding_model = None
        self.classifier_pipeline = None
        self.session_contexts: Dict[str, SessionContext] = {}
        self.total_classifications = 0
        self._model_loaded = False
        
        # Predefined intents with examples
        self.intent_examples = {
            "greeting": [
                "hello", "hi", "hey", "good morning", "good afternoon", 
                "good evening", "how are you", "what's up"
            ],
            "question": [
                "what is", "how do", "where is", "when does", "why is",
                "can you tell me", "do you know", "what about"
            ],
            "request": [
                "please", "can you", "could you", "would you", "I need",
                "help me", "show me", "find me"
            ],
            "booking": [
                "book", "reserve", "schedule", "appointment", "meeting",
                "table", "flight", "hotel", "restaurant"
            ],
            "weather": [
                "weather", "temperature", "rain", "sunny", "cloudy",
                "forecast", "climate", "hot", "cold"
            ],
            "navigation": [
                "directions", "route", "how to get", "where is", "location",
                "address", "map", "navigate", "drive", "walk"
            ],
            "shopping": [
                "buy", "purchase", "order", "cart", "checkout", "price",
                "cost", "product", "item", "store"
            ],
            "entertainment": [
                "movie", "music", "song", "play", "watch", "listen",
                "show", "game", "fun", "entertainment"
            ],
            "food": [
                "restaurant", "food", "eat", "hungry", "menu", "order",
                "delivery", "takeout", "recipe", "cook"
            ],
            "travel": [
                "travel", "trip", "vacation", "flight", "hotel", "destination",
                "visit", "tourism", "journey", "adventure"
            ],
            "complaint": [
                "problem", "issue", "wrong", "error", "complaint", "broken",
                "not working", "disappointed", "frustrated", "help"
            ],
            "goodbye": [
                "bye", "goodbye", "see you", "farewell", "take care",
                "talk later", "until next time", "have a good day"
            ]
        }
    
    async def load_model(self):
        """Load the intent classification model"""
        try:
            loop = asyncio.get_event_loop()
            
            # Load embedding model for similarity-based classification
            self.embedding_model = await loop.run_in_executor(
                None,
                lambda: SentenceTransformer(settings.embedding_model)
            )
            
            # Precompute embeddings for intent examples
            self.intent_embeddings = {}
            for intent, examples in self.intent_examples.items():
                embeddings = self.embedding_model.encode(examples)
                self.intent_embeddings[intent] = np.mean(embeddings, axis=0)
            
            self._model_loaded = True
            logger.info("Intent classification model loaded successfully")
            
        except Exception as e:
            logger.error("Failed to load intent classification model", error=str(e))
            raise
    
    def is_loaded(self) -> bool:
        """Check if model is loaded"""
        return self._model_loaded
    
    async def classify(self, text: str, session_id: Optional[str] = None) -> IntentResult:
        """Classify intent from text"""
        if not self.embedding_model:
            raise RuntimeError("Model not loaded")
        
        start_time = datetime.utcnow()
        
        try:
            # Get session context
            context = self._get_or_create_session(session_id) if session_id else None
            
            # Encode input text
            text_embedding = self.embedding_model.encode([text.lower()])[0]
            
            # Calculate similarities with intent embeddings
            similarities = {}
            for intent, intent_embedding in self.intent_embeddings.items():
                similarity = cosine_similarity(
                    text_embedding.reshape(1, -1),
                    intent_embedding.reshape(1, -1)
                )[0][0]
                similarities[intent] = float(similarity)
            
            # Apply contextual boosting
            if context:
                similarities = self._apply_contextual_boosting(similarities, context, text)
            
            # Sort by confidence
            sorted_intents = sorted(similarities.items(), key=lambda x: x[1], reverse=True)
            
            # Get top intent and alternatives
            top_intent, confidence = sorted_intents[0]
            alternatives = [
                IntentAlternative(intent=intent, confidence=conf)
                for intent, conf in sorted_intents[1:settings.max_alternatives + 1]
                if conf >= settings.confidence_threshold * 0.5
            ]
            
            # Update session context
            if context:
                context.conversation_history.append(text)
                context.intent_history.append(top_intent)
                context.last_activity = datetime.utcnow()
                
                # Keep history manageable
                if len(context.conversation_history) > 10:
                    context.conversation_history = context.conversation_history[-10:]
                    context.intent_history = context.intent_history[-10:]
            
            processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.total_classifications += 1
            
            return IntentResult(
                intent=top_intent,
                confidence=confidence,
                alternatives=alternatives,
                session_id=session_id,
                processing_time_ms=processing_time
            )
            
        except Exception as e:
            logger.error("Intent classification failed", error=str(e), text=text[:100])
            # Return default intent on error
            return IntentResult(
                intent="unknown",
                confidence=0.0,
                alternatives=[],
                session_id=session_id,
                processing_time_ms=0.0
            )
    
    def _apply_contextual_boosting(
        self, 
        similarities: Dict[str, float], 
        context: SessionContext, 
        current_text: str
    ) -> Dict[str, float]:
        """Apply contextual boosting based on conversation history"""
        boosted_similarities = similarities.copy()
        
        # Boost based on recent intent history
        if context.intent_history:
            recent_intents = context.intent_history[-3:]  # Last 3 intents
            
            for intent in recent_intents:
                # Boost related intents
                related_intents = self._get_related_intents(intent)
                for related_intent in related_intents:
                    if related_intent in boosted_similarities:
                        boosted_similarities[related_intent] *= 1.1
        
        # Boost based on conversation flow patterns
        if len(context.conversation_history) >= 2:
            prev_text = context.conversation_history[-1]
            if self._is_follow_up_question(prev_text, current_text):
                if "question" in boosted_similarities:
                    boosted_similarities["question"] *= 1.2
        
        return boosted_similarities
    
    def _get_related_intents(self, intent: str) -> List[str]:
        """Get intents related to the given intent"""
        related_map = {
            "greeting": ["question", "request"],
            "question": ["request", "navigation", "weather"],
            "booking": ["travel", "food", "entertainment"],
            "shopping": ["food", "entertainment"],
            "complaint": ["request"],
            "goodbye": []
        }
        return related_map.get(intent, [])
    
    def _is_follow_up_question(self, prev_text: str, current_text: str) -> bool:
        """Check if current text is a follow-up question"""
        follow_up_indicators = [
            "what about", "and", "also", "additionally", "furthermore",
            "moreover", "besides", "in addition", "plus"
        ]
        
        current_lower = current_text.lower()
        return any(indicator in current_lower for indicator in follow_up_indicators)
    
    def _get_or_create_session(self, session_id: str) -> SessionContext:
        """Get existing session or create new one"""
        if session_id not in self.session_contexts:
            self.session_contexts[session_id] = SessionContext(
                session_id=session_id,
                last_activity=datetime.utcnow()
            )
        
        return self.session_contexts[session_id]
    
    async def cleanup_expired_sessions(self):
        """Clean up expired sessions"""
        cutoff_time = datetime.utcnow() - timedelta(seconds=settings.session_timeout)
        expired_sessions = [
            sid for sid, context in self.session_contexts.items()
            if context.last_activity < cutoff_time
        ]
        
        for session_id in expired_sessions:
            del self.session_contexts[session_id]
        
        if expired_sessions:
            logger.info("Cleaned up expired sessions", count=len(expired_sessions))
    
    def get_supported_intents(self) -> List[str]:
        """Get list of supported intents"""
        return list(self.intent_examples.keys())
    
    def get_average_confidence(self) -> float:
        """Get average confidence across classifications"""
        # This is a simplified metric - in production you'd track this properly
        return 0.82  # Placeholder
    
    async def retrain_model(self):
        """Retrain model with new data (placeholder)"""
        logger.info("Model retraining initiated")
        # In production, this would:
        # 1. Collect new training data
        # 2. Fine-tune the model
        # 3. Validate performance
        # 4. Deploy updated model
        await asyncio.sleep(1)  # Simulate training time
        logger.info("Model retraining completed")
    
    def add_training_example(self, text: str, intent: str):
        """Add new training example"""
        if intent not in self.intent_examples:
            self.intent_examples[intent] = []
        
        # Add to examples (with deduplication)
        text_lower = text.lower()
        if text_lower not in self.intent_examples[intent]:
            self.intent_examples[intent].append(text_lower)
            
            # Recompute embedding for this intent
            if self.embedding_model:
                embeddings = self.embedding_model.encode(self.intent_examples[intent])
                self.intent_embeddings[intent] = np.mean(embeddings, axis=0)
                
        logger.info("Added training example", intent=intent, text=text[:50])
