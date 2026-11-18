"""Client CLI (Khôi): lệnh `/…`, hiển thị tin của nhiều phòng.

Chạy: `docker compose run --rm client` (hoặc trên máy: `PYTHONPATH=. python client/src/client.py`).
Gõ /help để xem lệnh.

Luồng (xem connection.py): luồng chính đọc bàn phím; luồng đọc socket gọi `on_message`; luồng PING.
Dữ liệu hai luồng cùng dùng nằm trong `State`, có khoá:
- `sent`: requestId → request đã gửi, để khớp response với lệnh (ví dụ in lại nội dung tin riêng).
- `current_room`: phòng hiện tại; luồng chính đọc khi gửi tin, luồng đọc đổi khi vào/tạo/rời phòng.
"""

import os
import sys
import threading

from commands import HELP, parse
from connection import Connection
from display import format_message

HOST = os.getenv("CLIENT_TARGET_HOST", "localhost")  # trong Docker: "server"
PORT = int(os.getenv("CLIENT_TARGET_PORT", "5000"))
PING_INTERVAL_SEC = float(os.getenv("PING_INTERVAL_SEC", "30"))
READ_TIMEOUT_SEC = float(os.getenv("READ_TIMEOUT_SEC", "90"))

_print_lock = threading.Lock()  # luồng chính và luồng đọc cùng in: mỗi lần in trọn vẹn
_quit_done = threading.Event()  # luồng đọc báo cho luồng chính: đã nhận QUIT_RESPONSE


def out(text: str) -> None:
    with _print_lock:
        print(text, flush=True)


class State:
    def __init__(self):
        self._lock = threading.Lock()
        self.current_room: str | None = None
        self.sent: dict[str, dict] = {}

    def remember(self, rid: str, request: dict) -> None:
        with self._lock:
            self.sent[rid] = request

    def take(self, rid: str | None) -> dict | None:
        with self._lock:
            return self.sent.pop(rid, None) if rid else None

    def get_room(self) -> str | None:
        with self._lock:
            return self.current_room

    def set_room(self, room: str | None) -> None:
        with self._lock:
            self.current_room = room

    def room_left(self, room: str) -> None:
        with self._lock:
            if self.current_room == room:
                self.current_room = None


state = State()


def update_state(msg: dict) -> None:
    """Đổi phòng hiện tại theo response thành công."""
    if msg.get("code") not in (200, 201):
        return
    command, d = msg.get("command"), msg.get("data", {})
    if command in ("CREATE_ROOM_RESPONSE", "JOIN_ROOM_RESPONSE"):
        state.set_room(d.get("room"))
    elif command == "LEAVE_ROOM_RESPONSE":
        state.room_left(d.get("room"))
    elif command == "LOGIN_RESPONSE" and d.get("rooms") and state.get_room() is None:
        state.set_room(d["rooms"][0])


def on_message(msg: dict) -> None:
    if msg.get("command") == "QUIT_RESPONSE":
        _quit_done.set()
    sent = state.take(msg.get("requestId"))
    update_state(msg)
    text = format_message(msg, sent)
    if text:
        out(text)
    if msg.get("command") in ("CREATE_ROOM_RESPONSE", "JOIN_ROOM_RESPONSE", "LEAVE_ROOM_RESPONSE") \
            and msg.get("code") in (200, 201):
        out(f"(phòng hiện tại: {state.get_room() or 'chưa chọn'})")


def on_disconnect(reason: str) -> None:
    out(f"*** Mất kết nối tới server: {reason}")
    os._exit(1)  # luồng chính đang chặn ở input(), không dừng được bằng cách khác


def main() -> None:
    conn = Connection(HOST, PORT, on_message, on_disconnect, PING_INTERVAL_SEC, READ_TIMEOUT_SEC)
    try:
        conn.connect()
    except OSError as exc:
        out(f"Không kết nối được tới {HOST}:{PORT}: {exc}")
        sys.exit(1)
    out(f"Đã kết nối tới {HOST}:{PORT}. Gõ /help để xem lệnh.")
    for line in sys.stdin:
        action = parse(line, state.get_room())
        if action.kind == "send":
            # Ghi nhớ TRƯỚC khi gửi: response có thể về (ở luồng đọc) trước khi request() trả về.
            rid = conn.next_id()
            state.remember(rid, {"command": action.command, "payload": action.payload})
            conn.request(action.command, action.payload, rid=rid)
        elif action.kind == "use":
            state.set_room(action.room)
            out(f"(phòng hiện tại: {action.room})")
        elif action.kind == "help":
            out(HELP)
        elif action.kind == "error":
            out("!! " + action.text)
        elif action.kind == "quit":
            break
    # Chờ QUIT_RESPONSE (tối đa 5 s) rồi mới đóng. Server xử lý lệnh của một kết nối theo đúng thứ
    # tự, nên khi QUIT_RESPONSE về thì response của mọi lệnh gửi trước đó cũng đã về và đã được in.
    if conn.request("QUIT"):
        _quit_done.wait(5)
    conn.close()
    out("Đã thoát.")


if __name__ == "__main__":
    main()
