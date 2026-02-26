"""
app.py — FastAPI application.

Handles Telegram webhooks, security validation, and bridges
the messaging layer with the LangGraph agentic loop.
"""

import asyncio
import logging
from dotenv import load_dotenv

# Load .env into os.environ BEFORE any other imports that read env vars
load_dotenv()
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from langgraph.types import Command

from config.settings import settings
from interfaces.telegram import TelegramClient
from nodes.graph import build_graph, checkpointer_context
from core.lane_manager import lane_manager
from core.messaging import StandardMessage, ResumeMessage

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ── Globals (initialized at startup) ────────────────────────
telegram_client: TelegramClient = None
graph = None
checkpointer = None


# ==========================================================
# 1. Lifespan (startup / shutdown)
# ==========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_client, graph, checkpointer

    logger.info("🚀 Starting Personal Assistant...")

    # ── Onboarding check ─────────────────────────────────────
    if settings.needs_onboarding:
        logger.warning("  ⚠️  INDRA is not configured yet! Run the setup wizard:")
        logger.warning("    uv run python onboarding.py")
        logger.warning("  Or use CLI mode: uv run python onboarding.py --cli")
        # Yield to keep FastAPI alive but don't initialize anything
        yield
        return

    # Initialize Telegram client
    telegram_client = TelegramClient(settings.telegram_bot_token)
    logger.info("✅ Telegram client initialized")

    # Initialize MemoryGate
    try:
        from memory import memorygate
        await memorygate.initialize()
        logger.info("✅ MemoryGate initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize MemoryGate: {e}")

    logger.info(f"✅ Allowed chat IDs: {settings.allowed_chat_id_list}")

    # Open the SQLite checkpointer for the full lifespan of the app
    async with checkpointer_context() as checkpointer:
        # Build and compile the LangGraph with the persistent checkpointer
        graph = build_graph(checkpointer=checkpointer)
        logger.info("✅ LangGraph compiled with SQLite checkpointer")

        # Start Cron Manager
        from core.cron_manager import cron_manager
        await cron_manager.start()
        logger.info("✅ Cron scheduler started")

        # Delete any existing webhook and start polling for local dev
        await telegram_client.delete_webhook()
        logger.info("✅ Webhook cleared — using polling mode")

        # Start polling in background
        polling_task = asyncio.create_task(_poll_telegram())
        logger.info("🟢 Personal Assistant is ready! (polling mode)")

        yield

        # Shutdown
        logger.info("🔴 Shutting down...")
        await cron_manager.stop()
        polling_task.cancel()
        await telegram_client.close()
        try:
            from memory import memorygate
            await memorygate.store.close()
            logger.info("✅ Zvec memory stores flushed and closed")
        except Exception as e:
            logger.error(f"❌ Error closing memory stores: {e}")
            
    # SQLite connection is closed automatically when the async with block exits
    logger.info("✅ SQLite checkpointer closed")



# ==========================================================
# 2. Telegram Polling (for local dev)
# ==========================================================

