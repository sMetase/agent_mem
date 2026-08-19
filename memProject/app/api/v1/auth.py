# -*- coding: utf-8 -*-
"""
控制台用户登录 — 登录即注册（login 时用户不存在则自动创建）。

对应前后端问题 #6：userId 由登录派生，登录返回 {user, token, user_id}，
前端登录后把 user_id 写入 AppConfig，移除 Settings 的 userId 手动配置。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AuthenticationError
from app.core.logger import get_logger
from app.core.security import (
    create_access_token,
    generate_user_id,
    hash_password,
    verify_password,
)
from app.models.base import User
from app.schemas.common import ok

logger = get_logger("auth_api")

router = APIRouter()


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128, description="登录账号")
    password: str = Field(..., min_length=1, max_length=128, description="密码")


@router.post("/login", summary="登录（不存在则自动注册）")
async def auth_login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """登录即注册：username 不存在则自动创建（用传入 password）。"""
    username = body.username.strip()

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if user is None:
        # 自动注册
        user = User(
            user_id=generate_user_id(),
            username=username,
            password_hash=hash_password(body.password),
            name=username,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info(f"新用户自动注册: username={username}, user_id={user.user_id}")
    else:
        # 已有用户，验证密码
        if not user.password_hash or not verify_password(body.password, user.password_hash):
            raise AuthenticationError("用户名或密码错误")
        logger.info(f"用户登录: username={username}, user_id={user.user_id}")

    token = create_access_token(subject=user.user_id)

    return ok({
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "name": user.name,
        },
        "token": token,
        "user_id": user.user_id,
    })
