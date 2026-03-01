"""
mcp_servers/background_tools.py

Provides tools for asynchronous background execution (subagents).
"""

import asyncio
import logging
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
import httpx

logger = logging.getLogger(__name__)

async def run_research_task(query: str, thread_id: str, platform: str):
    """
    Background task that actually executes the research via LangGraph.
    """
    logger.info(f"[Background] Starting true subagent for '{query}' on thread {thread_id} ({platform})")
    
    try:
        from nodes.subagents import build_researcher_graph
        researcher_graph = build_researcher_graph()
        
        sub_state = {
            "messages": [], 
            "user_input": f"Research this thoroughly: {query}",
            "chat_id": f"subagent_{thread_id}",
            "tool_failure_count": 0
        }
        
        # We invoke without a checkpointer, making it an ephemeral execution
        result = await researcher_graph.ainvoke(sub_state)
        
        # Safely parse content (in case of list of dicts from Gemini)
        summary = result["messages"][-1].content
        if isinstance(summary, list):
            summary = "\n".join(item.get("text", "") for item in summary if isinstance(item, dict) and "text" in item)
            
        # Use Universal Gateway instead of hardcoding core architecture
        async with httpx.AsyncClient() as client:
            await client.post(
                f"http://localhost:8000/api/v1/system/{thread_id}/notify",
                json={
                    "message": f"🔔 **[Subagent Report]**\n\n{summary}",
                    "platform": platform
                },
                timeout=10.0
            )
            
    except Exception as e:
        logger.error(f"[Background] Subagent task failed: {e}", exc_info=True)
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"http://localhost:8000/api/v1/system/{thread_id}/notify",
                    json={
                        "message": f"🔔 **[Subagent Task Failed]**\nAn error occurred: {str(e)}",
                        "platform": platform
                    },
                    timeout=10.0
                )
        except Exception:
            pass


@tool
async def delegate_research(query: str, config: RunnableConfig) -> str:
    """
    Kicks off a background research task without blocking the current conversation.
    Use this when the user asks for complex research or long-running tasks.
    
    Args:
        query: The research topic or question to investigate.
    """
    thread_id = config.get("configurable", {}).get("thread_id", "default_thread")
    platform = config.get("configurable", {}).get("platform", "telegram")
    logger.info(f"Delegating research: {query} (thread: {thread_id} via {platform})")
    
    # Fire and forget
    asyncio.create_task(run_research_task(query, thread_id, platform))
    
    return f"Background process initiated for research on '{query}'. The system will notify the conversation asynchronously when it completes."

TOOL_REGISTRY = {
    "delegate_research": delegate_research
}
