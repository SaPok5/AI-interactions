"""WebSocket connection manager"""

import asyncio
import uuid
from typing import Dict, Set
from fastapi import WebSocket
import structlog

from ..middleware.metrics import record_websocket_connection, record_websocket_disconnection

logger = structlog.get_logger(__name__)


class ConnectionManager:
    """Manages WebSocket connections"""
    
    def __init__(self):
        self.active_connections: Dict[str, Dict] = {}
        self.user_sessions: Dict[str, Set[str]] = {}  # user_id -> set of connection_ids
    
    async def connect(self, websocket: WebSocket, connection_id: str, token: str = None):
        """Accept a new WebSocket connection with optional JWT token"""
        await websocket.accept()
        
        # Verify JWT token if provided
        user_id = None
        if token:
            try:
                import jwt
                from ..config import settings
                payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
                # Support common claim names
                user_id = payload.get("sub") or payload.get("user_id") or payload.get("uid")
                logger.info("WebSocket authenticated", connection_id=connection_id, user_id=user_id)
            except Exception as e:
                logger.warning("WebSocket token verification failed", error=str(e))
        
        # Store connection info
        connection_info = {
            "websocket": websocket,
            "connected_at": asyncio.get_event_loop().time(),
            "last_activity": asyncio.get_event_loop().time(),
            "user_id": user_id,
            "authenticated": user_id is not None
        }
        
        self.active_connections[connection_id] = connection_info
        
        logger.info("WebSocket connection established", connection_id=connection_id, authenticated=user_id is not None)
        
        # Send connection confirmation
        await self.send_personal_message({
            "type": "connection_established",
            "connection_id": connection_id,
            "authenticated": user_id is not None
        }, connection_id)
        
        # Record metrics
        record_websocket_connection()
    
    async def disconnect(self, connection_id: str):
        """Disconnect and cleanup a WebSocket connection"""
        if connection_id in self.active_connections:
            connection_info = self.active_connections.pop(connection_id)
            websocket = connection_info["websocket"]
            
            # Remove from user sessions and cleanup empty sets
            user_ids_to_remove = []
            for user_id, connections in self.user_sessions.items():
                connections.discard(connection_id)
                if not connections:  # Remove empty user sessions
                    user_ids_to_remove.append(user_id)
            
            for user_id in user_ids_to_remove:
                del self.user_sessions[user_id]
            
            # Record metrics
            record_websocket_disconnection()
            
            logger.info("WebSocket connection closed", connection_id=connection_id)
    
    async def disconnect_all(self):
        """Disconnect all active connections"""
        for connection_id in list(self.active_connections.keys()):
            await self.disconnect(connection_id)
    
    def associate_user(self, connection_id: str, user_id: str):
        """Associate a connection with a user"""
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = set()
        self.user_sessions[user_id].add(connection_id)
        
        logger.info("Connection associated with user", 
                   connection_id=connection_id, user_id=user_id)
    
    async def send_personal_message(self, message: dict, connection_id: str):
        """Send a message to a specific connection"""
        if connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]["websocket"]
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error("Failed to send message", 
                           connection_id=connection_id, error=str(e))
                await self.disconnect(connection_id)
    
    async def send_message(self, connection_id: str, message: dict):
        """Alias for send_personal_message for backward compatibility"""
        await self.send_personal_message(message, connection_id)
    
    async def send_to_user(self, message: dict, user_id: str):
        """Send a message to all connections of a user"""
        if user_id in self.user_sessions:
            connections = self.user_sessions[user_id].copy()
            for connection_id in connections:
                await self.send_personal_message(message, connection_id)
    
    async def broadcast(self, message: dict):
        """Broadcast a message to all active connections"""
        if self.active_connections:
            tasks = []
            for connection_id in list(self.active_connections.keys()):
                tasks.append(self.send_personal_message(message, connection_id))
            await asyncio.gather(*tasks, return_exceptions=True)
    
    def get_connection_count(self) -> int:
        """Get total number of active connections"""
        return len(self.active_connections)
    
    def get_user_connections(self, user_id: str) -> Set[str]:
        """Get all connection IDs for a user"""
        return self.user_sessions.get(user_id, set())
