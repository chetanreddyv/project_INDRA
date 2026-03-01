import asyncio
import logging
from pydantic import Field
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)

async def _monitor_background_process(process, command: str, thread_id: str):
    """Waits for a background process to finish and notifies the main agent."""
    stdout, stderr = await process.communicate()
    output = stdout.decode('utf-8', errors='replace').strip()
    error = stderr.decode('utf-8', errors='replace').strip()
    
    # Format the completion notification
    msg = f"🔔 **[Background Process Complete]**\nCommand: `{command}`\nExit Code: {process.returncode}"
    if output: msg += f"\n\nSTDOUT:\n```\n{output[:1000]}\n```"
    if error: msg += f"\n\nSTDERR:\n```\n{error[:1000]}\n```"

    # Inject into LangGraph state!
    if thread_id:
        try:
            from nodes.graph import checkpointer_context, build_graph
            async with checkpointer_context() as cp:
                main_graph = build_graph(checkpointer=cp)
                await main_graph.aupdate_state(
                    {"configurable": {"thread_id": thread_id}},
                    {"messages": [AIMessage(content=msg)]}
                )
        except Exception as e:
            logger.error(f"Failed to push background process result for {thread_id}: {e}")

@tool
async def exec_command(
    command: str = Field(
        ..., 
        description="The exact shell command to run. DO NOT use interactive commands (like vim, nano, or top)."
    ),
    timeout_seconds: int = Field(
        ..., 
        description="Timeout in seconds. You MUST provide 60 if unsure."
    ),
    background: bool = Field(
        ..., 
        description="Set to True to run asynchronously in the background, otherwise False."
    ),
    config: RunnableConfig = None
) -> str:
    """
    Executes a shell command on the host system. 
    Returns the standard output and standard error.
    """
    logger.info(f"Executing shell command: `{command}` (Background: {background}, Timeout: {timeout_seconds}s)")
    
    thread_id = config.get("configurable", {}).get("thread_id") if config else None
    
    # --- FIRE AND FORGET MODE (NOW WITH MONITORING) ---
    if background:
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            asyncio.create_task(_monitor_background_process(process, command, thread_id))
            return f"Background process started successfully with PID: {process.pid}. You will be notified when it finishes."
        except Exception as e:
            return f"Failed to start background process: {str(e)}"

    # --- BLOCKING MODE (WITH STRICT TIMEOUTS) ---
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # We wrap the communication in wait_for to prevent infinite hangs
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), 
            timeout=timeout_seconds
        )
        
        output = stdout.decode('utf-8', errors='replace').strip()
        error = stderr.decode('utf-8', errors='replace').strip()
        
        result = []
        if output:
            result.append(f"STDOUT:\n{output}")
        if error:
            result.append(f"STDERR:\n{error}")
            
        if process.returncode != 0:
            result.append(f"Process exited with error code {process.returncode}")
            
        return "\n\n".join(result) if result else "Command executed successfully with no output."
        
    except asyncio.TimeoutError:
        # If the command hangs, we aggressively kill it to free the LangGraph thread
        try:
            process.kill()
        except ProcessLookupError:
            pass
        return f"ERROR: Command timed out after {timeout_seconds} seconds. The process was killed. Make sure you are not running interactive commands."
        
    except Exception as e:
        return f"Execution failed: {str(e)}"

TOOL_REGISTRY = {
    "exec_command": exec_command
}
