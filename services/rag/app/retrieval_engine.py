"""Retrieval engine for semantic search and context generation"""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
import structlog
from collections import defaultdict, Counter

from .config import settings
from .vector_store import VectorStore
from .models import SearchResult

logger = structlog.get_logger(__name__)

class RetrievalEngine:
    """Advanced retrieval engine with semantic search and context generation"""
    
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
        self.total_searches = 0
        self.search_times = []
        self.query_cache = {}
        self.cache_hits = 0
        self.search_patterns = defaultdict(int)
        self.popular_queries = Counter()
    
    async def search(
        self,
        query: str,
        entities: List[Dict[str, Any]] = None,
        limit: int = 10,
        threshold: float = 0.7,
        filters: Optional[Dict[str, Any]] = None
    ) -> SearchResult:
        """Perform semantic search with context generation"""
        start_time = datetime.utcnow()
        
        try:
            # Check cache first
            cache_key = self._generate_cache_key(query, entities, limit, threshold, filters)
            if cache_key in self.query_cache:
                cached_result = self.query_cache[cache_key]
                # Check if cache is still valid (1 hour)
                if (datetime.utcnow() - cached_result["timestamp"]).seconds < settings.cache_ttl_seconds:
                    self.cache_hits += 1
                    cached_result["result"].search_time_ms = 0  # Cache hit
                    return cached_result["result"]
            
            # Enhance query with entities
            enhanced_query = self._enhance_query_with_entities(query, entities or [])
            
            # Perform vector search
            search_results = await self.vector_store.search(
                query=enhanced_query,
                limit=limit * 2,  # Get more results for better context
                threshold=threshold,
                filters=filters
            )
            
            # Re-rank results
            ranked_results = self._rerank_results(search_results, query, entities or [])
            
            # Limit to requested number
            final_results = ranked_results[:limit]
            
            # Generate context from results
            context = self._generate_context(final_results)
            
            # Extract sources
            sources = self._extract_sources(final_results)
            
            # Calculate search time
            search_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Create result
            result = SearchResult(
                query=query,
                results=final_results,
                context=context,
                sources=sources,
                total_results=len(search_results),
                search_time_ms=search_time
            )
            
            # Cache result
            self.query_cache[cache_key] = {
                "result": result,
                "timestamp": datetime.utcnow()
            }
            
            # Update metrics
            self.total_searches += 1
            self.search_times.append(search_time)
            if len(self.search_times) > 1000:
                self.search_times = self.search_times[-1000:]
            
            # Track patterns
            self._track_search_patterns(query, entities or [])
            self.popular_queries[query.lower()] += 1
            
            logger.debug("Search completed", 
                        query=query[:100],
                        results=len(final_results),
                        search_time_ms=search_time)
            
            return result
            
        except Exception as e:
            logger.error("Search failed", query=query[:100], error=str(e))
            # Return empty result on error
            return SearchResult(
                query=query,
                results=[],
                context="",
                sources=[],
                total_results=0,
                search_time_ms=0
            )
    
    def _enhance_query_with_entities(self, query: str, entities: List[Dict[str, Any]]) -> str:
        """Enhance query with extracted entities"""
        if not entities:
            return query
        
        # Extract relevant entity text
        entity_terms = []
        for entity in entities:
            entity_text = entity.get("text", "")
            entity_label = entity.get("label", "")
            
            # Add entity text if it's not already in query
            if entity_text and entity_text.lower() not in query.lower():
                entity_terms.append(entity_text)
        
        # Combine query with entity terms
        if entity_terms:
            enhanced_query = f"{query} {' '.join(entity_terms)}"
            return enhanced_query
        
        return query
    
    def _rerank_results(
        self,
        results: List[Dict[str, Any]],
        query: str,
        entities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Re-rank search results based on additional criteria"""
        if not results:
            return results
        
        # Calculate additional scores
        for result in results:
            additional_score = 0.0
            
            # Boost results that contain entities
            content = result.get("content", "").lower()
            for entity in entities:
                entity_text = entity.get("text", "").lower()
                if entity_text and entity_text in content:
                    additional_score += 0.1
            
            # Boost results from recent documents
            metadata = result.get("metadata", {})
            created_at = metadata.get("created_at", "")
            if created_at:
                try:
                    doc_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    days_old = (datetime.utcnow() - doc_date.replace(tzinfo=None)).days
                    if days_old < 30:  # Recent documents get boost
                        additional_score += 0.05
                except:
                    pass
            
            # Boost results with higher chunk index (usually more important content)
            chunk_index = metadata.get("chunk_index", 0)
            if chunk_index == 0:  # First chunk often contains key information
                additional_score += 0.05
            
            # Update similarity score
            original_similarity = result.get("similarity", 0.0)
            result["similarity"] = min(1.0, original_similarity + additional_score)
            result["rerank_boost"] = additional_score
        
        # Sort by updated similarity
        return sorted(results, key=lambda x: x.get("similarity", 0.0), reverse=True)
    
    def _generate_context(self, results: List[Dict[str, Any]]) -> str:
        """Generate context from search results"""
        if not results:
            return ""
        
        # Group results by document to avoid repetition
        doc_contents = {}
        for result in results:
            doc_id = result.get("metadata", {}).get("document_id", "")
            if doc_id not in doc_contents:
                doc_contents[doc_id] = []
            doc_contents[doc_id].append(result.get("content", ""))
        
        # Create context from top results
        context_parts = []
        total_length = 0
        max_context_length = 2000  # Maximum context length
        
        for result in results:
            content = result.get("content", "")
            if content and total_length + len(content) < max_context_length:
                # Add document title if available
                title = result.get("metadata", {}).get("title", "")
                if title and title not in context_parts:
                    context_parts.append(f"From '{title}':")
                
                context_parts.append(content)
                total_length += len(content)
            
            if total_length >= max_context_length:
                break
        
        return "\n\n".join(context_parts)
    
    def _extract_sources(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract source information from results"""
        sources = []
        seen_docs = set()
        
        for result in results:
            metadata = result.get("metadata", {})
            doc_id = metadata.get("document_id", "")
            
            if doc_id and doc_id not in seen_docs:
                seen_docs.add(doc_id)
                
                source = {
                    "document_id": doc_id,
                    "title": metadata.get("title", "Untitled"),
                    "filename": metadata.get("filename", ""),
                    "content_type": metadata.get("content_type", ""),
                    "similarity": result.get("similarity", 0.0),
                    "chunk_count": 1  # Will be updated if more chunks from same doc
                }
                
                sources.append(source)
            else:
                # Update chunk count for existing source
                for source in sources:
                    if source["document_id"] == doc_id:
                        source["chunk_count"] += 1
                        # Update similarity to highest among chunks
                        source["similarity"] = max(source["similarity"], result.get("similarity", 0.0))
                        break
        
        # Sort sources by similarity
        return sorted(sources, key=lambda x: x["similarity"], reverse=True)
    
    async def find_similar_documents(
        self,
        document_id: str,
        limit: int = 10,
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Find documents similar to a given document"""
        try:
            # Get a representative chunk from the document
            doc_results = await self.vector_store.search(
                query="",  # Empty query to get by filter only
                limit=1,
                filters={"document_id": document_id}
            )
            
            if not doc_results:
                return []
            
            # Use the content of the first chunk as query
            representative_content = doc_results[0].get("content", "")
            
            # Search for similar content, excluding the source document
            similar_results = await self.vector_store.search(
                query=representative_content,
                limit=limit * 2,
                threshold=threshold
            )
            
            # Filter out chunks from the same document
            filtered_results = [
                result for result in similar_results
                if result.get("metadata", {}).get("document_id") != document_id
            ]
            
            # Group by document and get best chunk per document
            doc_best_chunks = {}
            for result in filtered_results:
                doc_id = result.get("metadata", {}).get("document_id", "")
                if doc_id:
                    if (doc_id not in doc_best_chunks or 
                        result.get("similarity", 0) > doc_best_chunks[doc_id].get("similarity", 0)):
                        doc_best_chunks[doc_id] = result
            
            # Return top similar documents
            similar_docs = list(doc_best_chunks.values())
            similar_docs.sort(key=lambda x: x.get("similarity", 0), reverse=True)
            
            return similar_docs[:limit]
            
        except Exception as e:
            logger.error("Failed to find similar documents", 
                        document_id=document_id, 
                        error=str(e))
            return []
    
    def _generate_cache_key(
        self,
        query: str,
        entities: Optional[List[Dict[str, Any]]],
        limit: int,
        threshold: float,
        filters: Optional[Dict[str, Any]]
    ) -> str:
        """Generate cache key for query"""
        import hashlib
        
        # Create key from query parameters
        key_parts = [
            query.lower(),
            str(limit),
            str(threshold)
        ]
        
        if entities:
            entity_texts = [e.get("text", "") for e in entities]
            key_parts.append("|".join(sorted(entity_texts)))
        
        if filters:
            filter_str = "|".join(f"{k}:{v}" for k, v in sorted(filters.items()))
            key_parts.append(filter_str)
        
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _track_search_patterns(self, query: str, entities: List[Dict[str, Any]]):
        """Track search patterns for analytics"""
        # Track query length patterns
        query_length = len(query.split())
        if query_length <= 3:
            self.search_patterns["short_queries"] += 1
        elif query_length <= 10:
            self.search_patterns["medium_queries"] += 1
        else:
            self.search_patterns["long_queries"] += 1
        
        # Track entity usage
        if entities:
            self.search_patterns["queries_with_entities"] += 1
            entity_types = [e.get("label", "") for e in entities]
            for entity_type in set(entity_types):
                if entity_type:
                    self.search_patterns[f"entity_{entity_type.lower()}"] += 1
        else:
            self.search_patterns["queries_without_entities"] += 1
    
    def get_average_search_time(self) -> float:
        """Get average search time in milliseconds"""
        if not self.search_times:
            return 0.0
        return sum(self.search_times) / len(self.search_times)
    
    def get_cache_hit_rate(self) -> float:
        """Get cache hit rate"""
        if self.total_searches == 0:
            return 0.0
        return self.cache_hits / self.total_searches
    
    def get_search_patterns(self) -> Dict[str, int]:
        """Get search patterns for analytics"""
        return dict(self.search_patterns)
    
    def get_popular_queries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most popular queries"""
        return [
            {"query": query, "count": count}
            for query, count in self.popular_queries.most_common(limit)
        ]
    
    def clear_cache(self):
        """Clear the query cache"""
        self.query_cache.clear()
        self.cache_hits = 0
        logger.info("Query cache cleared")
