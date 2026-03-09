from pydantic import BaseModel


class SubmitRequest(BaseModel):
    problem_id: int
    language: str
    src_code: str


from typing import Optional

class RunRequest(BaseModel):
    language: str
    time_limit: int
    memory_limit: int
    src_code: str
    std_in: str = " "
    callback_url: Optional[str] = None


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
