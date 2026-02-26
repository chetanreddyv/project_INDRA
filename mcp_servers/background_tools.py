"""
mcp_servers/background_tools.py

Provides tools for asynchronous background execution (subagents).
"""

import asyncio
import logging
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)

async def run_research_task(query: str, thread_id: str):
    """
    Background task that actually executes the research.
    """
    logger.info(f"[Background] Starting research for '{query}' on thread {thread_id}")
    
    # Simulate a long-running research task
    await asyncio.sleep(10)
    
    # In a real implementation we would run a SubGraph here.
    summary = f"Research completed for '{query}'.\n\n(This is a simulated background subagent response. In production, this would execute a dedicated LangGraph subgraph.)"

    # Inject the findings back into the main thread state
    try:
        from nodes.graph import checkpointer_context, build_graph
        async with checkpointer_context() as cp:
            graph = build_graph(checkpointer=cp)
            
            await graph.aupdate_state(
                {"configurable": {"thread_id": thread_id}},
                {"messages": [AIMessage(content=f"🔔 **[Background Task Complete]**\n\n{summary}")]}
            )
            logger.info(f"[Background] Injected research results for thread {thread_id}")
            
    except Exception as e:
        logger.error(f"[Background] Failed to inject findings: {e}")


@tool
async def delegate_research(query: str, config: RunnableConfig) -> str:
    """
    Kicks off a background research task without blocking the current conversation.
    Use this when the user asks for complex research or long-running tasks.
    
    Args:
        query: The research topic or question to investigate.
    """
    thread_id = config.get("configurable", {}).get("thread_id", "default_thread")
    logger.info(f"Delegating research: {query} (thread: {thread_id})")
    
    # Fire and forget
    asyncio.create_task(run_research_task(query, thread_id))
    
    return f"Background process initiated for research on '{query}'. The system will notify the conversation asynchronously when it completes."

TOOL_REGISTRY = {
    "delegate_research": delegate_research
}
