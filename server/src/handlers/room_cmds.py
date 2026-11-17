"""Lệnh phòng (Khôi): LIST_ROOMS, CREATE_ROOM, JOIN_ROOM, LEAVE_ROOM (protocol-design 4.3).

Thông báo vào/rời phòng (NOTIFY_JOIN, NOTIFY_LEAVE) gửi tới thành viên đang online của phòng đó,
trừ chính người vào/rời.

Luật phòng và khoá phòng nằm trong rooms.py; file này chỉ lấy tham số và trả response.
"""

import rooms
import storage
from dispatch import Reply, command, require
from session import broadcast
from shared import protocol


@command(protocol.LIST_ROOMS)
def list_rooms(session, payload):
    """Mọi phòng, sắp theo tên: `{rooms: [{name, members, joined}]}`.

    `members`: số thành viên (kể cả offline); `joined`: người gọi có trong phòng không.
    """
    mine = set(storage.rooms_of_user(session.username))
    return Reply(data={"rooms": [
        {"name": r["name"], "members": r["members"], "joined": r["name"] in mine}
        for r in storage.list_rooms()]})


@command(protocol.CREATE_ROOM)
def create_room(session, payload):
    """Tạo phòng, người tạo tự là thành viên. 201 `{room}`; tên sai 400; đã có 409."""
    room = require(payload, "room", str)
    rooms.check_name(room)
    rooms.create(room, session.username)
    return Reply(code=protocol.CREATED, data={"room": room})


@command(protocol.JOIN_ROOM)
def join_room(session, payload):
    """Tham gia phòng. 200 `{room, members}`; không tồn tại 404; đã ở trong phòng 409."""
    room = require(payload, "room", str)
    me = session.username
    members = rooms.join(room, me)  # danh sách chép trong khoá phòng
    # Báo cho các thành viên khác SAU response và NGOÀI khoá phòng (gửi có thể chờ tới 5 s).
    others = [m for m in members if m != me]
    notify = protocol.push(protocol.NOTIFY_JOIN, {"room": room, "username": me})
    return Reply(data={"room": room, "members": members},
                 after=[lambda: broadcast(others, notify)])


@command(protocol.LEAVE_ROOM)
def leave_room(session, payload):
    """Rời phòng. 200 `{room, deleted}`; không tồn tại 404; không phải thành viên 403.

    `deleted`: phòng vừa bị xoá vì không còn ai. Thành viên phòng chỉ mất khi LEAVE_ROOM; thoát
    app hay mất kết nối thì vẫn còn trong phòng.
    """
    room = require(payload, "room", str)
    me = session.username
    deleted, remaining = rooms.leave(room, me)
    notify = protocol.push(protocol.NOTIFY_LEAVE, {"room": room, "username": me})
    # Phòng bị xoá thì remaining rỗng: không ai để báo.
    return Reply(data={"room": room, "deleted": deleted},
                 after=[lambda: broadcast(remaining, notify)])
