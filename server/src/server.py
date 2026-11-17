"""Server MRCP/1.0: nhận kết nối, mỗi client một luồng, vòng đọc tách message.

Khung bước 3 (nhận kết nối, vòng đọc), bước 4 (Session: gửi có khoá, chờ đọc bằng
select), bước 5 (chuyển message cho dispatcher).
"""

import logging
import select
import signal
import socket
import sys
import threading
import time

try:
    import config
except ValueError as exc:  # config.ConfigError là lớp con của ValueError
    print(f"Lỗi cấu hình: {exc}", file=sys.stderr)
    sys.exit(1)

from shared import protocol
from shared.protocol import FrameBuffer, FrameTooLarge, ProtocolError
import handlers  # noqa: F401  (import để các file handler đăng ký lệnh bằng @command)
from dispatch import dispatch
from session import Session
import storage
from stubs import cleanup  # TẠM: thay bằng cleanup() thật của Huy

log = logging.getLogger("server")

RECV_SIZE = 4096           # số byte tối đa đọc trong một lần recv()
REJECT_SEND_TIMEOUT = 1.0  # giây; gửi ERROR 503 không được làm luồng chính bị treo
DRAIN_SEC = 1.0            # giây; đọc bỏ dữ liệu còn lại sau ERROR 413 trước khi đóng


# ---------------------------------------------------------------------------
# Giới hạn số client (MAX_CLIENTS)
# ---------------------------------------------------------------------------

_client_count = 0
_client_count_lock = threading.Lock()


def _try_reserve_slot() -> bool:
    """Giữ một chỗ cho client mới; trả False nếu đã đủ MAX_CLIENTS."""
    global _client_count
    # "Kiểm tra rồi tăng" phải nằm trọn trong khoá. Nếu không, hai luồng cùng thấy
    # count = 99 và cùng tăng lên, server nhận 101 client.
    with _client_count_lock:
        if _client_count >= config.MAX_CLIENTS:
            return False
        _client_count += 1
        return True


def _release_slot() -> None:
    global _client_count
    with _client_count_lock:
        _client_count -= 1


# ---------------------------------------------------------------------------
# Đọc có hạn chót
# ---------------------------------------------------------------------------


def _wait_readable(sock: socket.socket, timeout: float) -> bool:
    """Chờ tới khi socket có dữ liệu (hoặc EOF/lỗi) trong tối đa `timeout` giây.

    Dùng select() thay vì sock.settimeout(): timeout của socket đã dành cho việc gửi
    (Session.SEND_TIMEOUT_SEC), và nó áp cho cả socket, kể cả khi luồng khác gửi.
    """
    readable, _, _ = select.select([sock], [], [], max(timeout, 0))
    return bool(readable)


def _send_final_and_drain(session: Session, msg: dict) -> None:
    """Gửi message cuối cùng (ERROR 413), báo hết dữ liệu, đọc bỏ phần client còn gửi.

    Nếu đóng socket khi trong bộ đệm nhận vẫn còn dữ liệu chưa đọc, hệ điều hành gửi
    RST thay vì FIN, và client có thể mất luôn ERROR 413 chưa kịp đọc. Vì vậy:
    gửi, shutdown(SHUT_WR) để gửi FIN sau message, rồi đọc bỏ tối đa DRAIN_SEC giây.
    """
    if not session.send(msg):
        return  # đã hỏng, Session đã shutdown socket
    sock = session.sock
    try:
        sock.shutdown(socket.SHUT_WR)
        end = time.monotonic() + DRAIN_SEC
        while (remaining := end - time.monotonic()) > 0:
            if _wait_readable(sock, remaining) and not sock.recv(RECV_SIZE):
                break  # client đã đóng
    except (OSError, ValueError):
        pass  # socket lỗi: đằng nào cũng đóng


# ---------------------------------------------------------------------------
# Xử lý từng message
# ---------------------------------------------------------------------------


def _handle_line(session: Session, line: bytes) -> bool:
    """Decode một dòng rồi chuyển cho dispatcher. Trả True nếu phải đóng kết nối."""
    try:
        msg = protocol.decode(line)
    except ProtocolError as exc:
        # Sai nội dung nhưng ranh giới message rõ ràng: trả 400, giữ kết nối.
        session.send(protocol.error(protocol.BAD_REQUEST, str(exc)))
        return False
    return dispatch(session, msg)


# ---------------------------------------------------------------------------
# Luồng phục vụ một client
# ---------------------------------------------------------------------------


