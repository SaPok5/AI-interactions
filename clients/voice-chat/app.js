/**
 * Enhanced ChatGPT-Style Voice Assistant Application
 * Real-time voice interaction with document context and live transcription
 * Improved error handling, performance, and user experience
 */

class VoiceAssistantApp {
    constructor() {
        this.ws = null;
        this.mediaRecorder = null;
        this.audioContext = null;
        this.analyser = null;
        this.microphone = null;
        this.dataArray = null;
        this.animationId = null;
        
        // State management
        this.isRecording = false;
        this.isConnected = false;
        this.isProcessingAudio = false;
        this.isAIResponding = false;
        this.uploadedFiles = new Map(); // Use Map for better performance
        this.conversationHistory = [];
        this.transcriptEntries = [];
        this.currentAudioChunks = [];
        
        // Enhanced settings with validation
        this.settings = {
            voice: 'nova',
            speed: 1.0,
            autoPlayback: true,
            showTranscript: true,
            audioQuality: 'high', // low, medium, high
            pushToTalk: true,
            keyboardShortcuts: true,
            maxRetries: 3,
            timeoutDuration: 30000
        };
        
        // Performance tracking
        this.metrics = {
            recordingStartTime: null,
            processingStartTime: null,
            responseTime: null,
            errorCount: 0
        };
        
        // Retry mechanism
        this.retryCount = 0;
        this.maxRetries = 3;
        
        this.initializeElements();
        this.setupEventListeners();
        this.initializeAudioContext();
        this.connectWebSocket();
        this.setupPerformanceMonitoring();
    }
    
    initializeElements() {
        // Connection status
        this.connectionStatus = document.getElementById('connectionStatus');
        this.statusDot = this.connectionStatus?.querySelector('.status-dot');
        this.statusText = this.connectionStatus?.querySelector('.status-text');
        
        // Document upload
        this.documentSection = document.getElementById('documentSection');
        this.uploadArea = document.getElementById('uploadArea');
        this.fileInput = document.getElementById('fileInput');
        this.uploadedFilesContainer = document.getElementById('uploadedFiles');
        
        // Chat interface
        this.conversation = document.getElementById('conversation');
        this.voiceVisualizer = document.getElementById('voiceVisualizer');
        this.voiceButton = document.getElementById('voiceButton');
        this.stopButton = document.getElementById('stopButton');
        this.voiceStatus = document.getElementById('voiceStatus');
        
        // Settings
        this.settingsPanel = document.getElementById('settingsPanel');
        this.settingsToggle = document.getElementById('settingsToggle');
        this.voiceSelect = document.getElementById('voiceSelect');
        this.speedSlider = document.getElementById('speedSlider');
        this.autoPlayback = document.getElementById('autoPlayback');
        this.showTranscript = document.getElementById('showTranscript');
        
        // Transcript
        this.transcriptPanel = document.getElementById('transcriptPanel');
        this.transcriptToggle = document.getElementById('transcriptToggle');
        this.transcriptContent = document.getElementById('transcriptContent');
        this.clearTranscript = document.getElementById('clearTranscript');
        this.exportTranscript = document.getElementById('exportTranscript');
        
        // Audio
        this.audioPlayer = document.getElementById('audioPlayer');
        
        // Validate critical elements exist
        if (!this.voiceButton || !this.conversation) {
            throw new Error('Critical UI elements missing. Please check your HTML structure.');
        }
    }
    
