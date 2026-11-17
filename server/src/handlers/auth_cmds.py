"""Lệnh phiên (Huy): REGISTER, LOGIN, PING, QUIT, ...

PING: bản tối thiểu do Kiệt viết ở khung bước 6 để khung có một lệnh chạy từ đầu
đến cuối; Huy có thể sửa khi làm phần heartbeat. Các lệnh còn lại Huy viết tiếp
vào file này.
"""

from dispatch import Reply, command
from shared import protocol


@command(protocol.PING, auth=False)
def ping(session, payload):
    """Nhịp tim: client gửi PING mỗi PING_INTERVAL_SEC giây, server trả PING_RESPONSE 200.

    Không cần làm gì thêm: vòng đọc (server.py) tự dời hạn chót khi nhận đủ một
    message, và client tự đặt lại bộ đếm "mất kết nối" khi nhận được response.
    """
    return Reply()
