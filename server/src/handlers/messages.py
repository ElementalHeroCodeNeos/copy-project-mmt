"""Tin nhắn văn bản (Kiệt): ROOM_MSG, PRIVATE_MSG (protocol-design mục 4.2).

Không lưu tin nhắn (scope đã thu hẹp): server chỉ chuyển tiếp tới người đang online.
"""

from datetime import datetime, timezone

import config
import stubs as rooms        # TẠM: đổi thành `import rooms` khi Khôi xong rooms.py
from dispatch import CommandError, Reply, command, require
from session import broadcast, registry
from shared import protocol
from storage import get_user

_NOT_REACHABLE = "Người nhận không tồn tại hoặc đang offline"


def _now_ts() -> str:
    """Thời điểm server nhận tin: ISO 8601 giờ UTC, đến giây, ví dụ 2026-11-15T09:00:00Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check_content(payload: dict) -> str:
    """Lấy `content`: thiếu/sai kiểu → 400, chỉ có khoảng trắng → 400, quá dài → 413.

    Nội dung gửi đi giữ nguyên (không cắt khoảng trắng).
    """
    content = require(payload, "content", str)
    if not content.strip():
        raise CommandError(protocol.BAD_REQUEST, "Tin nhắn rỗng")
    if len(content) > config.MAX_TEXT_CHARS:
        raise CommandError(protocol.TOO_LARGE,
                           f"Tin nhắn dài quá {config.MAX_TEXT_CHARS} ký tự")
    return content


@command(protocol.ROOM_MSG)
def room_msg(session, payload):
    room = require(payload, "room", str)
    content = _check_content(payload)
    sender = session.username

    # Trong khoá phòng: kiểm tra phòng còn tồn tại, người gửi là thành viên, và chép
    # danh sách thành viên. Nhả khoá rồi mới gửi (kiet-context 10.9): gửi có thể chờ
    # tới 5 s nếu có client đứng hình, không được bắt cả phòng chờ theo.
    with rooms.lock(room):
        if not rooms.room_exists(room):
            raise CommandError(protocol.NOT_FOUND, f"Phòng {room} không tồn tại")
        if not rooms.is_member(room, sender):
            raise CommandError(protocol.FORBIDDEN, f"Bạn không phải thành viên phòng {room}")
        members = list(rooms.members_of(room))

    ts = _now_ts()
    notify = protocol.push(protocol.NOTIFY_ROOM_MSG,
                           {"room": room, "from": sender, "content": content, "ts": ts})
    # Push đi SAU response (dispatcher chạy `after` sau khi gửi response), tới mọi
    # thành viên đang online, kể cả người gửi. Hai người cùng nhắn một lúc thì các
    # người nhận có thể thấy hai tin theo thứ tự khác nhau (chốt bước 7: 3A).
    return Reply(data={"ts": ts}, after=[lambda: broadcast(members, notify)])


@command(protocol.PRIVATE_MSG)
def private_msg(session, payload):
    to = require(payload, "to", str)
    content = _check_content(payload)
    sender = session.username
    if to == sender:
        raise CommandError(protocol.BAD_REQUEST, "Không thể nhắn riêng cho chính mình")
    # Cùng một câu cho "không tồn tại" và "offline" (protocol-design mục 4.2).
    if get_user(to) is None:
        raise CommandError(protocol.NOT_FOUND, _NOT_REACHABLE)
    target = registry.get(to)

    ts = _now_ts()
    notify = protocol.push(protocol.NOTIFY_PRIVATE_MSG,
                           {"from": sender, "to": to, "content": content, "ts": ts})
    # Gửi cho người nhận TRƯỚC, rồi mới trả lời người gửi (chốt bước 7: 4A): người nhận
    # vừa offline thì người gửi nhận 404 thay vì 200 rồi tin mất. "Gửi được" nghĩa là
    # đã ghi vào bộ đệm TCP, không có nghĩa là người nhận đã đọc.
    if target is None or not target.send(notify):
        raise CommandError(protocol.NOT_FOUND, _NOT_REACHABLE)
    return Reply(data={"ts": ts})
