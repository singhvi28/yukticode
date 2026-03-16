from pydantic import BaseModel, Field
from typing import Optional


class SubmitRequest(BaseModel):
    problem_id: int
    language: str
    src_code: str = Field(..., max_length=65536)
    contest_id: Optional[int] = None


class RunRequest(BaseModel):
    language: str
    time_limit: int
    memory_limit: int
    src_code: str = Field(..., max_length=65536)
    std_in: str = " "
    callback_url: Optional[str] = None


class RunBatchTestCase(BaseModel):
    input: str = Field(default=" ", max_length=1_000_000)
    expected_output: Optional[str] = Field(default=None, max_length=1_000_000)

class RunBatchRequest(BaseModel):
    language: str
    time_limit: int
    memory_limit: int
    src_code: str = Field(..., max_length=65536)
    tests: list[RunBatchTestCase]


class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_admin: bool
