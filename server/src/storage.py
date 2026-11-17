"""Lưu trữ SQLite (Huy): tài khoản, phòng, thành viên phòng.

Không lưu tin nhắn (scope đã thu hẹp). Database nằm ở `config.DATA_DIR/chat.db`, trong
Docker volume `chat-data`, nên còn nguyên sau `docker compose down` (mất khi `down -v`).

Lược đồ (chốt bước 2):

    users(
        username TEXT PRIMARY KEY,           -- đã kiểm tra quy tắc và đổi về chữ thường ở handler
        pw_hash  TEXT NOT NULL,              -- hex, từ auth.hash_password
        salt     TEXT NOT NULL               -- hex
    )
    rooms(
        name TEXT PRIMARY KEY                -- tạo trùng → IntegrityError → create_room trả False
    )
    room_members(
        seq      INTEGER PRIMARY KEY AUTOINCREMENT,                        -- thứ tự tham gia
        room     TEXT NOT NULL REFERENCES rooms(name) ON DELETE CASCADE,  -- leave_room xoá phòng
                                                                          -- trống thì dòng tự xoá theo
        username TEXT NOT NULL REFERENCES users(username),
        UNIQUE(room, username)
    )
    -- Bật `PRAGMA foreign_keys = ON` cho mỗi kết nối (SQLite tắt mặc định).

Quy ước cho người gọi:
- `storage.py` KHÔNG kiểm tra quy tắc username, mật khẩu hay tên phòng: lưu đúng chuỗi được
  truyền vào. Handler `REGISTER`/`LOGIN` (Huy) và `rooms.py` (Khôi) kiểm tra trước khi gọi.
- Trùng khoá (username, tên phòng, thành viên) → hàm trả `False`. Mọi lỗi SQLite khác để lan
  lên; dispatcher trả 500 và ghi log, kết nối vẫn giữ.
- Mọi hàm đều tự lấy khoá database bên trong. Khoá database là khoá TRONG CÙNG
  (kiet-context 10.9): trong lúc giữ nó, không gọi `registry`, không gửi qua socket, không
  gọi hàm storage khác. Được gọi hàm storage bên trong `with rooms.lock(room)`.
- Các hàm chỉ bảo vệ từng thao tác riêng lẻ. Chuỗi thao tác "kiểm tra rồi thay đổi" trên một
  phòng (ví dụ JOIN_ROOM: room_exists rồi add_member) phải nằm trong `rooms.lock(room)`.

Cách dùng SQLite với nhiều luồng (một kết nối chung + khoá, hay mỗi lần một kết nối…) chốt
ở bước 4; không ảnh hưởng giao diện dưới đây.
"""


# ---------------------------------------------------------------------------
# Khởi tạo
# ---------------------------------------------------------------------------


def init_db(db_path: str | None = None) -> None:
    """Mở database và tạo 3 bảng nếu chưa có. Gọi một lần trong `main()` của server.py.

    `db_path=None` → `config.DATA_DIR/chat.db` (tạo thư mục nếu chưa có). Test truyền một
    file tạm hoặc `":memory:"` để không đụng database thật.
    Gọi lại lần nữa thì đóng database cũ và mở database mới (dùng trong test).
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Tài khoản (Huy dùng trong REGISTER, LOGIN; Kiệt dùng get_user trong PRIVATE_MSG)
# ---------------------------------------------------------------------------


def create_user(username: str, pw_hash: str, salt: str) -> bool:
    """Thêm tài khoản. `False` nếu username đã có.

    Trùng bị chặn bằng PRIMARY KEY (UNIQUE) ngay khi ghi, không kiểm tra trước rồi mới
    ghi: hai REGISTER cùng username cùng lúc thì đúng một lần thành công.
    """
    raise NotImplementedError


def get_user(username: str) -> dict | None:
    """`{"username", "pw_hash", "salt"}`, hoặc `None` nếu không có tài khoản này."""
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Phòng (Khôi gọi từ rooms.py, trong rooms.lock(room) khi cần)
# ---------------------------------------------------------------------------


def create_room(room: str, creator: str) -> bool:
    """Tạo phòng và thêm `creator` làm thành viên đầu tiên, trong MỘT giao dịch.

    `False` nếu phòng đã có (không thay đổi gì). Server sập giữa chừng thì không để lại
    phòng trống.
    """
    raise NotImplementedError


def leave_room(room: str, username: str) -> tuple[bool, bool]:
    """Gỡ `username` khỏi phòng; nếu phòng không còn ai thì xoá phòng, trong MỘT giao dịch.

    Trả `(left, deleted)`: `left=False` nếu người đó không phải thành viên (khi đó
    `deleted=False`); `deleted=True` nếu phòng vừa bị xoá vì trống.
    Người gọi giữ `rooms.lock(room)` để không ai JOIN chen vào giữa lúc phòng đang bị xoá.
    """
    raise NotImplementedError


def room_exists(room: str) -> bool:
    """Phòng có tồn tại không."""
    raise NotImplementedError


def add_member(room: str, username: str) -> bool:
    """Thêm thành viên. `False` nếu người đó đã là thành viên.

    Điều kiện: phòng đang tồn tại (người gọi kiểm tra `room_exists` trong cùng
    `rooms.lock(room)`). Phòng không tồn tại thì khoá ngoại báo lỗi, lỗi lan lên (500).
    """
    raise NotImplementedError


def is_member(room: str, username: str) -> bool:
    """`username` có phải thành viên phòng `room` không (phòng không tồn tại → `False`)."""
    raise NotImplementedError


def list_members(room: str) -> list[str]:
    """Mọi thành viên của phòng, kể cả offline, theo thứ tự tham gia (cột `seq`).

    Phòng không tồn tại → `[]`. Lọc người online thì dùng `registry`, ngoài hàm này.
    """
    raise NotImplementedError


def list_rooms() -> list[dict]:
    """Mọi phòng, sắp theo tên: `[{"name": "lab", "members": 3}, ...]`.

    `members` là số thành viên (kể cả offline), đếm bằng một câu GROUP BY.
    """
    raise NotImplementedError


def rooms_of_user(username: str) -> list[str]:
    """Các phòng `username` đang tham gia, sắp theo tên. Huy dùng khi báo online/offline."""
    raise NotImplementedError
