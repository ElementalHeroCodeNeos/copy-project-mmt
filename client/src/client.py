"""Client CLI (Khôi) — bước 21: kết nối thật, gõ JSON thô.

Mỗi dòng gõ vào là một message JSON gửi thẳng lên server (thêm requestId nếu thiếu); mọi message
server gửi về được in ra. Gõ `/quit` để thoát. Bước 22 thay bằng lệnh dạng `/join lab`.
"""

import json
import os
import sys
import threading
import time

from connection import Connection

HOST = os.getenv("CLIENT_TARGET_HOST", "localhost")  # trong Docker: "server"
PORT = int(os.getenv("CLIENT_TARGET_PORT", "5000"))
PING_INTERVAL_SEC = float(os.getenv("PING_INTERVAL_SEC", "30"))
READ_TIMEOUT_SEC = float(os.getenv("READ_TIMEOUT_SEC", "90"))

_print_lock = threading.Lock()  # luồng chính và luồng đọc cùng in: in từng dòng trọn vẹn


def out(text: str) -> None:
    with _print_lock:
        print(text, flush=True)


def on_message(msg: dict) -> None:
    if msg.get("command") == "PING_RESPONSE":
        return  # nhịp tim, không cần hiện
    out("<< " + json.dumps(msg, ensure_ascii=False))


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
    out(f"Đã kết nối tới {HOST}:{PORT}. Gõ một dòng JSON, hoặc /quit để thoát.")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line == "/quit":
            break
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            out("!! Không phải JSON")
            continue
        if isinstance(msg, dict):
            msg.setdefault("requestId", str(time.monotonic_ns()))
        conn.send(msg)
    conn.request("QUIT")
    time.sleep(0.3)  # chờ QUIT_RESPONSE tới rồi mới đóng
    conn.close()


if __name__ == "__main__":
    main()
