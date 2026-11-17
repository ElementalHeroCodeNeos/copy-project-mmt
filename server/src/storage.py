"""Lưu trữ SQLite (Huy): tài khoản, phòng, thành viên phòng.

Không lưu tin nhắn (scope đã thu hẹp). Database nằm ở `config.DATA_DIR/chat.db`, trong
Docker volume `chat-data`, nên còn nguyên sau `docker compose down` (mất khi `down -v`).

Lược đồ: xem `_SCHEMA` bên dưới (chốt bước 2).

Quy ước cho người gọi:
- `storage.py` KHÔNG kiểm tra quy tắc username, mật khẩu hay tên phòng: lưu đúng chuỗi được
  truyền vào. Handler `REGISTER`/`LOGIN` (Huy) và `rooms.py` (Khôi) kiểm tra trước khi gọi.
- Trùng khoá (username, tên phòng, thành viên) → hàm trả `False`. Mọi lỗi SQLite khác (kể cả
  vi phạm khoá ngoại) để lan lên; dispatcher trả 500 và ghi log, kết nối vẫn giữ.
- Mọi hàm đều tự lấy khoá database bên trong. Khoá database là khoá TRONG CÙNG
  (kiet-context 10.9): trong lúc giữ nó, không gọi `registry`, không gửi qua socket, không
  gọi hàm storage khác. Được gọi hàm storage bên trong `with rooms.lock(room)`.
- Các hàm chỉ bảo vệ từng thao tác riêng lẻ. Chuỗi thao tác "kiểm tra rồi thay đổi" trên một
  phòng (ví dụ JOIN_ROOM: room_exists rồi add_member) phải nằm trong `rooms.lock(room)`.

Nhiều luồng (chốt bước 4, 1A): MỘT kết nối chung cho cả server + MỘT `threading.Lock`; mọi hàm,
cả đọc lẫn ghi, giữ khoá trong lúc dùng kết nối. Các thao tác database chạy lần lượt, mỗi thao
tác vài mili giây, đủ cho vài chục client.
"""

