"""Kết nối tới server (Khôi): luồng đọc socket, PING nền, phát hiện mất kết nối.

Client có 3 luồng (chốt bước 21):
- Luồng chính: đọc bàn phím, gọi `request()` để gửi lệnh.
- Luồng đọc (`_read_loop`): đọc socket, tách message bằng FrameBuffer (shared/protocol.py), gọi
  `on_message(msg)` cho MỌI message (response lẫn push). Server có thể đẩy NOTIFY_* bất cứ lúc nào,
  nên không thể "gửi rồi chờ đọc response" trong luồng chính.
- Luồng PING (`_ping_loop`): gửi PING mỗi `ping_interval` giây để server không ngắt vì im lặng.

Hai luồng cùng gửi (luồng chính và luồng PING) nên `send()` giữ `_send_lock`: mỗi message được
`sendall()` liền một mạch, không bị chen giữa (cùng lý do với Session.send_lock ở server).

Mất kết nối, phát hiện bằng một trong ba cách, rồi gọi `on_disconnect(lý_do)` đúng một lần:
- Server đóng (EOF) hoặc lỗi socket (reset) khi đọc.
- Gửi thất bại.
- Quá `read_timeout` giây không nhận được message nào (server treo, mạng đứt mà không có FIN/RST).
  Server trả PING_RESPONSE mỗi lần client PING, nên bình thường không bao giờ im quá 30 s.
"""

import itertools
import select
import socket
import threading
import time

from shared import protocol
from shared.protocol import FrameBuffer, FrameTooLarge, ProtocolError

RECV_SIZE = 4096
SEND_TIMEOUT_SEC = 10.0  # server không đọc nữa thì gửi bỏ cuộc sau 10 s, coi như mất kết nối


class Connection:
    def __init__(self, host: str, port: int, on_message, on_disconnect,
                 ping_interval: float = 30, read_timeout: float = 90):
        self.host, self.port = host, port
        self.on_message = on_message          # gọi từ luồng đọc
        self.on_disconnect = on_disconnect    # gọi đúng một lần, từ luồng phát hiện ra
        self.ping_interval = ping_interval
        self.read_timeout = read_timeout
        self.sock: socket.socket | None = None
        self._send_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._stopped = threading.Event()     # đã dừng (mất kết nối hoặc tự đóng)
        self._ids = itertools.count(1)

    # --- mở / đóng ------------------------------------------------------------

    def connect(self) -> None:
        """Kết nối rồi chạy luồng đọc và luồng PING (daemon: thoát theo chương trình)."""
        self.sock = socket.create_connection((self.host, self.port), timeout=10)
        self.sock.settimeout(SEND_TIMEOUT_SEC)  # chỉ ảnh hưởng gửi; đọc dùng select()
        threading.Thread(target=self._read_loop, name="reader", daemon=True).start()
        threading.Thread(target=self._ping_loop, name="pinger", daemon=True).start()

    def close(self) -> None:
        """Tự đóng (sau QUIT): dừng các luồng, KHÔNG gọi on_disconnect."""
        with self._state_lock:
            if self._stopped.is_set():
                return
            self._stopped.set()
        self._close_socket()

    @property
    def connected(self) -> bool:
        return self.sock is not None and not self._stopped.is_set()

    # --- gửi --------------------------------------------------------------------

    def request(self, command: str, payload: dict | None = None) -> str | None:
        """Gửi một request kèm requestId tự tăng. Trả requestId, hoặc None nếu gửi thất bại."""
        rid = str(next(self._ids))
        ok = self.send({"command": command, "requestId": rid, "payload": payload or {}})
        return rid if ok else None

    def send(self, msg: dict) -> bool:
        data = protocol.encode(msg)
        with self._send_lock:
            if self._stopped.is_set():
                return False
            try:
                self.sock.sendall(data)
                return True
            except OSError as exc:
                lost = exc
        self._lost(f"gửi thất bại ({lost})")
        return False

    # --- các luồng nền -----------------------------------------------------------

    def _read_loop(self) -> None:
        buf = FrameBuffer(protocol.DEFAULT_MAX_BYTES)
        deadline = time.monotonic() + self.read_timeout
        while not self._stopped.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._lost(f"{self.read_timeout:g} s không nhận được gì từ server")
                return
            try:
                readable, _, _ = select.select([self.sock], [], [], remaining)
                if not readable:
                    continue  # đầu vòng sẽ thấy hết hạn
                data = self.sock.recv(RECV_SIZE)
            except (OSError, ValueError) as exc:  # ValueError: socket đã bị đóng
                self._lost(f"lỗi kết nối ({exc})")
                return
            if not data:
                self._lost("server đã đóng kết nối")
                return
            try:
                lines = buf.feed(data)
            except FrameTooLarge:
                self._lost("server gửi message quá lớn")
                return
            if lines:
                deadline = time.monotonic() + self.read_timeout
            for line in lines:
                try:
                    msg = protocol.decode(line)
                except ProtocolError:
                    continue  # dòng hỏng: bỏ qua, đọc tiếp
                self.on_message(msg)

    def _ping_loop(self) -> None:
        # Event.wait(): ngủ ping_interval giây, nhưng thức dậy ngay khi kết nối dừng.
        while not self._stopped.wait(self.ping_interval):
            self.send({"command": protocol.PING, "payload": {}})

    # --- mất kết nối ---------------------------------------------------------------

    def _lost(self, reason: str) -> None:
        """Gọi on_disconnect đúng một lần, dù luồng đọc và luồng gửi cùng phát hiện."""
        with self._state_lock:
            if self._stopped.is_set():
                return  # đã dừng (đã báo, hoặc người dùng tự đóng sau QUIT)
            self._stopped.set()
        self._close_socket()
        self.on_disconnect(reason)

    def _close_socket(self) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
