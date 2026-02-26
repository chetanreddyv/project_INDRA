import logging
from abc import ABC, abstractmethod
from typing import Any, Dict

logger = logging.getLogger("mcp.clients")

class ClientInterface(ABC):
    """
    Abstract base class for all INDRA input/output clients.
    Decouples the LangGraph execution engine from the delivery mechanism.
    """
    
    @abstractmethod
    async def send_message(self, thread_id: str, content: str) -> None:
        """
        Pushes a standard text message to the client.
        
        Args:
            thread_id: The unique identifier for the conversation/user.
            content: The text/HTML content to send.
        """
        pass
        
    @abstractmethod
    async def request_approval(self, thread_id: str, tool_name: str, args: Dict[str, Any]) -> None:
        """
        Pushes an interactive approval request (e.g., UI buttons) to the client.
        
        Args:
            thread_id: The unique identifier for the conversation/user.
            tool_name: The name of the action requiring approval.
            args: The exact arguments the LLM wants to execute the tool with.
        """
        pass
