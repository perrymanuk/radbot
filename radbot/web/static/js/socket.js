/**
 * Enhanced WebSocket management module for RadBot UI
 * With persistent connections, reconnection logic, and message queueing
 */

// WebSocket instance
let socket = null;
let socketConnected = false;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 10;
const INITIAL_RECONNECT_DELAY = 1000;
const MAX_RECONNECT_DELAY = 30000;
let pendingMessages = [];

// Map to keep track of all active WebSocket connections by session ID
const sessionConnections = {};

/**
 * WebSocketManager class for handling WebSocket connections with reconnection logic
 */
class WebSocketManager {
  constructor(baseUrl, sessionId) {
    this.baseUrl = baseUrl || `ws://${window.location.host}`;
    this.socket = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = MAX_RECONNECT_ATTEMPTS;
    this.initialReconnectDelay = INITIAL_RECONNECT_DELAY;
    this.maxReconnectDelay = MAX_RECONNECT_DELAY;
    this.sessionId = sessionId;
    this.messageCallbacks = [];
    this.stateCallbacks = [];
    this.connected = false;
    this.pendingMessages = [];
    this.heartbeatInterval = null;
    this.missedHeartbeats = 0;
    this.lastActivityTimestamp = Date.now();
    this._intentionalClose = false;

    // Connect immediately
    this.connect();
  }
  
  // Helper method to get readable WebSocket state
  getReadyStateString() {
    if (!this.socket) return 'NO_SOCKET';
    
    switch (this.socket.readyState) {
      case WebSocket.CONNECTING:
        return 'CONNECTING';
      case WebSocket.OPEN:
        return 'OPEN';
      case WebSocket.CLOSING:
        return 'CLOSING';
      case WebSocket.CLOSED:
        return 'CLOSED';
      default:
        return `UNKNOWN(${this.socket.readyState})`;
    }
  }
  
  connect() {
    // Properly close existing socket if needed
    if (this.socket) {
      try {
        // Only attempt to close if not already closed
        if (this.socket.readyState !== WebSocket.CLOSED) {
          console.log(`Closing existing socket for session ${this.sessionId} (state: ${this.getReadyStateString()})`);
          // Mark as intentional close so the onclose handler doesn't schedule a reconnect
          this._intentionalClose = true;
          // Use a clean close code to avoid excessive reconnection attempts
          this.socket.close(1000, "Clean reconnection");
        }
      } catch (e) {
        console.warn(`Error closing existing socket for session ${this.sessionId}:`, e);
      }
      this.socket = null;
    }

    // Check if we've had too many reconnection attempts in a short time
    if (this.reconnectAttempts > 5) {
      console.warn(`Too many reconnection attempts (${this.reconnectAttempts}), taking a longer break`);
      // Wait a bit longer between reconnection attempts
      setTimeout(() => {
        console.log("Resuming reconnection attempts after break");
        this._doConnect();
      }, 5000);
      return;
    }

    this._doConnect();
  }

