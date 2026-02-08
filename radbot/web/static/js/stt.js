/**
 * Speech-to-Text module for RadBot UI
 * Handles mic recording, transcription via backend API, and auto-send
 */

class STTManager {
  constructor() {
    this.state = 'idle'; // idle | recording | processing
    this.mediaRecorder = null;
    this.audioChunks = [];
    this.stream = null;
  }

  /**
   * Toggle recording on/off
   */
  async toggle() {
    if (this.state === 'idle') {
      await this.startRecording();
    } else if (this.state === 'recording') {
      this.stopRecording();
    }
    // If processing, ignore clicks
  }

  /**
   * Start recording from microphone
   */
  async startRecording() {
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      console.error('Microphone access denied:', err);
      this._showError('Microphone access denied. Please allow mic access and try again.');
      return;
    }

    this.audioChunks = [];

    // Use webm/opus which Google STT supports directly
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : 'audio/webm';

    try {
      this.mediaRecorder = new MediaRecorder(this.stream, { mimeType });
    } catch (err) {
      console.error('MediaRecorder creation failed:', err);
      this._stopStream();
      this._showError('Audio recording not supported in this browser.');
      return;
    }

    this.mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        this.audioChunks.push(event.data);
      }
    };

    this.mediaRecorder.onstop = () => {
      this._processAudio();
    };

    this.mediaRecorder.start();
    this.state = 'recording';
    this._updateButton();
    console.log('STT recording started');
  }

  /**
   * Stop recording
   */
  stopRecording() {
    if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
      this.state = 'processing';
      this._updateButton();
      this.mediaRecorder.stop();
      this._stopStream();
      console.log('STT recording stopped, processing...');
    }
  }

  /**
   * Send recorded audio to backend for transcription
   */
  async _processAudio() {
    if (this.audioChunks.length === 0) {
      console.warn('No audio data recorded');
      this.state = 'idle';
      this._updateButton();
      return;
    }

    const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
    this.audioChunks = [];

    // Skip very short recordings (< 0.5s worth of data, roughly < 4KB)
    if (audioBlob.size < 4000) {
      console.warn('Recording too short, ignoring');
      this.state = 'idle';
      this._updateButton();
      return;
    }

    try {
      const formData = new FormData();
      formData.append('audio', audioBlob, 'recording.webm');

      const response = await fetch('/api/stt/transcribe', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const detail = await response.text();
        console.error('STT transcription failed:', response.status, detail);
        // Show user-friendly error for common cases
        if (response.status === 400) {
          this._showError('No speech detected. Please try again.');
        } else {
          this._showError('Transcription failed. Please try again.');
        }
        this.state = 'idle';
        this._updateButton();
        return;
      }

      const data = await response.json();
      const text = data.text;

      if (text && text.trim()) {
        console.log('STT transcribed:', text);
        this._sendTranscribedText(text.trim());
      } else {
        this._showError('No speech detected. Please try again.');
      }
    } catch (error) {
      console.error('STT error:', error);
      this._showError('Transcription error. Please try again.');
    }

    this.state = 'idle';
    this._updateButton();
  }

  /**
   * Inject transcribed text into chat and auto-send
   */
  _sendTranscribedText(text) {
    const chatInput = document.getElementById('chat-input');
    if (!chatInput) return;

    // Set the text in the input
    chatInput.value = text;

    // Trigger input event for textarea resize
    chatInput.dispatchEvent(new Event('input', { bubbles: true }));

    // Auto-send by triggering the send button
    const sendButton = document.getElementById('send-button');
    if (sendButton) {
      sendButton.click();
    }
  }

  /**
   * Show a temporary error message in the chat
   */
  _showError(message) {
    // Use the chat addMessage if available
    if (typeof window.chatModule !== 'undefined' && window.chatModule.addMessage) {
      window.chatModule.addMessage('system', message);
    } else {
      // Fallback: find any addMessage on window
      const addMsg = window.addMessage || (window.chatModule && window.chatModule.addMessage);
      if (typeof addMsg === 'function') {
        addMsg('system', message);
      } else {
        console.warn('STT error (no UI):', message);
      }
    }
  }

  /**
   * Stop the media stream tracks
   */
  _stopStream() {
    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
      this.stream = null;
    }
  }

  /**
   * Update the mic button visual state
   */
  _updateButton() {
    const btn = document.getElementById('stt-mic-button');
    if (!btn) return;

    btn.classList.remove('stt-idle', 'stt-recording', 'stt-processing');

    switch (this.state) {
      case 'recording':
        btn.classList.add('stt-recording');
        btn.title = 'Stop recording';
        btn.textContent = 'REC';
        break;
      case 'processing':
        btn.classList.add('stt-processing');
        btn.title = 'Processing...';
        btn.textContent = '...';
        break;
      default:
        btn.classList.add('stt-idle');
        btn.title = 'Push to talk';
        btn.textContent = 'MIC';
        break;
    }
  }
}

// Create global singleton
window.sttManager = new STTManager();

/**
 * Initialize STT module - creates the mic button in the input area
 */
export function initSTT() {
  const inputWrapper = document.querySelector('.chat-input-wrapper');
  if (!inputWrapper) {
    console.warn('STT: chat input wrapper not found');
    return;
  }

  // Don't create duplicate buttons
  if (document.getElementById('stt-mic-button')) {
    return;
  }

  const btn = document.createElement('button');
  btn.id = 'stt-mic-button';
  btn.className = 'stt-mic-button stt-idle';
  btn.type = 'button';
  btn.textContent = 'MIC';
  btn.title = 'Push to talk';

  btn.addEventListener('click', (e) => {
    e.preventDefault();
    window.sttManager.toggle();
  });

  // Insert mic button before the send button
  const sendButton = document.getElementById('send-button');
  if (sendButton) {
    inputWrapper.insertBefore(btn, sendButton);
  } else {
    inputWrapper.appendChild(btn);
  }

  console.log('STT module initialized');
}