    async initializeAudioContext() {
        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.analyser = this.audioContext.createAnalyser();
            this.analyser.fftSize = 256;
            this.dataArray = new Uint8Array(this.analyser.frequencyBinCount);
        } catch (error) {
            console.error('Failed to initialize audio context:', error);
            this.showError('Audio context initialization failed. Some features may not work.');
        }
    }
    
    setupEventListeners() {
        // Document upload with improved error handling
        this.uploadArea?.addEventListener('click', () => this.fileInput?.click());
        this.uploadArea?.addEventListener('dragover', this.handleDragOver.bind(this));
        this.uploadArea?.addEventListener('dragleave', this.handleDragLeave.bind(this));
        this.uploadArea?.addEventListener('drop', this.handleDrop.bind(this));
        this.fileInput?.addEventListener('change', this.handleFileSelect.bind(this));
        
        // Enhanced voice controls with proper event handling
        this.setupVoiceControls();
        
        // Settings with validation
        this.settingsToggle?.addEventListener('click', this.toggleSettings.bind(this));
        this.voiceSelect?.addEventListener('change', this.updateVoiceSettings.bind(this));
        this.speedSlider?.addEventListener('input', this.updateSpeedSettings.bind(this));
        this.autoPlayback?.addEventListener('change', this.updateSettings.bind(this));
        this.showTranscript?.addEventListener('change', this.toggleTranscriptSetting.bind(this));
        
        // Transcript controls
        this.transcriptToggle?.addEventListener('click', this.toggleTranscript.bind(this));
        this.clearTranscript?.addEventListener('click', this.clearTranscriptHistory.bind(this));
        this.exportTranscript?.addEventListener('click', this.exportTranscriptHistory.bind(this));
        
        // Keyboard shortcuts with improved handling
        document.addEventListener('keydown', this.handleKeyboardShortcuts.bind(this));
        document.addEventListener('keyup', this.handleKeyboardUp.bind(this));
        
        // Audio player events with error recovery
        this.audioPlayer?.addEventListener('ended', this.onAudioEnded.bind(this));
        this.audioPlayer?.addEventListener('error', this.onAudioError.bind(this));
        this.audioPlayer?.addEventListener('loadstart', () => this.updateVoiceStatus('Loading AI response...'));
        
        // Window events for cleanup
        window.addEventListener('beforeunload', this.cleanup.bind(this));
        window.addEventListener('visibilitychange', this.handleVisibilityChange.bind(this));
    }
    
    setupVoiceControls() {
        const events = [
            { type: 'mousedown', handler: this.startRecording },
            { type: 'mouseup', handler: this.stopRecording },
            { type: 'mouseleave', handler: this.stopRecording },
            { type: 'touchstart', handler: this.startRecording },
            { type: 'touchend', handler: this.stopRecording },
            { type: 'touchcancel', handler: this.stopRecording }
        ];
        
        events.forEach(({ type, handler }) => {
            this.voiceButton?.addEventListener(type, (e) => {
                e.preventDefault();
                handler.call(this, e);
            });
        });
        
        this.stopButton?.addEventListener('click', this.forceStop.bind(this));
    }
    
    connectWebSocket() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.close();
        }
        
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.hostname}:8080/ws`;
        
        this.updateConnectionStatus('Connecting...', false);
        
        try {
            this.ws = new WebSocket(wsUrl);
            this.setupWebSocketHandlers();
            
            // Connection timeout
            const connectionTimeout = setTimeout(() => {
                if (this.ws.readyState !== WebSocket.OPEN) {
                    this.ws.close();
                    this.handleConnectionError('Connection timeout');
                }
            }, 10000);
            
            this.ws.onopen = () => {
                clearTimeout(connectionTimeout);
                this.isConnected = true;
                this.retryCount = 0;
                this.updateConnectionStatus('Connected', true);
                this.sendMessage({ 
                    type: 'auth', 
                    session_id: this.generateSessionId(),
                    client_capabilities: this.getClientCapabilities()
                });
            };
            
        } catch (error) {
            console.error('WebSocket connection failed:', error);
            this.handleConnectionError('Failed to connect');
        }
    }
    
    setupWebSocketHandlers() {
        this.ws.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                this.handleWebSocketMessage(message);
            } catch (error) {
                console.error('Failed to parse WebSocket message:', error);
                this.metrics.errorCount++;
            }
        };
        
        this.ws.onclose = (event) => {
            this.isConnected = false;
            this.updateConnectionStatus('Disconnected', false);
            
            // Implement exponential backoff for reconnection
            if (this.retryCount < this.maxRetries) {
                const delay = Math.min(1000 * Math.pow(2, this.retryCount), 10000);
                this.retryCount++;
                this.updateConnectionStatus(`Reconnecting in ${delay/1000}s...`, false);
                setTimeout(() => this.connectWebSocket(), delay);
            } else {
                this.updateConnectionStatus('Connection failed', false);
                this.showError('Unable to connect to server. Please refresh the page.');
            }
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.handleConnectionError('Connection error');
        };
    }
    
    handleConnectionError(message) {
        this.updateConnectionStatus(message, false);
        this.metrics.errorCount++;
    }
    
    getClientCapabilities() {
        return {
            audio: {
                formats: ['webm', 'wav', 'mp3'],
                sampleRate: 16000,
                channels: 1
            },
            features: ['transcript', 'voice_visualization', 'document_context']
        };
    }
    
    handleWebSocketMessage(message) {
        console.log('Received WebSocket message:', message);
        
        // Add message validation
        if (!message.type) {
            console.warn('Invalid message format - missing type:', message);
            return;
        }
        
        switch (message.type) {
            case 'auth_success':
                console.log('Authentication successful');
                this.updateVoiceStatus('Ready - upload a document to begin');
                break;
                
            case 'auth_error':
                console.warn('Authentication error:', message.message);
                this.showError('Authentication failed. Some features may be limited.');
                break;
                
            case 'connection_established':
                console.log('Connection established:', message.connection_id);
                break;
                
            case 'document_processed':
                this.handleDocumentProcessed(message);
                break;
                
            case 'transcription':
                this.handleTranscription(message.data);
                break;
                
            case 'speech_to_text':
                this.handleTranscription(message.data);
                break;
                
            case 'ai_response':
                this.handleAIResponse(message.data);
                break;
                
            case 'audio_response':
                this.handleAudioResponse(message);
                break;
                
            case 'error':
                this.handleError(message);
                break;
                
            case 'processing_status':
                this.updateVoiceStatus(message.data?.status || 'Processing...');
                break;
                
            case 'chat_message':
                this.handleChatMessage(message);
                break;
                
            case 'heartbeat':
                this.sendMessage({ type: 'heartbeat_response' });
                break;
                
            default:
                console.warn('Unknown message type:', message.type, message);
                break;
        }
    }
    
    // File Upload Handling
    handleDragOver(e) {
        e.preventDefault();
        this.documentSection.classList.add('drag-over');
    }
    
    handleDragLeave(e) {
        e.preventDefault();
        this.documentSection.classList.remove('drag-over');
    }
    
    handleDrop(e) {
        e.preventDefault();
        this.documentSection.classList.remove('drag-over');
        const files = Array.from(e.dataTransfer.files);
        this.processFiles(files);
    }
    
    handleFileSelect(e) {
        const files = Array.from(e.target.files);
        this.processFiles(files);
    }
    
    async processFiles(files) {
        // Enhanced file validation with better error messages
        const validTypes = {
            'application/pdf': 'PDF',
            'application/msword': 'DOC',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'DOCX',
            'text/plain': 'TXT',
            'application/rtf': 'RTF',
            'text/markdown': 'MD'
        };
        
        const validFiles = files.filter(file => {
            const isValidType = Object.keys(validTypes).includes(file.type);
            const isValidSize = file.size <= 10 * 1024 * 1024; // 10MB limit
            
            if (!isValidType) {
                this.showError(`Invalid file type: ${file.name}. Supported: ${Object.values(validTypes).join(', ')}`);
                return false;
            }
            
            if (!isValidSize) {
                this.showError(`File too large: ${file.name}. Maximum size: 10MB`);
                return false;
            }
            
            // Check for duplicates
            if (this.uploadedFiles.has(file.name)) {
                this.showError(`File already uploaded: ${file.name}`);
                return false;
            }
            
            return true;
        });
        
        if (validFiles.length === 0) {
            return;
        }
        
        // Process files with progress tracking
        for (const file of validFiles) {
            try {
                await this.handleFileUpload(file);
            } catch (error) {
                console.error('File upload failed:', error);
                this.showError(`Failed to upload ${file.name}: ${error.message}`);
            }
        }
        
        // Enable voice chat after successful upload
        if (this.uploadedFiles.size > 0) {
            this.voiceButton.disabled = false;
            this.updateVoiceStatus('Hold the button to start talking');
        }
    }
    
    async handleFileUpload(file) {
        const fileId = 'file_' + Math.random().toString(36).substr(2, 9);
        const uploadStartTime = Date.now();
        
        try {
            // Show upload progress
            this.updateVoiceStatus(`Processing ${file.name}...`);
            
            // Read file content with progress tracking
            const fileContent = await this.readFileContent(file);
            
            // Add to uploaded files Map for better performance
            this.uploadedFiles.set(fileId, {
                id: fileId,
                name: file.name,
                type: file.type,
                size: file.size,
                content: fileContent,
                uploadTime: Date.now() - uploadStartTime
            });
            
            // Update UI with file size formatting
            this.displayUploadedFile({
                id: fileId,
                name: file.name,
                type: file.type,
                size: this.formatFileSize(file.size),
                uploadTime: Date.now() - uploadStartTime
            });
            
            // Send to backend with retry mechanism
            await this.sendMessageWithRetry({
                type: 'document_upload',
                file_id: fileId,
                file_name: file.name,
                file_type: file.type,
                file_data: fileContent
            });
            
            // Enable voice interaction
            this.voiceButton.disabled = false;
            const labelEl = this.voiceButton.querySelector('.button-text');
            if (labelEl) {
                labelEl.textContent = 'Hold to Talk';
            }
            this.updateVoiceStatus('Document uploaded! AI will greet you shortly...');
            
        } catch (error) {
            console.error('File upload error:', error);
            this.showError(`Failed to upload ${file.name}: ${error.message}`);
            // Remove from uploaded files if it was added
            this.uploadedFiles.delete(fileId);
        }
    }
    
    displayUploadedFile(file) {
        const fileTag = document.createElement('div');
        fileTag.className = 'file-tag';
        fileTag.dataset.fileId = file.id;
        fileTag.innerHTML = `
            <div class="file-info">
                <span class="file-name">${this.escapeHtml(file.name)}</span>
                <span class="file-details">${file.size} • ${file.uploadTime}ms</span>
            </div>
            <button class="remove-file" onclick="app.removeFile('${file.id}')" aria-label="Remove ${this.escapeHtml(file.name)}">×</button>
        `;
        this.uploadedFilesContainer.appendChild(fileTag);
    }
    
    removeFile(fileId) {
        // Remove from Map
        this.uploadedFiles.delete(fileId);
        
        // Remove from UI
        const fileTag = this.uploadedFilesContainer.querySelector(`[data-file-id="${fileId}"]`);
        if (fileTag) {
            fileTag.remove();
        }
        
        // Send removal notification to backend
        this.sendMessage({
            type: 'document_removed',
            file_id: fileId
        });
        
        // Disable voice if no files
        if (this.uploadedFiles.size === 0) {
            this.voiceButton.disabled = true;
            this.updateVoiceStatus('Upload a document to enable voice chat');
        }
    }
    
    // Enhanced Voice Recording Implementation
    async startRecording() {
        if (!this.isConnected || this.uploadedFiles.size === 0 || this.isRecording || this.isProcessingAudio) return;
        
        // Prevent accidental short recordings
        this.metrics.recordingStartTime = Date.now();
        
        try {
            // Enhanced audio constraints based on quality setting
            const audioConstraints = this.getAudioConstraints();
            const stream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints });
            
            // Setup media recorder with fallback MIME types
            const mimeType = this.getSupportedMimeType();
            this.mediaRecorder = new MediaRecorder(stream, { mimeType });
            
            this.currentAudioChunks = [];
            this.isRecording = true;
            
            // Enhanced audio visualization
            if (this.audioContext && this.analyser) {
                this.microphone = this.audioContext.createMediaStreamSource(stream);
                this.microphone.connect(this.analyser);
            }
            
            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.currentAudioChunks.push(event.data);
                }
            };
            
            this.mediaRecorder.onstop = () => {
                this.processRecordedAudio();
                stream.getTracks().forEach(track => track.stop());
                if (this.microphone) {
                    this.microphone.disconnect();
                    this.microphone = null;
                }
            };
            
            this.mediaRecorder.onerror = (error) => {
                console.error('MediaRecorder error:', error);
                this.showError('Recording failed. Please try again.');
                this.stopRecording();
            };
            
            this.mediaRecorder.start(100); // Collect data every 100ms
            this.updateRecordingUI(true);
            this.startVoiceVisualization();
            this.updateVoiceStatus('Listening...');
            
        } catch (error) {
            console.error('Failed to start recording:', error);
            this.handleRecordingError(error);
        }
    }
    
    stopRecording() {
        if (!this.isRecording || !this.mediaRecorder) return;
        
        // Check minimum recording duration to prevent accidental taps
        const recordingDuration = Date.now() - this.metrics.recordingStartTime;
        if (recordingDuration < 500) { // Less than 500ms
            this.updateVoiceStatus('Recording too short - hold longer');
            this.forceStop();
            return;
        }
        
        this.isRecording = false;
        this.updateRecordingUI(false);
        this.stopVoiceVisualization();
        this.updateVoiceStatus('Processing audio...');
        
        this.mediaRecorder.stop();
    }
    
    async processRecordedAudio() {
        if (this.currentAudioChunks.length === 0) {
            this.updateVoiceStatus('No audio recorded');
            return;
        }
        
        try {
            this.metrics.processingStartTime = Date.now();
            
            const audioBlob = new Blob(this.currentAudioChunks, { type: this.getSupportedMimeType() });
            const arrayBuffer = await audioBlob.arrayBuffer();
            const base64Audio = btoa(String.fromCharCode(...new Uint8Array(arrayBuffer)));
            
            // Enhanced message with metadata
            const message = {
                type: 'voice_input',
                audio_data: base64Audio,
                format: this.getSupportedMimeType().split('/')[1].split(';')[0],
                context_files: Array.from(this.uploadedFiles.keys()),
                metadata: {
                    duration: Date.now() - this.metrics.recordingStartTime,
                    quality: this.settings.audioQuality,
                    timestamp: Date.now()
                }
            };
            
            await this.sendMessageWithRetry(message);
            
            this.updateVoiceStatus('Processing your voice...');
            this.isProcessingAudio = true;
            
        } catch (error) {
            console.error('Failed to process audio:', error);
            this.showError('Failed to process audio recording');
            this.updateVoiceStatus('Hold the button to try again');
            this.isProcessingAudio = false;
            this.metrics.errorCount++;
        }
    }
    
    forceStop() {
        // Prevent infinite recursion by directly stopping without calling stopRecording
        if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
            this.isRecording = false;
            this.updateRecordingUI(false);
            this.stopVoiceVisualization();
            this.mediaRecorder.stop();
        }
        
        // Also stop any ongoing AI speech
        this.audioPlayer.pause();
        this.audioPlayer.currentTime = 0;
        this.updateVoiceStatus('Hold the button to start talking');
    }
    
    // Message Handling
    handleTranscription(data) {
        console.log('Processing transcription:', data);
        const userText = data.text || data.transcript || '';
        
        if (userText.trim()) {
            // Show what the user said
            this.addMessage('user', userText);
            this.addTranscriptEntry('You', userText);
            
            // Update status to show transcription received
            this.updateVoiceStatus('Processing your request...');
            // Keep processing flag true since we're waiting for AI response
        } else {
            this.updateVoiceStatus('Could not understand audio - try again');
            this.isProcessingAudio = false;
        }
    }
    
    handleAIResponse(data) {
        console.log('Processing AI response:', data);
        const aiText = data.text;
        const isAutoGenerated = data.auto_generated || false;
        
        this.addMessage('ai', aiText);
        this.addTranscriptEntry('AI Assistant', aiText);
        
        // Always auto-play AI responses for natural conversation flow
        this.requestAudioSynthesis(aiText);
        
        // Reset processing flag
        this.isProcessingAudio = false;
        
        // Update status based on whether this is an auto-generated greeting
        if (isAutoGenerated) {
            this.updateVoiceStatus('AI is greeting you - tap to respond');
        } else {
            this.updateVoiceStatus('Hold the button to continue talking');
        }
    }
    
    async requestAudioSynthesis(text) {
        // Request TTS through WebSocket instead of REST API
        this.sendMessage({
            type: 'tts_request',
            text: text,
            voice: this.settings.voice,
            speed: this.settings.speed
        });
    }
    
    // Track played audio responses to prevent duplicates
    playedAudioResponses = new Set();
    
    handleAudioResponse(message) {
        const data = message.data || message;
        
        // Check for duplicate audio response using message ID if available
        const messageId = message.id || (data.audio_data ? data.audio_data.substring(0, 32) : null);
        if (messageId && this.playedAudioResponses.has(messageId)) {
            console.log('Skipping duplicate audio response:', messageId);
            return;
        }
        
        // Add to played responses set
        if (messageId) {
            this.playedAudioResponses.add(messageId);
            // Clean up old entries to prevent memory leaks
            if (this.playedAudioResponses.size > 100) {
                const firstEntry = this.playedAudioResponses.values().next().value;
                this.playedAudioResponses.delete(firstEntry);
            }
        }
        
        if (data.audio_data) {
            this.playAudio(data.audio_data);
        } else {
            console.warn('Received audio response without audio_data:', message);
            this.isProcessingAudio = false;
            this.updateVoiceStatus('Audio response incomplete');
        }
    }
    
    async playAudio(audioData) {
        try {
            // Prevent overlapping audio playback
            if (this.isProcessingAudio && this.audioPlayer.src) {
                console.log('Audio already playing, stopping current playback');
                this.audioPlayer.pause();
                this.audioPlayer.currentTime = 0;
                
                // Clean up previous audio URL
                if (this.audioPlayer.src && this.audioPlayer.src.startsWith('blob:')) {
                    URL.revokeObjectURL(this.audioPlayer.src);
                }
            }
            
            // Set processing state to prevent new audio requests during playback
            this.isProcessingAudio = true;
            
            // Convert base64 to blob
            const audioBlob = this.base64ToBlob(audioData, 'audio/wav');
            
            // Handle browser autoplay policy restrictions
            // Try to resume audio context if suspended
            if (this.audioContext && this.audioContext.state === 'suspended') {
                await this.audioContext.resume();
            }
            
            // Create object URL for audio playback
            const audioUrl = URL.createObjectURL(audioBlob);
            this.audioPlayer.src = audioUrl;
            
            // Set up playback with proper user interaction handling
            this.updateVoiceStatus('AI is speaking...');
            
            // Add error handling for play promise
            try {
                // For browsers with strict autoplay policies, we might need user interaction
                await this.audioPlayer.play();
            } catch (playError) {
                console.warn('Audio play failed, trying alternative approach:', playError);
                
                // Try to resume audio context and play again
                if (this.audioContext && this.audioContext.state === 'suspended') {
                    try {
                        await this.audioContext.resume();
                        await this.audioPlayer.play();
                    } catch (resumeError) {
                        console.warn('Audio context resume failed:', resumeError);
                    }
                }
                
                // Fallback: try playing after a short delay
                setTimeout(async () => {
                    try {
                        // Ensure audio context is running
                        if (this.audioContext && this.audioContext.state === 'suspended') {
                            await this.audioContext.resume();
                        }
                        await this.audioPlayer.play();
                    } catch (fallbackError) {
                        console.error('Audio playback completely failed:', fallbackError);
                        
                        // Provide user-friendly error message
                        this.updateVoiceStatus('Audio playback blocked - click anywhere to enable sound');
                        
                        // Add a one-time event listener to handle user interaction
                        const handleUserInteraction = async () => {
                            try {
                                if (this.audioContext && this.audioContext.state === 'suspended') {
                                    await this.audioContext.resume();
                                }
                                await this.audioPlayer.play();
                                document.removeEventListener('click', handleUserInteraction);
                                document.removeEventListener('touchstart', handleUserInteraction);
                            } catch (interactionError) {
                                console.error('Audio playback failed after user interaction:', interactionError);
                                this.updateVoiceStatus('Audio playback failed - check browser settings');
                            }
                        };
                        
                        document.addEventListener('click', handleUserInteraction, { once: true });
                        document.addEventListener('touchstart', handleUserInteraction, { once: true });
                        
                        this.isProcessingAudio = false;
                    }
                }, 100);
            }
            
        } catch (error) {
            console.error('Audio setup error:', error);
            this.updateVoiceStatus('Audio processing failed');
            this.isProcessingAudio = false;
        }
    }
    
    onAudioEnded() {
        // After AI finishes speaking, encourage user interaction
        this.updateVoiceStatus('Your turn - hold the button to respond');
        
        // Reset processing state
        this.isProcessingAudio = false;
        
        // Add subtle visual cue that it's user's turn
        this.voiceButton.classList.add('pulse-animation');
        setTimeout(() => {
            this.voiceButton.classList.remove('pulse-animation');
        }, 3000);
    }
    
    onAudioError(error) {
        console.error('Audio playback error:', error);
        this.updateVoiceStatus('Hold the button to start talking');
        
        // Reset processing state on error
        this.isProcessingAudio = false;
    }
    
    handleChatMessage(message) {
        // Handle chat messages from conversation history
        if (message.content && message.content.trim()) {
            this.addMessage(message.role || 'assistant', message.content);
        }
    }
    
    // UI Updates
    addMessage(sender, text) {
        console.log('Adding message to chat:', sender, text);
        
        // Remove welcome message on first real message
        const welcomeMessage = this.conversation.querySelector('.welcome-message');
        if (welcomeMessage) {
            welcomeMessage.remove();
        }
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}`;
        
        const avatar = document.createElement('div');
        avatar.className = `avatar ${sender}-avatar`;
        avatar.innerHTML = sender === 'user' ? 
            '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>' :
            '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>';
        
        const content = document.createElement('div');
        content.className = 'message-content';
        content.textContent = text;
        
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(content);
        
        this.conversation.appendChild(messageDiv);
        this.conversation.scrollTop = this.conversation.scrollHeight;
        
        this.conversationHistory.push({ sender, text, timestamp: new Date() });
    }
    
    addTranscriptEntry(speaker, text) {
        if (!this.settings.showTranscript) return;
        
        const entry = document.createElement('div');
        entry.className = `transcript-entry ${speaker === 'You' ? 'user' : 'ai'}`;
        entry.innerHTML = `
            <div class="speaker">${speaker}:</div>
            <div class="text">${text}</div>
        `;
        
        this.transcriptContent.appendChild(entry);
        this.transcriptContent.scrollTop = this.transcriptContent.scrollHeight;
        
        this.transcriptEntries.push({ speaker, text, timestamp: new Date() });
        
        // Remove placeholder if it exists
        const placeholder = this.transcriptContent.querySelector('.transcript-placeholder');
        if (placeholder) placeholder.remove();
    }
    
    updateConnectionStatus(status, connected) {
        this.statusText.textContent = status;
        this.statusDot.classList.toggle('connected', connected);
    }
    
    updateRecordingUI(recording) {
        this.voiceButton.classList.toggle('recording', recording);
        let labelEl = this.voiceButton.querySelector('.button-text');
        if (!labelEl) {
            labelEl = document.createElement('span');
            labelEl.className = 'button-text';
            this.voiceButton.appendChild(labelEl);
        }
        labelEl.textContent = recording ? 'Release to Send' : 'Hold to Talk';
        this.stopButton.style.display = recording ? 'block' : 'none';
    }
    
    updateVoiceStatus(status) {
        this.voiceStatus.textContent = status;
        
        // Add visual feedback for different states
        this.voiceStatus.className = 'voice-status';
        if (status.includes('Processing') || status.includes('preparing')) {
            this.voiceStatus.classList.add('processing');
        } else if (status.includes('AI is speaking') || status.includes('greeting')) {
            this.voiceStatus.classList.add('ai-speaking');
        } else if (status.includes('Your turn') || status.includes('respond')) {
            this.voiceStatus.classList.add('user-turn');
        }
    }
    
    startVoiceVisualization() {
        this.voiceVisualizer.classList.add('active');
    }
    
    stopVoiceVisualization() {
        this.voiceVisualizer.classList.remove('active');
    }
    
    // Settings Management
    toggleSettings() {
        this.settingsPanel.classList.toggle('open');
    }
    
    updateVoiceSettings() {
        this.settings.voice = this.voiceSelect.value;
    }
    
    updateSpeedSettings() {
        this.settings.speed = parseFloat(this.speedSlider.value);
        document.getElementById('speedValue').textContent = this.settings.speed.toFixed(1);
    }
    
    updateSettings() {
        this.settings.autoPlayback = this.autoPlayback.checked;
        this.settings.showTranscript = this.showTranscript.checked;
    }
    
    toggleTranscript() {
        this.transcriptPanel.classList.toggle('open');
        this.settings.showTranscript = this.showTranscript.checked;
    }
    
    clearTranscriptHistory() {
        this.transcriptEntries = [];
        this.transcriptContent.innerHTML = '<div class="transcript-placeholder">Transcript will appear here...</div>';
    }
    
    exportTranscriptHistory() {
        const transcript = this.transcriptEntries.map(entry => 
            `${entry.speaker}: ${entry.text}`
        ).join('\n\n');
        
        const blob = new Blob([transcript], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `transcript-${new Date().toISOString().split('T')[0]}.txt`;
        a.click();
        URL.revokeObjectURL(url);
    }
    
    // Keyboard Shortcuts
    handleKeyboardShortcuts(e) {
        if (e.ctrlKey || e.metaKey) {
            switch (e.key) {
                case 's':
                    e.preventDefault();
                    this.toggleSettings();
                    break;
                case 't':
                    e.preventDefault();
                    this.toggleTranscript();
                    break;
            }
        }
        
        // Space bar for push-to-talk
        if (e.code === 'Space' && !e.target.matches('input, textarea')) {
            e.preventDefault();
            if (e.type === 'keydown' && !this.isRecording) {
                this.startRecording();
            } else if (e.type === 'keyup' && this.isRecording) {
                this.stopRecording();
            }
        }
    }
    
    // Utility Functions
    generateSessionId() {
        return 'session_' + Math.random().toString(36).substr(2, 16);
    }
    
    sendMessage(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        } else {
            console.warn('WebSocket not connected, cannot send message:', message);
        }
    }
    
    async readFileContent(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }
    
    base64ToBlob(base64, mimeType) {
        const byteCharacters = atob(base64);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
            byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        return new Blob([byteArray], { type: mimeType });
    }
    
    showError(message) {
        console.error('Error:', message);
        // Create a simple error notification
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-notification';
        errorDiv.textContent = message;
        errorDiv.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #ff4444;
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            z-index: 1000;
            font-size: 14px;
            max-width: 300px;
        `;
        
        document.body.appendChild(errorDiv);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (errorDiv.parentNode) {
                errorDiv.parentNode.removeChild(errorDiv);
            }
        }, 5000);
    }
    
    handleError(message) {
        console.error('WebSocket error:', message);
        this.showError(message.message || 'An error occurred');
        this.updateVoiceStatus('Error occurred - try again');
    }

    // Enhanced utility methods
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    getAudioConstraints() {
        const baseConstraints = {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true
        };

        switch (this.settings.audioQuality) {
            case 'high':
                return { ...baseConstraints, sampleRate: 48000, channelCount: 1 };
            case 'medium':
                return { ...baseConstraints, sampleRate: 22050, channelCount: 1 };
            case 'low':
                return { ...baseConstraints, sampleRate: 16000, channelCount: 1 };
            default:
                return { ...baseConstraints, sampleRate: 16000, channelCount: 1 };
        }
    }

    getSupportedMimeType() {
        const types = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/mp4',
            'audio/wav'
        ];

        for (const type of types) {
            if (MediaRecorder.isTypeSupported(type)) {
                return type;
            }
        }
        return 'audio/webm'; // fallback
    }

    handleRecordingError(error) {
        if (error.name === 'NotAllowedError') {
            this.showError('Microphone access denied. Please allow microphone access and try again.');
        } else if (error.name === 'NotFoundError') {
            this.showError('No microphone found. Please connect a microphone and try again.');
        } else {
            this.showError('Failed to access microphone. Please check your audio settings.');
        }
        this.metrics.errorCount++;
    }

    async sendMessageWithRetry(message, retries = 3) {
        for (let i = 0; i < retries; i++) {
            try {
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify(message));
                    return;
                } else {
                    throw new Error('WebSocket not connected');
                }
            } catch (error) {
                if (i === retries - 1) throw error;
                await this.delay(1000 * Math.pow(2, i)); // Exponential backoff
            }
        }
    }

    handleDocumentProcessed(message) {
        console.log('Document processed:', message.file_name);
        this.updateVoiceStatus('Document ready - AI is preparing to greet you...');
    }

    toggleTranscriptSetting() {
        this.settings.showTranscript = this.showTranscript.checked;
        this.transcriptPanel.style.display = this.settings.showTranscript ? 'block' : 'none';
    }

    handleKeyboardUp(e) {
        if (e.code === 'Space' && this.isRecording && !e.target.matches('input, textarea')) {
            e.preventDefault();
            this.stopRecording();
        }
    }

    setupPerformanceMonitoring() {
        // Monitor memory usage
        if (performance.memory) {
            setInterval(() => {
                const memory = performance.memory;
                if (memory.usedJSHeapSize > 50 * 1024 * 1024) { // 50MB
                    console.warn('High memory usage detected:', memory.usedJSHeapSize);
                }
            }, 30000);
        }

        // Limit conversation history to prevent memory leaks
        setInterval(() => {
            if (this.conversationHistory.length > 100) {
                this.conversationHistory = this.conversationHistory.slice(-50);
            }
            if (this.transcriptEntries.length > 100) {
                this.transcriptEntries = this.transcriptEntries.slice(-50);
            }
        }, 60000);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // Enhanced Lifecycle Management
    handleVisibilityChange() {
        if (document.hidden) {
            // Pause operations when tab is hidden
            this.forceStop();
        } else {
            // Resume connection check when tab becomes visible
            if (!this.isConnected) {
                this.connectWebSocket();
            }
        }
    }

    cleanup() {
        console.log('Cleaning up resources...');

        // Stop recording
        this.forceStop();

        // Close WebSocket
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }

        // Close audio context
        if (this.audioContext && this.audioContext.state !== 'closed') {
            this.audioContext.close();
        }

        // Clean up audio URLs
        if (this.audioPlayer?.src) {
            URL.revokeObjectURL(this.audioPlayer.src);
        }

        // Cancel animations
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
        }

        // Clear data
        this.uploadedFiles.clear();
        this.conversationHistory = [];
        this.transcriptEntries = [];
    }

    // Enhanced Error Recovery
    async attemptRecovery() {
        console.log('Attempting system recovery...');

        try {
            // Reset states
            this.isRecording = false;
            this.isProcessingAudio = false;
            this.isAIResponding = false;

            // Reconnect WebSocket
            if (!this.isConnected) {
                this.connectWebSocket();
            }

            // Reinitialize audio context if needed
            if (!this.audioContext || this.audioContext.state === 'closed') {
                await this.initializeAudioContext();
            }

            this.updateVoiceStatus('System recovered - ready to continue');
            this.showSuccess('System recovered successfully');

        } catch (error) {
            console.error('Recovery failed:', error);
            this.showError('Recovery failed. Please refresh the page.');
        }
    }

    // Debug and monitoring methods
    getSystemStatus() {
        return {
            connected: this.isConnected,
            recording: this.isRecording,
            processing: this.isProcessingAudio,
            aiResponding: this.isAIResponding,
            filesUploaded: this.uploadedFiles.size,
            conversationLength: this.conversationHistory.length,
            transcriptLength: this.transcriptEntries.length,
            metrics: this.metrics,
            audioContextState: this.audioContext?.state,
            wsReadyState: this.ws?.readyState
        };
    }

    showSuccess(message) {
        const successDiv = document.createElement('div');
        successDiv.className = 'success-notification';
        successDiv.textContent = message;
        successDiv.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #28a745;
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            z-index: 1000;
            font-size: 14px;
            max-width: 300px;
        `;

        document.body.appendChild(successDiv);

        setTimeout(() => {
            if (successDiv.parentNode) {
                successDiv.parentNode.removeChild(successDiv);
            }
        }, 3000);
    }

    // Initialize settings on startup
    init() {
        this.loadSettings();
        this.updateVoiceStatus('Ready - upload a document to begin');
    }

    loadSettings() {
        try {
            const saved = localStorage.getItem('voiceAssistantSettings');
            if (saved) {
                const settings = JSON.parse(saved);
                this.settings = { ...this.settings, ...settings };
                this.applySettings();
            }
        } catch (error) {
            console.warn('Failed to load settings:', error);
        }
    }

    saveSettings() {
        try {
            localStorage.setItem('voiceAssistantSettings', JSON.stringify(this.settings));
        } catch (error) {
            console.warn('Failed to save settings:', error);
        }
    }

    applySettings() {
        if (this.voiceSelect) this.voiceSelect.value = this.settings.voice;
        if (this.speedSlider) this.speedSlider.value = this.settings.speed;
        if (this.autoPlayback) this.autoPlayback.checked = this.settings.autoPlayback;
        if (this.showTranscript) this.showTranscript.checked = this.settings.showTranscript;
    }
}

