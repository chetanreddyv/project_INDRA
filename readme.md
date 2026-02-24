# ⚡ INDRA — Intelligent Network for Data, Reasoning, and Action

> *"The thunderbolt is not just a weapon — it is a force that restores order, breaks stagnation, and brings the rain that makes things grow."*

**INDRA** is a production-grade agentic personal AI assistant accessible via Telegram. Built with FastAPI, LangGraph, and Pydantic AI (Gemini), it features intelligent skill routing, human-in-the-loop approval for write actions, persistent long-term memory, and a composable architecture designed for extensibility.

---

## Table of Contents

- [Why INDRA?](#why-indra)
- [Architecture Overview](#architecture-overview)
- [System Flow](#system-flow)
- [Component Deep Dive](#component-deep-dive)
  - [1. FastAPI Application Layer](#1-fastapi-application-layer-apppy)
  - [2. Telegram Client](#2-telegram-client-telegrampy)
  - [3. LangGraph Orchestration](#3-langgraph-orchestration-graphpy)
  - [4. Router Node](#4-router-node-nodesrouterpy)
  - [5. Agent Node](#5-agent-node-nodesagentpy)
  - [6. Human Approval Node](#6-human-approval-node-nodesapprovalpy)
  - [7. Synthesizer Node](#7-synthesizer-node-nodessynthesizerpy)
  - [8. Memory System](#8-memory-system-memorypy)
  - [9. Identity & Skills](#9-identity--skills)
  - [10. Configuration](#10-configuration)
- [Design Decisions](#design-decisions)
- [Directory Structure](#directory-structure)
- [Quick Start](#quick-start)
- [Environment Variables](#environment-variables)
- [Deployment](#deployment)
- [Roadmap](#roadmap)

---

## Why INDRA?

Most AI assistants are stateless chat wrappers. INDRA is different:

| Feature | Generic Bot | INDRA |
|---|---|---|
| Intent routing | ❌ Fixed commands | ✅ LLM-powered skill classification |
| Write safety | ❌ Executes blindly | ✅ Human-in-the-Loop approval |
| Memory | ❌ No context | ✅ Persistent long-term memory |
| Identity | ❌ Generic | ✅ Rich persona with operating principles |
| Self-correction | ❌ Fails silently | ✅ Retries with error context (up to 3x) |
| Architecture | ❌ Monolith | ✅ Modular LangGraph DAG |

---

## Architecture Overview

INDRA is built as a **four-node LangGraph StateGraph** orchestrated by a FastAPI server and connected to the user via Telegram.

```
┌──────────────────────────────────────────────────────────────┐
│                        TELEGRAM                              │
│                    (User Interface)                          │
└──────────────┬──────────────────────────────┬────────────────┘
               │  Messages                    │  Callbacks
               ▼                              ▼
┌──────────────────────────────────────────────────────────────┐
│                     FASTAPI (app.py)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │   Polling /  │  │   Security   │  │   Background     │    │
│  │   Webhooks   │  │   Layer      │  │   MemoryGate     │    │
│  └──────┬───────┘  └──────────────┘  └──────────────────┘    │
│         │                                                     │
│         ▼                                                     │
│  ┌────────────────────────────────────────────────────────┐   │
│  │              LANGGRAPH STATE MACHINE                   │   │
│  │                                                        │   │
│  │   START ──▶ Router ──▶ Agent ──▶ Synthesizer ──▶ END   │   │
│  │                          │                             │   │
│  │                          ├──▶ Human Approval ──┐       │   │
│  │                          │                     ▼       │   │
│  │                          ◀──── (retry/edit) ◀──┘       │   │
│  │                                                        │   │
│  └────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────-──┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│                    GEMINI 2.5 FLASH                          │
│              (via Pydantic AI + Google GLA)                  │
└──────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Web Framework** | FastAPI | HTTP server, webhook handling, lifespan management |
| **Orchestration** | LangGraph | Stateful DAG with checkpointing and interrupts |
| **LLM Framework** | Pydantic AI | Structured outputs, type-safe agent responses |
| **LLM Provider** | Gemini 2.5 Flash | Fast inference with structured output support |
| **Messaging** | Telegram Bot API | User-facing interface with inline keyboards |
| **State Persistence** | MemorySaver / SQLite | Graph state checkpointing |
| **Memory Extraction** | Gemini 2.5 Flash | Biographical fact extraction |
| **Semantic Vectors** | FastEmbed | Local BGE embeddings |
| **Document Store** | SQLite WAL | Fast history and text storage |
| **Vector DB** | Zvec | In-process semantic retrieval |
| **Configuration** | Pydantic Settings | Type-safe environment variable management |
| **Deployment** | Docker + Docker Compose | Containerized local and production deployment |

---

## System Flow

### Happy Path (Read-only query)

```
1. User sends "What design patterns should I use for a microservice?"
2. Telegram delivers update via polling (local) or webhook (production)
3. FastAPI validates chat_id against allowlist
4. LangGraph starts: START → Router
5. Router (Gemini Flash) classifies intent → "code_assistant" (confidence: 0.92)
6. Agent loads identity.md + memory context + skills/code_assistant.md
7. Agent calls Gemini 2.5 Flash with full system prompt
8. Pydantic AI enforces AgentResponse schema (HTML-formatted output)
9. Synthesizer sanitizes response for Telegram
10. Bot sends rich HTML response back to user
11. MemoryGate accesses SQLite thread history + FastEmbed vectors
12. MemoryGate extracts facts, stores texts in SQLite, vectors in Zvec
```

### Write Path (Human-in-the-Loop)

```
1. User sends "Send an email to John about the meeting tomorrow"
2. Router classifies → "google_workspace" (confidence: 0.95)
3. Agent detects write action ("send_email") via keyword heuristics
4. Graph routes to Human Approval node
5. Approval node calls interrupt() → LangGraph pauses, saves state
6. Telegram sends inline keyboard: [✅ Approve] [❌ Reject] [✏️ Edit]
7. User clicks "Approve"
8. Callback handler resumes graph with Command(resume="approve")
9. Approval node executes action, returns response
10. Synthesizer → Telegram → User sees confirmation
```

### Self-Correction Path

```
1. Agent encounters a tool failure or API error
2. tool_failure_count increments (1/3)
3. Conditional edge routes back to Agent node for retry
4. If count reaches 3, routes to Synthesizer with fallback error message
```

---

## Component Deep Dive

### 1. FastAPI Application Layer (`app.py`)

The central orchestrator. Manages the full application lifecycle and bridges Telegram with LangGraph.

**Key responsibilities:**
- **Lifespan management** — Initializes Telegram client, MemorySaver checkpointer, and compiles the LangGraph at startup. Cleans up on shutdown.
- **Dual ingestion modes** — Supports both long-polling (local dev, no public URL needed) and webhooks (production with HTTPS).
- **Security** — Validates `X-Telegram-Bot-Api-Secret-Token` headers and enforces a chat ID allowlist.
- **Graph execution** — Streams events from `graph.astream()`, detects interrupts (HITL), and dispatches responses.
- **Background memory** — Fires `_run_memorygate()` as an async task after each response (non-blocking).

**Design decision — Polling vs. Webhooks:**
Telegram webhooks require a public HTTPS URL, which doesn't work on `localhost`. Instead of requiring ngrok or similar tunneling, INDRA implements a native polling loop (`_poll_telegram`) that long-polls the `getUpdates` API with a 30-second timeout. Messages are processed sequentially to avoid Gemini rate-limit bursts on the free tier.

**Design decision — Sequential processing:**
Early versions used `asyncio.create_task()` to process messages concurrently. This caused Gemini API rate-limit errors (429) when multiple queued messages fired simultaneously. Switching to `await _run_graph()` ensures one message completes before the next starts.

---

### 2. Telegram Client (`telegram.py`)

A lightweight async wrapper around the Telegram Bot API built on `httpx`.

**Key features:**
- **Message chunking** — Automatically splits messages exceeding Telegram's 4096-character limit.
- **HTML parse mode with fallback** — Uses `parse_mode="HTML"` by default. If Telegram returns a 400 Bad Request (malformed HTML), automatically retries without formatting to ensure message delivery.
- **Inline keyboard support** — Sends Approve / Reject / Edit buttons for HITL workflows.
- **Callback query handling** — Acknowledges button presses and edits the original message to show the user's decision.
- **Long-polling** — `get_updates()` uses a custom httpx timeout (`timeout + 10s`) to prevent the HTTP client from timing out before Telegram's long-poll completes.

**Design decision — HTML over Markdown:**
Telegram's legacy Markdown parser (`parse_mode="Markdown"`) is notoriously strict — unescaped `*`, `_`, `` ` ``, or `[` characters cause 400 errors. HTML (`parse_mode="HTML"`) is far more forgiving and pairs naturally with the Pydantic `AgentResponse` model which instructs the LLM to emit only valid Telegram HTML tags.

---

### 3. LangGraph Orchestration (`graph.py`)

Defines the `AgentState` TypedDict and wires all four nodes into a compiled `StateGraph`.

**State Schema:**
```python
class AgentState(TypedDict):
    chat_id: str                    # Telegram chat ID (= thread_id)
    user_input: str                 # Current user message
    skill_selected: Optional[str]   # Router's chosen skill
    routing_reasoning: Optional[str]# Router's explanation
    agent_response: Optional[str]   # Final response text
    pending_action: Optional[dict]  # Action awaiting HITL approval
    tool_failure_count: int         # Self-correction counter
    memory_context: Optional[str]   # Retrieved long-term context
```

**Graph topology:**
```
START → router → agent → (conditional)
                           ├→ human_approval → (conditional)
                           │                    ├→ agent (edit)
                           │                    └→ synthesizer
                           ├→ agent (retry, up to 3x)
                           └→ synthesizer → END
```

**Conditional edges:**
- `route_after_agent` — Checks `tool_failure_count` (≥3 → synthesizer), `_retry` flag (→ agent), `pending_action` (→ human_approval), or normal completion (→ synthesizer).
- `route_after_approval` — If user requested an edit, re-runs the agent. Otherwise, proceeds to synthesizer.

**Design decision — Compile-time graph vs. runtime decisions:**
The graph topology is fixed at compile time (edges are wired once). Runtime behavior is controlled entirely through conditional edge functions that inspect the state dict. This ensures deterministic, debuggable flows while still allowing dynamic branching.

---

### 4. Router Node (`nodes/router.py`)

A fast Gemini Flash call that classifies user intent into one of four skills.

**How it works:**
1. Takes the raw `user_input` from state
2. Calls a Pydantic AI agent with `output_type=RouterDecision`
3. Returns a structured response: `skill`, `confidence`, `reasoning`
4. If confidence < 0.5, falls back to `general_chat`
5. If the API call fails entirely, gracefully defaults to `general_chat`

**Available skills:**
| Skill | Handles |
|---|---|
| `general_chat` | Conversation, advice, knowledge questions |
| `google_workspace` | Email, calendar, meetings, Drive |
| `code_assistant` | Debugging, code gen, architecture review |
| `data_analyst` | SQL queries, data analysis |

**Design decision — Lazy initialization:**
The router agent is lazily initialized via `_get_router_agent()` to prevent import-time failures when `GOOGLE_API_KEY` isn't yet set (e.g., during test imports or module-level resolution before `load_dotenv()` runs).

---

### 5. Agent Node (`nodes/agent.py`)

The core execution engine. Loads dynamic prompts, calls Gemini, and detects write actions.

**System prompt construction (layered):**
```
┌──────────────────────────────────┐
│  1. identity.md                  │  ← Core persona (Indra)
├──────────────────────────────────┤
│  2. User Context (from memory)   │  ← Long-term preferences + history
├──────────────────────────────────┤
│  3. skills/{skill}.md            │  ← Skill-specific instructions
└──────────────────────────────────┘
```

**Structured output enforcement:**
```python
class AgentResponse(BaseModel):
    response: str = Field(
        description="MUST be formatted using ONLY valid Telegram HTML tags..."
    )
```

This Pydantic model is passed as `output_type` to the Pydantic AI agent, ensuring the LLM always returns valid, parseable HTML — eliminating the Telegram 400 errors caused by rogue Markdown characters.

**Write action detection:**
Uses keyword heuristics to detect if the user's message matches known write actions (e.g., "send email", "create event") from `mcp_config.json`. If detected, sets `pending_action` in state, which triggers the HITL approval flow.

**Self-correction:**
On exception, increments `tool_failure_count` and sets `_retry: True`. The conditional edge in `graph.py` routes back to the agent node. After 3 failures, the graph gives up and returns a human-readable fallback error.

---

### 6. Human Approval Node (`nodes/approval.py`)

Implements LangGraph's `interrupt()` mechanism for safe mutating operations.

**Flow:**
1. Receives `pending_action` from agent state
2. Calls `interrupt()` with action details — LangGraph pauses and saves state
3. FastAPI sends Telegram inline keyboard buttons
4. User clicks a button → webhook/polling delivers callback
5. `Command(resume=decision)` resumes the graph at this node
6. Node processes the decision:
   - **Approve** → Executes the action, returns confirmation
   - **Reject** → Returns rejection message
   - **Edit** → Sets `_needs_rerun: True`, routes back to agent with edit instructions

**Design decision — Why interrupt() over polling:**
LangGraph's native `interrupt()` is purpose-built for this pattern. It saves the full graph state atomically, allows resumption at exactly the right point, and handles concurrent users cleanly through thread-scoped checkpoints.

---

### 7. Synthesizer Node (`nodes/synthesizer.py`)

Formats the agent's response for Telegram delivery.

**Responsibilities:**
- Sanitizes Markdown artifacts (triple backticks → single backtick for Telegram compatibility)
- Provides a fallback message ("I processed your request but have nothing to report") when `agent_response` is empty
- Ensures the response fits within Telegram's character limits

---

### 8. Memory System (`memory.py`)

A background "hippocampus" that learns from every conversation, backed by **SQLite** for blazing-fast storage and **Zvec + FastEmbed** for in-process semantic search.

**Architecture:**
```
Conversation → MemoryGate.process() → Gemini Extraction → ZvecMemoryStore
                                           │                   │
                                           ▼                   ▼
                                    ExtractedMemory     (FastEmbed VDB)
                                    - Preferences       - 384-dim BGE Vectors
                                    - Facts             (SQLite Text Store)
                                    - Corrections       - Text / WAL History
```

**Three memory types:**
| Type | Example | Purpose |
|---|---|---|
| **Preferences** | "Prefers formal emails" | Style and behavior rules |
| **Facts** | "Works on agentic AI systems" | Biographical and project context |
| **Corrections** | "Don't suggest Python 2" | Explicit user corrections |

**Storage:**
- `data/agent_session.db` — SQLite WAL for high-concurrency thread history and memory text storage.
- `data/zvec_index/` — Zvec highly-optimized, local vector index.

**Design decisions:**
- **In-process Vector DB (Zvec)** — Chosen over network databases like Pinecone. Zvec provides sub-millisecond local semantic search without infra overhead.
- **Local Embeddings (FastEmbed)** — We swapped out Gemini APIs for `BAAI/bge-small-en-v1.5` running locally via FastEmbed. This cuts API latency to zero and avoids rate limits entirely while indexing memories.
- **SQLite WAL** — Write-Ahead Logging allows background memory extraction to write to the DB without locking the read queries from the main LangGraph router.
- **Background processing** — Memory extraction runs via `asyncio.to_thread` and background tasks after the response is sent, so it never blocks the user.

---

### 9. Identity & Skills

**Identity (`identity.md`):**
The foundational persona prompt. Defines INDRA's name, acronym meaning, aura (Clarity, Power, Sovereignty), core traits, operating principles, and voice/tone. This is always the first section in the system prompt, establishing the agent's personality before any skill-specific instructions.

**Skills (`skills/*.md`):**
Interchangeable instruction sets loaded dynamically based on the router's classification:

| File | Focus |
|---|---|
| `general_chat.md` | Warm, concise conversationalist |
| `google_workspace.md` | Email drafting, calendar management, Google Drive |
| `code_assistant.md` | Senior Staff Engineer persona for debugging and architecture |
| `data_analyst.md` | SQL-first data analysis with safety rules for database operations |

**Design decision — Markdown over code:**
Skills are defined as plain Markdown files rather than Python classes for several reasons:
1. **Non-engineers can edit them** — No Python knowledge required to modify behavior
2. **Hot-reloadable** — Files are read at runtime, no server restart needed
3. **Version-controllable** — Easy to diff, review, and roll back
4. **Composable** — Identity + Memory + Skill are concatenated with `---` separators

---

### 10. Configuration

**`config/settings.py`** — Pydantic Settings with type validation:
- Loads from `.env` file automatically
- Validates required fields (`telegram_bot_token`, `google_api_key`) at startup
- Parses `ALLOWED_CHAT_IDS` comma-separated string into `list[int]` via a `@property`
- Ignores extra env vars (`extra = "ignore"`)

**`config/mcp_config.json`** — Declares available MCP tools per skill and which are "write actions" requiring human approval. Currently defines the `google_workspace` skill's tool surface.

---

## Design Decisions

### Why LangGraph over raw chains?
LangGraph provides **stateful execution with checkpointing**, **conditional routing**, and native **interrupt/resume** for HITL — all essential for a production assistant. A simple LangChain chain cannot pause mid-execution, wait for human input via Telegram, and resume.

### Why Pydantic AI over raw Gemini SDK?
Pydantic AI provides **structured outputs** (`output_type=AgentResponse`), eliminating the need to parse free-text LLM responses. It also standardizes the agent interface, making it trivial to swap between LLM providers later (OpenAI, Anthropic, etc.).

### Why polling over webhooks for local dev?
Telegram webhooks require a publicly accessible HTTPS URL. Rather than depending on ngrok or similar tunneling tools, INDRA implements native long-polling in the `TelegramClient`, making local development zero-config.

### Why MemorySaver over SQLite for checkpointing?
`AsyncSqliteSaver` caused disk I/O errors under concurrent async access. `MemorySaver` eliminates this entirely — state lives in-memory for the lifetime of the process. For production with persistence across restarts, the code is designed to swap back to SQLite or PostgreSQL via a single line change.

### Why HTML over Markdown for Telegram?
Telegram's legacy `parse_mode="Markdown"` rejects messages with unescaped special characters (`*`, `_`, `` ` ``), which LLMs frequently generate. HTML is far more tolerant and pairs naturally with the Pydantic `AgentResponse` model that instructs the LLM to emit only valid HTML tags.

---

## Directory Structure

```
personal-assistant/
├── app.py                     # FastAPI server, polling, graph execution
├── graph.py                   # LangGraph StateGraph definition
├── telegram.py                # Telegram Bot API client
├── memory.py                  # MemoryGate: extraction + persistence
├── identity.md                # INDRA persona definition
│
├── nodes/                     # LangGraph node implementations
│   ├── router.py              # Intent classifier (Gemini Flash)
│   ├── agent.py               # Pydantic AI executor
│   ├── approval.py            # Human-in-the-Loop interrupt node
│   └── synthesizer.py         # Response formatter
│
├── skills/                    # Dynamic skill prompts (Markdown)
│   ├── general_chat.md
│   ├── google_workspace.md
│   ├── code_assistant.md
│   └── data_analyst.md
│
├── config/
│   ├── settings.py            # Pydantic Settings (env validation)
│   └── mcp_config.json        # MCP tool definitions & write actions
│
├── mcp_servers/
│   └── google_workspace.py    # Google Workspace MCP server
│
├── data/                      # Runtime data (gitignored)
│   ├── agent_session.db       # SQLite WAL memory text db
│   └── zvec_index/            # Zvec vector embeddings
│
├── google_auth_helper.py      # Google OAuth2 token management
├── pyproject.toml             # Dependencies & project metadata
├── Dockerfile                 # Production container
├── docker-compose.yml         # Local Docker orchestration
├── .env.example               # Environment variable template
└── .gitignore
```

---

## Quick Start

### Prerequisites
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A Google AI Studio API key from [ai.google.dev](https://ai.google.dev)

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/your-username/Personal_Assistant.git
cd Personal_Assistant

# 2. Install dependencies
uv sync

# 3. Run the setup wizard (recommended for first-time setup)
uv run python onboarding.py
```

The setup wizard opens a **localhost web UI** that walks you through every configuration step — obtaining API keys, connecting Telegram, and validating everything works. No manual `.env` editing needed.

> **Headless / SSH?** Use CLI mode: `uv run python onboarding.py --cli`

<details>
<summary><strong>Manual setup (advanced)</strong></summary>

```bash
# Copy and edit the env template
cp .env.example .env
# Edit .env with your TELEGRAM_BOT_TOKEN, GOOGLE_API_KEY, and ALLOWED_CHAT_IDS
```
</details>

```bash
# 4. Run the assistant
uv run python app.py
```

### Verify
1. Open Telegram and message your bot
2. You should see logs like:
   ```
   📩 Message from 123456789: Hello
   ✅ Router → general_chat (confidence: 0.9)
   ✅ Agent response generated (142 chars)
   💬 Sent response to 123456789
   ```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | Bot token from @BotFather |
| `GOOGLE_API_KEY` | ✅ | Google AI Studio API key |
| `ALLOWED_CHAT_IDS` | ✅ | Comma-separated Telegram chat IDs |
| `TELEGRAM_SECRET_TOKEN` | ❌ | Webhook secret verification |
| `LANGCHAIN_TRACING_V2` | ❌ | Enable LangSmith tracing |
| `LANGSMITH_API_KEY` | ❌ | LangSmith API key |
| `LOGFIRE_TOKEN` | ❌ | Logfire observability token |

---

## Deployment

### Docker

```bash
docker compose up --build
```

### Production (Azure Container Apps, etc.)

1. Switch from polling to webhook mode in `app.py`
2. Set `TELEGRAM_SECRET_TOKEN` for webhook verification
3. Register your webhook URL with Telegram:
   ```bash
   curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://your-domain.com/webhook", "secret_token": "your-secret"}'
   ```
4. Deploy the Docker container with `GOOGLE_API_KEY` and `TELEGRAM_BOT_TOKEN` as secrets

---

## Roadmap

- [ ] **MCP Tool Integration** — Wire real Google Workspace tools (Gmail, Calendar, Drive) into the agent node via FastMCP
- [ ] **Observability** — LangSmith tracing, Logfire/OpenTelemetry metrics, token usage dashboards
- [x] **Vector Memory** — Upgraded from JSON to Zvec + FastEmbed for local semantic memory retrieval
- [ ] **Multi-turn Context** — Pass conversation history through the graph for multi-turn reasoning
- [ ] **Cost Controls** — Token budgets via Pydantic AI `UsageLimits` and LiteLLM proxy
- [ ] **Integration Tests** — Comprehensive test suite with mocked Telegram and Gemini
- [ ] **Streaming Responses** — Stream agent output token-by-token to Telegram for faster perceived latency
- [ ] **Additional Skills** — Jira, Slack, Notion, financial analysis

---

## License

MIT

---

<p align="center">
  Built with ⚡ by <a href="https://github.com/chetanv-code">Chetan Valluru</a>
</p>


to be added in readme.md
- secure tool execution approval, human-in-the-loop approval for write actions by stripping away llms the power of deciding whether human approval is required or not. and literally write actions only execute after human approval due to deterministic nature of the code.