/**
 * Core application module for RadBot web interface
 * Manages state, initialization, and agent context
 */

// Global state
const state = {
    messages: [],          // Current conversation
    socket: null,          // WebSocket connection
    status: 'disconnected', // Connection status
    socketConnected: false, // WebSocket connected
    userAgentData: null,   // Browser data
    thinking: false,       // Is the agent thinking?
    currentAgentName: 'BETO', // Current agent name
    theme: 'light',        // UI theme
    selectedSection: 'chat', // Currently selected section
    events: [],            // Event log
    tasks: [],             // Tasks from agent
    isConfigVisible: false, // Configuration panel visibility
    isSettingsVisible: false, // Settings panel visibility
    isEventsVisible: false, // Events panel visibility
    isTasksVisible: false, // Tasks panel visibility
    agentModels: {},       // Map of agent names to models
    speechRecognition: null, // Speech recognition
    speechSynthesis: null, // Speech synthesis
    voiceInput: false,     // Voice input mode
    voiceOutput: false,    // Voice output mode
    isMobile: false,       // Mobile device detection
    darkModeMediaQuery: null, // System dark mode preference
    firstMessageSent: false, // Track if user has sent a message
    pendingMessage: null,  // Queued message waiting for connection
    messageQueue: [],      // Queue of messages to send
    selectedSession: null, // Current session ID
    sessions: [],          // Available sessions
    isSessionsVisible: false, // Session panel visibility
    wasConnected: false,   // Track if we were connected before
    lastTypingTime: 0,     // Last time user was typing
    typingTimer: null,     // Typing indicator timer
    typingIndicatorShown: false, // Is typing indicator visible?
    savedScrollPosition: 0, // Saved scroll position
    lastContentHeight: 0,  // Last content height
    connectionAttempts: 0, // Connection attempt counter
    lastPing: 0,           // Last ping time
    pingInterval: null,    // Ping interval
    reconnectTimeout: null, // Reconnect timeout
    maxReconnectAttempts: 10, // Max reconnect attempts
    sessionStorage: {},    // In-memory session storage
    commandHistory: [],    // Command history
    commandHistoryIndex: -1, // Command history index
    commandHistoryTemp: '', // Temporary command for history navigation
    inputHeight: 56,       // Input height
    maxInputHeight: 200,   // Max input height
    backupInterval: null,  // Backup interval
    backupEnabled: true,   // Backup enabled
    contextSizeLimit: 24,  // Max number of messages to send for context
    filterActive: '',      // Active filter
    selectedAgent: null,   // Selected agent for commands
    commandRegistry: {},   // Registry of slash commands
    agentContexts: {},     // Empty object - we're not tracking individual agent contexts anymore
    headerHeight: 60,      // Header height
    initialized: false,    // Initialization state
    isSearchActive: false, // Search mode
    searchQuery: '',       // Current search query
    searchResults: [],     // Search results
    searchIndex: -1,       // Current search result index
    headerContent: '',     // Dynamic header content
    lastSpeechTimestamp: 0, // Last speech timestamp
    isSpeaking: false,     // Speaking status
    transitionInProgress: false, // Page transition
    pageTitle: 'RadBot',   // Page title
    lastActivityTime: Date.now(), // Last activity time
    idleTimeout: null,     // Idle timeout
    maxIdleTime: 30 * 60 * 1000, // 30 minutes
    idleWarningShown: false, // Idle warning shown
    reconnectOnActivity: true, // Reconnect on activity
    eventsFilter: 'all',   // Events filter
    lastProblem: null,     // Last error/warning message
    menuOpen: false,       // Mobile menu state
    pendingScroll: false,  // Pending scroll to bottom
    unreadCount: 0,        // Unread message count
};

// Module initialization
(function() {
    document.addEventListener('DOMContentLoaded', initializeApp);
    
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        initializeApp();
    }
})();

