import asyncio
import logging
from pydantic import Field
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

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
    )
) -> str:
    """
    Executes a shell command on the host system. 
    Returns the standard output and standard error.
    """
    logger.info(f"Executing shell command: `{command}` (Background: {background}, Timeout: {timeout_seconds}s)")
    
    # --- FIRE AND FORGET MODE ---
    if background:
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            return f"Background process started successfully with PID: {process.pid}"
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
