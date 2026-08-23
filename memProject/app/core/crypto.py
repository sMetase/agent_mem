# -*- coding: utf-8 -*-
"""敏感字段对称加密（Fernet）。密钥从 SECRET_KEY 派生。"""
import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _get_fernet() -> Fernet:
    key = get_settings().app.secret_key or "dev-secret-key"
    digest = hashlib.sha256(key.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


def encrypt_secret(plaintext: str | None) -> str | None:
    """加密敏感字段；空值原样返回。"""
    if not plaintext:
        return plaintext
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str | None) -> str | None:
    """解密敏感字段；空值原样返回；解密失败（如历史明文）原样返回。"""
    if not ciphertext:
        return ciphertext
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except Exception:
        return ciphertext
