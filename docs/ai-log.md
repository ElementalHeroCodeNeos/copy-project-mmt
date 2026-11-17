# AI Usage Log
 
> **Mandatory** — see [`INSTRUCTION.md` §7](../INSTRUCTION.md#7-ai-usage-policy).
> Record the AI interactions that **mattered** — ones that produced or shaped design, code, tests or documentation
> that ended up in this repository. A few lines each is enough; you do not need to log every prompt.
>
> Write entries **as you go** (right after the session). The AI assistant configuration in this repo asks your
> assistant to remind you and to suggest a draft entry — but the "what we kept / verified" column must be yours.
 
---
 
## Log
# Log của Đặng Tuấn Kiệt
| # | Date | Member | Tool / model | Task — what you asked | What AI produced | What you kept, changed or rejected — and how you verified it | Files |
|:-:|------|--------|--------------|-----------------------|------------------|---------------------------------------------------------------|-------|
| 1 | 2026-11-04 | Đặng Tuấn Kiệt | Claude | Xác định yêu cầu M1; nháp mục 1–3 proposal và đề xuất chức năng cho Multi-room Chat | Tóm tắt yêu cầu M1; nháp mục Problem, Idea; danh sách chức năng chia theo Must, Nice, Out of scope |  | docs/proposal.md |
| 2 | 2026-11-04 | Đặng Tuấn Kiệt | Claude | Rút gọn scope cho phù hợp thời gian và khả năng nhóm; mô tả chi tiết chức năng | Bảng scope rút gọn, mô tả từng chức năng | Phát hiện việc AI bỏ chức năng PING/PONG có thể khiến client vẫn online mà chỉ ngồi đọc tin nhắn bị kick nhầm -> giữ lại | docs/proposal.md |
| 3 | 2026-11-04 | Đặng Tuấn Kiệt | Claude | Nháp mục 5-6, giải thích thuật ngữ TCP và UDP | Nháp Challenge, Design sketch; giải thích đặc điểm TCP/UDP và lý do chọn TCP cho project Chat | Viết lại phần Transport cho dễ hiểu; chốt ngôn ngữ Python  | docs/proposal.md |
| 4 | 2026-11-05 | Đặng Tuấn Kiệt | Claude | Cân nhắc mở rộng scope: thêm tài khoản, tham gia nhiều phòng, giữ thành viên khi mất kết nối, lưu trữ tin nhắn | Đề xuất các hướng mở rộng kèm ưu nhược điểm; so sánh SQLite với MySQL; gợi ý gửi bù tin theo số thứ tự | Chọn hướng có tài khoản + nhiều phòng, lưu bằng SQLite; bỏ gửi bù theo số thứ tự, thay bằng hiện N tin gần nhất + lệnh xem lịch sử | docs/proposal.md |
| 5 | 2026-11-07 | Đặng Tuấn Kiệt | Claude | Cân nhắc làm GUI, gửi file, chức năng phòng đầy đủ sang Must have | Yêu cầu của thầy không bắt buộc GUI và không có mục điểm liên quan đến GUI; gửi file nằm trong gợi ý của thầy | Thêm chức năng gửi file, chức năng chủ phòng (mật khẩu, xoá phòng, kick) lên Must have; GUI để Nice to have | docs/proposal.md |
| 6 | 2026-11-07  | Đặng Tuấn Kiệt | Claude | So sánh thread-per-client và asyncio | So sánh hai mô hình kèm code minh họa; ví dụ hệ thống thật (Mattermost, Synapse, Zulip) | Giữ lựa chọn thread-per-client vì quy mô client nhỏ và trọng tâm môn là đồng bộ luồng | docs/proposal.md |
| 7 | 2026-11-07 | Đặng Tuấn Kiệt | Claude | Đề xuất phương án phân công công việc | Đề xuất phân công | Chốt phân công phù hợp | docs/proposal.md |
| 8 | 2026-11-10 | Đặng Tuấn Kiệt | Claude | Nháp protocol-design.md phần chức năng được giao (mục 1–8); giải thích các khái niệm như framing, recv(), stateful, push | Bản nháp đặc tả protocol; danh sách điểm chưa chốt kèm phương án | Viết lại những điểm chưa rõ nghĩa; đối chiếu với template và INSTRUCTION.md để kiểm tra đúng yêu cầu thầy | docs/protocol-design.md |
| 9 | 2026-11-11 | Đặng Tuấn Kiệt | Claude | Chốt các điểm còn mở (khung message, requestId, MAX_CLIENTS, ACK mảnh file…); rút gọn sequence diagram; viết lại mục 8 theo cấu trúc Chọn / Đã loại / Đánh đổi; rà soát bản cuối | Đề xuất phương án kèm lý do cho từng điểm; sơ đồ bỏ chi tiết bên trong server; mục 8 viết lại; các lỗi còn sót lại của bản cuối | Bỏ các lựa chọn chi tiết ở mục 8, chọn phương án phù hợp, đối chiếu mã lỗi giữa mục 4 và 5 | docs/protocol-design.md |
| 10 | 2026-11-15 | Đặng Tuấn Kiệt | Claude | Thu hẹp scope về mức tối thiểu; chia lại phân công cho cân bằng | Bảng Must/Nice/Out mới; ước lượng tỷ lệ phân công theo khối lượng code và theo kiến thức mạng; bảng phân công mới; danh sách chỗ cần sửa trong proposal | Chuyển gửi file, lịch sử, chủ phòng sang Nice to have vì không đủ thời gian. | docs/proposal.md |
| 11 | 2026-11-15 | Đặng Tuấn Kiệt | Claude | Rà các phần tốn công so với chức năng chính; cập nhật protocol-design theo scope mới | Chỉ ra 3 chỗ có thể đơn giản hoá (thay phiên cũ, lưu tin, trường `id`); 3 phương án cho PRIVATE_MSG khi người nhận offline; bản protocol-design đã sửa | Chọn cả 3 hướng đơn giản hoá: không lưu tin, bỏ id, trả 409 thay vì thay phiên cũ. Không làm thêm phần lịch sử tối thiểu. | docs/protocol-design.md |
| 12 | 2026-11-15 | Đặng Tuấn Kiệt | Claude | Dựng khung server bước 1: Docker và cấu hình | Dockerfile, compose (volume SQLite), `.env.example`, `config.py`, `server.py` tối thiểu; 4 điểm cần chọn kèm đánh đổi | - Chọn các phương án: Container chạy bằng root; Biến sai thì server dừng ngay, không dùng giá trị mặc định.<br> - Chạy các lệnh kiểm tra và xác nhận kết quả mong muốn | server/Dockerfile, docker-compose.yml, .env.example, .dockerignore, server/src/ |
| 13 | 2026-11-15 | Đặng Tuấn Kiệt | Claude | Khung server bước 2: shared/protocol.py | `FrameBuffer`, `encode`/`decode`, `response`/`push`/`error`, hằng số; 30 unit test; 4 điểm cần chốt kèm đánh đổi | - Chọn các phương án: Mã trạng thái và tên lệnh viết bằng hằng số thường (OK = 200), không dùng enum; requestId sai kiểu thì trả ERROR 400, giữ kết nối; trường message viết tiếng Việt.<br> - Chạy 30 test và đã qua | shared/, tests/test_protocol.py |
| 14 | 2026-11-15 | Đặng Tuấn Kiệt | Claude | Khung server bước 3: nhận kết nối, luồng mỗi client, vòng đọc | Vòng accept, `MAX_CLIENTS` có khoá, vòng đọc với hạn chót theo message, ERROR 400/413/503, stub `cleanup`, `scripts/nc.py`, 9 test tích hợp; 5 điểm cần chốt kèm đánh đổi | Chọn các phương án: timeout tính theo message hoàn chỉnh, không dùng settimeout(90) cho mỗi recv(); luồng client là luồng daemon; đếm MAX_CLIENTS bằng biến đếm cộng Lock, để lộ rõ vùng găng; khi chưa có dispatcher, mọi lệnh tạm trả ERROR 400 "Lệnh không tồn tại"; viết scripts/nc.py để test bằng tay, kèm yêu cầu in UTF-8 cho tiếng Việt. | server/src/, scripts/nc.py, tests/test_server.py |
| 15 | 2026-11-15 | Đặng Tuấn Kiệt | Claude | Khung server bước 4: session.py | `Session` (khoá gửi, thời gian chờ gửi 5 s, gửi lỗi thì shutdown), `SessionRegistry`, `broadcast`; vòng đọc chuyển sang `select()`; 14 test mới; 4 điểm cần chốt kèm đánh đổi |  | server/src/, tests/ |
| 16 | 2026-11-15 | Đặng Tuấn Kiệt | Claude | Khung server bước 5: dispatch.py | `@command`, `Reply` (có `after`, `close`), `CommandError`, `require`/`optional`, thư mục `handlers/`; 15 test; 4 điểm cần chốt kèm đánh đổi |  | server/src/, tests/test_dispatch.py |
| 17 | 2026-11-15 | Đặng Tuấn Kiệt | Claude | Khung server bước 6: PING | Handler `PING` tối thiểu trong `handlers/auth_cmds.py`; bỏ `PONG`, trả `PING_RESPONSE`; 2 test mới; 2 điểm cần chốt kèm đánh đổi |  | server/src/handlers/, shared/protocol.py, tests/test_server.py |
| 18 | 2026-11-15 | Đặng Tuấn Kiệt | Claude | Khung server bước 7: ROOM_MSG, PRIVATE_MSG | `handlers/messages.py` (ROOM_MSG, PRIVATE_MSG, `ts`), stub phòng/`get_user` trong `stubs.py`, `LOGIN` giả (`handlers/stub_cmds.py`); 16 test mới (unit và kịch bản chat nhiều client); 5 điểm cần chốt kèm đánh đổi |  | server/src/handlers/, server/src/stubs.py, tests/ |
| 19 | 2026-11-17 | Đặng Tuấn Kiệt | Claude | Cập nhật protocol-design theo khung server | Sửa mục 3.1–3.4, 4.2, 5, 6.4–6.6: PING_RESPONSE thay PONG, định dạng `ts`, `requestId` phải là chuỗi, thiếu `payload` → 400, thứ tự gửi của PRIVATE_MSG, message tiếng Việt |  | docs/protocol-design.md |
| 20 | 2026-11-18 | Đặng Tuấn Kiệt | Claude | Bước 13: architecture.md — mô hình đồng thời và khoá | Mục 1–4, 6: sơ đồ luồng server, so sánh mô hình kèm số đo thật, bảng 7 loại dữ liệu dùng chung và khoá, thứ tự khoá, đánh đổi thứ tự tin, vòng đời kết nối, 9 quyết định thiết kế; chừa dòng phòng (Khôi) và mục Deployment (Huy) |  | docs/architecture.md |
 
# Log của Hà Anh Khôi
| # | Date | Member | Tool / model | Task — what you asked | What AI produced | What you kept, changed or rejected — and how you verified it | Files |
|:-:|------|--------|--------------|-----------------------|------------------|---------------------------------------------------------------|-------|
| 1 | 2026-11-18 | Hà Anh Khôi | Claude | Bước 15: rooms.py (khoá phòng, luật phòng) | rooms.py: một khoá chung cho mọi phòng, quy tắc tên phòng, create/join/leave trong khoá phòng, giao diện cho ROOM_MSG; 7 unit test (có test hai luồng chen nhau khi phòng bị xoá); sửa test bấp bênh của bước 11. AI tự chọn phương án theo đề xuất (Khôi vắng) |  | server/src/rooms.py, tests/test_rooms.py, tests/test_server.py, tests/test_robustness.py |
| 2 | 2026-11-18 | Hà Anh Khôi | Claude | Bước 16: LIST_ROOMS, CREATE_ROOM, JOIN_ROOM, LEAVE_ROOM | room_cmds.py (4 lệnh, payload/response và mã lỗi); gỡ phòng giả (messages.py dùng rooms.py thật, stubs.py chỉ còn docstring); 3 test lệnh phòng, sửa các test tin nhắn dùng phòng thật. AI tự chọn phương án theo đề xuất |  | server/src/handlers/, server/src/stubs.py, shared/protocol.py, tests/ |
| 3 | 2026-11-18 | Hà Anh Khôi | Claude | Bước 17: thông báo vào/rời phòng | NOTIFY_JOIN/NOTIFY_LEAVE {room, username} tới thành viên online của phòng, gửi sau response và ngoài khoá phòng; recv_response() trong client test; 1 test mới. AI tự chọn phương án theo đề xuất |  | server/src/handlers/room_cmds.py, shared/protocol.py, tests/test_server.py |
| 4 | 2026-11-18 | Hà Anh Khôi | Claude | Bước 18: docs protocol 4.3, 6.7, phần phòng trong architecture | Bảng lệnh phòng và push vào/rời, quy tắc phòng; sơ đồ 6.7; dòng phòng trong bảng dữ liệu dùng chung của architecture |  | docs/protocol-design.md, docs/architecture.md |
| 5 | 2026-11-18 | Hà Anh Khôi | Claude | Bước 20: client Dockerfile và build context | client/Dockerfile (python:3.12-slim, COPY shared/), build context client về thư mục gốc trong docker-compose.yml, client.py tối thiểu (kết nối + PING); chạy thử trong Docker. AI tự chọn phương án theo đề xuất |  | client/Dockerfile, client/src/client.py, docker-compose.yml |
 
# Log của Đỗ Đăng Huy
| # | Date | Member | Tool / model | Task — what you asked | What AI produced | What you kept, changed or rejected — and how you verified it | Files |
|:-:|------|--------|--------------|-----------------------|------------------|---------------------------------------------------------------|-------|
| 1 | 2026-11-18 | Đỗ Đăng Huy | Claude | Bước 2: chốt giao diện storage.py cùng Khôi (bảng users, rooms, room_members) | 11 điểm cần chốt kèm phương án và đánh đổi; storage.py chỉ có giao diện (11 hàm, docstring, lược đồ 3 bảng) | Bỏ delete_room và remove_member vì không có chỗ nào gọi. Chạy lệnh kiểm tra | server/src/storage.py |
| 2 | 2026-11-18 | Đỗ Đăng Huy | Claude | Bước 3: băm và kiểm tra mật khẩu | auth.py (pbkdf2_hmac sha256 600.000 vòng, salt 16 byte, chuẩn hoá NFC, compare_digest); 8 unit test; 7 điểm cần chốt kèm đánh đổi | | server/src/auth.py, tests/test_auth.py |
| 3 | 2026-11-18 | Đỗ Đăng Huy | Claude | Bước 4: cài đặt SQLite (users, rooms, room_members) | storage.py: một kết nối chung + khoá, giao dịch với `with conn`, INSERT OR IGNORE; init_db() trong server.py; DATA_DIR tạm cho test server; 17 unit test (có test 20 luồng đăng ký trùng); 6 điểm cần chốt kèm đánh đổi | Chọn các phương án: một kết nối SQLite chung, kèm một khoá; giao dịch với with conn:; dùng INSERT OR IGNORE để phân biệt trùng khoá với lỗi khoá ngoại; gọi init_db() ở đầu main(); mỗi test server dùng một database tạm riêng; | server/src/storage.py, server/src/server.py, tests/test_server.py, tests/test_storage.py |
| 4 | 2026-11-18 | Đỗ Đăng Huy | Claude | Bước 5: REGISTER, LOGIN thật | REGISTER (đổi chữ thường, kiểm tra quy tắc, 201/400/409), LOGIN (409 → 401 → bind, trả {username, rooms}); gỡ LOGIN giả và get_user giả; 9 test mới, sửa test cũ cho hợp băm thật; 7 điểm cần chốt kèm đánh đổi | Chọn các phương án đề xuất | server/src/handlers/, server/src/stubs.py, tests/test_server.py, tests/test_messages.py |
| 5 | 2026-11-18 | Đỗ Đăng Huy | Claude | Bước 6: QUIT | Handler QUIT (Reply(close=True), không cần đăng nhập); 3 test (đóng sau response, đăng nhập lại được ngay, bỏ qua message sau QUIT) |  | server/src/handlers/auth_cmds.py, tests/test_server.py |
| 6 | 2026-11-18 | Đỗ Đăng Huy | Claude | Bước 8: cleanup thật, báo online/offline | presence.py (cleanup, roommates, NOTIFY_ONLINE/NOTIFY_OFFLINE tới bạn cùng phòng đang online); LOGIN báo online trong after; gỡ cleanup giả; 6 unit test + 4 test với server thật |  | server/src/presence.py, server/src/handlers/auth_cmds.py, server/src/server.py, server/src/stubs.py, shared/protocol.py, tests/test_presence.py, tests/test_server.py |
| 7 | 2026-11-18 | Đỗ Đăng Huy | Claude | Bước 9: LIST_ONLINE, danh sách thành viên phòng | LIST_ONLINE ({users} sắp theo tên); LIST_MEMBERS ({room, members:[{username, online}]}, 404/403, đọc database một lần); 4 unit test + 1 test với server thật |  | server/src/handlers/auth_cmds.py, shared/protocol.py, tests/test_presence.py, tests/test_server.py |
| 8 | 2026-11-18 | Đỗ Đăng Huy | Claude | Bước 10: docs protocol mục 4.1, 4.4, sơ đồ 6.1–6.3, 6.8 | Bảng lệnh REGISTER, LOGIN, PING, QUIT, LIST_ONLINE, LIST_MEMBERS, NOTIFY_ONLINE/OFFLINE; 4 sơ đồ Mermaid; đối chiếu với code bước 5–9 |  | docs/protocol-design.md |
| 9 | 2026-11-18 | Đỗ Đăng Huy | Claude | Bước 11: test nhiều client, kill -9, client im lặng + testing-guide.md | test_robustness.py (30 client cùng lúc, tiến trình client bị kill, client đã đăng nhập im lặng, 200 KB rác); load_test.py chạy với server Docker (50, 90, 110 client); tách ServerHarness trong test_server.py; testing-guide.md với kết quả chạy thật |  | tests/test_robustness.py, tests/load_test.py, tests/test_server.py, docs/testing-guide.md |
 
---
 
## Notable Interactions
 
Describe **2–5 interactions that shaped the project** (a design decision, a hard bug, a rejected suggestion).
These are likely oral-defense topics.
 
### N1. Chốt scope qua nhiều lần cân nhắc
 
- **Member / date / tool:** 
Đặng Tuấn Kiệt / 2026-11-04 → 2026-11-07 / Claude
- **Prompt (key excerpt):** 
Rút gọn scope cho phù hợp thời gian, độ khó; sau đó mở rộng thêm chức năng để hệ thống hoàn thiện hơn
- **What the AI suggested:**
    + Lần 1: Bản rút gọn (chỉ username, một phòng, không lưu trữ)
    + Lần 2: Bản mở rộng (tài khoản, nhiều phòng, SQLite, gửi bù tin theo số thứ tự)
    + Lần 3: Thêm các chức năng gửi file, GUI, phân quyền phòng, các chức năng khác như gửi voice, tự kết nối lại, thông báo theo từ khóa
- **What we decided and why:**
    + Giữ tài khoản + nhiều phòng vì mất kết nối mà bị out khỏi phòng thì không thực thế
    + Bỏ chức năng gửi bù theo số thứ tự, thay bằng N tin gần nhất + lệnh xem lịch sử
    + Đưa chức năng gửi file và chủ phòng lên Must have, GUI để Nice to have
- **What the AI got wrong or missed (if anything):**
+ AI đề xuất bỏ PING/PONG thay bằng chỉ có timeout, khiến người dùng chỉ ngồi đọc bị kill nhầm
+ AI gợi ý theo dõi tin nhắn từ phòng mà người dùng chưa tham gia, không hợp lý