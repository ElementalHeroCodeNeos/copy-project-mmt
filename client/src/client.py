"""Client CLI (Khôi) — bước 20: bản tối thiểu để kiểm tra Docker và mạng.

Kết nối tới server theo biến môi trường, gửi một PING, in response rồi thoát.
Bước 21 thay bằng kết nối thật (luồng đọc, PING nền, phát hiện mất kết nối).
"""

import os
import socket
import sys

from shared import protocol

HOST = os.getenv("CLIENT_TARGET_HOST", "localhost")  # trong Docker: "server" (tên service)
PORT = int(os.getenv("CLIENT_TARGET_PORT", "5000"))


def main() -> None:
    try:
        sock = socket.create_connection((HOST, PORT), timeout=10)
    except OSError as exc:
        print(f"Không kết nối được tới {HOST}:{PORT}: {exc}")
        sys.exit(1)
    with sock:
        print(f"Đã kết nối tới {HOST}:{PORT}")
        sock.sendall(protocol.encode({"command": protocol.PING, "payload": {}}))
        buf, lines = protocol.FrameBuffer(protocol.DEFAULT_MAX_BYTES), []
        while not lines:
            data = sock.recv(4096)
            if not data:
                print("Server đã đóng kết nối")
                sys.exit(1)
            lines = buf.feed(data)
        print("Server trả:", protocol.decode(lines[0]))


if __name__ == "__main__":
    main()
