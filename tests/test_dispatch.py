"""Unit test cho server/src/dispatch.py (khung bước 5).

    python -m unittest tests.test_dispatch -v
"""

import socket
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server" / "src"))

import dispatch as dispatch_mod  # noqa: E402
from dispatch import CommandError, Reply, command, dispatch, optional, require  # noqa: E402
from shared import protocol  # noqa: E402
from shared.protocol import FrameBuffer, decode, encode  # noqa: E402


class FakeSession:
    """Session giả: ghi lại mọi message được gửi, không cần socket."""

    def __init__(self, username=None, send_ok=True):
        self.username = username
        self.peer = "fake:0"
        self.sent: list[dict] = []
        self.send_ok = send_ok

    def send(self, msg: dict) -> bool:
        self.sent.append(msg)
        return self.send_ok


class DispatchTestBase(unittest.TestCase):
    def setUp(self):
        # Mỗi test có bảng lệnh riêng; khôi phục bảng gốc sau test.
        self._saved = dict(dispatch_mod._commands)
        dispatch_mod._commands.clear()

    def tearDown(self):
        dispatch_mod._commands.clear()
        dispatch_mod._commands.update(self._saved)


class DispatchTest(DispatchTestBase):
    def test_unknown_command_is_error_400(self):
        s = FakeSession()
        close = dispatch(s, {"command": "KHONG_CO", "requestId": "1", "payload": {}})
        self.assertFalse(close)
        self.assertEqual(s.sent, [{"command": "ERROR", "requestId": "1", "code": 400,
                                   "message": "Lệnh không tồn tại: KHONG_CO"}])

    def test_auth_required(self):
        calls = []

        @command("T_AUTH")
        def handler(session, payload):
            calls.append(session.username)
            return Reply()

        s = FakeSession()
        dispatch(s, {"command": "T_AUTH", "payload": {}})
        self.assertEqual((s.sent[0]["command"], s.sent[0]["code"]), ("T_AUTH_RESPONSE", 401))
        self.assertEqual(calls, [])  # handler không được gọi

        s = FakeSession(username="kiet")
        dispatch(s, {"command": "T_AUTH", "payload": {}})
        self.assertEqual(s.sent[0]["code"], 200)
        self.assertEqual(calls, ["kiet"])

    def test_no_auth_command_runs_without_login(self):
        @command("T_OPEN", auth=False)
        def handler(session, payload):
            return Reply(data={"x": 1})

        s = FakeSession()
        dispatch(s, {"command": "T_OPEN", "requestId": "7", "payload": {}})
        self.assertEqual(s.sent, [{"command": "T_OPEN_RESPONSE", "requestId": "7", "code": 200,
                                   "message": "OK", "data": {"x": 1}}])

    def test_payload_missing_or_not_object(self):
        @command("T_P", auth=False)
        def handler(session, payload):
            return Reply()

        for msg in ({"command": "T_P"}, {"command": "T_P", "payload": []},
                    {"command": "T_P", "payload": None}):
            s = FakeSession()
            dispatch(s, msg)
            self.assertEqual((s.sent[0]["command"], s.sent[0]["code"]), ("T_P_RESPONSE", 400))

    def test_command_error_becomes_response(self):
        @command("T_ERR", auth=False)
        def handler(session, payload):
            raise CommandError(protocol.FORBIDDEN, "Bạn không phải thành viên phòng")

        s = FakeSession()
        dispatch(s, {"command": "T_ERR", "requestId": "a", "payload": {}})
        self.assertEqual(s.sent, [{"command": "T_ERR_RESPONSE", "requestId": "a", "code": 403,
                                   "message": "Bạn không phải thành viên phòng", "data": {}}])

    def test_unexpected_exception_is_500_and_logged(self):
        @command("T_BUG", auth=False)
        def handler(session, payload):
            return {}["khong_co"]  # KeyError

        s = FakeSession()
        with self.assertLogs("dispatch", level="ERROR") as logs:
            close = dispatch(s, {"command": "T_BUG", "payload": {}})
        self.assertFalse(close)
        self.assertEqual(s.sent[0]["code"], 500)
        self.assertNotIn("KeyError", s.sent[0]["message"])  # không lộ chi tiết cho client
        self.assertIn("KeyError", "\n".join(logs.output))   # nhưng có trong log

    def test_handler_returning_none_is_500(self):
        @command("T_NONE", auth=False)
        def handler(session, payload):
            pass  # quên return Reply(...)

        s = FakeSession()
        with self.assertLogs("dispatch", level="ERROR"):
            dispatch(s, {"command": "T_NONE", "payload": {}})
        self.assertEqual(s.sent[0]["code"], 500)

    def test_after_runs_after_response_even_if_send_failed(self):
        order = []

        @command("T_AFTER", auth=False)
        def handler(session, payload):
            def bad():
                raise ValueError("lỗi trong after")
            return Reply(after=[lambda: order.append("a"), bad, lambda: order.append("c")])

        s = FakeSession(send_ok=False)  # gửi response thất bại
        with self.assertLogs("dispatch", level="ERROR"):
            dispatch(s, {"command": "T_AFTER", "payload": {}})
        self.assertEqual(len(s.sent), 1)          # response đã được gửi trước
        self.assertEqual(order, ["a", "c"])       # after vẫn chạy; hàm lỗi không chặn hàm sau

    def test_push_is_sent_after_response(self):
        @command("T_PUSH", auth=False)
        def handler(session, payload):
            return Reply(after=[lambda: session.send(protocol.push("NOTIFY_T", {}))])

        s = FakeSession()
        dispatch(s, {"command": "T_PUSH", "payload": {}})
        self.assertEqual([m["command"] for m in s.sent], ["T_PUSH_RESPONSE", "NOTIFY_T"])

    def test_reply_close(self):
        @command("T_QUIT", auth=False)
        def handler(session, payload):
            return Reply(close=True)

        s = FakeSession()
        self.assertTrue(dispatch(s, {"command": "T_QUIT", "payload": {}}))
        self.assertEqual(s.sent[0]["code"], 200)

    def test_duplicate_registration_raises(self):
        @command("T_DUP")
        def first(session, payload):
            return Reply()

        with self.assertRaises(RuntimeError):
            @command("T_DUP")
            def second(session, payload):
                return Reply()


