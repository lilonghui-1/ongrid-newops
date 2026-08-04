"""安全模块 - JWT 令牌生成/验证 + 密码哈希

基于 python-jose (HS256) 和 passlib[bcrypt] 实现：
- 密码哈希与校验
- access_token / refresh_token 生成与解码
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import jwt
from passlib.context import CryptContext

# ---------------------------------------------------------------------------
# 配置：密钥从环境变量/配置读取，提供安全的默认占位值
# 生产环境务必通过环境变量 OPS_AGENT_SECRET_KEY 覆盖
# ---------------------------------------------------------------------------
SECRET_KEY: str = os.getenv(
    "OPS_AGENT_SECRET_KEY",
    "ops-agent-secret-key-change-in-production",
)
ALGORITHM: str = "HS256"

# 令牌有效期
ACCESS_TOKEN_EXPIRE_MINUTES: int = 30      # access_token 默认 30 分钟过期
REFRESH_TOKEN_EXPIRE_DAYS: int = 7         # refresh_token 默认 7 天过期

# 密码哈希上下文（bcrypt）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# 密码哈希
# ---------------------------------------------------------------------------
def verify_password(plain: str, hashed: str) -> bool:
    """验证明文密码与哈希值是否匹配。

    Args:
        plain: 明文密码
        hashed: 已哈希的密码

    Returns:
        匹配返回 True，否则 False
    """
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        # 哈希格式异常等情况一律视为校验失败
        return False


def get_password_hash(password: str) -> str:
    """生成密码的 bcrypt 哈希值。

    Args:
        password: 明文密码

    Returns:
        哈希后的密码字符串
    """
    return pwd_context.hash(password)


# ---------------------------------------------------------------------------
# JWT 令牌
# ---------------------------------------------------------------------------
def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """创建访问令牌 (access token)。

    Args:
        data: 需要写入 payload 的数据（通常包含 sub=username、role 等）
        expires_delta: 自定义过期时长；为 None 时默认 30 分钟

    Returns:
        编码后的 JWT 字符串
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta is not None else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: Dict[str, Any]) -> str:
    """创建刷新令牌 (refresh token)，默认 7 天过期。

    Args:
        data: 需要写入 payload 的数据

    Returns:
        编码后的 JWT 字符串
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """解码并验证 JWT 令牌，返回 payload 字典。

    Args:
        token: JWT 字符串

    Returns:
        解码后的 payload

    Raises:
        jose.JWTError: 令牌无效、过期或签名不匹配时抛出
    """
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
