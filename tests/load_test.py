"""Test tải (Huy, bước 11): N client cùng đăng ký, đăng nhập, PING, giữ kết nối, rồi QUIT.

Chạy trên máy host khi server đang chạy (ví dụ `docker compose up -d server`):

    python tests/load_test.py              # mặc định 50 client tới localhost:5000
    N_CLIENTS=90 python tests/load_test.py

Không phải unit test (tên không bắt đầu bằng test_ nên `unittest discover` bỏ qua).
Mỗi lần chạy dùng tên tài khoản mới (hậu tố ngẫu nhiên), không đụng tài khoản thật.
"""

import os
import secrets
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared.protocol import FrameBuffer, decode, encode  # noqa: E402

HOST = os.getenv("CLIENT_TARGET_HOST", "localhost")
PORT = int(os.getenv("CLIENT_TARGET_PORT", "5000"))
N = int(os.getenv("N_CLIENTS", "50"))
HOLD_SEC = 2.0
PASSWORD = "loadtest123"
RUN_ID = secrets.token_hex(2)  # 4 ký tự hex: tên tài khoản ≤ 20 ký tự

results: list[tuple[int, bool, float, str]] = []
lock = threading.Lock()


def request(sock, buf: FrameBuffer, pending: list, msg: dict) -> dict:
    """Gửi một request, đọc tới khi có response (bỏ qua push xen giữa)."""
    sock.sendall(encode(msg))
    want = msg["command"] + "_RESPONSE"
    while True:
        while not pending:
            data = sock.recv(4096)
            if not data:
                raise EOFError("server đóng kết nối")
            pending += buf.feed(data)
        reply = decode(pending.pop(0))
        if reply["command"] in (want, "ERROR"):
            return reply


def client(i: int) -> None:
    name = f"lt{RUN_ID}_{i:03d}"
    start = time.perf_counter()
    try:
        with socket.create_connection((HOST, PORT), timeout=30) as s:
            buf, pending = FrameBuffer(1 << 20), []
            auth = {"username": name, "password": PASSWORD}
            r = request(s, buf, pending, {"command": "REGISTER", "payload": auth})
            assert r["code"] == 201, r
            r = request(s, buf, pending, {"command": "LOGIN", "payload": auth})
            assert r["code"] == 200, r
            r = request(s, buf, pending, {"command": "PING", "requestId": str(i), "payload": {}})
            assert (r["code"], r.get("requestId")) == (200, str(i)), r
            latency = time.perf_counter() - start
            time.sleep(HOLD_SEC)  # giữ kết nối để chồng lên các client khác
            request(s, buf, pending, {"command": "QUIT", "payload": {}})
        with lock:
            results.append((i, True, latency, ""))
    except Exception as exc:  # noqa: BLE001
        with lock:
            results.append((i, False, time.perf_counter() - start, repr(exc)))


def main() -> None:
    print(f"{N} client -> {HOST}:{PORT} (REGISTER + LOGIN + PING, giữ {HOLD_SEC} s, QUIT)")
    t0 = time.perf_counter()
    threads = [threading.Thread(target=client, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total = time.perf_counter() - t0
    ok = [r for r in results if r[1]]
    fail = [r for r in results if not r[1]]
    lat = sorted(r[2] for r in ok)
    print(f"{len(ok)}/{N} thành công trong {total:.2f} s")
    if lat:
        print(f"thời gian tới khi nhận PING_RESPONSE: nhỏ nhất {lat[0]:.2f} s, "
              f"trung vị {lat[len(lat) // 2]:.2f} s, lớn nhất {lat[-1]:.2f} s")
    for i, _, _, err in fail[:5]:
        print(f"  client {i} lỗi: {err}")
    sys.exit(0 if not fail else 1)


if __name__ == "__main__":
    main()
