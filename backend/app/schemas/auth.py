"""认证相关模型。"""

from pydantic import BaseModel, Field, field_validator

from app.schemas.user import UserSummary


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=32, description="用户名,允许中文")
    password: str = Field(min_length=8, max_length=64, description="至少含字母与数字")

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("用户名不能为空白")
        return v.strip()

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError("密码需同时包含字母与数字")
        return v


class RegisterOut(BaseModel):
    user_id: int


class LoginIn(RegisterIn):
    pass


class LoginOut(BaseModel):
    token: str
    user: UserSummary