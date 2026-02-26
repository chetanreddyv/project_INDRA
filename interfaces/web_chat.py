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
    --gold-matte:     #c9a84c;
    --gold-dark:      #a08030;
    --gold-line:      rgba(201, 168, 76, 0.35);
    --gold-line-dim:  rgba(201, 168, 76, 0.12);
    --gold-glow:      rgba(201, 168, 76, 0.08);

    --frost-bg:       rgba(240, 238, 232, 0.55);
    --frost-border:   rgba(201, 168, 76, 0.20);
    --frost-input:    rgba(200, 198, 192, 0.35);

    --text-primary:   #2a2520;
    --text-secondary: #6b5e45;
    --text-dim:       #a09880;
    --text-inverse:   #faf8f4;

    --success:        #16a34a;
    --error:          #dc2626;

    --page-bg:        #f7f4ee;

    --font-body:  'Inter', sans-serif;
    --font-royal: 'Cinzel', serif;

    --panel-radius:   24px;
    --sidebar-width:  240px;
    --shell-padding:  20px;
  }

  html, body { height: 100%; }

  body {
    font-family: var(--font-body);
    background: var(--page-bg);
    color: var(--text-primary);
    overflow: hidden;
  }

  /* ═══════════════════════════════════════════════════════
     YANTRA SVG BACKGROUND
     ═══════════════════════════════════════════════════════ */
  .yantra-bg {
    position: fixed;
    inset: 0;
    width: 100%;
    height: 100%;
    z-index: 0;
    pointer-events: none;
    opacity: 0.6;
  }

  /* ═══════════════════════════════════════════════════════
     SHELL — full-viewport flex container
     ═══════════════════════════════════════════════════════ */
  .shell {
    display: flex;
    height: 100vh;
    padding: var(--shell-padding);
    gap: 0;
    position: relative;
    z-index: 1;
  }

  /* ═══════════════════════════════════════════════════════
     SIDEBAR — 20% left, part of page
     ═══════════════════════════════════════════════════════ */
  .sidebar {
    width: var(--sidebar-width);
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    padding: 32px 20px;
    gap: 40px;
  }

  .sidebar-logo {
    text-align: center;
  }

  .sidebar-logo-icon {
    width: 56px;
    height: 56px;
    margin: 0 auto 12px;
    border: 2px solid var(--gold-matte);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    color: var(--gold-matte);
    position: relative;
  }
  /* Decorative ring */
  .sidebar-logo-icon::after {
    content: '';
    position: absolute;
    inset: -6px;
    border: 1px solid var(--gold-line);
    border-radius: 50%;
  }

  .sidebar-logo-title {
    font-family: var(--font-royal);
    font-size: 22px;
    font-weight: 700;
    color: var(--gold-matte);
    letter-spacing: 5px;
    text-transform: uppercase;
  }

  .sidebar-logo-sub {
    font-size: 10px;
    color: var(--text-dim);
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-top: 4px;
  }

  /* Yantra divider */
  .sidebar-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--gold-line), transparent);
    margin: 0 8px;
  }

  .sidebar-nav {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .sidebar-nav-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    border-radius: 12px;
    font-size: 13px;
    font-weight: 500;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s;
    letter-spacing: 0.3px;
  }
  .sidebar-nav-item:hover {
    background: var(--gold-glow);
    color: var(--gold-dark);
  }
  .sidebar-nav-item.active {
    color: var(--gold-matte);
    background: rgba(201, 168, 76, 0.08);
    border: 1px solid var(--gold-line-dim);
  }
  .sidebar-nav-item .nav-icon {
    width: 18px;
    text-align: center;
    font-size: 14px;
  }

  /* Sidebar footer */
  .sidebar-footer {
    margin-top: auto;
    text-align: center;
  }
  .sidebar-footer-text {
    font-size: 10px;
    color: var(--text-dim);
    letter-spacing: 1px;
    text-transform: uppercase;
  }

  /* Status indicator */
  .sidebar-status {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    font-size: 11px;
    color: var(--success);
    margin-bottom: 8px;
  }
  .sidebar-status::before {
    content: '';
    width: 6px;
    height: 6px;
    background: var(--success);
    border-radius: 50%;
    animation: pulse 2s ease-in-out infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }

  /* ═══════════════════════════════════════════════════════
     MAIN PANEL — 80% right, rounded frosted glass
     ═══════════════════════════════════════════════════════ */
  .main-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    background: var(--frost-bg);
    border: 1px solid var(--frost-border);
    border-radius: var(--panel-radius);
    backdrop-filter: blur(40px) saturate(1.2);
    -webkit-backdrop-filter: blur(40px) saturate(1.2);
    box-shadow:
      0 8px 60px rgba(0, 0, 0, 0.04),
      inset 0 1px 0 rgba(255, 255, 255, 0.6);
    position: relative;
    overflow: hidden;
  }

  /* Gold motif border accent — top edge */
  .main-panel::before {
    content: '';
    position: absolute;
    top: 0;
    left: 40px;
    right: 40px;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--gold-matte), transparent);
    opacity: 0.4;
    z-index: 2;
  }

  /* ─── Panel Header ─────────────────────────────────── */
  .panel-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 20px 28px;
    border-bottom: 1px solid rgba(201, 168, 76, 0.10);
  }

  .panel-header-title {
    font-family: var(--font-royal);
    font-size: 15px;
    font-weight: 600;
    color: var(--gold-matte);
    letter-spacing: 3px;
    text-transform: uppercase;
  }

  .panel-header-line {
    flex: 1;
    height: 1px;
    background: linear-gradient(90deg, var(--gold-line-dim), transparent);
  }

  /* ─── Messages ─────────────────────────────────────── */
  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 24px 28px;
    padding-bottom: 100px; /* space for floating input */
    display: flex;
    flex-direction: column;
    gap: 16px;
    scroll-behavior: smooth;
  }

  /* Scrollbar */
  .messages::-webkit-scrollbar { width: 4px; }
  .messages::-webkit-scrollbar-track { background: transparent; }
  .messages::-webkit-scrollbar-thumb {
    background: rgba(201, 168, 76, 0.20);
    border-radius: 2px;
  }
  .messages::-webkit-scrollbar-thumb:hover {
    background: rgba(201, 168, 76, 0.35);
  }

  .msg {
    max-width: 72%;
    padding: 14px 20px;
    border-radius: 18px;
    font-size: 14px;
    line-height: 1.75;
    animation: fadeUp 0.3s ease;
    word-wrap: break-word;
    white-space: pre-wrap;
  }

  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  .msg.user {
    align-self: flex-end;
    background: rgba(201, 168, 76, 0.10);
    border: 1px solid rgba(201, 168, 76, 0.18);
    border-bottom-right-radius: 6px;
    color: var(--text-primary);
  }

  .msg.bot {
    align-self: flex-start;
    background: rgba(255, 255, 255, 0.55);
    border: 1px solid rgba(201, 168, 76, 0.12);
    border-bottom-left-radius: 6px;
    color: var(--text-primary);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
  }

  .msg.bot .msg-name {
    font-family: var(--font-royal);
    font-size: 10px;
    color: var(--gold-matte);
    letter-spacing: 2px;
    margin-bottom: 6px;
    text-transform: uppercase;
    font-weight: 600;
  }

  /* Markdown inside bot messages */
  .msg.bot code {
    background: rgba(201, 168, 76, 0.08);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 13px;
    color: var(--gold-dark);
  }

  .msg.bot pre {
    background: rgba(247, 244, 238, 0.90);
    border: 1px solid rgba(201, 168, 76, 0.12);
    border-radius: 10px;
    padding: 14px;
    margin: 8px 0;
    overflow-x: auto;
    font-size: 13px;
    color: var(--text-primary);
  }

  .msg.bot pre code {
    background: none;
    padding: 0;
  }

  .msg.bot strong { color: var(--gold-dark); }
  .msg.bot em { color: var(--text-secondary); }
  .msg.bot ul, .msg.bot ol { padding-left: 20px; margin: 6px 0; }
  .msg.bot li { margin-bottom: 4px; }

  /* ─── Typing indicator ─────────────────────────────── */
  .typing {
    display: none;
    align-self: flex-start;
    padding: 14px 20px;
    background: rgba(255, 255, 255, 0.50);
    border: 1px solid rgba(201, 168, 76, 0.12);
    border-radius: 18px;
    border-bottom-left-radius: 6px;
  }
  .typing.show { display: block; }

  .typing-dots {
    display: flex;
    gap: 5px;
  }
  .typing-dots span {
    width: 6px;
    height: 6px;
    background: var(--gold-matte);
    border-radius: 50%;
    animation: dotPulse 1.4s ease-in-out infinite;
  }
  .typing-dots span:nth-child(2) { animation-delay: 0.2s; }
  .typing-dots span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes dotPulse {
    0%, 100% { opacity: 0.25; transform: scale(0.8); }
    50% { opacity: 1; transform: scale(1); }
  }

  /* ─── HITL Approval ────────────────────────────────── */
  .hitl-card {
    align-self: flex-start;
    max-width: 72%;
    background: rgba(255, 255, 255, 0.55);
    border: 1px solid rgba(201, 168, 76, 0.18);
    border-radius: 18px;
    padding: 20px;
    animation: fadeUp 0.3s ease;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
  }

  .hitl-card .hitl-title {
    font-size: 12px;
    font-family: var(--font-royal);
    color: var(--gold-matte);
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .hitl-card .hitl-details {
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.6;
    margin-bottom: 16px;
    white-space: pre-wrap;
  }

  .hitl-buttons {
    display: flex;
    gap: 10px;
  }

  .hitl-btn {
    padding: 8px 22px;
    border-radius: 10px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    border: none;
    transition: all 0.2s;
    letter-spacing: 0.3px;
  }

  .hitl-btn.approve {
    background: var(--success);
    color: #fff;
  }
  .hitl-btn.approve:hover { box-shadow: 0 4px 16px rgba(22, 163, 74, 0.25); }

  .hitl-btn.reject {
    background: transparent;
    border: 1px solid rgba(220, 38, 38, 0.20);
    color: var(--error);
  }
  .hitl-btn.reject:hover { background: rgba(220, 38, 38, 0.06); }

  .hitl-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  /* ═══════════════════════════════════════════════════════
     FLOATING INPUT — absolute at bottom of main panel
     ═══════════════════════════════════════════════════════ */
  .input-float {
    position: absolute;
    bottom: 20px;
    left: 24px;
    right: 24px;
    z-index: 10;
  }

  .input-glass {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 8px 8px 20px;
    background: rgba(200, 198, 190, 0.35);
    border: 1px solid rgba(201, 168, 76, 0.15);
    border-radius: 50px;
    backdrop-filter: blur(30px) saturate(1.3);
    -webkit-backdrop-filter: blur(30px) saturate(1.3);
    box-shadow:
      0 4px 24px rgba(0, 0, 0, 0.04),
      inset 0 1px 0 rgba(255, 255, 255, 0.50);
    transition: border-color 0.25s, box-shadow 0.25s;
  }
  .input-glass:focus-within {
    border-color: rgba(201, 168, 76, 0.35);
    box-shadow:
      0 4px 24px rgba(0, 0, 0, 0.04),
      0 0 0 3px rgba(201, 168, 76, 0.06),
      inset 0 1px 0 rgba(255, 255, 255, 0.50);
  }

  .input-field {
    flex: 1;
    background: transparent;
    border: none;
    padding: 10px 0;
    font-size: 14px;
    font-family: var(--font-body);
    color: var(--text-primary);
    outline: none;
    resize: none;
    max-height: 100px;
    min-height: 24px;
    line-height: 1.5;
  }
  .input-field::placeholder {
    color: var(--text-dim);
    font-weight: 300;
  }

  .send-btn {
    width: 40px;
    height: 40px;
    background: var(--gold-matte);
    border: none;
    border-radius: 50%;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    color: var(--text-inverse);
    transition: all 0.2s;
    flex-shrink: 0;
  }
  .send-btn:hover {
    background: var(--gold-dark);
    transform: scale(1.05);
  }
  .send-btn:disabled {
    opacity: 0.3;
    cursor: not-allowed;
    transform: none;
  }

  /* ═══════════════════════════════════════════════════════
     WELCOME
     ═══════════════════════════════════════════════════════ */
  .welcome {
    text-align: center;
    padding: 80px 20px 40px;
    animation: fadeUp 0.5s ease;
  }

  .welcome-yantra {
    width: 80px;
    height: 80px;
    margin: 0 auto 20px;
    position: relative;
  }
  .welcome-yantra svg {
    width: 100%;
    height: 100%;
  }

  .welcome h2 {
    font-family: var(--font-royal);
    font-size: 28px;
    color: var(--gold-matte);
    letter-spacing: 6px;
    margin-bottom: 8px;
    font-weight: 700;
    text-transform: uppercase;
  }
  .welcome p {
    color: var(--text-secondary);
    font-size: 13px;
    font-weight: 300;
    letter-spacing: 0.5px;
  }
  .welcome .welcome-hint {
    color: var(--text-dim);
    margin-top: 24px;
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
  }

  /* ═══════════════════════════════════════════════════════
     RESPONSIVE
     ═══════════════════════════════════════════════════════ */
  @media (max-width: 768px) {
    :root {
      --sidebar-width: 0px;
      --shell-padding: 8px;
      --panel-radius:  16px;
    }
    .sidebar { display: none; }
    .input-float { left: 12px; right: 12px; bottom: 12px; }
    .messages { padding: 16px 16px 90px; }
    .msg { max-width: 90%; }
    .hitl-card { max-width: 90%; }
  }
</style>
</head>
<body>

<!-- ═══ YANTRA SVG BACKGROUND ═══ -->
<svg class="yantra-bg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" preserveAspectRatio="xMidYMid slice">
  <defs>
    <style>
      .yl { fill: none; stroke: #c9a84c; stroke-width: 0.5; opacity: 0.25; }
      .yl2 { fill: none; stroke: #c9a84c; stroke-width: 0.3; opacity: 0.15; }
      .yl3 { fill: none; stroke: #c9a84c; stroke-width: 0.8; opacity: 0.12; }
    </style>
  </defs>

  <!-- Outer circle (Bhupura gate) -->
  <circle class="yl3" cx="500" cy="500" r="420"/>
  <circle class="yl2" cx="500" cy="500" r="400"/>
  <circle class="yl2" cx="500" cy="500" r="380"/>

  <!-- Lotus petals — outer ring (16 petals) -->
  <g class="yl2">
    <ellipse cx="500" cy="110" rx="28" ry="60" transform="rotate(0, 500, 500)"/>
    <ellipse cx="500" cy="110" rx="28" ry="60" transform="rotate(22.5, 500, 500)"/>
    <ellipse cx="500" cy="110" rx="28" ry="60" transform="rotate(45, 500, 500)"/>
    <ellipse cx="500" cy="110" rx="28" ry="60" transform="rotate(67.5, 500, 500)"/>
    <ellipse cx="500" cy="110" rx="28" ry="60" transform="rotate(90, 500, 500)"/>
    <ellipse cx="500" cy="110" rx="28" ry="60" transform="rotate(112.5, 500, 500)"/>
    <ellipse cx="500" cy="110" rx="28" ry="60" transform="rotate(135, 500, 500)"/>
    <ellipse cx="500" cy="110" rx="28" ry="60" transform="rotate(157.5, 500, 500)"/>
    <ellipse cx="500" cy="110" rx="28" ry="60" transform="rotate(180, 500, 500)"/>
    <ellipse cx="500" cy="110" rx="28" ry="60" transform="rotate(202.5, 500, 500)"/>
    <ellipse cx="500" cy="110" rx="28" ry="60" transform="rotate(225, 500, 500)"/>
    <ellipse cx="500" cy="110" rx="28" ry="60" transform="rotate(247.5, 500, 500)"/>
    <ellipse cx="500" cy="110" rx="28" ry="60" transform="rotate(270, 500, 500)"/>
    <ellipse cx="500" cy="110" rx="28" ry="60" transform="rotate(292.5, 500, 500)"/>
    <ellipse cx="500" cy="110" rx="28" ry="60" transform="rotate(315, 500, 500)"/>
    <ellipse cx="500" cy="110" rx="28" ry="60" transform="rotate(337.5, 500, 500)"/>
  </g>

  <!-- Inner lotus petals (8 petals) -->
  <g class="yl">
    <ellipse cx="500" cy="200" rx="22" ry="50" transform="rotate(0, 500, 500)"/>
    <ellipse cx="500" cy="200" rx="22" ry="50" transform="rotate(45, 500, 500)"/>
    <ellipse cx="500" cy="200" rx="22" ry="50" transform="rotate(90, 500, 500)"/>
    <ellipse cx="500" cy="200" rx="22" ry="50" transform="rotate(135, 500, 500)"/>
    <ellipse cx="500" cy="200" rx="22" ry="50" transform="rotate(180, 500, 500)"/>
    <ellipse cx="500" cy="200" rx="22" ry="50" transform="rotate(225, 500, 500)"/>
    <ellipse cx="500" cy="200" rx="22" ry="50" transform="rotate(270, 500, 500)"/>
    <ellipse cx="500" cy="200" rx="22" ry="50" transform="rotate(315, 500, 500)"/>
  </g>

  <!-- Sri Yantra triangles — downward (Shakti) -->
  <polygon class="yl" points="500,180 280,700 720,700"/>
  <polygon class="yl2" points="500,220 310,660 690,660"/>
  <polygon class="yl2" points="500,260 340,620 660,620"/>
  <polygon class="yl2" points="500,300 365,585 635,585"/>

  <!-- Sri Yantra triangles — upward (Shiva) -->
  <polygon class="yl" points="500,820 280,300 720,300"/>
  <polygon class="yl2" points="500,780 310,340 690,340"/>
  <polygon class="yl2" points="500,740 340,380 660,380"/>
  <polygon class="yl2" points="500,700 365,415 635,415"/>

  <!-- Inner concentric circles -->
  <circle class="yl" cx="500" cy="500" r="200"/>
  <circle class="yl2" cx="500" cy="500" r="160"/>
  <circle class="yl2" cx="500" cy="500" r="120"/>
  <circle class="yl" cx="500" cy="500" r="60"/>

  <!-- Bindu (center point) -->
  <circle cx="500" cy="500" r="4" fill="#c9a84c" opacity="0.2"/>

  <!-- Decorative corner motifs -->
  <g class="yl2">
    <!-- Top-left -->
    <line x1="20" y1="20" x2="120" y2="20"/>
    <line x1="20" y1="20" x2="20" y2="120"/>
    <path d="M 20,20 Q 60,60 20,120"/>
    <!-- Top-right -->
    <line x1="980" y1="20" x2="880" y2="20"/>
    <line x1="980" y1="20" x2="980" y2="120"/>
    <path d="M 980,20 Q 940,60 980,120"/>
    <!-- Bottom-left -->
    <line x1="20" y1="980" x2="120" y2="980"/>
    <line x1="20" y1="980" x2="20" y2="880"/>
    <path d="M 20,980 Q 60,940 20,880"/>
    <!-- Bottom-right -->
    <line x1="980" y1="980" x2="880" y2="980"/>
    <line x1="980" y1="980" x2="980" y2="880"/>
    <path d="M 980,980 Q 940,940 980,880"/>
  </g>

  <!-- Subtle diamond grid overlay -->
  <g class="yl2" opacity="0.4">
    <line x1="500" y1="0" x2="500" y2="1000"/>
    <line x1="0" y1="500" x2="1000" y2="500"/>
    <line x1="0" y1="0" x2="1000" y2="1000"/>
    <line x1="1000" y1="0" x2="0" y2="1000"/>
  </g>
</svg>

<div class="shell">
  <!-- ═══ SIDEBAR ═══ -->
  <aside class="sidebar">
    <div class="sidebar-logo">
      <div class="sidebar-logo-icon">⚡</div>
      <div class="sidebar-logo-title">Indra</div>
      <div class="sidebar-logo-sub">King of the Gods</div>
    </div>

    <div class="sidebar-divider"></div>

    <nav class="sidebar-nav">
      <div class="sidebar-nav-item active">
        <span class="nav-icon">◈</span>
        Chat
      </div>
      <div class="sidebar-nav-item">
        <span class="nav-icon">◇</span>
        Memory
      </div>
      <div class="sidebar-nav-item">
        <span class="nav-icon">△</span>
        Skills
      </div>
    </nav>

    <div class="sidebar-footer">
      <div class="sidebar-status">Online</div>
      <div class="sidebar-footer-text">Powered by Gemini</div>
    </div>
  </aside>

  <!-- ═══ MAIN PANEL ═══ -->
  <main class="main-panel">
    <!-- Panel Header -->
    <div class="panel-header">
      <span class="panel-header-title">Chat</span>
      <span class="panel-header-line"></span>
    </div>

    <!-- Messages -->
    <div class="messages" id="messages">
      <div class="welcome" id="welcome">
        <div class="welcome-yantra">
          <svg viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg">
            <circle cx="40" cy="40" r="36" fill="none" stroke="#c9a84c" stroke-width="1" opacity="0.5"/>
            <circle cx="40" cy="40" r="28" fill="none" stroke="#c9a84c" stroke-width="0.5" opacity="0.35"/>
            <polygon points="40,10 18,55 62,55" fill="none" stroke="#c9a84c" stroke-width="0.8" opacity="0.5"/>
            <polygon points="40,70 18,25 62,25" fill="none" stroke="#c9a84c" stroke-width="0.8" opacity="0.5"/>
            <circle cx="40" cy="40" r="8" fill="none" stroke="#c9a84c" stroke-width="0.8" opacity="0.4"/>
            <circle cx="40" cy="40" r="2.5" fill="#c9a84c" opacity="0.4"/>
          </svg>
        </div>
        <h2>Indra</h2>
        <p>Intelligent Network for Data, Reasoning, and Action</p>
        <p class="welcome-hint">Type a message to begin</p>
      </div>

      <div class="typing" id="typing">
        <div class="typing-dots">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>

    <!-- Floating Input -->
    <div class="input-float">
      <div class="input-glass">
        <textarea class="input-field" id="input" placeholder="Message Indra..." rows="1"></textarea>
        <button class="send-btn" id="sendBtn" onclick="sendMessage()">↑</button>
      </div>
    </div>
  </main>
</div>

<script>
  const THREAD_ID = 'web_' + Math.random().toString(36).slice(2, 10);
  let isWaiting = false;

  // ═══ Auto-resize textarea ═══
  const input = document.getElementById('input');
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 100) + 'px';
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
      div.innerHTML = `<div class="msg-name">Indra</div>${renderMarkdown(text)}`;
    } else {
      div.textContent = text;
    }

    container.insertBefore(div, typing);
    scrollToBottom();
  }

  // ═══ Basic Markdown renderer ═══
  function renderMarkdown(text) {
    text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
    text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\*(.+?)\*/g, '<strong>$1</strong>');
    text = text.replace(/_(.+?)_/g, '<em>$1</em>');
    text = text.replace(/^[-•] (.+)$/gm, '<li>$1</li>');
    text = text.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
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
      <div class="hitl-title">◈ Approval Required</div>
      <div class="hitl-details">
        <strong>Action:</strong> ${action}
        ${argsHtml ? '\n' + argsHtml : ''}
      </div>
      <div class="hitl-buttons">
        <button class="hitl-btn approve" onclick="handleApproval('approve', this)">Approve</button>
        <button class="hitl-btn reject" onclick="handleApproval('reject', this)">Reject</button>
      </div>
    `;
    container.insertBefore(card, typing);
    scrollToBottom();
  }

  // ═══ Handle approval ═══
  async function handleApproval(decision, btn) {
    const buttons = btn.parentElement.querySelectorAll('button');
    buttons.forEach(b => b.disabled = true);

    btn.textContent = decision === 'approve' ? 'Executing...' : 'Rejected';

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

      btn.textContent = decision === 'approve' ? '✓ Approved' : '✗ Rejected';
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
