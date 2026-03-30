from pydantic import BaseModel, Field


class CriterionInput(BaseModel):
    name: str
    weight: int = Field(ge=0, le=100)
    description: str = ""


class JobRoleCreate(BaseModel):
    title: str
    description: str
    criteria: list[CriterionInput]


class JobRoleUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    criteria: list[CriterionInput] | None = None


class RankingSessionCreate(BaseModel):
    job_role_id: int
    folder_path: str
