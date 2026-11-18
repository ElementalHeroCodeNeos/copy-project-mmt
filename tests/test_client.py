"""Test cho client (Khôi): kết nối, luồng đọc, PING nền, phát hiện mất kết nối (bước 21).

    python -m unittest tests.test_client -v
"""

import os
import queue
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client" / "src"))
from test_server import ROOT, ServerHarness  # noqa: E402

from commands import parse  # noqa: E402
from connection import Connection  # noqa: E402
from display import format_message  # noqa: E402

CLIENT = ROOT / "client" / "src" / "client.py"


class Recorder:
    """Ghi lại message và lý do mất kết nối mà Connection báo về."""

    def __init__(self):
        self.messages: queue.Queue = queue.Queue()
        self.lost: queue.Queue = queue.Queue()

    def on_message(self, msg):
        self.messages.put(msg)

    def on_disconnect(self, reason):
        self.lost.put(reason)


class ConnectionTest(ServerHarness):
    ENV = {"READ_TIMEOUT_SEC": "2"}  # server ngắt client im lặng sau 2 s

    def make(self, ping_interval=30, read_timeout=90, port=None):
        rec = Recorder()
        conn = Connection("127.0.0.1", port or self.port, rec.on_message, rec.on_disconnect,
                          ping_interval, read_timeout)
        conn.connect()
        self.addCleanup(conn.close)
        return conn, rec

    def test_request_gets_response_with_request_id(self):
        conn, rec = self.make()
        rid = conn.request("PING")
        msg = rec.messages.get(timeout=3)
        self.assertEqual((msg["command"], msg["requestId"]), ("PING_RESPONSE", rid))

    def test_background_ping_keeps_connection_alive(self):
        """Không gõ gì 3,5 s (server timeout 2 s) nhưng PING nền giữ kết nối."""
        conn, rec = self.make(ping_interval=0.5)
        time.sleep(3.5)
        self.assertTrue(rec.lost.empty(), "bị ngắt dù có PING nền")
        conn.request("LIST_ONLINE")
        cmds = set()
        while "LIST_ONLINE_RESPONSE" not in cmds:
            cmds.add(rec.messages.get(timeout=3)["command"])

    def test_without_ping_server_closes_and_client_notices(self):
        conn, rec = self.make(ping_interval=100)
        self.assertIn("server đã đóng", rec.lost.get(timeout=5))
        self.assertFalse(conn.connected)

    def test_server_killed_is_detected(self):
        conn, rec = self.make()
        self.proc.kill()
        self.assertIsInstance(rec.lost.get(timeout=5), str)
        self.assertFalse(conn.send({"command": "PING", "payload": {}}))

    def test_silent_server_times_out(self):
        """Server nhận kết nối nhưng không bao giờ gửi gì: client báo mất kết nối sau read_timeout."""
        listener = socket.create_server(("127.0.0.1", 0))
        self.addCleanup(listener.close)
        accepted = []
        threading.Thread(target=lambda: accepted.append(listener.accept()), daemon=True).start()
        start = time.monotonic()
        conn, rec = self.make(ping_interval=100, read_timeout=1,
                              port=listener.getsockname()[1])
        self.assertIn("không nhận được gì", rec.lost.get(timeout=5))
        self.assertLess(time.monotonic() - start, 3)
        for s, _ in accepted:
            s.close()

    def test_quit_then_close_does_not_report_disconnect(self):
        conn, rec = self.make()
        conn.request("QUIT")
        self.assertEqual(rec.messages.get(timeout=3)["command"], "QUIT_RESPONSE")
        conn.close()
        time.sleep(0.3)
        self.assertTrue(rec.lost.empty())

    def test_concurrent_sends_do_not_interleave(self):
        """Nhiều luồng cùng gửi qua một Connection: server nhận đủ, không dòng nào hỏng."""
        conn, rec = self.make()
        threads = [threading.Thread(target=lambda: [conn.request("PING") for _ in range(50)])
                   for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        got = [rec.messages.get(timeout=5) for _ in range(200)]
        self.assertTrue(all(m["command"] == "PING_RESPONSE" for m in got))
        self.assertEqual(len({m["requestId"] for m in got}), 200)


class ParseTest(unittest.TestCase):
    """commands.parse (bước 22)."""

    def test_plain_text_goes_to_current_room(self):
        a = parse("  chào cả nhóm  ", "lab")
        self.assertEqual((a.kind, a.command, a.payload),
                         ("send", "ROOM_MSG", {"room": "lab", "content": "  chào cả nhóm  "}))
        self.assertEqual(parse("chào", None).kind, "error")  # chưa chọn phòng

    def test_commands(self):
        cases = {
            "/login huy matkhau123": ("LOGIN", {"username": "huy", "password": "matkhau123"}),
            "/join lab": ("JOIN_ROOM", {"room": "lab"}),
            "/rooms": ("LIST_ROOMS", {}),
            "/msg kiet tối nay  họp nhé": ("PRIVATE_MSG", {"to": "kiet", "content": "tối nay  họp nhé"}),
            "/members": ("LIST_MEMBERS", {"room": "lab"}),  # mặc định phòng hiện tại
        }
        for line, (command, payload) in cases.items():
            a = parse(line, "lab")
            self.assertEqual((a.kind, a.command, a.payload), ("send", command, payload), line)

    def test_local_and_errors(self):
        self.assertEqual((parse("/use web", "lab").kind, parse("/use web", "lab").room), ("use", "web"))
        self.assertEqual(parse("/quit", None).kind, "quit")
        self.assertEqual(parse("", None).kind, "none")
        for bad in ("/join", "/msg kiet", "/khong_co", "/login huy"):
            self.assertEqual(parse(bad, "lab").kind, "error", bad)


class DisplayTest(unittest.TestCase):
    """display.format_message (bước 22)."""

    def test_room_and_private_messages_have_prefix(self):
        msg = {"command": "NOTIFY_ROOM_MSG",
               "data": {"room": "lab", "from": "kiet", "content": "hi", "ts": "2026-11-15T09:00:00Z"}}
        self.assertRegex(format_message(msg), r"^\[\d\d:\d\d\] \[lab\] kiet: hi$")
        msg = {"command": "NOTIFY_PRIVATE_MSG",
               "data": {"from": "kiet", "to": "huy", "content": "hi", "ts": "2026-11-15T09:00:00Z"}}
        self.assertIn("[riêng] kiet → bạn: hi", format_message(msg))

    def test_private_msg_response_shows_what_was_sent(self):
        msg = {"command": "PRIVATE_MSG_RESPONSE", "code": 200, "data": {"ts": "2026-11-15T09:00:00Z"}}
        sent = {"command": "PRIVATE_MSG", "payload": {"to": "huy", "content": "hi"}}
        self.assertIn("[riêng] bạn → huy: hi", format_message(msg, sent))

    def test_errors_and_silent_responses(self):
        msg = {"command": "JOIN_ROOM_RESPONSE", "code": 404, "message": "Phòng x không tồn tại"}
        self.assertEqual(format_message(msg), "!! Phòng x không tồn tại (404)")
        self.assertIsNone(format_message({"command": "ROOM_MSG_RESPONSE", "code": 200, "data": {}}))
        self.assertIsNone(format_message({"command": "PING_RESPONSE", "code": 200, "data": {}}))


class ClientProgramTest(ServerHarness):
    """Chạy hai tiến trình client.py thật, gõ lệnh qua stdin (bước 22)."""

    ENV = {"READ_TIMEOUT_SEC": "30"}

    def run_client(self, lines: list[str], delay: float = 0) -> subprocess.Popen:
        env = dict(os.environ, CLIENT_TARGET_HOST="127.0.0.1", CLIENT_TARGET_PORT=str(self.port),
                   PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8")
        proc = subprocess.Popen([sys.executable, "-u", str(CLIENT)], env=env, text=True,
                                encoding="utf-8", stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        self.addCleanup(proc.kill)

        def feed():
            for line in lines:
                if line.startswith("#sleep "):
                    time.sleep(float(line.split()[1]))
                    continue
                proc.stdin.write(line + "\n")
                proc.stdin.flush()
            proc.stdin.close()

        threading.Thread(target=feed, daemon=True).start()
        return proc

    def test_two_clients_chat_in_room_and_private(self):
        khoi = self.run_client(["/register khoi matkhau123", "/login khoi matkhau123",
                                "/create lab", "#sleep 3", "chào huy", "#sleep 1.5", "/quit"])
        huy = self.run_client(["#sleep 1.5", "/register huy matkhau123", "/login huy matkhau123",
                               "/join lab", "#sleep 2", "/msg khoi nhận rồi", "#sleep 1", "/quit"])
        # Không dùng communicate(): nó đóng stdin ngay, client tưởng người dùng đã gõ hết và thoát.
        khoi.wait(timeout=20)
        huy.wait(timeout=20)
        out_khoi, out_huy = khoi.stdout.read(), huy.stdout.read()
        khoi.stdout.close()
        huy.stdout.close()
        self.assertIn("Đã tạo phòng lab", out_khoi)
        self.assertIn("* huy vào phòng lab", out_khoi)
        self.assertRegex(out_huy, r"\[lab\] khoi: chào huy")      # tin phòng có tiền tố phòng
        self.assertIn("[riêng] huy → bạn: nhận rồi", out_khoi)    # tin riêng
        self.assertIn("[riêng] bạn → khoi: nhận rồi", out_huy)
        for out in (out_khoi, out_huy):  # QUIT là thoát bình thường, không phải mất kết nối
            self.assertIn("Đã thoát.", out)
            self.assertNotIn("Mất kết nối", out)


if __name__ == "__main__":
    unittest.main()
