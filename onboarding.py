"""
onboarding.py — Interactive setup wizard for INDRA.

Launches a beautiful localhost web UI that walks non-technical users
through every configuration step.  Validates API keys in real-time
against the actual APIs and writes a .env file on completion.

Usage:
    uv run python onboarding.py           # opens browser to localhost:8000
    uv run python onboarding.py --cli     # CLI-only fallback (headless)
"""

import os
import sys
import json
import asyncio
import webbrowser
import logging
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent
ENV_PATH = PROJECT_ROOT / ".env"
ENV_EXAMPLE_PATH = PROJECT_ROOT / ".env.example"

# ══════════════════════════════════════════════════════════════
# 1. Validation helpers
# ══════════════════════════════════════════════════════════════

async def validate_gemini_key(api_key: str) -> dict:
    """Test a Gemini API key with a real lightweight call."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return {"valid": True, "message": "Gemini API key is valid ✅"}
            elif resp.status_code == 400:
                return {"valid": False, "message": "Invalid API key format. Check for extra spaces or characters."}
            elif resp.status_code == 403:
                return {"valid": False, "message": "API key is forbidden — it may be restricted or disabled."}
            else:
                return {"valid": False, "message": f"Unexpected response ({resp.status_code}). Double-check the key."}
    except Exception as e:
        return {"valid": False, "message": f"Connection error: {str(e)}"}


async def validate_telegram_token(token: str) -> dict:
    """Test a Telegram bot token via getMe."""
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            data = resp.json()
            if data.get("ok"):
                bot_name = data["result"].get("first_name", "Unknown")
                username = data["result"].get("username", "")
                return {
                    "valid": True,
                    "message": f"Connected to bot: {bot_name} (@{username}) ✅",
                    "bot_name": bot_name,
                    "username": username,
                }
            else:
                return {"valid": False, "message": "Invalid token. Make sure you copied the full token from @BotFather."}
    except Exception as e:
        return {"valid": False, "message": f"Connection error: {str(e)}"}


def validate_chat_ids(chat_ids: str) -> dict:
    """Validate comma-separated chat IDs."""
    if not chat_ids.strip():
        return {"valid": False, "message": "At least one Chat ID is required."}
    try:
        ids = [int(cid.strip()) for cid in chat_ids.split(",") if cid.strip()]
        if not ids:
            return {"valid": False, "message": "No valid IDs found. Enter numeric Telegram chat IDs."}
        return {"valid": True, "message": f"{len(ids)} Chat ID(s) configured ✅"}
    except ValueError:
        return {"valid": False, "message": "Chat IDs must be numbers, separated by commas."}


def write_env_file(config: dict) -> str:
    """Write the .env file from the collected configuration."""
    lines = [
        "# ── Telegram ─────────────────────────────────────────────────",
        f"TELEGRAM_BOT_TOKEN={config.get('telegram_bot_token', '')}",
        f"TELEGRAM_SECRET_TOKEN={config.get('telegram_secret_token', '')}",
        f"ALLOWED_CHAT_IDS={config.get('allowed_chat_ids', '')}",
        "",
        "# ── LLM (Gemini) ────────────────────────────────────────────",
        f"GOOGLE_API_KEY={config.get('google_api_key', '')}",
        "",
        "# ── Google Workspace ─────────────────────────────────────────",
        f"GOOGLE_TOKEN_JSON={config.get('google_token_json', '')}",
        "",
        "# ── Observability (optional) ─────────────────────────────────",
        f"LANGCHAIN_TRACING_V2={config.get('langchain_tracing', 'false')}",
        f"LANGSMITH_API_KEY={config.get('langsmith_key', '')}",
        f"LOGFIRE_TOKEN={config.get('logfire_token', '')}",
    ]
    content = "\n".join(lines) + "\n"
    ENV_PATH.write_text(content)
    return str(ENV_PATH)


# ══════════════════════════════════════════════════════════════
# 2. FastAPI mini-app
# ══════════════════════════════════════════════════════════════

app = FastAPI(title="INDRA Setup Wizard")


class ValidateRequest(BaseModel):
    key: str

class CompleteRequest(BaseModel):
    google_api_key: str
    telegram_bot_token: str
    allowed_chat_ids: str
    telegram_secret_token: str = ""
    google_token_json: str = ""


@app.get("/", response_class=HTMLResponse)
async def serve_wizard():
    """Serve the single-page onboarding wizard."""
    return HTMLResponse(content=WIZARD_HTML, status_code=200)


@app.post("/api/validate/gemini")
async def api_validate_gemini(req: ValidateRequest):
    result = await validate_gemini_key(req.key.strip())
    return JSONResponse(content=result)


@app.post("/api/validate/telegram")
async def api_validate_telegram(req: ValidateRequest):
    result = await validate_telegram_token(req.key.strip())
    return JSONResponse(content=result)


@app.post("/api/validate/chat-id")
async def api_validate_chat_id(req: ValidateRequest):
    result = validate_chat_ids(req.key.strip())
    return JSONResponse(content=result)


@app.post("/api/complete")
async def api_complete(req: CompleteRequest):
    """Write .env and return success."""
    config = req.model_dump()
    env_path = write_env_file(config)
    return JSONResponse(content={
        "success": True,
        "env_path": env_path,
        "message": "Configuration saved! You can now start INDRA.",
    })


# ══════════════════════════════════════════════════════════════
# 3. HTML/CSS/JS — Indian Mythology-Inspired UI
# ══════════════════════════════════════════════════════════════

WIZARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>INDRA — Setup Wizard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Cinzel:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  /* ─── Reset & Base ─────────────────────────────────────── */
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg-deep:        #07060e;
    --bg-card:        rgba(18, 15, 35, 0.70);
    --bg-sidebar:     rgba(14, 11, 28, 0.85);
    --border-subtle:  rgba(212, 175, 55, 0.12);
    --border-glow:    rgba(212, 175, 55, 0.25);

    /* 2-3 tone palette: Deep Indigo + Saffron Gold + Subtle Maroon */
    --gold:           #d4a017;
    --gold-light:     #f0d060;
    --gold-dim:       rgba(212, 160, 23, 0.35);
    --indigo:         #2d1b69;
    --indigo-light:   #4a2fa0;
    --maroon:         #6b1030;
    --maroon-dim:     rgba(107, 16, 48, 0.3);

    --text-primary:   #f0e6d2;
    --text-secondary: #a89b80;
    --text-dim:       #6b6050;

    --success:        #34d399;
    --error:          #f87171;

    --font-body:  'Inter', sans-serif;
    --font-royal: 'Cinzel', serif;
  }

  body {
    font-family: var(--font-body);
    background: var(--bg-deep);
    color: var(--text-primary);
    min-height: 100vh;
    overflow-x: hidden;
  }

  /* ─── Animated Background ──────────────────────────────── */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background:
      radial-gradient(ellipse 800px 600px at 20% 30%, rgba(45, 27, 105, 0.35) 0%, transparent 70%),
      radial-gradient(ellipse 600px 500px at 80% 70%, rgba(107, 16, 48, 0.20) 0%, transparent 70%),
      radial-gradient(ellipse 400px 400px at 50% 50%, rgba(212, 160, 23, 0.08) 0%, transparent 70%);
    pointer-events: none;
    z-index: 0;
  }

  /* ─── Shell ────────────────────────────────────────────── */
  .shell {
    display: flex;
    min-height: 100vh;
    position: relative;
    z-index: 1;
  }

  /* ─── Sidebar ──────────────────────────────────────────── */
  .sidebar {
    width: 280px;
    min-height: 100vh;
    background: var(--bg-sidebar);
    border-right: 1px solid var(--border-subtle);
    padding: 40px 24px;
    display: flex;
    flex-direction: column;
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
  }

  .logo-section {
    text-align: center;
    margin-bottom: 48px;
  }

  .logo-icon {
    width: 72px;
    height: 72px;
    margin: 0 auto 16px;
    background: linear-gradient(135deg, var(--gold), var(--gold-light));
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 0 40px rgba(212, 160, 23, 0.30), 0 0 80px rgba(212, 160, 23, 0.10);
    font-size: 32px;
  }

  .logo-title {
    font-family: var(--font-royal);
    font-size: 28px;
    font-weight: 700;
    color: var(--gold);
    letter-spacing: 4px;
    text-shadow: 0 0 30px rgba(212, 160, 23, 0.3);
  }

  .logo-subtitle {
    font-size: 11px;
    color: var(--text-secondary);
    margin-top: 4px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
  }

  /* ─── Step indicators ──────────────────────────────────── */
  .steps { list-style: none; flex: 1; }

  .steps li {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 14px 16px;
    border-radius: 10px;
    margin-bottom: 4px;
    cursor: pointer;
    transition: all 0.3s ease;
    font-size: 14px;
    color: var(--text-dim);
  }

  .steps li:hover { background: rgba(212, 160, 23, 0.05); }
  .steps li.active {
    background: rgba(212, 160, 23, 0.08);
    color: var(--gold-light);
    border: 1px solid var(--border-glow);
  }
  .steps li.completed { color: var(--success); }

  .step-dot {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    border: 2px solid var(--text-dim);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 600;
    flex-shrink: 0;
    transition: all 0.3s ease;
  }
  .steps li.active .step-dot {
    border-color: var(--gold);
    background: var(--gold-dim);
    color: var(--gold-light);
    box-shadow: 0 0 12px rgba(212, 160, 23, 0.25);
  }
  .steps li.completed .step-dot {
    border-color: var(--success);
    background: rgba(52, 211, 153, 0.15);
    color: var(--success);
  }

  .sidebar-footer {
    font-size: 11px;
    color: var(--text-dim);
    text-align: center;
    padding-top: 24px;
    border-top: 1px solid var(--border-subtle);
  }

  /* ─── Main content ─────────────────────────────────────── */
  .main {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 48px;
  }

  .card {
    width: 100%;
    max-width: 640px;
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 20px;
    padding: 48px;
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    box-shadow:
      0 4px 60px rgba(0, 0, 0, 0.4),
      inset 0 1px 0 rgba(212, 175, 55, 0.06);
    animation: fadeUp 0.5s ease;
  }

  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(20px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  .card-title {
    font-family: var(--font-royal);
    font-size: 26px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 8px;
  }

  .card-desc {
    font-size: 14px;
    color: var(--text-secondary);
    line-height: 1.7;
    margin-bottom: 32px;
  }

  .card-desc a {
    color: var(--gold);
    text-decoration: none;
    border-bottom: 1px solid var(--gold-dim);
    transition: border-color 0.2s;
  }
  .card-desc a:hover {
    border-color: var(--gold);
  }

  /* ─── Instruction box ──────────────────────────────────── */
  .instructions {
    background: rgba(45, 27, 105, 0.2);
    border: 1px solid rgba(74, 47, 160, 0.25);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 28px;
    font-size: 13px;
    line-height: 1.8;
    color: var(--text-secondary);
  }
  .instructions ol { padding-left: 20px; }
  .instructions li { margin-bottom: 6px; }
  .instructions strong { color: var(--text-primary); }

  /* ─── Form elements ────────────────────────────────────── */
  .input-group {
    margin-bottom: 24px;
  }

  .input-label {
    display: block;
    font-size: 12px;
    font-weight: 500;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 8px;
  }

  .input-row {
    display: flex;
    gap: 10px;
  }

  .input-field {
    flex: 1;
    background: rgba(7, 6, 14, 0.6);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    padding: 14px 16px;
    font-size: 14px;
    font-family: 'Inter', monospace;
    color: var(--text-primary);
    outline: none;
    transition: border-color 0.25s, box-shadow 0.25s;
  }

  .input-field::placeholder { color: var(--text-dim); }
  .input-field:focus {
    border-color: var(--gold);
    box-shadow: 0 0 0 3px rgba(212, 160, 23, 0.10);
  }
  .input-field.valid   { border-color: var(--success); }
  .input-field.invalid { border-color: var(--error); }

  /* ─── Buttons ──────────────────────────────────────────── */
  .btn {
    padding: 12px 28px;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    border: none;
    transition: all 0.25s ease;
    letter-spacing: 0.3px;
  }

  .btn-validate {
    background: linear-gradient(135deg, var(--indigo), var(--indigo-light));
    color: var(--text-primary);
    border: 1px solid rgba(74, 47, 160, 0.4);
  }
  .btn-validate:hover {
    box-shadow: 0 0 20px rgba(74, 47, 160, 0.3);
    transform: translateY(-1px);
  }
  .btn-validate:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
  }

  .btn-next {
    background: linear-gradient(135deg, var(--gold), #c49515);
    color: var(--bg-deep);
    font-weight: 700;
    min-width: 140px;
    box-shadow: 0 0 20px rgba(212, 160, 23, 0.15);
  }
  .btn-next:hover {
    box-shadow: 0 0 30px rgba(212, 160, 23, 0.30);
    transform: translateY(-1px);
  }
  .btn-next:disabled {
    opacity: 0.35;
    cursor: not-allowed;
    transform: none;
  }

  .btn-back {
    background: transparent;
    border: 1px solid var(--border-subtle);
    color: var(--text-secondary);
  }
  .btn-back:hover {
    background: rgba(212, 175, 55, 0.05);
    border-color: var(--border-glow);
  }

  .btn-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 32px;
  }

  /* ─── Validation feedback ──────────────────────────────── */
  .feedback {
    margin-top: 12px;
    padding: 12px 16px;
    border-radius: 8px;
    font-size: 13px;
    display: none;
    animation: fadeUp 0.3s ease;
  }
  .feedback.success {
    display: block;
    background: rgba(52, 211, 153, 0.08);
    border: 1px solid rgba(52, 211, 153, 0.25);
    color: var(--success);
  }
  .feedback.error {
    display: block;
    background: rgba(248, 113, 113, 0.08);
    border: 1px solid rgba(248, 113, 113, 0.25);
    color: var(--error);
  }

  /* ─── Loading spinner ──────────────────────────────────── */
  .spinner {
    display: inline-block;
    width: 16px;
    height: 16px;
    border: 2px solid rgba(240, 230, 210, 0.3);
    border-top-color: var(--gold);
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
    vertical-align: middle;
    margin-right: 6px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ─── Completion screen ────────────────────────────────── */
  .completion-icon {
    width: 80px;
    height: 80px;
    margin: 0 auto 24px;
    background: linear-gradient(135deg, var(--gold), var(--gold-light));
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 36px;
    box-shadow: 0 0 60px rgba(212, 160, 23, 0.35);
  }

  .cmd-block {
    background: rgba(7, 6, 14, 0.8);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    padding: 16px 20px;
    font-family: 'Courier New', monospace;
    font-size: 14px;
    color: var(--gold-light);
    margin: 20px 0;
    position: relative;
  }
  .cmd-block .copy-btn {
    position: absolute;
    right: 10px;
    top: 10px;
    background: rgba(212, 160, 23, 0.15);
    border: 1px solid var(--border-glow);
    color: var(--gold);
    padding: 4px 12px;
    border-radius: 6px;
    font-size: 11px;
    cursor: pointer;
    transition: all 0.2s;
  }
  .cmd-block .copy-btn:hover { background: rgba(212, 160, 23, 0.25); }

  .config-summary {
    background: rgba(45, 27, 105, 0.15);
    border: 1px solid rgba(74, 47, 160, 0.2);
    border-radius: 12px;
    padding: 20px;
    margin: 20px 0;
  }
  .config-summary h4 {
    color: var(--text-secondary);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 12px;
  }
  .config-row {
    display: flex;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid rgba(212, 175, 55, 0.06);
    font-size: 13px;
  }
  .config-row:last-child { border-bottom: none; }
  .config-key { color: var(--text-secondary); }
  .config-val { color: var(--success); font-weight: 500; }
  .config-val.skipped { color: var(--text-dim); }

  /* ─── Skip link ────────────────────────────────────────── */
  .skip-link {
    font-size: 12px;
    color: var(--text-dim);
    cursor: pointer;
    text-decoration: underline;
    text-underline-offset: 3px;
    transition: color 0.2s;
    display: inline-block;
    margin-top: 12px;
  }
  .skip-link:hover { color: var(--text-secondary); }

  /* ─── Page sections ────────────────────────────────────── */
  .page { display: none; }
  .page.active { display: block; }

  /* ─── Responsive ───────────────────────────────────────── */
  @media (max-width: 768px) {
    .shell { flex-direction: column; }
    .sidebar {
      width: 100%;
      min-height: auto;
      flex-direction: row;
      padding: 16px;
      overflow-x: auto;
    }
    .logo-section { display: none; }
    .steps { display: flex; gap: 8px; }
    .steps li { padding: 8px 12px; font-size: 12px; white-space: nowrap; }
    .sidebar-footer { display: none; }
    .main { padding: 24px; }
    .card { padding: 28px; }
  }
</style>
</head>
<body>

<div class="shell">
  <!-- ═══ SIDEBAR ═══ -->
  <aside class="sidebar">
    <div class="logo-section">
      <div class="logo-icon">⚡</div>
      <div class="logo-title">INDRA</div>
      <div class="logo-subtitle">Setup Wizard</div>
    </div>
    <ul class="steps" id="stepsList">
      <li class="active"  data-step="0"><span class="step-dot">1</span> Welcome</li>
      <li data-step="1"><span class="step-dot">2</span> Google API Key</li>
      <li data-step="2"><span class="step-dot">3</span> Telegram Bot</li>
      <li data-step="3"><span class="step-dot">4</span> Chat ID</li>
      <li data-step="4"><span class="step-dot">5</span> Google Workspace</li>
      <li data-step="5"><span class="step-dot">✦</span> Complete</li>
    </ul>
    <div class="sidebar-footer">
      Powered by Gemini 2.5 Flash<br>
      <span style="color:var(--gold-dim)">King of the Gods</span>
    </div>
  </aside>

  <!-- ═══ MAIN CONTENT ═══ -->
  <main class="main">
    <!-- ── Step 0: Welcome ── -->
    <div class="card page active" id="page-0">
      <div style="text-align:center; margin-bottom:24px;">
        <div class="logo-icon" style="margin:0 auto 16px;">⚡</div>
        <h1 class="card-title" style="font-size:32px;">Welcome to INDRA</h1>
      </div>
      <p class="card-desc" style="text-align:center;">
        <em>Intelligent Network for Data, Reasoning, and Action</em><br><br>
        This wizard will guide you through setting up your personal AI assistant
        in a few quick steps. You'll need:
      </p>
      <div class="instructions">
        <ol>
          <li><strong>A Google AI Studio API Key</strong> — powers the intelligence (free tier available)</li>
          <li><strong>A Telegram Bot Token</strong> — connects INDRA to your Telegram</li>
          <li><strong>Your Telegram Chat ID</strong> — restricts access to only you</li>
          <li><strong>Google Workspace credentials</strong> — <em>optional</em>, for email & calendar</li>
        </ol>
      </div>
      <p class="card-desc" style="text-align:center; margin-bottom:0;">
        Each step takes about 1–2 minutes. Let's begin. ⚡
      </p>
      <div class="btn-row" style="justify-content:center;">
        <button class="btn btn-next" onclick="goToStep(1)">Begin Setup →</button>
      </div>
    </div>

    <!-- ── Step 1: Google API Key ── -->
    <div class="card page" id="page-1">
      <h2 class="card-title">Google API Key</h2>
      <p class="card-desc">
        This key powers INDRA's intelligence via the Gemini 2.5 Flash model.
      </p>
      <div class="instructions">
        <ol>
          <li>Go to <a href="https://aistudio.google.com/apikey" target="_blank">Google AI Studio → API Keys</a></li>
          <li>Click <strong>"Create API Key"</strong></li>
          <li>Copy the key and paste it below</li>
        </ol>
      </div>
      <div class="input-group">
        <label class="input-label">Google API Key</label>
        <div class="input-row">
          <input class="input-field" id="geminiKey" type="password" placeholder="AIzaSy...">
          <button class="btn btn-validate" id="btnValidateGemini" onclick="validateGemini()">Validate</button>
        </div>
        <div class="feedback" id="geminiResult"></div>
      </div>
      <div class="btn-row">
        <button class="btn btn-back" onclick="goToStep(0)">← Back</button>
        <button class="btn btn-next" id="btnNext1" disabled onclick="goToStep(2)">Next →</button>
      </div>
    </div>

    <!-- ── Step 2: Telegram Bot ── -->
    <div class="card page" id="page-2">
      <h2 class="card-title">Telegram Bot Token</h2>
      <p class="card-desc">
        INDRA lives inside Telegram. You'll create a bot via BotFather.
      </p>
      <div class="instructions">
        <ol>
          <li>Open Telegram and search for <a href="https://t.me/BotFather" target="_blank">@BotFather</a></li>
          <li>Send the command <strong>/newbot</strong></li>
          <li>Choose a name (e.g., "INDRA") and a username (e.g., "my_indra_bot")</li>
          <li>BotFather will reply with your bot token — copy it below</li>
        </ol>
      </div>
      <div class="input-group">
        <label class="input-label">Bot Token</label>
        <div class="input-row">
          <input class="input-field" id="telegramToken" type="password" placeholder="123456789:AABBCCDD...">
          <button class="btn btn-validate" id="btnValidateTelegram" onclick="validateTelegram()">Validate</button>
        </div>
        <div class="feedback" id="telegramResult"></div>
      </div>
      <div class="btn-row">
        <button class="btn btn-back" onclick="goToStep(1)">← Back</button>
        <button class="btn btn-next" id="btnNext2" disabled onclick="goToStep(3)">Next →</button>
      </div>
    </div>

    <!-- ── Step 3: Chat ID ── -->
    <div class="card page" id="page-3">
      <h2 class="card-title">Telegram Chat ID</h2>
      <p class="card-desc">
        This restricts who can talk to INDRA. Only your chat ID will be allowed.
      </p>
      <div class="instructions">
        <ol>
          <li>Open Telegram and search for <a href="https://t.me/userinfobot" target="_blank">@userinfobot</a></li>
          <li>Send it any message — it will reply with your <strong>Chat ID</strong> (a number)</li>
          <li>Paste that number below</li>
        </ol>
        <p style="margin-top:8px;"><strong>Multiple users?</strong> Separate IDs with commas: <code style="color:var(--gold);">123,456,789</code></p>
      </div>
      <div class="input-group">
        <label class="input-label">Allowed Chat IDs</label>
        <div class="input-row">
          <input class="input-field" id="chatIds" type="text" placeholder="1234567890">
          <button class="btn btn-validate" id="btnValidateChat" onclick="validateChatId()">Validate</button>
        </div>
        <div class="feedback" id="chatIdResult"></div>
      </div>
      <div class="btn-row">
        <button class="btn btn-back" onclick="goToStep(2)">← Back</button>
        <button class="btn btn-next" id="btnNext3" disabled onclick="goToStep(4)">Next →</button>
      </div>
    </div>

    <!-- ── Step 4: Google Workspace (Optional) ── -->
    <div class="card page" id="page-4">
      <h2 class="card-title">Google Workspace</h2>
      <p class="card-desc">
        <em>Optional.</em> Enable INDRA to manage your Gmail, Calendar, and Drive.
        You can skip this and add it later.
      </p>
      <div class="instructions">
        <ol>
          <li>Go to <a href="https://console.cloud.google.com/apis/credentials" target="_blank">Google Cloud Console → Credentials</a></li>
          <li>Create an <strong>OAuth 2.0 Client ID</strong> (Desktop App type)</li>
          <li>Download the <code style="color:var(--gold);">credentials.json</code> file</li>
          <li>Place it in the INDRA project root folder</li>
          <li>After setup, run: <code style="color:var(--gold);">uv run python google_auth_helper.py</code></li>
        </ol>
      </div>
      <p class="card-desc" style="font-size:13px; color:var(--text-dim); margin-bottom: 0;">
        This step requires a Google Cloud project. If you're not sure, skip it — INDRA works
        perfectly for general chat, coding help, and data analysis without it.
      </p>
      <div class="btn-row">
        <button class="btn btn-back" onclick="goToStep(3)">← Back</button>
        <div>
          <span class="skip-link" onclick="goToStep(5)" style="margin-right:16px;">Skip for now</span>
          <button class="btn btn-next" onclick="goToStep(5)">Next →</button>
        </div>
      </div>
    </div>

    <!-- ── Step 5: Complete ── -->
    <div class="card page" id="page-5">
      <div style="text-align:center;">
        <div class="completion-icon">⚡</div>
        <h2 class="card-title" style="font-size:28px;">INDRA is Ready</h2>
        <p class="card-desc">Your configuration has been saved. The thunderbolt is forged.</p>
      </div>
      <div class="config-summary">
        <h4>Configuration Summary</h4>
        <div class="config-row">
          <span class="config-key">Google API Key</span>
          <span class="config-val" id="sumGemini">—</span>
        </div>
        <div class="config-row">
          <span class="config-key">Telegram Bot</span>
          <span class="config-val" id="sumTelegram">—</span>
        </div>
        <div class="config-row">
          <span class="config-key">Chat IDs</span>
          <span class="config-val" id="sumChatIds">—</span>
        </div>
        <div class="config-row">
          <span class="config-key">Google Workspace</span>
          <span class="config-val skipped" id="sumWorkspace">Skipped</span>
        </div>
      </div>
      <p class="card-desc" style="text-align:center; margin-bottom:8px;">Start INDRA with:</p>
      <div class="cmd-block">
        <span>uv run python app.py</span>
        <button class="copy-btn" onclick="copyCmd()">Copy</button>
      </div>
      <p class="card-desc" style="text-align:center; font-size:12px; color:var(--text-dim);">
        Then open Telegram and message your bot. INDRA will respond. ⚡
      </p>
    </div>
  </main>
</div>

<script>
  // ═══ State ═══
  const state = {
    currentStep: 0,
    validated: { gemini: false, telegram: false, chatId: false },
    values: { gemini: '', telegram: '', chatId: '', botName: '' },
  };

  // ═══ Navigation ═══
  function goToStep(n) {
    // Don't navigate forward past validation gates
    if (n === 2 && !state.validated.gemini)  return;
    if (n === 3 && !state.validated.telegram) return;
    if (n === 4 && !state.validated.chatId)   return;

    // If going to completion, save config
    if (n === 5) saveConfig();

    state.currentStep = n;
    // Update pages
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(`page-${n}`).classList.add('active');

    // Update sidebar
    document.querySelectorAll('.steps li').forEach(li => {
      const s = parseInt(li.dataset.step);
      li.classList.remove('active', 'completed');
      if (s === n) li.classList.add('active');
      else if (s < n) li.classList.add('completed');
    });

    // Update completed dots
    document.querySelectorAll('.steps li.completed .step-dot').forEach(dot => {
      dot.textContent = '✓';
    });
    document.querySelectorAll('.steps li:not(.completed) .step-dot').forEach(dot => {
      const idx = parseInt(dot.parentElement.dataset.step) + 1;
      if (dot.parentElement.dataset.step === '5') dot.textContent = '✦';
      else dot.textContent = idx;
    });
  }

  // ═══ Validation ═══
  async function validateGemini() {
    const key = document.getElementById('geminiKey').value.trim();
    if (!key) return;
    const btn = document.getElementById('btnValidateGemini');
    const fb = document.getElementById('geminiResult');
    const field = document.getElementById('geminiKey');

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>Checking...';

    try {
      const resp = await fetch('/api/validate/gemini', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({key})
      });
      const data = await resp.json();
      fb.className = 'feedback ' + (data.valid ? 'success' : 'error');
      fb.textContent = data.message;
      field.className = 'input-field ' + (data.valid ? 'valid' : 'invalid');
      state.validated.gemini = data.valid;
      if (data.valid) state.values.gemini = key;
      document.getElementById('btnNext1').disabled = !data.valid;
    } catch (e) {
      fb.className = 'feedback error';
      fb.textContent = 'Network error — check your connection.';
    }
    btn.disabled = false;
    btn.textContent = 'Validate';
  }

  async function validateTelegram() {
    const key = document.getElementById('telegramToken').value.trim();
    if (!key) return;
    const btn = document.getElementById('btnValidateTelegram');
    const fb = document.getElementById('telegramResult');
    const field = document.getElementById('telegramToken');

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>Checking...';

    try {
      const resp = await fetch('/api/validate/telegram', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({key})
      });
      const data = await resp.json();
      fb.className = 'feedback ' + (data.valid ? 'success' : 'error');
      fb.textContent = data.message;
      field.className = 'input-field ' + (data.valid ? 'valid' : 'invalid');
      state.validated.telegram = data.valid;
      if (data.valid) {
        state.values.telegram = key;
        state.values.botName = data.bot_name || '';
      }
      document.getElementById('btnNext2').disabled = !data.valid;
    } catch (e) {
      fb.className = 'feedback error';
      fb.textContent = 'Network error — check your connection.';
    }
    btn.disabled = false;
    btn.textContent = 'Validate';
  }

  async function validateChatId() {
    const key = document.getElementById('chatIds').value.trim();
    if (!key) return;
    const btn = document.getElementById('btnValidateChat');
    const fb = document.getElementById('chatIdResult');
    const field = document.getElementById('chatIds');

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>Checking...';

    try {
      const resp = await fetch('/api/validate/chat-id', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({key})
      });
      const data = await resp.json();
      fb.className = 'feedback ' + (data.valid ? 'success' : 'error');
      fb.textContent = data.message;
      field.className = 'input-field ' + (data.valid ? 'valid' : 'invalid');
      state.validated.chatId = data.valid;
      if (data.valid) state.values.chatId = key;
      document.getElementById('btnNext3').disabled = !data.valid;
    } catch (e) {
      fb.className = 'feedback error';
      fb.textContent = 'Network error — check your connection.';
    }
    btn.disabled = false;
    btn.textContent = 'Validate';
  }

  // ═══ Save Config ═══
  async function saveConfig() {
    // Update completion summary
    const geminiMask = state.values.gemini ? '••••' + state.values.gemini.slice(-6) : '—';
    document.getElementById('sumGemini').textContent = geminiMask + ' ✅';
    document.getElementById('sumTelegram').textContent = state.values.botName
      ? `${state.values.botName} ✅` : '✅';
    document.getElementById('sumChatIds').textContent = state.values.chatId + ' ✅';

    // POST to backend
    try {
      await fetch('/api/complete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          google_api_key: state.values.gemini,
          telegram_bot_token: state.values.telegram,
          allowed_chat_ids: state.values.chatId,
        })
      });
    } catch (e) {
      console.error('Failed to save config:', e);
    }
  }

  function copyCmd() {
    navigator.clipboard.writeText('uv run python app.py');
    const btn = event.target;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = 'Copy', 1500);
  }

  // ═══ Enter key support ═══
  document.addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    const step = state.currentStep;
    if (step === 1) validateGemini();
    else if (step === 2) validateTelegram();
    else if (step === 3) validateChatId();
  });
</script>

</body>
</html>
"""


