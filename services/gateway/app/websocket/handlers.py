"""WebSocket message handlers"""

import asyncio
import json
from typing import Dict, Any
from fastapi import WebSocket, WebSocketDisconnect
import structlog
import redis.asyncio as redis

from .manager import ConnectionManager
from ..middleware.auth import verify_token

logger = structlog.get_logger(__name__)


class WebSocketHandler:
    """Handles WebSocket messages and routing"""
    
    def __init__(self, redis, connection_manager=None):
        self.redis = redis
        self.connections: Dict[str, WebSocket] = {}
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
        self.processed_messages: set = set()  # For message deduplication
        # Use provided connection manager or create new one
        if connection_manager:
            self.connection_manager = connection_manager
        else:
            # Import here to avoid circular import
            from .manager import ConnectionManager
            self.connection_manager = ConnectionManager()
        self.message_handlers = {
            "auth": self._handle_auth,
            "audio_frame": self._handle_audio_frame,
            "start_session": self._handle_start_session,
            "end_session": self._handle_end_session,
            "ping": self._handle_ping,
            "document_uploaded": self._handle_document_uploaded,
            "document_upload": self._handle_document_upload,
            "voice_input": self._handle_voice_input,
            "tts_request": self._handle_tts_request,
            "voice_settings": self._handle_voice_settings,
            "text": self._handle_text_message,
            "voice_start": self._handle_voice_start,
            "voice_stop": self._handle_voice_stop,
        }
    
    async def handle_connection(self, websocket: WebSocket, connection_id: str):
        """Handle a WebSocket connection lifecycle"""
        try:
            while True:
                # Receive message
                data = await websocket.receive()
                
                if data["type"] == "websocket.disconnect":
                    break
                
                # Parse message
                try:
                    if "text" in data:
                        message = json.loads(data["text"])
                    elif "bytes" in data:
                        # Handle binary audio data
                        await self._handle_binary_message(data["bytes"], connection_id)
                        continue
                    else:
                        continue
                    
                    # Route message to handler
                    await self._route_message(message, connection_id)
                    
                except json.JSONDecodeError:
                    await self._send_error(connection_id, "Invalid JSON format")
                except Exception as e:
                    logger.error("Message handling error", error=str(e), connection_id=connection_id)
                    await self._send_error(connection_id, "Message processing error")
        
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected", connection_id=connection_id)
        except Exception as e:
            logger.error("WebSocket error", error=str(e), connection_id=connection_id)
    
    async def _route_message(self, message: Dict[str, Any], connection_id: str):
        """Route message to appropriate handler"""
        message_type = message.get("type")
        
        logger.info("Routing message", message_type=message_type, connection_id=connection_id)
        
        if message_type in self.message_handlers:
            await self.message_handlers[message_type](message, connection_id)
        else:
            logger.warning("Unknown message type", message_type=message_type, connection_id=connection_id)
            await self._send_error(connection_id, f"Unknown message type: {message_type}")
    
    async def _handle_auth(self, message: Dict[str, Any], connection_id: str):
        """Handle authentication message"""
        token = message.get("token")
        session_id = message.get("session_id")
        
        # For demo purposes, allow session_id-based "authentication"
        if not token and session_id:
            # Create a demo user session
            user_id = f"demo_user_{session_id}"
            
            # Associate connection with demo user
            self.connection_manager.associate_user(connection_id, user_id)
            if connection_id in self.connection_manager.active_connections:
                self.connection_manager.active_connections[connection_id]["authenticated"] = True
                self.connection_manager.active_connections[connection_id]["user_id"] = user_id
            
            # Store session info in Redis
            await self.redis.setex(
                f"ws_session:{connection_id}",
                3600,  # 1 hour
                json.dumps({
                    "user_id": user_id,
                    "authenticated": True,
                    "demo_mode": True,
                    "session_id": session_id
                })
            )
            
            await self._send_message(connection_id, {
                "type": "auth_success",
                "user_id": user_id,
                "demo_mode": True
            })
            return
        
        if not token:
            # Use a dedicated auth_error type so clients can react appropriately
            await self._send_message(connection_id, {
                "type": "auth_error",
                "message": "Token required"
            })
            return
        
        try:
            # Verify token
            user_payload = verify_token(token)
            # Support common claim names similar to ConnectionManager
            user_id = user_payload.get("sub") or user_payload.get("user_id") or user_payload.get("uid")
            if not user_id:
                raise ValueError("Missing user identifier in token claims")
            
            # Associate connection with user
            self.connection_manager.associate_user(connection_id, user_id)
            # Mark this connection as authenticated for subsequent checks
            if connection_id in self.connection_manager.active_connections:
                self.connection_manager.active_connections[connection_id]["authenticated"] = True
                self.connection_manager.active_connections[connection_id]["user_id"] = user_id
            
            # Store session info in Redis
            await self.redis.setex(
                f"ws_session:{connection_id}",
                3600,  # 1 hour
                json.dumps({
                    "user_id": user_id,
                    "authenticated": True,
                    "roles": user_payload.get("roles", [])
                })
            )
            
            await self._send_message(connection_id, {
                "type": "auth_success",
                "user_id": user_id
            })
            
        except Exception as e:
            # Send explicit auth_error so frontend can mark auth_failed state
            await self._send_message(connection_id, {
                "type": "auth_error",
                "message": "Authentication failed"
            })
    
    async def _handle_audio_frame(self, message: Dict[str, Any], connection_id: str):
        """Handle audio frame message"""
        # Verify authentication
        if not await self._is_authenticated(connection_id):
            await self._send_error(connection_id, "Authentication required")
            return
        
        # Extract audio data
        audio_data = message.get("payload")
        session_id = message.get("session_id")
        sequence = message.get("seq", 0)
        
        if not audio_data or not session_id:
            await self._send_error(connection_id, "Missing audio data or session_id")
            return
        
        # Forward to speech service (via Redis pub/sub or direct HTTP)
        await self._forward_to_speech_service({
            "type": "audio_frame",
            "session_id": session_id,
            "connection_id": connection_id,
            "sequence": sequence,
            "payload": audio_data
        })
    
    async def _handle_binary_message(self, data: bytes, connection_id: str):
        """Handle binary audio data"""
        # Verify authentication
        if not await self._is_authenticated(connection_id):
            return
        
        # Get session info
        session_info = await self.redis.get(f"ws_session:{connection_id}")
        if not session_info:
            return
        
        session_data = json.loads(session_info)
        
        # Forward binary audio to speech service
        await self._forward_binary_to_speech_service(data, connection_id, session_data)
    
    async def _handle_start_session(self, message: Dict[str, Any], connection_id: str):
        """Handle session start message"""
        if not await self._is_authenticated(connection_id):
            await self._send_error(connection_id, "Authentication required")
            return
        
        session_id = message.get("session_id")
        if not session_id:
            # Generate session ID if not provided
            import uuid
            session_id = str(uuid.uuid4())
        
        # Initialize session state
        await self.redis.setex(
            f"active_session:{connection_id}",
            3600,
            json.dumps({
                "session_id": session_id,
                "started_at": asyncio.get_event_loop().time(),
                "status": "active"
            })
        )
        
        await self._send_message(connection_id, {
            "type": "session_started",
            "session_id": session_id
        })
    
    async def _handle_end_session(self, message: Dict[str, Any], connection_id: str):
        """Handle session end message"""
        # Clean up session state
        await self.redis.delete(f"active_session:{connection_id}")
        
        await self._send_message(connection_id, {
            "type": "session_ended"
        })
    
    async def _handle_ping(self, message: Dict[str, Any], connection_id: str):
        """Handle ping message"""
        await self._send_message(connection_id, {
            "type": "pong",
            "timestamp": message.get("timestamp")
        })
    
    async def _handle_document_uploaded(self, message: Dict[str, Any], connection_id: str):
        """Handle document uploaded notification from client"""
        # Require authentication
        if not await self._is_authenticated(connection_id):
            await self._send_error(connection_id, "Authentication required")
            return
        
        doc = message.get("document") or {}
        # In a full implementation, forward to RAG/ingestion service. For now, ack.
        await self._send_message(connection_id, {
            "type": "document_processed",
            "document": doc,
            "status": "indexed",
            "timestamp": message.get("timestamp")
        })
    
    async def _is_authenticated(self, connection_id: str) -> bool:
        """Check if connection is authenticated"""
        connection_info = self.connection_manager.active_connections.get(connection_id)
        if not connection_info:
            logger.warning("Authentication check failed - connection not found", connection_id=connection_id)
            return False
        
        authenticated = connection_info.get("authenticated", False)
        logger.info("Authentication check", connection_id=connection_id, authenticated=authenticated, 
                   user_id=connection_info.get("user_id"), 
                   connection_keys=list(connection_info.keys()))
        
        return authenticated
    
    async def _send_message(self, connection_id: str, message: Dict[str, Any]):
        """Send message to connection"""
        await self.connection_manager.send_personal_message(message, connection_id)
    
    async def _send_error(self, connection_id: str, error_message: str):
        """Send error message to connection"""
        await self._send_message(connection_id, {
            "type": "error",
            "message": error_message
        })
    
    async def _forward_to_speech_service(self, message: Dict[str, Any]):
        """Forward message to speech service via Redis pub/sub"""
        await self.redis.publish("speech_input", json.dumps(message))
    
    async def _forward_binary_to_speech_service(self, data: bytes, connection_id: str, session_data: Dict[str, Any]):
        """Forward binary audio to speech service"""
        # Store binary data in Redis with expiration
        key = f"audio_frame:{connection_id}:{asyncio.get_event_loop().time()}"
        await self.redis.setex(key, 60, data)  # 1 minute expiration
        
        # Publish notification
        await self.redis.publish("speech_binary", json.dumps({
            "type": "binary_audio",
            "connection_id": connection_id,
            "data_key": key,
            "user_id": session_data["user_id"]
        }))
    
    async def handle_message(self, message_text: str, connection_id: str):
        """Handle text message - wrapper for _route_message"""
        try:
            message = json.loads(message_text)
            await self._route_message(message, connection_id)
        except json.JSONDecodeError:
            await self._send_error(connection_id, "Invalid JSON format")
        except Exception as e:
            logger.error("Message handling error", error=str(e), connection_id=connection_id)
            await self._send_error(connection_id, "Message processing error")
    
    async def handle_binary_message(self, data: bytes, connection_id: str):
        """Handle binary message - wrapper for _handle_binary_message"""
        await self._handle_binary_message(data, connection_id)
    
    async def _handle_voice_settings(self, message: Dict[str, Any], connection_id: str):
        """Handle voice settings configuration"""
        if not await self._is_authenticated(connection_id):
            await self._send_error(connection_id, "Authentication required")
            return
        
        settings = message.get("settings", {})
        
        # Store voice settings in Redis
        await self.redis.setex(
            f"voice_settings:{connection_id}",
            3600,  # 1 hour
            json.dumps(settings)
        )
        
        await self._send_message(connection_id, {
            "type": "voice_settings_updated",
            "settings": settings
        })
    
    async def _handle_text_message(self, message: Dict[str, Any], connection_id: str):
        """Handle text message from user"""
        if not await self._is_authenticated(connection_id):
            await self._send_error(connection_id, "Authentication required")
            return
        
        text = message.get("text", "")
        session_id = message.get("session_id")
        
        if not text:
            await self._send_error(connection_id, "Missing text content")
            return
        
        # Echo the user's message to chat
        await self._send_message(connection_id, {
            "type": "chat_message",
            "role": "user",
            "content": text,
            "timestamp": asyncio.get_event_loop().time()
        })
        
        # Forward to orchestrator for processing
        await self._forward_to_orchestrator({
            "type": "text_input",
            "text": text,
            "session_id": session_id,
            "connection_id": connection_id
        })
    
    async def _handle_voice_start(self, message: Dict[str, Any], connection_id: str):
        """Handle voice recording start"""
        if not await self._is_authenticated(connection_id):
            await self._send_error(connection_id, "Authentication required")
            return
        
        session_id = message.get("session_id")
        
        # Store voice session state
        await self.redis.setex(
            f"voice_session:{connection_id}",
            300,  # 5 minutes
            json.dumps({
                "session_id": session_id,
                "status": "recording",
                "started_at": asyncio.get_event_loop().time()
            })
        )
        
        await self._send_message(connection_id, {
            "type": "voice_recording_started",
            "session_id": session_id
        })
    
    async def _handle_voice_stop(self, message: Dict[str, Any], connection_id: str):
        """Handle voice recording stop"""
        if not await self._is_authenticated(connection_id):
            await self._send_error(connection_id, "Authentication required")
            return
        
        session_id = message.get("session_id")
        
        # Update voice session state
        await self.redis.setex(
            f"voice_session:{connection_id}",
            300,  # 5 minutes
            json.dumps({
                "session_id": session_id,
                "status": "processing",
                "stopped_at": asyncio.get_event_loop().time()
            })
        )
        
        await self._send_message(connection_id, {
            "type": "voice_recording_stopped",
            "session_id": session_id
        })
        
        # Trigger speech processing
        await self._forward_to_speech_service({
            "type": "process_audio",
            "session_id": session_id,
            "connection_id": connection_id
        })
    
    async def _forward_to_orchestrator(self, message: Dict[str, Any]):
        """Forward message to orchestrator service via Redis pub/sub"""
        logger.info("Forwarding to orchestrator", message_type=message.get("type"), connection_id=message.get("connection_id"))
        await self.redis.publish("orchestrator_input", json.dumps(message))
    
    async def handle_service_response(self, service: str, response: Dict[str, Any]):
        """Handle responses from backend services"""
        connection_id = response.get("connection_id")
        if not connection_id:
            logger.warning("No connection_id in service response", service=service, response_type=response.get("type"))
            return
        
        logger.info("Processing service response", service=service, response_type=response.get("type"), connection_id=connection_id)
        
        if service == "speech" and response.get("type") == "transcription":
            # Send transcription to client
            await self._send_message(connection_id, {
                "type": "transcription",
                "data": response.get("data", {})
            })
            
            # Forward to orchestrator for AI response
            transcription_data = response.get("data", {})
            await self._forward_to_orchestrator({
                "type": "voice_input",
                "text": transcription_data.get("text", ""),
                "session_id": response.get("session_id"),
                "connection_id": connection_id
            })
        
        elif service == "orchestrator" and response.get("type") == "ai_response":
            # Create message ID for deduplication
            message_id = f"{connection_id}:{response.get('type')}:{hash(str(response.get('data', {})))}"
            
            if message_id in self.processed_messages:
                logger.debug("Skipping duplicate message", message_id=message_id)
                return
            
            self.processed_messages.add(message_id)
            
            # Clean up old message IDs (keep only last 100)
            if len(self.processed_messages) > 100:
                self.processed_messages = set(list(self.processed_messages)[-50:])
            
            # Extract text from nested data structure
            response_data = response.get("data", {})
            ai_text = response_data.get("text", "")
            
            logger.info("Sending AI response to client", connection_id=connection_id, text=ai_text[:50])
            
            # Send AI response to chat
            await self._send_message(connection_id, {
                "type": "chat_message",
                "role": "assistant",
                "content": ai_text,
                "timestamp": response.get("timestamp", asyncio.get_event_loop().time())
            })
            
            # Forward to TTS for audio generation
            await self._forward_to_tts_service({
                "type": "synthesize",
                "text": ai_text,
                "session_id": response.get("session_id"),
                "connection_id": connection_id,
                "voice_settings": await self._get_voice_settings(connection_id)
            })
        
        elif service == "tts" and response.get("type") == "audio_ready":
            # Send audio to client
            logger.info("🔊 Forwarding TTS audio to client", connection_id=connection_id, has_audio_data=bool(response.get("audio_data")))
            await self._send_message(connection_id, {
                "type": "audio_response",
                "audio_url": response.get("audio_url"),
                "audio_data": response.get("audio_data"),
                "session_id": response.get("session_id"),
                "auto_play": response.get("auto_play", False)
            })
    
    async def _forward_to_tts_service(self, message: Dict[str, Any]):
        """Forward message to TTS service via Redis pub/sub"""
        await self.redis.publish("tts_input", json.dumps(message))
    
    async def _handle_document_upload(self, message: Dict[str, Any], connection_id: str):
        """Handle document upload from client"""
        logger.info("Processing document upload", connection_id=connection_id, file_name=message.get("file_name"))
        
        if not await self._is_authenticated(connection_id):
            logger.warning("Document upload rejected - not authenticated", connection_id=connection_id)
            await self._send_error(connection_id, "Authentication required")
            return
        
        file_data = message.get("file_data")
        file_name = message.get("file_name")
        file_type = message.get("file_type")
        file_id = message.get("file_id")
        
        logger.info("Document upload data", connection_id=connection_id, file_name=file_name, file_type=file_type, has_data=bool(file_data))
        
        if not file_data or not file_name:
            logger.warning("Document upload rejected - missing data", connection_id=connection_id, file_name=file_name, has_data=bool(file_data))
            await self._send_error(connection_id, "Missing file data or name")
            return
        
        # Store document context for persistent memory
        await self._store_document_context(connection_id, file_id, file_name, file_data)
        
        # Send document to RAG service for processing and indexing
        await self._send_to_rag_service(file_data, file_name, file_type, file_id, connection_id)
        
        # Acknowledge the upload
        await self._send_message(connection_id, {
            "type": "document_processed",
            "file_id": file_id,
            "file_name": file_name,
            "status": "processed"
        })
        
        # Automatically start AI greeting and document analysis
        await self._initiate_ai_greeting(connection_id, file_name, file_id)
    
    async def _handle_voice_input(self, message: Dict[str, Any], connection_id: str):
        """Handle voice input from client"""
        if not await self._is_authenticated(connection_id):
            await self._send_error(connection_id, "Authentication required")
            return
        
        # Check if already processing audio for this connection
        processing_key = f"processing_audio:{connection_id}"
        is_processing = await self.redis.get(processing_key)
        if is_processing:
            return  # Skip duplicate processing
        
        # Set processing flag
        await self.redis.setex(processing_key, 30, "true")  # 30 second timeout
        
        audio_data = message.get("audio_data")
        format_type = message.get("format", "webm")
        context_files = message.get("context_files", [])
        settings = message.get("settings", {})
        
        if not audio_data:
            await self.redis.delete(processing_key)
            await self._send_error(connection_id, "Missing audio data")
            return
        
        try:
            # Forward to speech service for transcription
            await self.redis.publish("speech_input", json.dumps({
                "type": "transcribe_audio",
                "audio_data": audio_data,
                "format": format_type,
                "connection_id": connection_id,
                "context_files": context_files
            }))
            
        finally:
            # Clear processing flag after a delay to prevent rapid requests
            await asyncio.sleep(0.5)
            await self.redis.delete(processing_key)
    
    async def _handle_tts_request(self, message: Dict[str, Any], connection_id: str):
        """Handle TTS synthesis request"""
        if not await self._is_authenticated(connection_id):
            await self._send_error(connection_id, "Authentication required")
            return
        
        text = message.get("text")
        voice = message.get("voice", "alloy")
        speed = message.get("speed", 1.0)
        
        if not text:
            await self._send_error(connection_id, "Missing text for synthesis")
            return
        
        # Send processing status
        await self._send_message(connection_id, {
            "type": "processing_status",
            "data": {
                "status": "Generating audio..."
            }
        })
        
        # Forward to TTS service for actual synthesis
        await self._forward_to_tts_service({
            "type": "synthesize",
            "text": text,
            "connection_id": connection_id,
            "voice_settings": {
                "voice": voice,
                "speed": speed
            }
        })

    async def _send_to_rag_service(self, file_data: str, file_name: str, file_type: str, file_id: str, connection_id: str):
        """Send document to RAG service for processing and indexing"""
        try:
            import httpx
            import base64
            
            # Decode base64 file data - handle potential padding issues
            try:
                # Remove data URL prefix if present (data:application/...;base64,)
                if file_data.startswith('data:'):
                    file_data = file_data.split(',', 1)[1]
                
                # Add padding if needed
                missing_padding = len(file_data) % 4
                if missing_padding:
                    file_data += '=' * (4 - missing_padding)
                
                file_bytes = base64.b64decode(file_data)
                logger.info("Successfully decoded file data", file_name=file_name, size=len(file_bytes))
            except Exception as decode_error:
                logger.error("Base64 decode failed", error=str(decode_error), file_name=file_name)
                await self._send_error(connection_id, f"File encoding error: {str(decode_error)}")
                return
            
            # Prepare multipart form data
            files = {
                'file': (file_name, file_bytes, file_type or 'application/octet-stream')
            }
            
            data = {
                'document_id': file_id,
                'connection_id': connection_id,
                'metadata': json.dumps({
                    'filename': file_name,
                    'content_type': file_type,
                    'uploaded_by': connection_id,
                    'size': len(file_bytes)
                })
            }
            
            # Send to RAG service
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://rag:8005/upload",
                    files=files,
                    data=data,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    logger.info("Document sent to RAG service", file_name=file_name, file_id=file_id)
                else:
                    logger.warning("RAG service upload failed", status=response.status_code, file_name=file_name)
                    
        except Exception as e:
            logger.error("Failed to send document to RAG service", error=str(e), file_name=file_name)

    async def _get_voice_settings(self, connection_id: str) -> Dict[str, Any]:
        """Get voice settings for connection"""
        settings_data = await self.redis.get(f"voice_settings:{connection_id}")
        if settings_data:
            return json.loads(settings_data)
        return {
            "voice": "alloy",
            "speed": 1.0,
            "pitch": 1.0
        }
    
    async def _store_document_context(self, connection_id: str, file_id: str, file_name: str, file_data: str):
        """Store document context for persistent memory"""
        # Store document in conversation context
        context_key = f"conversation_context:{connection_id}"
        context_data = await self.redis.get(context_key)
        
        if context_data:
            context = json.loads(context_data)
        else:
            context = {
                "documents": [],
                "conversation_history": [],
                "user_preferences": {},
                "session_start": asyncio.get_event_loop().time()
            }
        
        # Add document to context
        context["documents"].append({
            "file_id": file_id,
            "file_name": file_name,
            "upload_time": asyncio.get_event_loop().time(),
            "content_preview": file_data[:500] if file_data else ""  # Store first 500 chars for context
        })
        
        # Store updated context with 24 hour expiration
        await self.redis.setex(context_key, 86400, json.dumps(context))
    
    async def _initiate_ai_greeting(self, connection_id: str, file_name: str, file_id: str):
        """Initiate AI greeting and document analysis"""
        # Get document context
        context_key = f"conversation_context:{connection_id}"
        context_data = await self.redis.get(context_key)
        context = json.loads(context_data) if context_data else {}
        
        # Check if greeting already sent for this session
        if context.get("greeting_sent", False):
            logger.info("Greeting already sent for this session", connection_id=connection_id)
            return
        
        documents = context.get("documents", [])
        doc_count = len(documents)
        
        # Create personalized greeting based on documents
        if doc_count == 1:
            greeting_text = f"Hello! I see you've uploaded '{file_name}'. I'm excited to help you learn from this document. Let me take a moment to analyze it and then we can start our conversation. What would you like to explore about this material?"
        else:
            doc_names = [doc["file_name"] for doc in documents]
            greeting_text = f"Great! You now have {doc_count} documents uploaded: {', '.join(doc_names)}. I can help you understand and explore all of these materials. What specific topic or question would you like to start with?"
        
        # Send AI greeting message
        await self._send_message(connection_id, {
            "type": "ai_response",
            "data": {
                "text": greeting_text,
                "auto_generated": True,
                "document_context": True
            }
        })
        
        # Store greeting in conversation history
        if "conversation_history" not in context:
            context["conversation_history"] = []
        
        context["conversation_history"].append({
            "role": "assistant",
            "content": greeting_text,
            "timestamp": asyncio.get_event_loop().time(),
            "type": "greeting"
        })
        
        # Mark greeting as sent to prevent duplicates
        context["greeting_sent"] = True
        await self.redis.setex(context_key, 86400, json.dumps(context))
        
        # Automatically generate and play TTS for greeting
        await self._forward_to_tts_service({
            "type": "synthesize",
            "text": greeting_text,
            "connection_id": connection_id,
            "voice_settings": await self._get_voice_settings(connection_id),
            "auto_play": True
        })
    
    async def _get_conversation_context(self, connection_id: str) -> Dict[str, Any]:
        """Get conversation context for connection"""
        context_key = f"conversation_context:{connection_id}"
        context_data = await self.redis.get(context_key)
        return json.loads(context_data) if context_data else {}
    
    async def _update_conversation_history(self, connection_id: str, role: str, content: str, message_type: str = "message"):
        """Update conversation history with new message"""
        context = await self._get_conversation_context(connection_id)
        
        if "conversation_history" not in context:
            context["conversation_history"] = []
        
        context["conversation_history"].append({
            "role": role,
            "content": content,
            "timestamp": asyncio.get_event_loop().time(),
            "type": message_type
        })
        
        # Keep only last 50 messages to prevent memory bloat
        if len(context["conversation_history"]) > 50:
            context["conversation_history"] = context["conversation_history"][-50:]
        
        context_key = f"conversation_context:{connection_id}"
        await self.redis.setex(context_key, 86400, json.dumps(context))
