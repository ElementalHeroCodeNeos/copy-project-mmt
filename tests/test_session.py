"""Unit test cho server/src/session.py (khung bước 4). Dùng socket.socketpair(), không cần server.

    python -m unittest tests.test_session -v
"""

import socket
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server" / "src"))

import session as session_mod  # noqa: E402
from session import Session, SessionRegistry, broadcast  # noqa: E402
from shared.protocol import FrameBuffer, decode  # noqa: E402


def make_session() -> tuple[Session, socket.socket]:
    """Một Session (phía server) và đầu kia của kết nối (phía client)."""
    server_side, client_side = socket.socketpair()
    return Session(server_side, ("test", 0)), client_side


def read_messages(sock: socket.socket, count: int, timeout: float = 5) -> list[dict]:
    sock.settimeout(timeout)
    fb, out = FrameBuffer(1 << 20), []
    while len(out) < count:
        data = sock.recv(65536)
        if not data:
            break
        out += [decode(line) for line in fb.feed(data)]
    return out


class SessionSendTest(unittest.TestCase):
    def setUp(self):
        self.to_close: list = []

    def tearDown(self):
        for x in self.to_close:
            x.close()

    def pair(self):
        s, c = make_session()
        self.to_close += [s, c]
        return s, c

    def test_send_delivers_one_line(self):
        s, c = self.pair()
        self.assertTrue(s.send({"command": "PING"}))
        self.assertEqual(read_messages(c, 1), [{"command": "PING"}])

    def test_send_after_close_returns_false(self):
        s, _ = self.pair()
        s.close()
        s.close()  # gọi lần hai không lỗi
        self.assertFalse(s.send({"command": "PING"}))

    def test_stuck_client_send_times_out_and_shuts_down(self):
        # Client không bao giờ đọc: bộ đệm đầy, sendall phải bỏ cuộc sau SEND_TIMEOUT_SEC.
        old = session_mod.SEND_TIMEOUT_SEC
        session_mod.SEND_TIMEOUT_SEC = 0.5
        try:
            s, _ = self.pair()
        finally:
            session_mod.SEND_TIMEOUT_SEC = old
        start = time.monotonic()
        ok = True
        while ok and time.monotonic() - start < 10:
            ok = s.send({"command": "NOTIFY_X", "data": {"x": "a" * 100_000}})
        self.assertFalse(ok, "gửi tới client đứng hình không bao giờ thất bại")
        self.assertTrue(s.broken)
        self.assertFalse(s.send({"command": "PING"}))  # các lần sau trả False ngay

    @unittest.skipUnless(sys.platform.startswith("linux"),
                         "Chỉ Linux: shutdown() đánh thức luồng đang chờ đọc (Windows thì không)")
    def test_failed_send_wakes_reader_thread(self):
        # Giống server: luồng đọc của client đang chờ select(); một luồng khác gửi thất
        # bại -> Session shutdown socket -> luồng đọc thức dậy, nhận EOF để tự dọn phiên.
        import select
        s, _ = self.pair()
        woke = {}

        def reader():
            start = time.monotonic()
            readable, _, _ = select.select([s.sock], [], [], 10)
            woke["data"] = s.sock.recv(10) if readable else None
            woke["after"] = time.monotonic() - start

        t = threading.Thread(target=reader)
        t.start()
        time.sleep(0.3)
        s.broken = False
        s._shutdown()  # điều Session.send() làm khi gửi thất bại
        t.join(5)
        self.assertEqual(woke.get("data"), b"")
        self.assertLess(woke["after"], 2)

    def test_shutdown_sends_eof_to_client(self):
        s, c = self.pair()
        s._shutdown()
        c.settimeout(2)
        self.assertEqual(c.recv(10), b"")  # client thấy server đã đóng

    def test_concurrent_sends_do_not_interleave(self):
        # 4 luồng cùng gửi message lớn tới một client; nhờ send_lock, mọi dòng nhận
        # được vẫn là JSON nguyên vẹn (không bị trộn giữa hai message).
        s, c = self.pair()
        threads_n, per_thread = 4, 50
        payload = {n: str(n) * 20_000 for n in range(threads_n)}

        def worker(n):
            for i in range(per_thread):
                s.send({"command": "NOTIFY_X", "data": {"n": n, "i": i, "pad": payload[n]}})

        received = []
        reader = threading.Thread(target=lambda: received.extend(
            read_messages(c, threads_n * per_thread, timeout=20)))
        reader.start()
        workers = [threading.Thread(target=worker, args=(n,)) for n in range(threads_n)]
        for w in workers:
            w.start()
        for w in workers:
            w.join()
        reader.join()
        self.assertEqual(len(received), threads_n * per_thread)
        for m in received:
            self.assertEqual(m["data"]["pad"], payload[m["data"]["n"]])


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.reg = SessionRegistry()
        self.pairs = [make_session() for _ in range(4)]
        self.s = [p[0] for p in self.pairs]

    def tearDown(self):
        for s, c in self.pairs:
            s.close()
            c.close()

    def test_bind_sets_username_and_rejects_duplicates(self):
        self.assertTrue(self.reg.bind("kiet", self.s[0]))
        self.assertEqual(self.s[0].username, "kiet")
        self.assertFalse(self.reg.bind("kiet", self.s[1]))     # tài khoản đang online
        self.assertIsNone(self.s[1].username)
        self.assertFalse(self.reg.bind("khoi", self.s[0]))     # kết nối đã đăng nhập
        self.assertIs(self.reg.get("kiet"), self.s[0])
        self.assertTrue(self.reg.is_online("kiet"))

    def test_unbind_only_matching_session(self):
        self.reg.bind("kiet", self.s[0])
        self.assertFalse(self.reg.unbind("kiet", self.s[1]))   # phiên khác: không gỡ
        self.assertTrue(self.reg.is_online("kiet"))
        self.assertTrue(self.reg.unbind("kiet", self.s[0]))
        self.assertIsNone(self.s[0].username)
        self.assertFalse(self.reg.is_online("kiet"))
        self.assertFalse(self.reg.unbind("kiet", self.s[0]))   # gỡ lần hai: False
        self.assertTrue(self.reg.bind("kiet", self.s[1]))      # đăng nhập lại được

    def test_returned_lists_are_copies(self):
        self.reg.bind("b", self.s[0])
        self.reg.bind("a", self.s[1])
        names = self.reg.online_usernames()
        self.assertEqual(names, ["a", "b"])
        names.clear()
        self.assertEqual(self.reg.online_usernames(), ["a", "b"])

    def test_sessions_of_skips_offline_and_duplicates(self):
        self.reg.bind("a", self.s[0])
        self.reg.bind("b", self.s[1])
        self.assertEqual(self.reg.sessions_of(["a", "x", "b", "a"]), [self.s[0], self.s[1]])

    def test_concurrent_bind_same_username_only_one_wins(self):
        # 50 luồng cùng lúc đăng nhập một tài khoản: đúng 1 luồng thành công.
        n = 50
        pairs = [make_session() for _ in range(n)]
        barrier = threading.Barrier(n)
        results = [None] * n

        def worker(i):
            barrier.wait()  # cho mọi luồng xuất phát cùng lúc
            results[i] = self.reg.bind("kiet", pairs[i][0])

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        try:
            self.assertEqual(results.count(True), 1)
            winner = pairs[results.index(True)][0]
            self.assertIs(self.reg.get("kiet"), winner)
            self.assertEqual(sum(p[0].username == "kiet" for p in pairs), 1)
        finally:
            for s, c in pairs:
                s.close()
                c.close()


class BroadcastTest(unittest.TestCase):
    def test_broadcast_reaches_online_and_skips_dead(self):
        reg = SessionRegistry()
        pairs = [make_session() for _ in range(3)]
        try:
            for name, (s, _) in zip(["a", "b", "c"], pairs):
                reg.bind(name, s)
            pairs[1][0].close()  # b chết (socket đã đóng) nhưng vẫn trong registry
            msg = {"command": "NOTIFY_ROOM_MSG", "data": {"content": "hi"}}
            broadcast(["a", "b", "c", "offline"], msg, reg)
            self.assertEqual(read_messages(pairs[0][1], 1), [msg])
            self.assertEqual(read_messages(pairs[2][1], 1), [msg])
        finally:
            for s, c in pairs:
                s.close()
                c.close()


if __name__ == "__main__":
    unittest.main()