# ══════════════════════════════════════════════════════════════
# 4. CLI fallback
# ══════════════════════════════════════════════════════════════

async def run_cli():
    """Interactive CLI-only onboarding for headless environments."""
    print("\n" + "═" * 56)
    print("  ⚡  INDRA — Setup Wizard (CLI Mode)")
    print("═" * 56)
    print("\nThis wizard will configure your .env file step by step.\n")

    config = {}

    # Step 1: Gemini API Key
    print("── Step 1/4: Google API Key ──────────────────────────")
    print("  Get one at: https://aistudio.google.com/apikey\n")
    while True:
        key = input("  Paste your Google API Key: ").strip()
        if not key:
            print("  ⚠️  Key cannot be empty.\n")
            continue
        result = await validate_gemini_key(key)
        if result["valid"]:
            print(f"  {result['message']}\n")
            config["google_api_key"] = key
            break
        else:
            print(f"  ❌ {result['message']} Try again.\n")

    # Step 2: Telegram Bot Token
    print("── Step 2/4: Telegram Bot Token ─────────────────────")
    print("  Create a bot: https://t.me/BotFather → /newbot\n")
    while True:
        token = input("  Paste your Bot Token: ").strip()
        if not token:
            print("  ⚠️  Token cannot be empty.\n")
            continue
        result = await validate_telegram_token(token)
        if result["valid"]:
            print(f"  {result['message']}\n")
            config["telegram_bot_token"] = token
            break
        else:
            print(f"  ❌ {result['message']} Try again.\n")

    # Step 3: Chat IDs
    print("── Step 3/4: Telegram Chat ID ───────────────────────")
    print("  Find yours: message @userinfobot on Telegram\n")
    while True:
        ids = input("  Enter your Chat ID(s): ").strip()
        result = validate_chat_ids(ids)
        if result["valid"]:
            print(f"  {result['message']}\n")
            config["allowed_chat_ids"] = ids
            break
        else:
            print(f"  ❌ {result['message']} Try again.\n")

    # Step 4: Google Workspace
    print("── Step 4/4: Google Workspace (Optional) ────────────")
    ws = input("  Set up Gmail/Calendar? (y/N): ").strip().lower()
    if ws == "y":
        print("  → Place credentials.json in the project root")
        print("  → Then run: uv run python google_auth_helper.py\n")
    else:
        print("  → Skipped. You can set this up later.\n")

    # Write .env
    env_path = write_env_file(config)
    print("═" * 56)
    print(f"  ✅ Configuration saved to {env_path}")
    print(f"\n  Start INDRA with:  uv run python app.py")
    print("═" * 56 + "\n")


# ══════════════════════════════════════════════════════════════
# 5. Entrypoint
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if "--cli" in sys.argv:
        asyncio.run(run_cli())
    else:
        import uvicorn

        print("\n  ⚡ INDRA Setup Wizard")
        print("  Opening http://localhost:8888 in your browser...\n")

        # Open browser after a short delay (server needs to start)
        import threading
        threading.Timer(1.5, lambda: webbrowser.open("http://localhost:8888")).start()

        uvicorn.run(app, host="0.0.0.0", port=8888, log_level="warning")
