"""Test tích hợp cho vòng đọc và giới hạn của server (khung bước 3).

Mỗi test chạy một server thật (subprocess) trên một cổng trống, với giới hạn nhỏ để
test nhanh: MAX_CLIENTS=3, READ_TIMEOUT_SEC=2, MAX_MESSAGE_BYTES=1024.

    python -m unittest tests.test_server -v
"""

import os
import socket
import struct
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from shared.protocol import FrameBuffer, decode, encode

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "src"))
import storage  # noqa: E402  (tạo phòng sẵn trong database của server khi test)
SERVER = ROOT / "server" / "src" / "server.py"
MAX_CLIENTS = 3
READ_TIMEOUT = 2
MAX_BYTES = 1024
MAX_TEXT = 50
PASSWORD = "matkhau123"
TS_FORMAT = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Client:
    """Client test tối giản: gửi bytes, đọc từng message, phát hiện EOF."""

    def __init__(self, port: int):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.buffer = FrameBuffer(1 << 20)
        self.pending: list[bytes] = []

    def send(self, data: bytes) -> None:
        self.sock.sendall(data)

    def recv_msg(self, timeout: float = 3) -> dict:
        deadline = time.monotonic() + timeout
        while not self.pending:
            self.sock.settimeout(max(deadline - time.monotonic(), 0.01))
            data = self.sock.recv(4096)
            if not data:
                raise EOFError("server đã đóng kết nối")
            self.pending += self.buffer.feed(data)
        return decode(self.pending.pop(0))

    def wait_closed(self, timeout: float) -> bool:
        """True nếu server đóng kết nối (EOF hoặc reset) trong `timeout` giây."""
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            self.sock.settimeout(remaining)
            try:
                if not self.sock.recv(4096):
                    return True
            except TimeoutError:
                return False
            except OSError:
                return True
        return False

    def close(self) -> None:
        self.sock.close()


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.port = _free_port()
        # Mỗi test một database rỗng trong thư mục tạm, không đụng /app/data (Huy, bước 4).
        self.data_dir = tempfile.mkdtemp(prefix="chat-test-")
        env = dict(os.environ,
                   SERVER_HOST="127.0.0.1", SERVER_PORT=str(self.port),
                   MAX_CLIENTS=str(MAX_CLIENTS), READ_TIMEOUT_SEC=str(READ_TIMEOUT),
                   MAX_MESSAGE_BYTES=str(MAX_BYTES), MAX_TEXT_CHARS=str(MAX_TEXT),
                   LOG_LEVEL="INFO", DATA_DIR=self.data_dir,
                   PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8")
        self.proc = subprocess.Popen([sys.executable, "-u", str(SERVER)], env=env,
                                     stderr=subprocess.PIPE, text=True, encoding="utf-8")
        self.logs: list[str] = []
        ready = threading.Event()

        def read_logs():  # phải đọc liên tục, nếu không pipe đầy thì server bị treo
            for line in self.proc.stderr:
                self.logs.append(line)
                if "Đang lắng nghe" in line:
                    ready.set()

        threading.Thread(target=read_logs, daemon=True).start()
        self.assertTrue(ready.wait(5), "server không khởi động được:\n" + "".join(self.logs))
        self.clients: list[Client] = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.proc.kill()
        self.proc.wait()
        self.proc.stderr.close()
        storage.init_db(":memory:")  # đóng file database nếu test đã mở (Windows không xoá file đang mở)
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def connect(self) -> Client:
        c = Client(self.port)
        self.clients.append(c)
        return c

    # --- dữ liệu lỗi -------------------------------------------------------

    def test_garbage_gets_400_and_connection_stays(self):
        c = self.connect()
        c.send(b"hello\n")
        msg = c.recv_msg()
        self.assertEqual((msg["command"], msg["code"]), ("ERROR", 400))
        self.assertEqual(msg["message"], "JSON không hợp lệ")
        c.send(encode({"command": "KHONG_CO_LENH", "requestId": "1", "payload": {}}))
        msg = c.recv_msg()  # vẫn đọc được: kết nối còn sống
        self.assertEqual((msg["code"], msg["requestId"]), (400, "1"))

    def test_bad_request_id_type_gets_400(self):
        c = self.connect()
        c.send(b'{"command":"KHONG_CO_LENH","requestId":7,"payload":{}}\n')
        msg = c.recv_msg()
        self.assertEqual((msg["code"], msg["message"]), (400, "requestId phải là chuỗi"))

    def test_too_large_gets_413_then_closed(self):
        c = self.connect()
        c.send(b"x" * (MAX_BYTES * 50))  # nhiều hơn giới hạn, không có \n
        msg = c.recv_msg()
        self.assertEqual((msg["command"], msg["code"]), ("ERROR", 413))
        self.assertTrue(c.wait_closed(3))

    # --- tách message ------------------------------------------------------

    def test_message_split_and_glued(self):
        c = self.connect()
        c.send(b'{"command":"A_X","requestId":"a"}\n{"command":"B_X","req')
        time.sleep(0.2)
        c.send(b'uestId":"b"}\n')
        self.assertEqual(c.recv_msg()["requestId"], "a")
        self.assertEqual(c.recv_msg()["requestId"], "b")

    # --- MAX_CLIENTS -------------------------------------------------------

    def test_max_clients_rejects_with_503_and_frees_slot(self):
        first = [self.connect() for _ in range(MAX_CLIENTS)]
        extra = self.connect()
        msg = extra.recv_msg()
        self.assertEqual((msg["command"], msg["code"]), ("ERROR", 503))
        self.assertTrue(extra.wait_closed(2))

        first[0].close()  # trả một chỗ
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            c = self.connect()
            c.send(encode({"command": "KHONG_CO_LENH", "payload": {}}))
            if c.recv_msg()["code"] == 400:
                return  # đã vào được
            time.sleep(0.1)
        self.fail("không vào lại được sau khi một client rời đi")

    # --- timeout -----------------------------------------------------------

    def test_silent_client_is_closed_after_timeout(self):
        c = self.connect()
        start = time.monotonic()
        self.assertTrue(c.wait_closed(READ_TIMEOUT + 2))
        self.assertGreaterEqual(time.monotonic() - start, READ_TIMEOUT - 0.5)

    def test_trickling_client_is_closed_after_timeout(self):
        # Gửi 1 byte mỗi 0,3 s nhưng không bao giờ đủ một message: vẫn bị đóng (1B).
        c = self.connect()
        c.send(b"{")
        start = time.monotonic()
        closed = False
        while time.monotonic() - start < READ_TIMEOUT + 2:
            try:
                c.send(b" ")
            except OSError:
                closed = True
                break
            if c.wait_closed(0.3):
                closed = True
                break
        self.assertTrue(closed, "client gửi nhỏ giọt không bị đóng")

    def test_active_client_stays_past_timeout(self):
        # Client gửi PING đều đặn (như client thật) thì không bị ngắt dù quá READ_TIMEOUT.
        c = self.connect()
        start = time.monotonic()
        while time.monotonic() - start < READ_TIMEOUT * 2:
            c.send(encode({"command": "PING", "payload": {}}))
            self.assertEqual(c.recv_msg()["command"], "PING_RESPONSE")
            time.sleep(READ_TIMEOUT / 3)

    # --- PING (bước 6) -----------------------------------------------------

    def test_ping_without_login(self):
        c = self.connect()
        c.send(encode({"command": "PING", "requestId": "p1", "payload": {}}))
        self.assertEqual(c.recv_msg(), {"command": "PING_RESPONSE", "requestId": "p1",
                                        "code": 200, "message": "OK", "data": {}})

    def test_ping_without_payload_is_400(self):
        c = self.connect()
        c.send(b'{"command":"PING"}\n')
        msg = c.recv_msg()
        self.assertEqual((msg["command"], msg["code"]), ("PING_RESPONSE", 400))

    # --- client đứng hình (bước 4) ----------------------------------------

    def test_client_that_never_reads_is_disconnected(self):
        # Client gửi rất nhiều lệnh nhưng không đọc response: bộ đệm gửi của server
        # đầy, Session.send() hết giờ (5 s) và server ngắt client này.
        c = self.connect()
        c.sock.settimeout(20)
        try:
            c.send(b"x\n" * 300_000)  # 300.000 lệnh rác -> 300.000 ERROR 400 không ai đọc
        except OSError:
            pass  # server đã ngắt giữa chừng
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if any("gửi thất bại" in line for line in self.logs):
                break
            time.sleep(0.2)
        self.assertTrue(any("Gửi tới" in line and "thất bại" in line for line in self.logs),
                        "server không ngắt client đứng hình")
        # Server vẫn phục vụ người khác bình thường.
        other = self.connect()
        other.send(encode({"command": "KHONG_CO_LENH", "requestId": "ok", "payload": {}}))
        self.assertEqual(other.recv_msg()["requestId"], "ok")

    # --- REGISTER, LOGIN (Huy, bước 5) --------------------------------------

    def request(self, c: Client, command: str, payload: dict) -> dict:
        c.send(encode({"command": command, "payload": payload}))
        return c.recv_msg()

    def register(self, c: Client, name: str, password: str = PASSWORD) -> dict:
        return self.request(c, "REGISTER", {"username": name, "password": password})

    def send_login(self, c: Client, name: str, password: str = PASSWORD) -> dict:
        return self.request(c, "LOGIN", {"username": name, "password": password})

    def login(self, name: str, register: bool = True) -> Client:
        """Kết nối mới, đăng ký (bỏ qua nếu đã có) rồi đăng nhập."""
        c = self.connect()
        if register:
            self.assertIn(self.register(c, name)["code"], (201, 409))
        msg = self.send_login(c, name)
        self.assertEqual((msg["command"], msg["code"]), ("LOGIN_RESPONSE", 200), msg)
        return c

    def logins(self, *names: str) -> list[Client]:
        """Đăng ký HẾT rồi mới đăng nhập từng người.

        Mỗi lần băm mật khẩu ~0,4 s và test dùng READ_TIMEOUT_SEC=2: nếu đăng ký xen giữa,
        người đăng nhập đầu tiên ngồi chờ quá 2 s và bị server ngắt vì im lặng.
        """
        first = self.connect()  # đăng ký trên kết nối của người đầu (test chỉ cho MAX_CLIENTS=3)
        for n in names:
            self.assertIn(self.register(first, n)["code"], (201, 409))
        self.assertEqual(self.send_login(first, names[0])["code"], 200)
        return [first] + [self.login(n, register=False) for n in names[1:]]

    def test_register_then_login(self):
        c = self.connect()
        msg = self.register(c, "huy")
        self.assertEqual((msg["command"], msg["code"], msg["data"]),
                         ("REGISTER_RESPONSE", 201, {"username": "huy"}))
        msg = self.send_login(c, "huy")
        self.assertEqual((msg["code"], msg["data"]), (200, {"username": "huy", "rooms": []}))

    def test_register_does_not_log_in(self):
        c = self.connect()
        self.register(c, "huy")
        c.send(encode({"command": "ROOM_MSG", "payload": {"room": "lab", "content": "hi"}}))
        self.assertEqual(c.recv_msg()["code"], 401)

    def test_register_duplicate_is_409(self):
        c = self.connect()
        self.assertEqual(self.register(c, "huy")["code"], 201)
        self.assertEqual(self.register(c, "huy", "matkhau_khac")["code"], 409)
        self.assertEqual(self.register(c, "HUY")["code"], 409)  # chữ hoa = cùng tài khoản

    def test_register_uppercase_is_lowercased(self):
        c = self.connect()
        self.assertEqual(self.register(c, "Huy_01")["data"], {"username": "huy_01"})
        self.assertEqual(self.send_login(c, "HUY_01")["code"], 200)

    def test_register_invalid_input_is_400(self):
        c = self.connect()
        cases = [("ab", PASSWORD), ("a" * 21, PASSWORD), ("huy!", PASSWORD), (" huy", PASSWORD),
                 ("đăng", PASSWORD), ("huy", "12345"), ("huy", "x" * 129)]
        for name, password in cases:
            self.assertEqual(self.register(c, name, password)["code"], 400, (name, password))
        self.assertEqual(self.request(c, "REGISTER", {"username": "huy"})["code"], 400)
        self.assertEqual(self.request(c, "REGISTER", {"username": 1, "password": PASSWORD})["code"],
                         400)

    def test_login_wrong_password_and_unknown_user_same_401(self):
        c = self.connect()
        self.register(c, "huy")
        wrong = self.send_login(c, "huy", "sai_mat_khau")
        unknown = self.send_login(c, "khong_co")
        self.assertEqual((wrong["code"], unknown["code"]), (401, 401))
        self.assertEqual(wrong["message"], unknown["message"])

    def test_login_twice_on_same_connection_is_409(self):
        c = self.login("huy")
        msg = self.send_login(c, "huy")
        self.assertEqual((msg["code"], msg["message"]), (409, "Kết nối này đã đăng nhập"))

    def test_login_same_name_twice_is_409(self):
        self.login("kiet")
        msg = self.send_login(self.connect(), "kiet")
        self.assertEqual((msg["code"], msg["message"]),
                         (409, "Tài khoản đang online ở kết nối khác"))

    def test_login_wrong_password_while_online_is_401_not_409(self):
        """Không biết mật khẩu thì không dò được ai đang online."""
        self.login("kiet")
        self.assertEqual(self.send_login(self.connect(), "kiet", "sai_mat_khau")["code"], 401)

    # --- QUIT (Huy, bước 6) ----------------------------------------------------

    def test_quit_gets_response_then_closed(self):
        c = self.connect()  # chưa đăng nhập vẫn QUIT được
        msg = self.request(c, "QUIT", {})
        self.assertEqual((msg["command"], msg["code"]), ("QUIT_RESPONSE", 200))
        self.assertTrue(c.wait_closed(2))

    def test_quit_frees_username_immediately(self):
        c = self.login("huy")
        self.assertEqual(self.request(c, "QUIT", {})["code"], 200)
        self.assertTrue(c.wait_closed(2))
        c.close()
        self.clients.remove(c)
        self.login("huy", register=False)  # phiên cũ đã dọn: đăng nhập lại được ngay

    def test_messages_after_quit_are_ignored(self):
        c = self.connect()
        c.send(encode({"command": "QUIT", "requestId": "q", "payload": {}})
               + encode({"command": "PING", "requestId": "p", "payload": {}}))
        self.assertEqual(c.recv_msg()["requestId"], "q")
        with self.assertRaises((EOFError, ConnectionError)):  # đóng luôn, không có PING_RESPONSE
            c.recv_msg(timeout=2)

    # --- online/offline (Huy, bước 8) ------------------------------------------

    def seed_room(self, room: str, *members: str) -> None:
        """Tạo phòng thẳng trong file database của server (chưa có lệnh CREATE_ROOM của Khôi).

        Các tài khoản phải được REGISTER trước (khoá ngoại). Server và test là hai tiến trình
        cùng mở một file SQLite; SQLite tự khoá file nên an toàn.
        """
        storage.init_db(os.path.join(self.data_dir, "chat.db"))
        storage.create_room(room, members[0])
        for m in members[1:]:
            storage.add_member(room, m)

    def roommates_online(self) -> tuple[Client, Client]:
        """kiet và huy chung phòng `lab`; kiet đăng nhập trước, huy sau. Trả (kiet, huy)."""
        kiet = self.connect()
        for n in ("kiet", "huy"):
            self.register(kiet, n)
        self.seed_room("lab", "kiet", "huy")
        self.assertEqual(self.send_login(kiet, "kiet")["data"]["rooms"], ["lab"])
        huy = self.login("huy", register=False)
        return kiet, huy

    def test_login_notifies_roommates(self):
        kiet, huy = self.roommates_online()
        self.assertEqual(kiet.recv_msg(), {"command": "NOTIFY_ONLINE", "data": {"username": "huy"}})
        self.assertNoMessage(huy)  # không báo cho chính mình

    def test_abrupt_disconnect_notifies_offline(self):
        kiet, huy = self.roommates_online()
        kiet.recv_msg()  # NOTIFY_ONLINE của huy
        huy.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        huy.close()  # RST, giống bị kill
        self.assertEqual(kiet.recv_msg(), {"command": "NOTIFY_OFFLINE", "data": {"username": "huy"}})

    def test_quit_notifies_offline(self):
        kiet, huy = self.roommates_online()
        kiet.recv_msg()
        self.request(huy, "QUIT", {})
        self.assertEqual(kiet.recv_msg(), {"command": "NOTIFY_OFFLINE", "data": {"username": "huy"}})

    def test_not_logged_in_disconnect_notifies_nobody(self):
        kiet, huy = self.roommates_online()
        kiet.recv_msg()
        stranger = self.connect()
        stranger.close()
        self.assertNoMessage(kiet)

    # --- LIST_ONLINE, LIST_MEMBERS (Huy, bước 9) --------------------------------

    def test_list_online_and_members(self):
        kiet, huy = self.roommates_online()
        kiet.recv_msg()  # NOTIFY_ONLINE
        msg = self.request(huy, "LIST_ONLINE", {})
        self.assertEqual((msg["command"], msg["data"]),
                         ("LIST_ONLINE_RESPONSE", {"users": ["huy", "kiet"]}))
        msg = self.request(huy, "LIST_MEMBERS", {"room": "lab"})
        self.assertEqual(msg["data"]["members"], [{"username": "kiet", "online": True},
                                                  {"username": "huy", "online": True}])

    # --- tin nhắn (bước 7, dùng phòng giả "lab") ------------------------------

    def assertNoMessage(self, c: Client, wait: float = 0.5):
        with self.assertRaises(TimeoutError):
            c.recv_msg(timeout=wait)

    def test_room_msg_requires_login(self):
        c = self.connect()
        c.send(encode({"command": "ROOM_MSG", "payload": {"room": "lab", "content": "hi"}}))
        self.assertEqual(c.recv_msg()["code"], 401)

    def test_room_msg_reaches_all_members_response_first(self):
        a, b, c = self.logins("kiet", "khoi", "huy")
        a.send(encode({"command": "ROOM_MSG", "requestId": "r1",
                       "payload": {"room": "lab", "content": "Chào cả nhóm"}}))
        resp = a.recv_msg()  # người gửi nhận response TRƯỚC push
        self.assertEqual((resp["command"], resp["requestId"], resp["code"]),
                         ("ROOM_MSG_RESPONSE", "r1", 200))
        self.assertRegex(resp["data"]["ts"], TS_FORMAT)
        expected = {"command": "NOTIFY_ROOM_MSG",
                    "data": {"room": "lab", "from": "kiet", "content": "Chào cả nhóm",
                             "ts": resp["data"]["ts"]}}
        for member in (a, b, c):  # kể cả người gửi
            self.assertEqual(member.recv_msg(), expected)

    def test_room_msg_errors(self):
        a = self.login("kiet")
        cases = [({"room": "khong_co", "content": "hi"}, 404),
                 ({"room": "lab", "content": ""}, 400),
                 ({"room": "lab", "content": "x" * (MAX_TEXT + 1)}, 413),
                 ({"room": "lab"}, 400)]
        for payload, code in cases:
            a.send(encode({"command": "ROOM_MSG", "payload": payload}))
            self.assertEqual(a.recv_msg()["code"], code, payload)
        self.assertNoMessage(a)  # lỗi thì không có push nào

    def test_private_msg_only_to_recipient(self):
        a, b, c = self.logins("kiet", "huy", "khoi")
        a.send(encode({"command": "PRIVATE_MSG", "payload": {"to": "huy", "content": "tối họp nhé"}}))
        resp = a.recv_msg()
        self.assertEqual(resp["code"], 200)
        self.assertEqual(b.recv_msg(), {"command": "NOTIFY_PRIVATE_MSG",
                                        "data": {"from": "kiet", "to": "huy",
                                                 "content": "tối họp nhé", "ts": resp["data"]["ts"]}})
        self.assertNoMessage(a)  # người gửi không nhận lại tin riêng
        self.assertNoMessage(c)

    def test_private_msg_errors(self):
        a = self.login("kiet")
        a.send(encode({"command": "PRIVATE_MSG", "payload": {"to": "kiet", "content": "hi"}}))
        self.assertEqual(a.recv_msg()["code"], 400)   # gửi cho chính mình
        a.send(encode({"command": "PRIVATE_MSG", "payload": {"to": "offline", "content": "hi"}}))
        self.assertEqual(a.recv_msg()["code"], 404)   # không online

    def test_dead_member_does_not_block_room(self):
        a, b, c = self.logins("kiet", "khoi", "huy")
        b.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        b.close()  # khoi chết đột ngột (RST)
        time.sleep(0.3)
        a.send(encode({"command": "ROOM_MSG", "payload": {"room": "lab", "content": "còn ai không"}}))
        self.assertEqual(a.recv_msg()["code"], 200)
        self.assertEqual(c.recv_msg()["data"]["content"], "còn ai không")

    def test_username_freed_after_disconnect(self):
        a = self.login("kiet")
        a.close()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:  # chờ server dọn phiên cũ
            c = self.connect()
            if self.send_login(c, "kiet")["code"] == 200:
                return
            c.close()
            time.sleep(0.1)
        self.fail("không đăng nhập lại được sau khi phiên cũ ngắt")

    # --- ngắt đột ngột -----------------------------------------------------

    def test_abrupt_disconnect_does_not_affect_others(self):
        other = self.connect()
        victim = self.connect()
        victim.send(b'{"command":"KHONG_')  # đang gửi dở thì mất
        # SO_LINGER = 0: close() gửi RST thay vì FIN, giống client bị kill hoặc rút mạng.
        victim.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        victim.close()
        time.sleep(0.3)
        other.send(encode({"command": "KHONG_CO_LENH", "requestId": "ok", "payload": {}}))
        self.assertEqual(other.recv_msg()["requestId"], "ok")
        self.assertEqual(self.proc.poll(), None, "server đã chết")


if __name__ == "__main__":
    unittest.main()
