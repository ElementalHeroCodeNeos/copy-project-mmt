"""Phiên kết nối và danh sách người online (kiet-context mục 10.2).

- Session: một kết nối TCP; gửi có khoá riêng để nhiều luồng cùng gửi tới một
  client không trộn dữ liệu.
- SessionRegistry: username -> Session của những người đang online, có khoá riêng.
- broadcast(): gửi một message tới nhiều người, ngoài mọi khoá dữ liệu chung.
"""

import logging
import socket
import threading

from shared import protocol

log = logging.getLogger("session")

# Thời gian tối đa cho một lần gửi. Client "đứng hình" (không đọc) làm bộ đệm gửi
# đầy; sau SEND_TIMEOUT_SEC giây người gửi bỏ cuộc thay vì bị treo theo.
SEND_TIMEOUT_SEC = 5.0


class Session:
    def __init__(self, sock: socket.socket, addr):
        self.sock = sock
        self.addr = addr
        self.peer = f"{addr[0]}:{addr[1]}"
        self.username: str | None = None  # chỉ registry.bind/unbind được gán
        self.send_lock = threading.Lock()
        self.broken = False  # True sau lần gửi thất bại đầu tiên
        # Timeout của socket giờ chỉ áp cho việc gửi; vòng đọc dùng select() riêng.
        sock.settimeout(SEND_TIMEOUT_SEC)

    def send(self, msg: dict) -> bool:
        """Gửi một message. Thất bại thì trả False, không ném lỗi.

        Gửi lỗi hoặc hết giờ thì coi client là đã chết: sendall() hết giờ có thể đã
        gửi dở một phần message, nên luồng dữ liệu tới client này đã hỏng. Ta
        shutdown socket để luồng đọc của client đó thức dậy và tự dọn phiên.
        """
        data = protocol.encode(msg)
        with self.send_lock:  # một message phải đi liền một mạch, không bị chen giữa
            if self.broken:
                return False
            try:
                self.sock.sendall(data)
                return True
            except OSError as exc:  # gồm TimeoutError, BrokenPipeError, ConnectionResetError
                self.broken = True
                log.warning("Gửi tới %s thất bại (%r), ngắt kết nối", self.peer, exc)
                self._shutdown()
                return False

    def _shutdown(self) -> None:
        # Dùng shutdown chứ không close: luồng đọc của client này có thể đang chờ
        # trên socket; close từ luồng khác không an toàn, còn shutdown chỉ đánh thức
        # luồng đó (recv trả b"") để nó tự đóng trong cleanup().
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def close(self) -> None:
        """Đóng socket; gọi nhiều lần không lỗi. Chỉ luồng của chính client gọi."""
        with self.send_lock:  # chờ lần gửi đang dở (nếu có) xong rồi mới đóng
            self.broken = True
            try:
                self.sock.close()
            except OSError:
                pass


class SessionRegistry:
    """Danh sách người online toàn server. Mọi truy cập đều qua self._lock."""

    def __init__(self):
        self._lock = threading.Lock()
        self._by_name: dict[str, Session] = {}

    def bind(self, username: str, session: Session) -> bool:
        """Gắn username với session. False nếu username đã online hoặc session đã đăng nhập.

        "Kiểm tra đã online chưa" và "gắn" nằm trong cùng một khoá, nên hai lần LOGIN
        cùng lúc vào một tài khoản chỉ có đúng một lần thành công.
        """
        with self._lock:
            if username in self._by_name or session.username is not None:
                return False
            self._by_name[username] = session
            session.username = username
            return True

    def unbind(self, username: str, session: Session) -> bool:
        """Gỡ username, chỉ khi nó vẫn gắn với đúng session này. True nếu đã gỡ."""
        with self._lock:
            if self._by_name.get(username) is not session:
                return False
            del self._by_name[username]
            session.username = None
            return True

    def get(self, username: str) -> Session | None:
        with self._lock:
            return self._by_name.get(username)

    def is_online(self, username: str) -> bool:
        with self._lock:
            return username in self._by_name

    def online_usernames(self) -> list[str]:
        """Bản sao danh sách người online, sắp theo tên."""
        with self._lock:
            return sorted(self._by_name)

    def sessions_of(self, usernames) -> list[Session]:
        """Bản sao các phiên của những người đang online trong `usernames` (bỏ trùng)."""
        with self._lock:
            result, seen = [], set()
            for name in usernames:
                s = self._by_name.get(name)
                if s is not None and name not in seen:
                    seen.add(name)
                    result.append(s)
            return result


registry = SessionRegistry()


def broadcast(usernames, msg: dict, reg: SessionRegistry = registry) -> None:
    """Gửi msg tới những người đang online trong `usernames`.

    Lấy bản sao danh sách phiên trong khoá registry, nhả khoá, rồi mới gửi: không giữ
    khoá dữ liệu chung nào trong lúc gửi qua socket (gửi có thể chờ tới SEND_TIMEOUT_SEC).
    Phiên chết thì send() trả False và bị bỏ qua, không ảnh hưởng người khác.
    """
    for s in reg.sessions_of(usernames):
        s.send(msg)
