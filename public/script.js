const keyList = document.getElementById('key-list');
const logTerminal = document.getElementById('log-terminal');
const addKeyBtn = document.getElementById('add-key-btn');
const modal = document.getElementById('add-key-modal');
const closeModal = document.getElementById('close-modal');
const confirmAddKey = document.getElementById('confirm-add-key');
const keyLabelInput = document.getElementById('key-label');

// Fetch Keys
async function fetchKeys() {
    const res = await fetch('/api/keys');
    const keys = await res.json();
    renderKeys(keys);
}

// Render Keys
function renderKeys(keys) {
    if (keys.length === 0) {
        keyList.innerHTML = '<p class="text-dim" style="text-align:center; padding: 2rem;">No API keys found.</p>';
        return;
    }
    keyList.innerHTML = keys.map(k => `
        <div class="key-item">
            <div class="key-info">
                <h4>${k.label}</h4>
                <p>Created: ${new Date(k.created).toLocaleDateString()}</p>
            </div>
            <div class="key-string">${k.key}</div>
            <button class="delete-key" onclick="deleteKey('${k.id}')">&times;</button>
        </div>
    `).join('');
}

// Delete Key
async function deleteKey(id) {
    if (!confirm('Are you sure you want to delete this key?')) return;
    await fetch(`/api/keys/${id}`, { method: 'DELETE' });
    fetchKeys();
    showNotification('Key deleted successfully');
}

// Fetch Logs
async function fetchLogs() {
    const res = await fetch('/api/logs');
    const logs = await res.json();
    renderLogs(logs);
}

// Render Logs
function renderLogs(logs) {
    const currentScroll = logTerminal.scrollTop;
    const isAtBottom = logTerminal.scrollHeight - logTerminal.clientHeight <= logTerminal.scrollTop + 10;

    logTerminal.innerHTML = logs.map(l => `
        <div class="log-entry log-${l.type}">
            <span class="log-ts">[${l.timestamp}]</span>
            <span class="log-msg">${l.msg}</span>
        </div>
    `).join('');

    if (isAtBottom) {
        logTerminal.scrollTop = logTerminal.scrollHeight;
    }
}

// Modal Logic
addKeyBtn.onclick = () => modal.style.display = 'flex';
closeModal.onclick = () => modal.style.display = 'none';

confirmAddKey.onclick = async () => {
    const label = keyLabelInput.value.trim();
    if (!label) return alert('Please enter a label');
    
    await fetch('/api/keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label })
    });
    
    keyLabelInput.value = '';
    modal.style.display = 'none';
    fetchKeys();
    showNotification('New API key generated');
};

// Notification
function showNotification(msg) {
    const notif = document.createElement('div');
    notif.className = 'notification';
    notif.textContent = msg;
    document.getElementById('notifications').appendChild(notif);
    setTimeout(() => notif.remove(), 3000);
}

// Initial Fetch and Polling
fetchKeys();
fetchLogs();
setInterval(fetchLogs, 2000); // Poll logs every 2 seconds