class RequireOptionalTest(unittest.TestCase):
    def test_require(self):
        self.assertEqual(require({"room": "lab"}, "room", str), "lab")
        for payload in ({}, {"room": 1}, {"room": None}):
            with self.assertRaises(CommandError) as ctx:
                require(payload, "room", str)
            self.assertEqual(ctx.exception.code, 400)

    def test_require_int_rejects_bool(self):
        self.assertEqual(require({"n": 3}, "n", int), 3)
        with self.assertRaises(CommandError):
            require({"n": True}, "n", int)

    def test_optional(self):
        self.assertEqual(optional({}, "limit", int, 20), 20)
        self.assertEqual(optional({"limit": 5}, "limit", int, 20), 5)
        with self.assertRaises(CommandError):
            optional({"limit": "5"}, "limit", int, 20)


class ServeClientCloseTest(DispatchTestBase):
    """Reply.close: server gửi response rồi đóng kết nối (chạy _serve_client thật)."""

    def test_connection_closed_after_reply_close(self):
        import server  # server/src/server.py

        @command("T_QUIT", auth=False)
        def handler(session, payload):
            return Reply(close=True)

        server_side, client_side = socket.socketpair()
        server._try_reserve_slot()  # _serve_client sẽ trả chỗ trong finally
        t = threading.Thread(target=server._serve_client, args=(server_side, ("test", 0)))
        t.start()
        # Dòng sau T_QUIT không được xử lý.
        client_side.sendall(encode({"command": "T_QUIT", "payload": {}}) +
                            encode({"command": "KHONG_CO", "payload": {}}))
        client_side.settimeout(5)
        fb, lines = FrameBuffer(), []
        while data := client_side.recv(4096):
            lines += fb.feed(data)
        t.join(5)
        client_side.close()
        self.assertFalse(t.is_alive())
        self.assertEqual([decode(x)["command"] for x in lines], ["T_QUIT_RESPONSE"])


if __name__ == "__main__":
    unittest.main()
