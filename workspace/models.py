from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    path: str = Field(min_length=1)


class Workspace(BaseModel):
    id: str
    name: str
    path: str
    is_git_repo: bool
    created_at: str
