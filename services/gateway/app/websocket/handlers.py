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
    
    def __init__(self, connection_manager: ConnectionManager, redis_client: redis.Redis):
        self.connection_manager = connection_manager
        self.redis = redis_client
        self.message_handlers = {
            "auth": self._handle_auth,
            "audio_frame": self._handle_audio_frame,
            "start_session": self._handle_start_session,
            "end_session": self._handle_end_session,
            "ping": self._handle_ping,
            "document_uploaded": self._handle_document_uploaded,
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
        
        if message_type in self.message_handlers:
            await self.message_handlers[message_type](message, connection_id)
        else:
            await self._send_error(connection_id, f"Unknown message type: {message_type}")
    
    async def _handle_auth(self, message: Dict[str, Any], connection_id: str):
        """Handle authentication message"""
        token = message.get("token")
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
            return False
        
        return connection_info.get("authenticated", False)
    
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
        await self.redis.publish("orchestrator_input", json.dumps(message))
    
    async def handle_service_response(self, service: str, response: Dict[str, Any]):
        """Handle responses from backend services"""
        connection_id = response.get("connection_id")
        if not connection_id:
            return
        
        if service == "speech" and response.get("type") == "transcription":
            # Send transcription to chat
            await self._send_message(connection_id, {
                "type": "chat_message",
                "role": "user",
                "content": response.get("text", ""),
                "timestamp": response.get("timestamp", asyncio.get_event_loop().time())
            })
            
            # Forward to orchestrator for AI response
            await self._forward_to_orchestrator({
                "type": "voice_input",
                "text": response.get("text", ""),
                "session_id": response.get("session_id"),
                "connection_id": connection_id
            })
        
        elif service == "orchestrator" and response.get("type") == "ai_response":
            # Send AI response to chat
            await self._send_message(connection_id, {
                "type": "chat_message",
                "role": "assistant",
                "content": response.get("text", ""),
                "timestamp": response.get("timestamp", asyncio.get_event_loop().time())
            })
            
            # Forward to TTS for audio generation
            await self._forward_to_tts_service({
                "type": "synthesize",
                "text": response.get("text", ""),
                "session_id": response.get("session_id"),
                "connection_id": connection_id,
                "voice_settings": await self._get_voice_settings(connection_id)
            })
        
        elif service == "tts" and response.get("type") == "audio_ready":
            # Send audio to client
            await self._send_message(connection_id, {
                "type": "audio_response",
                "audio_url": response.get("audio_url"),
                "audio_data": response.get("audio_data"),
                "session_id": response.get("session_id")
            })
    
    async def _forward_to_tts_service(self, message: Dict[str, Any]):
        """Forward message to TTS service via Redis pub/sub"""
        await self.redis.publish("tts_input", json.dumps(message))
    
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
