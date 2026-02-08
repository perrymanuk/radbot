/**
 * Chat functionality module for RadBot UI
 */

// DOM References
let chatMessages;
let chatInput;
let sendButton;
let resetButton;

// Export references to be used by other modules
export function getChatElements() {
    return {
        messages: chatMessages,
        input: chatInput,
        sendButton: sendButton,
        resetButton: resetButton
    };
}

// Initialize chat functionality
export function initChat() {
    console.log('Initializing chat module');
    
    // Initialize DOM references
    chatMessages = document.getElementById('chat-messages');
    chatInput = document.getElementById('chat-input');
    sendButton = document.getElementById('send-button');
    resetButton = document.getElementById('reset-button');
    
    // If any critical elements are missing, return false
    if (!chatInput || !chatMessages) {
        console.log('Critical chat UI elements not found');
        return false;
    }
    
    // Configure Marked.js with syntax highlighting using Prism
    if (typeof marked !== 'undefined') {
        marked.setOptions({
            highlight: function(code, lang) {
                if (Prism && lang && Prism.languages[lang]) {
                    try {
                        return Prism.highlight(code, Prism.languages[lang], lang);
                    } catch (e) {
                        console.warn('Error highlighting code:', e);
                        return code;
                    }
                }
                return code;
            },
            breaks: true,
            gfm: true
        });
    }
    
    // Add chat event listeners
    chatInput.addEventListener('keydown', handleInputKeydown);
    
    // Auto-resize textarea as user types and check for memory indicator
    chatInput.addEventListener('input', function(event) {
        resizeTextarea();
        updateMemoryIndicator();
        
        // Remove history mode highlighting when user starts typing
        if (messageHistoryIndex !== -1) {
            messageHistoryIndex = -1;
            chatInput.classList.remove('history-mode');
        }
    });
    
    // Set initial compact height
    setTimeout(resizeTextarea, 0);
    
    if (sendButton) {
        sendButton.addEventListener('click', sendMessage);
    }
    
    if (resetButton) {
        resetButton.addEventListener('click', resetConversation);
    }
    
    return true;
}