  // Actual connection implementation
  _doConnect() {
    
    const wsUrl = `${this.baseUrl}/ws/${this.sessionId}`;
    console.log(`Connecting to WebSocket at ${wsUrl} (attempt #${this.reconnectAttempts + 1})`);

    try {
      // Update activity timestamp
      this.lastActivityTimestamp = Date.now();

      // Create new WebSocket with a short timeout
      const socket = new WebSocket(wsUrl);
      this.socket = socket;

      // Add connection timeout
      const connectionTimeout = setTimeout(() => {
        if (socket.readyState !== WebSocket.OPEN) {
          console.warn(`WebSocket connection timed out for session ${this.sessionId}`);
          try {
            socket.close(1000, "Connection timeout");
          } catch (e) {
            console.warn(`Error closing WebSocket after timeout: ${e}`);
          }
        }
      }, 5000);
      
      this.socket.onopen = () => {
        // Clear the connection timeout
        clearTimeout(connectionTimeout);

        console.log(`WebSocket connected for session ${this.sessionId}`);
        this.connected = true;
        this.reconnectAttempts = 0;
        socketConnected = true;
        this.lastActivityTimestamp = Date.now();
        
        // Update UI status
        if (window.statusUtils) {
          window.statusUtils.setStatus('ready');
        }
        
        // Start heartbeat after successful connection
        this.startHeartbeat();
        
        // Send any pending messages
        this.sendPendingMessages();
        
        // Request sync with server for any new messages
        if (window.chatPersistence) {
          const messages = window.chatPersistence.getMessages(this.sessionId);
          if (messages.length > 0) {
            const lastMessage = messages[messages.length - 1];
            console.log(`Requesting sync for session ${this.sessionId} since last message:`, lastMessage.id);
            
            this.send(JSON.stringify({
              type: 'sync_request',
              lastMessageId: lastMessage.id,
              timestamp: lastMessage.timestamp
            }));
          } else {
            // If no local messages, request limited history
            console.log(`No local messages for session ${this.sessionId}, requesting recent history`);
            this.send(JSON.stringify({
              type: 'history_request',
              limit: 50
            }));
          }
        }
      };
      
      this.socket.onmessage = (event) => {
        // Update activity timestamp
        this.lastActivityTimestamp = Date.now();
        
        // Add message size safety check for debugging
        try {
          const msgSize = event.data.length;
          if (msgSize > 500000) { // Log large messages (500KB+)
            console.warn(`Received very large message: ${msgSize} bytes`);
          }
          
          // Try to parse as JSON to check early
          if (msgSize > 0) {
            // Use a separate try block for parsing to ensure we still handle the message
            try {
              JSON.parse(event.data);
            } catch (parseError) {
              console.error(`WebSocket message parse error (before handler): ${parseError.message}`);
            }
          }
        } catch (e) {
          console.warn(`Error checking message size: ${e}`);
        }
        
        // Handle the message with error recovery
        try {
          this.handleMessage(event);
        } catch (error) {
          console.error(`Error in message handler: ${error.message}`);
          // Try to recover and not lose connection due to one bad message
        }
      };
      
      this.socket.onclose = (event) => {
        // Log detailed close info
        const wasClean = event.wasClean ? 'clean' : 'unclean';
        console.log(`WebSocket ${wasClean} disconnect for session ${this.sessionId}, code: ${event.code}, reason: ${event.reason || 'none'}`);

        // Stop heartbeat on disconnection
        this.stopHeartbeat();

        // If this close was triggered by connect() replacing this socket,
        // don't update state or schedule a reconnect (the new socket handles that)
        if (this._intentionalClose) {
          this._intentionalClose = false;
          console.log(`Intentional close for session ${this.sessionId}, skipping reconnect (new socket in progress)`);
          return;
        }

        this.connected = false;
        socketConnected = false;

        // Update UI status
        if (window.statusUtils) {
          window.statusUtils.setStatus('disconnected');
        }

        // Check if we should reconnect
        const timeSinceLastActivity = Date.now() - this.lastActivityTimestamp;
        const inactiveTimeThreshold = 10 * 60 * 1000; // 10 minutes

        if (timeSinceLastActivity > inactiveTimeThreshold) {
          console.log(`Session ${this.sessionId} has been inactive for ${Math.round(timeSinceLastActivity/1000/60)} minutes, not reconnecting`);
          return;
        }

        // Attempt to reconnect with exponential backoff
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          const delay = this.calculateReconnectDelay();
          console.log(`Connection closed for session ${this.sessionId}. Reconnecting in ${delay}ms...`);

          setTimeout(() => {
            this.reconnectAttempts++;
            this.connect();
          }, delay);
        } else {
          console.error(`Max reconnection attempts (${this.maxReconnectAttempts}) reached for session ${this.sessionId}`);
        }
      };
      
      this.socket.onerror = (error) => {
        console.error(`WebSocket error for session ${this.sessionId}:`, error);
        this.connected = false;
        socketConnected = false;
        
        // Update UI status
        if (window.statusUtils) {
          window.statusUtils.setStatus('error');
        }
      };
    } catch (error) {
      console.error(`Failed to connect WebSocket for session ${this.sessionId}:`, error);
      
      // Update UI status
      if (window.statusUtils) {
        window.statusUtils.setStatus('error');
      }
      
      // Try to reconnect after a delay
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        const delay = this.calculateReconnectDelay();
        console.log(`Connection attempt failed for session ${this.sessionId}. Retrying in ${delay}ms...`);
        
        setTimeout(() => {
          this.reconnectAttempts++;
          this.connect();
        }, delay);
      }
    }
  }
  
  calculateReconnectDelay() {
    // Exponential backoff with jitter
    const baseDelay = Math.min(
      this.maxReconnectDelay,
      this.initialReconnectDelay * Math.pow(2, this.reconnectAttempts)
    );
    // Add up to 30% jitter
    return baseDelay + (Math.random() * 0.3 * baseDelay);
  }
  
  send(data) {
    if (this.socket && this.connected) {
      this.socket.send(data);
    } else {
      console.log('WebSocket not connected, queueing message');
      this.pendingMessages.push(data);
    }
  }
  
  sendPendingMessages() {
    if (this.pendingMessages.length > 0) {
      console.log(`Sending ${this.pendingMessages.length} pending messages`);
      
      while (this.pendingMessages.length > 0) {
        const message = this.pendingMessages.shift();
        if (this.socket && this.connected) {
          this.socket.send(message);
        }
      }
    }
  }
  
  startHeartbeat() {
    this.stopHeartbeat(); // Clear any existing interval
    
    // Send heartbeat every 90 seconds
    this.heartbeatInterval = setInterval(() => {
      if (this.connected) {
        // Only send heartbeat if connection is still open
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
          console.log(`Sending heartbeat for session ${this.sessionId}`);
          this.send(JSON.stringify({ type: 'heartbeat' }));
          
          // Increment missed heartbeats counter
          this.missedHeartbeats++;
          
          // If we've missed too many heartbeats, close the connection and reconnect
          if (this.missedHeartbeats >= 8) {
            console.warn(`Too many missed heartbeats (${this.missedHeartbeats}) for session ${this.sessionId}, closing connection`);
            this.stopHeartbeat();
            if (this.socket) {
              try {
                // Only attempt to close if the socket is in an open or connecting state
                if (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING) {
                  this.socket.close(1000, "Heartbeat timeout"); // Use clean close code
                }
              } catch (e) {
                console.warn(`Error closing WebSocket: ${e}`);
              }
            }

            // Reset the socket completely
            this.socket = null;
            this.connected = false;

            // Set a longer reconnect delay after heartbeat failures
            this.reconnectAttempts = Math.min(this.maxReconnectAttempts - 1, this.reconnectAttempts + 2);
          }
        } else {
          // Socket isn't open, force reconnection
          console.warn(`Socket not open during heartbeat for session ${this.sessionId}, reconnecting...`);
          this.stopHeartbeat();
          this.connect();
        }
      }
    }, 90000);  // Increased from 60s to 90s
  }
  
  stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
    this.missedHeartbeats = 0;
  }
  
  handleMessage(event) {
    try {
      const data = JSON.parse(event.data);
      
      // Reset missed heartbeats on any message
      this.missedHeartbeats = 0;
      
      if (data.type === 'heartbeat') {
        // Handle heartbeat with session info for debugging
        console.log(`Received heartbeat response for session ${this.sessionId}`);
        
        // Additional debug info for tracking connection status
        if (this.socket) {
          console.log(`WebSocket state for ${this.sessionId}: ${this.getReadyStateString()}`); 
        }
        return;
      }
      
      if (data.type === 'sync_response' || data.type === 'history') {
        // Handle server providing message history
        console.log(`Received ${data.type} with ${data.messages ? data.messages.length : 0} messages`);
        
        if (data.messages && data.messages.length > 0 && window.chatPersistence) {
          const localMessages = window.chatPersistence.getMessages(this.sessionId);
          
          // Merge server messages with local messages
          if (window.mergeMessages) {
            const mergedMessages = window.mergeMessages(localMessages, data.messages);
            window.chatPersistence.saveMessages(this.sessionId, mergedMessages);
            
            // Refresh the UI if it's a full history update
            if (data.type === 'history') {
              console.log('Refreshing UI with merged messages');
              
              // Clear chat messages
              const chatMessages = window.chatModule.getChatElements().messages;
              if (chatMessages) {
                chatMessages.innerHTML = '';
              }
              
              // Render merged messages
              mergedMessages.forEach(msg => {
                if (msg.role && msg.content) {
                  window.chatModule.addMessage(msg.role, msg.content, msg.agent);
                }
              });
              
              window.chatModule.scrollToBottom();
            }
          }
        }
        return;
      }
      
      // Handle scheduled task notifications (reminders)
      if (data.type === 'scheduled_task_result') {
        console.log(`Scheduled task notification: ${data.task_name}`);
        const label = `⏰ [${data.task_name}]`;
        window.chatModule.addMessage('system', `${label} ${data.prompt}`);
        window.chatModule.scrollToBottom();
        // Auto-play TTS if enabled
        if (window.ttsManager && window.ttsManager.autoPlay && data.prompt) {
          window.ttsManager.enqueue(data.prompt);
        }
        return;
      }

      // Handle webhook results
      if (data.type === 'webhook_result') {
        console.log(`Webhook result: ${data.webhook_name}`);
        const label = `[Webhook: ${data.webhook_name}]`;
        window.chatModule.addMessage('system', `${label} ${data.prompt}`);
        if (data.response) {
          window.chatModule.addMessage('assistant', data.response, 'WEBHOOK');
          window.chatModule.scrollToBottom();
        }
        // Auto-play TTS if enabled
        if (window.ttsManager && window.ttsManager.autoPlay && data.response) {
          window.ttsManager.enqueue(data.response);
        }
        return;
      }

      // We no longer handle 'message' type as we only use events now
      if (data.type === 'status') {
        window.statusUtils.handleStatusUpdate(data.content);
      } else if (data.type === 'events') {
        // Process incoming events
        console.log('Received events data:', data.content);
        
        // Process various event types
        if (Array.isArray(data.content)) {
          const modelResponses = [];
          data.content.forEach(event => {
            // Handle agent transfer events - Check for actions.transfer_to_agent (ADK 0.4.0 style)
            if (event.actions && event.actions.transfer_to_agent) {
              const newAgent = event.actions.transfer_to_agent;
              console.log(`ADK 0.4.0 agent transfer detected via actions.transfer_to_agent: ${newAgent}`);
              console.log(`Agent transfer: ${window.state.currentAgentName} → ${newAgent}`);

              // Store this as a permanent transfer so it persists across page refreshes
              try {
                if (window.localStorage) {
                  window.localStorage.setItem('lastActiveAgent', newAgent);
                  console.log(`Stored ${newAgent} as lastActiveAgent in localStorage`);
                }
              } catch (e) {
                console.warn(`Failed to update localStorage with lastActiveAgent: ${e}`);
              }

              // Update agent state (simplified approach)
              if (window.switchAgentContext && typeof window.switchAgentContext === 'function') {
                // Call the simplified switchAgentContext function
                window.switchAgentContext(newAgent);
                console.log(`Agent name updated to: ${newAgent} (simplified approach)`);
              } else {
                // Direct update if function not available
                window.state.currentAgentName = newAgent;
                console.log(`Agent name directly updated to: ${newAgent}`);
              }

              // Always clear pending messages on agent transfer to prevent context bleed
              if (this.pendingMessages && this.pendingMessages.length > 0) {
                console.log(`Clearing ${this.pendingMessages.length} pending messages after agent transfer`);
                this.pendingMessages = [];
              }

              // IMPORTANT: First update the model before updating the agent status
              // This ensures the model update isn't overridden by updateAgentStatus

              // Get model from event details if available
              if (event.details && event.details.model) {
                window.statusUtils.updateModelStatus(event.details.model);
                console.log(`Updated model from event details: ${event.details.model}`);
              }
              // Try to get model from agentModels if available
              else if (window.state.agentModels) {
                // Convert to lowercase for case-insensitive lookup
                const agentKey = newAgent.toLowerCase();

                // Handle 'scout' agent specially since it's stored as scout_agent in backend
                if (agentKey === 'scout' && window.state.agentModels['scout_agent']) {
                  window.statusUtils.updateModelStatus(window.state.agentModels['scout_agent']);
                  console.log(`Updated model from agentModels for scout: ${window.state.agentModels['scout_agent']}`);
                }
                // Try exact match
                else if (window.state.agentModels[agentKey]) {
                  window.statusUtils.updateModelStatus(window.state.agentModels[agentKey]);
                  console.log(`Updated model from agentModels: ${window.state.agentModels[agentKey]}`);
                }
                // Try agent_name format
                else if (window.state.agentModels[agentKey + '_agent']) {
                  window.statusUtils.updateModelStatus(window.state.agentModels[agentKey + '_agent']);
                  console.log(`Updated model from agentModels with _agent suffix: ${window.state.agentModels[agentKey + '_agent']}`);
                }
                // Fallback to updateModelForCurrentAgent
                else {
                  console.log(`Agent ${agentKey} not found in agentModels, using fallback lookup...`);
                  if (typeof window.updateModelForCurrentAgent === 'function') {
                    // Temporarily set the agent name so updateModelForCurrentAgent works
                    const savedAgent = window.state.currentAgentName;
                    window.state.currentAgentName = newAgent;
                    window.updateModelForCurrentAgent();
                    window.state.currentAgentName = savedAgent; // Restore
                  }
                }
              }
              // Last resort fallback
              else if (typeof window.updateModelForCurrentAgent === 'function') {
                // Temporarily set the agent name so updateModelForCurrentAgent works
                const savedAgent = window.state.currentAgentName;
                window.state.currentAgentName = newAgent;
                window.updateModelForCurrentAgent();
                window.state.currentAgentName = savedAgent; // Restore
              }

              // Now update the agent status
              window.statusUtils.updateAgentStatus(newAgent);

              // Force an update of the status bar
              if (window.statusUtils.updateStatusBar) {
                window.statusUtils.updateStatusBar();
              }

              // Add a system message to notify the user about the agent change
              const transferMessage = `Agent switched to: ${newAgent.toUpperCase()}`;
              window.chatModule.addMessage('system', transferMessage);
            }
            
            // Collect model_response events (don't display yet)
            if ((event.type === 'model_response' || event.category === 'model_response') && event.text) {
              modelResponses.push(event);
            }
          });

          // Display only the LAST model_response to avoid duplicates
          // (matches the REST fallback approach in chat.js)
          if (modelResponses.length > 0) {
            // Prefer the event marked as final; otherwise use the last one
            const responseEvent = modelResponses.find(e => e.is_final) || modelResponses[modelResponses.length - 1];
            console.log(`Displaying 1 of ${modelResponses.length} model_response events (is_final: ${responseEvent.is_final})`);

            // Check for model information in event details
            if (responseEvent.details && responseEvent.details.model) {
              window.statusUtils.updateModelStatus(responseEvent.details.model);
            }

            // Check if the response indicates a specific agent
            let agentName = window.state.currentAgentName;
            if (responseEvent.agent_name) {
              agentName = responseEvent.agent_name.toUpperCase();
            } else if (responseEvent.details && responseEvent.details.agent_name) {
              agentName = responseEvent.details.agent_name.toUpperCase();
            } else if (responseEvent.details && responseEvent.details.agent) {
              agentName = responseEvent.details.agent.toUpperCase();
            }

            // Update the current agent if it has changed
            if (agentName !== window.state.currentAgentName) {
              console.log(`Agent change detected from model_response: ${window.state.currentAgentName} → ${agentName}`);
              if (responseEvent.details && responseEvent.details.model) {
                window.statusUtils.updateModelStatus(responseEvent.details.model);
              } else if (typeof window.updateModelForCurrentAgent === 'function') {
                const previousAgent = window.state.currentAgentName;
                window.state.currentAgentName = agentName;
                window.updateModelForCurrentAgent();
                window.state.currentAgentName = previousAgent;
              }
              window.statusUtils.updateAgentStatus(agentName);
              if (window.statusUtils && window.statusUtils.updateStatusBar) {
                window.statusUtils.updateStatusBar();
              }
            }

            // Display the single response
            const textSize = responseEvent.text ? responseEvent.text.length : 0;
            if (textSize > 0) {
              if (textSize > 500000) {
                window.chatModule.addMessage('system', `Rendering large message (${Math.round(textSize/1024)}KB)...`);
              }
              try {
                window.chatModule.addMessage('assistant', responseEvent.text, agentName);
                window.chatModule.scrollToBottom();
                // Auto-play TTS if enabled
                if (window.ttsManager && window.ttsManager.autoPlay) {
                  window.ttsManager.enqueue(responseEvent.text);
                }
              } catch (displayError) {
                console.error(`Error displaying message: ${displayError.message}`);
                try {
                  const truncatedText = responseEvent.text.substring(0, 100000) +
                    `\n\n[Message truncated for display. Original size: ${Math.round(textSize/1024)}KB]`;
                  window.chatModule.addMessage('assistant', truncatedText, agentName);
                  window.chatModule.scrollToBottom();
                } catch (fallbackError) {
                  console.error(`Fallback display also failed: ${fallbackError.message}`);
                  window.chatModule.addMessage('system', `Error: Could not display large message (${Math.round(textSize/1024)}KB). The response was too large to render.`);
                }
              }
            }
          }
        }
        
        // Pass to event handler if it exists
        if (typeof handleEvents === 'function') {
          handleEvents(data.content);
        }
      } else if (data.type === 'tasks') {
        // Process incoming tasks
        console.log('Received tasks data:', data.content);
        if (typeof handleTasks === 'function') {
          handleTasks(data.content);
        }
      }
    } catch (error) {
      console.error('Error handling WebSocket message:', error);
    }
  }
}

