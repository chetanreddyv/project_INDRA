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
    Background task that actually executes the research via LangGraph.
    """
    logger.info(f"[Background] Starting true subagent for '{query}' on thread {thread_id}")
    
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
        
        summary = result["messages"][-1].content
        
        from nodes.graph import checkpointer_context, build_graph
        async with checkpointer_context() as cp:
            main_graph = build_graph(checkpointer=cp)
            
            await main_graph.aupdate_state(
                {"configurable": {"thread_id": thread_id}},
                {"messages": [AIMessage(content=f"🔔 **[Subagent Report]**\n\n{summary}")]}
            )
            logger.info(f"[Background] Injected research results for thread {thread_id}")
            
    except Exception as e:
        logger.error(f"[Background] Subagent task failed: {e}", exc_info=True)
        # Attempt to inject error report
        try:
            from nodes.graph import checkpointer_context, build_graph
            async with checkpointer_context() as cp:
                main_graph = build_graph(checkpointer=cp)
                await main_graph.aupdate_state(
                    {"configurable": {"thread_id": thread_id}},
                    {"messages": [AIMessage(content=f"🔔 **[Subagent Task Failed]**\nAn error occurred: {str(e)}")]}
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
    logger.info(f"Delegating research: {query} (thread: {thread_id})")
    
    # Fire and forget
    asyncio.create_task(run_research_task(query, thread_id))
    
    return f"Background process initiated for research on '{query}'. The system will notify the conversation asynchronously when it completes."

TOOL_REGISTRY = {
    "delegate_research": delegate_research
}
