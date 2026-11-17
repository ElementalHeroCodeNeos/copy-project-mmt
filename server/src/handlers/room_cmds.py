"""Lệnh phòng (Khôi): LIST_ROOMS, CREATE_ROOM, JOIN_ROOM, LEAVE_ROOM (protocol-design 4.3).

Luật phòng và khoá phòng nằm trong rooms.py; file này chỉ lấy tham số và trả response.
"""

import rooms
import storage
from dispatch import Reply, command, require
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
    members = rooms.join(room, session.username)
    return Reply(data={"room": room, "members": members})


@command(protocol.LEAVE_ROOM)
def leave_room(session, payload):
    """Rời phòng. 200 `{room, deleted}`; không tồn tại 404; không phải thành viên 403.

    `deleted`: phòng vừa bị xoá vì không còn ai. Thành viên phòng chỉ mất khi LEAVE_ROOM; thoát
    app hay mất kết nối thì vẫn còn trong phòng.
    """
    room = require(payload, "room", str)
    deleted, _remaining = rooms.leave(room, session.username)
    return Reply(data={"room": room, "deleted": deleted})