// Add a message to the chat UI
export function addMessage(role, content, agentName) {
    // Ensure chatMessages element exists
    if (!chatMessages) {
        chatMessages = document.getElementById('chat-messages');
        if (!chatMessages) {
            console.error('Chat messages container not found, message not added');
            return;
        }
    }
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    // Note: Emoji conversion now happens right before markdown rendering
    
    // Set custom prompt for assistant messages based on current agent
    if (role === 'assistant') {
        // Allow specifying a custom agent for this message
        const agent = agentName || window.state.currentAgentName;
        
        // Add a custom data attribute for the prompt
        // Use lowercase for the terminal prompt style
        contentDiv.dataset.agentPrompt = `${agent.toLowerCase()}@radbox:~$ `;
        
        // Store the agent name as a data attribute for future reference
        messageDiv.dataset.agent = agent.toUpperCase();
    }
    
    // Check content size and handle very large messages more efficiently
    const contentSize = content ? content.length : 0;
    
    // Add size indicator for large messages
    if (contentSize > 100000) {
        console.warn(`Rendering large content: ${contentSize} chars`);
        messageDiv.classList.add('large-message');
        
        // Add a size indicator for very large messages
        const sizeIndicator = document.createElement('div');
        sizeIndicator.className = 'message-size-indicator';
        sizeIndicator.textContent = `Large message: ${Math.round(contentSize/1024)}KB`;
        messageDiv.appendChild(sizeIndicator);
    }
    
    // First convert emoji shortcodes to Unicode emojis
    content = window.emojiUtils.convertEmoji(content);
    
    // Then use marked.js to render markdown with compact options
    if (typeof marked !== 'undefined') {
        // For very large contents, simplify processing to improve performance
        if (contentSize > 300000) {
            // Skip some processing for extremely large content
            console.warn(`Using simplified rendering for very large content: ${contentSize} chars`);
        } else {
            // Normal processing - reduce blank lines for compactness
            content = content.replace(/\n\s*\n/g, '\n');
        }
        
        // Important: Check if the content already contains HTML with our special content-type elements.
        // If so, we need to handle them specially to prevent marked from modifying them
        const containsContentTypeElements = /<pre data-content-type=/i.test(content);
        
        if (containsContentTypeElements) {
            // Extract and preserve typed content blocks before markdown processing
            const preservedBlocks = [];
            const placeholders = [];
            
            // Extract content-type elements
            const contentTypeRegex = /<pre data-content-type=["']([^"']+)["'][^>]*>([\s\S]*?)<\/pre>/gi;
            let match;
            let index = 0;
            
            // Use regex to find all content-typed blocks and replace with placeholders
            let modifiedContent = content;
            while ((match = contentTypeRegex.exec(content)) !== null) {
                // Create a unique placeholder
                const placeholder = `__CONTENT_TYPE_PLACEHOLDER_${index}__`;
                placeholders.push(placeholder);
                
                // Save the original content
                preservedBlocks.push(match[0]);
                
                // Replace with placeholder
                modifiedContent = modifiedContent.replace(match[0], placeholder);
                index++;
            }
            
            // Process the content with placeholders using marked
            const parsedContent = marked.parse(modifiedContent);
            
            // Restore preserved blocks
            let finalContent = parsedContent;
            for (let i = 0; i < placeholders.length; i++) {
                finalContent = finalContent.replace(placeholders[i], preservedBlocks[i]);
            }
            
            // Set the final content
            contentDiv.innerHTML = finalContent;
        } else {
            // No special content blocks - now check for JSON code blocks
            const jsonCodeBlockRegex = /```(?:json)?\s*([\s\S]*?)```/g;
            content = content.replace(jsonCodeBlockRegex, function(match, jsonContent) {
                // For regular JSON content
                if (jsonContent.trim().startsWith('{') || jsonContent.trim().startsWith('[')) {
                    try {
                        // Handle escaped newlines by replacing them with actual newlines
                        const processedContent = jsonContent
                            .replace(/\\n/g, '\n')
                            .replace(/\\"/g, '"')
                            .replace(/\\\\/g, '\\');
                        
                        // Try to parse the JSON
                        const jsonObj = JSON.parse(processedContent);
                        
                        // Check if this is a special response type
                        const jsonString = JSON.stringify(jsonObj);
                        if (jsonString.includes('call_search_agent_response') || 
                            jsonString.includes('call_web_search_response') || 
                            jsonString.includes('function_call_response')) {
                            // This is a special response - preserve original formatting 
                            return `<pre data-content-type="json-raw" class="content-json-raw">${processedContent}</pre>`;
                        } else {
                            // Regular JSON - format nicely 
                            const formattedJson = JSON.stringify(jsonObj, null, 2);
                            return `<pre data-content-type="json-formatted" class="content-json-formatted">${formattedJson}</pre>`;
                        }
                    } catch (e) {
                        console.warn('Error parsing potential JSON in code block:', e);
                        // If it looks like JSON but parsing failed, still add class for highlighting
                        if (jsonContent.includes('{') || jsonContent.includes('[')) {
                            // Clean up escaped sequences as much as possible
                            const cleanedContent = jsonContent
                                .replace(/\\n/g, '\n')
                                .replace(/\\"/g, '"')
                                .replace(/\\\\/g, '\\');
                            return `<pre data-content-type="json-raw" class="content-json-raw">${cleanedContent}</pre>`;
                        }
                        return match; // Keep original if not JSON-like
                    }
                }
                return match; // Not JSON, return unchanged
            });
            
            // Process the content with marked
            contentDiv.innerHTML = marked.parse(content);
        }
        
        // Find all content-type elements that need highlighting
        const jsonElements = contentDiv.querySelectorAll('pre[data-content-type^="json-"]');
        
        // Apply Prism.js highlighting to JSON content if available
        if (typeof Prism !== 'undefined' && Prism.languages.json && jsonElements.length > 0) {
            jsonElements.forEach(element => {
                try {
                    // Get the content type
                    const contentType = element.getAttribute('data-content-type');
                    
                    // Check if content is actually JSON-like (has { or [)
                    const elementText = element.textContent.trim();
                    if (elementText.startsWith('{') || elementText.startsWith('[')) {
                        // For formatted JSON, ensure it's properly highlighted
                        if (contentType === 'json-formatted') {
                            // Apply Prism highlighting
                            const code = element.textContent;
                            element.innerHTML = Prism.highlight(code, Prism.languages.json, 'json');
                        }
                        // For raw JSON, apply minimal highlighting but preserve format exactly
                        else if (contentType === 'json-raw') {
                            // Do not apply Prism highlighting to raw JSON
                            // Instead, just ensure it has the RAW indicator
                            element.classList.add('raw-json-content');
                        }
                    } else {
                        // This isn't actually JSON syntax; remove the JSON type to avoid confusion
                        element.removeAttribute('data-content-type');
                        element.className = '';
                    }
                } catch (e) {
                    console.warn('Error applying syntax highlighting:', e);
                }
            });
        }
    } else {
        contentDiv.textContent = content;
    }
    
    // For system messages, add animations to simulate terminal loading
    if (role === 'system') {
        messageDiv.classList.add('system-message');
        
        // Add a small delay before showing the message
        setTimeout(() => {
            messageDiv.style.opacity = "1";
        }, 100);
    }
    
    // For assistant messages, simulate typing effect with the cursor
    if (role === 'assistant') {
        // Add typing cursor animation to the last message
        const messages = document.querySelectorAll('.message.assistant');
        messages.forEach(msg => {
            const lastPara = msg.querySelector('.message-content p:last-child');
            if (lastPara && lastPara.classList.contains('with-cursor')) {
                lastPara.classList.remove('with-cursor');
            }
        });
    }
    
    messageDiv.appendChild(contentDiv);

    // Add TTS play button to assistant messages
    if (role === 'assistant' && window.ttsManager) {
        try {
            // Dynamic import to avoid circular dependency
            if (typeof window.addTTSButton === 'function') {
                window.addTTSButton(messageDiv);
            }
        } catch (e) {
            // TTS module may not be loaded yet
        }
    }
    
    // Verify chat messages container exists
    if (!chatMessages) {
        chatMessages = document.getElementById('chat-messages');
        if (!chatMessages) {
            console.error('Chat messages container not found, creating fallback');
            // Create a fallback container if one doesn't exist
            chatMessages = document.createElement('div');
            chatMessages.id = 'chat-messages';
            chatMessages.className = 'chat-messages';
            document.body.appendChild(chatMessages);
        }
    }
    
    // Append the message
    chatMessages.appendChild(messageDiv);
    
    // Store message in persistence layer if we have a session ID
    // Check if this message is part of the initial load from localStorage
    const isInitialLoad = window.initialLoadInProgress === true;
    
    if (window.state && window.state.sessionId && window.chatPersistence && !isInitialLoad) {
        try {
            console.log(`Storing message for session ${window.state.sessionId}`);
            
            // Create a message object with a unique ID
            const messageObj = {
                id: crypto.randomUUID ? crypto.randomUUID() : generateUUID(),
                role: role,
                content: content,
                timestamp: Date.now(),
                agent: agentName || (window.state ? window.state.currentAgentName : null)
            };
            
            // Use the addMessage method to handle storage and server sync
            window.chatPersistence.addMessage(window.state.sessionId, messageObj);
            
            // Update session preview if session manager is available
            if (window.sessionManager && role !== 'system') {
                window.sessionManager.updateSessionPreview(window.state.sessionId, content, role);
            }
        } catch (error) {
            console.error('Error saving message to persistence:', error);
        }
    }
    
    // If Prism.js is available, highlight code blocks in the newly added message
    if (typeof Prism !== 'undefined') {
        // Allow DOM to update before highlighting
        setTimeout(() => {
            // Find all code blocks that need highlighting in this message
            const codeBlocks = messageDiv.querySelectorAll('pre code');
            if (codeBlocks.length > 0) {
                codeBlocks.forEach(codeBlock => {
                    // Get the language class if it exists
                    const preElement = codeBlock.parentElement;
                    const classes = preElement.className.split(' ');
                    let languageClass = classes.find(cl => cl.startsWith('language-'));
                    
                    // Check if code block exceeds max lines
                    const maxLines = 20;
                    const codeText = codeBlock.textContent || '';
                    const lineCount = (codeText.match(/\n/g) || []).length + 1;
                    
                    if (lineCount > maxLines) {
                        // Add scrollable class to pre element
                        preElement.classList.add('code-scrollable');
                        
                        // Add line count indicator
                        const lineCountIndicator = document.createElement('div');
                        lineCountIndicator.className = 'code-line-count';
                        lineCountIndicator.textContent = `${lineCount} lines`;
                        preElement.appendChild(lineCountIndicator);
                    }
                    
                    if (languageClass) {
                        // Ensure Prism recognizes this language
                        const language = languageClass.replace('language-', '');
                        if (Prism.languages[language]) {
                            // Apply highlighting
                            Prism.highlightElement(codeBlock);
                        }
                    } else {
                        // No language specified, try to detect the language
                        Prism.highlightElement(codeBlock);
                    }
                });
            }
        }, 50);
    }
    
    // Scroll to bottom with a slight delay to ensure DOM updates
    setTimeout(scrollToBottom, 10);
    
    // Also try scrolling after a longer delay just to be sure
    setTimeout(scrollToBottom, 300);
}

// Helper function to generate a UUID if not available in the browser
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

// Message history navigation
let messageHistory = [];
let messageHistoryIndex = -1;
let currentInputValue = '';

// Handle input keydown (send on Enter, new line on Shift+Enter, navigate history with Up/Down)
function handleInputKeydown(event) {
    // Check if command-suggestions element exists
    const commandSuggestionsElement = document.getElementById('command-suggestions');
    
    // If emoji suggestions are showing, don't send on Enter
    if (event.key === 'Enter' && !event.shiftKey && 
        window.emojiUtils.getSuggestions().length === 0 && 
        (!commandSuggestionsElement || !commandSuggestionsElement.classList.contains('visible'))) {
        event.preventDefault();
        sendMessage();
    }
    
    // Message history navigation with arrow keys - add debug logs
    if (event.key === 'ArrowUp' && !event.shiftKey) {
        console.log("UP ARROW - Before navigation: messageHistoryIndex =", messageHistoryIndex);
        
        // If first time pressing up, save the current input value
        if (messageHistoryIndex === -1) {
            currentInputValue = chatInput.value;
            console.log("Saved current input:", currentInputValue);
        }
        
        // Navigate backward in history
        navigateMessageHistory(-1);
        
        console.log("UP ARROW - After navigation: messageHistoryIndex =", messageHistoryIndex);
        event.preventDefault();
    } else if (event.key === 'ArrowDown' && !event.shiftKey) {
        console.log("DOWN ARROW - Before navigation: messageHistoryIndex =", messageHistoryIndex);
        
        // Navigate forward in history
        navigateMessageHistory(1);
        
        console.log("DOWN ARROW - After navigation: messageHistoryIndex =", messageHistoryIndex);
        event.preventDefault();
    }
}

// Navigate through message history
function navigateMessageHistory(direction) {
    console.log(`========== HISTORY NAVIGATION (${direction}) ==========`);
    
    // For up arrow, use -1 to go back in history (higher indices)
    // For down arrow, use +1 to go forward in history (lower indices)
    
    // If persistence isn't ready, we can't load history
    if (!window.state || !window.state.sessionId || !window.chatPersistence) {
        console.log('Chat persistence not available');
        return;
    }

    // ------------------------
    // STEP 1: Load history data if needed
    // ------------------------
    
    // Initialize hard-coded history array for debugging
    if (messageHistory.length === 0) {
        messageHistory = [
            "Test message 1 (oldest)",
            "Test message 2 (middle)",
            "Test message 3 (newest)"
        ];
        console.log("DEBUG: Using hard-coded test messages:", messageHistory);
    }
    
    /* Disabled for debugging
    // If this is the first navigation, load history from persistence
    if (messageHistory.length === 0) {
        console.log('Loading message history from persistence');
        
        try {
            // Get all saved messages
            const allMessages = window.chatPersistence.getMessages(window.state.sessionId);
            console.log(`Found ${allMessages.length} total messages in persistence`);
            
            // Create temp array for history
            let tempHistory = [];
            
            // Process user messages
            for (const msg of allMessages) {
                if (msg.role === 'user' && msg.content && msg.content.trim().length > 0) {
                    tempHistory.push(msg.content);
                }
            }
            
            // Reverse for newest first
            tempHistory.reverse();
            
            // Assign to the history array
            messageHistory = tempHistory;
            
            console.log(`Prepared ${messageHistory.length} messages for history navigation`);
            
            // Debug log the history contents
            if (messageHistory.length > 0) {
                messageHistory.slice(0, Math.min(5, messageHistory.length)).forEach((msg, i) => {
                    console.log(`History[${i}]: ${msg.substring(0, 30)}${msg.length > 30 ? '...' : ''}`);
                });
            }
        } catch (error) {
            console.error('Error loading message history:', error);
            messageHistory = []; // Reset to empty array on error
        }
    }
    */
    
    // ------------------------
    // STEP 2: Handle case with no history 
    // ------------------------
    if (messageHistory.length === 0) {
        console.log('No message history available');
        return;
    }

    // ------------------------
    // STEP 3: Store current input if needed
    // ------------------------
    
    // Save current input on first navigation up
    if (direction < 0 && messageHistoryIndex === -1) {
        currentInputValue = chatInput.value || '';
        console.log(`Saved current input: "${currentInputValue}"`);
    }
    
    // ------------------------
    // STEP 4: Calculate new index based on direction
    // ------------------------
    
    // Calculate new index with bounds checking
    let newIndex;
    
    if (direction < 0) {
        // UP arrow pressed - go back in history (increase index)
        newIndex = (messageHistoryIndex === -1) ? 0 : messageHistoryIndex + 1;
        console.log(`UP arrow: index ${messageHistoryIndex} -> ${newIndex}`);
    } else {
        // DOWN arrow pressed - go forward in history (decrease index)
        newIndex = messageHistoryIndex - 1;
        console.log(`DOWN arrow: index ${messageHistoryIndex} -> ${newIndex}`);
    }
    
    // Apply bounds checking
    if (newIndex >= messageHistory.length) {
        // Can't go further back than oldest message
        newIndex = messageHistory.length - 1;
        console.log(`Limited to oldest message: index = ${newIndex}`);
    }
    
    if (newIndex < -1) {
        // Can't go further forward than current input
        newIndex = -1;
        console.log(`Limited to current input: index = ${newIndex}`);
    }
    
    console.log(`Final index: ${newIndex} (valid range: -1 to ${messageHistory.length - 1})`);
    
    // ------------------------
    // STEP 5: Update the input field based on index
    // ------------------------
    
    if (newIndex === -1) {
        // Show current input
        console.log(`Using current input: "${currentInputValue}"`);
        
        try {
            const valueBefore = chatInput.value;
            chatInput.value = currentInputValue;
            chatInput.classList.remove('history-mode');  
            console.log(`Input value changed from "${valueBefore}" to "${chatInput.value}"`);
        } catch (e) {
            console.error("Error setting input value:", e);
        }
    } else {
        // Show history item
        const historyItem = messageHistory[newIndex];
        console.log(`Using history[${newIndex}]: "${historyItem.substring(0, 30)}${historyItem.length > 30 ? '...' : ''}"`);
        
        try {
            const valueBefore = chatInput.value;
            chatInput.value = historyItem;
            chatInput.classList.add('history-mode');
            console.log(`Input value changed from "${valueBefore}" to "${chatInput.value}"`);
        } catch (e) {
            console.error("Error setting input value:", e);
        }
    }
    
    // Update the index after successful change
    messageHistoryIndex = newIndex;
    
    // ------------------------
    // STEP 6: Force UI update with both approaches
    // ------------------------
    
    // Update cursor position immediately
    chatInput.selectionStart = chatInput.selectionEnd = chatInput.value.length;
    
    // Queue additional UI updates for next frame
    requestAnimationFrame(() => {
        try {
            // Ensure cursor is at the end again (even more reliably)
            chatInput.setSelectionRange(chatInput.value.length, chatInput.value.length);
            
            // Adjust input field height
            chatInput.style.height = 'auto';
            const newHeight = Math.min(Math.max(chatInput.scrollHeight, 30), 120);
            chatInput.style.height = `${newHeight}px`;
            
            // Update memory indicator
            updateMemoryIndicator();
            
            // Force redraw of input field
            chatInput.style.borderColor = chatInput.style.borderColor;
        } catch (e) {
            console.error("Error in UI updates:", e);
        }
    });
    
    // Force focus on input
    try {
        chatInput.focus();
    } catch (e) {
        console.error("Error focusing input:", e);
    }
    
    console.log(`========== END HISTORY NAVIGATION (${direction}) ==========`);
}

// Send message via WebSocket
export function sendMessage() {
    const message = chatInput.value.trim();

    if (!message) return;

    // Handle # prefix for memory storage
    if (message.startsWith('# ')) {
        // Extract the memory content (remove the # prefix)
        const memoryContent = message.substring(2).trim();

        if (memoryContent) {
            // Store in memory via API
            storeInMemory(memoryContent);

            // Clear input and update UI
            chatInput.value = '';
            resizeTextarea();

            // Add confirmation message
            addMessage('system', `📝 Saved to memory: "${memoryContent}"`);
            return;
        }
    }

    // Save this message to the current agent's context
    if (window.state && window.state.agentContexts && window.state.currentAgentName) {
        const agentContext = window.state.agentContexts[window.state.currentAgentName];
        if (agentContext) {
            agentContext.lastSentMessage = message;
            agentContext.pendingResponse = true;
            console.log(`Saved message to ${window.state.currentAgentName} context:`, message);
        }
    }
    
    // Add to message history (internal history list for navigation)
    // Only add to messageHistory if the message is unique or messageHistory is empty
    if (message && (messageHistory.length === 0 || messageHistory[0] !== message)) {
        messageHistory.unshift(message);
        // Keep history to a reasonable size
        if (messageHistory.length > 50) {
            messageHistory = messageHistory.slice(0, 50);
        }
    }
    
    // Reset history navigation index and remove history mode class
    messageHistoryIndex = -1;
    chatInput.classList.remove('history-mode');
    
    // Special handler for agent pls commands - force agent switch without forwarding previous prompt
    const agentPlsRegex = /^(\w+)\s+pls$/i;
    const agentPlsMatch = message.match(agentPlsRegex);

    if (agentPlsMatch) {
        const targetAgent = agentPlsMatch[1].toUpperCase();
        console.log(`AGENT REQUEST DETECTED - Forcing switch to ${targetAgent}`);

        // Check if this is a valid agent
        const validAgents = ['SCOUT', 'BETO', 'AXEL', 'SEARCH', 'CODE'];
        if (validAgents.includes(targetAgent) || targetAgent.endsWith('_AGENT')) {
            // Use the context switching function if available
            if (window.switchAgentContext && typeof window.switchAgentContext === 'function') {
                window.switchAgentContext(targetAgent);
            } else {
                // Direct update if context switching not available
                window.state.currentAgentName = targetAgent;
            }

            // Update CSS and status
            document.documentElement.style.setProperty('--agent-name', `"${window.state.currentAgentName}"`);

            // Direct update of status bar element to ensure it updates
            const agentStatus = document.getElementById('agent-status');
            if (agentStatus) {
                agentStatus.textContent = `AGENT: ${window.state.currentAgentName}`;
                console.log("Directly updated agent status element text: " + agentStatus.textContent);

                // Visual feedback for the change
                agentStatus.style.color = 'var(--term-blue)';
                setTimeout(() => {
                    agentStatus.style.color = '';
                }, 500);
            } else {
                console.error("Cannot find agent-status element in DOM");
            }

            // Update other UI elements
            window.statusUtils.updateClock();

            // First add the user message to the chat log
            addMessage('user', message);

            // Then add the system message about the agent switch
            addMessage('system', `Agent switched to: ${window.state.currentAgentName}`);

            // Force a status update to update all UI elements consistently
            window.statusUtils.setStatus('ready');

            // Clear any pending WebSocket messages to prevent forwarding
            if (window.socket && window.socket.manager && window.socket.manager.pendingMessages) {
                window.socket.manager.pendingMessages = [];
            }

            // Send introduction request with explicit agent targeting
            // This prevents any previous context from being included
            if (window.socket && window.socket.socketConnected) {
                window.socket.send(JSON.stringify({
                    message: `AGENT:${targetAgent}:Introduce yourself and describe your capabilities.`
                }));

                // Set status to indicate processing
                window.statusUtils.setStatus('thinking');
            }

            // Clear the input field and resize
            chatInput.value = '';
            resizeTextarea();

            // Return early to prevent normal message handling
            return;
        }
    }
    
    // Check if this is a slash command
    if (message.startsWith('/')) {
        window.commandUtils.executeCommand(message);
        chatInput.value = '';
        resizeTextarea();
        return;
    }
    
    // Convert emoji shortcodes to unicode emojis for display, but send original text to server
    const displayMessage = window.emojiUtils.convertEmoji(message);
    
    // Add user message to UI
    addMessage('user', displayMessage);
    
    // Clear input immediately after adding the message to UI
    chatInput.value = '';
    resizeTextarea();
    
    // Ensure WebSocket is connected or retry connecting if it's not
    if (window.socket) {
        if (window.socket.socketConnected) {
            // Send via WebSocket directly
            console.log("Sending message via connected WebSocket");

            // Ensure we have the most up-to-date agent name in case it was changed via transfer
            const currentAgentName = window.state.currentAgentName;

            // Only use AGENT: prefix when explicitly targeting a non-default agent.
            // For the root agent (BETO), send the raw message so it goes through
            // the normal runner path (avoids extra API calls from agent_transfer).
            const isRootAgent = !currentAgentName || currentAgentName.toUpperCase() === 'BETO';
            const outMessage = isRootAgent ? message : `AGENT:${currentAgentName}:${message}`;
            console.log(`Sending message to agent: ${currentAgentName} (root=${isRootAgent})`);

            window.socket.send(JSON.stringify({
                message: outMessage
            }));

            // Set status to indicate processing
            window.statusUtils.setStatus('thinking');
        } else {
            // Socket exists but not connected, retry connection and queue message
            console.log("WebSocket not connected, forcing reconnection and queueing message");

            // Force WebSocket to reconnect
            if (window.socket.manager && typeof window.socket.manager.connect === 'function') {
                window.socket.manager.connect();

                // Queue the message to be sent when connection is established
                window.socket.manager.pendingMessages.push(JSON.stringify({
                    message: message
                }));

                // Set status to indicate processing
                window.statusUtils.setStatus('connecting');

                // Start a timer to monitor WebSocket connection status
                const connectionCheckInterval = setInterval(() => {
                    if (window.socket && window.socket.socketConnected) {
                        console.log("WebSocket connection established, message should be sent from queue");
                        clearInterval(connectionCheckInterval);

                        // Update status to thinking once connected
                        window.statusUtils.setStatus('thinking');
                    }
                }, 500);

                // Timeout after 10 seconds and use REST fallback
                setTimeout(() => {
                    clearInterval(connectionCheckInterval);
                    if (!(window.socket && window.socket.socketConnected)) {
                        console.log("WebSocket connection timed out, falling back to REST API");
                        // Remove the queued message from WebSocket pending queue
                        // to prevent double-send when WebSocket later reconnects
                        if (window.socket && window.socket.manager && window.socket.manager.pendingMessages) {
                            const queuedMsg = JSON.stringify({ message: message });
                            window.socket.manager.pendingMessages = window.socket.manager.pendingMessages.filter(
                                m => m !== queuedMsg
                            );
                        }
                        sendMessageREST(message, displayMessage);
                    }
                }, 10000);
            } else {
                // Socket manager not available, fall back to REST
                console.log("WebSocket manager not available, falling back to REST API");
                sendMessageREST(message, displayMessage);
            }
        }
    } else {
        // No socket at all, create new socket and fall back to REST for this message
        console.log("No WebSocket instance found, falling back to REST API and creating new socket");

        // Initialize socket for future messages
        if (window.socketClient && typeof window.socketClient.initSocket === 'function') {
            window.socketClient.initSocket(window.state.sessionId).then(socket => {
                window.socket = socket;
                console.log("Created new WebSocket connection for future messages");
            }).catch(error => {
                console.error("Failed to create WebSocket connection:", error);
            });
        }

        // Use REST API for current message
        sendMessageREST(message, displayMessage);
    }
    
    // Ensure the agent name is visible in status bar
    const agentStatus = document.getElementById('agent-status');
    if (agentStatus) {
        agentStatus.textContent = `AGENT: ${window.state.currentAgentName.toUpperCase()}`;
    }
    
    scrollToBottom();
}

// Store text in memory using the memory API
function storeInMemory(text) {
    console.log(`Storing in memory: ${text}`);
    
    // Set status to indicate processing
    window.statusUtils.setStatus('processing');
    
    // Make API call to store memory
    fetch('/api/memory/store', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            text: text,
            memory_type: 'important_fact',
            session_id: window.state.sessionId
        })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        console.log('Memory storage response:', data);
        window.statusUtils.setStatus('ready');
    })
    .catch(error => {
        console.error('Error storing memory:', error);
        window.statusUtils.setStatus('error');
        
        // Try to extract more detailed error message if available
        let errorMsg = 'Error: Could not store memory. Please try again.';
        try {
            if (error.response) {
                return error.response.json().then(data => {
                    if (data && data.detail) {
                        errorMsg = `Error: ${data.detail}`;
                    }
                    addMessage('system', errorMsg);
                });
            }
        } catch (e) {
            console.log('Could not parse error details:', e);
        }
        
        addMessage('system', errorMsg);
    });
}

