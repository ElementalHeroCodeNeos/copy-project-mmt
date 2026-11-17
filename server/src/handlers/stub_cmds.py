"""LOGIN GIẢ (TẠM THỜI) để thử ROOM_MSG / PRIVATE_MSG trước khi Huy làm LOGIN thật.

Khi Huy thêm LOGIN thật vào handlers/auth_cmds.py: xoá file này và dòng
`from handlers import stub_cmds` trong handlers/__init__.py. Nếu quên xoá, server
báo "Lệnh LOGIN đã được đăng ký" ngay lúc khởi động (dispatch.py chặn đăng ký trùng).
"""

from dispatch import CommandError, Reply, command, require
from session import registry
from shared import protocol


@command(protocol.LOGIN, auth=False)
def login(session, payload):
    """Giả: nhận mọi username, bỏ qua mật khẩu (chưa có tài khoản, chưa có SQLite)."""
    username = require(payload, "username", str)
    if not username.strip():
        raise CommandError(protocol.BAD_REQUEST, "Username rỗng")
    if not registry.bind(username, session):
        raise CommandError(protocol.CONFLICT,
                           "Tài khoản đang online ở kết nối khác hoặc kết nối này đã đăng nhập")
    return Reply(data={"username": username})
