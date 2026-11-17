"""Lệnh phiên (Huy): REGISTER, LOGIN, PING, QUIT, ...

PING: bản tối thiểu do Kiệt viết ở khung bước 6 để khung có một lệnh chạy từ đầu
đến cuối; Huy có thể sửa khi làm phần heartbeat.
"""

import re

import auth
import presence
import storage
from dispatch import CommandError, Reply, command, require
from session import registry
from shared import protocol

USERNAME_RE = re.compile(r"[a-z0-9_]{3,20}")  # kiểm tra SAU khi đổi về chữ thường
PASSWORD_MIN, PASSWORD_MAX = 6, 128

_BAD_CREDENTIALS = "Sai tên đăng nhập hoặc mật khẩu"


@command(protocol.REGISTER, auth=False)
def register(session, payload):
    """Tạo tài khoản. 201; sai quy tắc → 400; username đã có → 409. Không tự đăng nhập."""
    username = require(payload, "username", str).lower()  # "Huy" → "huy" (chốt bước 5, 2A)
    password = require(payload, "password", str)
    if not USERNAME_RE.fullmatch(username):
        raise CommandError(protocol.BAD_REQUEST,
                           "Username phải dài 3–20 ký tự, chỉ gồm a-z, 0-9, _")
    if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise CommandError(protocol.BAD_REQUEST,
                           f"Mật khẩu phải dài {PASSWORD_MIN}–{PASSWORD_MAX} ký tự")

    pw_hash, salt = auth.hash_password(password)  # ~0,4 s, không giữ khoá nào
    # Trùng bị PRIMARY KEY chặn ngay lúc ghi (không kiểm tra trước rồi mới ghi): hai người
    # đăng ký cùng username cùng lúc thì đúng một người được 201.
    if not storage.create_user(username, pw_hash, salt):
        raise CommandError(protocol.CONFLICT, f"Username {username} đã có người dùng")
    return Reply(code=protocol.CREATED, data={"username": username})


@command(protocol.LOGIN, auth=False)
def login(session, payload):
    """Đăng nhập. 200 `{username, rooms}`; sai → 401; đã đăng nhập / đang online → 409.

    Không kiểm tra quy tắc username/mật khẩu (chốt bước 5, 3A): sai định dạng thì cũng
    không tìm thấy tài khoản → 401.
    """
    username = require(payload, "username", str).lower()
    password = require(payload, "password", str)

    # 1. Kiểm tra trước để khỏi tốn 0,4 s băm mật khẩu. registry.bind() vẫn kiểm tra lại
    #    trong khoá, nên dù hai LOGIN cùng kết nối chen nhau thì cũng không gắn hai lần.
    if session.username is not None:
        raise CommandError(protocol.CONFLICT, "Kết nối này đã đăng nhập")

    # 2. Mật khẩu kiểm tra TRƯỚC khi xem có online không: người không biết mật khẩu
    #    không dò được ai đang online. Cùng một câu cho "không có tài khoản" và "sai mật khẩu".
    user = storage.get_user(username)
    if user is None or not auth.verify_password(password, user["pw_hash"], user["salt"]):
        raise CommandError(protocol.UNAUTHORIZED, _BAD_CREDENTIALS)

    # 3. Kiểm tra "đang online" và gắn phiên trong CÙNG khoá registry (bind): hai LOGIN
    #    cùng tài khoản cùng lúc thì chỉ một cái thành công. bind tự gán session.username.
    if not registry.bind(username, session):
        raise CommandError(protocol.CONFLICT, "Tài khoản đang online ở kết nối khác")

    # Thành viên phòng giữ lại qua các lần đăng nhập: trả luôn để client hiện danh sách phòng.
    # Báo online cho bạn cùng phòng SAU response (Reply.after): người đăng nhập nhận
    # LOGIN_RESPONSE trước, rồi mới tới lượt người khác nhận NOTIFY_ONLINE.
    return Reply(data={"username": username, "rooms": storage.rooms_of_user(username)},
                 after=[lambda: presence.notify_online(username)])


@command(protocol.QUIT, auth=False)
def quit_(session, payload):
    """Thoát: trả QUIT_RESPONSE 200 rồi server đóng kết nối và gọi cleanup().

    Không cần đăng nhập (chưa đăng nhập cũng thoát được). `close=True`: dispatcher gửi
    response xong thì server.py thoát vòng đọc; các message gửi sau QUIT trong cùng một
    lần nhận bị bỏ qua. Dọn phiên (gỡ khỏi danh sách online, báo offline) nằm ở cleanup(),
    giống hệt khi client ngắt đột ngột, nên không viết hai lần.
    """
    return Reply(close=True)


@command(protocol.PING, auth=False)
def ping(session, payload):
    """Nhịp tim: client gửi PING mỗi PING_INTERVAL_SEC giây, server trả PING_RESPONSE 200.

    Không cần làm gì thêm: vòng đọc (server.py) tự dời hạn chót khi nhận đủ một
    message, và client tự đặt lại bộ đếm "mất kết nối" khi nhận được response.
    """
    return Reply()
