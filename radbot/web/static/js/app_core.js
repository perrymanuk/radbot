/**
 * RadBot Web Interface Client - Core Module
 * 
 * This module handles core functionality like state management,
 * global variables, and initialization.
 */

// Import all modules
import * as chatModule from './chat.js';
import * as emojiUtils from './emoji.js';
import * as commandUtils from './commands.js';
import * as statusUtils from './status.js';
import * as selectsUtils from './selects.js';
import * as socketClient from './socket.js';
import * as uiInit from './ui_initialization.js';
import * as dataServices from './data_services.js';
import * as eventRendering from './event_rendering.js';
import * as agentConfig from './agent_config.js';
import { addTTSButton } from './tts.js';
import { initSessionManager } from './sessions.js';

// Global state
export const state = {
    sessionId: localStorage.getItem('radbot_session_id') || null,
    currentAgentName: "BETO", // Track current agent name - use uppercase to match status bar
    currentModel: "gemini-2.5-pro", // Default model - will be updated with actual model info from events
    isDarkTheme: true // Always use dark theme
};

// Global data
export let events = [];
export let tasks = [];
export let projects = [];
export let socket = null;

// Make modules and utilities globally available
window.chatModule = chatModule;
window.emojiUtils = emojiUtils;
window.commandUtils = commandUtils;
window.statusUtils = statusUtils;
window.selectsUtils = selectsUtils;
window.socket = null;
window.state = state;
window.events = events;
window.tasks = tasks;
window.projects = projects;
window.addTTSButton = addTTSButton;

// Initialize
function init() {
    console.log('Initializing app_core.js');
    
    // Listen for tiling manager ready event
    document.addEventListener('tiling:ready', () => {
        console.log('Received tiling:ready event, initializing UI');
        uiInit.initializeUI();
    });
    
    // Listen for layout changes to re-initialize UI elements
    document.addEventListener('layout:changed', () => {
        console.log('Layout changed, reinitializing UI');
        uiInit.initializeUI();
    });
    
    // As a fallback, also wait a moment to try initialization
    setTimeout(() => {
        if (!chatModule.getChatElements().input) {
            console.log('Attempting UI initialization via timeout');
            uiInit.initializeUI();
        }
    }, 300);
    
    // Create session ID if not exists
    if (!state.sessionId) {
        state.sessionId = agentConfig.generateUUID();
        localStorage.setItem('radbot_session_id', state.sessionId);
    }
    
    // Connect to WebSocket (only if not already connected from initializeUI)
    if (!window.socket || typeof window.socket.then === 'function') {
        window.socket = socketClient.initSocket(state.sessionId);
    }
    
    // Initialize session manager
    initSessionManager();

    // Load chat history for the current session
    loadChatFromStorage();

    // Fetch tasks, projects, and events directly from API
    dataServices.fetchTasks();
    dataServices.fetchEvents();

    // Get initial agent and model information
    agentConfig.fetchAgentInfo();
}

// Load chat history from backend for the current session
async function loadChatFromStorage() {
    const sessionId = state.sessionId;
    if (!sessionId) return;

    const container = document.getElementById('chat-messages');
    if (container) container.innerHTML = '';

    try {
        const resp = await fetch(`/api/messages/${sessionId}?limit=200`);
        if (!resp.ok) return;
        const data = await resp.json();
        if (!data.messages || data.messages.length === 0) return;

        for (const msg of data.messages) {
            if (msg.role === 'system') continue;
            chatModule.addMessage(msg.role, msg.content, msg.agent_name || undefined);
        }
    } catch (e) {
        console.warn('Failed to load chat history:', e);
    }
}

// Make functions globally available for tiling manager
window.initializeUI = uiInit.initializeUI;
window.renderTasks = dataServices.renderTasks;
window.renderEvents = eventRendering.renderEvents;
window.updateModelForCurrentAgent = agentConfig.updateModelForCurrentAgent;
window.loadChatFromStorage = loadChatFromStorage;

// Fetch data immediately when panels are opened
document.addEventListener('command:tasks', function() {
    console.log("Tasks panel opened - fetching latest data");
    dataServices.fetchTasks();
});

document.addEventListener('command:events', function() {
    console.log("Events panel opened - fetching latest data");
    // Clear events cache before fetching to ensure we get fresh data
    events = [];
    window.events = [];
    
    // Wait for DOM to update, then fetch events
    setTimeout(() => {
        dataServices.fetchEvents();
    }, 100);
});

// Initialize on page load
document.addEventListener('DOMContentLoaded', init);

// Export module functions
export { init };