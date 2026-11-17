"""Các handler lệnh. Mỗi file đăng ký lệnh của mình bằng @command (dispatch.py).

@command chỉ đăng ký khi file được import. Vì vậy mỗi file handler phải được import
TƯỜNG MINH ở đây; quên import thì lệnh đó coi như không tồn tại (ERROR 400).

Tên file kết thúc bằng _cmds khi trùng tên với module dữ liệu ở server/src
(rooms.py, auth.py), để không nhầm hai module.
"""

from handlers import auth_cmds  # noqa: F401  Huy: REGISTER, LOGIN, PING, QUIT, LIST_ONLINE, ...
from handlers import messages   # noqa: F401  Kiệt: ROOM_MSG, PRIVATE_MSG

# Bỏ dấu # khi file tương ứng đã có:
# from handlers import room_cmds    # Khôi: LIST_ROOMS, CREATE_ROOM, JOIN_ROOM, LEAVE_ROOM
