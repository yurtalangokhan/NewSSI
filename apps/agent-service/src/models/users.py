from pydantic import BaseModel


class RenameProjectPayload(BaseModel):
    name: str


class UpsertProjectInstructionsPayload(BaseModel):
    instructions: str


class MoveChatSessionPayload(BaseModel):
    chat_session_id: str


class FileStatusesPayload(BaseModel):
    file_ids: list[str]
