/**
 * Sessions management module for RadBot UI
 * Handles multiple chat sessions and their persistence
 */

// Import utility functions
import * as socketClient from './socket.js';
import { ChatPersistence } from './chat_persistence.js';

// Sessions index storage key
const SESSIONS_INDEX_KEY = 'radbot_sessions_index';
const ACTIVE_SESSION_KEY = 'radbot_active_session_id';

// Session management class
export class SessionManager {
  constructor() {
    // Initialize sessions index or load from storage
    this.initSessionsIndex();
    
    // Chat persistence instance (will be provided externally)
    this.chatPersistence = null;
    
    // DOM references
    this.sessionsContainer = null;
    this.sessionSearch = null;
    this.newSessionButton = null;
    
    // Flag to track initialization state
    this.initialized = false;
    
    // Listen for storage events from other tabs
    window.addEventListener('storage', this.handleStorageEvent.bind(this));
  }
  
  // Initialize or load sessions index
  initSessionsIndex() {
    let sessionsData = localStorage.getItem(SESSIONS_INDEX_KEY);
    
    if (sessionsData) {
      try {
        this.sessionsIndex = JSON.parse(sessionsData);
        console.log(`Loaded sessions index with ${this.sessionsIndex.sessions.length} sessions`);
        
        // Do a full cleanup of the sessions index
        this.cleanSessionsIndex();
      } catch (error) {
        console.error('Error parsing sessions index:', error);
        this.createDefaultSessionsIndex();
      }
    } else {
      this.createDefaultSessionsIndex();
    }
    
    // Validate the structure
    if (!this.sessionsIndex || !Array.isArray(this.sessionsIndex.sessions)) {
      console.warn('Invalid sessions index structure, resetting...');
      this.createDefaultSessionsIndex();
    }
    
    // Ensure we have an active session
    if (!this.sessionsIndex.active_session_id) {
      // Use the stored session ID if available
      const storedSessionId = localStorage.getItem(ACTIVE_SESSION_KEY);
      
      if (storedSessionId) {
        this.sessionsIndex.active_session_id = storedSessionId;
      } else if (this.sessionsIndex.sessions.length > 0) {
        // Use the first session
        this.sessionsIndex.active_session_id = this.sessionsIndex.sessions[0].id;
      } else {
        // Create a new session
        const newSession = this.createDefaultSession();
        this.sessionsIndex.sessions.push(newSession);
        this.sessionsIndex.active_session_id = newSession.id;
      }
      
      // Save the updated index
      this.saveSessionsIndex();
    }
    
    // Ensure active session exists in sessions list
    const activeSessionExists = this.sessionsIndex.sessions.some(
      session => session.id === this.sessionsIndex.active_session_id
    );
    
    if (!activeSessionExists && this.sessionsIndex.active_session_id) {
      console.warn('Active session not found in sessions list, adding it');
      
      // Create a session object for the active session ID
      const activeSession = this.createDefaultSession(this.sessionsIndex.active_session_id);
      this.sessionsIndex.sessions.push(activeSession);
      this.saveSessionsIndex();
    }
  }
  
  // Clean up sessions index to remove duplicates and invalid sessions
  cleanSessionsIndex() {
    if (!this.sessionsIndex || !Array.isArray(this.sessionsIndex.sessions)) {
      console.warn('Cannot clean invalid sessions index');
      return;
    }
    
    const originalCount = this.sessionsIndex.sessions.length;
    
    // First, remove sessions with null or undefined IDs
    this.sessionsIndex.sessions = this.sessionsIndex.sessions.filter(session => {
      if (!session || !session.id) {
        console.warn('Removing session with null/undefined ID');
        return false;
      }
      return true;
    });
    
    // Then filter out duplicates by ID (keep most recent by last_message_at)
    const sessionMap = new Map();
    
    // First pass - collect all sessions by ID
    for (const session of this.sessionsIndex.sessions) {
      // Normalize session to ensure it has all required fields
      const normalizedSession = {
        ...session,
        name: session.name || `Session ${new Date(session.created_at || Date.now()).toLocaleDateString()}`,
        created_at: session.created_at || Date.now(),
        last_message_at: session.last_message_at || session.created_at || Date.now(),
        preview: session.preview || "Session"
      };
      
      // Check if we already have this session ID
      if (sessionMap.has(session.id)) {
        const existingSession = sessionMap.get(session.id);
        // Keep the one with the most recent last_message_at
        if ((normalizedSession.last_message_at || 0) > (existingSession.last_message_at || 0)) {
          sessionMap.set(session.id, normalizedSession);
        }
      } else {
        sessionMap.set(session.id, normalizedSession);
      }
    }
    
    // Convert back to array
    this.sessionsIndex.sessions = Array.from(sessionMap.values());
    
    // Check for data cleaned up
    const removedCount = originalCount - this.sessionsIndex.sessions.length;
    if (removedCount > 0) {
      console.log(`Cleaned up ${removedCount} sessions from index`);
      this.saveSessionsIndex();
    }
    
    // Clean up localStorage by removing orphaned chat data
    this.cleanOrphanedChatData();
  }
  
