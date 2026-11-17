"""Điều phối lệnh (kiet-context mục 10.3).

Mỗi lệnh là một hàm `handle(session, payload) -> Reply`, đăng ký bằng `@command`:

    @command(protocol.ROOM_MSG)                  # auth=True: phải đăng nhập
    def room_msg(session, payload):
        room = require(payload, "room", str)
        ...
        return Reply(data={"ts": ts}, after=[lambda: broadcast(...)])

Báo lỗi bằng `raise CommandError(code, message)`. Dispatcher tự kiểm tra lệnh có tồn
tại, đã đăng nhập, payload là object; gửi response; rồi chạy `after`.
"""

import logging
from dataclasses import dataclass, field
from typing import Callable

from shared import protocol

log = logging.getLogger("dispatch")


class CommandError(Exception):
    """Handler ném lỗi này để trả <LỆNH>_RESPONSE với mã `code` và câu `message`."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Reply:
    """Kết quả của handler.

    - code, message, data: nội dung <LỆNH>_RESPONSE.
    - after: các hàm không tham số, chạy SAU khi đã gửi response (ví dụ gửi
      NOTIFY_ROOM_MSG: protocol yêu cầu push đi sau response).
    - close: True thì sau response và after, server đóng kết nối và dọn phiên (QUIT).
    """
    code: int = protocol.OK
    data: dict = field(default_factory=dict)
    message: str = "OK"
    after: list[Callable[[], None]] = field(default_factory=list)
    close: bool = False


@dataclass(frozen=True)
class _Command:
    handler: Callable
    auth: bool


_commands: dict[str, _Command] = {}


def command(name: str, auth: bool = True):
    """Decorator đăng ký handler cho lệnh `name`. auth=False cho REGISTER, LOGIN, PING, QUIT."""
    def decorator(fn):
        if name in _commands:
            # Báo lỗi ngay lúc khởi động, không để lệnh sau âm thầm ghi đè lệnh trước.
            old = _commands[name].handler
            raise RuntimeError(f"Lệnh {name} đã được đăng ký ở {old.__module__}.{old.__name__}")
        _commands[name] = _Command(fn, auth)
        return fn
    return decorator


def registered_commands() -> list[str]:
    return sorted(_commands)


# ---------------------------------------------------------------------------
# Kiểm tra trường trong payload
# ---------------------------------------------------------------------------

_TYPE_NAMES = {str: "chuỗi", int: "số nguyên", float: "số", bool: "true/false",
               dict: "object", list: "mảng"}


def _is_type(value, typ) -> bool:
    # bool là lớp con của int trong Python: không để true/false lọt qua như số 1/0.
    if isinstance(value, bool) and typ is not bool:
        return False
    return isinstance(value, typ)


def require(payload: dict, key: str, typ: type):
    """Lấy trường bắt buộc; thiếu hoặc sai kiểu thì ném CommandError(400)."""
    if key not in payload or not _is_type(payload[key], typ):
        raise CommandError(protocol.BAD_REQUEST,
                           f"Thiếu trường {key} hoặc sai kiểu (cần {_TYPE_NAMES.get(typ, typ.__name__)})")
    return payload[key]


def optional(payload: dict, key: str, typ: type, default=None):
    """Lấy trường không bắt buộc; không có thì trả default, có mà sai kiểu thì CommandError(400)."""
    if key not in payload:
        return default
    if not _is_type(payload[key], typ):
        raise CommandError(protocol.BAD_REQUEST,
                           f"Trường {key} sai kiểu (cần {_TYPE_NAMES.get(typ, typ.__name__)})")
    return payload[key]


# ---------------------------------------------------------------------------
# Điều phối
# ---------------------------------------------------------------------------


def dispatch(session, msg: dict) -> bool:
    """Xử lý một message đã decode. Trả True nếu phải đóng kết nối (Reply.close)."""
    name = msg["command"]
    request_id = msg.get("requestId")

    def respond(code, message, data=None):
        session.send(protocol.response(name, code, message, data, request_id=request_id))

    cmd = _commands.get(name)
    if cmd is None:
        session.send(protocol.error(protocol.BAD_REQUEST, f"Lệnh không tồn tại: {name}",
                                    request_id=request_id))
        return False
    if cmd.auth and session.username is None:
        respond(protocol.UNAUTHORIZED, "Bạn cần đăng nhập trước")
        return False
    payload = msg.get("payload")
    if not isinstance(payload, dict):
        respond(protocol.BAD_REQUEST, "Thiếu trường payload hoặc payload không phải object")
        return False

    try:
        reply = cmd.handler(session, payload)
        if not isinstance(reply, Reply):
            raise TypeError(f"handler của {name} trả {type(reply).__name__}, không phải Reply")
    except CommandError as exc:
        respond(exc.code, exc.message)
        return False
    except Exception:
        # Chi tiết lỗi chỉ ghi vào log server, không gửi cho client.
        log.exception("Lỗi khi xử lý lệnh %s từ %s", name, session.peer)
        respond(protocol.INTERNAL_ERROR, "Lỗi máy chủ khi xử lý lệnh")
        return False

    respond(reply.code, reply.message, reply.data)
    # after chạy cả khi gửi response thất bại: lệnh đã được chấp nhận, người khác vẫn nhận.
    for fn in reply.after:
        try:
            fn()
        except Exception:
            log.exception("Lỗi trong after của lệnh %s từ %s", name, session.peer)
    return reply.close
