from dataclasses import dataclass
from typing import Optional

@dataclass
class IncomingMessageEvent:
    """
    A pure event representing an incoming message from a client.
    Contains NO callbacks, ensuring complete decoupling.
    """
    platform: str
    user_id: str
    text: str

@dataclass
class ResumeEvent:
    """
    A pure event representing a Human-In-The-Loop resumption request.
    """
    platform: str
    user_id: str
    decision: str
