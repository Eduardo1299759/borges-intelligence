"""Cifragem de credenciais em repouso (Fernet: AES-128-CBC + HMAC-SHA256).

A chave vem de BORGES_ENCRYPTION_KEY e nunca do banco. Quem obtiver só o banco não lê as credenciais.
Gere com: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class EncryptionUnavailable(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = get_settings().encryption_key
    if not key:
        raise EncryptionUnavailable("BORGES_ENCRYPTION_KEY não configurada: credenciais não podem ser armazenadas.")
    try:
        return Fernet(key.encode())
    except ValueError as exc:
        raise EncryptionUnavailable("BORGES_ENCRYPTION_KEY inválida (esperada uma chave Fernet).") from exc


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionUnavailable("Credencial não pôde ser decifrada (a chave de cifragem mudou?).") from exc
