/**
 * RadBot Web Interface Client - Data Services Module
 * 
 * This module handles fetching and rendering data from API endpoints
 */

import * as selectsUtils from './selects.js';
import { state, tasks, projects, events } from './app_core.js';

// Fetch tasks from API
export async function fetchTasks() {
    console.log("Fetching tasks data...");
    try {
        // Try to fetch from the real API
        try {
            const baseUrl = `${window.location.protocol}//${window.location.host}`;
            const apiUrl = `${baseUrl}/api/tasks`;
            console.log(`Attempting to fetch real tasks data from ${apiUrl}`);

            const response = await fetch(apiUrl);

            if (response.ok) {
                const tasksData = await response.json();
                console.log("Successfully fetched real task data:", tasksData);

                // The API returns tasks as a direct array
                window.tasks = tasksData || [];

                // We need to fetch projects separately
                try {
                    const projectsResponse = await fetch(`${baseUrl}/api/projects`);
                    if (projectsResponse.ok) {
                        window.projects = await projectsResponse.json();
                        console.log("Successfully fetched real projects data:", window.projects);
                    } else {
                        console.warn("Failed to fetch projects, using default project");
                        window.projects = [{project_id: "unknown", name: "Default"}];
                    }
                } catch (projectError) {
                    console.warn("Error fetching projects:", projectError);
                    window.projects = [{project_id: "unknown", name: "Default"}];
                }

                // Update selects module with projects
                selectsUtils.setProjects(window.projects);

                renderTasks();
                return;
            } else {
                console.warn(`API returned error status: ${response.status}`);
            }
        } catch (apiError) {
            console.warn("Failed to connect to API:", apiError);
        }

        // API failed - show empty state
        console.log("Task API unavailable, showing empty state");
        window.tasks = [];
        window.projects = [];

        // Update selects module with projects
        selectsUtils.setProjects(window.projects);

        renderTasks();
    } catch (error) {
        console.error('Unexpected error in fetchTasks:', error);
        
        // Fall back to simple mock data if everything else fails
        window.tasks = [{ task_id: "error1", title: "Error fetching tasks", status: "backlog", priority: "high", project_id: "error" }];
        window.projects = [{ project_id: "error", name: "Error" }];
        
        selectsUtils.setProjects(window.projects);
        renderTasks();
    }
}

// Render tasks in UI
export function renderTasks() {
    const tasksContainer = document.getElementById('tasks-container');
    if (!tasksContainer) return;
    
    // Clear existing tasks
    tasksContainer.innerHTML = '';
    
    // Get the selection state
    const { selectedProject, selectedStatus } = selectsUtils.getSelectionState();
    
    // Filter tasks
    const filteredTasks = window.tasks.filter(task => {
        // Handle project filtering with both project_id and project_name
        let projectMatch = selectedProject === 'all';
        if (!projectMatch) {
            if (task.project_name) {
                // Try to match by project name if it exists on the task
                const project = window.projects.find(p => p.name === task.project_name);
                if (project) {
                    projectMatch = project.project_id === selectedProject;
                }
            }
            // If we still don't have a match, try the project_id directly
            if (!projectMatch) {
                projectMatch = task.project_id === selectedProject;
            }
        }
        
        const statusMatch = selectedStatus === 'all' || selectedStatus === task.status;
        return projectMatch && statusMatch;
    });
    
    // Sort tasks - priority first, then by status
    filteredTasks.sort((a, b) => {
        // First sort by priority
        const priorityOrder = { high: 1, medium: 2, low: 3 };
        const priorityA = priorityOrder[a.priority] || 4;
        const priorityB = priorityOrder[b.priority] || 4;
        
        if (priorityA !== priorityB) {
            return priorityA - priorityB;
        }
        
        // Then sort by status
        const statusOrder = { inprogress: 1, backlog: 2, done: 3 };
        const statusA = statusOrder[a.status] || 4;
        const statusB = statusOrder[b.status] || 4;
        
        return statusA - statusB;
    });
    
    // "+ New Task" button
    const newBtn = document.createElement('button');
    newBtn.className = 'task-new-btn';
    newBtn.textContent = '+ New Task';
    newBtn.addEventListener('click', () => renderTaskCreateForm());
    tasksContainer.appendChild(newBtn);

    // Render each task
    filteredTasks.forEach(task => {
        const taskItem = document.createElement('div');
        taskItem.className = `task-item ${task.status}`;
        taskItem.dataset.id = task.task_id;
        
        const taskStatus = document.createElement('div');
        taskStatus.className = `task-status-indicator ${task.status}`;
        
        const taskTitle = document.createElement('div');
        taskTitle.className = 'task-title';
        // Prefer title if set, fall back to description for older tasks
        taskTitle.textContent = task.title || task.description || "Untitled Task";
        
        const taskProject = document.createElement('div');
        taskProject.className = 'task-project';
        
        // First try to use project_name if it exists directly on the task
        if (task.project_name) {
            taskProject.textContent = task.project_name;
        } else {
            // Fall back to looking up by project_id
            const project = window.projects.find(p => p.project_id === task.project_id);
            taskProject.textContent = project ? project.name : (task.project_id || "Unknown Project");
        }
        
        taskItem.appendChild(taskStatus);
        taskItem.appendChild(taskTitle);
        taskItem.appendChild(taskProject);
        
        // Add click handler to open edit form
        taskItem.addEventListener('click', () => {
            renderTaskEditForm(task);
        });
        
        tasksContainer.appendChild(taskItem);
    });
    
    // Show a message if no tasks found
    if (filteredTasks.length === 0) {
        const noTasksMsg = document.createElement('div');
        noTasksMsg.className = 'no-items-message';
        noTasksMsg.textContent = 'No tasks match the current filters';
        tasksContainer.appendChild(noTasksMsg);
    }
}

