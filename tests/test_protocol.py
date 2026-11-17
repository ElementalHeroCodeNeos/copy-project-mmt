"""Unit test cho shared/protocol.py. Chạy từ thư mục gốc repo:

    python -m unittest discover tests -v
"""

import json
import unittest

from shared import protocol
from shared.protocol import FrameBuffer, FrameTooLarge, ProtocolError, decode, encode


class EncodeTest(unittest.TestCase):
    def test_one_line_ending_with_newline(self):
        data = encode({"command": "PING", "payload": {}})
        self.assertEqual(data, b'{"command":"PING","payload":{}}\n')

    def test_vietnamese_kept_as_utf8(self):
        data = encode({"content": "Chào cả nhóm"})
        self.assertIn("Chào cả nhóm".encode("utf-8"), data)

    def test_newline_in_content_is_escaped(self):
        data = encode({"content": "dòng 1\ndòng 2"})
        self.assertEqual(data.count(b"\n"), 1)  # chỉ có \n ở cuối
        self.assertTrue(data.endswith(b"\n"))


class FrameBufferTest(unittest.TestCase):
    def test_message_split_in_two(self):
        # Ví dụ ở protocol-design.md mục 2
        fb = FrameBuffer()
        lines = fb.feed(b'{"command":"PING","payload":{}}\n{"command":"ROOM_MS')
        self.assertEqual(lines, [b'{"command":"PING","payload":{}}'])
        lines = fb.feed(b'G","payload":{"room":"lab","content":"hi"}}\n')
        self.assertEqual(lines, [b'{"command":"ROOM_MSG","payload":{"room":"lab","content":"hi"}}'])

    def test_two_messages_in_one_recv(self):
        fb = FrameBuffer()
        lines = fb.feed(b'{"command":"A"}\n{"command":"B"}\n')
        self.assertEqual(lines, [b'{"command":"A"}', b'{"command":"B"}'])

    def test_one_byte_at_a_time(self):
        fb = FrameBuffer()
        data = encode({"command": "ROOM_MSG", "payload": {"content": "Chào"}})
        lines = []
        for i in range(len(data)):
            lines += fb.feed(data[i:i + 1])  # tách cả giữa các byte của chữ "à"
        self.assertEqual(len(lines), 1)
        self.assertEqual(decode(lines[0])["payload"]["content"], "Chào")

    def test_empty_lines_and_crlf(self):
        fb = FrameBuffer()
        lines = fb.feed(b'\n\r\n  \n{"command":"PING"}\r\n')
        self.assertEqual(lines, [b'{"command":"PING"}\r'])
        self.assertEqual(decode(lines[0])["command"], "PING")  # JSON coi \r là khoảng trắng

    def test_incomplete_up_to_limit_is_ok(self):
        fb = FrameBuffer(max_bytes=10)
        self.assertEqual(fb.feed(b"x" * 10), [])

    def test_incomplete_over_limit_raises(self):
        fb = FrameBuffer(max_bytes=10)
        with self.assertRaises(FrameTooLarge):
            fb.feed(b"x" * 11)

    def test_incomplete_over_limit_across_feeds_raises(self):
        fb = FrameBuffer(max_bytes=10)
        fb.feed(b"x" * 6)
        with self.assertRaises(FrameTooLarge):
            fb.feed(b"x" * 6)

    def test_complete_line_over_limit_raises(self):
        fb = FrameBuffer(max_bytes=10)
        with self.assertRaises(FrameTooLarge):
            fb.feed(b"x" * 11 + b"\n")

    def test_line_exactly_at_limit_is_ok(self):
        fb = FrameBuffer(max_bytes=10)
        self.assertEqual(fb.feed(b"x" * 10 + b"\n"), [b"x" * 10])

    def test_default_limit_64kb(self):
        fb = FrameBuffer()
        with self.assertRaises(FrameTooLarge):
            fb.feed(b"x" * (64 * 1024 + 1))

    def test_too_large_is_not_protocol_error(self):
        # Server bắt ProtocolError để giữ kết nối; FrameTooLarge phải đi đường riêng.
        self.assertFalse(issubclass(FrameTooLarge, ProtocolError))


class DecodeTest(unittest.TestCase):
    def test_valid(self):
        msg = decode('{"command":"ROOM_MSG","requestId":"7","payload":{"room":"lab"}}'.encode())
        self.assertEqual(msg["command"], "ROOM_MSG")
        self.assertEqual(msg["requestId"], "7")

    def test_roundtrip(self):
        original = {"command": "PRIVATE_MSG", "payload": {"to": "huy", "content": "tối họp\nnhé"}}
        fb = FrameBuffer()
        (line,) = fb.feed(encode(original))
        self.assertEqual(decode(line), original)

    def assertProtocolError(self, line: bytes):
        with self.assertRaises(ProtocolError):
            decode(line)

    def test_not_utf8(self):
        self.assertProtocolError(b'{"command":"\xff"}')

    def test_not_json(self):
        self.assertProtocolError(b"hello")

    def test_not_object(self):
        self.assertProtocolError(b'["PING"]')
        self.assertProtocolError(b'"PING"')

    def test_missing_command(self):
        self.assertProtocolError(b'{"payload":{}}')

    def test_command_not_string(self):
        self.assertProtocolError(b'{"command":123}')
        self.assertProtocolError(b'{"command":""}')

    def test_request_id_not_string(self):
        self.assertProtocolError(b'{"command":"PING","requestId":7}')
        self.assertProtocolError(b'{"command":"PING","requestId":null}')

    def test_deeply_nested_json(self):
        self.assertProtocolError(b"[" * 60000 + b"]" * 60000)

    def test_huge_integer(self):
        self.assertProtocolError(b'{"command":"PING","n":' + b"9" * 5000 + b"}")


class BuildMessageTest(unittest.TestCase):
    def test_response_with_request_id(self):
        msg = protocol.response(protocol.ROOM_MSG, protocol.OK, data={"ts": "t"}, request_id="7")
        self.assertEqual(msg, {"command": "ROOM_MSG_RESPONSE", "requestId": "7",
                               "code": 200, "message": "OK", "data": {"ts": "t"}})
        self.assertEqual(list(msg), ["command", "requestId", "code", "message", "data"])

    def test_response_without_request_id(self):
        msg = protocol.response(protocol.ROOM_MSG, protocol.FORBIDDEN, "Bạn không phải thành viên phòng")
        self.assertNotIn("requestId", msg)
        self.assertEqual(msg["data"], {})

    def test_push(self):
        msg = protocol.push(protocol.NOTIFY_ROOM_MSG, {"room": "lab"})
        self.assertEqual(msg, {"command": "NOTIFY_ROOM_MSG", "data": {"room": "lab"}})

    def test_push_requires_notify_prefix(self):
        with self.assertRaises(ValueError):
            protocol.push(protocol.ROOM_MSG, {})

    def test_error(self):
        msg = protocol.error(protocol.BAD_REQUEST, "JSON không hợp lệ")
        self.assertEqual(msg, {"command": "ERROR", "code": 400, "message": "JSON không hợp lệ"})

    def test_built_messages_encode_to_valid_json(self):
        msg = protocol.error(protocol.TOO_LARGE, "Message quá 64 KB")
        self.assertEqual(json.loads(encode(msg)), msg)


if __name__ == "__main__":
    unittest.main()
