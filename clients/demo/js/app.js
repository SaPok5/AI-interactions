/**
 * Main Application Controller
 * Coordinates all modules and manages application lifecycle
 */

class LearningAssistantApp {
    constructor() {
        this.authManager = new AuthManager();
        this.wsManager = new WebSocketManager(this.authManager);
        this.audioManager = new AudioManager();
        this.uiManager = new UIManager(this.authManager, this.wsManager, this.audioManager);
        this.isInitialized = false;
    }

    /**
     * Initialize the application
     */
    async init() {
        console.log('Initializing Learning Assistant App...');
        
        try {
            // Initialize UI first
            this.uiManager.init();
            
            // Setup WebSocket message handlers
            this.setupWebSocketHandlers();
            
            // Check authentication status
            const authResult = await this.authManager.init();
            
            if (authResult.authenticated) {
                // User is already authenticated
                this.uiManager.showMainApp(authResult.user);
                await this.connectWebSocket();
            } else {
                // Show authentication screen
                this.uiManager.showAuthScreen();
            }
            
            this.isInitialized = true;
            console.log('Application initialized successfully');
            
        } catch (error) {
            console.error('Failed to initialize application:', error);
            this.uiManager.showNotification('error', 'Initialization Error', 'Failed to start the application');
        }
    }

    /**
     * Setup WebSocket message handlers
     */
    setupWebSocketHandlers() {
        // Connection status updates
        this.wsManager.onConnectionChange((status) => {
            this.uiManager.updateConnectionStatus(status);
            
            if (status === 'auth_failed') {
                this.uiManager.showNotification('error', 'Authentication Failed', 'Please log in again');
                this.handleLogout();
            }
        });

        // Handle chat messages (both user and AI)
        this.wsManager.onMessage('chat_message', (message) => {
            this.handleChatMessage(message);
        });

        // Handle audio responses
        this.wsManager.onMessage('audio_response', (message) => {
            this.handleAudioResponse(message);
        });

        // Handle voice recording status
        this.wsManager.onMessage('voice_recording_started', (message) => {
            this.handleVoiceRecordingStarted(message);
        });

        this.wsManager.onMessage('voice_recording_stopped', (message) => {
            this.handleVoiceRecordingStopped(message);
        });

        // Handle voice settings updates
        this.wsManager.onMessage('voice_settings_updated', (message) => {
            this.handleVoiceSettingsUpdated(message);
        });

        // Handle document processing updates
        this.wsManager.onMessage('document_processed', (message) => {
            this.handleDocumentProcessed(message);
        });

        // Handle conversation updates
        this.wsManager.onMessage('conversation_update', (message) => {
            this.handleConversationUpdate(message);
        });

        // Handle system messages
        this.wsManager.onMessage('system_message', (message) => {
            this.handleSystemMessage(message);
        });

        // Handle errors
        this.wsManager.onMessage('error', (message) => {
            this.handleServerError(message);
        });

        // Handle workflow status updates
        this.wsManager.onMessage('workflow_status', (message) => {
            this.handleWorkflowStatus(message);
        });
    }

    /**
     * Connect to WebSocket server
     */
    async connectWebSocket() {
        try {
            await this.wsManager.connect();
        } catch (error) {
            console.error('Failed to connect WebSocket:', error);
            this.uiManager.showNotification('error', 'Connection Error', 'Failed to connect to server');
        }
    }

    /**
     * Handle chat messages (both user and AI)
     */
    handleChatMessage(message) {
        const role = message.role || 'assistant';
        const content = message.content || message.text || 'No message content';
        
        // Add message to chat UI
        this.uiManager.addMessage(role, content, 'text');
        
        // Update session stats
        if (role === 'user') {
            this.uiManager.sessionStats.questionsAsked++;
        } else if (role === 'assistant') {
            this.uiManager.sessionStats.responsesReceived++;
        }
        this.uiManager.updateSessionStats();
    }

    /**
     * Handle audio response from AI
     */
    async handleAudioResponse(message) {
        try {
            if (message.audio_data) {
                // Use WebSocket manager's audio playback method for better quality
                await this.wsManager.playAudio(message.audio_data);
            } else if (message.audio_url) {
                // Fetch and play audio from URL
                const response = await fetch(message.audio_url);
                const audioBlob = await response.blob();
                await this.audioManager.playAudio(audioBlob);
            }
            
            // Update UI to show AI is speaking
            this.uiManager.updateVoiceStatus('ai_speaking');
            
        } catch (error) {
            console.error('Failed to play audio response:', error);
            this.uiManager.showNotification('error', 'Audio Error', 'Failed to play audio response');
            this.uiManager.updateVoiceStatus('idle');
        }
    }

    /**
     * Handle voice recording started
     */
    handleVoiceRecordingStarted(message) {
        console.log('Voice recording started:', message);
        this.uiManager.updateVoiceStatus('listening');
    }

    /**
     * Handle voice recording stopped
     */
    handleVoiceRecordingStopped(message) {
        console.log('Voice recording stopped:', message);
        this.uiManager.updateVoiceStatus('processing');
    }

    /**
     * Handle voice settings updated
     */
    handleVoiceSettingsUpdated(message) {
        console.log('Voice settings updated:', message.settings);
        this.uiManager.showNotification('success', 'Settings Updated', 'Voice settings have been updated');
    }

