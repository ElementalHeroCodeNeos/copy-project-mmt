"""Băm và kiểm tra mật khẩu (Huy).

Băm (hash) là một chiều: không lấy lại được mật khẩu gốc. Khi LOGIN, server băm mật khẩu
vừa nhận với salt đã lưu rồi so với hash đã lưu; server không bao giờ lưu mật khẩu thật.

Không kiểm tra quy tắc mật khẩu (6–128 ký tự): handler REGISTER/LOGIN kiểm tra trước.
"""

import hashlib
import hmac
import secrets
import unicodedata

HASH_NAME = "sha256"
# Mức OWASP khuyến nghị (2023) cho PBKDF2-HMAC-SHA256. Đổi số này thì mọi tài khoản cũ không
# đăng nhập được nữa (số vòng không lưu trong database), phải xoá database: `docker compose down -v`.
ITERATIONS = 600_000
SALT_BYTES = 16


def _derive(password: str, salt: bytes) -> bytes:
    # NFC: "ệ" gõ thành một ký tự hay "e" + dấu đều cho cùng một chuỗi byte.
    data = unicodedata.normalize("NFC", password).encode("utf-8")
    # pbkdf2_hmac nhả GIL trong lúc tính, các luồng client khác vẫn chạy.
    return hashlib.pbkdf2_hmac(HASH_NAME, data, salt, ITERATIONS)


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Băm mật khẩu. Trả `(hash_hex, salt_hex)` để lưu vào bảng users.

    `salt=None` (REGISTER) → tạo salt ngẫu nhiên mới. Truyền `salt` (hex) thì băm lại với
    salt đó (dùng trong test).
    """
    salt_bytes = secrets.token_bytes(SALT_BYTES) if salt is None else bytes.fromhex(salt)
    return _derive(password, salt_bytes).hex(), salt_bytes.hex()


def verify_password(password: str, hash_hex: str, salt_hex: str) -> bool:
    """Mật khẩu có khớp với hash đã lưu không.

    So sánh bằng `hmac.compare_digest`: thời gian so sánh không phụ thuộc vào vị trí byte
    đầu tiên khác nhau. `hash_hex`/`salt_hex` không phải hex hợp lệ (database hỏng) thì ném
    ValueError; dispatcher trả 500 và ghi log.
    """
    expected = bytes.fromhex(hash_hex)
    actual = _derive(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(actual, expected)
