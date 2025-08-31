"""Speculative prediction engine for intent forecasting"""

import asyncio
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import structlog
from transformers import GPT2LMHeadModel, GPT2Tokenizer
import torch
from collections import defaultdict, deque

from .config import settings
from .models import SpeculativeResult, IntentResult, SessionContext

logger = structlog.get_logger(__name__)

class SpeculativeEngine:
    """Speculative intent prediction engine"""
    
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.session_contexts: Dict[str, SessionContext] = {}
        self._model_loaded = False
        
        # Intent transition patterns learned from data
        self.intent_transitions = {
            "greeting": {"question": 0.4, "request": 0.3, "booking": 0.2, "goodbye": 0.1},
            "question": {"request": 0.5, "question": 0.3, "goodbye": 0.2},
            "request": {"question": 0.3, "booking": 0.3, "complaint": 0.2, "goodbye": 0.2},
            "booking": {"request": 0.4, "question": 0.3, "complaint": 0.2, "goodbye": 0.1},
            "weather": {"navigation": 0.3, "travel": 0.3, "question": 0.2, "goodbye": 0.2},
            "navigation": {"travel": 0.4, "question": 0.3, "goodbye": 0.3},
            "shopping": {"booking": 0.3, "question": 0.3, "complaint": 0.2, "goodbye": 0.2},
            "complaint": {"request": 0.5, "question": 0.3, "goodbye": 0.2}
        }
        
        # Common completion patterns
        self.completion_patterns = {
            "greeting": [
                "how are you today?",
                "what can I help you with?",
                "nice to meet you"
            ],
            "question": [
                "about the weather?",
                "about directions?",
                "about booking?"
            ],
            "request": [
                "help me with",
                "show me how to",
                "find information about"
            ],
            "booking": [
                "a table for dinner",
                "a flight to",
                "an appointment"
            ]
        }
    
    async def load_model(self):
        """Load the speculative prediction model"""
        try:
            # For now, use rule-based predictions
            # In production, you'd load a trained model
            self._model_loaded = True
            logger.info("Speculative engine loaded successfully")
            
        except Exception as e:
            logger.error("Failed to load speculative engine", error=str(e))
            raise
    
    def is_loaded(self) -> bool:
        """Check if model is loaded"""
        return self._model_loaded
    
    async def predict_next_intents(
        self, 
        partial_text: str, 
        current_intent: IntentResult, 
        session_id: Optional[str] = None
    ) -> List[SpeculativeResult]:
        """Predict likely next intents based on partial text and context"""
        try:
            # Get session context
            context = self._get_or_create_session(session_id) if session_id else None
            
            # Generate predictions based on multiple strategies
            predictions = []
            
            # Strategy 1: Intent transition probabilities
            transition_predictions = self._predict_from_transitions(current_intent.intent, context)
            predictions.extend(transition_predictions)
            
            # Strategy 2: Text completion analysis
            completion_predictions = await self._predict_from_text_completion(partial_text, current_intent)
            predictions.extend(completion_predictions)
            
            # Strategy 3: Context-based predictions
            if context:
                context_predictions = self._predict_from_context(context, current_intent)
                predictions.extend(context_predictions)
            
            # Merge and rank predictions
            merged_predictions = self._merge_predictions(predictions)
            
            # Return top predictions
            return merged_predictions[:settings.max_speculative_intents]
            
        except Exception as e:
            logger.error("Speculative prediction failed", error=str(e))
            return []
    
    def _predict_from_transitions(
        self, 
        current_intent: str, 
        context: Optional[SessionContext]
    ) -> List[SpeculativeResult]:
        """Predict based on intent transition patterns"""
        predictions = []
        
        # Get transition probabilities for current intent
        transitions = self.intent_transitions.get(current_intent, {})
        
        for next_intent, base_probability in transitions.items():
            # Adjust probability based on context
            adjusted_probability = base_probability
            
            if context and context.intent_history:
                # Boost probability if this intent appeared recently
                recent_intents = context.intent_history[-3:]
                if next_intent in recent_intents:
                    adjusted_probability *= 0.7  # Reduce repetition
                
                # Boost based on conversation patterns
                if len(context.intent_history) >= 2:
                    prev_intent = context.intent_history[-1]
                    if self._is_common_sequence(prev_intent, current_intent, next_intent):
                        adjusted_probability *= 1.3
            
            if adjusted_probability >= settings.speculative_threshold:
                predictions.append(SpeculativeResult(
                    intent=next_intent,
                    confidence=adjusted_probability,
                    completion_text=self._generate_completion_text(next_intent),
                    trigger_words=self._get_trigger_words(next_intent),
                    estimated_completion_time_ms=self._estimate_completion_time(next_intent)
                ))
        
        return predictions
    
    async def _predict_from_text_completion(
        self, 
        partial_text: str, 
        current_intent: IntentResult
    ) -> List[SpeculativeResult]:
        """Predict based on text completion patterns"""
        predictions = []
        
        # Analyze partial text for completion cues
        text_lower = partial_text.lower().strip()
        
        # Look for incomplete phrases that suggest specific intents
        completion_cues = {
            "can you": ["request"],
            "what is": ["question"],
            "where is": ["navigation", "question"],
            "how do": ["question", "request"],
            "i need": ["request", "booking"],
            "book a": ["booking"],
            "what's the weather": ["weather"],
            "i'm looking for": ["shopping", "navigation"],
            "help me": ["request"],
            "show me": ["request", "navigation"]
        }
        
        for cue, likely_intents in completion_cues.items():
            if text_lower.endswith(cue) or cue in text_lower:
                for intent in likely_intents:
                    if intent != current_intent.intent:  # Don't predict same intent
                        predictions.append(SpeculativeResult(
                            intent=intent,
                            confidence=0.8,
                            completion_text=self._generate_completion_text(intent),
                            trigger_words=[cue],
                            estimated_completion_time_ms=500
                        ))
        
        return predictions
    
    def _predict_from_context(
        self, 
        context: SessionContext, 
        current_intent: IntentResult
    ) -> List[SpeculativeResult]:
        """Predict based on conversation context"""
        predictions = []
        
        # Analyze conversation flow
        if len(context.conversation_history) >= 2:
            recent_topics = self._extract_topics(context.conversation_history[-3:])
            
            # Predict intents related to recent topics
            topic_intent_map = {
                "food": ["booking", "navigation"],
                "travel": ["booking", "weather", "navigation"],
                "shopping": ["navigation", "question"],
                "work": ["booking", "question"],
                "weather": ["travel", "navigation"]
            }
            
            for topic in recent_topics:
                if topic in topic_intent_map:
                    for intent in topic_intent_map[topic]:
                        if intent != current_intent.intent:
                            predictions.append(SpeculativeResult(
                                intent=intent,
                                confidence=0.7,
                                completion_text=self._generate_completion_text(intent),
                                trigger_words=[topic],
                                estimated_completion_time_ms=800
                            ))
        
        return predictions
    
    def _merge_predictions(self, predictions: List[SpeculativeResult]) -> List[SpeculativeResult]:
        """Merge and deduplicate predictions"""
        intent_scores = defaultdict(list)
        
        # Group by intent
        for pred in predictions:
            intent_scores[pred.intent].append(pred)
        
        # Merge predictions for same intent
        merged = []
        for intent, preds in intent_scores.items():
            if not preds:
                continue
            
            # Take highest confidence
            best_pred = max(preds, key=lambda x: x.confidence)
            
            # Combine trigger words
            all_triggers = set()
            for pred in preds:
                all_triggers.update(pred.trigger_words)
            
            best_pred.trigger_words = list(all_triggers)
            merged.append(best_pred)
        
        # Sort by confidence
        merged.sort(key=lambda x: x.confidence, reverse=True)
        
        return merged
    
    def _generate_completion_text(self, intent: str) -> str:
        """Generate completion text for intent"""
        patterns = self.completion_patterns.get(intent, [""])
        if patterns:
            return np.random.choice(patterns)
        return f"complete {intent} request"
    
    def _get_trigger_words(self, intent: str) -> List[str]:
        """Get trigger words for intent"""
        trigger_map = {
            "question": ["what", "how", "where", "when", "why"],
            "request": ["please", "can", "help", "need"],
            "booking": ["book", "reserve", "schedule"],
            "navigation": ["directions", "route", "location"],
            "weather": ["weather", "temperature", "forecast"],
            "shopping": ["buy", "purchase", "store"],
            "complaint": ["problem", "issue", "wrong"]
        }
        return trigger_map.get(intent, [])
    
    def _estimate_completion_time(self, intent: str) -> int:
        """Estimate time to complete intent (in ms)"""
        time_estimates = {
            "greeting": 200,
            "question": 800,
            "request": 1000,
            "booking": 1500,
            "navigation": 1200,
            "weather": 600,
            "shopping": 1000,
            "complaint": 1200,
            "goodbye": 300
        }
        return time_estimates.get(intent, 800)
    
    def _is_common_sequence(self, prev_intent: str, current_intent: str, next_intent: str) -> bool:
        """Check if this is a common intent sequence"""
        common_sequences = [
            ("greeting", "question", "request"),
            ("question", "request", "booking"),
            ("weather", "navigation", "travel"),
            ("shopping", "question", "booking")
        ]
        
        return (prev_intent, current_intent, next_intent) in common_sequences
    
    def _extract_topics(self, texts: List[str]) -> List[str]:
        """Extract topics from conversation history"""
        topics = []
        topic_keywords = {
            "food": ["restaurant", "food", "eat", "hungry", "menu"],
            "travel": ["travel", "trip", "flight", "hotel", "vacation"],
            "shopping": ["buy", "store", "shop", "purchase", "product"],
            "work": ["work", "office", "meeting", "job", "business"],
            "weather": ["weather", "rain", "sunny", "temperature", "forecast"]
        }
        
        combined_text = " ".join(texts).lower()
        
        for topic, keywords in topic_keywords.items():
            if any(keyword in combined_text for keyword in keywords):
                topics.append(topic)
        
        return topics
    
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
            logger.info("Cleaned up expired speculative sessions", count=len(expired_sessions))
    
    def update_transition_probabilities(self, from_intent: str, to_intent: str):
        """Update transition probabilities based on actual user behavior"""
        if from_intent not in self.intent_transitions:
            self.intent_transitions[from_intent] = {}
        
        # Simple learning rate
        learning_rate = 0.1
        current_prob = self.intent_transitions[from_intent].get(to_intent, 0.0)
        
        # Increase probability for this transition
        new_prob = current_prob + learning_rate * (1.0 - current_prob)
        self.intent_transitions[from_intent][to_intent] = new_prob
        
        # Normalize probabilities
        total_prob = sum(self.intent_transitions[from_intent].values())
        if total_prob > 1.0:
            for intent in self.intent_transitions[from_intent]:
                self.intent_transitions[from_intent][intent] /= total_prob