function initializeApp() {
    if (state.initialized) return;
    state.initialized = true;
    
    console.log('Initializing application...');
    
    // Set up device detection
    detectDevice();
    
    // Initialize UI components
    initializeUI();
    
    // Load preferences
    // Define loadPreferences function if not available
    if (typeof loadPreferences !== 'function') {
        console.log('loadPreferences not available, defining basic implementation');
        window.loadPreferences = function() {
            // Load theme preference
            const savedTheme = localStorage.getItem('theme');
            if (savedTheme) {
                state.theme = savedTheme;
                document.body.classList.toggle('dark-theme', state.theme === 'dark');
            }

            // Load voice preferences
            state.voiceInput = localStorage.getItem('voiceInput') === 'true';
            state.voiceOutput = localStorage.getItem('voiceOutput') === 'true';

            console.log('Basic preferences loaded');
        };
    }

    // Now call the function (either our basic implementation or the one loaded from another module)
    if (typeof loadPreferences === 'function') {
        loadPreferences();
    }
    
    // Initialize session management
    initializeSessions();
    
    // Set up event listeners
    setupEventListeners();
    
    // Initialize command registry
    initializeCommands();
    
    // Connect to the server
    initializeConnection();
    
    // Register global handlers (don't overwrite window.state if app_core.js already set it)
    if (!window.state) {
        window.state = state;
    }
    window.switchAgentContext = switchAgentContext;
    window.trackAgentContext = trackAgentContext;
    window.updateModelForCurrentAgent = updateModelForCurrentAgent;

    // Initialize TTS module
    try {
        if (window.ttsManager) {
            window.ttsManager.loadPreferences();
            // Dynamically import and init TTS UI
            import('/static/js/tts.js').then(ttsModule => {
                if (ttsModule.initTTS) {
                    ttsModule.initTTS();
                }
                if (ttsModule.addTTSButton) {
                    window.addTTSButton = ttsModule.addTTSButton;
                }
            }).catch(e => {
                console.warn('TTS module not available:', e);
            });
        }
    } catch (e) {
        console.warn('Error initializing TTS:', e);
    }

    console.log('Application initialized.');
}

// Handle device detection
function detectDevice() {
    state.isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    state.darkModeMediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    state.userAgentData = navigator.userAgentData || {
        brands: [{brand: 'Unknown', version: '0'}],
        platform: navigator.platform || 'Unknown'
    };
    
    console.log(`Device detected: ${state.isMobile ? 'Mobile' : 'Desktop'} - ${state.userAgentData.platform}`);
}

// Initialize UI components and settings
function initializeUI() {
    // Apply theme based on user preference or system setting
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
        state.theme = savedTheme;
    } else if (state.darkModeMediaQuery.matches) {
        state.theme = 'dark';
    }
    
    document.body.classList.toggle('dark-theme', state.theme === 'dark');
    
    // Setup theme toggle if it exists
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }
    
    // Initialize panels
    document.querySelectorAll('.panel-trigger').forEach(trigger => {
        const panel = trigger.getAttribute('data-panel');
        trigger.addEventListener('click', () => togglePanel(panel));
    });
    
    // Initialize message input
    const messageInput = document.getElementById('message');
    if (messageInput) {
        messageInput.addEventListener('input', function() {
            this.style.height = 'auto';
            const newHeight = Math.min(this.scrollHeight, state.maxInputHeight);
            this.style.height = newHeight + 'px';
            state.inputHeight = newHeight;
        });
    }
    
    // Initialize selects
    document.querySelectorAll('select.custom-select').forEach(select => {
        select.addEventListener('change', function() {
            const selectedOption = this.options[this.selectedIndex];
            const displayElement = this.parentElement.querySelector('.selected-option');
            if (displayElement) {
                displayElement.textContent = selectedOption.textContent;
            }
        });
        
        // Trigger initial selection
        const event = new Event('change');
        select.dispatchEvent(event);
    });
}

// Initialize session management
function initializeSessions() {
    // Load any session ID from local storage
    const savedSessionId = localStorage.getItem('currentSessionId');
    if (savedSessionId) {
        state.selectedSession = savedSessionId;
        console.log(`Loaded saved session ID: ${savedSessionId}`);
    } else {
        // Create new session ID if none exists
        state.selectedSession = 'session_' + Date.now();
        localStorage.setItem('currentSessionId', state.selectedSession);
        console.log(`Created new session ID: ${state.selectedSession}`);
    }
    
    // Check for a saved active agent
    const lastActiveAgent = localStorage.getItem('lastActiveAgent');
    if (lastActiveAgent) {
        state.currentAgentName = lastActiveAgent.toUpperCase();
        console.log(`Loaded last active agent: ${state.currentAgentName}`);
    }
    
    // Load session list from local storage
    const savedSessions = localStorage.getItem('sessions');
    if (savedSessions) {
        try {
            state.sessions = JSON.parse(savedSessions);
            console.log(`Loaded ${state.sessions.length} saved sessions`);
        } catch (e) {
            console.error('Failed to parse saved sessions:', e);
            state.sessions = [{id: state.selectedSession, name: 'Current Session'}];
        }
    } else {
        state.sessions = [{id: state.selectedSession, name: 'Current Session'}];
    }
    
    // Ensure current session is in the list
    if (!state.sessions.find(s => s.id === state.selectedSession)) {
        state.sessions.push({
            id: state.selectedSession,
            name: 'Current Session',
            created: Date.now()
        });
        saveSessions();
    }
    
    // Initialize session selector
    updateSessionSelector();
}

