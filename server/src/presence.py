"""Trạng thái online (Huy): dọn phiên khi ngắt, báo online/offline.

Thông báo chỉ gửi tới "bạn cùng phòng": thành viên ĐANG ONLINE của các phòng mà người đó
tham gia (không gửi cho chính người đó, không gửi toàn server).

Thứ tự khoá (kiet-context 10.9): đọc database (khoá database, trong cùng) rồi nhả; sau đó
broadcast lấy bản sao phiên trong khoá registry rồi nhả; gửi qua socket NGOÀI mọi khoá.
"""

import logging

import storage
from session import Session, broadcast, registry
from shared import protocol

log = logging.getLogger("presence")


def roommates(username: str) -> list[str]:
    """Mọi thành viên (kể cả offline) của các phòng `username` tham gia, trừ chính họ.

    Không trùng lặp, giữ thứ tự gặp lần đầu. broadcast() tự bỏ người offline.
    Chỉ đọc database, không lấy khoá phòng: danh sách có thể cũ đi một chút nếu ai đó vừa
    JOIN/LEAVE cùng lúc, chấp nhận được với một thông báo trạng thái.
    """
    seen: dict[str, None] = {}  # dict giữ thứ tự chèn, dùng như "set có thứ tự"
    for room in storage.rooms_of_user(username):
        for member in storage.list_members(room):
            if member != username:
                seen[member] = None
    return list(seen)


def notify_online(username: str) -> None:
    """Gửi NOTIFY_ONLINE {username} tới bạn cùng phòng. LOGIN gọi trong Reply.after."""
    broadcast(roommates(username), protocol.push(protocol.NOTIFY_ONLINE, {"username": username}))


def notify_offline(username: str) -> None:
    """Gửi NOTIFY_OFFLINE {username} tới bạn cùng phòng. cleanup() gọi sau khi unbind."""
    broadcast(roommates(username), protocol.push(protocol.NOTIFY_OFFLINE, {"username": username}))


def cleanup(session: Session) -> None:
    """Dọn phiên khi kết nối kết thúc vì bất kỳ lý do gì (EOF, reset, timeout, QUIT, 413).

    server.py gọi trong `finally` của luồng client, đúng một lần cho mỗi kết nối.
    1. Đã đăng nhập thì unbind. Chỉ báo offline khi unbind trả True, tức là phiên này đúng
       là phiên đang gắn với tài khoản (không báo nhầm khi phiên đã bị gỡ trước đó).
    2. Luôn đóng socket, kể cả khi báo offline lỗi (ví dụ lỗi database).
    """
    username = session.username
    try:
        if username is not None and registry.unbind(username, session):
            notify_offline(username)
    finally:
        session.close()
