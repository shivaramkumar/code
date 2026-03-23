const API_BASE = '/api';

// UI Elements
const uploadZone = document.getElementById('upload-zone');
const fileInput = document.getElementById('file-input');
const contextList = document.getElementById('context-list');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const messagesContainer = document.getElementById('messages-container');
const useContextToggle = document.getElementById('use-context-toggle');

// New Scope Selectors & Modal
const userProfileSelect = document.getElementById('user-profile-select');
const mcpToolSelect = document.getElementById('mcp-tool-select');
const currentScopeSpan = document.getElementById('current-scope');
const toolsModal = document.getElementById('tools-modal');
const registerToolForm = document.getElementById('register-tool-form');
const toolNameInput = document.getElementById('tool-name-input');
const toolDescInput = document.getElementById('tool-desc-input');
const toolUrlInput = document.getElementById('tool-url-input');
const toolFormFeedback = document.getElementById('tool-form-feedback');

function updateScopeLabel() {
    if(currentScopeSpan) currentScopeSpan.innerText = `${userProfileSelect.value} / ${mcpToolSelect.value}`;
}
if(userProfileSelect) userProfileSelect.addEventListener('change', updateScopeLabel);
if(mcpToolSelect) mcpToolSelect.addEventListener('change', updateScopeLabel);

// Helper to escape HTML to prevent XSS
function escapeHTML(str) {
    let div = document.createElement('div');
    div.innerText = str;
    return div.innerHTML;
}

// Upload Handling
uploadZone.addEventListener('click', () => fileInput.click());

uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.style.borderColor = 'var(--primary)';
});

uploadZone.addEventListener('dragleave', (e) => {
    e.preventDefault();
    uploadZone.style.borderColor = 'rgba(255, 255, 255, 0.2)';
});

uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.style.borderColor = 'rgba(255, 255, 255, 0.2)';
    if(e.dataTransfer.files.length) handleFileUpload(e.dataTransfer.files[0]);
});

fileInput.addEventListener('change', (e) => {
    if(e.target.files.length) handleFileUpload(e.target.files[0]);
});

async function handleFileUpload(file) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('user_id', userProfileSelect.value);
    formData.append('tool_id', mcpToolSelect.value);
    
    // UI Feedback
    uploadZone.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><p>Uploading and Chunking...</p>';
    
    try {
        const res = await fetch(`${API_BASE}/context/upload`, {
            method: 'POST',
            body: formData
        });
        if(res.ok) {
            loadContextDocs();
            uploadZone.innerHTML = '<i class="fa-solid fa-cloud-check text-gradient"></i><p>Upload Successful</p>';
            setTimeout(() => {
                uploadZone.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i><p>Drop files here or click</p>';
            }, 2000);
        }
    } catch (err) {
        console.error("Upload error", err);
        uploadZone.innerHTML = '<i class="fa-solid fa-triangle-exclamation" style="color:var(--danger)"></i><p>Upload Failed</p>';
    }
}

async function loadContextDocs() {
    try {
        const res = await fetch(`${API_BASE}/context/documents`);
        const docs = await res.json();
        contextList.innerHTML = docs.map(d => `
            <div class="doc-item">
                <i class="fa-solid fa-file-lines"></i>
                <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHTML(d.filename)}</span>
            </div>
        `).join('');
    } catch(e) {}
}

