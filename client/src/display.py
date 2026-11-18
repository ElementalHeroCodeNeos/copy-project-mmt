"""Hiển thị message từ server thành dòng chữ dễ đọc (Khôi, bước 22).

Tin của nhiều phòng hiện xen nhau trên cùng một màn hình, nên mỗi dòng có tiền tố phòng `[lab]`
(tin nhắn riêng: `[riêng]`). Các hàm ở đây không đụng tới mạng, nên test được riêng.
"""

from datetime import datetime, timezone


def local_time(ts: str | None) -> str:
    """'2026-11-15T09:00:00Z' (giờ UTC của server) → '16:00' theo giờ của máy đang chạy client."""
    if not ts:
        return "--:--"
    try:
        utc = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return ts
    return utc.astimezone().strftime("%H:%M")


def format_push(msg: dict) -> str | None:
    d = msg.get("data", {})
    match msg.get("command"):
        case "NOTIFY_ROOM_MSG":
            return f"[{local_time(d.get('ts'))}] [{d.get('room')}] {d.get('from')}: {d.get('content')}"
        case "NOTIFY_PRIVATE_MSG":
            return f"[{local_time(d.get('ts'))}] [riêng] {d.get('from')} → bạn: {d.get('content')}"
        case "NOTIFY_JOIN":
            return f"* {d.get('username')} vào phòng {d.get('room')}"
        case "NOTIFY_LEAVE":
            return f"* {d.get('username')} rời phòng {d.get('room')}"
        case "NOTIFY_ONLINE":
            return f"* {d.get('username')} online"
        case "NOTIFY_OFFLINE":
            return f"* {d.get('username')} offline"
    return f"? {msg}"


def format_response(msg: dict, sent: dict | None) -> str | None:
    """Response → dòng chữ. `sent` là request đã gửi cùng requestId (để biết nội dung đã gửi).

    Trả None nếu không cần in gì (ví dụ ROOM_MSG thành công: tin sẽ hiện qua NOTIFY_ROOM_MSG).
    """
    code, d = msg.get("code"), msg.get("data", {})
    command = msg.get("command", "").removesuffix("_RESPONSE")
    if code is None or code >= 400:
        return f"!! {msg.get('message', 'Lỗi')} ({code})"
    match command:
        case "REGISTER":
            return f"Đã đăng ký {d.get('username')}. Đăng nhập: /login {d.get('username')} <mật khẩu>"
        case "LOGIN":
            rooms = ", ".join(d.get("rooms", [])) or "(chưa có, /rooms để xem, /join để vào)"
            return f"Đăng nhập thành công: {d.get('username')}. Phòng của bạn: {rooms}"
        case "LIST_ROOMS":
            if not d.get("rooms"):
                return "Chưa có phòng nào. Tạo phòng: /create <tên>"
            return "Các phòng:\n" + "\n".join(
                f"  {r['name']} ({r['members']} người){'  ✓ đã vào' if r.get('joined') else ''}"
                for r in d["rooms"])
        case "CREATE_ROOM":
            return f"Đã tạo phòng {d.get('room')}, bạn đang ở phòng này"
        case "JOIN_ROOM":
            return f"Đã vào phòng {d.get('room')}. Thành viên: {', '.join(d.get('members', []))}"
        case "LEAVE_ROOM":
            gone = " (phòng không còn ai nên đã bị xoá)" if d.get("deleted") else ""
            return f"Đã rời phòng {d.get('room')}{gone}"
        case "LIST_ONLINE":
            return "Đang online: " + ", ".join(d.get("users", []))
        case "LIST_MEMBERS":
            people = ", ".join(f"{m['username']}{' (online)' if m['online'] else ''}"
                               for m in d.get("members", []))
            return f"Thành viên phòng {d.get('room')}: {people}"
        case "PRIVATE_MSG":
            p = (sent or {}).get("payload", {})
            return f"[{local_time(d.get('ts'))}] [riêng] bạn → {p.get('to')}: {p.get('content')}"
        case "ROOM_MSG" | "QUIT" | "PING":
            return None
    return None


def format_message(msg: dict, sent: dict | None = None) -> str | None:
    command = msg.get("command", "")
    if command == "ERROR":
        return f"!! Lỗi từ server: {msg.get('message')} ({msg.get('code')})"
    if command.startswith("NOTIFY_"):
        return format_push(msg)
    return format_response(msg, sent)