// Enhanced initialization with error handling
document.addEventListener('DOMContentLoaded', () => {
    try {
        window.app = new VoiceAssistantApp();
        window.app.init();

        // Add global error handler
        window.addEventListener('error', (e) => {
            console.error('Global error:', e.error);
            if (window.app) {
                window.app.showError('An unexpected error occurred');
                window.app.metrics.errorCount++;
            }
        });

        // Add unhandled promise rejection handler
        window.addEventListener('unhandledrejection', (e) => {
            console.error('Unhandled promise rejection:', e.reason);
            if (window.app) {
                window.app.showError('An unexpected error occurred');
            }
        });

        // Expose debug methods in development
        if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') {
            window.debug = {
                getStatus: () => window.app.getSystemStatus(),
                recover: () => window.app.attemptRecovery(),
                cleanup: () => window.app.cleanup()
            };
        }

    } catch (error) {
        console.error('Failed to initialize application:', error);
        document.body.innerHTML = `
            <div style="padding: 20px; text-align: center; color: #ff4444;">
                <h2>Application Failed to Load</h2>
                <p>Error: ${error.message}</p>
                <button onclick="location.reload()" style="padding: 10px 20px; margin-top: 10px;">
                    Reload Page
                </button>
            </div>
        `;
    }
});

// Enhanced CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }

    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }

    @keyframes pulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.05); }
    }

    .pulse-animation {
        animation: pulse 1.5s ease-in-out infinite;
    }

    .voice-status.processing::after {
        content: '';
        display: inline-block;
        width: 12px;
        height: 12px;
        margin-left: 8px;
        border: 2px solid #ccc;
        border-top: 2px solid #007bff;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    .disabled {
        opacity: 0.5;
        cursor: not-allowed !important;
    }

    .disconnected .voice-button {
        opacity: 0.5;
        pointer-events: none;
    }

    .file-tag {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 12px;
        margin: 4px 0;
        background: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 6px;
    }

    .file-info {
        display: flex;
        flex-direction: column;
        flex: 1;
    }

    .file-name {
        font-weight: 500;
        color: #333;
    }

    .file-details {
        font-size: 0.8em;
        color: #666;
        margin-top: 2px;
    }

    .remove-file {
        background: #dc3545;
        color: white;
        border: none;
        border-radius: 50%;
        width: 24px;
        height: 24px;
        cursor: pointer;
        margin-left: 8px;
    }

    .remove-file:hover {
        background: #c82333;
    }
`;
document.head.appendChild(style);
