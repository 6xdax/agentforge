from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    thinking: bool = False
    stream: bool = True
