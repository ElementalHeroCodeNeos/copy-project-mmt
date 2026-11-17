"""Phòng (Khôi): khoá phòng và luật phòng. SQL nằm trong storage.py (Huy).

Giao diện cho người khác (kiet-context 10.4):
- Kiệt (ROOM_MSG): `lock`, `room_exists`, `is_member`, `members_of`.
- Huy (online/offline): `rooms_of` (Huy hiện gọi thẳng storage.rooms_of_user, cùng kết quả).

Khoá phòng (chốt bước 15): MỘT khoá chung cho mọi phòng.
- Đơn giản và đúng: `lock(room)` dùng được với tên phòng không tồn tại (ROOM_MSG lấy khoá rồi
  mới kiểm tra phòng còn không), không phải tạo/xoá khoá theo phòng.
- Trong khoá chỉ có vài thao tác database (vài mili giây) và chép danh sách; KHÔNG gửi qua socket.
  Nên dù các phòng phải chờ nhau, thời gian chờ không đáng kể với vài chục client.
- Đã loại: mỗi phòng một khoá (dict tên phòng → khoá, cần thêm khoá bảo vệ dict). Phải quyết khi
  nào xoá khoá của phòng đã xoá: xoá lúc có luồng đang chờ khoá cũ thì hai luồng giữ hai khoá khác
  nhau cho cùng một tên phòng; không xoá thì client gửi ROOM_MSG tới hàng triệu tên phòng bịa ra
  làm dict phình mãi.

Thứ tự khoá (kiet-context 10.9): khoá phòng là khoá NGOÀI CÙNG; bên trong được gọi storage (khoá
database) hoặc registry, không giữ cả hai cùng lúc; không gửi socket trong khoá phòng.
"""

import re
import threading

import storage
from dispatch import CommandError
from shared import protocol

NAME_RE = re.compile(r"[a-z0-9_-]{3,20}")
NAME_RULE = "Tên phòng phải dài 3–20 ký tự, chỉ gồm a-z, 0-9, _ và -"

_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Giao diện cho ROOM_MSG (Kiệt) và người khác
# ---------------------------------------------------------------------------


def lock(room: str):
    """Context manager khoá phòng: `with rooms.lock(room): ...`.

    Một khoá chung, nên dùng được với cả tên phòng không tồn tại.
    """
    return _lock


def room_exists(room: str) -> bool:
    return storage.room_exists(room)


def is_member(room: str, username: str) -> bool:
    return storage.is_member(room, username)


def members_of(room: str) -> list[str]:
    """Mọi thành viên (kể cả offline), theo thứ tự tham gia; bản sao mới mỗi lần gọi."""
    return storage.list_members(room)


def rooms_of(username: str) -> list[str]:
    return storage.rooms_of_user(username)


# ---------------------------------------------------------------------------
# Luật phòng (handlers/room_cmds.py gọi). Lỗi ném CommandError → <LỆNH>_RESPONSE.
# ---------------------------------------------------------------------------


def check_name(room: str) -> None:
    """Tên sai quy tắc → 400. Không tự đổi chữ hoa: tên lưu đúng như gửi, ROOM_MSG dùng y nguyên."""
    if not NAME_RE.fullmatch(room):
        raise CommandError(protocol.BAD_REQUEST, NAME_RULE)


def create(room: str, creator: str) -> None:
    """Tạo phòng, người tạo tự là thành viên. Tên đã có → 409.

    storage.create_room làm cả hai việc trong một giao dịch, và trùng tên bị PRIMARY KEY chặn
    ngay lúc ghi, nên không cần "kiểm tra rồi tạo". Vẫn lấy khoá phòng để không chen giữa
    một JOIN/LEAVE khác (giữ đúng quy ước: mọi thay đổi phòng đều trong khoá phòng).
    """
    with lock(room):
        if not storage.create_room(room, creator):
            raise CommandError(protocol.CONFLICT, f"Phòng {room} đã tồn tại")


def join(room: str, username: str) -> list[str]:
    """Tham gia phòng. Trả danh sách thành viên SAU khi vào (bản sao, để báo cho mọi người).

    Không tồn tại → 404; đã là thành viên → 409. "Kiểm tra tồn tại" và "thêm" nằm trong cùng
    khoá phòng với "rời + xoá phòng trống" (leave), nên không ai vào được phòng đang bị xoá.
    """
    with lock(room):
        if not storage.room_exists(room):
            raise CommandError(protocol.NOT_FOUND, f"Phòng {room} không tồn tại")
        if not storage.add_member(room, username):
            raise CommandError(protocol.CONFLICT, f"Bạn đã ở trong phòng {room}")
        return storage.list_members(room)


def leave(room: str, username: str) -> tuple[bool, list[str]]:
    """Rời phòng. Trả `(deleted, còn_lại)`: phòng vừa bị xoá vì trống chưa, và thành viên còn lại.

    Không tồn tại → 404; không phải thành viên → 403. Rời, kiểm tra trống, xoá: một giao dịch
    (storage.leave_room) và trong khoá phòng.
    """
    with lock(room):
        if not storage.room_exists(room):
            raise CommandError(protocol.NOT_FOUND, f"Phòng {room} không tồn tại")
        left, deleted = storage.leave_room(room, username)
        if not left:
            raise CommandError(protocol.FORBIDDEN, f"Bạn không phải thành viên phòng {room}")
        return deleted, ([] if deleted else storage.list_members(room))
