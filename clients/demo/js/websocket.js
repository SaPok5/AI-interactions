/**
 * WebSocket Manager
 * Handles real-time communication with the backend gateway service
 */

class WebSocketManager {
    constructor(authManager) {
        this.authManager = authManager;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.isConnecting = false;
        this.messageHandlers = new Map();
        this.connectionListeners = [];
        this.sessionId = this.generateSessionId();
        this.isAuthenticated = false;
        this.pendingQueue = [];
        // Sequence counter for audio frames
        this.audioSeq = 0;
    }

    /**
     * Connect to WebSocket server
     */
    async connect() {
        if (this.isConnecting || (this.ws && this.ws.readyState === WebSocket.OPEN)) {
            return;
        }

        this.isConnecting = true;
        
        try {
            // Get auth token if available
            const token = this.authManager ? this.authManager.getToken() : null;
            const wsUrl = token ? `ws://localhost:8080/ws?token=${token}` : 'ws://localhost:8080/ws';
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.log('WebSocket connected');
                this.isConnecting = false;
                this.reconnectAttempts = 0;
                this.isAuthenticated = false;
                this.notifyConnectionChange('connected');
                
                // Authenticate the connection
                this.authenticate();
            };

            this.ws.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    this.handleMessage(message);
                } catch (error) {
                    console.error('Error parsing WebSocket message:', error);
                }
            };

            this.ws.onclose = (event) => {
                console.log('WebSocket disconnected:', event.code, event.reason);
                this.isConnecting = false;
                this.isAuthenticated = false;
                this.notifyConnectionChange('disconnected');
                
                // Attempt to reconnect if not a clean close
                if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.scheduleReconnect();
                }
            };

            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.isConnecting = false;
                this.isAuthenticated = false;
                this.notifyConnectionChange('error');
            };

        } catch (error) {
            console.error('Failed to create WebSocket connection:', error);
            this.isConnecting = false;
            this.notifyConnectionChange('error');
        }
    }

    /**
     * Authenticate WebSocket connection
     */
    authenticate() {
        if (!this.authManager.isAuthenticated()) {
            console.error('Cannot authenticate WebSocket: user not logged in');
            return;
        }

        const authMessage = {
            type: 'auth',
            token: this.authManager.getToken(),
            session_id: this.sessionId,
            user_id: this.authManager.getCurrentUser()?.id
        };

        this.send(authMessage);
    }

    /**
     * Send message through WebSocket
     */
    send(message) {
        // Always include session_id
        const messageWithSession = { ...message, session_id: this.sessionId };

        // Allow auth message to go through as soon as socket is open
        const isAuthMessage = messageWithSession.type === 'auth';

        // If socket not open, enqueue and try to connect
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.warn('WebSocket not connected, queuing message');
            this.pendingQueue.push(messageWithSession);
            if (!this.isConnecting) {
                this.connect();
            }
            return false;
        }

        // If not authenticated yet, queue non-auth messages until auth completes
        if (!this.isAuthenticated && !isAuthMessage) {
            console.warn('WebSocket not authenticated, queuing message');
            this.pendingQueue.push(messageWithSession);
            return false;
        }

        try {
            this.ws.send(JSON.stringify(messageWithSession));
            return true;
        } catch (error) {
            console.error('Error sending WebSocket message:', error);
            return false;
        }
    }

    /**
     * Handle incoming messages
     */
    handleMessage(message) {
        console.log('Received WebSocket message:', message);

        // Handle authentication response
        if (message.type === 'auth_success') {
            console.log('WebSocket authentication successful');
            this.isAuthenticated = true;
            this.notifyConnectionChange('authenticated');
            this.flushQueue();
            return;
        }

        // Handle authentication error explicitly
        if (message.type === 'auth_error') {
            console.error('WebSocket authentication failed');
            this.isAuthenticated = false;
            this.notifyConnectionChange('auth_failed');
            return;
        }

        // Route message to registered handlers
        const handlers = this.messageHandlers.get(message.type) || [];
        handlers.forEach(handler => {
            try {
                handler(message);
            } catch (error) {
                console.error(`Error in message handler for ${message.type}:`, error);
            }
        });

        // Handle generic message types
        if (message.type === 'error') {
            console.error('Server error:', message);
            this.notifyError(message.message || 'Unknown server error');
        }
    }

    /**
     * Register message handler
     */
    onMessage(type, handler) {
        if (!this.messageHandlers.has(type)) {
            this.messageHandlers.set(type, []);
        }
        this.messageHandlers.get(type).push(handler);
    }

    /**
     * Remove message handler
     */
    offMessage(type, handler) {
        const handlers = this.messageHandlers.get(type);
        if (handlers) {
            const index = handlers.indexOf(handler);
            if (index > -1) {
                handlers.splice(index, 1);
            }
        }
    }

    /**
     * Add connection listener
     */
    onConnectionChange(listener) {
        this.connectionListeners.push(listener);
    }

    /**
     * Remove connection listener
     */
    offConnectionChange(listener) {
        const index = this.connectionListeners.indexOf(listener);
        if (index > -1) {
            this.connectionListeners.splice(index, 1);
        }
    }

    /**
     * Notify connection change
     */
    notifyConnectionChange(status) {
        this.connectionListeners.forEach(listener => {
            try {
                listener(status);
            } catch (error) {
                console.error('Error in connection listener:', error);
            }
        });
    }

    /**
     * Notify error
     */
    notifyError(message) {
        const errorHandlers = this.messageHandlers.get('error') || [];
        errorHandlers.forEach(handler => {
            try {
                handler({ type: 'error', message });
            } catch (error) {
                console.error('Error in error handler:', error);
            }
        });
    }

    /**
     * Flush queued messages after connection/authentication
     */
    flushQueue() {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.warn('flushQueue called but socket not open; leaving queue intact');
            return;
        }
        if (!this.isAuthenticated) {
            console.warn('flushQueue called but not authenticated; leaving queue intact');
            return;
        }
        if (!this.pendingQueue.length) return;

        const queue = this.pendingQueue;
        this.pendingQueue = [];
        console.log(`Flushing ${queue.length} queued message(s)`);
        for (const msg of queue) {
            try {
                this.ws.send(JSON.stringify(msg));
            } catch (err) {
                console.error('Failed to send queued message, re-queuing', err);
                this.pendingQueue.push(msg);
                // If send fails, break to avoid spinning
                break;
            }
        }
    }

    /**
     * Schedule reconnection
     */
    scheduleReconnect() {
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
        
        console.log(`Scheduling reconnect attempt ${this.reconnectAttempts} in ${delay}ms`);
        
        setTimeout(() => {
            if (this.reconnectAttempts <= this.maxReconnectAttempts) {
                this.connect();
            } else {
                console.error('Max reconnection attempts reached');
                this.notifyConnectionChange('failed');
            }
        }, delay);
    }

    /**
     * Disconnect WebSocket
     */
    disconnect() {
        if (this.ws) {
            this.ws.close(1000, 'Client disconnect');
            this.ws = null;
        }
        this.reconnectAttempts = this.maxReconnectAttempts; // Prevent reconnection
    }

    /**
     * Get connection status
     */
    getConnectionStatus() {
        if (!this.ws) return 'disconnected';
        
        switch (this.ws.readyState) {
            case WebSocket.CONNECTING:
                return 'connecting';
            case WebSocket.OPEN:
                return 'connected';
            case WebSocket.CLOSING:
                return 'closing';
            case WebSocket.CLOSED:
                return 'disconnected';
            default:
                return 'unknown';
        }
    }

    /**
     * Whether the WebSocket is open and authenticated
     */
    isConnected() {
        return !!(this.ws && this.ws.readyState === WebSocket.OPEN && this.isAuthenticated);
    }

    /**
     * Generate unique session ID
     */
    generateSessionId() {
        return 'session_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
    }

    /**
     * Send audio data for processing
     */
    sendAudio(audioBlob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                const audioData = Array.from(new Uint8Array(reader.result));
                
                const message = {
                    type: 'audio_frame',
                    payload: audioData,
                    format: 'webm',
                    seq: ++this.audioSeq,
                    timestamp: Date.now()
                };

                if (this.send(message)) {
                    resolve();
                } else {
                    reject(new Error('Failed to send audio data'));
                }
            };
            reader.onerror = () => reject(new Error('Failed to read audio blob'));
            reader.readAsArrayBuffer(audioBlob);
        });
    }

    /**
     * Send text message
     */
    sendText(text) {
        const message = {
            type: 'text',
            text: text,  // Changed from 'content' to 'text' to match backend
            timestamp: Date.now()
        };

        return this.send(message);
    }

    /**
     * Send voice recording start notification
     */
    sendVoiceStart() {
        const message = {
            type: 'voice_start',
            timestamp: Date.now()
        };

        return this.send(message);
    }

    /**
     * Send voice recording stop notification
     */
    sendVoiceStop() {
        const message = {
            type: 'voice_stop',
            timestamp: Date.now()
        };

        return this.send(message);
    }

    /**
     * Send document upload notification
     */
    sendDocumentUploaded(documentInfo) {
        const message = {
            type: 'document_uploaded',
            document: documentInfo,
            timestamp: Date.now()
        };

        return this.send(message);
    }

    /**
     * Send voice settings update
     */
    sendVoiceSettings(settings) {
        const message = {
            type: 'voice_settings',
            settings: settings,
            timestamp: Date.now()
        };

        return this.send(message);
    }

    /**
     * Play audio from base64 data
     */
    async playAudio(audioData) {
        try {
            // Convert base64 to blob
            const audioBlob = this.base64ToBlob(audioData, 'audio/wav');
            const audioUrl = URL.createObjectURL(audioBlob);
            
            // Create audio element
            const audio = new Audio(audioUrl);
            audio.volume = 0.8;
            
            // Play audio
            await audio.play();
            
            // Clean up URL after playing
            audio.addEventListener('ended', () => {
                URL.revokeObjectURL(audioUrl);
            });
            
            return audio;
        } catch (error) {
            console.error('Error playing audio:', error);
            throw error;
        }
    }

    /**
     * Convert base64 to blob
     */
    base64ToBlob(base64, mimeType) {
        const byteCharacters = atob(base64);
        const byteNumbers = new Array(byteCharacters.length);
        
        for (let i = 0; i < byteCharacters.length; i++) {
            byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        
        const byteArray = new Uint8Array(byteNumbers);
        return new Blob([byteArray], { type: mimeType });
    }
}

// Export for use in other modules
window.WebSocketManager = WebSocketManager;
