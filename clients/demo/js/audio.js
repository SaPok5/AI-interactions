/**
 * Audio Manager
 * Handles audio recording, playback, and voice interaction
 */

class AudioManager {
    constructor() {
        this.mediaRecorder = null;
        this.audioStream = null;
        this.audioChunks = [];
        this.isRecording = false;
        this.isPlaying = false;
        this.audioContext = null;
        this.analyser = null;
        this.visualizerData = null;
        this.visualizerCallback = null;
        this.recordingStartTime = null;
        this.maxRecordingTime = 30000; // 30 seconds max
        this.recordingTimer = null;
        this.chunkCallback = null; // streaming callback
        this.hpf = null;
        this.compressor = null;
        this.processedDestination = null; // MediaStreamDestination
        this.processedStream = null; // MediaStream used by MediaRecorder
    }

    /**
     * Initialize audio system
     */
    async init() {
        try {
            // Request microphone permission
            this.audioStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    sampleRate: 16000
                }
            });

            // Create audio context and processing chain
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.analyser = this.audioContext.createAnalyser();
            this.analyser.fftSize = 256;

            const source = this.audioContext.createMediaStreamSource(this.audioStream);

            // High-pass filter to remove low-frequency rumble
            this.hpf = this.audioContext.createBiquadFilter();
            this.hpf.type = 'highpass';
            this.hpf.frequency.value = 120; // Hz

            // Gentle compressor to improve intelligibility
            this.compressor = this.audioContext.createDynamicsCompressor();
            this.compressor.threshold.value = -24; // dB
            this.compressor.knee.value = 30; // dB
            this.compressor.ratio.value = 2.5; // :1
            this.compressor.attack.value = 0.003; // s
            this.compressor.release.value = 0.25; // s

            // Destination stream for MediaRecorder
            this.processedDestination = this.audioContext.createMediaStreamDestination();

            // Wire graph: Mic -> HPF -> Compressor -> [Analyser + Destination]
            source.connect(this.hpf);
            this.hpf.connect(this.compressor);
            this.compressor.connect(this.analyser);
            this.compressor.connect(this.processedDestination);

            // Processed stream for recording
            this.processedStream = this.processedDestination.stream;
            
            this.visualizerData = new Uint8Array(this.analyser.frequencyBinCount);

            return { success: true };
        } catch (error) {
            console.error('Failed to initialize audio:', error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Start audio recording
     */
    async startRecording() {
        if (this.isRecording) {
            console.warn('Already recording');
            return false;
        }

        if (!this.audioStream) {
            const initResult = await this.init();
            if (!initResult.success) {
                throw new Error(initResult.error);
            }
        }

        try {
            this.audioChunks = [];
            const recorderStream = this.processedStream || this.audioStream;
            this.mediaRecorder = new MediaRecorder(recorderStream, {
                mimeType: 'audio/webm;codecs=opus',
                audioBitsPerSecond: 32000
            });

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                    // Stream out chunk if a callback is registered
                    if (typeof this.chunkCallback === 'function') {
                        try { this.chunkCallback(event.data); } catch (_) {}
                    }
                }
            };

            this.mediaRecorder.onstop = () => {
                this.isRecording = false;
                if (this.recordingTimer) {
                    clearTimeout(this.recordingTimer);
                    this.recordingTimer = null;
                }
            };

            // Emit chunks every 200ms for low-latency streaming
            this.mediaRecorder.start(200);
            this.isRecording = true;
            this.recordingStartTime = Date.now();

            // Auto-stop recording after max time
            this.recordingTimer = setTimeout(() => {
                if (this.isRecording) {
                    this.stopRecording();
                }
            }, this.maxRecordingTime);

            // Start visualization
            this.startVisualization();

            return true;
        } catch (error) {
            console.error('Failed to start recording:', error);
            this.isRecording = false;
            throw error;
        }
    }

    /**
     * Stop audio recording
     */
    stopRecording() {
        return new Promise((resolve) => {
            if (!this.isRecording || !this.mediaRecorder) {
                resolve(null);
                return;
            }

            this.mediaRecorder.onstop = () => {
                this.isRecording = false;
                this.stopVisualization();
                
                if (this.recordingTimer) {
                    clearTimeout(this.recordingTimer);
                    this.recordingTimer = null;
                }

                if (this.audioChunks.length > 0) {
                    const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
                    const duration = Date.now() - this.recordingStartTime;
                    
                    resolve({
                        blob: audioBlob,
                        duration: duration,
                        size: audioBlob.size
                    });
                } else {
                    resolve(null);
                }
            };

            this.mediaRecorder.stop();
        });
    }

    /**
     * Play audio from blob or URL
     */
    async playAudio(audioSource) {
        if (this.isPlaying) {
            this.stopAudio();
        }

        try {
            const audio = new Audio();
            
            if (audioSource instanceof Blob) {
                audio.src = URL.createObjectURL(audioSource);
            } else if (typeof audioSource === 'string') {
                audio.src = audioSource;
            } else {
                throw new Error('Invalid audio source');
            }

            this.isPlaying = true;

            audio.onended = () => {
                this.isPlaying = false;
                if (audioSource instanceof Blob) {
                    URL.revokeObjectURL(audio.src);
                }
            };

            audio.onerror = (error) => {
                console.error('Audio playback error:', error);
                this.isPlaying = false;
                if (audioSource instanceof Blob) {
                    URL.revokeObjectURL(audio.src);
                }
            };

            await audio.play();
            return audio;
        } catch (error) {
            console.error('Failed to play audio:', error);
            this.isPlaying = false;
            throw error;
        }
    }

    /**
     * Stop audio playback
     */
    stopAudio() {
        // This would need to be implemented with a reference to the current audio element
        this.isPlaying = false;
    }

    /**
     * Start audio visualization
     */
    startVisualization() {
        if (!this.analyser || !this.visualizerCallback) return;

        const updateVisualization = () => {
            if (!this.isRecording) return;

            this.analyser.getByteFrequencyData(this.visualizerData);
            
            // Calculate average amplitude
            let sum = 0;
            for (let i = 0; i < this.visualizerData.length; i++) {
                sum += this.visualizerData[i];
            }
            const average = sum / this.visualizerData.length;
            
            // Normalize to 0-1 range
            const normalizedAmplitude = average / 255;
            
            if (this.visualizerCallback) {
                this.visualizerCallback(normalizedAmplitude, this.visualizerData);
            }

            requestAnimationFrame(updateVisualization);
        };

        updateVisualization();
    }

    /**
     * Stop audio visualization
     */
    stopVisualization() {
        if (this.visualizerCallback) {
            this.visualizerCallback(0, null);
        }
    }

    /**
     * Set visualization callback
     */
    setVisualizationCallback(callback) {
        this.visualizerCallback = callback;
    }

    /**
     * Set streaming chunk callback (Blob => void)
     */
    setChunkCallback(callback) {
        this.chunkCallback = callback;
    }

    /**
     * Get recording status
     */
    getRecordingStatus() {
        return {
            isRecording: this.isRecording,
            duration: this.isRecording ? Date.now() - this.recordingStartTime : 0,
            maxDuration: this.maxRecordingTime
        };
    }

    /**
     * Get playback status
     */
    getPlaybackStatus() {
        return {
            isPlaying: this.isPlaying
        };
    }

    /**
     * Check if audio is supported
     */
    isSupported() {
        return !!(navigator.mediaDevices && 
                 navigator.mediaDevices.getUserMedia && 
                 window.MediaRecorder);
    }

    /**
     * Get available audio devices
     */
    async getAudioDevices() {
        try {
            const devices = await navigator.mediaDevices.enumerateDevices();
            return devices.filter(device => device.kind === 'audioinput');
        } catch (error) {
            console.error('Failed to get audio devices:', error);
            return [];
        }
    }

    /**
     * Switch audio input device
     */
    async switchAudioDevice(deviceId) {
        try {
            // Stop current stream
            if (this.audioStream) {
                this.audioStream.getTracks().forEach(track => track.stop());
            }

            // Get new stream with specified device
            this.audioStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    deviceId: deviceId ? { exact: deviceId } : undefined,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    sampleRate: 16000
                }
            });

            // Reconnect to audio context
            if (this.audioContext && this.analyser) {
                const source = this.audioContext.createMediaStreamSource(this.audioStream);
                source.connect(this.analyser);
            }

            return { success: true };
        } catch (error) {
            console.error('Failed to switch audio device:', error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Cleanup audio resources
     */
    cleanup() {
        if (this.isRecording) {
            this.stopRecording();
        }

        if (this.audioStream) {
            this.audioStream.getTracks().forEach(track => track.stop());
            this.audioStream = null;
        }

        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        this.mediaRecorder = null;
        this.analyser = null;
        this.visualizerData = null;
        this.visualizerCallback = null;
    }

    /**
     * Play text via TTS (Web Speech API)
     * Returns when playback finishes
     */
    async playText(text, opts = {}) {
        if (!('speechSynthesis' in window)) {
            throw new Error('Speech synthesis not supported');
        }

        // Cancel any ongoing speech
        try { window.speechSynthesis.cancel(); } catch (_) {}

        const {
            rate = 1.0,
            pitch = 1.0,
            volume = 1.0,
            voiceName
        } = opts;

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = rate;
        utterance.pitch = pitch;
        utterance.volume = volume;

        // Pick a pleasant english voice if available
        const pickVoice = () => {
            const voices = speechSynthesis.getVoices();
            if (!voices || !voices.length) return null;
            if (voiceName) return voices.find(v => v.name === voiceName) || null;
            return (
                voices.find(v => v.name && (v.name.includes('Google') || v.name.includes('Microsoft'))) ||
                voices.find(v => v.lang && v.lang.toLowerCase().startsWith('en')) ||
                null
            );
        };

        const maybeAssignVoice = () => {
            const v = pickVoice();
            if (v) utterance.voice = v;
        };

        // Some browsers load voices asynchronously
        maybeAssignVoice();
        if (!utterance.voice) {
            await new Promise(resolve => setTimeout(resolve, 50));
            maybeAssignVoice();
        }

        this.isPlaying = true;
        return new Promise((resolve, reject) => {
            utterance.onend = () => { this.isPlaying = false; resolve(); };
            utterance.onerror = (e) => { this.isPlaying = false; resolve(); };
            try {
                speechSynthesis.speak(utterance);
            } catch (e) {
                this.isPlaying = false;
                reject(e);
            }
        });
    }
}

// Export for use in other modules
window.AudioManager = AudioManager;