// Event handler stubs
function handleResize() {}
function handleScroll() {}
function handleOnline() { state.status = 'ready'; }
function handleOffline() { state.status = 'offline'; }
function handleFocus() { state.lastActivityTime = Date.now(); }
function handleBlur() {}
function handleBeforeUnload() {}
function handleKeyDown() {}
function handleSystemThemeChange(e) {
    if (!localStorage.getItem('theme')) {
        document.body.classList.toggle('dark-theme', e.matches);
    }
}
function resetIdleTimer() { state.lastActivityTime = Date.now(); }
function saveSessions() {
    try { localStorage.setItem('sessions', JSON.stringify(state.sessions)); } catch(e) {}
}
function sendMessage() {}
function processMessageQueue() {}

// Set up event listeners
function setupEventListeners() {
    // Window events
    window.addEventListener('resize', handleResize);
    window.addEventListener('scroll', handleScroll);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    window.addEventListener('focus', handleFocus);
    window.addEventListener('blur', handleBlur);
    window.addEventListener('beforeunload', handleBeforeUnload);

    // Setup keyboard shortcuts
    document.addEventListener('keydown', handleKeyDown);

    // Handle theme changes
    if (state.darkModeMediaQuery) {
        state.darkModeMediaQuery.addEventListener('change', handleSystemThemeChange);
    }

    // Handle idle detection
    document.addEventListener('mousemove', resetIdleTimer);
    document.addEventListener('keypress', resetIdleTimer);
    document.addEventListener('click', resetIdleTimer);
    document.addEventListener('scroll', resetIdleTimer);

    // Start idle timer
    resetIdleTimer();
}

// Find the last message ID for a specific agent
function findLastMessageIdForAgent(agentName) {
    // Get the chat message elements
    const chatMessages = document.querySelectorAll('.chat-message');
    
    // Iterate through messages in reverse order (newest first)
    for (let i = chatMessages.length - 1; i >= 0; i--) {
        const msg = chatMessages[i];
        const msgId = msg.getAttribute('data-id');
        const role = msg.getAttribute('data-role');
        const agent = msg.getAttribute('data-agent');
        
        // Match messages from this agent, or from user to this agent
        if ((role === 'user' && (!agent || agent === agentName)) || 
           (role === 'assistant' && (!agent || agent === agentName))) {
            return msgId;
        }
    }

    return null;
}

// Simplified agent context tracking - just maintain current agent
window.trackAgentContext = function(agentName) {
    // Normalize agent name to uppercase for consistency
    agentName = agentName.toUpperCase();

    console.log(`Using simplified agent context tracking for: ${agentName}`);
    return {
        lastMessageId: null,
        lastSentMessage: null,
        pendingResponse: false
    };
};

// Simplified agent switching - just update the current agent name
window.switchAgentContext = function(newAgentName) {
    // Normalize agent name to uppercase for consistency
    newAgentName = newAgentName.toUpperCase();
    const prevAgentName = state.currentAgentName;
    console.log(`Switching from ${prevAgentName} to ${newAgentName} (simplified approach)`);

    // Simply update the current agent name - no context preservation between agents
    state.currentAgentName = newAgentName;

    // Log the change
    console.log(`Current agent is now: ${state.currentAgentName}`);

    // Also save current agent in localStorage to persist between page refreshes
    try {
        localStorage.setItem('lastActiveAgent', newAgentName);
        console.log(`Saved ${newAgentName} as lastActiveAgent in localStorage`);
    } catch (e) {
        console.warn(`Error saving lastActiveAgent to localStorage: ${e}`);
    }

    // Update document CSS property with agent name
    document.documentElement.style.setProperty('--agent-name', `"${newAgentName}"`);

    // Update agent status display
    const agentStatus = document.getElementById('agent-status');
    if (agentStatus) {
        agentStatus.textContent = `AGENT: ${newAgentName}`;
        console.log(`Updated agent status display to: ${newAgentName}`);
    }

    // Return a simple context object
    return {
        lastMessageId: null,
        lastSentMessage: null,
        pendingResponse: false
    };
};

// Toggle a panel via tiling manager
function togglePanel(panelName) {
    if (window.tilingManager) {
        window.tilingManager.togglePanel(panelName);
    }
}

// Stub functions referenced in command registry
function showCommandHelp() { console.log('Help command'); }
function clearChat() {
    const msgs = document.getElementById('chat-messages');
    if (msgs) msgs.innerHTML = '';
}
function toggleTheme() {
    document.body.classList.toggle('dark-theme');
}
function toggleVoice() { console.log('Voice toggle'); }
function switchAgent(name) {
    if (window.switchAgentContext) window.switchAgentContext(name || 'BETO');
}
function useClaudeTemplate() { console.log('Claude template'); }