async def _poll_telegram():
    """
    Background task: long-poll Telegram for updates.
    This replaces webhooks for local development.
    """
    offset = 0
    logger.info("📡 Polling Telegram for updates...")

    while True:
        try:
            updates = await telegram_client.get_updates(offset=offset, timeout=30)
            for update in updates:
                offset = update["update_id"] + 1

                # Handle callback queries (button clicks)
                if "callback_query" in update:
                    await _handle_callback_query(update["callback_query"])
                    continue

                # Handle text messages
                message = update.get("message", {})
                chat_id = message.get("chat", {}).get("id")
                text = message.get("text", "")

                if not chat_id or not text:
                    continue

                # Check chat_id allowlist
                allowed = settings.allowed_chat_id_list
                if allowed and chat_id not in allowed:
                    logger.warning(f"⚠️ Ignored message from unauthorized chat_id: {chat_id}")
                    continue

                logger.info(f"📩 Message from {chat_id}: {text[:100]}")

                # Show typing and run graph SEQUENTIALLY via LaneManager
                await telegram_client.send_typing_action(chat_id)

                async def reply(response_text: str):
                    await telegram_client.send_message(chat_id=chat_id, text=response_text)

                async def approve(action_summary: str, thread_id: str):
                    await telegram_client.send_approval_buttons(chat_id=chat_id, action_summary=action_summary, thread_id=thread_id)

                msg = StandardMessage(
                    platform="telegram",
                    user_id=str(chat_id),
                    text=text,
                    reply_func=reply,
                    approval_func=approve
                )
                await lane_manager.submit(str(chat_id), agent_daemon, msg)

        except asyncio.CancelledError:
            logger.info("📡 Polling stopped")
            break
        except Exception as e:
            logger.error(f"Polling error: {e}")
            await asyncio.sleep(2)


# ==========================================================
# 3. FastAPI App
# ==========================================================

app = FastAPI(
    title="Personal AI Assistant",
    description="Agentic personal assistant via Telegram & Web",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount web chat UI
from interfaces.web_chat import router as chat_router
app.include_router(chat_router)


# ==========================================================
# 3. Security Dependencies
# ==========================================================

async def verify_telegram_secret(request: Request):
    """Validate the X-Telegram-Bot-Api-Secret-Token header."""
    if not settings.telegram_secret_token:
        return  # No secret configured, skip validation

    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret != settings.telegram_secret_token:
        logger.warning(f"⚠️ Rejected request: invalid secret token")
        raise HTTPException(status_code=401, detail="Invalid secret token")


def verify_chat_id(chat_id: int):
    """Ensure the chat_id is in the allowlist."""
    allowed = settings.allowed_chat_id_list
    if allowed and chat_id not in allowed:
        logger.warning(f"⚠️ Rejected request from unauthorized chat_id: {chat_id}")
        raise HTTPException(status_code=403, detail="Unauthorized chat")


# ==========================================================
# 4. Endpoints
# ==========================================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "graph_ready": graph is not None,
        "telegram_ready": telegram_client is not None,
    }


@app.post("/webhook", dependencies=[Depends(verify_telegram_secret)])
async def webhook(request: Request):
    """
    Receive Telegram webhook updates.
    
    Handles two types:
    1. message — User sent a text message → run the graph
    2. callback_query — User clicked an inline button → resume the graph
    """
    body = await request.json()
    logger.info(f"📩 Webhook received")

    # ── Handle callback queries (button clicks) ──────────────
    if "callback_query" in body:
        return await _handle_callback_query(body["callback_query"])

    # ── Handle text messages ─────────────────────────────────
    if "message" in body:
        message = body["message"]
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")

        if not chat_id or not text:
            return {"status": "ignored", "reason": "no chat_id or text"}

        verify_chat_id(chat_id)

        # Show typing indicator
        await telegram_client.send_typing_action(chat_id)

        async def reply(response_text: str):
            await telegram_client.send_message(chat_id=chat_id, text=response_text)

        async def approve(action_summary: str, thread_id: str):
            await telegram_client.send_approval_buttons(chat_id=chat_id, action_summary=action_summary, thread_id=thread_id)

        msg = StandardMessage(
            platform="telegram",
            user_id=str(chat_id),
            text=text,
            reply_func=reply,
            approval_func=approve
        )
        # Run the graph sequentially via LaneManager
        await lane_manager.submit(str(chat_id), agent_daemon, msg)

        return {"status": "processing"}

    return {"status": "ignored", "reason": "unhandled update type"}


# ==========================================================
# 5. Graph Execution
# ==========================================================

