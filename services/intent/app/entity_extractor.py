"""Entity extraction engine with NER models"""

import asyncio
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import structlog
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
import spacy
from spacy import displacy

from .config import settings
from .models import Entity, EntityResult

logger = structlog.get_logger(__name__)

class EntityExtractor:
    """Named Entity Recognition and extraction"""
    
    def __init__(self):
        self.nlp = None
        self.ner_pipeline = None
        self._model_loaded = False
        
        # Custom entity patterns
        self.custom_patterns = {
            "phone": r'\b(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b',
            "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "url": r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
            "time": r'\b(?:[01]?[0-9]|2[0-3]):[0-5][0-9](?:\s?[AaPp][Mm])?\b',
            "date": r'\b(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+)?(?:[0-3]?[0-9](?:st|nd|rd|th)?,?\s+)?(?:19|20)\d{2}\b',
            "money": r'\$\s?(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d{2})?',
            "percentage": r'\b\d+(?:\.\d+)?%\b'
        }
    
    async def load_model(self):
        """Load the NER model"""
        try:
            loop = asyncio.get_event_loop()
            
            # Load spaCy model
            self.nlp = await loop.run_in_executor(
                None,
                lambda: spacy.load("en_core_web_sm")
            )
            
            # Load transformer-based NER pipeline
            self.ner_pipeline = await loop.run_in_executor(
                None,
                lambda: pipeline(
                    "ner",
                    model=settings.entity_model,
                    tokenizer=settings.entity_model,
                    aggregation_strategy="simple"
                )
            )
            
            self._model_loaded = True
            logger.info("Entity extraction model loaded successfully")
            
        except Exception as e:
            logger.error("Failed to load entity extraction model", error=str(e))
            # Fallback to basic regex-based extraction
            self._model_loaded = True
            logger.warning("Using fallback regex-based entity extraction")
    
    def is_loaded(self) -> bool:
        """Check if model is loaded"""
        return self._model_loaded
    
    async def extract(self, text: str) -> EntityResult:
        """Extract entities from text"""
        start_time = datetime.utcnow()
        entities = []
        
        try:
            # Extract using spaCy if available
            if self.nlp:
                entities.extend(await self._extract_with_spacy(text))
            
            # Extract using transformer model if available
            if self.ner_pipeline:
                entities.extend(await self._extract_with_transformers(text))
            
            # Extract custom patterns
            entities.extend(self._extract_custom_patterns(text))
            
            # Remove duplicates and merge overlapping entities
            entities = self._merge_entities(entities)
            
            processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            return EntityResult(
                entities=entities,
                processing_time_ms=processing_time
            )
            
        except Exception as e:
            logger.error("Entity extraction failed", error=str(e), text=text[:100])
            return EntityResult(entities=[], processing_time_ms=0.0)
    
    async def _extract_with_spacy(self, text: str) -> List[Entity]:
        """Extract entities using spaCy"""
        entities = []
        
        try:
            loop = asyncio.get_event_loop()
            doc = await loop.run_in_executor(None, self.nlp, text)
            
            for ent in doc.ents:
                entities.append(Entity(
                    text=ent.text,
                    label=ent.label_,
                    confidence=0.9,  # spaCy doesn't provide confidence scores
                    start=ent.start_char,
                    end=ent.end_char
                ))
                
        except Exception as e:
            logger.error("spaCy entity extraction failed", error=str(e))
        
        return entities
    
    async def _extract_with_transformers(self, text: str) -> List[Entity]:
        """Extract entities using transformer model"""
        entities = []
        
        try:
            loop = asyncio.get_event_loop()
            ner_results = await loop.run_in_executor(None, self.ner_pipeline, text)
            
            for result in ner_results:
                entities.append(Entity(
                    text=result['word'],
                    label=result['entity_group'],
                    confidence=result['score'],
                    start=result['start'],
                    end=result['end']
                ))
                
        except Exception as e:
            logger.error("Transformer entity extraction failed", error=str(e))
        
        return entities
    
    def _extract_custom_patterns(self, text: str) -> List[Entity]:
        """Extract entities using custom regex patterns"""
        entities = []
        
        for entity_type, pattern in self.custom_patterns.items():
            matches = re.finditer(pattern, text, re.IGNORECASE)
            
            for match in matches:
                entities.append(Entity(
                    text=match.group(),
                    label=entity_type.upper(),
                    confidence=0.95,  # High confidence for regex matches
                    start=match.start(),
                    end=match.end()
                ))
        
        return entities
    
    def _merge_entities(self, entities: List[Entity]) -> List[Entity]:
        """Merge overlapping entities and remove duplicates"""
        if not entities:
            return entities
        
        # Sort by start position
        entities.sort(key=lambda x: x.start)
        
        merged = []
        current = entities[0]
        
        for next_entity in entities[1:]:
            # Check for overlap
            if next_entity.start <= current.end:
                # Overlapping entities - keep the one with higher confidence
                if next_entity.confidence > current.confidence:
                    current = next_entity
                # If same confidence, keep the longer one
                elif (next_entity.confidence == current.confidence and 
                      (next_entity.end - next_entity.start) > (current.end - current.start)):
                    current = next_entity
            else:
                # No overlap - add current and move to next
                merged.append(current)
                current = next_entity
        
        # Add the last entity
        merged.append(current)
        
        return merged
    
    def get_supported_entities(self) -> List[str]:
        """Get list of supported entity types"""
        base_entities = [
            "PERSON", "ORG", "GPE", "LOC", "PRODUCT", "EVENT", "WORK_OF_ART",
            "LAW", "LANGUAGE", "DATE", "TIME", "PERCENT", "MONEY", "QUANTITY",
            "ORDINAL", "CARDINAL"
        ]
        
        custom_entities = [entity_type.upper() for entity_type in self.custom_patterns.keys()]
        
        return base_entities + custom_entities
    
    def extract_specific_entity(self, text: str, entity_type: str) -> List[Entity]:
        """Extract specific type of entity"""
        all_entities = asyncio.run(self.extract(text)).entities
        return [entity for entity in all_entities if entity.label == entity_type.upper()]
    
    def get_entity_context(self, text: str, entity: Entity, context_window: int = 20) -> str:
        """Get context around an entity"""
        start = max(0, entity.start - context_window)
        end = min(len(text), entity.end + context_window)
        
        context = text[start:end]
        
        # Mark the entity in context
        entity_start_in_context = entity.start - start
        entity_end_in_context = entity.end - start
        
        return (
            context[:entity_start_in_context] + 
            f"[{entity.label}:{context[entity_start_in_context:entity_end_in_context]}]" +
            context[entity_end_in_context:]
        )
