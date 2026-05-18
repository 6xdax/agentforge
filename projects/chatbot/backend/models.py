from pydantic import BaseModel, Field
from typing import Optional, List, Literal


class AttachmentRef(BaseModel):
    file_name: str
    saved_path: str
    size: Optional[int] = None


class ChatRequest(BaseModel):
    chat_id: str
    message: str
    thinking: bool = False
    stream: bool = True
    file_paths: List[str] = Field(default_factory=list)
    file_attachments: List[AttachmentRef] = Field(default_factory=list)


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str


class ToolCall(BaseModel):
    """Tool call record for history"""
    call_id: str
    name: str
    arguments: Optional[dict] = None
    result: Optional[str] = None
    status: Literal["running", "completed", "error"] = "completed"


class HistoryMessage(BaseModel):
    """Structured history message for frontend display"""
    role: Literal["user", "assistant"]
    content: str
    attachments: Optional[List[AttachmentRef]] = None
    thinking: Optional[str] = None
    thinking_completed: bool = False
    tool_calls: Optional[List[ToolCall]] = None
    usage: Optional[dict] = None
