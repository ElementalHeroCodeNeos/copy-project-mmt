"""MRCP/1.0: tách message và mã hoá/giải mã JSON (docs/protocol-design.md mục 2, 3).

Mỗi message là một object JSON trên một dòng, mã UTF-8, kết thúc bằng một byte \\n.
Server và client cùng dùng module này.
"""

import json

# ---------------------------------------------------------------------------
# Hằng số
# ---------------------------------------------------------------------------

DEFAULT_MAX_BYTES = 65536  # 64 KB, khớp MAX_MESSAGE_BYTES trong .env.example

# Mã trạng thái (protocol-design.md mục 5)
OK = 200
CREATED = 201
BAD_REQUEST = 400
UNAUTHORIZED = 401
FORBIDDEN = 403
NOT_FOUND = 404
CONFLICT = 409
TOO_LARGE = 413
INTERNAL_ERROR = 500
SERVICE_UNAVAILABLE = 503

# Tên lệnh. Khôi và Huy thêm tên lệnh của mình (mục 4.3, 4.4) vào đây.
REGISTER = "REGISTER"
LOGIN = "LOGIN"
PING = "PING"  # server trả PING_RESPONSE như mọi lệnh khác (không có lệnh PONG riêng)
QUIT = "QUIT"
ROOM_MSG = "ROOM_MSG"
PRIVATE_MSG = "PRIVATE_MSG"
NOTIFY_ROOM_MSG = "NOTIFY_ROOM_MSG"
NOTIFY_PRIVATE_MSG = "NOTIFY_PRIVATE_MSG"
NOTIFY_ONLINE = "NOTIFY_ONLINE"    # Huy: bạn cùng phòng vừa đăng nhập, data {username}
NOTIFY_OFFLINE = "NOTIFY_OFFLINE"  # Huy: bạn cùng phòng vừa ngắt/QUIT, data {username}
ERROR = "ERROR"

RESPONSE_SUFFIX = "_RESPONSE"
NOTIFY_PREFIX = "NOTIFY_"


# ---------------------------------------------------------------------------
# Lỗi
# ---------------------------------------------------------------------------


class ProtocolError(ValueError):
    """Message có ranh giới rõ nhưng nội dung sai: trả ERROR 400, giữ kết nối."""


class FrameTooLarge(Exception):
    """Dữ liệu quá max_bytes mà chưa gặp \\n: trả ERROR 413, đóng kết nối.

    Cố ý không kế thừa ProtocolError, để `except ProtocolError` (giữ kết nối)
    không bắt nhầm lỗi này (phải đóng kết nối).
    """


# ---------------------------------------------------------------------------
# Tách message (framing)
# ---------------------------------------------------------------------------


def encode(msg: dict) -> bytes:
    """dict -> một dòng JSON UTF-8 kết thúc bằng \\n."""
    text = json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
    return text.encode("utf-8") + b"\n"


class FrameBuffer:
    """Bộ đệm nhận của một kết nối: ghép các lần recv() thành từng dòng."""

    def __init__(self, max_bytes: int = DEFAULT_MAX_BYTES):
        self.max_bytes = max_bytes
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        """Nối data vào bộ đệm, trả các dòng hoàn chỉnh (đã bỏ \\n và dòng rỗng).

        Ném FrameTooLarge khi một dòng dài hơn max_bytes, hoặc phần chưa gặp \\n
        dài hơn max_bytes. Sau khi ném thì kết nối phải đóng, không gọi feed nữa.
        """
        self._buf += data
        lines = []
        start = 0
        while True:
            nl = self._buf.find(b"\n", start)
            if nl == -1:
                break
            line = bytes(self._buf[start:nl])
            start = nl + 1
            if len(line) > self.max_bytes:
                raise FrameTooLarge(f"Dòng dài {len(line)} byte, vượt {self.max_bytes}")
            if line.strip():  # bỏ dòng rỗng hoặc chỉ có khoảng trắng (kể cả \r)
                lines.append(line)
        del self._buf[:start]
        if len(self._buf) > self.max_bytes:
            raise FrameTooLarge(f"Đã nhận {len(self._buf)} byte chưa gặp \\n, vượt {self.max_bytes}")
        return lines


# ---------------------------------------------------------------------------
# Giải mã
# ---------------------------------------------------------------------------


def decode(line: bytes) -> dict:
    """Một dòng (không có \\n) -> dict. Ném ProtocolError nếu sai khung message."""
    try:
        text = line.decode("utf-8")
    except UnicodeDecodeError:
        raise ProtocolError("Dữ liệu không phải UTF-8 hợp lệ") from None
    try:
        msg = json.loads(text)
    except (ValueError, RecursionError):
        # ValueError: JSON sai cú pháp (JSONDecodeError là lớp con), hoặc số nguyên quá dài.
        # RecursionError: JSON lồng quá sâu, ví dụ [[[[...]]]].
        raise ProtocolError("JSON không hợp lệ") from None
    if not isinstance(msg, dict):
        raise ProtocolError("Message phải là một object JSON")
    command = msg.get("command")
    if not isinstance(command, str) or not command:
        raise ProtocolError("Thiếu trường command hoặc command không phải chuỗi")
    if "requestId" in msg and not isinstance(msg["requestId"], str):
        raise ProtocolError("requestId phải là chuỗi")
    return msg


# ---------------------------------------------------------------------------
# Tạo message
# ---------------------------------------------------------------------------


def response(command: str, code: int, message: str = "OK", data: dict | None = None,
             request_id: str | None = None) -> dict:
    """Tạo <command>_RESPONSE. Chỉ thêm requestId khi request có."""
    msg = {"command": command + RESPONSE_SUFFIX}
    if request_id is not None:
        msg["requestId"] = request_id
    msg["code"] = code
    msg["message"] = message
    msg["data"] = data if data is not None else {}
    return msg


def push(command: str, data: dict) -> dict:
    """Tạo thông báo đẩy; command phải là tên đầy đủ, ví dụ NOTIFY_ROOM_MSG."""
    if not command.startswith(NOTIFY_PREFIX):
        raise ValueError(f"Tên push phải bắt đầu bằng {NOTIFY_PREFIX}: {command!r}")
    return {"command": command, "data": data}


def error(code: int, message: str, request_id: str | None = None) -> dict:
    """Tạo message ERROR (lỗi không gắn với lệnh nào)."""
    msg = {"command": ERROR}
    if request_id is not None:
        msg["requestId"] = request_id
    msg["code"] = code
    msg["message"] = message
    return msg
