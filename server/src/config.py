"""Cấu hình server, đọc từ biến môi trường (xem .env.example).

Mỗi giá trị được đọc một lần khi import module. Biến không có hoặc rỗng thì dùng
giá trị mặc định; biến có giá trị sai thì ném ConfigError để server dừng ngay.
"""

import os


class ConfigError(ValueError):
    """Biến môi trường có giá trị không hợp lệ."""


def _str(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _int(name: str, default: int, min_value: int = 1, max_value: int | None = None) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name}={raw!r} không phải số nguyên") from None
    if value < min_value or (max_value is not None and value > max_value):
        upper = max_value if max_value is not None else "∞"
        raise ConfigError(f"{name}={value} nằm ngoài khoảng [{min_value}, {upper}]")
    return value


_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def _log_level(name: str, default: str) -> str:
    value = _str(name, default).upper()
    if value not in _LOG_LEVELS:
        raise ConfigError(f"{name}={value!r} phải là một trong {', '.join(_LOG_LEVELS)}")
    return value


SERVER_HOST = _str("SERVER_HOST", "0.0.0.0")
SERVER_PORT = _int("SERVER_PORT", 5000, max_value=65535)
MAX_MESSAGE_BYTES = _int("MAX_MESSAGE_BYTES", 65536)
READ_TIMEOUT_SEC = _int("READ_TIMEOUT_SEC", 90)
MAX_CLIENTS = _int("MAX_CLIENTS", 100)
MAX_TEXT_CHARS = _int("MAX_TEXT_CHARS", 2000)
DATA_DIR = _str("DATA_DIR", "/app/data")
LOG_LEVEL = _log_level("LOG_LEVEL", "INFO")
