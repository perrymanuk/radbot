/**
 * Text-to-Speech module for RadBot UI
 * Handles audio synthesis, playback, and auto-play toggle
 */

class TTSManager {
  constructor() {
    this._audioContext = null;
    this._currentSource = null;
    this.isPlaying = false;
    this.autoPlay = false;
    this.queue = [];
    this._processing = false;
  }

  /**
   * Get or create the shared AudioContext (reused across all plays)
   */
  _getAudioContext() {
    if (!this._audioContext) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this._audioContext = new AudioCtx();
    }
    // Resume if suspended (browser auto-play policy)
    if (this._audioContext.state === 'suspended') {
      this._audioContext.resume();
    }
    return this._audioContext;
  }

  /**
   * Fetch audio from the TTS API and play it via Web Audio API
   */
  async play(text) {
    if (!text || !text.trim()) return;

    // Stop any current playback
    this.stop();

    try {
      const response = await fetch('/api/tts/synthesize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text }),
      });

      if (!response.ok) {
        const detail = await response.text();
        console.error('TTS synthesis failed:', response.status, detail);
        return;
      }

      const ctx = this._getAudioContext();
      const arrayBuffer = await response.arrayBuffer();
      const audioBuffer = await ctx.decodeAudioData(arrayBuffer);

      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(ctx.destination);

      this._currentSource = source;
      this.isPlaying = true;

      source.onended = () => {
        this.isPlaying = false;
        this._currentSource = null;
        this._updateButtons();
        this._processQueue();
      };

      source.start(0);
      this._updateButtons();
    } catch (error) {
      console.error('TTS error:', error);
      this.isPlaying = false;
      this._currentSource = null;
      this._updateButtons();
    }
  }

  /**
   * Stop current playback
   */
  stop() {
    if (this._currentSource) {
      try {
        this._currentSource.stop();
      } catch (e) {
        // stop() throws InvalidStateError if already stopped
      }
      this._currentSource = null;
    }
    this.isPlaying = false;
    this.queue = [];
    this._processing = false;
    this._updateButtons();
  }

  /**
   * Queue text for auto-play
   */
  enqueue(text) {
    if (!this.autoPlay) return;
    this.queue.push(text);
    this._processQueue();
  }

  async _processQueue() {
    if (this._processing || this.isPlaying || this.queue.length === 0) return;
    this._processing = true;
    const text = this.queue.shift();
    await this.play(text);
    this._processing = false;
  }

  /**
   * Toggle auto-play mode
   */
  toggleAutoPlay() {
    this.autoPlay = !this.autoPlay;
    localStorage.setItem('tts_autoplay', this.autoPlay ? 'true' : 'false');
    this._updateAutoPlayToggle();
    console.log(`TTS auto-play ${this.autoPlay ? 'enabled' : 'disabled'}`);
  }

  /**
   * Load saved auto-play preference
   */
  loadPreferences() {
    this.autoPlay = localStorage.getItem('tts_autoplay') === 'true';
    this._updateAutoPlayToggle();
  }

  /**
   * Update the auto-play toggle button state
   */
  _updateAutoPlayToggle() {
    const toggle = document.getElementById('tts-autoplay-toggle');
    if (toggle) {
      toggle.classList.toggle('active', this.autoPlay);
      toggle.title = this.autoPlay ? 'Auto-play ON' : 'Auto-play OFF';
    }
  }

  /**
   * Update all TTS play button visual states
   */
  _updateButtons() {
    document.querySelectorAll('.tts-play-btn').forEach(btn => {
      if (this.isPlaying && btn.dataset.playing === 'true') {
        btn.textContent = '■';
        btn.title = 'Stop';
      } else {
        btn.textContent = '▶';
        btn.title = 'Play';
        btn.dataset.playing = 'false';
      }
    });
  }
}

// Create global instance
window.ttsManager = new TTSManager();

/**
 * Add a TTS play button to a message element
 */
export function addTTSButton(messageDiv) {
  if (!messageDiv || !messageDiv.classList.contains('assistant')) return;

  const contentDiv = messageDiv.querySelector('.message-content');
  if (!contentDiv) return;

  const btn = document.createElement('button');
  btn.className = 'tts-play-btn';
  btn.textContent = '▶';
  btn.title = 'Play';
  btn.dataset.playing = 'false';

  btn.addEventListener('click', (e) => {
    e.stopPropagation();

    if (window.ttsManager.isPlaying && btn.dataset.playing === 'true') {
      window.ttsManager.stop();
      btn.dataset.playing = 'false';
      return;
    }

    // Get the text content (strip HTML)
    const text = contentDiv.textContent || contentDiv.innerText || '';
    if (!text.trim()) return;

    // Reset all other buttons
    document.querySelectorAll('.tts-play-btn').forEach(b => {
      b.dataset.playing = 'false';
      b.textContent = '▶';
      b.title = 'Play';
    });

    btn.dataset.playing = 'true';
    btn.textContent = '■';
    btn.title = 'Stop';

    window.ttsManager.play(text);
  });

  messageDiv.appendChild(btn);
}

/**
 * Initialize TTS module
 */
export function initTTS() {
  window.ttsManager.loadPreferences();

  // Add auto-play toggle to header controls if it doesn't exist yet
  const controls = document.querySelector('.controls');
  if (controls && !document.getElementById('tts-autoplay-toggle')) {
    const toggle = document.createElement('button');
    toggle.id = 'tts-autoplay-toggle';
    toggle.className = 'tts-autoplay-toggle';
    toggle.textContent = 'TTS';
    toggle.title = window.ttsManager.autoPlay ? 'Auto-play ON' : 'Auto-play OFF';
    if (window.ttsManager.autoPlay) toggle.classList.add('active');

    toggle.addEventListener('click', () => {
      window.ttsManager.toggleAutoPlay();
    });

    controls.appendChild(toggle);
  }

  console.log('TTS module initialized');
}
