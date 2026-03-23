const API_BASE = '/api';

// UI Elements
const uploadZone = document.getElementById('upload-zone');
const fileInput = document.getElementById('file-input');
const contextList = document.getElementById('context-list');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const messagesContainer = document.getElementById('messages-container');
const useContextToggle = document.getElementById('use-context-toggle');

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

chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if(!text) return;
    
    chatInput.value = '';
    addMessage('user', text);
    showTyping();
    
    try {
        const res = await fetch(`${API_BASE}/ai/chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                message: text,
                use_context: useContextToggle.checked
            })
        });
        const data = await res.json();
        removeTyping();
        
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
loadContextDocs();
