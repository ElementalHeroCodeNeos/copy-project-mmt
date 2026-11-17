"""Công cụ test bằng tay, thay cho `nc` (máy Windows thường không có nc).

    python scripts/nc.py [host] [port]      # mặc định localhost, SERVER_PORT hoặc 5000

Mỗi dòng gõ vào được gửi nguyên văn kèm \\n (gửi được cả dữ liệu rác).
Mọi dòng server gửi về được in ra với tiền tố "<< ". Thoát: Ctrl+C (hoặc Ctrl+Z rồi
Enter trên Windows, Ctrl+D trên Linux/macOS).
"""

import os
import socket
import sys
import threading


def _receive(sock: socket.socket) -> None:
    buffer = b""
    while True:
        try:
            data = sock.recv(4096)
        except OSError as exc:
            print(f"[mất kết nối: {exc}]", flush=True)
            break
        if not data:
            print("[server đã đóng kết nối]", flush=True)
            break
        buffer += data
        *lines, buffer = buffer.split(b"\n")
        for line in lines:
            print("<<", line.decode("utf-8", errors="replace"), flush=True)
    os._exit(0)  # thoát cả chương trình, kể cả khi luồng chính đang chờ bàn phím


def main() -> None:
    # Console Windows và Git Bash mặc định không dùng UTF-8: ép UTF-8 để tiếng Việt không lỗi.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")

    host = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else int(os.getenv("SERVER_PORT", "5000"))

    sock = socket.create_connection((host, port))
    print(f"[đã kết nối {host}:{port}]", flush=True)
    threading.Thread(target=_receive, args=(sock,), daemon=True).start()

    try:
        while line := sys.stdin.readline():
            sock.sendall(line.rstrip("\r\n").encode("utf-8") + b"\n")
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        print(f"[gửi thất bại: {exc}]", flush=True)
    sock.close()


if __name__ == "__main__":
    main()