    /**
     * Handle document processing completion
     */
    handleDocumentProcessed(message) {
        const documentName = message.document?.name || 'Document';
        this.uiManager.showNotification('success', 'Document Ready', `${documentName} has been processed and is ready for questions`);
        
        // Update chat title if this is the first document
        if (this.uiManager.uploadedFiles.length === 1) {
            document.getElementById('chatTitle').textContent = `Learning: ${documentName}`;
            document.getElementById('chatSubtitle').textContent = 'Ask questions about your document';
        }
    }

    /**
     * Handle conversation updates
     */
    handleConversationUpdate(message) {
        if (message.summary) {
            // Could show conversation summary or insights
            console.log('Conversation summary:', message.summary);
        }
        
        if (message.suggestions) {
            // Could show suggested follow-up questions
            console.log('Suggested questions:', message.suggestions);
        }
    }

    /**
     * Handle system messages
     */
    handleSystemMessage(message) {
        const type = message.level || 'info';
        const title = message.title || 'System Message';
        const content = message.content || message.message;
        
        this.uiManager.showNotification(type, title, content);
    }

    /**
     * Handle server errors
     */
    handleServerError(message) {
        console.error('Server error:', message);
        
        const errorMessage = message.message || message.error || 'Unknown server error';
        this.uiManager.showNotification('error', 'Server Error', errorMessage);
        
        // Add error message to chat
        this.uiManager.addMessage('assistant', `I apologize, but I encountered an error: ${errorMessage}`, 'text');
    }

    /**
     * Handle workflow status updates
     */
    handleWorkflowStatus(message) {
        console.log('Workflow status:', message);
        
        if (message.status === 'processing') {
            // Could show processing indicator
        } else if (message.status === 'completed') {
            // Could hide processing indicator
        } else if (message.status === 'error') {
            this.handleServerError({ message: message.error || 'Workflow error' });
        }
    }

    /**
     * Play audio response
     */
    async playAudioResponse(audioUrl) {
        try {
            await this.audioManager.playAudio(audioUrl);
        } catch (error) {
            console.error('Failed to play audio:', error);
        }
    }

    /**
     * Convert base64 to blob
     */
    base64ToBlob(base64Data, contentType = '') {
        const byteCharacters = atob(base64Data);
        const byteArrays = [];
        
        for (let offset = 0; offset < byteCharacters.length; offset += 512) {
            const slice = byteCharacters.slice(offset, offset + 512);
            const byteNumbers = new Array(slice.length);
            
            for (let i = 0; i < slice.length; i++) {
                byteNumbers[i] = slice.charCodeAt(i);
            }
            
            const byteArray = new Uint8Array(byteNumbers);
            byteArrays.push(byteArray);
        }
        
        return new Blob(byteArrays, { type: contentType });
    }

    /**
     * Get application settings
     */
    getSettings() {
        const defaultSettings = {
            autoPlay: true,
            interruption: true,
            learningStyle: 'conversational',
            responseDetail: 'detailed'
        };
        
        try {
            const saved = localStorage.getItem('app_settings');
            return saved ? { ...defaultSettings, ...JSON.parse(saved) } : defaultSettings;
        } catch (error) {
            console.error('Failed to load settings:', error);
            return defaultSettings;
        }
    }

    /**
     * Handle logout
     */
    async handleLogout() {
        await this.authManager.logout();
        this.wsManager.disconnect();
        this.audioManager.cleanup();
        this.uiManager.showAuthScreen();
    }

    /**
     * Handle application errors
     */
    handleError(error, context = 'Application') {
        console.error(`${context} error:`, error);
        this.uiManager.showNotification('error', `${context} Error`, error.message || 'An unexpected error occurred');
    }

    /**
     * Cleanup application resources
     */
    cleanup() {
        this.wsManager.disconnect();
        this.audioManager.cleanup();
        console.log('Application cleanup completed');
    }
}

// Global error handler
window.addEventListener('error', (event) => {
    console.error('Global error:', event.error);
    if (window.app) {
        window.app.handleError(event.error, 'Global');
    }
});

// Unhandled promise rejection handler
window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled promise rejection:', event.reason);
    if (window.app) {
        window.app.handleError(event.reason, 'Promise');
    }
});

// Initialize application when DOM is loaded
document.addEventListener('DOMContentLoaded', async () => {
    try {
        window.app = new LearningAssistantApp();
        await window.app.init();
        
        // Make UI manager globally accessible for onclick handlers
        window.ui = window.app.uiManager;
        
    } catch (error) {
        console.error('Failed to start application:', error);
        
        // Show basic error message if UI manager is not available
        const errorDiv = document.createElement('div');
        errorDiv.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: #ef4444;
            color: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            z-index: 10000;
        `;
        errorDiv.innerHTML = `
            <h3>Application Error</h3>
            <p>Failed to start the AI Learning Assistant</p>
            <p style="font-size: 14px; opacity: 0.9;">${error.message}</p>
            <button onclick="location.reload()" style="margin-top: 10px; padding: 8px 16px; background: white; color: #ef4444; border: none; border-radius: 4px; cursor: pointer;">
                Reload Page
            </button>
        `;
        document.body.appendChild(errorDiv);
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.app) {
        window.app.cleanup();
    }
});
