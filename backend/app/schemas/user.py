"""用户相关模型。"""

from typing import Optional

from pydantic import BaseModel, Field


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


class UserSearchOut(BaseModel):
    items: list[UserSummary]