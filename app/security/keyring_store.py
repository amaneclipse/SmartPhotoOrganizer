"""Credential Manager-backed key storage. Never falls back to plaintext."""
from __future__ import annotations
try:
    import keyring
except ImportError:
    keyring = None

class SecureStorageError(RuntimeError): pass
class KeyringStore:
    service_name = "smart-photo-organizer"
    def __init__(self, service_name: str | None = None): self.service_name = service_name or self.service_name
    def available(self) -> bool: return keyring is not None
    def save(self, provider_id: str, secret: str) -> None:
        if not keyring: raise SecureStorageError("Библиотека keyring не установлена; ключ не сохранён.")
        try: keyring.set_password(self.service_name, provider_id, secret)
        except Exception as exc: raise SecureStorageError("Windows Credential Manager недоступен; ключ не сохранён.") from exc
    def get(self, provider_id: str) -> str | None:
        if not keyring: return None
        try: return keyring.get_password(self.service_name, provider_id)
        except Exception as exc: raise SecureStorageError("Не удалось прочитать ключ из Windows Credential Manager.") from exc
    def delete(self, provider_id: str) -> None:
        if not keyring: return
        try: keyring.delete_password(self.service_name, provider_id)
        except Exception as exc:
            if "not found" not in str(exc).lower(): raise SecureStorageError("Не удалось удалить ключ из Windows Credential Manager.") from exc
