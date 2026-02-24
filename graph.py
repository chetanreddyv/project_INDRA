"""
graph.py — LangGraph StateGraph definition.

Defines the AgentState, wires up all nodes, and compiles the graph
with SQLite checkpointing for persistent state across restarts.
"""

import logging
from typing import TypedDict, Optional, Any
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from nodes.agent import agent_node
from nodes.approval import human_approval_node

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
        START → router → agent → (conditional)
                                   ├→ human_approval → (conditional)
                                   │                    ├→ agent (edit)
                                   │                    └→ synthesizer
                                   ├→ agent (retry)
                                   └→ synthesizer → END
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

# The checkpointer is initialized asynchronously in app.py startup
# This module exports the builder function, not a pre-built graph