async def agent_daemon(msg: StandardMessage) -> dict:
    """
    Unified LangGraph runner. Processes the message and returns a dict with the result.
    If callbacks are provided in msg, they are called immediately.
    """
    config = {"configurable": {"thread_id": msg.user_id}}

    try:
        # Stream through the graph
        async for event in graph.astream(
            {
                "chat_id": msg.user_id,
                "user_input": msg.text,
                "tool_failure_count": 0,
            },
            config=config,
            stream_mode="updates",
        ):
            logger.debug(f"Graph event ({msg.platform}): {event}")

        # Check final state
        state = await graph.aget_state(config)

        if state.next:
            interrupted = state.tasks[0].interrupts[0].value
            tool_args = interrupted.get("tool_args", {})
            args_text = (
                "\n".join(f"  • *{k}*: `{v}`" for k, v in tool_args.items())
                if tool_args
                else ""
            )
            action_summary = (
                f"*Action:* `{interrupted.get('action', 'unknown')}`\n"
                f"*Skill:* `{interrupted.get('skill', 'unknown')}`\n\n"
                f"{interrupted.get('details', '')}"
                + (f"\n\n*Arguments:*\n{args_text}" if args_text else "")
            )
            
            if msg.approval_func:
                await msg.approval_func(action_summary, msg.user_id)
                logger.info(f"🔐 HITL: Sent approval request to {msg.platform} user {msg.user_id}")
            
            return {
                "approval_required": True,
                "action": interrupted.get("action", "unknown"),
                "details": interrupted.get("details", ""),
                "tool_args": interrupted.get("tool_args", {}),
            }
        else:
            response = state.values.get("agent_response", "Done!")
            
            if response is None:
                response = "Done!"

            if msg.reply_func and response.strip() != "HEARTBEAT_OK":
                await msg.reply_func(response)
                logger.info(f"💬 Sent response to {msg.platform} user {msg.user_id}")
            elif response.strip() == "HEARTBEAT_OK":
                logger.info(f"🔇 Suppressed HEARTBEAT_OK from {msg.platform} user {msg.user_id}")

            # Trigger memorygate in background
            import asyncio
            asyncio.create_task(_run_memorygate(msg.user_id, msg.text, response))
            
            return {"response": response}

    except Exception as e:
        logger.error(f"❌ Graph execution error ({msg.platform}): {e}", exc_info=True)
        error_text = f"❌ Sorry, I encountered an error:\n{str(e)[:500]}"
        if msg.reply_func:
            try:
                await msg.reply_func(error_text)
            except Exception:
                await msg.reply_func("❌ An error occurred.")
        return {"error": str(e)[:500]}


async def _handle_callback_query(callback_query: dict):
    """
    Handle inline keyboard button clicks (Approve/Reject/Edit).
    Resumes the paused LangGraph.
    """
    callback_id = callback_query.get("id")
    data = callback_query.get("data", "")
    chat_id = callback_query.get("message", {}).get("chat", {}).get("id")
    message_id = callback_query.get("message", {}).get("message_id")

    if not data or not chat_id:
        return {"status": "ignored"}

    # Parse callback data: "approve:thread_id", "reject:thread_id", "edit:thread_id"
    parts = data.split(":", 1)
    decision = parts[0]
    thread_id = parts[1] if len(parts) > 1 else str(chat_id)

    logger.info(f"🔘 Callback: {decision} from {chat_id} (thread: {thread_id})")

    # Acknowledge the button press immediately
    await telegram_client.answer_callback_query(
        callback_id, text=f"{'✅ Approved' if decision == 'approve' else '❌ Rejected' if decision == 'reject' else '✏️ Editing'}..."
    )

    # Update the original message to show the decision
    decision_text = {
        "approve": "✅ *Approved* — executing...",
        "reject": "❌ *Rejected*",
        "edit": "✏️ *Editing* — please send your modifications...",
    }.get(decision, "Unknown action")

    await telegram_client.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=decision_text,
    )

    if decision == "edit":
        # For edit, we wait for the user's next message (it'll come through /webhook)
        # We store a flag so the next message is treated as an edit instruction
        # For now, just inform the user
        await telegram_client.send_message(
            chat_id=chat_id,
            text="Please send me the changes you'd like to make.",
        )
        return {"status": "awaiting_edit"}

    async def reply(response_text: str):
        await telegram_client.send_message(chat_id=chat_id, text=response_text)

    msg = ResumeMessage(
        platform="telegram",
        user_id=thread_id,
        decision=decision,
        reply_func=reply
    )

    # Resume the graph sequentially via LaneManager
    await lane_manager.submit(
        thread_id, 
        resume_daemon, 
        msg
    )

    return {"status": "resumed"}


