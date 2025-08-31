"""Vector store implementation with ChromaDB"""

import asyncio
import uuid
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import structlog
import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
import numpy as np

from .config import settings
from .models import ProcessedDocument, DocumentChunk, DocumentMetadata

logger = structlog.get_logger(__name__)

class VectorStore:
    """Vector store for document embeddings and similarity search"""
    
    def __init__(self):
        self.client = None
        self.collection = None
        self.embedding_model = None
        self.document_count = 0
        self.chunk_count = 0
        
    async def initialize(self):
        """Initialize the vector store"""
        try:
            # Initialize ChromaDB client
            self.client = chromadb.PersistentClient(
                path=settings.vector_db_path,
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # Get or create collection
            self.collection = self.client.get_or_create_collection(
                name="documents",
                metadata={"hnsw:space": "cosine"}
            )
            
            # Load embedding model
            loop = asyncio.get_event_loop()
            self.embedding_model = await loop.run_in_executor(
                None,
                lambda: SentenceTransformer(settings.embedding_model)
            )
            
            # Update counts
            await self._update_counts()
            
            logger.info("Vector store initialized", 
                       documents=self.document_count,
                       chunks=self.chunk_count)
            
        except Exception as e:
            logger.error("Failed to initialize vector store", error=str(e))
            raise
    
    async def add_document(self, document: ProcessedDocument):
        """Add a document to the vector store"""
        try:
            # Generate embeddings for chunks
            chunk_texts = [chunk.content for chunk in document.chunks]
            
            if not chunk_texts:
                logger.warning("No chunks to add", document_id=document.document_id)
                return
            
            # Generate embeddings in executor to avoid blocking
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None,
                self.embedding_model.encode,
                chunk_texts
            )
            
            # Prepare data for ChromaDB
            ids = [chunk.chunk_id for chunk in document.chunks]
            documents_content = chunk_texts
            metadatas = []
            
            for i, chunk in enumerate(document.chunks):
                metadata = chunk.metadata.copy()
                metadata.update({
                    "document_id": document.document_id,
                    "title": document.title,
                    "chunk_index": i,
                    "start_char": chunk.start_char,
                    "end_char": chunk.end_char,
                    "created_at": document.created_at.isoformat(),
                    "updated_at": document.updated_at.isoformat()
                })
                metadatas.append(metadata)
            
            # Add to collection
            self.collection.add(
                ids=ids,
                embeddings=embeddings.tolist(),
                documents=documents_content,
                metadatas=metadatas
            )
            
            self.document_count += 1
            self.chunk_count += len(document.chunks)
            
            logger.info("Document added to vector store", 
                       document_id=document.document_id,
                       chunks=len(document.chunks))
            
        except Exception as e:
            logger.error("Failed to add document", 
                        document_id=document.document_id, 
                        error=str(e))
            raise
    
    async def search(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.7,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar documents"""
        try:
            # Generate query embedding
            loop = asyncio.get_event_loop()
            query_embedding = await loop.run_in_executor(
                None,
                lambda: self.embedding_model.encode([query])[0]
            )
            
            # Prepare where clause for filtering
            where_clause = {}
            if filters:
                for key, value in filters.items():
                    where_clause[key] = value
            
            # Search in collection
            results = self.collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=min(limit, settings.max_search_results),
                where=where_clause if where_clause else None,
                include=["documents", "metadatas", "distances"]
            )
            
            # Process results
            search_results = []
            if results["ids"] and results["ids"][0]:
                for i, chunk_id in enumerate(results["ids"][0]):
                    distance = results["distances"][0][i]
                    similarity = 1 - distance  # Convert distance to similarity
                    
                    if similarity >= threshold:
                        search_results.append({
                            "chunk_id": chunk_id,
                            "content": results["documents"][0][i],
                            "metadata": results["metadatas"][0][i],
                            "similarity": similarity,
                            "distance": distance
                        })
            
            return search_results
            
        except Exception as e:
            logger.error("Search failed", query=query[:100], error=str(e))
            raise
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete a document from the vector store"""
        try:
            # Find all chunks for this document
            results = self.collection.get(
                where={"document_id": document_id},
                include=["metadatas"]
            )
            
            if not results["ids"]:
                return False
            
            # Delete all chunks
            self.collection.delete(
                where={"document_id": document_id}
            )
            
            chunk_count = len(results["ids"])
            self.document_count -= 1
            self.chunk_count -= chunk_count
            
            logger.info("Document deleted", 
                       document_id=document_id,
                       chunks_deleted=chunk_count)
            
            return True
            
        except Exception as e:
            logger.error("Failed to delete document", 
                        document_id=document_id, 
                        error=str(e))
            return False
    
    async def list_documents(
        self,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None
    ) -> List[DocumentMetadata]:
        """List documents in the vector store"""
        try:
            # Get all documents (grouped by document_id)
            all_results = self.collection.get(
                include=["metadatas"]
            )
            
            # Group by document_id
            documents_map = {}
            for i, chunk_id in enumerate(all_results["ids"]):
                metadata = all_results["metadatas"][i]
                doc_id = metadata.get("document_id")
                
                if doc_id not in documents_map:
                    documents_map[doc_id] = {
                        "document_id": doc_id,
                        "title": metadata.get("title", "Untitled"),
                        "filename": metadata.get("filename", ""),
                        "content_type": metadata.get("content_type", ""),
                        "size": metadata.get("size", 0),
                        "chunk_count": 0,
                        "created_at": metadata.get("created_at", ""),
                        "updated_at": metadata.get("updated_at", ""),
                        "tags": metadata.get("tags", []),
                        "category": metadata.get("category")
                    }
                
                documents_map[doc_id]["chunk_count"] += 1
            
            # Convert to list and apply search filter
            documents = list(documents_map.values())
            
            if search:
                search_lower = search.lower()
                documents = [
                    doc for doc in documents
                    if (search_lower in doc["title"].lower() or 
                        search_lower in doc["filename"].lower())
                ]
            
            # Apply pagination
            total = len(documents)
            documents = documents[offset:offset + limit]
            
            # Convert to DocumentMetadata objects
            result = []
            for doc in documents:
                try:
                    created_at = datetime.fromisoformat(doc["created_at"]) if doc["created_at"] else datetime.utcnow()
                    updated_at = datetime.fromisoformat(doc["updated_at"]) if doc["updated_at"] else datetime.utcnow()
                except:
                    created_at = updated_at = datetime.utcnow()
                
                result.append(DocumentMetadata(
                    document_id=doc["document_id"],
                    title=doc["title"],
                    filename=doc["filename"],
                    content_type=doc["content_type"],
                    size=doc["size"],
                    chunk_count=doc["chunk_count"],
                    created_at=created_at,
                    updated_at=updated_at,
                    tags=doc["tags"],
                    category=doc["category"]
                ))
            
            return result
            
        except Exception as e:
            logger.error("Failed to list documents", error=str(e))
            return []
    
    async def get_document_count(self) -> int:
        """Get total number of documents"""
        return self.document_count
    
    async def get_chunk_count(self) -> int:
        """Get total number of chunks"""
        return self.chunk_count
    
    async def get_storage_size(self) -> float:
        """Get storage size in MB (approximate)"""
        try:
            # This is an approximation - ChromaDB doesn't provide direct size info
            return self.chunk_count * 0.001  # Rough estimate
        except:
            return 0.0
    
    async def get_documents_by_type(self) -> Dict[str, int]:
        """Get document count by content type"""
        try:
            results = self.collection.get(include=["metadatas"])
            
            type_counts = {}
            processed_docs = set()
            
            for metadata in results["metadatas"]:
                doc_id = metadata.get("document_id")
                if doc_id in processed_docs:
                    continue
                
                processed_docs.add(doc_id)
                content_type = metadata.get("content_type", "unknown")
                type_counts[content_type] = type_counts.get(content_type, 0) + 1
            
            return type_counts
            
        except Exception as e:
            logger.error("Failed to get documents by type", error=str(e))
            return {}
    
    async def health_check(self) -> Dict[str, Any]:
        """Check vector store health"""
        try:
            # Test basic operations
            test_results = self.collection.get(limit=1)
            
            return {
                "status": "healthy",
                "documents": self.document_count,
                "chunks": self.chunk_count,
                "embedding_model": settings.embedding_model,
                "collection_name": self.collection.name if self.collection else None
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def load_existing_documents(self):
        """Load count of existing documents"""
        try:
            await self._update_counts()
            logger.info("Loaded existing documents", 
                       documents=self.document_count,
                       chunks=self.chunk_count)
        except Exception as e:
            logger.error("Failed to load existing documents", error=str(e))
    
    async def _update_counts(self):
        """Update document and chunk counts"""
        try:
            if self.collection:
                # Get all metadata to count unique documents
                results = self.collection.get(include=["metadatas"])
                
                unique_docs = set()
                for metadata in results["metadatas"]:
                    doc_id = metadata.get("document_id")
                    if doc_id:
                        unique_docs.add(doc_id)
                
                self.document_count = len(unique_docs)
                self.chunk_count = len(results["ids"])
                
        except Exception as e:
            logger.error("Failed to update counts", error=str(e))
    
    async def reindex_all_documents(self):
        """Reindex all documents (rebuild embeddings)"""
        try:
            logger.info("Starting document reindexing")
            
            # Get all documents
            results = self.collection.get(
                include=["documents", "metadatas"]
            )
            
            if not results["ids"]:
                logger.info("No documents to reindex")
                return
            
            # Regenerate embeddings
            loop = asyncio.get_event_loop()
            new_embeddings = await loop.run_in_executor(
                None,
                self.embedding_model.encode,
                results["documents"]
            )
            
            # Update collection with new embeddings
            self.collection.update(
                ids=results["ids"],
                embeddings=new_embeddings.tolist()
            )
            
            logger.info("Document reindexing completed", 
                       chunks_reindexed=len(results["ids"]))
            
        except Exception as e:
            logger.error("Reindexing failed", error=str(e))
            raise
