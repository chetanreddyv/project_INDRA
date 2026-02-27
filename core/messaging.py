from dataclasses import dataclass

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

@dataclass
class SystemEvent:
    """
    A pure event representing a headless system trigger (e.g., cron job).
    Designed to spin up an agent thread without a direct user request.
    """
    platform: str      # usually 'system' or 'cron'
    user_id: str       # the thread_id to inject this event into
    text: str          # the system prompt/trigger instructions
    deliver: bool      # whether the outbound response should be sent to the user via channel_manager
