"""用户相关模型。"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class UserSummary(BaseModel):
    """用户简要信息(搜索结果/成员列表/好友列表)。"""

    user_id: int
    name: str
    avatar: Optional[str] = None
    online: bool = False


class UserProfile(BaseModel):
    """用户完整资料(仅本人可见)。"""

    user_id: int
    name: str
    avatar: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    register_time: int
    login_time: Optional[int] = None


class UserUpdateIn(BaseModel):
    """修改资料;修改密码需提供旧密码通过校验。"""

    name: Optional[str] = Field(default=None, min_length=2, max_length=32)
    email: Optional[str] = Field(default=None, max_length=128)
    phone: Optional[str] = Field(default=None, max_length=32)
    avatar: Optional[str] = Field(default=None, max_length=255)
    old_password: Optional[str] = Field(default=None, min_length=8, max_length=64)
    new_password: Optional[str] = Field(default=None, min_length=8, max_length=64)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 2:
            raise ValueError("用户名长度需在 2-32 个字符之间")
        return v

    @field_validator("new_password")
    @classmethod
    def new_password_strength(cls, v: Optional[str]) -> Optional[str]:
        # 与注册保持一致：改密也不能绕过字母+数字的强度要求
        if v is not None and (not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v)):
            raise ValueError("密码需同时包含字母与数字")
        return v


class DeleteAccountIn(BaseModel):
    """注销账号需要再次验证当前密码，避免 token 泄露后被直接毁号。"""

    password: str = Field(min_length=8, max_length=64, description="当前密码")


class UserSearchOut(BaseModel):
    items: list[UserSummary]