  // Clean up orphaned chat data in localStorage
  cleanOrphanedChatData() {
    // Get all active session IDs
    const activeSessionIds = new Set(this.sessionsIndex.sessions.map(session => session.id));
    
    // Look for chat data keys that don't match our sessions
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      
      // Skip non-chat data
      if (!key || !key.startsWith('radbot_chat_')) {
        continue;
      }
      
      // Extract session ID from key
      const sessionId = key.replace('radbot_chat_', '');
      
      // Check if it matches an active session
      if (!activeSessionIds.has(sessionId)) {
        console.log(`Removing orphaned chat data for session: ${sessionId}`);
        localStorage.removeItem(key);
      }
    }
  }
  
  // Create default sessions index structure
  createDefaultSessionsIndex() {
    // Use existing session ID from localStorage if available
    const existingSessionId = localStorage.getItem('radbot_session_id');
    
    // Create the base session with existing ID or new one
    const defaultSession = this.createDefaultSession(existingSessionId);
    
    // Create the sessions index
    this.sessionsIndex = {
      active_session_id: defaultSession.id,
      sessions: [defaultSession]
    };
    
    console.log('Created default sessions index with active session:', defaultSession.id);
    
    // Save it to localStorage
    this.saveSessionsIndex();
    
    // Update the active session ID in localStorage
    localStorage.setItem(ACTIVE_SESSION_KEY, defaultSession.id);
    
    // If needed, update the legacy session ID for backward compatibility
    if (!existingSessionId) {
      localStorage.setItem('radbot_session_id', defaultSession.id);
    }
  }
  
  // Create a default session object
  createDefaultSession(id = null) {
    // Generate a UUID if not provided
    const sessionId = id || (crypto.randomUUID ? crypto.randomUUID() : this.generateUUID());
    
    // Create the session object
    return {
      id: sessionId,
      name: `Session ${new Date().toLocaleDateString()}`,
      created_at: Date.now(),
      last_message_at: Date.now(),
      preview: "New session started"
    };
  }
  
  // Save the sessions index to localStorage
  saveSessionsIndex() {
    try {
      localStorage.setItem(SESSIONS_INDEX_KEY, JSON.stringify(this.sessionsIndex));
      console.log('Saved sessions index to localStorage');
      return true;
    } catch (error) {
      console.error('Error saving sessions index:', error);
      return false;
    }
  }
  
  // Generate a UUID for session ID
  generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      const r = Math.random() * 16 | 0;
      const v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }
  
  // Set chat persistence instance
  setChatPersistence(chatPersistence) {
    this.chatPersistence = chatPersistence;
  }
  
  // Initialize the sessions UI
  initSessionsUI() {
    // Find DOM elements
    this.sessionsContainer = document.getElementById('sessions-container');
    this.sessionSearch = document.getElementById('session-search');
    this.newSessionButton = document.getElementById('new-session-button');
    
    // Check if we found the container
    if (!this.sessionsContainer) {
      console.log('Sessions container not found, waiting for panel to be ready...');
      
      // Check if the sessions panel is open
      const sessionsPanel = document.querySelector('[data-content="sessions"]');
      
      if (sessionsPanel) {
        // Panel exists but container not found - wait briefly for DOM to update
        console.log('Sessions panel exists, waiting for DOM update...');
        setTimeout(() => {
          this.sessionsContainer = document.getElementById('sessions-container');
          if (this.sessionsContainer) {
            console.log('Sessions container found after delay, initializing...');
            this.completeInitialization();
          } else {
            console.warn('Sessions container still not found after delay');
          }
        }, 100);
      } else {
        // Panel not open, set an observer to initialize when it becomes available
        const observer = new MutationObserver((mutations, obs) => {
          // Check if sessions panel has been added
          const panel = document.querySelector('[data-content="sessions"]');
          if (panel) {
            console.log('Sessions panel detected in DOM');
            
            // Wait a moment for the panel content to be fully rendered
            setTimeout(() => {
              this.sessionsContainer = document.getElementById('sessions-container');
              if (this.sessionsContainer) {
                console.log('Sessions container found after panel open, initializing...');
                this.completeInitialization();
                obs.disconnect(); // Stop observing once initialized
              } else {
                console.warn('Sessions container not found after panel open');
              }
            }, 200);
          }
        });
        
        // Start observing the document body for DOM changes
        observer.observe(document.body, { childList: true, subtree: true });
        
        console.log('Set up observer for sessions panel');
      }
      
      return false;
    }
    
    return this.completeInitialization();
  }
  
  // Complete the initialization once the container is found
  completeInitialization() {
    // Set up event handlers
    if (this.newSessionButton) {
      // Clone and replace to prevent duplicate event handlers
      const newBtn = this.newSessionButton.cloneNode(true);
      if (this.newSessionButton.parentNode) {
        this.newSessionButton.parentNode.replaceChild(newBtn, this.newSessionButton);
      }
      this.newSessionButton = newBtn;
      this.newSessionButton.addEventListener('click', this.createNewSession.bind(this));
    }
    
    if (this.sessionSearch) {
      // Clone and replace to prevent duplicate event handlers
      const newSearch = this.sessionSearch.cloneNode(true);
      if (this.sessionSearch.parentNode) {
        this.sessionSearch.parentNode.replaceChild(newSearch, this.sessionSearch);
      }
      this.sessionSearch = newSearch;
      this.sessionSearch.addEventListener('input', this.filterSessions.bind(this));
    }
    
    // Render the sessions list
    this.renderSessionsList();

    // Fetch sessions from backend API and merge
    this.fetchSessionsFromAPI();

    // Set initialization flag
    this.initialized = true;
    
    console.log('Sessions UI initialized successfully');
    return true;
  }
  
  // Fetch sessions from the backend API and merge into localStorage index
  async fetchSessionsFromAPI() {
    try {
      const baseUrl = `${window.location.protocol}//${window.location.host}`;
      const response = await fetch(`${baseUrl}/api/sessions/`);

      if (!response.ok) {
        console.warn(`Sessions API returned status ${response.status}`);
        return;
      }

      const data = await response.json();
      const apiSessions = data.sessions || [];
      console.log(`Fetched ${apiSessions.length} sessions from API`);

      if (apiSessions.length === 0) return;

      // Build a map of existing local sessions by ID
      const localMap = new Map(
        this.sessionsIndex.sessions.map(s => [s.id, s])
      );

      let changed = false;

      for (const apiSession of apiSessions) {
        const local = localMap.get(apiSession.id);

        if (local) {
          // Merge: API is authoritative for name/preview/timestamps
          if (apiSession.name && apiSession.name !== local.name) {
            local.name = apiSession.name;
            changed = true;
          }
          if (apiSession.preview && apiSession.preview !== local.preview) {
            local.preview = apiSession.preview;
            changed = true;
          }
          if (apiSession.last_message_at) {
            const apiTime = new Date(apiSession.last_message_at).getTime();
            if (apiTime > (local.last_message_at || 0)) {
              local.last_message_at = apiTime;
              changed = true;
            }
          }
        } else {
          // New session from API — add to local index
          this.sessionsIndex.sessions.push({
            id: apiSession.id,
            name: apiSession.name || `Session ${apiSession.id.substring(0, 8)}`,
            created_at: new Date(apiSession.created_at).getTime(),
            last_message_at: apiSession.last_message_at
              ? new Date(apiSession.last_message_at).getTime()
              : Date.now(),
            preview: apiSession.preview || "Session"
          });
          changed = true;
        }
      }

      if (changed) {
        this.saveSessionsIndex();
        this.renderSessionsList();
      }
    } catch (error) {
      console.warn("Failed to fetch sessions from API:", error);
    }
  }

  // Render the sessions list with retry mechanism
  renderSessionsList(retryCount = 0) {
    const MAX_RETRIES = 3;
    
    // Try to find the container if not set yet
    if (!this.sessionsContainer) {
      this.sessionsContainer = document.getElementById('sessions-container');
    }
    
    // Check again if we found the container
    if (!this.sessionsContainer) {
      console.log(`Sessions container not found for rendering (attempt ${retryCount + 1}/${MAX_RETRIES + 1})`);
      
      // Check if sessions panel exists but container not found
      const sessionsPanel = document.querySelector('[data-content="sessions"]');
      if (sessionsPanel) {
        // Panel exists but DOM might not be fully ready - retry with delay
        if (retryCount < MAX_RETRIES) {
          console.log(`Sessions panel exists but container not found, retrying in ${200 * (retryCount + 1)}ms`);
          setTimeout(() => {
            this.renderSessionsList(retryCount + 1);
          }, 200 * (retryCount + 1));
        } else {
          console.warn(`Sessions container not found after ${MAX_RETRIES} retries`);
          // Try to re-initialize the UI as a last resort
          this.initSessionsUI();
        }
      } else {
        console.log('Sessions panel not open, rendering skipped');
      }
      return;
    }
    
    // Clear existing sessions
    this.sessionsContainer.innerHTML = '';
    
    // Get search filter if any
    const searchFilter = this.sessionSearch ? this.sessionSearch.value.toLowerCase() : '';
    
    // Filter and sort sessions
    const filteredSessions = this.sessionsIndex.sessions
      .filter(session => {
        if (!searchFilter) return true;
        return session.name.toLowerCase().includes(searchFilter) ||
               session.preview.toLowerCase().includes(searchFilter);
      })
      .sort((a, b) => b.last_message_at - a.last_message_at);
    
    // Check if we have sessions to display
    if (filteredSessions.length === 0) {
      const emptyState = document.createElement('div');
      emptyState.className = 'sessions-empty-state';
      
      if (searchFilter) {
        emptyState.textContent = 'No sessions match your search';
      } else {
        emptyState.textContent = 'No sessions found';
      }
      
      this.sessionsContainer.appendChild(emptyState);
      return;
    }
    
    // Render each session
    filteredSessions.forEach(session => {
      const sessionItem = document.createElement('div');
      sessionItem.className = 'session-item';
      sessionItem.dataset.id = session.id;
      
      // Mark active session
      if (session.id === this.sessionsIndex.active_session_id) {
        sessionItem.classList.add('active');
      }
      
      // Format date for display
      const sessionDate = new Date(session.created_at).toLocaleDateString();
      const lastActive = session.last_message_at ? this.formatTimestamp(session.last_message_at) : 'Never';
      
      // Add session content
      sessionItem.innerHTML = `
        <div class="session-title">${this.escapeHTML(session.name)}</div>
        <div class="session-meta">
          <span>Created: ${sessionDate}</span>
          <span>Last active: ${lastActive}</span>
        </div>
        <div class="session-preview">${this.escapeHTML(session.preview)}</div>
      `;
      
      // Add click handler
      sessionItem.addEventListener('click', () => {
        this.switchToSession(session.id);
      });
      
      this.sessionsContainer.appendChild(sessionItem);
    });
  }
  
  // Switch to a different session
  switchToSession(sessionId) {
    // Don't switch if already on this session
    if (sessionId === this.sessionsIndex.active_session_id) {
      console.log(`Already on session ${sessionId}`);
      return;
    }
    
    console.log(`Switching to session ${sessionId}`);
    
    // Store previous session ID for cleanup
    const previousSessionId = this.sessionsIndex.active_session_id;
    
    // Update the active session ID
    this.sessionsIndex.active_session_id = sessionId;
    localStorage.setItem(ACTIVE_SESSION_KEY, sessionId);
    localStorage.setItem('radbot_session_id', sessionId); // For backward compatibility
    
    // Save the sessions index
    this.saveSessionsIndex();
    
    // Update UI state
    if (window.state) {
      window.state.sessionId = sessionId;
    }
    
    // Update active session in UI
    this.updateActiveSessionUI(sessionId);
    
    // Load messages for the new session - do this before establishing WebSocket
    // so the UI shows content immediately
    if (window.loadChatFromStorage) {
      window.loadChatFromStorage();
    }
    
    // Handle WebSocket connection updates
    if (window.socketClient) {
      let closePromise = Promise.resolve();
      
      // First, properly close the connection for the old session
      if (window.socketClient.closeSocket && previousSessionId) {
        console.log(`Closing WebSocket for previous session ${previousSessionId}`);
        try {
          window.socketClient.closeSocket(previousSessionId);
          
          // Give the close operation a moment to complete
          closePromise = new Promise(resolve => setTimeout(resolve, 100));
        } catch (e) {
          console.warn(`Error closing previous WebSocket for session ${previousSessionId}:`, e);
        }
      }
      
      // After closing, connect to the new session
      closePromise.then(() => {
        if (window.socketClient.initSocket) {
          console.log(`Initializing WebSocket for new session ${sessionId}`);
          try {
            window.socket = window.socketClient.initSocket(sessionId);
          } catch (e) {
            console.error(`Error initializing WebSocket for session ${sessionId}:`, e);
          }
        }
      });
    }
    
    // Close any open panels
    this.closeSessionsPanel();
    
    // Dispatch event for other components
    window.dispatchEvent(new CustomEvent('sessionChanged', {
      detail: { sessionId, previousSessionId }
    }));
  }
  
  // Update UI to show the active session
  updateActiveSessionUI(sessionId) {
    // Update session items
    const sessionItems = document.querySelectorAll('.session-item');
    sessionItems.forEach(item => {
      if (item.dataset.id === sessionId) {
        item.classList.add('active');
      } else {
        item.classList.remove('active');
      }
    });
  }
  
  // Close the sessions panel
  closeSessionsPanel() {
    if (window.tilingManager) {
      // Check if panel is open before trying to close it
      const panel = document.querySelector('[data-content="sessions"]');
      if (panel) {
        window.tilingManager.togglePanel('sessions');
      }
    }
  }
  
  // Create a new session
  createNewSession() {
    // Store old session ID for cleanup
    const previousSessionId = this.sessionsIndex.active_session_id;
    
    // Create a new session object with guaranteed unique ID
    const newSession = this.createDefaultSession();
    
    console.log(`Creating new session with ID ${newSession.id}`);
    
    // Make sure it's not a duplicate before adding
    const existingSessionIndex = this.sessionsIndex.sessions.findIndex(s => s.id === newSession.id);
    if (existingSessionIndex >= 0) {
      console.warn(`Attempted to create session with duplicate ID ${newSession.id}, reusing existing session`);
      return this.switchToSession(newSession.id);
    }
    
    // Add to sessions index
    this.sessionsIndex.sessions.push(newSession);
    
    // Set as active session
    this.sessionsIndex.active_session_id = newSession.id;
    
    // Save the sessions index
    this.saveSessionsIndex();

    // Update localStorage for backward compatibility
    localStorage.setItem('radbot_session_id', newSession.id);
    localStorage.setItem(ACTIVE_SESSION_KEY, newSession.id);

    // Update UI state
    if (window.state) {
      window.state.sessionId = newSession.id;
    }

    // Sync new session to backend (fire-and-forget)
    try {
      const baseUrl = `${window.location.protocol}//${window.location.host}`;
      fetch(`${baseUrl}/api/sessions/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: newSession.id,
          name: newSession.name
        })
      }).catch(err => console.warn("Failed to sync new session to backend:", err));
    } catch (e) {
      console.warn("Error syncing new session to backend:", e);
    }

    // Re-render sessions list
    this.renderSessionsList();
    
    // Clear chat messages
    if (window.chatModule && window.chatModule.getChatElements().messages) {
      window.chatModule.getChatElements().messages.innerHTML = '';
      
      // Add welcome message
      window.chatModule.addMessage('system', 'New session started. Welcome to RadBot!');
      
      // Set initial chat history
      if (window.chatPersistence) {
        // Use the createMessageObject if available
        let initialMessage;
        if (window.createMessageObject) {
          initialMessage = window.createMessageObject('system', 'New session started. Welcome to RadBot!');
        } else if (window.chatModule && window.chatModule.createMessageObject) {
          initialMessage = window.chatModule.createMessageObject('system', 'New session started. Welcome to RadBot!');
        } else {
          // Fallback to direct object creation
          initialMessage = {
            id: crypto.randomUUID ? crypto.randomUUID() : this.generateUUID(),
            role: 'system',
            content: 'New session started. Welcome to RadBot!',
            timestamp: Date.now()
          };
        }
        window.chatPersistence.saveMessages(newSession.id, [initialMessage]);
      }
    }
    
    // Create a new WebSocket connection for the new session
    if (window.socketClient) {
      let closePromise = Promise.resolve();
      
      // First, properly close the connection for the old session
      if (window.socketClient.closeSocket && previousSessionId) {
        console.log(`Closing WebSocket for previous session ${previousSessionId}`);
        try {
          window.socketClient.closeSocket(previousSessionId);
          
          // Give the close operation a moment to complete
          closePromise = new Promise(resolve => setTimeout(resolve, 100));
        } catch (e) {
          console.warn(`Error closing previous WebSocket for session ${previousSessionId}:`, e);
        }
      }
      
      // After closing, connect to the new session
      closePromise.then(() => {
        if (window.socketClient.initSocket) {
          console.log(`Initializing WebSocket for new session ${newSession.id}`);
          try {
            window.socket = window.socketClient.initSocket(newSession.id);
          } catch (e) {
            console.error(`Error initializing WebSocket for new session ${newSession.id}:`, e);
          }
        }
      });
    }
    
    // Dispatch event for other components
    window.dispatchEvent(new CustomEvent('sessionChanged', {
      detail: { sessionId: newSession.id, previousSessionId }
    }));
    
    // Close the sessions panel
    this.closeSessionsPanel();
    
    return newSession;
  }
  
  // Rename a session
  renameSession(sessionId, newName) {
    // Find the session
    const sessionIndex = this.sessionsIndex.sessions.findIndex(s => s.id === sessionId);
    
    if (sessionIndex === -1) {
      console.error(`Session ${sessionId} not found`);
      return false;
    }
    
    // Update the name
    this.sessionsIndex.sessions[sessionIndex].name = newName;
    
    // Save the sessions index
    this.saveSessionsIndex();
    
    // Re-render sessions list
    this.renderSessionsList();
    
    return true;
  }
  
  // Delete a session
  deleteSession(sessionId) {
    // Don't delete if it's the only session
    if (this.sessionsIndex.sessions.length <= 1) {
      console.warn('Cannot delete the only session');
      return false;
    }
    
    // Don't delete the active session
    if (sessionId === this.sessionsIndex.active_session_id) {
      console.warn('Cannot delete the active session');
      return false;
    }
    
    // Find the session
    const sessionIndex = this.sessionsIndex.sessions.findIndex(s => s.id === sessionId);
    
    if (sessionIndex === -1) {
      console.error(`Session ${sessionId} not found`);
      return false;
    }
    
    // Remove the session
    this.sessionsIndex.sessions.splice(sessionIndex, 1);
    
    // Save the sessions index
    this.saveSessionsIndex();
    
    // Remove the session's chat data
    if (this.chatPersistence) {
      this.chatPersistence.clearChat(sessionId);
    }
    
    // Re-render sessions list
    this.renderSessionsList();
    
    return true;
  }
  
  // Filter sessions by search term
  filterSessions() {
    if (!this.sessionSearch) return;
    
    // Just re-render the list which includes filtering
    this.renderSessionsList();
  }
  
  // Update session preview with latest message
  updateSessionPreview(sessionId, messageContent, role) {
    // Find the session
    const sessionIndex = this.sessionsIndex.sessions.findIndex(s => s.id === sessionId);
    
    if (sessionIndex === -1) {
      console.error(`Session ${sessionId} not found for preview update`);
      return false;
    }
    
    // Create preview text
    let previewText = messageContent;
    
    // Truncate and clean up the preview text
    previewText = previewText
      .replace(/\n/g, ' ')     // Replace newlines with spaces
      .replace(/\s+/g, ' ')    // Replace multiple spaces with a single space
      .trim();                // Trim whitespace
    
    // Truncate to a reasonable length
    if (previewText.length > 100) {
      previewText = previewText.substring(0, 97) + '...';
    }
    
    // Add role prefix for assistant messages
    if (role === 'assistant') {
      previewText = '🤖 ' + previewText;
    } else if (role === 'user') {
      previewText = '👤 ' + previewText;
    }
    
    // Update session data
    this.sessionsIndex.sessions[sessionIndex].preview = previewText;
    this.sessionsIndex.sessions[sessionIndex].last_message_at = Date.now();
    
    // Save the sessions index
    this.saveSessionsIndex();
    
    // Re-render if initialized
    if (this.initialized) {
      this.renderSessionsList();
    }
    
    return true;
  }
  
  // Get active session ID
  getActiveSessionId() {
    return this.sessionsIndex.active_session_id;
  }
  
  // Get session by ID
  getSessionById(sessionId) {
    return this.sessionsIndex.sessions.find(s => s.id === sessionId);
  }
  
  // Handle storage events from other tabs
  handleStorageEvent(event) {
    if (event.key === SESSIONS_INDEX_KEY) {
      console.log('Sessions index updated in another tab, reloading...');
      
      // Reload sessions index
      try {
        this.sessionsIndex = JSON.parse(event.newValue);
        
        // Re-render if initialized
        if (this.initialized) {
          this.renderSessionsList();
        }
      } catch (error) {
        console.error('Error parsing sessions index from storage event:', error);
      }
    } else if (event.key === ACTIVE_SESSION_KEY) {
      console.log('Active session changed in another tab');
      
      // Update active session
      const newSessionId = event.newValue;
      
      if (newSessionId && newSessionId !== this.sessionsIndex.active_session_id) {
        this.sessionsIndex.active_session_id = newSessionId;
        
        // Update UI if initialized
        if (this.initialized) {
          this.updateActiveSessionUI(newSessionId);
        }
      }
    }
  }
  
  // Format timestamp as relative time
  formatTimestamp(timestamp) {
    const now = Date.now();
    const diff = now - timestamp;
    
    // Less than a minute
    if (diff < 60000) {
      return 'Just now';
    }
    
    // Less than an hour
    if (diff < 3600000) {
      const minutes = Math.floor(diff / 60000);
      return `${minutes} ${minutes === 1 ? 'minute' : 'minutes'} ago`;
    }
    
    // Less than a day
    if (diff < 86400000) {
      const hours = Math.floor(diff / 3600000);
      return `${hours} ${hours === 1 ? 'hour' : 'hours'} ago`;
    }
    
    // Less than a week
    if (diff < 604800000) {
      const days = Math.floor(diff / 86400000);
      return `${days} ${days === 1 ? 'day' : 'days'} ago`;
    }
    
    // Format as date
    return new Date(timestamp).toLocaleDateString();
  }
  
  // Escape HTML to prevent XSS
  escapeHTML(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
}

// Singleton instance
let sessionManager = null;

// Initialize and export the session manager
export function initSessionManager() {
  if (!sessionManager) {
    sessionManager = new SessionManager();
    
    // Make it globally available
    window.sessionManager = sessionManager;
    
    console.log('Session manager initialized');
  }
  
  return sessionManager;
}

// Setup event listener to initialize sessions UI when panel opens.
// NOTE: panel-trigger.js handles button clicks, tiling.js handles togglePanel().
// This listener only handles sessions UI initialization AFTER the panel is opened.
document.addEventListener('DOMContentLoaded', function() {
  console.log('Setting up sessions panel initialization hooks');

  // When sessions command fires, initialize the sessions UI after the panel opens
  document.addEventListener('command:sessions', function() {
    console.log('Sessions command received in sessions.js - initializing UI');

    // tiling.js handles the actual togglePanel call.
    // We just need to initialize the sessions UI after the panel opens.
    setTimeout(() => {
      if (window.tilingManager && window.tilingManager.panelStates.sessionsOpen && window.sessionManager) {
        if (!window.sessionManager.initialized) {
          window.sessionManager.initSessionsUI();
        } else if (!window.sessionManager.sessionsContainer) {
          window.sessionManager.renderSessionsList(0);
        }
        // Always refresh from API when panel opens
        window.sessionManager.fetchSessionsFromAPI();

        // Fallback retry
        setTimeout(() => {
          if (window.sessionManager && (!window.sessionManager.initialized || !window.sessionManager.sessionsContainer)) {
            window.sessionManager.initSessionsUI();
          }
        }, 300);
      }
    }, 200);
  });

  // Listen for layout changes to reinitialize UI
  document.addEventListener('layout:changed', function() {
    setTimeout(() => {
      if (window.sessionManager && window.tilingManager && window.tilingManager.panelStates.sessionsOpen) {
        console.log('Reinitializing sessions UI after layout change');
        window.sessionManager.initSessionsUI();
      }
    }, 300);
  });
});

// Export for module use
export { sessionManager };