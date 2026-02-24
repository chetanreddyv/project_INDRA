"""
web_chat.py — Localhost web chat interface for INDRA.

Provides a beautiful single-page chat UI served at /chat that
communicates with the same LangGraph pipeline used by Telegram.

API endpoints are defined in app.py — this module only serves the HTML.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/chat", response_class=HTMLResponse)
async def serve_chat():
    return HTMLResponse(CHAT_HTML)


CHAT_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>INDRA — Chat</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Cinzel:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg-deep:        #f5f0e8;
    --bg-sidebar:     rgba(255, 255, 255, 0.55);
    --bg-msg-user:    rgba(212, 175, 55, 0.12);
    --bg-msg-bot:     rgba(255, 255, 255, 0.65);
    --bg-input:       rgba(255, 255, 255, 0.60);
    --border-subtle:  rgba(212, 175, 55, 0.22);
    --border-glow:    rgba(212, 175, 55, 0.40);

    --gold:           #b8860b;
    --gold-light:     #d4a017;
    --gold-dim:       rgba(212, 160, 23, 0.30);
    --gold-accent:    rgba(212, 175, 55, 0.08);

    --text-primary:   #1a1710;
    --text-secondary: #6b5e40;
    --text-dim:       #9e9480;

    --success:        #16a34a;
    --error:          #dc2626;

    --font-body:  'Inter', sans-serif;
    --font-royal: 'Cinzel', serif;

    --glass-bg:       rgba(255, 255, 255, 0.50);
    --glass-border:   rgba(212, 175, 55, 0.25);
    --glass-shadow:   0 8px 32px rgba(180, 140, 20, 0.08);
  }

  html, body { height: 100%; }

  body {
    font-family: var(--font-body);
    background: linear-gradient(145deg, #faf7f0 0%, #f0e8d8 40%, #ede4d0 100%);
    color: var(--text-primary);
    overflow: hidden;
  }

  /* ─── Animated Background ──────────────────────────── */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background:
      radial-gradient(ellipse 900px 700px at 15% 20%, rgba(212, 175, 55, 0.10) 0%, transparent 70%),
      radial-gradient(ellipse 600px 500px at 85% 75%, rgba(212, 160, 23, 0.07) 0%, transparent 70%),
      radial-gradient(ellipse 500px 500px at 50% 50%, rgba(255, 255, 255, 0.40) 0%, transparent 70%);
    pointer-events: none;
    z-index: 0;
  }

  /* ─── Layout ───────────────────────────────────────── */
  .chat-app {
    display: flex;
    flex-direction: column;
    height: 100vh;
    position: relative;
    z-index: 1;
  }

  /* ─── Header ───────────────────────────────────────── */
  .header {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 16px 24px;
    background: var(--glass-bg);
    border-bottom: 1px solid var(--glass-border);
    backdrop-filter: blur(24px) saturate(1.4);
    -webkit-backdrop-filter: blur(24px) saturate(1.4);
    box-shadow: 0 1px 12px rgba(180, 140, 20, 0.06);
  }

  .header-icon {
    width: 40px;
    height: 40px;
    background: linear-gradient(135deg, var(--gold), var(--gold-light));
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    box-shadow: 0 0 20px rgba(212, 160, 23, 0.20), 0 0 40px rgba(212, 160, 23, 0.08);
  }

  .header-title {
    font-family: var(--font-royal);
    font-size: 20px;
    font-weight: 600;
    color: var(--gold);
    letter-spacing: 2px;
  }

  .header-status {
    font-size: 11px;
    color: var(--success);
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .header-status::before {
    content: '';
    width: 7px;
    height: 7px;
    background: var(--success);
    border-radius: 50%;
    display: inline-block;
    animation: pulse 2s ease-in-out infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  /* ─── Messages ─────────────────────────────────────── */
  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    scroll-behavior: smooth;
  }

  /* Scrollbar */
  .messages::-webkit-scrollbar { width: 6px; }
  .messages::-webkit-scrollbar-track { background: transparent; }
  .messages::-webkit-scrollbar-thumb {
    background: rgba(212, 160, 23, 0.25);
    border-radius: 3px;
  }
  .messages::-webkit-scrollbar-thumb:hover {
    background: rgba(212, 160, 23, 0.40);
  }

  .msg {
    max-width: 75%;
    padding: 14px 18px;
    border-radius: 16px;
    font-size: 14px;
    line-height: 1.7;
    animation: fadeUp 0.3s ease;
    word-wrap: break-word;
    white-space: pre-wrap;
  }

  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  .msg.user {
    align-self: flex-end;
    background: rgba(212, 175, 55, 0.12);
    border: 1px solid rgba(212, 175, 55, 0.25);
    border-bottom-right-radius: 4px;
    color: var(--text-primary);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    box-shadow: 0 2px 12px rgba(180, 140, 20, 0.06);
  }

  .msg.bot {
    align-self: flex-start;
    background: rgba(255, 255, 255, 0.65);
    border: 1px solid var(--glass-border);
    border-bottom-left-radius: 4px;
    color: var(--text-primary);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    box-shadow: var(--glass-shadow);
  }

  .msg.bot .msg-name {
    font-family: var(--font-royal);
    font-size: 11px;
    color: var(--gold);
    letter-spacing: 1px;
    margin-bottom: 6px;
    text-transform: uppercase;
  }

  /* Markdown rendering inside bot messages */
  .msg.bot code {
    background: rgba(212, 175, 55, 0.10);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 13px;
    color: #8b6914;
  }

  .msg.bot pre {
    background: rgba(245, 240, 232, 0.80);
    border: 1px solid rgba(212, 175, 55, 0.15);
    border-radius: 8px;
    padding: 12px;
    margin: 8px 0;
    overflow-x: auto;
    font-size: 13px;
    color: var(--text-primary);
  }

  .msg.bot pre code {
    background: none;
    padding: 0;
    color: var(--text-primary);
  }

  .msg.bot strong { color: var(--gold); }
  .msg.bot em { color: var(--text-secondary); }
  .msg.bot ul, .msg.bot ol { padding-left: 20px; margin: 6px 0; }
  .msg.bot li { margin-bottom: 4px; }

  /* ─── Typing indicator ─────────────────────────────── */
  .typing {
    display: none;
    align-self: flex-start;
    padding: 14px 18px;
    background: rgba(255, 255, 255, 0.60);
    border: 1px solid var(--glass-border);
    border-radius: 16px;
    border-bottom-left-radius: 4px;
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
  }
  .typing.show { display: block; }

  .typing-dots {
    display: flex;
    gap: 5px;
  }
  .typing-dots span {
    width: 7px;
    height: 7px;
    background: var(--gold);
    border-radius: 50%;
    animation: dotPulse 1.4s ease-in-out infinite;
  }
  .typing-dots span:nth-child(2) { animation-delay: 0.2s; }
  .typing-dots span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes dotPulse {
    0%, 100% { opacity: 0.3; transform: scale(0.8); }
    50% { opacity: 1; transform: scale(1); }
  }

  /* ─── HITL Approval ────────────────────────────────── */
  .hitl-card {
    align-self: flex-start;
    max-width: 75%;
    background: rgba(255, 255, 255, 0.60);
    border: 1px solid var(--glass-border);
    border-radius: 16px;
    padding: 18px;
    animation: fadeUp 0.3s ease;
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    box-shadow: var(--glass-shadow);
  }

  .hitl-card .hitl-title {
    font-size: 13px;
    color: var(--gold);
    font-weight: 600;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .hitl-card .hitl-details {
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.6;
    margin-bottom: 14px;
    white-space: pre-wrap;
  }

  .hitl-buttons {
    display: flex;
    gap: 10px;
  }

  .hitl-btn {
    padding: 8px 20px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    border: none;
    transition: all 0.2s;
  }

  .hitl-btn.approve {
    background: linear-gradient(135deg, var(--success), #15803d);
    color: #fff;
  }
  .hitl-btn.approve:hover { box-shadow: 0 0 15px rgba(22, 163, 74, 0.30); }

  .hitl-btn.reject {
    background: rgba(220, 38, 38, 0.08);
    border: 1px solid rgba(220, 38, 38, 0.25);
    color: var(--error);
  }
  .hitl-btn.reject:hover { background: rgba(220, 38, 38, 0.15); }

  .hitl-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  /* ─── Input area ───────────────────────────────────── */
  .input-area {
    padding: 16px 24px;
    background: var(--glass-bg);
    border-top: 1px solid var(--glass-border);
    backdrop-filter: blur(24px) saturate(1.4);
    -webkit-backdrop-filter: blur(24px) saturate(1.4);
    box-shadow: 0 -1px 12px rgba(180, 140, 20, 0.04);
  }

  .input-row {
    display: flex;
    gap: 12px;
    max-width: 900px;
    margin: 0 auto;
  }

  .input-field {
    flex: 1;
    background: rgba(255, 255, 255, 0.70);
    border: 1px solid rgba(212, 175, 55, 0.20);
    border-radius: 12px;
    padding: 14px 18px;
    font-size: 14px;
    font-family: var(--font-body);
    color: var(--text-primary);
    outline: none;
    transition: border-color 0.25s, box-shadow 0.25s;
    resize: none;
    max-height: 120px;
    min-height: 48px;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
  }
  .input-field::placeholder { color: var(--text-dim); }
  .input-field:focus {
    border-color: var(--gold);
    box-shadow: 0 0 0 3px rgba(212, 160, 23, 0.12);
  }

  .send-btn {
    width: 48px;
    height: 48px;
    background: linear-gradient(135deg, var(--gold), #a07608);
    border: none;
    border-radius: 12px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    color: #fff;
    transition: all 0.2s;
    flex-shrink: 0;
    box-shadow: 0 4px 16px rgba(212, 160, 23, 0.20);
  }
  .send-btn:hover {
    box-shadow: 0 6px 24px rgba(212, 160, 23, 0.35);
    transform: translateY(-1px);
  }
  .send-btn:disabled {
    opacity: 0.3;
    cursor: not-allowed;
    transform: none;
  }

  /* ─── Welcome message ──────────────────────────────── */
  .welcome {
    text-align: center;
    padding: 60px 20px;
    animation: fadeUp 0.5s ease;
  }

  .welcome-icon {
    width: 80px;
    height: 80px;
    margin: 0 auto 20px;
    background: linear-gradient(135deg, var(--gold), var(--gold-light));
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 36px;
    box-shadow: 0 0 60px rgba(212, 160, 23, 0.20), 0 0 120px rgba(212, 160, 23, 0.06);
  }

  .welcome h2 {
    font-family: var(--font-royal);
    font-size: 24px;
    color: var(--gold);
    margin-bottom: 8px;
  }
  .welcome p {
    color: var(--text-secondary);
    font-size: 14px;
  }

  /* ─── Responsive ───────────────────────────────────── */
  @media (max-width: 640px) {
    .msg { max-width: 90%; }
    .hitl-card { max-width: 90%; }
    .messages { padding: 16px; }
  }
</style>
</head>
<body>

<div class="chat-app">
  <!-- Header -->
  <div class="header">
    <div class="header-icon">⚡</div>
    <span class="header-title">INDRA</span>
    <span class="header-status">Online</span>
  </div>

  <!-- Messages -->
  <div class="messages" id="messages">
    <div class="welcome" id="welcome">
      <div class="welcome-icon">⚡</div>
      <h2>INDRA</h2>
      <p>Intelligent Network for Data, Reasoning, and Action</p>
      <p style="color:var(--text-dim); margin-top:12px; font-size:12px;">Type a message to begin</p>
    </div>

    <div class="typing" id="typing">
      <div class="typing-dots">
        <span></span><span></span><span></span>
      </div>
    </div>
  </div>

  <!-- Input -->
  <div class="input-area">
    <div class="input-row">
      <textarea class="input-field" id="input" placeholder="Message INDRA..." rows="1"></textarea>
      <button class="send-btn" id="sendBtn" onclick="sendMessage()">↑</button>
    </div>
  </div>
</div>

<script>
  const THREAD_ID = 'web_' + Math.random().toString(36).slice(2, 10);
  let isWaiting = false;

  // ═══ Auto-resize textarea ═══
  const input = document.getElementById('input');
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  });

  // ═══ Send message ═══
  async function sendMessage() {
    const text = input.value.trim();
    if (!text || isWaiting) return;

    // Hide welcome
    const welcome = document.getElementById('welcome');
    if (welcome) welcome.remove();

    // Add user message
    addMessage(text, 'user');
    input.value = '';
    input.style.height = 'auto';

    // Show typing
    isWaiting = true;
    document.getElementById('sendBtn').disabled = true;
    showTyping(true);

    try {
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ message: text, thread_id: THREAD_ID })
      });
      const data = await resp.json();

      showTyping(false);

      if (data.approval_required) {
        // Show HITL approval card
        addHitlCard(data.action, data.details, data.tool_args);
      } else if (data.response) {
        addMessage(data.response, 'bot');
      } else if (data.error) {
        addMessage('❌ ' + data.error, 'bot');
      }
    } catch (e) {
      showTyping(false);
      addMessage('❌ Connection error. Is the server running?', 'bot');
    }

    isWaiting = false;
    document.getElementById('sendBtn').disabled = false;
    input.focus();
  }

  // ═══ Add message bubble ═══
  function addMessage(text, role) {
    const container = document.getElementById('messages');
    const typing = document.getElementById('typing');
    const div = document.createElement('div');
    div.className = `msg ${role}`;

    if (role === 'bot') {
      div.innerHTML = `<div class="msg-name">INDRA</div>${renderMarkdown(text)}`;
    } else {
      div.textContent = text;
    }

    container.insertBefore(div, typing);
    scrollToBottom();
  }

  // ═══ Basic Markdown renderer ═══
  function renderMarkdown(text) {
    // Code blocks
    text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    // Inline code
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bold
    text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\*(.+?)\*/g, '<strong>$1</strong>');
    // Italic
    text = text.replace(/_(.+?)_/g, '<em>$1</em>');
    // Lists
    text = text.replace(/^[-•] (.+)$/gm, '<li>$1</li>');
    text = text.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
    // Line breaks (preserve whitespace)
    text = text.replace(/\n/g, '<br>');
    return text;
  }

  // ═══ HITL approval card ═══
  function addHitlCard(action, details, toolArgs) {
    const container = document.getElementById('messages');
    const typing = document.getElementById('typing');

    const argsHtml = Object.entries(toolArgs || {})
      .map(([k, v]) => `  • <strong>${k}</strong>: ${v}`)
      .join('\n');

    const card = document.createElement('div');
    card.className = 'hitl-card';
    card.innerHTML = `
      <div class="hitl-title">🔐 Approval Required</div>
      <div class="hitl-details">
        <strong>Action:</strong> ${action}
        ${argsHtml ? '\n' + argsHtml : ''}
      </div>
      <div class="hitl-buttons">
        <button class="hitl-btn approve" onclick="handleApproval('approve', this)">✅ Approve</button>
        <button class="hitl-btn reject" onclick="handleApproval('reject', this)">❌ Reject</button>
      </div>
    `;
    container.insertBefore(card, typing);
    scrollToBottom();
  }

  // ═══ Handle approval ═══
  async function handleApproval(decision, btn) {
    // Disable buttons
    const buttons = btn.parentElement.querySelectorAll('button');
    buttons.forEach(b => b.disabled = true);

    btn.textContent = decision === 'approve' ? '⏳ Executing...' : '❌ Rejected';

    showTyping(true);

    try {
      const resp = await fetch('/api/chat/approve', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ decision, thread_id: THREAD_ID })
      });
      const data = await resp.json();

      showTyping(false);

      if (data.response) {
        addMessage(data.response, 'bot');
      }

      // Update button text
      btn.textContent = decision === 'approve' ? '✅ Approved' : '❌ Rejected';
    } catch (e) {
      showTyping(false);
      addMessage('❌ Error processing approval.', 'bot');
    }
  }

  // ═══ Helpers ═══
  function showTyping(show) {
    document.getElementById('typing').classList.toggle('show', show);
    if (show) scrollToBottom();
  }

  function scrollToBottom() {
    const container = document.getElementById('messages');
    setTimeout(() => container.scrollTop = container.scrollHeight, 50);
  }

  // Enter to send, Shift+Enter for newline
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
</script>

</body>
</html>
"""
