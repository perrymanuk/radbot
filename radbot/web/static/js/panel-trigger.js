/**
 * Panel Trigger System for RadBot UI
 *
 * This script is the SINGLE source of button click -> command event dispatch.
 * tiling.js listens for command:sessions/tasks/events and calls togglePanel().
 *
 * Do NOT add duplicate togglePanel calls or duplicate click listeners elsewhere.
 */

// Track which buttons already have handlers to prevent stacking
const _handledButtons = new Set();

// Wait for DOM content loaded to initialize
document.addEventListener('DOMContentLoaded', function() {
    console.log('Panel trigger system initialized');
    setupDirectHandlers();
});

// Set up direct handlers for buttons (idempotent - safe to call multiple times)
function setupDirectHandlers() {
    setupButton('toggle-sessions-button', 'command:sessions');
    setupButton('toggle-tasks-button', 'command:tasks');
    setupButton('toggle-events-button', 'command:events');
}

function setupButton(buttonId, commandEvent) {
    const button = document.getElementById(buttonId);
    if (!button) return;

    // Only add listener once per button element
    if (_handledButtons.has(button)) return;
    _handledButtons.add(button);

    button.addEventListener('click', function(e) {
        console.log(`${buttonId} clicked, dispatching ${commandEvent}`);
        e.preventDefault();
        e.stopPropagation();
        document.dispatchEvent(new CustomEvent(commandEvent));
    });
}

// Re-attach handlers when layout changes (tiling recreates DOM elements)
document.addEventListener('tiling:ready', function() {
    // Layout changes create new DOM elements, so clear tracked set
    _handledButtons.clear();
    setTimeout(setupDirectHandlers, 200);
});

document.addEventListener('layout:changed', function() {
    _handledButtons.clear();
    setTimeout(setupDirectHandlers, 200);
});