// Reset the conversation
async function resetConversation() {
    try {
        const response = await fetch(`/api/sessions/${window.state.sessionId}/reset`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        
        // Clear all messages except the first one (welcome message)
        const messages = chatMessages.querySelectorAll('.message');
        
        for (let i = 1; i < messages.length; i++) {
            messages[i].remove();
        }
        
        // Also clear events
        if (window.events && Array.isArray(window.events)) {
            console.log('Clearing event history');
            window.events = [];
            
            // If events are currently displayed, refresh the view
            const eventsContainer = document.getElementById('events-container');
            if (eventsContainer) {
                console.log('Refreshing events view');
                // If renderEvents is available, call it
                if (typeof window.renderEvents === 'function') {
                    window.renderEvents();
                }
                // Otherwise just clear the container
                else {
                    eventsContainer.innerHTML = '<div class="event-empty-state">No events recorded yet.</div>';
                }
            }
        }
        
        // Also clear persisted chat history
        if (window.chatPersistence && window.state.sessionId) {
            console.log('Clearing persisted chat history for session:', window.state.sessionId);
            window.chatPersistence.clearChat(window.state.sessionId);
        }
        
        addMessage('system', 'Session cleared. New terminal started.');
    } catch (error) {
        console.error('Error resetting conversation:', error);
        addMessage('system', 'Error: Could not reset conversation.');
    }
}

// Send message via REST API (fallback)
async function sendMessageREST(message, displayMessage) {
    window.statusUtils.setStatus('thinking');
    
    // Note: User message is already added to UI by sendMessage function
    // and input is already cleared before this function is called
    
    try {
        // Ensure we have the most up-to-date agent name in case it was changed via transfer
        const currentAgentName = window.state.currentAgentName;

        // Only use AGENT: prefix for non-default agents (same logic as WebSocket path)
        const isRootAgent = !currentAgentName || currentAgentName.toUpperCase() === 'BETO';
        const outMessage = isRootAgent ? message : `AGENT:${currentAgentName}:${message}`;
        console.log(`Sending REST message to agent: ${currentAgentName} (root=${isRootAgent})`);

        const formData = new FormData();
        formData.append('message', outMessage);
        formData.append('session_id', window.state.sessionId);

        const response = await fetch('/api/chat', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Process events from response (same approach as WebSocket)
        if (data.events && Array.isArray(data.events)) {
            // Process model_response events
            const modelResponses = data.events.filter(
                event => (event.type === 'model_response' || event.category === 'model_response') && event.text
            );
            
            // Show the last model response in the UI
            if (modelResponses.length > 0) {
                const lastResponse = modelResponses[modelResponses.length - 1];
                const agentName = lastResponse.agent_name || 
                               (lastResponse.details && lastResponse.details.agent_name) || 
                               window.state.currentAgentName;
                
                // Check if this is a recovered response from a malformed function call
                const isRecovered = lastResponse.details && lastResponse.details.recovered_from === 'malformed_function_call';
                
                if (isRecovered) {
                    console.log("Displaying recovered response from malformed function call in REST response");
                }
                
                addMessage('assistant', lastResponse.text, agentName);
            } else {
                // Fallback to direct response if no model_response events
                addMessage('assistant', data.response);
            }
            
            // If events are globally accessible, update them
            if (typeof window.events !== 'undefined') {
                // Merge with existing events
                window.events = [...(window.events || []), ...data.events];
                
                // If event rendering function exists, call it
                if (typeof window.renderEvents === 'function') {
                    window.renderEvents();
                }
            }
        } else {
            // Fallback to direct response if no events
            addMessage('assistant', data.response);
        }
        
        window.statusUtils.setStatus('ready');
    } catch (error) {
        console.error('Error sending message:', error);
        window.statusUtils.setStatus('error');
        addMessage('system', 'Error: Could not send message. Please try again later.');
    }
    
    scrollToBottom();
}

// Resize textarea based on content
export function resizeTextarea() {
    if (!chatInput) return;
    
    // Reset height to auto to correctly calculate new height
    chatInput.style.height = 'auto';
    
    // Limit to max-height defined in CSS
    let newHeight = Math.min(chatInput.scrollHeight, 120);
    
    // Set minimum height
    newHeight = Math.max(newHeight, 30);
    
    chatInput.style.height = newHeight + 'px';
    
    // Check for # prefix to show memory indicator
    updateMemoryIndicator();
}

// Update visual indicator for memory mode (# prefix)
function updateMemoryIndicator() {
    if (!chatInput) return;
    
    const text = chatInput.value;
    const isMemoryCommand = /^#\s/.test(text);
    
    if (isMemoryCommand) {
        chatInput.classList.add('memory-mode');
        
        // Add or update tooltip if not present
        let tooltip = document.getElementById('memory-tooltip');
        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.id = 'memory-tooltip';
            tooltip.className = 'memory-tooltip';
            tooltip.textContent = 'This will be saved to memory';
            
            // Insert tooltip after input
            chatInput.parentNode.insertBefore(tooltip, chatInput.nextSibling);
        }
    } else {
        chatInput.classList.remove('memory-mode');
        
        // Remove tooltip if present
        const tooltip = document.getElementById('memory-tooltip');
        if (tooltip) {
            tooltip.remove();
        }
    }
}

// Scroll chat to bottom
export function scrollToBottom() {
    if (!chatMessages) return;
    
    chatMessages.scrollTop = chatMessages.scrollHeight;
}