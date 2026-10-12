"""好友相关模型。"""

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.user import UserSummary


class FriendItem(BaseModel):
    user_id: int
    name: str
    avatar: Optional[str] = None
    remark: Optional[str] = None
    group_name: Optional[str] = None
    online: bool = False


class FriendListOut(BaseModel):
    items: list[FriendItem]


class FriendRequestCreateIn(BaseModel):
    target_user_id: int = Field(gt=0)


class FriendRequestOut(BaseModel):
    request_id: int
    from_user: Optional[UserSummary] = None  # 收到的申请携带对方信息
    to_user_id: int
    status: str
    create_time: int


class FriendRequestListOut(BaseModel):
    items: list[FriendRequestOut]