async def resume_daemon(msg: ResumeMessage) -> dict:
    """
    Unified LangGraph resumer.
    """
    config = {"configurable": {"thread_id": msg.user_id}}
    try:
        async for event in graph.astream(
            Command(resume=msg.decision),
            config=config,
            stream_mode="updates",
        ):
            logger.debug(f"Resume event ({msg.platform}): {event}")

        state = await graph.aget_state(config)
        if not state.next:
            response = state.values.get("agent_response", "Done!")
            if msg.reply_func:
                await msg.reply_func(response)
            return {"response": response}
        else:
            return {"status": "paused_again"}

    except Exception as e:
        logger.error(f"❌ Resume error ({msg.platform}): {e}", exc_info=True)
        if msg.reply_func:
            await msg.reply_func(f"❌ Error resuming action:\n`{str(e)[:500]}`")
        return {"error": str(e)[:500]}


# ==========================================================
# 6. Background Memory Gate
# ==========================================================

async def _run_memorygate(thread_id: str, user_input: str, agent_response: str):
    """
    Background task: extract context from the conversation
    and store in long-term memory.
    """
    try:
        from memory import memorygate
        await memorygate.process(thread_id, user_input, agent_response)
        # Background sync Zvec vector index AFTER SQLite writes are done
        await memorygate.store.sync_pending_memories()
    except Exception as e:
        logger.error(f"Memorygate error: {e}", exc_info=True)


# ==========================================================
# 7. Web Chat API Handlers
# ==========================================================

@app.post("/api/chat")
async def web_chat_send(request: Request):
    """
    Web chat endpoint — runs the LangGraph and returns the result as JSON.
    Supports the same HITL flow as Telegram.
    Enqueued via LaneManager to avoid race conditions.
    """
    if not graph:
        return JSONResponse({"error": "Graph not initialized"}, status_code=503)

    body = await request.json()
    user_input = body.get("message", "").strip()
    thread_id = body.get("thread_id", "web_default")

    if not user_input:
        return JSONResponse({"error": "Empty message"})

    logger.info(f"🌐 Web chat from {thread_id}: {user_input[:100]}")

    msg = StandardMessage(
        platform="web",
        user_id=thread_id,
        text=user_input
    )

    # Enqueue execution and await the future so we can respond to the HTTP request
    future = await lane_manager.submit(thread_id, agent_daemon, msg)
    try:
        result = await future
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"❌ Web chat error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)[:500]})


@app.post("/api/chat/approve")
async def web_chat_approve(request: Request):
    """
    Web chat HITL approval — resumes the paused graph.
    Enqueued via LaneManager.
    """
    if not graph:
        return JSONResponse({"error": "Graph not initialized"}, status_code=503)

    body = await request.json()
    decision = body.get("decision", "reject")
    thread_id = body.get("thread_id", "web_default")

    logger.info(f"🌐 Web approval: {decision} for thread {thread_id}")

    msg = ResumeMessage(
        platform="web",
        user_id=thread_id,
        decision=decision
    )

    future = await lane_manager.submit(thread_id, resume_daemon, msg)
    try:
        result = await future
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"❌ Web approval error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)[:500]})


# ==========================================================
# 8. Entrypoint
# ==========================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