// Chat Handling
function addMessage(role, content, meta = null) {
    const isUser = role === 'user';
    const div = document.createElement('div');
    div.className = `message ${role}`;
    
    let metaHtml = '';
    if (meta && meta.source === 'semantic_cache') {
        metaHtml = `<div class="cache-badge"><i class="fa-solid fa-bolt"></i> Semantic Cache Hit</div>`;
    }
    
    div.innerHTML = `
        <div class="avatar"><i class="fa-solid ${isUser ? 'fa-user' : 'fa-robot'}"></i></div>
        <div class="message-content">
            ${metaHtml}
            ${escapeHTML(content).replace(/\\n/g, '<br>')}
        </div>
    `;
    messagesContainer.appendChild(div);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function showTyping() {
    const div = document.createElement('div');
    div.className = 'message assistant typing';
    div.id = 'typing-indicator';
    div.innerHTML = `
        <div class="avatar"><i class="fa-solid fa-robot"></i></div>
        <div class="message-content">
            <div class="typing-indicator">
                <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
            </div>
        </div>
    `;
    messagesContainer.appendChild(div);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function removeTyping() {
    const el = document.getElementById('typing-indicator');
    if(el) el.remove();
}

// Additional UI Elements
const appBrandName = document.getElementById('app-brand-name');
const pageTitle = document.getElementById('page-title');
const modelBadge = document.getElementById('model-badge');
const mcpServerLabel = document.getElementById('mcp-server-label');
const welcomeMessageText = document.getElementById('welcome-message-text');
const archExplorer = document.getElementById('arch-explorer');
const eventTimeline = document.getElementById('event-timeline');

// Configuration
let appConfig = {};

async function loadConfig() {
    try {
        const res = await fetch(`${API_BASE}/config`);
        appConfig = await res.json();
        
        // Apply Config to UI
        if(appConfig.app_name) {
            appBrandName.innerText = appConfig.app_name;
            pageTitle.innerText = appConfig.app_name;
            welcomeMessageText.innerText = `Hello! Welcome to ${appConfig.app_name}. Try sending a message or uploading a file to watch the backend components process your request in the Architecture Explorer.`;
        }
        if(appConfig.model_name) {
            modelBadge.innerText = `Model: ${appConfig.model_name}`;
        }
        if(appConfig.mcp_server_name) {
            mcpServerLabel.innerText = `${appConfig.mcp_server_name} Online`;
        }
    } catch(e) {
        console.error("Failed to load config.");
        modelBadge.innerText = "Model: Unknown";
    }
}

// Architecture Explorer Logic
function toggleArchitecture() {
    archExplorer.classList.toggle('hidden');
}

function clearTimeline() {
    eventTimeline.innerHTML = '';
}

function addArchitectureEvent(layer, action, desc) {
    const div = document.createElement('div');
    const layerClass = `layer-${layer.toLowerCase().replace(/\s+/g, '-')}`;
    div.className = `arch-event ${layerClass}`;
    
    div.innerHTML = `
        <div class="event-header">
            <span class="event-layer"><i class="fa-solid fa-code-branch"></i> ${escapeHTML(layer)}</span>
        </div>
        <div class="event-action">${escapeHTML(action)}</div>
        <div class="event-desc">${escapeHTML(desc)}</div>
    `;
    eventTimeline.appendChild(div);
    eventTimeline.scrollTop = eventTimeline.scrollHeight;
}

// Chat Handling Update
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if(!text) return;
    
    chatInput.value = '';
    addMessage('user', text);
    showTyping();
    clearTimeline(); // Clear previous arch logs
    
    try {
        const res = await fetch(`${API_BASE}/ai/chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                message: text,
                use_context: useContextToggle.checked,
                user_id: userProfileSelect.value,
                tool_id: mcpToolSelect.value
            })
        });
        const data = await res.json();
        removeTyping();
        
        // Render Learning Events
        if (data.events && data.events.length > 0) {
            data.events.forEach(ev => addArchitectureEvent(ev.layer, ev.action, ev.description));
        } else {
             eventTimeline.innerHTML = '<div class="timeline-empty"><p>No layout events captured.</p></div>';
        }
        
        if (data.error) {
            addMessage('assistant', `⚠️ Error: ${data.error}. ${data.note || ''}`);
        } else {
            addMessage('assistant', data.response, data);
        }
    } catch(e) {
        removeTyping();
        addMessage('assistant', `⚠️ Network error: Could not connect to AI backend.`);
    }
});

// Auto-resize textarea
chatInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
});

// Submit on Enter (Shift+Enter for new line)
chatInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault(); // Prevent default new line
        chatForm.querySelector('button[type="submit"]').click();
    }
});

// Initial Load
loadConfig();
loadContextDocs();

// REST API Tool Management
async function loadTools() {
    try {
        const res = await fetch(`${API_BASE}/tools`);
        const tools = await res.json();
        mcpToolSelect.innerHTML = tools.map(t => `<option value="${t.name}">${t.name}</option>`).join('');
        updateScopeLabel();
    } catch(e) { console.error("Could not fetch tools"); }
}

function openToolsModal() { 
    toolsModal.classList.remove('hidden'); 
    toolFormFeedback.style.display = 'none';
    toolFormFeedback.className = '';
}
function closeToolsModal() { toolsModal.classList.add('hidden'); }

registerToolForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = registerToolForm.querySelector('button');
    btn.innerText = "Registering...";
    toolFormFeedback.style.display = 'none';
    
    try {
        const payload = {
            name: toolNameInput.value,
            description: toolDescInput.value
        };
        if(toolUrlInput && toolUrlInput.value) {
            payload.api_endpoint = toolUrlInput.value;
        }

        const res = await fetch(`${API_BASE}/tools`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        
        const data = await res.json();
        
        if(!res.ok) {
            throw new Error(data.detail || 'Failed to register tool');
        }
        
        toolFormFeedback.style.display = 'block';
        toolFormFeedback.style.background = 'rgba(16, 185, 129, 0.2)';
        toolFormFeedback.style.color = '#10b981';
        toolFormFeedback.style.border = '1px solid #10b981';
        toolFormFeedback.innerText = `Success! '${data.name}' registered.`;
        
        await loadTools();
        
        setTimeout(() => {
            closeToolsModal();
            toolNameInput.value = '';
            toolDescInput.value = '';
            if(toolUrlInput) toolUrlInput.value = '';
        }, 1500);
        
    } catch(err) {
        toolFormFeedback.style.display = 'block';
        toolFormFeedback.style.background = 'rgba(239, 68, 68, 0.2)';
        toolFormFeedback.style.color = '#ef4444';
        toolFormFeedback.style.border = '1px solid #ef4444';
        toolFormFeedback.innerText = err.message;
    } finally {
        btn.innerText = "Register Tool";
    }
});

loadTools();