import os
import sqlite3
import threading

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,            -- đã kiểm tra quy tắc và đổi về chữ thường ở handler
    pw_hash  TEXT NOT NULL,               -- hex, từ auth.hash_password
    salt     TEXT NOT NULL                -- hex
);
CREATE TABLE IF NOT EXISTS rooms (
    name TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS room_members (
    seq      INTEGER PRIMARY KEY AUTOINCREMENT,                        -- thứ tự tham gia
    room     TEXT NOT NULL REFERENCES rooms(name) ON DELETE CASCADE,   -- xoá phòng thì dòng
                                                                       -- thành viên tự xoá theo
    username TEXT NOT NULL REFERENCES users(username),
    UNIQUE (room, username)
);
"""

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()  # khoá database: khoá trong cùng


def _db() -> sqlite3.Connection:
    """Kết nối hiện tại. Chỉ gọi khi đang giữ `_lock`."""
    if _conn is None:
        raise RuntimeError("Chưa gọi storage.init_db()")
    return _conn


# ---------------------------------------------------------------------------
# Khởi tạo
# ---------------------------------------------------------------------------


def init_db(db_path: str | None = None) -> None:
    """Mở database và tạo 3 bảng nếu chưa có. Gọi một lần trong `main()` của server.py.

    `db_path=None` → `config.DATA_DIR/chat.db` (tạo thư mục nếu chưa có). Test truyền một
    file tạm hoặc `":memory:"` để không đụng database thật.
    Gọi lại lần nữa thì đóng database cũ và mở database mới (dùng trong test).
    """
    global _conn
    if db_path is None:
        db_path = os.path.join(config.DATA_DIR, "chat.db")
    if db_path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    # check_same_thread=False: mặc định Python cấm dùng kết nối ở luồng khác luồng đã tạo nó.
    # Ở đây mọi luồng client dùng chung kết nối, an toàn vì luôn giữ `_lock`.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite tắt khoá ngoại mặc định
    conn.executescript(_SCHEMA)
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = conn


# ---------------------------------------------------------------------------
# Tài khoản (Huy dùng trong REGISTER, LOGIN; Kiệt dùng get_user trong PRIVATE_MSG)
# ---------------------------------------------------------------------------


def create_user(username: str, pw_hash: str, salt: str) -> bool:
    """Thêm tài khoản. `False` nếu username đã có.

    Trùng bị chặn bằng PRIMARY KEY ngay khi ghi, không kiểm tra trước rồi mới ghi: hai
    REGISTER cùng username cùng lúc thì đúng một lần thành công.
    """
    # INSERT OR IGNORE: trùng khoá thì SQLite bỏ qua câu lệnh (rowcount = 0) thay vì báo lỗi.
    # Vi phạm khoá ngoại KHÔNG bị bỏ qua, vẫn báo lỗi (chốt bước 4, 3A).
    with _lock, _db() as conn:  # `with conn`: xong thì commit, lỗi thì rollback
        cur = conn.execute(
            "INSERT OR IGNORE INTO users (username, pw_hash, salt) VALUES (?, ?, ?)",
            (username, pw_hash, salt))
        return cur.rowcount == 1


def get_user(username: str) -> dict | None:
    """`{"username", "pw_hash", "salt"}`, hoặc `None` nếu không có tài khoản này."""
    with _lock:
        row = _db().execute(
            "SELECT username, pw_hash, salt FROM users WHERE username = ?",
            (username,)).fetchone()
    if row is None:
        return None
    return {"username": row[0], "pw_hash": row[1], "salt": row[2]}


# ---------------------------------------------------------------------------
# Phòng (Khôi gọi từ rooms.py, trong rooms.lock(room) khi cần)
# ---------------------------------------------------------------------------


def create_room(room: str, creator: str) -> bool:
    """Tạo phòng và thêm `creator` làm thành viên đầu tiên, trong MỘT giao dịch.

    `False` nếu phòng đã có (không thay đổi gì). Server sập giữa chừng thì không để lại
    phòng trống. `creator` không có trong bảng users → lỗi khoá ngoại, không tạo gì.
    """
    with _lock, _db() as conn:
        cur = conn.execute("INSERT OR IGNORE INTO rooms (name) VALUES (?)", (room,))
        if cur.rowcount == 0:
            return False
        conn.execute("INSERT INTO room_members (room, username) VALUES (?, ?)",
                     (room, creator))
        return True


def leave_room(room: str, username: str) -> tuple[bool, bool]:
    """Gỡ `username` khỏi phòng; nếu phòng không còn ai thì xoá phòng, trong MỘT giao dịch.

    Trả `(left, deleted)`: `left=False` nếu người đó không phải thành viên (khi đó
    `deleted=False`); `deleted=True` nếu phòng vừa bị xoá vì trống.
    Người gọi giữ `rooms.lock(room)` để không ai JOIN chen vào giữa lúc phòng đang bị xoá.
    """
    with _lock, _db() as conn:
        cur = conn.execute("DELETE FROM room_members WHERE room = ? AND username = ?",
                           (room, username))
        if cur.rowcount == 0:
            return False, False
        (remaining,) = conn.execute("SELECT COUNT(*) FROM room_members WHERE room = ?",
                                    (room,)).fetchone()
        if remaining > 0:
            return True, False
        conn.execute("DELETE FROM rooms WHERE name = ?", (room,))
        return True, True


def room_exists(room: str) -> bool:
    """Phòng có tồn tại không."""
    with _lock:
        row = _db().execute("SELECT 1 FROM rooms WHERE name = ?", (room,)).fetchone()
    return row is not None


def add_member(room: str, username: str) -> bool:
    """Thêm thành viên. `False` nếu người đó đã là thành viên.

    Điều kiện: phòng đang tồn tại (người gọi kiểm tra `room_exists` trong cùng
    `rooms.lock(room)`). Phòng hoặc user không tồn tại thì khoá ngoại báo lỗi, lỗi lan lên (500).
    """
    with _lock, _db() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO room_members (room, username) VALUES (?, ?)",
            (room, username))
        return cur.rowcount == 1


def is_member(room: str, username: str) -> bool:
    """`username` có phải thành viên phòng `room` không (phòng không tồn tại → `False`)."""
    with _lock:
        row = _db().execute("SELECT 1 FROM room_members WHERE room = ? AND username = ?",
                            (room, username)).fetchone()
    return row is not None


def list_members(room: str) -> list[str]:
    """Mọi thành viên của phòng, kể cả offline, theo thứ tự tham gia (cột `seq`).

    Phòng không tồn tại → `[]`. Lọc người online thì dùng `registry`, ngoài hàm này.
    """
    with _lock:
        rows = _db().execute(
            "SELECT username FROM room_members WHERE room = ? ORDER BY seq",
            (room,)).fetchall()
    return [r[0] for r in rows]


def list_rooms() -> list[dict]:
    """Mọi phòng, sắp theo tên: `[{"name": "lab", "members": 3}, ...]`.

    `members` là số thành viên (kể cả offline), đếm bằng một câu GROUP BY.
    """
    with _lock:
        rows = _db().execute(
            "SELECT r.name, COUNT(m.username) FROM rooms r "
            "LEFT JOIN room_members m ON m.room = r.name "
            "GROUP BY r.name ORDER BY r.name").fetchall()
    return [{"name": name, "members": count} for name, count in rows]


def rooms_of_user(username: str) -> list[str]:
    """Các phòng `username` đang tham gia, sắp theo tên. Huy dùng khi báo online/offline."""
    with _lock:
        rows = _db().execute(
            "SELECT room FROM room_members WHERE username = ? ORDER BY room",
            (username,)).fetchall()
    return [r[0] for r in rows]
