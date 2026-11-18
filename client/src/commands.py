"""Chuyển dòng người dùng gõ thành lệnh protocol (Khôi, bước 22).

Gõ `/lệnh tham số`; gõ chữ thường (không có `/`) là gửi tin vào phòng hiện tại.
Hàm `parse()` không đụng tới mạng, nên test được riêng.
"""

from dataclasses import dataclass, field

HELP = """Lệnh:
  /register <tên> <mật khẩu>   đăng ký          /login <tên> <mật khẩu>   đăng nhập
  /rooms                       danh sách phòng  /create <phòng>           tạo phòng (và vào luôn)
  /join <phòng>                vào phòng        /leave <phòng>            rời phòng
  /use <phòng>                 chọn phòng hiện tại (gõ chữ thường là gửi vào phòng này)
  /members [phòng]             thành viên phòng /online                   ai đang online
  /msg <tên> <nội dung>        nhắn riêng       /quit                     thoát
  <nội dung>                   gửi vào phòng hiện tại"""


@dataclass
class Action:
    """Kết quả phân tích một dòng.

    kind: "send" (gửi `command` + `payload`), "use" (đổi phòng hiện tại sang `room`),
          "help", "quit", "error" (in `text`), "none" (dòng trống).
    """
    kind: str
    command: str | None = None
    payload: dict = field(default_factory=dict)
    room: str | None = None
    text: str = ""


# lệnh: (tên lệnh protocol, các tham số; tham số cuối cùng có "*" thì lấy hết phần còn lại)
_SIMPLE = {
    "/register": ("REGISTER", ["username", "password"]),
    "/login": ("LOGIN", ["username", "password"]),
    "/rooms": ("LIST_ROOMS", []),
    "/create": ("CREATE_ROOM", ["room"]),
    "/join": ("JOIN_ROOM", ["room"]),
    "/leave": ("LEAVE_ROOM", ["room"]),
    "/online": ("LIST_ONLINE", []),
    "/msg": ("PRIVATE_MSG", ["to", "content*"]),
}


def parse(line: str, current_room: str | None) -> Action:
    # Bỏ BOM (﻿): một số terminal (PowerShell khi pipe) chèn vào đầu dữ liệu nhập.
    text = line.rstrip("\r\n").lstrip("﻿")
    if not text.strip():
        return Action("none")
    if not text.startswith("/"):
        if current_room is None:
            return Action("error", text="Chưa chọn phòng: /join <phòng> hoặc /use <phòng>")
        return Action("send", "ROOM_MSG", {"room": current_room, "content": text})

    name, _, rest = text.partition(" ")
    name = name.lower()
    if name in ("/help", "/?"):
        return Action("help", text=HELP)
    if name == "/quit":
        return Action("quit")
    if name == "/use":
        room = rest.strip()
        return Action("use", room=room) if room else Action("error", text="Cú pháp: /use <phòng>")
    if name == "/members":
        room = rest.strip() or current_room
        if not room:
            return Action("error", text="Cú pháp: /members <phòng>")
        return Action("send", "LIST_MEMBERS", {"room": room})
    if name not in _SIMPLE:
        return Action("error", text=f"Lệnh lạ {name}. Gõ /help để xem các lệnh")

    command, params = _SIMPLE[name]
    payload = {}
    for i, param in enumerate(params):
        if param.endswith("*"):           # lấy hết phần còn lại, giữ nguyên khoảng trắng bên trong
            value = rest.strip()
            rest = ""
        else:
            value, _, rest = rest.strip().partition(" ")
        if not value:
            usage = " ".join(f"<{p.rstrip('*')}>" for p in params)
            return Action("error", text=f"Cú pháp: {name} {usage}")
        payload[param.rstrip("*")] = value
    return Action("send", command, payload)
