"""Bản giả (stub) TẠM THỜI cho các phần người khác phụ trách.

Mỗi hàm ở đây có cùng tên và tham số với bản thật (kiet-context mục 10.4–10.6). Khi
bản thật xong thì đổi dòng import ở nơi dùng và xoá hàm tương ứng ở đây:

| Hàm ở đây                         | Bản thật           | Nơi đang import             |
|-----------------------------------|--------------------|-----------------------------|
| cleanup                           | Huy                | server.py                   |
| room_exists, is_member,           | rooms.py (Khôi)    | handlers/messages.py        |
| members_of, lock                  |                    | (`import stubs as rooms`)   |
"""

import threading

from session import Session, registry


# ---------------------------------------------------------------------------
# cleanup (Huy, kiet-context 10.6)
# ---------------------------------------------------------------------------


def cleanup(session: Session) -> None:
    """Giả cho cleanup(session) của Huy.

    Bản giả: gỡ khỏi danh sách online (nếu đã đăng nhập) rồi đóng socket.
    Bản thật của Huy thêm: nếu unbind trả True thì báo offline cho các phòng liên quan.
    """
    if session.username is not None:
        registry.unbind(session.username, session)
    session.close()


# ---------------------------------------------------------------------------
# rooms.py (Khôi, kiet-context 10.4)
# ---------------------------------------------------------------------------

FAKE_ROOM = "lab"
_rooms_lock = threading.Lock()  # bản giả: một khoá chung cho mọi phòng


def room_exists(room: str) -> bool:
    """Giả: chỉ có phòng `lab`."""
    return room == FAKE_ROOM


def is_member(room: str, username: str) -> bool:
    """Giả: ai cũng là thành viên phòng `lab`."""
    return room == FAKE_ROOM


def members_of(room: str) -> list[str]:
    """Giả: thành viên phòng `lab` là mọi người đang online.

    Bản thật trả mọi thành viên, kể cả offline (lấy từ SQLite); broadcast tự lọc người online.
    """
    return registry.online_usernames() if room == FAKE_ROOM else []


def lock(room: str):
    """Giả: context manager khoá phòng (`with rooms.lock(room): ...`).

    Bản thật cần dùng được cả với tên phòng KHÔNG tồn tại: ROOM_MSG lấy khoá trước,
    rồi mới kiểm tra phòng còn tồn tại không (phòng có thể vừa bị xoá khi trống).
    """
    return _rooms_lock
