"""Unit test cho server/src/presence.py (bước 8): cleanup, báo online/offline.

Dùng session giả (không cần socket) và database trong bộ nhớ.

    python -m unittest tests.test_presence -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server" / "src"))

import handlers  # noqa: E402,F401  (đăng ký các lệnh)
import presence  # noqa: E402
import storage  # noqa: E402
from dispatch import dispatch  # noqa: E402
from session import registry  # noqa: E402


class FakeSession:
    """Session giả: ghi lại message được gửi, nhớ đã bị đóng chưa."""

    def __init__(self):
        self.username = None
        self.peer = "fake:0"
        self.sent: list[dict] = []
        self.closed = False

    def send(self, msg: dict) -> bool:
        self.sent.append(msg)
        return True

    def close(self) -> None:
        self.closed = True


class Fixture(unittest.TestCase):
    """Dữ liệu dùng chung: huy chung phòng với khoi (lab) và kiet, khoi (web); nam ở riêng."""

    def setUp(self):
        storage.init_db(":memory:")
        for n in ("huy", "khoi", "kiet", "nam"):
            storage.create_user(n, "h", "s")
        storage.create_room("lab", "huy")
        storage.add_member("lab", "khoi")
        storage.create_room("web", "huy")
        storage.add_member("web", "kiet")
        storage.add_member("web", "khoi")
        storage.create_room("game", "nam")  # nam không chung phòng với huy
        self.sessions = {}

    def tearDown(self):
        for name, s in self.sessions.items():
            registry.unbind(name, s)

    def online(self, *names):
        for n in names:
            s = FakeSession()
            self.assertTrue(registry.bind(n, s))
            self.sessions[n] = s
        return [self.sessions[n] for n in names]


class PresenceTest(Fixture):
    def test_roommates_union_without_self_or_duplicates(self):
        self.assertEqual(presence.roommates("huy"), ["khoi", "kiet"])
        self.assertEqual(presence.roommates("nam"), [])

    def test_cleanup_notifies_online_roommates_only(self):
        huy, khoi, kiet, nam = self.online("huy", "khoi", "kiet", "nam")
        presence.cleanup(huy)
        expected = {"command": "NOTIFY_OFFLINE", "data": {"username": "huy"}}
        self.assertEqual(khoi.sent, [expected])
        self.assertEqual(kiet.sent, [expected])
        self.assertEqual(nam.sent, [])  # không chung phòng
        self.assertEqual(huy.sent, [])  # không gửi cho chính mình
        self.assertTrue(huy.closed)
        self.assertFalse(registry.is_online("huy"))
        self.assertIsNone(huy.username)

    def test_cleanup_not_logged_in_just_closes(self):
        (khoi,) = self.online("khoi")
        s = FakeSession()
        presence.cleanup(s)
        self.assertTrue(s.closed)
        self.assertEqual(khoi.sent, [])

    def test_cleanup_stale_session_does_not_notify(self):
        """Phiên không còn gắn với tài khoản (unbind trả False): không báo offline nhầm."""
        (khoi,) = self.online("khoi")
        stale = FakeSession()
        stale.username = "huy"  # tự nhận là huy nhưng không có trong registry
        presence.cleanup(stale)
        self.assertEqual(khoi.sent, [])
        self.assertTrue(stale.closed)

    def test_cleanup_closes_even_if_notify_fails(self):
        (huy,) = self.online("huy")
        storage._conn.close()  # database hỏng: notify_offline ném lỗi
        try:
            with self.assertRaises(Exception):
                presence.cleanup(huy)
            self.assertTrue(huy.closed)
            self.assertFalse(registry.is_online("huy"))
        finally:
            storage.init_db(":memory:")

    def test_notify_online(self):
        khoi, nam = self.online("khoi", "nam")
        presence.notify_online("huy")
        self.assertEqual(khoi.sent, [{"command": "NOTIFY_ONLINE", "data": {"username": "huy"}}])
        self.assertEqual(nam.sent, [])


class ListCommandsTest(Fixture):
    """LIST_ONLINE, LIST_MEMBERS qua dispatcher (bước 9)."""

    def run_cmd(self, session, command, payload):
        dispatch(session, {"command": command, "payload": payload})
        return session.sent.pop()

    def test_list_online_sorted(self):
        huy, _, _ = self.online("kiet", "huy", "nam")
        msg = self.run_cmd(huy, "LIST_ONLINE", {})
        self.assertEqual((msg["code"], msg["data"]), (200, {"users": ["huy", "kiet", "nam"]}))

    def test_list_members_with_online_status_in_join_order(self):
        huy, khoi = self.online("huy", "khoi")
        msg = self.run_cmd(huy, "LIST_MEMBERS", {"room": "web"})
        self.assertEqual(msg["data"], {"room": "web", "members": [
            {"username": "huy", "online": True},
            {"username": "kiet", "online": False},
            {"username": "khoi", "online": True}]})

    def test_list_members_errors(self):
        (nam,) = self.online("nam")
        self.assertEqual(self.run_cmd(nam, "LIST_MEMBERS", {"room": "lab"})["code"], 403)
        self.assertEqual(self.run_cmd(nam, "LIST_MEMBERS", {"room": "khong_co"})["code"], 404)
        self.assertEqual(self.run_cmd(nam, "LIST_MEMBERS", {})["code"], 400)

    def test_list_commands_require_login(self):
        s = FakeSession()
        self.assertEqual(self.run_cmd(s, "LIST_ONLINE", {})["code"], 401)
        self.assertEqual(self.run_cmd(s, "LIST_MEMBERS", {"room": "lab"})["code"], 401)


if __name__ == "__main__":
    unittest.main()
