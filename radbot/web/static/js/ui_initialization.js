/**
 * RadBot Web Interface Client - UI Initialization Module
 * 
 * This module handles UI initialization and setup of event listeners
 */

import * as chatModule from './chat.js';
import * as emojiUtils from './emoji.js';
import * as commandUtils from './commands.js';
import * as statusUtils from './status.js';
import * as selectsUtils from './selects.js';
import * as socketClient from './socket.js';
import { state } from './app_core.js';
import { addTTSButton, initTTS } from './tts.js';
import { initSTT } from './stt.js';

// Initialize UI elements after DOM is ready
export function initializeUI() {
    console.log('Initializing UI elements');
    
    // Initialize each module
    const chatInitialized = chatModule.initChat();
    const emojiInitialized = emojiUtils.initEmoji();
    const commandsInitialized = commandUtils.initCommands();
    const statusInitialized = statusUtils.initStatus();
    
    // If any critical modules failed to initialize, try again in a moment
    if (!chatInitialized) {
        console.log('Critical UI elements not found, retrying initialization...');
        setTimeout(initializeUI, 200);
        return;
    }
    
    console.log('UI elements initialized successfully');
    
    // Initialize voice wave animation
    initVoiceWaveAnimation();
    
    // Set up select components
    selectsUtils.initSelects();
    
    // Initialize event panel buttons
    initEventPanelButtons();
    
    // Initialize event type filter
    initEventTypeFilter();
    
    // Initialize TTS module (must be after tiling renders templates)
    try {
        initTTS();
        window.addTTSButton = addTTSButton;
        console.log('TTS module initialized from UI initialization');
    } catch (e) {
        console.warn('TTS initialization failed:', e);
    }

    // Initialize STT module (mic button in input area)
    try {
        initSTT();
        console.log('STT module initialized from UI initialization');
    } catch (e) {
        console.warn('STT initialization failed:', e);
    }

    // Check if WebSocket needs to be initialized or reinitialized
    if (!window.socket) {
        window.socket = socketClient.initSocket(state.sessionId);
    }
}

// Initialize event panel buttons
// NOTE: Click handlers for toggle buttons are managed by panel-trigger.js
// to prevent duplicate listener stacking. This function is intentionally empty.
function initEventPanelButtons() {
    // panel-trigger.js handles button click -> command event dispatch
}

// Initialize event type filter
export function initEventTypeFilter() {
    const eventTypeFilter = document.getElementById('event-type-filter');
    
    // Check if the events panel exists yet
    const eventsPanel = document.querySelector('[data-content="events"]');
    if (!eventsPanel) {
        // No need to spam console logs if panel isn't open yet
        return false;
    }
    
    if (eventTypeFilter) {
        console.log('Setting up event type filter');
        
        // Remove old event listeners by cloning
        const newFilter = eventTypeFilter.cloneNode(true);
        if (eventTypeFilter.parentNode) {
            eventTypeFilter.parentNode.replaceChild(newFilter, eventTypeFilter);
        }
        
        // Set up the new event listener
        newFilter.addEventListener('change', function() {
            console.log('Event type filter changed to:', this.value);
            window.renderEvents();
        });
        
        return true;
    } else {
        // Only retry a few times to avoid excessive logs
        console.log('Event type filter element not found, will retry once events panel opens');
        
        // Set up a mutation observer to detect when the events panel is created
        const observer = new MutationObserver((mutations) => {
            if (document.getElementById('event-type-filter')) {
                console.log('Event filter detected in DOM, initializing');
                observer.disconnect();
                setTimeout(initEventTypeFilter, 100);
            }
        });
        
        // Only observe if the events panel exists
        if (eventsPanel) {
            observer.observe(eventsPanel, { childList: true, subtree: true });
        }
        
        // Also listen for the events panel opening
        document.addEventListener('command:events', function eventsPanelOpened() {
            console.log('Events panel opened event detected');
            document.removeEventListener('command:events', eventsPanelOpened);
            setTimeout(initEventTypeFilter, 300);
        });
        
        return false;
    }
}

// Initialize voice wave animation
export function initVoiceWaveAnimation() {
    const voiceWave = document.querySelector('.voice-wave-animation');
    if (!voiceWave) return;
    
    // Clear existing bars
    voiceWave.innerHTML = '';
    
    // Create bars
    const bars = 20;
    for (let i = 0; i < bars; i++) {
        const bar = document.createElement('div');
        bar.className = 'voice-bar';
        
        // Set random initial height and animation delay
        const height = 4 + Math.floor(Math.random() * 8);
        const delay = Math.random() * 0.5;
        
        bar.style.height = `${height}px`;
        bar.style.animation = `voice-wave-animation 1.5s ease-in-out ${delay}s infinite`;
        
        voiceWave.appendChild(bar);
    }
}