/**
 * UI Manager
 * Handles all user interface interactions and updates
 */

class UIManager {
    constructor(authManager, wsManager, audioManager) {
        this.authManager = authManager;
        this.wsManager = wsManager;
        this.audioManager = audioManager;
        this.currentScreen = 'loading';
        this.uploadedFiles = [];
        this.sessionStats = {
            questionsAsked: 0,
            sessionStartTime: Date.now(),
            documentsProcessed: 0
        };
        this.voiceEnabled = false;
        this.isVoiceActive = false;
        this.hasGreeted = false;
        
        // Initialize UI element references
        this.initializeElements();
    }
    
    /**
     * Initialize UI element references
     */
    initializeElements() {
        // Chat interface elements
        this.chatInterface = document.getElementById('chatInterface');
        this.chatMessages = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.exportChatBtn = document.getElementById('exportChatBtn');
        this.clearChatBtn = document.getElementById('clearChatBtn');
        
        // Conversation mode elements
        this.generalModeBtn = document.getElementById('generalModeBtn');
        this.documentModeBtn = document.getElementById('documentModeBtn');
        this.currentMode = 'general';
    }

    /**
     * Initialize UI
     */
    init() {
        this.setupEventListeners();
        this.setupNotifications();
        this.updateSessionTimer();
        
        // Initialize audio visualization
        this.audioManager.setVisualizationCallback((amplitude, data) => {
            this.updateVoiceVisualizer(amplitude);
        });
        
        // Show welcome screen initially
        this.showWelcomeScreen();
    }

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // Authentication tabs
        document.querySelectorAll('.auth-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                this.switchAuthTab(e.target.dataset.tab);
            });
        });

        // Authentication forms
        document.getElementById('loginForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleLogin();
        });

        document.getElementById('registerForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleRegister();
        });

        // User menu
        document.getElementById('userMenuBtn').addEventListener('click', () => {
            this.toggleUserDropdown();
        });

        document.getElementById('logoutBtn').addEventListener('click', () => {
            this.handleLogout();
        });

        document.getElementById('settingsBtn').addEventListener('click', () => {
            this.showSettingsModal();
        });

        // File upload
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');

        uploadArea.addEventListener('click', () => fileInput.click());
        uploadArea.addEventListener('dragover', this.handleDragOver.bind(this));
        uploadArea.addEventListener('dragleave', this.handleDragLeave.bind(this));
        uploadArea.addEventListener('drop', this.handleFileDrop.bind(this));
        fileInput.addEventListener('change', this.handleFileSelect.bind(this));

        // Voice controls
        document.getElementById('voiceToggle').addEventListener('change', (e) => {
            this.toggleVoiceMode(e.target.checked);
        });

        document.getElementById('voiceSpeed').addEventListener('input', (e) => {
            this.updateVoiceSpeed(e.target.value);
        });

        document.getElementById('voiceType').addEventListener('change', (e) => {
            this.updateVoiceType(e.target.value);
        });

        // Chat interface (with null checks)
        if (this.sendBtn) {
            this.sendBtn.addEventListener('click', () => this.sendMessage());
        }
        if (this.messageInput) {
            this.messageInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }
        if (this.exportChatBtn) {
            this.exportChatBtn.addEventListener('click', () => this.exportChat());
        }
        if (this.clearChatBtn) {
            this.clearChatBtn.addEventListener('click', () => this.clearChat());
        }
        
        // Conversation mode listeners (with null checks)
        if (this.generalModeBtn) {
            this.generalModeBtn.addEventListener('click', () => this.setConversationMode('general'));
        }
        if (this.documentModeBtn) {
            this.documentModeBtn.addEventListener('click', () => this.setConversationMode('document'));
        }
        
        // Auto-resize textarea (with null check)
        if (this.messageInput) {
            this.messageInput.addEventListener('input', () => this.autoResizeTextarea());
        }

        const voiceBtn = document.getElementById('voiceBtn');
        if (voiceBtn) {
            voiceBtn.addEventListener('click', () => {
                this.toggleVoiceRecording();
            });
        }

        // Close dropdowns when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.user-menu')) {
                this.hideUserDropdown();
            }
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.code === 'Space') {
                e.preventDefault();
                this.toggleVoiceRecording();
            }
            if (e.key === 'Escape') {
                this.stopVoiceRecording();
            }
        });
    }

    /**
     * Show loading screen
     */
    showLoadingScreen() {
        this.hideAllScreens();
        document.getElementById('loadingScreen').classList.remove('hidden');
        this.currentScreen = 'loading';
    }

    /**
     * Show welcome screen inside main app
     */
    showWelcomeScreen() {
        // Ensure only the main app is visible
        this.hideAllScreens();
        document.getElementById('mainApp').classList.remove('hidden');

        // Show welcome screen and hide chat interface
        const welcome = document.getElementById('welcomeScreen');
        const chat = document.getElementById('chatInterface');
        if (welcome) welcome.classList.remove('hidden');
        if (chat) chat.classList.add('hidden');

        // Wire quick action buttons if present
        const uploadQuickBtn = document.getElementById('uploadQuickBtn');
        if (uploadQuickBtn && !uploadQuickBtn._bound) {
            uploadQuickBtn.addEventListener('click', () => {
                const uploadArea = document.getElementById('uploadArea');
                if (uploadArea) uploadArea.scrollIntoView({ behavior: 'smooth', block: 'center' });
            });
            uploadQuickBtn._bound = true;
        }

        const startChatBtn = document.getElementById('startChatBtn');
        if (startChatBtn && !startChatBtn._bound) {
            startChatBtn.addEventListener('click', () => this.showChatInterface());
            startChatBtn._bound = true;
        }

        this.currentScreen = 'welcome';
    }

    /**
     * Show authentication screen
     */
    showAuthScreen() {
        this.hideAllScreens();
        document.getElementById('authScreen').classList.remove('hidden');
        this.currentScreen = 'auth';
    }

    /**
     * Show main application
     */
    showMainApp(user) {
        this.hideAllScreens();
        document.getElementById('mainApp').classList.remove('hidden');
        document.getElementById('userName').textContent = user.name || user.email;
        this.currentScreen = 'main';
        
        // Reset session stats
        this.sessionStats.sessionStartTime = Date.now();
        this.updateSessionStats();
    }

    /**
     * Hide all screens
     */
    hideAllScreens() {
        document.getElementById('loadingScreen').classList.add('hidden');
        document.getElementById('authScreen').classList.add('hidden');
        document.getElementById('mainApp').classList.add('hidden');
    }

    /**
     * Switch authentication tab
     */
    switchAuthTab(tab) {
        // Update tab buttons
        document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
        document.querySelector(`[data-tab="${tab}"]`).classList.add('active');

        // Update forms
        document.getElementById('loginForm').classList.toggle('hidden', tab !== 'login');
        document.getElementById('registerForm').classList.toggle('hidden', tab !== 'register');

        // Clear error
        this.hideAuthError();
    }

    /**
     * Handle login
     */
    async handleLogin() {
        const email = document.getElementById('loginEmail').value;
        const password = document.getElementById('loginPassword').value;

        if (!email || !password) {
            this.showAuthError('Please fill in all fields');
            return;
        }

        this.setAuthLoading(true);
        
        const result = await this.authManager.login(email, password);
        
        this.setAuthLoading(false);

        if (result.success) {
            this.showMainApp(result.user);
            this.showNotification('success', 'Welcome back!', 'Successfully logged in');
        } else {
            this.showAuthError(result.error);
        }
    }

    /**
     * Handle registration
     */
    async handleRegister() {
        const name = document.getElementById('registerName').value;
        const email = document.getElementById('registerEmail').value;
        const password = document.getElementById('registerPassword').value;
        const confirmPassword = document.getElementById('confirmPassword').value;

        if (!name || !email || !password || !confirmPassword) {
            this.showAuthError('Please fill in all fields');
            return;
        }

        if (password !== confirmPassword) {
            this.showAuthError('Passwords do not match');
            return;
        }

        if (password.length < 6) {
            this.showAuthError('Password must be at least 6 characters');
            return;
        }

        this.setAuthLoading(true);
        
        const result = await this.authManager.register(name, email, password);
        
        this.setAuthLoading(false);

        if (result.success) {
            this.showMainApp(result.user);
            this.showNotification('success', 'Welcome!', 'Account created successfully');
        } else {
            this.showAuthError(result.error);
        }
    }

    /**
     * Handle logout
     */
    async handleLogout() {
        await this.authManager.logout();
        this.wsManager.disconnect();
        this.audioManager.cleanup();
        this.showAuthScreen();
        this.showNotification('success', 'Logged out', 'You have been logged out successfully');
    }

    /**
     * Show authentication error
     */
    showAuthError(message) {
        const errorEl = document.getElementById('authError');
        errorEl.textContent = message;
        errorEl.classList.remove('hidden');
    }

    /**
     * Hide authentication error
     */
    hideAuthError() {
        document.getElementById('authError').classList.add('hidden');
    }

    /**
     * Set authentication loading state
     */
    setAuthLoading(loading) {
        const loginBtn = document.querySelector('#loginForm .auth-btn');
        const registerBtn = document.querySelector('#registerForm .auth-btn');
        
        [loginBtn, registerBtn].forEach(btn => {
            btn.disabled = loading;
            btn.innerHTML = loading ? 
                '<i class="fas fa-spinner fa-spin"></i> Please wait...' :
                btn.dataset.originalText || btn.innerHTML;
        });

        if (!loading) {
            loginBtn.innerHTML = '<i class="fas fa-sign-in-alt"></i> Sign In';
            registerBtn.innerHTML = '<i class="fas fa-user-plus"></i> Create Account';
        }
    }

    /**
     * Update connection status
     */
    updateConnectionStatus(status) {
        const dot = document.getElementById('connectionDot');
        const text = document.getElementById('connectionText');

        dot.className = 'status-dot';
        
        switch (status) {
            case 'connected':
                dot.classList.add('connected');
                text.textContent = 'Connected';
                break;
            case 'connecting':
                text.textContent = 'Connecting...';
                break;
            case 'authenticated':
                dot.classList.add('connected');
                text.textContent = 'Ready';
                break;
            case 'disconnected':
                dot.classList.add('disconnected');
                text.textContent = 'Disconnected';
                break;
            case 'error':
            case 'failed':
                dot.classList.add('disconnected');
                text.textContent = 'Connection Failed';
                break;
            default:
                text.textContent = 'Unknown';
        }
    }

    /**
     * Toggle user dropdown
     */
    toggleUserDropdown() {
        document.getElementById('userDropdown').classList.toggle('hidden');
    }

    /**
     * Hide user dropdown
     */
    hideUserDropdown() {
        document.getElementById('userDropdown').classList.add('hidden');
    }

    /**
     * Handle file drag over
     */
    handleDragOver(e) {
        e.preventDefault();
        e.currentTarget.classList.add('dragover');
    }

    /**
     * Handle file drag leave
     */
    handleDragLeave(e) {
        e.preventDefault();
        e.currentTarget.classList.remove('dragover');
    }

    /**
     * Handle file drop
     */
    handleFileDrop(e) {
        e.preventDefault();
        e.currentTarget.classList.remove('dragover');
        
        const files = Array.from(e.dataTransfer.files);
        this.processFiles(files);
    }

    /**
     * Handle file select
     */
    handleFileSelect(e) {
        const files = Array.from(e.target.files);
        this.processFiles(files);
    }

    /**
     * Process uploaded files
     */
    async processFiles(files) {
        const allowedTypes = ['.pdf', '.doc', '.docx', '.txt'];
        const maxSize = 10 * 1024 * 1024; // 10MB

        for (const file of files) {
            const extension = '.' + file.name.split('.').pop().toLowerCase();
            
            if (!allowedTypes.includes(extension)) {
                this.showNotification('error', 'Invalid file type', `${file.name} is not supported`);
                continue;
            }

            if (file.size > maxSize) {
                this.showNotification('error', 'File too large', `${file.name} exceeds 10MB limit`);
                continue;
            }

            await this.uploadFile(file);
        }
    }

    /**
     * Upload file
     */
    async uploadFile(file) {
        const fileInfo = {
            id: Date.now() + '_' + Math.random().toString(36).substr(2, 9),
            name: file.name,
            size: file.size,
            type: file.type,
            uploadTime: new Date()
        };

        // Add to file list UI
        this.addFileToList(fileInfo);

        try {
            // Simulate file upload (replace with actual upload logic)
            await this.simulateFileUpload(file, fileInfo);
            
            this.uploadedFiles.push(fileInfo);
            this.sessionStats.documentsProcessed++;
            this.updateSessionStats();
            
            // Notify WebSocket
            this.wsManager.sendDocumentUploaded(fileInfo);
            
            this.showNotification('success', 'File uploaded', `${file.name} processed successfully`);
        } catch (error) {
            this.showNotification('error', 'Upload failed', `Failed to process ${file.name}`);
            this.removeFileFromList(fileInfo.id);
        }
    }

    /**
     * Simulate file upload with progress
     */
    simulateFileUpload(file, fileInfo) {
        return new Promise((resolve, reject) => {
            // Simulate processing time
            setTimeout(() => {
                if (Math.random() > 0.1) { // 90% success rate
                    resolve();
                } else {
                    reject(new Error('Processing failed'));
                }
            }, 2000 + Math.random() * 3000);
        });
    }

    /**
     * Add file to list
     */
    addFileToList(fileInfo) {
        const fileList = document.getElementById('fileList');
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        fileItem.dataset.fileId = fileInfo.id;
        
        const extension = fileInfo.name.split('.').pop().toLowerCase();
        const iconMap = {
            'pdf': 'fas fa-file-pdf',
            'doc': 'fas fa-file-word',
            'docx': 'fas fa-file-word',
            'txt': 'fas fa-file-alt'
        };
        
        fileItem.innerHTML = `
            <div class="file-icon">
                <i class="${iconMap[extension] || 'fas fa-file'}"></i>
            </div>
            <div class="file-info">
                <div class="file-name">${fileInfo.name}</div>
                <div class="file-size">${this.formatFileSize(fileInfo.size)}</div>
            </div>
            <div class="file-actions">
                <button class="file-action delete" onclick="ui.removeFile('${fileInfo.id}')" title="Remove">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
        
        fileList.appendChild(fileItem);
    }

    /**
     * Remove file from list
     */
    removeFileFromList(fileId) {
        const fileItem = document.querySelector(`[data-file-id="${fileId}"]`);
        if (fileItem) {
            fileItem.remove();
        }
    }

    /**
     * Remove file
     */
    removeFile(fileId) {
        this.removeFileFromList(fileId);
        this.uploadedFiles = this.uploadedFiles.filter(f => f.id !== fileId);
        this.sessionStats.documentsProcessed = Math.max(0, this.sessionStats.documentsProcessed - 1);
        this.updateSessionStats();
        this.showNotification('success', 'File removed', 'Document removed from session');
    }

    /**
     * Format file size
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    /**
     * Toggle voice mode
     */
    async toggleVoiceMode(enabled) {
        this.voiceEnabled = enabled;
        
        if (enabled) {
            const initResult = await this.audioManager.init();
            if (!initResult.success) {
                this.showNotification('error', 'Microphone Error', initResult.error);
                document.getElementById('voiceToggle').checked = false;
                this.voiceEnabled = false;
                return;
            }
            this.showNotification('success', 'Voice Enabled', 'You can now use voice interaction');
        } else {
            this.audioManager.cleanup();
            this.showNotification('success', 'Voice Disabled', 'Voice interaction turned off');
        }

        // Update voice settings visibility
        document.getElementById('voiceSettings').style.display = enabled ? 'block' : 'none';
        
        // Update voice button state
        const voiceBtn = document.getElementById('voiceBtn');
        voiceBtn.disabled = !enabled;
        voiceBtn.title = enabled ? 'Toggle Voice Recording' : 'Enable voice mode first';
    }

    /**
     * Update voice speed
     */
    updateVoiceSpeed(speed) {
        document.querySelector('#voiceSpeed + .range-value').textContent = speed + 'x';
        this.wsManager.sendVoiceSettings({ speed: parseFloat(speed) });
    }

    /**
     * Update voice type
     */
    updateVoiceType(type) {
        this.wsManager.sendVoiceSettings({ voice: type });
    }

    /**
     * Toggle voice recording
     */
    async toggleVoiceRecording() {
        if (!this.voiceEnabled) {
            this.showNotification('warning', 'Voice Disabled', 'Please enable voice mode first');
            return;
        }

        if (this.isVoiceActive) {
            await this.stopVoiceRecording();
        } else {
            await this.startVoiceRecording();
        }
    }

    /**
     * Start voice recording
     */
    async startVoiceRecording() {
        try {
            // Stream out chunks every ~200ms while recording
            this.audioManager.setChunkCallback(async (blob) => {
                try {
                    if (this.wsManager && typeof this.wsManager.isConnected === 'function' && this.wsManager.isConnected()) {
                        await this.wsManager.sendAudio(blob);
                    }
                } catch (_) { /* swallow chunk send errors to avoid breaking stream */ }
            });

            await this.audioManager.startRecording();
            this.isVoiceActive = true;
            
            // Update UI
            document.getElementById('voiceBtn').classList.add('active');
            document.getElementById('voiceVisualizer').classList.remove('hidden');
            document.getElementById('voiceStatus').textContent = 'Listening...';
            
            this.showNotification('success', 'Recording', 'Speak now...');
        } catch (error) {
            this.showNotification('error', 'Recording Error', error.message);
        }
    }

    /**
     * Stop voice recording
     */
    async stopVoiceRecording() {
        if (!this.isVoiceActive) return;

        try {
            const recording = await this.audioManager.stopRecording();
            this.isVoiceActive = false;
            // Stop streaming chunks
            this.audioManager.setChunkCallback(null);
            
            // Update UI
            document.getElementById('voiceBtn').classList.remove('active');
            document.getElementById('voiceVisualizer').classList.add('hidden');
            const statusEl = document.getElementById('voiceStatus');
            if (statusEl) statusEl.textContent = 'Processing...';
            
            if (recording && recording.blob.size > 0) {
                console.log('Audio recorded, sending to server...');
                // Final chunk (in case any remainder)
                if (this.wsManager && typeof this.wsManager.isConnected === 'function' && this.wsManager.isConnected()) {
                    await this.wsManager.sendAudio(recording.blob);
                }
                this.addMessage('user', 'Voice message', 'audio');
            } else {
                this.showNotification('warning', 'No Audio', 'No audio was recorded');
            }
        } catch (error) {
            this.showNotification('error', 'Recording Error', error.message);
        }
    }

    /**
     * Update voice visualizer
     */
    updateVoiceVisualizer(amplitude) {
        const waves = document.querySelectorAll('.voice-wave');
        waves.forEach((wave, index) => {
            const height = 20 + (amplitude * 30 * (1 + Math.sin(Date.now() * 0.01 + index) * 0.5));
            wave.style.height = height + 'px';
        });
    }

    /**
     * Send text message
     */
    sendMessage() {
        const input = document.getElementById('messageInput');
        const text = input.value.trim();
        
        if (!text) return;

        // Add to chat
        this.addUserMessage(text);
        
        // Clear input and reset height
        input.value = '';
        input.style.height = 'auto';
        
        // Show typing indicator
        this.showTypingIndicator();
        
        // Send to WebSocket if available
        if (this.wsManager && typeof this.wsManager.isConnected === 'function' && this.wsManager.isConnected()) {
            this.wsManager.sendText(text, this.currentMode);
        } else {
            // Simulate AI response for demo
            setTimeout(() => {
                this.hideTypingIndicator();
                this.addAIMessage(this.generateDemoResponse(text));
            }, 1500);
        }
    }

    /**
     * Add message to chat (supports both 'user'/'ai' and 'assistant' sender types)
     */
    addMessage(sender, content, type = 'text') {
        const messagesContainer = document.getElementById('chatMessages');
        const message = document.createElement('div');
        
        // Normalize sender type for consistency
        const normalizedSender = sender === 'assistant' ? 'ai' : sender;
        message.className = `message ${normalizedSender}`;
        
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const avatar = normalizedSender === 'user' ? 'U' : 'AI';
        
        let displayContent = content;
        if (type === 'audio') {
            displayContent = '<i class="fas fa-microphone"></i> Voice message';
        }
        
        message.innerHTML = `
            <div class="message-avatar">${avatar}</div>
            <div class="message-content">
                ${displayContent}
                <div class="message-time">${time}</div>
            </div>
        `;
        
        messagesContainer.appendChild(message);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        
        // Hide typing indicator when AI responds
        if (normalizedSender === 'ai') {
            this.hideTypingIndicator();
        }
    }

    /**
     * Add user message to chat
     */
    addUserMessage(text, timestamp = null) {
        const time = timestamp || new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user-message';
        messageDiv.innerHTML = `
            <div class="message-avatar">
                <i class="fas fa-user"></i>
            </div>
            <div class="message-content">
                <div class="message-header">
                    <span class="sender-name">You</span>
                    <span class="message-time">${time}</span>
                </div>
                <div class="message-text">${this.formatMessage(text)}</div>
            </div>
        `;
        
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    /**
     * Scroll chat container to bottom
     */
    scrollToBottom() {
        const container = this.chatMessages || document.getElementById('chatMessages');
        if (!container) return;
        try {
            container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
        } catch (e) {
            // Fallback if scrollTo not supported
            container.scrollTop = container.scrollHeight;
        }
    }
    
    /**
     * Auto-resize the message textarea based on content
     */
    autoResizeTextarea() {
        const ta = this.messageInput || document.getElementById('messageInput');
        if (!ta) return;
        const minHeight = 40; // px
        const maxHeight = 160; // px
        ta.style.height = 'auto';
        const newHeight = Math.min(maxHeight, Math.max(minHeight, ta.scrollHeight));
        ta.style.height = newHeight + 'px';
    }
    
    /**
     * Format chat message text into safe HTML
     */
    formatMessage(text) {
        if (typeof text !== 'string') return '';
        // Basic escape
        const escaped = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        // Convert newlines to <br>
        return escaped.replace(/\n/g, '<br>');
    }
    
    /**
     * Add AI message to chat
     */
    addAIMessage(text, timestamp = null) {
        const time = timestamp || new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message ai-message';
        messageDiv.innerHTML = `
            <div class="message-avatar">
                <i class="fas fa-robot"></i>
            </div>
            <div class="message-content">
                <div class="message-header">
                    <span class="sender-name">AI Assistant</span>
                    <span class="message-time">${time}</span>
                </div>
                <div class="message-text">${this.formatMessage(text)}</div>
            </div>
        `;
        
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    /**
     * Add system message
     */
    addSystemMessage(text) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'system-message';
        messageDiv.innerHTML = `
            <div class="system-content">
                <i class="fas fa-info-circle"></i>
                <span>${text}</span>
            </div>
        `;
        
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    /**
     * Show typing indicator
     */
    showTypingIndicator() {
        // Remove existing typing indicator
        this.hideTypingIndicator();
        
        const typingDiv = document.createElement('div');
        typingDiv.className = 'message ai-message typing-indicator-message';
        typingDiv.id = 'typingIndicator';
        typingDiv.innerHTML = `
            <div class="message-avatar">
                <i class="fas fa-robot"></i>
            </div>
            <div class="typing-indicator">
                <div class="typing-dots">
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                </div>
            </div>
        `;
        
        this.chatMessages.appendChild(typingDiv);
        this.scrollToBottom();
    }
    
    /**
     * Hide typing indicator
     */
    hideTypingIndicator() {
        const typingIndicator = document.getElementById('typingIndicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }
    
    /**
     * Generate demo response
     */
    generateDemoResponse(userMessage) {
        const responses = {
            general: [
                "That's an interesting question! Let me think about that...",
                "I'd be happy to help you with that. Here's what I think...",
                "Great question! Based on my knowledge...",
                "Let me provide you with some insights on that topic..."
            ],
            document: [
                "Based on the document you uploaded, I can see that...",
                "Looking at your document, here's what I found relevant to your question...",
                "From the content you shared, I can explain...",
                "According to the document, here's the information you're looking for..."
            ]
        };
        
        const modeResponses = responses[this.currentMode] || responses.general;
        const randomResponse = modeResponses[Math.floor(Math.random() * modeResponses.length)];
        
        return `${randomResponse}\n\n*Note: This is a demo response. The full AI backend integration will provide detailed, contextual answers based on your ${this.currentMode === 'document' ? 'uploaded documents' : 'questions'}.*`;
    }

    /**
     * Show chat interface
     */
    showChatInterface() {
        document.getElementById('welcomeScreen').classList.add('hidden');
        document.getElementById('chatInterface').classList.remove('hidden');
        
        // Play voice greeting when entering chat for the first time
        if (!this.hasGreeted) {
            // If voice isn't enabled yet, try enabling to allow auto-listen
            // This will prompt for mic permission once.
            if (!this.voiceEnabled) {
                this.toggleVoiceMode(true).catch(() => {});
            }
            this.playVoiceGreeting();
            this.hasGreeted = true;
        }
    }
    
    /**
     * Play voice greeting and add to chat
     */
    async playVoiceGreeting() {
        const greetingText = "Welcome to your AI Learning Assistant! I'm here to help you with any questions you have. You can upload documents for specific discussions, or we can have a general conversation about any topic you're curious about. How can I assist you today?";
        
        // Add greeting to chat immediately
        this.addAIMessage(greetingText);
        
        // Try to play voice greeting if TTS is available
        try {
            if (this.audioManager && typeof this.audioManager.playText === 'function') {
                await this.audioManager.playText(greetingText, { rate: 0.7, pitch: 0.9, volume: 0.9 });
            } else if ('speechSynthesis' in window) {
                const utterance = new SpeechSynthesisUtterance(greetingText);
                utterance.rate = 0.7;
                utterance.pitch = 0.9;
                utterance.volume = 0.9;
                const voices = speechSynthesis.getVoices();
                const preferredVoice = voices.find(voice => 
                    (voice.name.includes('Google') && voice.lang.startsWith('en')) ||
                    (voice.name.includes('Microsoft') && voice.lang.startsWith('en')) ||
                    (voice.name.includes('Natural') && voice.lang.startsWith('en')) ||
                    (voice.lang === 'en-US' && voice.localService)
                );
                if (preferredVoice) utterance.voice = preferredVoice;
                speechSynthesis.speak(utterance);
                await new Promise((resolve) => {
                    utterance.onend = resolve;
                    utterance.onerror = resolve;
                });
            }
        } catch (e) {
            // ignore playback errors
        }

        // After greeting finishes, auto-start listening if voice mode is enabled and not already recording
        // Wait a moment for TTS to fully complete before starting mic
        if (this.voiceEnabled && !this.isVoiceActive) {
            setTimeout(async () => {
                try {
                    await this.startVoiceRecording();
                } catch (e) {
                    this.showNotification('warning', 'Microphone blocked', 'Click the mic button or allow microphone access to speak.');
                }
            }, 500);
        }
    }

    /**
     * Export chat
     */
    exportChat() {
        const messages = document.querySelectorAll('.message');
        let chatText = 'AI Learning Assistant - Conversation Export\n';
        chatText += '='.repeat(50) + '\n\n';
        
        messages.forEach(message => {
            const sender = message.classList.contains('user') ? 'You' : 'AI Assistant';
            const content = message.querySelector('.message-content').textContent.trim();
            const time = message.querySelector('.message-time').textContent;
            
            chatText += `[${time}] ${sender}: ${content}\n\n`;
        });
        
        const blob = new Blob([chatText], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `chat-export-${new Date().toISOString().split('T')[0]}.txt`;
        a.click();
        URL.revokeObjectURL(url);
        
        this.showNotification('success', 'Chat Exported', 'Conversation saved to file');
    }

    /**
     * Update session stats
     */
    updateSessionStats() {
        document.getElementById('questionsAsked').textContent = this.sessionStats.questionsAsked;
        document.getElementById('documentsProcessed').textContent = this.sessionStats.documentsProcessed;
    }

    /**
     * Update session timer
     */
    updateSessionTimer() {
        const updateTimer = () => {
            if (this.currentScreen === 'main') {
                const elapsed = Date.now() - this.sessionStats.sessionStartTime;
                const minutes = Math.floor(elapsed / 60000);
                document.getElementById('sessionTime').textContent = minutes + 'm';
            }
        };
        
        updateTimer();
        setInterval(updateTimer, 60000); // Update every minute
    }

    /**
     * Show settings modal
     */
    showSettingsModal() {
        document.getElementById('settingsModal').classList.remove('hidden');
    }

    /**
     * Hide settings modal
     */
    hideSettingsModal() {
        document.getElementById('settingsModal').classList.add('hidden');
    }

    /**
     * Save settings
     */
    saveSettings() {
        // Collect settings
        const settings = {
            autoPlay: document.getElementById('autoPlayToggle').checked,
            interruption: document.getElementById('interruptionToggle').checked,
            learningStyle: document.getElementById('learningStyle').value,
            responseDetail: document.getElementById('responseDetail').value
        };
        
        // Save to localStorage
        localStorage.setItem('app_settings', JSON.stringify(settings));
        
        // Send to server
        this.wsManager.sendVoiceSettings(settings);
        
        this.hideSettingsModal();
        this.showNotification('success', 'Settings Saved', 'Your preferences have been updated');
    }

    /**
     * Reset settings
     */
    resetSettings() {
        if (confirm('Reset all settings to default values?')) {
            localStorage.removeItem('app_settings');
            
            // Reset UI
            document.getElementById('autoPlayToggle').checked = true;
            document.getElementById('interruptionToggle').checked = true;
            document.getElementById('learningStyle').value = 'conversational';
            document.getElementById('responseDetail').value = 'detailed';
            
            this.showNotification('success', 'Settings Reset', 'All settings restored to defaults');
        }
    }

    /**
     * Setup notifications system
     */
    setupNotifications() {
        // Create notifications container if it doesn't exist
        if (!document.getElementById('notifications')) {
            const container = document.createElement('div');
            container.id = 'notifications';
            container.className = 'notifications';
            document.body.appendChild(container);
        }
    }

    /**
     * Show notification
     */
    showNotification(type, title, message, duration = 5000) {
        const container = document.getElementById('notifications');
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        
        const iconMap = {
            success: 'fas fa-check-circle',
            error: 'fas fa-exclamation-circle',
            warning: 'fas fa-exclamation-triangle',
            info: 'fas fa-info-circle'
        };
        
        notification.innerHTML = `
            <div class="notification-icon">
                <i class="${iconMap[type] || iconMap.info}"></i>
            </div>
            <div class="notification-content">
                <div class="notification-title">${title}</div>
                <div class="notification-message">${message}</div>
            </div>
            <button class="notification-close">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        // Add close functionality
        notification.querySelector('.notification-close').addEventListener('click', () => {
            this.removeNotification(notification);
        });
        
        container.appendChild(notification);
        
        // Auto-remove after duration
        if (duration > 0) {
            setTimeout(() => {
                this.removeNotification(notification);
            }, duration);
        }
    }

    /**
     * Remove notification
     */
    removeNotification(notification) {
        if (notification && notification.parentNode) {
            notification.style.animation = 'slideOut 0.3s ease-out forwards';
            setTimeout(() => {
                notification.remove();
            }, 300);
        }
    }

    /**
     * Update voice status and UI indicators
     */
    updateVoiceStatus(status) {
        const voiceBtn = document.getElementById('voiceBtn');
        const statusText = document.getElementById('statusText');
        const voiceVisualizer = document.querySelector('.voice-visualizer');
        
        // Remove all status classes
        voiceBtn?.classList.remove('listening', 'processing', 'speaking');
        
        switch (status) {
            case 'listening':
                voiceBtn?.classList.add('listening');
                if (statusText) statusText.textContent = 'Listening...';
                this.isVoiceActive = true;
                this.startVoiceVisualization();
                break;
                
            case 'processing':
                voiceBtn?.classList.add('processing');
                if (statusText) statusText.textContent = 'Processing...';
                this.stopVoiceVisualization();
                break;
                
            case 'ai_speaking':
                voiceBtn?.classList.add('speaking');
                if (statusText) statusText.textContent = 'AI Speaking...';
                this.startVoiceVisualization();
                break;
                
            case 'idle':
            default:
                if (statusText) statusText.textContent = this.voiceEnabled ? 'Voice Ready' : 'Voice Disabled';
                this.isVoiceActive = false;
                this.stopVoiceVisualization();
                break;
        }
    }

    /**
     * Start voice visualization
     */
    startVoiceVisualization() {
        const visualizer = document.querySelector('.voice-visualizer');
        if (visualizer) {
            visualizer.classList.add('active');
        }
    }

    /**
     * Stop voice visualization
     */
    stopVoiceVisualization() {
        const visualizer = document.querySelector('.voice-visualizer');
        if (visualizer) {
            visualizer.classList.remove('active');
        }
    }
}

// Export for use in other modules
window.UIManager = UIManager;
