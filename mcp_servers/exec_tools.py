"""
mcp_servers/exec_tools.py — Shell Execution Tools

Provides the agent with the ability to execute terminal commands in the workspace.
Supports both foreground and background execution, with yielding delays.
"""

import asyncio
import os
import uuid
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("mcp.exec_tools")

class ProcessSession:
    def __init__(self, process, command, workdir):
        self.process = process
        self.command = command
        self.workdir = workdir
        self.output_buffer = []
        self.start_time = time.time()
        self.is_done = False
        self.exit_code = None
        
        # Start read loop
        self.read_task = asyncio.create_task(self._read_output())

    async def _read_output(self):
        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    break
                self.output_buffer.append(line.decode('utf-8', errors='replace'))
        except Exception as e:
            logger.error(f"Error reading process output: {e}")
        finally:
            self.is_done = True
            try:
                self.exit_code = await self.process.wait()
            except:
                pass
            logger.info(f"Process session for '{self.command}' finished with code {self.exit_code}")

    def get_output(self, clear=True):
        out = "".join(self.output_buffer)
        if clear:
            self.output_buffer = []
        return out

_SESSIONS: Dict[str, ProcessSession] = {}

async def execute_command(
    command: str,
    workdir: str = None,
    env: dict = None,
    yieldMs: int = 10000,
    background: bool = False,
    timeout: int = 1800,
    **kwargs
) -> str:
    """
    Run a shell command in the workspace.
    
    Args:
        command: The shell command to execute.
        workdir: Working directory (defaults to current cwd).
        env: key/value overrides for environment variables.
        yieldMs: Delay in ms before auto-backgrounding (default 10000).
        background: If True, background immediately and return sessionId.
        timeout: Execution timeout in seconds (default 1800).
    """
    logger.info(f"🛠️ exec(command='{command[:50]}...', background={background})")
    
    workdir = workdir or os.getcwd()
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=workdir,
            env=run_env
        )
    except Exception as e:
        logger.error(f"❌ Failed to start command: {e}")
        return f"Failed to start command: {e}"

    session_id = str(uuid.uuid4())[:8]
    session = ProcessSession(proc, command, workdir)
    _SESSIONS[session_id] = session

    if background:
        return f"Session started in background. ID: {session_id}"
    
    # Wait for completion or yieldMs
    wait_sec = yieldMs / 1000.0
    try:
        await asyncio.wait_for(proc.wait(), timeout=wait_sec)
        out = session.get_output()
        del _SESSIONS[session_id]
        return f"Command exited with code {proc.returncode}:\n{out}"
    except asyncio.TimeoutError:
        out = session.get_output()
        return (
            f"Command reached yield timeout ({yieldMs}ms) and is now running in background.\n"
            f"Session ID: {session_id}\n"
            f"Initial Output:\n{out}\n"
            f"Use the process tool with action='poll' and sessionId='{session_id}' to check status."
        )

async def process_action(action: str, sessionId: str, keys: list = None, text: str = None) -> str:
    """
    Interact with a background process session.
    
    Args:
        action: One of 'poll', 'send-keys', 'submit', 'paste', 'kill'.
        sessionId: The ID of the session to interact with.
        keys: List of keys to send (for send-keys).
        text: Text to paste (for paste).
    """
    logger.info(f"🛠️ process(action='{action}', sessionId='{sessionId}')")
    
    if sessionId not in _SESSIONS:
        return f"Error: Session {sessionId} not found. It may have already been cleaned up or the ID is invalid."
        
    session = _SESSIONS[sessionId]
    
    if action == "poll":
        out = session.get_output()
        status = f"done (code {session.exit_code})" if session.is_done else "running"
        return f"Status: {status}\nOutput:\n{out}"
        
    elif action == "submit":
        if session.is_done:
            return "Session is already done."
        try:
            session.process.stdin.write(b'\n')
            await session.process.stdin.drain()
            await asyncio.sleep(0.5)
            out = session.get_output()
            return f"Submitted. Output:\n{out}"
        except Exception as e:
            return f"Error submitting: {e}"
            
    elif action == "paste":
        if session.is_done:
            return "Session is already done."
        if not text:
            return "Error: text argument required for paste."
        try:
            session.process.stdin.write(text.encode('utf-8'))
            await session.process.stdin.drain()
            await asyncio.sleep(0.5)
            out = session.get_output()
            return f"Pasted text. Output:\n{out}"
        except Exception as e:
            return f"Error pasting: {e}"
            
    elif action == "kill":
        if not session.is_done:
            session.process.terminate()
            return f"Session {sessionId} terminated."
        return "Session already complete."
        
    elif action == "send-keys":
         if session.is_done:
            return "Session is already done."
         if not keys:
             return "Error: keys argument required for send-keys."
         
         # Basic mapping for common terminal sequences
         try:
             for key in keys:
                 if key == "Enter" or key == "Return":
                     session.process.stdin.write(b'\n')
                 elif key == "C-c":
                     # Sending SIGINT to the process group is more robust, but terminate is safer
                     session.process.terminate()
                     break
                 else:
                     session.process.stdin.write(key.encode('utf-8'))
             await session.process.stdin.drain()
             await asyncio.sleep(0.5)
             out = session.get_output()
             return f"Sent keys. Output:\n{out}"
         except Exception as e:
            return f"Error sending keys: {e}"
         
    else:
        return f"Unknown action: {action}"

# ══════════════════════════════════════════════════════════════
# Tool Registry
# ══════════════════════════════════════════════════════════════

TOOL_REGISTRY: Dict[str, Any] = {
    # 'exec' and 'process' are built-in Python names, so we export them here under the requested API names
    "exec": execute_command,
    "process": process_action,
}
