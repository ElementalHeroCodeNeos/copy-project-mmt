"""Test độ bền (Huy, bước 11): nhiều client cùng lúc, client bị kill -9, client im lặng, rác.

Mỗi test chạy một server thật (xem ServerHarness trong test_server.py).

    python -m unittest tests.test_robustness -v
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_server import PASSWORD, ROOT, Client, ServerHarness  # noqa: E402

from shared.protocol import encode  # noqa: E402

N_CLIENTS = 30

# Client chạy trong tiến trình riêng để bị kill thật (kill -9 trên Linux, TerminateProcess
# trên Windows): hệ điều hành đóng socket, server không nhận được QUIT nào.
CHILD_CLIENT = r"""
import socket, sys, time
sys.path.insert(0, sys.argv[3])
from shared.protocol import FrameBuffer, decode, encode
s = socket.create_connection(("127.0.0.1", int(sys.argv[1])))
s.sendall(encode({"command": "LOGIN", "payload": {"username": sys.argv[2], "password": sys.argv[4]}}))
buf = FrameBuffer(1 << 20); lines = []
while not lines:
    lines = buf.feed(s.recv(4096))
print(decode(lines[0])["code"], flush=True)
time.sleep(60)
"""


class ManyClientsTest(ServerHarness):
    """30 client đăng nhập và nhắn tin CÙNG LÚC (mỗi client một luồng)."""

    ENV = {"MAX_CLIENTS": "50", "READ_TIMEOUT_SEC": "60", "MAX_TEXT_CHARS": "2000"}

    def test_concurrent_logins_and_room_messages(self):
        names = [f"user{i:02d}" for i in range(N_CLIENTS)]
        clients: dict[str, Client] = {}
        errors: list[str] = []
        lock = threading.Lock()
        all_ready = threading.Barrier(N_CLIENTS)
        joined = threading.Barrier(N_CLIENTS)

        def run(name):
            try:
                c = Client(self.port)
                with lock:
                    clients[name] = c
                # 30 luồng cùng băm mật khẩu: trên máy bận, một client có thể chờ quá 3 s
                # (thời gian chờ mặc định của test), nên cho chờ tới 30 s.
                assert self.register(c, name, timeout=30)["code"] == 201
                assert self.send_login(c, name, timeout=30)["code"] == 200
                if name == names[0]:
                    assert self.request(c, "CREATE_ROOM", {"room": "lab"})["code"] == 201
                all_ready.wait(timeout=60)  # mọi người online và phòng đã có
                if name != names[0]:         # 29 người cùng JOIN_ROOM một lúc
                    assert self.request(c, "JOIN_ROOM", {"room": "lab"}, timeout=30)["code"] == 200
                joined.wait(timeout=60)      # mọi người đã vào phòng rồi mới nhắn
                c.send(encode({"command": "ROOM_MSG", "requestId": name,
                               "payload": {"room": "lab", "content": f"chào từ {name}"}}))
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors.append(f"{name}: {exc!r}")
                all_ready.abort()
                joined.abort()

        start = time.monotonic()
        threads = [threading.Thread(target=run, args=(n,)) for n in names]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.clients.extend(clients.values())
        self.assertEqual(errors, [])
        login_time = time.monotonic() - start

        # Mỗi client nhận: 1 ROOM_MSG_RESPONSE của mình + N NOTIFY_ROOM_MSG (kể cả của mình).
        # Mỗi dòng phải là JSON hợp lệ: nếu hai luồng ghi xen vào cùng một socket thì decode lỗi.
        expected = {f"chào từ {n}" for n in names}
        for name, c in clients.items():
            got, responses = set(), 0
            while len(got) < N_CLIENTS or responses < 1:
                msg = c.recv_msg(timeout=10)
                if msg["command"] == "ROOM_MSG_RESPONSE":
                    self.assertEqual((msg["requestId"], msg["code"]), (name, 200))
                    responses += 1
                elif msg["command"] == "NOTIFY_ROOM_MSG":
                    got.add(msg["data"]["content"])
            self.assertEqual(got, expected, name)
        total = time.monotonic() - start
        print(f"\n  [đo] {N_CLIENTS} client: đăng ký + đăng nhập + gửi xong sau {login_time:.2f} s, "
              f"mỗi client nhận đủ {N_CLIENTS} tin sau {total:.2f} s", file=sys.stderr)
        self.assertIsNone(self.proc.poll(), "server đã chết")


class FailureTest(ServerHarness):
    """Client bị kill, im lặng, gửi rác: server dọn phiên, báo offline, vẫn phục vụ người khác."""

    ENV = {"MAX_CLIENTS": "5", "READ_TIMEOUT_SEC": "2"}

    def test_killed_client_process_is_cleaned_up(self):
        kiet, huy = self.roommates_online()
        kiet.recv_msg()  # NOTIFY_ONLINE của huy (kết nối trong test)
        self.request(huy, "QUIT", {})  # huy trong test thoát; tiến trình con đăng nhập lại là huy
        self.assertEqual(kiet.recv_msg()["command"], "NOTIFY_OFFLINE")

        child = subprocess.Popen(
            [sys.executable, "-c", CHILD_CLIENT, str(self.port), "huy", str(ROOT), PASSWORD],
            stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "200")  # tiến trình con đã đăng nhập
            self.assertEqual(kiet.recv_msg(), {"command": "NOTIFY_ONLINE", "data": {"username": "huy"}})
            child.kill()  # kill -9: không QUIT, không đóng socket lịch sự
            child.wait()
            self.assertEqual(kiet.recv_msg(timeout=5),
                             {"command": "NOTIFY_OFFLINE", "data": {"username": "huy"}})
        finally:
            child.kill()
            child.stdout.close()
        self.login("huy", register=False)  # phiên đã dọn: đăng nhập lại được ngay
        self.assertIsNone(self.proc.poll(), "server đã chết")

    def test_silent_logged_in_client_times_out_and_goes_offline(self):
        kiet, huy = self.roommates_online()
        kiet.recv_msg()  # NOTIFY_ONLINE của huy
        # kiet gửi PING đều để không bị timeout; huy im lặng hoàn toàn.
        deadline = time.monotonic() + 6
        offline = None
        while time.monotonic() < deadline and offline is None:
            kiet.send(encode({"command": "PING", "payload": {}}))
            try:
                while True:
                    msg = kiet.recv_msg(timeout=0.5)
                    if msg["command"] == "NOTIFY_OFFLINE":
                        offline = msg
                        break
            except TimeoutError:
                pass
        self.assertEqual(offline, {"command": "NOTIFY_OFFLINE", "data": {"username": "huy"}})
        self.assertTrue(huy.wait_closed(1))

    def test_random_garbage_does_not_hurt_others(self):
        other = self.login("kiet")
        bad = self.connect()
        bad.sock.settimeout(5)
        try:
            bad.send(os.urandom(200_000))  # 200 KB byte ngẫu nhiên, có cả \n lẫn byte không UTF-8
        except OSError:
            pass  # server có thể đã đóng giữa chừng (413)
        self.assertTrue(bad.wait_closed(10), "server không đóng kết nối gửi rác")
        msg = self.request(other, "LIST_ONLINE", {})
        self.assertEqual((msg["code"], msg["data"]), (200, {"users": ["kiet"]}))
        self.assertIsNone(self.proc.poll(), "server đã chết")


if __name__ == "__main__":
    import unittest
    unittest.main()
