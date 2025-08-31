#!/usr/bin/env python3
"""
Quick WebSocket Gateway for Voice Assistant Demo
Provides immediate connection for the frontend while Docker builds are fixed
"""

import asyncio
import json
import logging
import os
from typing import Dict, Any
import websockets
from websockets.server import WebSocketServerProtocol
import google.generativeai as genai
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure Google API
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', 'AIzaSyDZN8OZn4AcpH7yJBw6qwD0IlGh9jK6qH4')
genai.configure(api_key=GOOGLE_API_KEY)

class VoiceAssistantGateway:
    def __init__(self):
        self.connected_clients: Dict[str, WebSocketServerProtocol] = {}
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        
    async def register_client(self, websocket: WebSocketServerProtocol, session_id: str):
        """Register a new client connection"""
        self.connected_clients[session_id] = websocket
        self.sessions[session_id] = {
            'created_at': datetime.now(),
            'settings': {
                'language': 'auto',
                'model': 'gemini-1.5-flash',
                'voice': 'en-US-Standard-A'
            }
        }
        logger.info(f"Client {session_id} connected")
        
    async def unregister_client(self, session_id: str):
        """Unregister a client connection"""
        if session_id in self.connected_clients:
            del self.connected_clients[session_id]
        if session_id in self.sessions:
            del self.sessions[session_id]
        logger.info(f"Client {session_id} disconnected")
        
    async def send_message(self, session_id: str, message_type: str, payload: Dict[str, Any]):
        """Send message to specific client"""
        if session_id in self.connected_clients:
            websocket = self.connected_clients[session_id]
            message = {
                'type': message_type,
                'payload': payload
            }
            try:
                await websocket.send(json.dumps(message))
            except websockets.exceptions.ConnectionClosed:
                await self.unregister_client(session_id)
                
    async def handle_create_session(self, session_id: str, payload: Dict[str, Any]):
        """Handle session creation"""
        if session_id in self.sessions:
            self.sessions[session_id]['settings'].update(payload)
            
        await self.send_message(session_id, 'session_created', {
            'session_id': session_id,
            'status': 'connected'
        })
        
    async def handle_text_message(self, session_id: str, payload: Dict[str, Any]):
        """Handle text message from user"""
        text = payload.get('text', '')
        if not text:
            return
            
        try:
            # Send to Gemini
            response = await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: self.model.generate_content(text)
            )
            
            response_text = response.text if response.text else "I'm sorry, I couldn't generate a response."
            
            # Send response back
            await self.send_message(session_id, 'llm_response', {
                'text': response_text,
                'confidence': 0.9,
                'model': 'gemini-1.5-flash'
            })
            
            # Send metrics
            await self.send_message(session_id, 'metrics', {
                'responseTime': 800,  # Simulated
                'confidence': 0.9,
                'detectedLanguage': 'English'
            })
            
        except Exception as e:
            logger.error(f"Error processing text message: {e}")
            await self.send_message(session_id, 'error', {
                'message': 'Failed to process your message. Please try again.'
            })
            
    async def handle_audio_data(self, session_id: str, payload: Dict[str, Any]):
        """Handle audio data from user"""
        # For now, simulate transcription
        await self.send_message(session_id, 'transcription_result', {
            'text': 'Hello, this is a simulated transcription. Please use text input for now.',
            'confidence': 0.8,
            'language': 'en'
        })
        
    async def handle_update_settings(self, session_id: str, payload: Dict[str, Any]):
        """Handle settings update"""
        if session_id in self.sessions:
            self.sessions[session_id]['settings'].update(payload)
            
        await self.send_message(session_id, 'settings_updated', {
            'status': 'success'
        })
        
    async def handle_message(self, websocket: WebSocketServerProtocol, session_id: str, message: Dict[str, Any]):
        """Handle incoming WebSocket message"""
        message_type = message.get('type')
        payload = message.get('payload', {})
        
        try:
            if message_type == 'create_session':
                await self.handle_create_session(session_id, payload)
            elif message_type == 'text_message':
                await self.handle_text_message(session_id, payload)
            elif message_type == 'audio_data':
                await self.handle_audio_data(session_id, payload)
            elif message_type == 'update_settings':
                await self.handle_update_settings(session_id, payload)
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except Exception as e:
            logger.error(f"Error handling message {message_type}: {e}")
            await self.send_message(session_id, 'error', {
                'message': f'Error processing {message_type}'
            })

    async def handle_client(self, websocket: WebSocketServerProtocol, path: str):
        """Handle new client connection"""
        session_id = f"session_{len(self.connected_clients)}"
        await self.register_client(websocket, session_id)
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self.handle_message(websocket, session_id, data)
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                    await self.send_message(session_id, 'error', {
                        'message': 'Invalid message format'
                    })
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister_client(session_id)

async def main():
    """Start the WebSocket server"""
    gateway = VoiceAssistantGateway()
    
    logger.info("Starting Voice Assistant Gateway on ws://localhost:8080/ws")
    
    async with websockets.serve(
        gateway.handle_client,
        "localhost",
        8080,
        subprotocols=["echo-protocol"]
    ):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Gateway stopped by user")
    except Exception as e:
        logger.error(f"Gateway error: {e}")
