"""
RAG Service - Complete Implementation
Handles document indexing, vector search, and context retrieval
"""

import asyncio
import json
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import structlog
import redis.asyncio as redis

from .config import settings
from .vector_store import VectorStore
from .document_processor import DocumentProcessor
from .retrieval_engine import RetrievalEngine
from .models import SearchRequest, SearchResult, DocumentMetadata

logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("📚 Starting RAG Service")
    
    # Initialize Redis connection
    app.state.redis = redis.from_url(settings.redis_url)
    
    # Initialize core components
    app.state.vector_store = VectorStore()
    app.state.document_processor = DocumentProcessor()
    app.state.retrieval_engine = RetrievalEngine(app.state.vector_store)
    
    # Initialize vector store
    await app.state.vector_store.initialize()
    
    # Load existing documents
    await app.state.vector_store.load_existing_documents()
    
    logger.info("✅ RAG Service initialized")
    
    yield
    
    logger.info("🛑 Shutting down RAG Service")
    await app.state.redis.close()

app = FastAPI(
    title="RAG Service",
    description="Retrieval-Augmented Generation with vector search",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/search", response_model=SearchResult)
async def search_documents(request: SearchRequest):
    """Search documents using vector similarity"""
    try:
        result = await app.state.retrieval_engine.search(
            query=request.query,
            entities=request.entities,
            limit=request.limit,
            threshold=request.threshold,
            filters=request.filters
        )
        return result
    except Exception as e:
        logger.error("Document search failed", error=str(e))
        raise HTTPException(status_code=500, detail="Search failed")

@app.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    metadata: Optional[str] = None
):
    """Upload and index a document"""
    try:
        # Read file content
        content = await file.read()
        
        # Parse metadata if provided
        doc_metadata = {}
        if metadata:
            try:
                doc_metadata = json.loads(metadata)
            except json.JSONDecodeError:
                pass
        
        # Add file info to metadata
        doc_metadata.update({
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(content)
        })
        
        # Process document in background
        if background_tasks:
            background_tasks.add_task(
                process_and_index_document,
                content, file.filename, doc_metadata,
                app.state.document_processor, app.state.vector_store
            )
            
            return {
                "message": "Document upload started",
                "filename": file.filename,
                "status": "processing"
            }
        else:
            # Process synchronously
            result = await process_and_index_document(
                content, file.filename, doc_metadata,
                app.state.document_processor, app.state.vector_store
            )
            return result
            
    except Exception as e:
        logger.error("Document upload failed", error=str(e))
        raise HTTPException(status_code=500, detail="Upload failed")

async def process_and_index_document(
    content: bytes,
    filename: str,
    metadata: Dict[str, Any],
    processor: DocumentProcessor,
    vector_store: VectorStore
):
    """Process and index a document"""
    try:
        # Process document
        processed_doc = await processor.process_document(content, filename, metadata)
        
        # Index in vector store
        await vector_store.add_document(processed_doc)
        
        logger.info("Document indexed successfully", filename=filename)
        
        return {
            "message": "Document indexed successfully",
            "filename": filename,
            "chunks": len(processed_doc.chunks),
            "status": "completed"
        }
        
    except Exception as e:
        logger.error("Document processing failed", filename=filename, error=str(e))
        raise

@app.post("/index-text")
async def index_text(
    text: str,
    title: str = "Untitled",
    metadata: Optional[Dict[str, Any]] = None
):
    """Index raw text content"""
    try:
        # Create document metadata
        doc_metadata = metadata or {}
        doc_metadata.update({
            "title": title,
            "content_type": "text/plain",
            "source": "api"
        })
        
        # Process text
        processed_doc = await app.state.document_processor.process_text(
            text, title, doc_metadata
        )
        
        # Index in vector store
        await app.state.vector_store.add_document(processed_doc)
        
        return {
            "message": "Text indexed successfully",
            "title": title,
            "chunks": len(processed_doc.chunks)
        }
        
    except Exception as e:
        logger.error("Text indexing failed", error=str(e))
        raise HTTPException(status_code=500, detail="Text indexing failed")

@app.get("/documents")
async def list_documents(
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None
):
    """List indexed documents"""
    try:
        documents = await app.state.vector_store.list_documents(
            limit=limit,
            offset=offset,
            search=search
        )
        return {"documents": documents}
    except Exception as e:
        logger.error("Failed to list documents", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to list documents")

@app.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """Delete a document from the index"""
    try:
        success = await app.state.vector_store.delete_document(document_id)
        if success:
            return {"message": "Document deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Document not found")
    except Exception as e:
        logger.error("Failed to delete document", document_id=document_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to delete document")

@app.post("/reindex")
async def reindex_documents(background_tasks: BackgroundTasks):
    """Reindex all documents"""
    try:
        background_tasks.add_task(
            app.state.vector_store.reindex_all_documents
        )
        return {"message": "Reindexing started"}
    except Exception as e:
        logger.error("Failed to start reindexing", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to start reindexing")

@app.get("/similar/{document_id}")
async def find_similar_documents(
    document_id: str,
    limit: int = 10,
    threshold: float = 0.7
):
    """Find documents similar to a given document"""
    try:
        similar_docs = await app.state.retrieval_engine.find_similar_documents(
            document_id=document_id,
            limit=limit,
            threshold=threshold
        )
        return {"similar_documents": similar_docs}
    except Exception as e:
        logger.error("Failed to find similar documents", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to find similar documents")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    vector_store_health = await app.state.vector_store.health_check()
    
    return {
        "status": "healthy",
        "service": "rag",
        "vector_store": vector_store_health,
        "document_count": await app.state.vector_store.get_document_count(),
        "chunk_count": await app.state.vector_store.get_chunk_count()
    }

# Initialize Prometheus metrics globally
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

rag_total_documents = Gauge('rag_total_documents', 'Total documents in vector store')
rag_total_chunks = Gauge('rag_total_chunks', 'Total chunks in vector store')
rag_total_searches = Counter('rag_total_searches', 'Total searches performed')
rag_average_search_time = Gauge('rag_average_search_time_ms', 'Average search time in ms')
rag_vector_store_size = Gauge('rag_vector_store_size_mb', 'Vector store size in MB')

@app.get("/metrics")
async def get_metrics():
    """Get service metrics in Prometheus format"""
    from fastapi import Response
    
    # Set current values
    rag_total_documents.set(await app.state.vector_store.get_document_count())
    rag_total_chunks.set(await app.state.vector_store.get_chunk_count())
    rag_total_searches._value._value = app.state.retrieval_engine.total_searches
    rag_average_search_time.set(app.state.retrieval_engine.get_average_search_time())
    rag_vector_store_size.set(await app.state.vector_store.get_storage_size())
    
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/stats")
async def get_statistics():
    """Get detailed statistics"""
    return {
        "documents_by_type": await app.state.vector_store.get_documents_by_type(),
        "search_patterns": app.state.retrieval_engine.get_search_patterns(),
        "popular_queries": app.state.retrieval_engine.get_popular_queries(),
        "performance_metrics": {
            "avg_indexing_time_ms": app.state.document_processor.get_average_processing_time(),
            "avg_search_time_ms": app.state.retrieval_engine.get_average_search_time(),
            "cache_hit_rate": app.state.retrieval_engine.get_cache_hit_rate()
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
