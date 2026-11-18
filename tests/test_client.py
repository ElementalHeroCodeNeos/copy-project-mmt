"""Test cho client (Khôi): kết nối, luồng đọc, PING nền, phát hiện mất kết nối (bước 21).

    python -m unittest tests.test_client -v
"""

import queue
import socket
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client" / "src"))
from test_server import ServerHarness  # noqa: E402

from connection import Connection  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
