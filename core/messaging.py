from dataclasses import dataclass
from typing import Callable, Awaitable, Optional

@dataclass
class StandardMessage:
    """
    A unified message format decoupled from specific platform SDKs.
    Follows the Nanobot philosophy by reducing integration complexity.
    """
    platform: str          # e.g., "telegram", "web"
    user_id: str           # The user id or thread id for tracking state
    text: str              # The user's input/prompt
    
    # Async callback to send a normal text response directly back
    reply_func: Optional[Callable[[str], Awaitable[None]]] = None
    
    # Async callback to send human-in-the-loop (HITL) approval requests
    approval_func: Optional[Callable[[str, str], Awaitable[None]]] = None

@dataclass
class ResumeMessage:
    """
    A unified format for resuming a paused agent.
    """
    platform: str
    user_id: str
    decision: str          # "approve" or "reject"
    
    # Async callback to send normal text response after resumption
    reply_func: Optional[Callable[[str], Awaitable[None]]] = None