// Initialize command registry
function initializeCommands() {
    // Add base commands
    state.commandRegistry = {
        help: {
            description: 'Show available commands',
            action: showCommandHelp
        },
        clear: {
            description: 'Clear the chat',
            action: clearChat
        },
        theme: {
            description: 'Toggle dark/light theme',
            action: toggleTheme
        },
        settings: {
            description: 'Open settings panel',
            action: () => togglePanel('settings')
        },
        events: {
            description: 'Toggle events panel',
            action: () => togglePanel('events')
        },
        tasks: {
            description: 'Toggle tasks panel',
            action: () => togglePanel('tasks')
        },
        sessions: {
            description: 'Open sessions panel',
            action: () => togglePanel('sessions')
        },
        voice: {
            description: 'Toggle voice input/output',
            action: toggleVoice
        },
        agent: {
            description: 'Switch to a different agent',
            action: switchAgent,
            args: ['agent_name']
        },
        claude: {
            description: 'Use a Claude template',
            action: useClaudeTemplate,
            args: ['template_name', '...args']
        }
    };

    console.log('Command registry initialized with', Object.keys(state.commandRegistry).length, 'commands');
}

// Handle model updates for agent switching
window.updateModelForCurrentAgent = function() {
    // Don't update if agent models aren't loaded yet
    if (!state.agentModels || Object.keys(state.agentModels).length === 0) {
        console.log('Agent models not loaded yet, skipping model update');
        return;
    }

    const agentName = state.currentAgentName.toLowerCase();
    
    // Handle specialized naming conventions
    if (agentName === 'scout' && state.agentModels['scout_agent']) {
        window.statusUtils.updateModelStatus(state.agentModels['scout_agent']);
        console.log(`Updated model for scout: ${state.agentModels['scout_agent']}`);
    }
    // Try exact match
    else if (state.agentModels[agentName]) {
        window.statusUtils.updateModelStatus(state.agentModels[agentName]);
        console.log(`Updated model for ${agentName}: ${state.agentModels[agentName]}`);
    }
    // Try _agent suffix
    else if (state.agentModels[agentName + '_agent']) {
        window.statusUtils.updateModelStatus(state.agentModels[agentName + '_agent']);
        console.log(`Updated model for ${agentName} using _agent suffix: ${state.agentModels[agentName + '_agent']}`);
    }
    // Default to main model
    else if (state.agentModels['main']) {
        window.statusUtils.updateModelStatus(state.agentModels['main']);
        console.log(`Using main model for ${agentName}: ${state.agentModels['main']}`);
    }
    else {
        console.log(`No model found for agent: ${agentName}`);
    }
};

// Initialize WebSocket connection
function initializeConnection() {
    if (state.socket && state.socketConnected) {
        console.log('Already connected, skipping connection initialization');
        return;
    }
    
    // Attempt to connect via socket.js module
    if (window.initSocket && typeof window.initSocket === 'function') {
        console.log('Initializing socket connection for session:', state.selectedSession);
        
        window.initSocket(state.selectedSession).then(socket => {
            state.socket = socket;
            state.socketConnected = socket.socketConnected;
            
            console.log('Socket connection initialized:', state.socketConnected ? 'Connected' : 'Disconnected');
            
            if (state.socketConnected) {
                state.wasConnected = true;
                state.status = 'ready';
                
                // Process any pending messages
                if (state.pendingMessage) {
                    console.log('Sending pending message:', state.pendingMessage);
                    sendMessage(state.pendingMessage);
                    state.pendingMessage = null;
                }
                
                if (state.messageQueue.length > 0) {
                    console.log(`Processing ${state.messageQueue.length} queued messages`);
                    processMessageQueue();
                }
                
                // Request agent models information
                requestAgentModels();
            }
        });
    } else {
        console.error('Socket initialization function not available');
        state.status = 'error';
    }
}

// Update session selector
function updateSessionSelector() {
    const sessionSelector = document.getElementById('session-selector');
    if (!sessionSelector) return;
    
    // Clear current options
    sessionSelector.innerHTML = '';
    
    // Add options for each session
    state.sessions.forEach(session => {
        const option = document.createElement('option');
        option.value = session.id;
        option.textContent = session.name || session.id;
        option.selected = session.id === state.selectedSession;
        sessionSelector.appendChild(option);
    });
}

// Request agent models information
function requestAgentModels() {
    if (state.socket && state.socketConnected) {
        console.log('Requesting agent models information');
        state.socket.send(JSON.stringify({
            type: 'agent_models_request'
        }));
    }
}

// Global exports - don't overwrite if app_core.js already set window.state
if (!window.state) {
    window.state = state;
}
window.initializeApp = initializeApp;
window.switchAgentContext = switchAgentContext;
window.trackAgentContext = trackAgentContext;
window.updateModelForCurrentAgent = updateModelForCurrentAgent;