def _serve_client(conn: socket.socket, addr) -> None:
    session = Session(conn, addr)
    peer = session.peer
    log.info("Client %s đã kết nối", peer)
    buffer = FrameBuffer(config.MAX_MESSAGE_BYTES)
    timeout = config.READ_TIMEOUT_SEC
    # Hạn chót chỉ được dời khi nhận đủ ít nhất một message hoàn chỉnh (không phải
    # mỗi khi nhận byte), để client gửi nhỏ giọt từng byte không giữ kết nối mãi.
    deadline = time.monotonic() + timeout
    reason = "không rõ"
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                reason = f"không nhận được message nào trong {timeout} s"
                break
            try:
                if not _wait_readable(conn, remaining):
                    continue  # hết thời gian chờ; đầu vòng sẽ thấy remaining <= 0
                data = conn.recv(RECV_SIZE)
            except (OSError, ValueError) as exc:  # ConnectionResetError, socket đã đóng...
                reason = f"lỗi socket: {exc!r}"
                break
            if not data:
                # EOF: client đóng, hoặc Session.send() đã shutdown vì gửi thất bại.
                reason = ("gửi thất bại, client không đọc hoặc đã chết" if session.broken
                          else "client đóng kết nối (EOF)")
                break
            try:
                lines = buffer.feed(data)
            except FrameTooLarge:
                _send_final_and_drain(session, protocol.error(
                    protocol.TOO_LARGE, f"Message vượt quá {config.MAX_MESSAGE_BYTES} byte"))
                reason = "message quá lớn (413)"
                break
            if lines:
                deadline = time.monotonic() + timeout
            if any(_handle_line(session, line) for line in lines):
                # any() dừng ở dòng đầu tiên trả True: các dòng sau QUIT bị bỏ qua.
                reason = "đóng theo yêu cầu của lệnh (Reply.close)"
                break
    except Exception:
        # Lỗi bất ngờ chỉ làm chết luồng của client này, không làm sập server.
        log.exception("Lỗi bất ngờ khi phục vụ %s", peer)
        reason = "lỗi bất ngờ trong server"
    finally:
        try:
            cleanup(session)
        except Exception:
            log.exception("cleanup() lỗi với %s", peer)
        finally:
            _release_slot()  # luôn trả chỗ, kể cả khi cleanup lỗi
        log.info("Client %s đã ngắt: %s", peer, reason)


# ---------------------------------------------------------------------------
# Luồng chính: accept
# ---------------------------------------------------------------------------


def _reject(conn: socket.socket, peer: str) -> None:
    """Từ chối client thứ MAX_CLIENTS + 1: gửi ERROR 503 rồi đóng (chưa tạo Session)."""
    log.warning("Từ chối %s: đã đủ %d client", peer, config.MAX_CLIENTS)
    try:
        conn.settimeout(REJECT_SEND_TIMEOUT)
        conn.sendall(protocol.encode(protocol.error(
            protocol.SERVICE_UNAVAILABLE, f"Server đã đủ {config.MAX_CLIENTS} client, thử lại sau")))
    except OSError:
        pass
    finally:
        conn.close()


def _handle_sigterm(signum, frame):
    # `docker compose down` gửi SIGTERM. Python chạy là PID 1 trong container nên
    # không tự dừng khi nhận SIGTERM; ta đổi nó thành SystemExit để thoát gọn.
    raise SystemExit(0)


def main() -> None:
    logging.basicConfig(
        level=config.LOG_LEVEL,
        format="%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s",
    )
    signal.signal(signal.SIGTERM, _handle_sigterm)
    storage.init_db()  # Huy: tạo database rỗng nếu chưa có; lỗi thì dừng trước khi nhận client

    listener =socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Cho phép bind lại cổng ngay sau khi server khởi động lại.
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((config.SERVER_HOST, config.SERVER_PORT))
    listener.listen()
    log.info("Đang lắng nghe trên %s:%d (tối đa %d client)",
             config.SERVER_HOST, config.SERVER_PORT, config.MAX_CLIENTS)

    try:
        while True:
            try:
                conn, addr = listener.accept()
            except OSError as exc:
                # Ví dụ hết file descriptor: ghi log, chờ chút rồi thử lại, không sập server.
                log.warning("accept() lỗi: %r", exc)
                time.sleep(0.1)
                continue
            peer = f"{addr[0]}:{addr[1]}"
            if not _try_reserve_slot():
                _reject(conn, peer)
                continue
            thread = threading.Thread(target=_serve_client, args=(conn, addr),
                                      name=f"client-{peer}", daemon=True)
            try:
                thread.start()
            except RuntimeError:  # không tạo được luồng mới
                log.exception("Không tạo được luồng cho %s", peer)
                _release_slot()
                conn.close()
    except (KeyboardInterrupt, SystemExit):
        log.info("Đang dừng server")
    finally:
        listener.close()


if __name__ == "__main__":
    main()
