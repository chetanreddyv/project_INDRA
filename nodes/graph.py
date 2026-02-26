"""
graph.py — LangGraph StateGraph definition.

Defines the AgentState, wires up all nodes, and compiles the graph
with SQLite checkpointing for persistent state across restarts.
"""

import logging
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .agent import agent_node
from .approval import human_approval_node

logger = logging.getLogger(__name__)


# ==========================================================
# 1. State Schema
# ==========================================================

class AgentState(TypedDict):
    """Full state flowing through the LangGraph."""

    # ── Core ──────────────────────────────────────────────────
    chat_id: str                              # Telegram chat ID (= thread_id)
    user_input: str                           # Current user message

    # ── Agent ─────────────────────────────────────────────────
    agent_response: Optional[str]             # Final response text
    pending_action: Optional[dict]            # Action awaiting HITL approval
    tool_failure_count: int                   # Self-correction counter

    # ── Memory ────────────────────────────────────────────────
    memory_context: Optional[str]             # Retrieved long-term context


# ==========================================================
# 2. Conditional Routing
# ==========================================================

def route_after_agent(state: AgentState) -> str:
    """Decide what happens after the agent node."""
    # If agent hit max failures, go straight to END
    if state.get("tool_failure_count", 0) >= 3:
        return END
    # If agent needs a retry (self-correction)
    if state.get("_retry"):
        return "agent"
    # If there's a pending write action, route to HITL
    if state.get("pending_action"):
        return "human_approval"
    # Normal completion
    return END


def route_after_approval(state: AgentState) -> str:
    """Decide what happens after human approval."""
    # If user requested an edit, re-run the agent
    if state.get("_needs_rerun"):
        return "agent"
    return END


# ==========================================================
# 3. Graph Construction
# ==========================================================

def build_graph(checkpointer=None):
    """
    Build and compile the LangGraph StateGraph.
    
    Flow:
        START → agent → (conditional)
                                   ├→ human_approval → (conditional)
                                   │                    ├→ agent (edit)
                                   │                    └→ END
                                   ├→ agent (retry)
                                   └→ END
    """
    builder = StateGraph(AgentState)

    # Add nodes
    builder.add_node("agent", agent_node)
    builder.add_node("human_approval", human_approval_node)

    # Wire edges
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        route_after_agent,
        ["human_approval", "agent", END],
    )
    builder.add_conditional_edges(
        "human_approval",
        route_after_approval,
        ["agent", END],
    )

    # Compile with checkpointer
    graph = builder.compile(checkpointer=checkpointer)
    logger.info("✅ LangGraph compiled successfully")
    return graph


# ==========================================================
# 4. Graph Instance (with SQLite checkpointer)
# ==========================================================

import os
from pathlib import Path

# Default path — can be overridden via the DB_PATH env var
_DEFAULT_DB_PATH = os.getenv("DB_PATH", "./data/checkpoints.db")


def checkpointer_context(db_path: str = _DEFAULT_DB_PATH):
    """
    Return an async context manager that opens an AsyncSqliteSaver.

    Usage (in FastAPI lifespan)::

        async with checkpointer_context() as cp:
            graph = build_graph(checkpointer=cp)
            yield  # serve requests
        # connection is closed automatically on exit

    Args:
        db_path: Path to the SQLite file.  The parent directory is
                 created automatically if it does not exist.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"📂 SQLite checkpointer will use → {db_path}")
    return AsyncSqliteSaver.from_conn_string(db_path)
