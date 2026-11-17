"""Unit test cho handlers/messages.py (khung bước 7): các nhánh khó tạo bằng server thật.

Kịch bản chat đầy đủ (nhiều client thật) nằm trong tests/test_server.py.

    python -m unittest tests.test_messages -v
"""

import re
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server" / "src"))

import handlers  # noqa: E402,F401  (đăng ký ROOM_MSG, PRIVATE_MSG, LOGIN, PING)
from handlers import messages  # noqa: E402
from dispatch import dispatch  # noqa: E402
from session import registry  # noqa: E402

TS_FORMAT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class FakeSession:
    def __init__(self, username=None, send_ok=True):
        self.username = username
        self.peer = "fake:0"
        self.sent: list[dict] = []
        self.send_ok = send_ok

    def send(self, msg: dict) -> bool:
        self.sent.append(msg)
        return self.send_ok


def room_msg(content="hi", room="lab"):
    return {"command": "ROOM_MSG", "payload": {"room": room, "content": content}}


class RoomMsgTest(unittest.TestCase):
    def test_ts_format(self):
        self.assertRegex(messages._now_ts(), TS_FORMAT)

    def test_not_member_is_403(self):
        s = FakeSession(username="kiet")
        with mock.patch.object(messages.rooms, "is_member", return_value=False):
            dispatch(s, room_msg())
        self.assertEqual(s.sent[0]["code"], 403)

    def test_whitespace_only_is_400(self):
        s = FakeSession(username="kiet")
        dispatch(s, room_msg(content="   \n\t"))
        self.assertEqual((s.sent[0]["code"], s.sent[0]["message"]), (400, "Tin nhắn rỗng"))

    def test_content_kept_as_is(self):
        # Không cắt khoảng trắng: người nhận thấy đúng nội dung đã gửi.
        s = FakeSession(username="kiet")
        with mock.patch.object(messages, "broadcast") as fake_broadcast:
            dispatch(s, room_msg(content="  chào\n  cả nhóm  "))
        self.assertEqual(s.sent[0]["code"], 200)
        members, notify = fake_broadcast.call_args.args
        self.assertEqual(notify["data"]["content"], "  chào\n  cả nhóm  ")

    def test_too_long_is_413(self):
        s = FakeSession(username="kiet")
        with mock.patch.object(messages.config, "MAX_TEXT_CHARS", 5):
            dispatch(s, room_msg(content="123456"))
        self.assertEqual(s.sent[0]["code"], 413)

    def test_lock_released_after_error(self):
        # Ném CommandError bên trong `with rooms.lock(...)` vẫn phải nhả khoá.
        s = FakeSession(username="kiet")
        dispatch(s, room_msg(room="khong_co"))
        self.assertEqual(s.sent[0]["code"], 404)
        self.assertFalse(messages.rooms.lock("lab").locked())


class PrivateMsgTest(unittest.TestCase):
    def tearDown(self):
        for name in ("huy_test",):
            s = registry.get(name)
            if s is not None:
                registry.unbind(name, s)

    def test_target_send_fails_is_404(self):
        # Người nhận vừa chết: gửi thất bại → người gửi nhận 404, không phải 200 (4A).
        target = FakeSession(send_ok=False)
        registry.bind("huy_test", target)
        s = FakeSession(username="kiet")
        with mock.patch.object(messages, "get_user", return_value={"username": "huy_test"}):
            dispatch(s, {"command": "PRIVATE_MSG", "payload": {"to": "huy_test", "content": "hi"}})
        self.assertEqual(len(target.sent), 1)       # đã thử gửi cho người nhận
        self.assertEqual(s.sent[0]["code"], 404)

    def test_unknown_user_is_404(self):
        s = FakeSession(username="kiet")
        with mock.patch.object(messages, "get_user", return_value=None):
            dispatch(s, {"command": "PRIVATE_MSG", "payload": {"to": "ai_do", "content": "hi"}})
        self.assertEqual((s.sent[0]["code"], s.sent[0]["message"]),
                         (404, "Người nhận không tồn tại hoặc đang offline"))


if __name__ == "__main__":
    unittest.main()