// Update a task via the API
export async function updateTask(taskId, updates) {
    const baseUrl = `${window.location.protocol}//${window.location.host}`;
    const response = await fetch(`${baseUrl}/api/tasks/${taskId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates)
    });
    const result = await response.json();
    if (!response.ok) {
        throw new Error(result.detail || 'Failed to update task');
    }
    // Refresh the task list
    await fetchTasks();
    return result;
}

// Delete a task via the API
export async function deleteTask(taskId) {
    const baseUrl = `${window.location.protocol}//${window.location.host}`;
    const response = await fetch(`${baseUrl}/api/tasks/${taskId}`, {
        method: 'DELETE'
    });
    const result = await response.json();
    if (!response.ok) {
        throw new Error(result.detail || 'Failed to delete task');
    }
    await fetchTasks();
    return result;
}

// Create a new task via the API
export async function createTask(data) {
    const baseUrl = `${window.location.protocol}//${window.location.host}`;
    const response = await fetch(`${baseUrl}/api/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    const result = await response.json();
    if (!response.ok) {
        throw new Error(result.detail || 'Failed to create task');
    }
    await fetchTasks();
    return result;
}

// Render a creation form for a new task
export function renderTaskCreateForm() {
    const tasksContainer = document.getElementById('tasks-container');
    if (!tasksContainer) return;

    tasksContainer.innerHTML = '';

    const form = document.createElement('div');
    form.className = 'task-edit-form';

    // Back button
    const back = document.createElement('button');
    back.className = 'task-edit-back';
    back.textContent = '\u2190 Back to tasks';
    back.addEventListener('click', () => renderTasks());
    form.appendChild(back);

    // Title field
    const titleField = document.createElement('div');
    titleField.className = 'task-edit-field';
    const titleLabel = document.createElement('label');
    titleLabel.className = 'task-edit-label';
    titleLabel.textContent = 'Title';
    const titleInput = document.createElement('input');
    titleInput.type = 'text';
    titleInput.className = 'task-edit-input';
    titleInput.placeholder = 'Short summary';
    titleField.appendChild(titleLabel);
    titleField.appendChild(titleInput);
    form.appendChild(titleField);

    // Description field
    const descField = document.createElement('div');
    descField.className = 'task-edit-field';
    const descLabel = document.createElement('label');
    descLabel.className = 'task-edit-label';
    descLabel.textContent = 'Description';
    const descInput = document.createElement('textarea');
    descInput.className = 'task-edit-textarea';
    descInput.rows = 4;
    descField.appendChild(descLabel);
    descField.appendChild(descInput);
    form.appendChild(descField);

    // Status field
    const statusField = document.createElement('div');
    statusField.className = 'task-edit-field';
    const statusLabel = document.createElement('label');
    statusLabel.className = 'task-edit-label';
    statusLabel.textContent = 'Status';
    const statusSelect = document.createElement('select');
    statusSelect.className = 'task-edit-select';
    ['backlog', 'inprogress', 'done'].forEach(s => {
        const opt = document.createElement('option');
        opt.value = s;
        opt.textContent = s === 'inprogress' ? 'In Progress' : s.charAt(0).toUpperCase() + s.slice(1);
        if (s === 'backlog') opt.selected = true;
        statusSelect.appendChild(opt);
    });
    statusField.appendChild(statusLabel);
    statusField.appendChild(statusSelect);
    form.appendChild(statusField);

    // Project field
    const projField = document.createElement('div');
    projField.className = 'task-edit-field';
    const projLabel = document.createElement('label');
    projLabel.className = 'task-edit-label';
    projLabel.textContent = 'Project';
    const projSelect = document.createElement('select');
    projSelect.className = 'task-edit-select';
    (window.projects || []).forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.project_id;
        opt.textContent = p.name;
        projSelect.appendChild(opt);
    });
    projField.appendChild(projLabel);
    projField.appendChild(projSelect);
    form.appendChild(projField);

    // Action buttons
    const actions = document.createElement('div');
    actions.className = 'task-edit-actions';

    const saveBtn = document.createElement('button');
    saveBtn.className = 'task-edit-btn save';
    saveBtn.textContent = 'Save';
    saveBtn.addEventListener('click', async () => {
        const title = titleInput.value.trim();
        const description = descInput.value.trim();
        if (!title && !description) {
            alert('Please enter a title or description.');
            return;
        }
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';
        try {
            await createTask({
                title: title || undefined,
                description: description || undefined,
                status: statusSelect.value,
                project_id: projSelect.value
            });
        } catch (err) {
            console.error('Failed to create task:', err);
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save';
            alert('Failed to create task: ' + err.message);
        }
    });

    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'task-edit-btn cancel';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.addEventListener('click', () => renderTasks());

    actions.appendChild(saveBtn);
    actions.appendChild(cancelBtn);
    form.appendChild(actions);

    tasksContainer.appendChild(form);
}

// Render an edit form for a single task
export function renderTaskEditForm(task) {
    const tasksContainer = document.getElementById('tasks-container');
    if (!tasksContainer) return;

    tasksContainer.innerHTML = '';

    const form = document.createElement('div');
    form.className = 'task-edit-form';

    // Back button
    const back = document.createElement('button');
    back.className = 'task-edit-back';
    back.textContent = '\u2190 Back to tasks';
    back.addEventListener('click', () => renderTasks());
    form.appendChild(back);

    // Title field
    const titleField = document.createElement('div');
    titleField.className = 'task-edit-field';
    const titleLabel = document.createElement('label');
    titleLabel.className = 'task-edit-label';
    titleLabel.textContent = 'Title';
    const titleInput = document.createElement('input');
    titleInput.type = 'text';
    titleInput.className = 'task-edit-input';
    titleInput.placeholder = 'Short summary (optional)';
    titleInput.value = task.title || '';
    titleField.appendChild(titleLabel);
    titleField.appendChild(titleInput);
    form.appendChild(titleField);

    // Description field
    const descField = document.createElement('div');
    descField.className = 'task-edit-field';
    const descLabel = document.createElement('label');
    descLabel.className = 'task-edit-label';
    descLabel.textContent = 'Description';
    const descInput = document.createElement('textarea');
    descInput.className = 'task-edit-textarea';
    descInput.rows = 4;
    descInput.value = task.description || '';
    descField.appendChild(descLabel);
    descField.appendChild(descInput);
    form.appendChild(descField);

    // Status field
    const statusField = document.createElement('div');
    statusField.className = 'task-edit-field';
    const statusLabel = document.createElement('label');
    statusLabel.className = 'task-edit-label';
    statusLabel.textContent = 'Status';
    const statusSelect = document.createElement('select');
    statusSelect.className = 'task-edit-select';
    ['backlog', 'inprogress', 'done'].forEach(s => {
        const opt = document.createElement('option');
        opt.value = s;
        opt.textContent = s === 'inprogress' ? 'In Progress' : s.charAt(0).toUpperCase() + s.slice(1);
        if (task.status === s) opt.selected = true;
        statusSelect.appendChild(opt);
    });
    statusField.appendChild(statusLabel);
    statusField.appendChild(statusSelect);
    form.appendChild(statusField);

    // Project field
    const projField = document.createElement('div');
    projField.className = 'task-edit-field';
    const projLabel = document.createElement('label');
    projLabel.className = 'task-edit-label';
    projLabel.textContent = 'Project';
    const projSelect = document.createElement('select');
    projSelect.className = 'task-edit-select';
    (window.projects || []).forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.project_id;
        opt.textContent = p.name;
        if (task.project_id === p.project_id || task.project_name === p.name) opt.selected = true;
        projSelect.appendChild(opt);
    });
    projField.appendChild(projLabel);
    projField.appendChild(projSelect);
    form.appendChild(projField);

    // Action buttons
    const actions = document.createElement('div');
    actions.className = 'task-edit-actions';

    const saveBtn = document.createElement('button');
    saveBtn.className = 'task-edit-btn save';
    saveBtn.textContent = 'Save';
    saveBtn.addEventListener('click', async () => {
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';
        try {
            const updates = {};
            const newTitle = titleInput.value.trim();
            if (newTitle !== (task.title || '')) updates.title = newTitle;
            const newDesc = descInput.value.trim();
            if (newDesc !== (task.description || '')) updates.description = newDesc;
            if (statusSelect.value !== task.status) updates.status = statusSelect.value;
            if (projSelect.value !== task.project_id) updates.project_id = projSelect.value;
            if (Object.keys(updates).length > 0) {
                await updateTask(task.task_id, updates);
            } else {
                renderTasks();
            }
        } catch (err) {
            console.error('Failed to update task:', err);
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save';
            alert('Failed to update task: ' + err.message);
        }
    });

    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'task-edit-btn cancel';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.addEventListener('click', () => renderTasks());

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'task-edit-btn delete';
    deleteBtn.textContent = 'Delete';
    deleteBtn.addEventListener('click', () => {
        // Show inline confirmation
        deleteBtn.style.display = 'none';
        const confirmWrap = document.createElement('span');
        confirmWrap.className = 'task-edit-confirm';
        const confirmLabel = document.createElement('span');
        confirmLabel.textContent = 'Delete this task? ';
        confirmLabel.className = 'task-edit-confirm-label';
        const yesBtn = document.createElement('button');
        yesBtn.className = 'task-edit-btn delete';
        yesBtn.textContent = 'Yes';
        yesBtn.addEventListener('click', async () => {
            yesBtn.disabled = true;
            yesBtn.textContent = 'Deleting...';
            try {
                await deleteTask(task.task_id);
            } catch (err) {
                console.error('Failed to delete task:', err);
                alert('Failed to delete task: ' + err.message);
                yesBtn.disabled = false;
                yesBtn.textContent = 'Yes';
                deleteBtn.style.display = '';
                confirmWrap.remove();
            }
        });
        const noBtn = document.createElement('button');
        noBtn.className = 'task-edit-btn cancel';
        noBtn.textContent = 'No';
        noBtn.addEventListener('click', () => {
            deleteBtn.style.display = '';
            confirmWrap.remove();
        });
        confirmWrap.appendChild(confirmLabel);
        confirmWrap.appendChild(yesBtn);
        confirmWrap.appendChild(noBtn);
        actions.appendChild(confirmWrap);
    });

    actions.appendChild(saveBtn);
    actions.appendChild(cancelBtn);
    actions.appendChild(deleteBtn);
    form.appendChild(actions);

    tasksContainer.appendChild(form);
}

// Fetch events from API
export async function fetchEvents() {
    console.log("Fetching events data...");
    try {
        // Determine the API base URL - use current origin
        const baseUrl = `${window.location.protocol}//${window.location.host}`;
        
        // Get the current session ID - reuse the one from socket connection if available
        const sessionId = state.sessionId || localStorage.getItem('radbot_session_id') || generateUUID();
        
        // Based on custom_web_ui.md - we need to use the session API endpoint
        const apiUrl = `${baseUrl}/api/events/${sessionId}`;
        console.log(`Attempting to fetch events data from ${apiUrl}`);
        
        try {
            // Make the API request
            const response = await fetch(apiUrl, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                // Parse the response
                const data = await response.json();
                console.log("Successfully fetched events data:", data);
                
                if (data && Array.isArray(data)) {
                    // Direct array of events
                    window.events = data;
                } else if (data && data.events && Array.isArray(data.events)) {
                    // Object with events array property
                    window.events = data.events;
                } else {
                    console.warn("Unexpected events data format:", data);
                    window.events = [];
                }
                
                // Render the events in the UI
                window.renderEvents();
                return;
            } else {
                // Handle error response
                console.warn(`API returned error status: ${response.status}`);
                
                // Try to get more details from error response
                try {
                    const errorData = await response.json();
                    console.warn("Error details:", errorData);
                } catch (parseError) {
                    console.warn("Could not parse error response");
                }
                
                // API returned an error - show empty state
                if (response.status === 404) {
                    console.log("No events found for this session or endpoint not found");
                } else {
                    console.warn(`Events API error: ${response.status} ${response.statusText}`);
                }
                window.events = [];
                
                window.renderEvents();
            }
        } catch (apiError) {
            // Handle API connection errors (CORS, connection refused, etc.)
            console.error("API error fetching events:", apiError);
            
            window.events = [];
            
            window.renderEvents();
        }
    } catch (error) {
        // Handle any unexpected errors
        console.error('Unexpected error in fetchEvents:', error);
        
        window.events = [{
            type: "other",
            timestamp: new Date().toISOString(),
            category: "error",
            summary: "Unexpected Error",
            details: {
                error_message: `An unexpected error occurred: ${error.message}`,
                error_type: error.name,
                error_stack: error.stack
            }
        }];
        
        window.renderEvents();
    }
}

// Helper function to generate UUID (moved from main file)
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}