// Cooldown for creating new connections (to prevent rapid reconnects)
let lastConnectionTime = 0;
const CONNECTION_COOLDOWN = 1000; // 1 second minimum between connections

// Initialize WebSocket connection
export function initSocket(sessionId) {
  console.log('Initializing WebSocket connection with session ID:', sessionId);
  
  // Prevent excessive connection attempts in a short time
  const now = Date.now();
  const timeSinceLastConnection = now - lastConnectionTime;
  
  if (timeSinceLastConnection < CONNECTION_COOLDOWN) {
    console.log(`Connection attempt too soon (${timeSinceLastConnection}ms since last connection)`);
    console.log(`Delaying connection for ${CONNECTION_COOLDOWN - timeSinceLastConnection}ms`);
    
    // Create a promise that resolves after the cooldown period
    return new Promise(resolve => {
      setTimeout(() => {
        console.log(`Cooldown complete, continuing with connection to ${sessionId}`);
        const connection = _initSocketImplementation(sessionId);
        resolve(connection);
      }, CONNECTION_COOLDOWN - timeSinceLastConnection);
    });
  }
  
  // Update last connection time
  lastConnectionTime = now;
  
  // Proceed with normal initialization
  return _initSocketImplementation(sessionId);
}

// Actual implementation of socket initialization (to allow for delayed calls)
function _initSocketImplementation(sessionId) {
  // Check if we already have a connection for this session
  if (sessionConnections[sessionId]) {
    console.log(`Reusing existing WebSocket connection for session ${sessionId}`);
    
    // Get the existing manager
    const manager = sessionConnections[sessionId];
    
    // If the connection was closed, reconnect
    if (!manager.connected) {
      // Get the current socket state for better logging
      const socketState = manager.socket ? manager.getReadyStateString() : 'NO_SOCKET';
      console.log(`Reconnecting existing WebSocket for session ${sessionId} (current state: ${socketState})`);
      
      // Check if we've attempted a reconnect recently
      const timeSinceLastActivity = Date.now() - manager.lastActivityTimestamp;
      if (timeSinceLastActivity < 2000) { // 2 seconds
        console.log(`Recent activity detected (${timeSinceLastActivity}ms ago), delaying reconnect`);
        // Don't attempt another reconnect if there was recent activity
        // This helps prevent connection thrashing
        
        // Still return an interface that appears connected
        return createSocketInterface(manager, sessionId);
      }
      
      // Safe to reconnect
      manager.connect();
    }
    
    // Extract socket from manager
    socket = manager.socket;
    
    // Return the existing interface
    return createSocketInterface(manager, sessionId);
  }
  
  // Create a new WebSocketManager instance with safe URL generation
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}`;
  
  console.log(`Creating new WebSocketManager for ${sessionId} at ${wsUrl}`);
  const manager = new WebSocketManager(wsUrl, sessionId);
  
  // Store in our sessions map
  sessionConnections[sessionId] = manager;
  
  // Extract socket from manager
  socket = manager.socket;
  
  // Return a simplified interface
  return createSocketInterface(manager, sessionId);
}

// Create a standardized interface for socket interaction
function createSocketInterface(manager, sessionId) {
  return {
    socket: manager.socket,
    // Use a getter so socketConnected always reflects the live connection state
    // (previously this was a snapshot that went stale after disconnect/reconnect)
    get socketConnected() { return manager.connected; },
    sessionId: sessionId,
    send: (data) => {
      if (manager && typeof data === 'string') {
        manager.send(data);
      } else if (typeof data === 'object') {
        manager.send(JSON.stringify(data));
      } else {
        console.error('Invalid data format for WebSocket send:', data);
      }
    },
    // Expose the manager for advanced usage
    manager: manager
  };
}

// Close a session's WebSocket connection
export function closeSocket(sessionId) {
  if (sessionConnections[sessionId]) {
    console.log(`Closing WebSocket connection for session ${sessionId}`);
    const manager = sessionConnections[sessionId];
    
    // Stop heartbeat to prevent reconnection attempts
    manager.stopHeartbeat();
    
    try {
      // Close the socket with clean code if it's open
      if (manager.socket) {
        const state = manager.getReadyStateString();
        console.log(`WebSocket for session ${sessionId} is in state ${state} before close`);
        
        if (manager.socket.readyState === WebSocket.OPEN || 
            manager.socket.readyState === WebSocket.CONNECTING) {
          // Use clean close code 1000 (normal closure)
          manager.socket.close(1000, "Session change");
        }
      }
    } catch (e) {
      console.warn(`Error during WebSocket clean close for session ${sessionId}:`, e);
    }
    
    // Clean up all resources
    manager.connected = false;
    manager.socket = null;
    
    // Remove from our sessions map to prevent memory leaks
    delete sessionConnections[sessionId];
    
    console.log(`WebSocket connection for session ${sessionId} successfully closed`);
    return true;
  }
  
  console.log(`No WebSocket connection found for session ${sessionId}`);
  return false;
}

// Handle incoming tasks data
function handleTasks(tasksData) {
  if (!tasksData || !Array.isArray(tasksData)) {
    console.error('Invalid tasks data received:', tasksData);
    return;
  }
  
  window.tasks = tasksData;
  
  // Check if tasks view is available before rendering
  if (typeof window.renderTasks === 'function') {
    window.renderTasks();
  }
}

// Handle incoming events data
function handleEvents(eventsData) {
  if (!eventsData || !Array.isArray(eventsData)) {
    console.error('Invalid events data received:', eventsData);
    return;
  }
  
  window.events = eventsData;
  
  // Check if events view is available before rendering
  if (typeof window.renderEvents === 'function') {
    window.renderEvents();
  }
}