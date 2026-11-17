# Project Proposal — Milestone M1
 
---
 
## 1. Team & Topic
 
- **Team:** Nhóm 14 - Đặng Tuấn Kiệt, Hà Anh Khôi, Đỗ Đăng Huy
- **Topic:** Multi-room Chat System qua TCP

---

## 2. Problem
 
- What problem are you solving, and **who** has it?  
  Các nhóm nhỏ như CLB, nhóm lab hay nhóm làm đồ án cần một kênh chat theo chủ đề (phòng). Họ cần tự kiểm soát dữ liệu và chạy được trong mạng nội bộ, đặc biệt khi phòng máy không có internet, hoặc mạng trường/công ty chặn các ứng dụng chat.
- How is it solved today (existing solutions)? Why is that not good enough for your scenario?  
  Hiện nay giải quyết thế nào: Dùng Zalo, Messenger, Discord hoặc Slack.  
  Vì sao chưa đủ cho tình huống này:
    + Phụ thuộc internet: mất Internet, hoặc mạng chặn các ứng dụng chat thì không chat được.
    + Phụ thuộc bên thứ ba: Dữ liệu nội bộ (tin nhắn, code, tài liệu) đi qua và được lưu trên máy chủ bên thứ 3, nên nhóm không kiểm soát được
    + Phải đăng ký tài khoản bằng số điện thoại hoặc email
    + Không tự host được, hoặc tự host thì quá nặng (Mattermost, Rocket.Chat cần database và nhiều dịch vụ).

---

## 3. Idea
 
- Your solution in 3–5 sentences.  
  Một chat server gọn nhẹ, chạy bằng một lệnh docker compose up, giao tiếp qua giao thức tầng ứng dụng tự thiết kế trên TCP. Người dùng đăng ký và đăng nhập bằng username, tham gia nhiều phòng cùng lúc, nhắn tin trong phòng và nhắn riêng. Server phục vụ nhiều client cùng lúc, không sập khi client mất kết nối đột ngột hay gửi dữ liệu rác.
- What is **interesting or new** about it compared with existing solutions?  
  Điểm thú vị:  
  + Không cần internet, chạy trong mạng nội bộ
  + Không cần tài khoản email/số điện thoại để đăng nhập

---

## 4. Scope
 
| Must have (M3) | Nice to have | Out of scope |
|----------------|--------------|--------------|
|Đăng ký, đăng nhập bằng username và mật khẩu |Gửi file |Gửi ảnh, tin nhắn thoại |
|Xem danh sách phòng, tạo/tham gia/rời phòng |Xem lịch sử tin nhắn |Gọi thoại/ video |
|Gửi tin nhắn văn bản (trong phòng và nhắn riêng) |Chủ phòng: đặt mật khẩu phòng, xoá phòng, kick thành viên |Sửa/xoá tin |
|Xem danh sách người online, thành viên phòng, thông báo vào/rời phòng |GUI |Tìm kiếm tin |
|Xử lý client ngắt kết nối đột ngột, im lặng quá lâu hoặc gửi dữ liệu lỗi | |Duyệt yêu cầu tham gia, đổi tên phòng |
| | |Mã hoá đường truyền |

---
 
## 5. Key Networking Challenge
 
What is the hardest networking problem in your project, and how do you plan to tackle it?  
### Trạng thái dùng chung (shared state) giữa nhiều luồng
- Vấn đề: Server lưu danh sách tài khoản, người đang online, thành viên phòng (shared state). Mỗi client được phục vụ bởi một thread riêng, nhưng mọi thread đều đọc và sửa chung các dữ liệu này, nên các thao tác có thể chen nhau.  
Ví dụ 1: Hai người đăng ký cùng username là “kiet” gần như cùng lúc. Cả hai thread đều kiểm tra thấy username chưa tồn tại, rồi cả hai cùng thêm vào, nên hai người dùng chung một username.
Ví dụ 2: hai thread cùng gửi dữ liệu vào socket của một client (một thread gửi tin phòng, một thread gửi thông báo), dữ liệu hai message bị trộn vào nhau.
- Giải pháp:
  + Đặt bước kiểm tra và cập nhật trong cùng một vùng khóa (critical section, dùng lock). Thread nào trên server lấy được khóa trước thì làm xong rồi mới nhả khóa, các thread khác phải chờ đến lượt. 
  + Mỗi client có một khóa gửi riêng, để tại một thời điểm chỉ một thread được ghi vào socket của client đó.
  + Không giữ khóa của dữ liệu chung trong lúc gọi send(), để một client có mạng chậm không làm cả server phải chờ theo.

---

## 6. Initial Design Sketch
 
- **Transport:** TCP / UDP / both — why?
  * Giao thức tầng vận chuyển (transport): TCP 
  * Giải thích:
    - Chat cần: 
      + Các thông điệp (message) không bị mất/đảo thứ tự để tránh cuộc trò chuyện sai nghĩa
      + Các lệnh như LOGIN, JOIN_ROOM bị mất thì trạng thái giữa client và server sẽ bị lệch. 
    - TCP hỗ trợ:
      + Có kết nối (connection-oriented): bắt tay 3 bước trước khi gửi, nên server biết chính xác client nào đang kết nối, và biết khi client ngắt.
      + Tin cậy (reliable): gói nào mất thì TCP tự gửi lại nhờ cơ chế xác nhận (ACK).
      + Đúng thứ tự (ordered): nhờ đánh số thứ tự (sequence number), các gói tin đến đúng thứ tự gửi.  
      Nhược điểm: TCP là luồng byte nên phải tự tách thông điệp (message framing). Một gói bị mất thì phải chờ gửi lại, nên độ trễ tăng.
    - UDP không có cả 3 đặc điểm đó nên phải tự làm thủ công. Ưu điểm: UDP không cần tách thông điệp (mỗi datagram là một thông điệp riêng) và độ trễ thấp hơn.
- **Message framing & format:** *(first idea)*
  Cách tách và định dạng thông điệp (message framing & format): Mỗi thông điệp (message) là một object JSON trên một dòng, kết thúc bằng "\n", mã hóa UTF-8. Kích thước tối đa dự kiến 64 KB; vượt quá thì trả lỗi và đóng kết nối đó.
- **First 3–5 commands:** *(name, direction, purpose)*
  Các lệnh đầu tiên:
  | Lệnh | Chiều | Ý nghĩa |
  |-------|-------|-------|
  | LOGIN | C->S | Đăng nhập bằng username và mật khẩu |
  | JOIN_ROOM | C->S | Tham gia một phòng đã có |
  | ROOM_MSG | C->S | Gửi tin nhắn vào một phòng |
  | NOTIFY_ROOM_MSG | S->C | Server đẩy (push) tin nhắn của phòng tới các thành viên |
  | PING/PONG | C<->S | Heartbeat, kiểm tra kết nối còn sống |
- **Concurrency model:** *(first idea)*
  Mô hình xử lý đồng thời (concurrency model): Mỗi client một luồng (thread-per-client), dùng socket chặn (blocking socket).
- **Language(s):**
  Python - có sẵn thư viện socket và threading, nên code ngắn, dễ giải thích

---

## 7. Alternatives Considered
 
| Option | Chosen? | Why / why not |
|--------|:-------:|---------------|
|TCP |V |Dữ liệu đến đủ, đúng thứ tự (reliable, ordered), phù hợp ứng dụng chat |
|UDP |X |Phải tự xử lý mất gói tin, sai thứ tự |
|Phân tách bằng \n (delimiter) + JSON |V |- Dễ cài đặt: mỗi message kết thúc bằng ký tự \n, bên nhận đọc đến ký tự này thì biết đã nhận đủ một message<br>- Dữ liệu dạng chữ nên dễ quan sát, gỡ lỗi<br>- An toàn: JSON mã hoá ký tự xuống dòng trong nội dung, nên \n chỉ xuất hiện ở cuối message, do vậy không cắt nhầm tin |
|Tiền tố độ dài (length-prefix) |X |Gửi được dữ liệu nhị phân trực tiếp, nhưng phức tạp hơn |
|Mỗi client một luồng (thread-per-client) |V |Hệ thống tự host cho một nhóm nhỏ (vài chục client); code đọc tuần tự, dễ hiểu |
|Nhóm luồng cố định (thread pool) |X |Với blocking socket, số luồng cố định nên chỉ phục vụ được K client cùng lúc, client thứ K+1 phải chờ; với kết nối chat kéo dài thì không có lợi gì hơn thread-per-client.|
|Vòng lặp sự kiện (event loop / asyncio) |X |Một luồng phục vụ được hàng nghìn client nhờ non-blocking socket, nhưng nhóm không cần quy mô đó (vài chục client). Thread-per-client đủ dùng, code đọc tuần tự, dễ giải thích hơn. |
|SQLite |V |Có sẵn trong Python, chỉ là một file, không cần thêm service |
|MySQL/PostgreSQL |X |Phải chạy thêm 1 service database, trái với mục tiêu gọn nhẹ của hệ thống |

---
 
## 8. Ownership Plan
 
| Member | Will own (modules / documents) |
|--------|--------------------------------|
|Đặng Tuấn Kiệt |- Server: tách message và mã hoá/giải mã JSON, nhận kết nối, luồng phục vụ mỗi client, giới hạn số client tối đa, quản lý phiên và chiến lược khoá, điều phối lệnh, xử lý dữ liệu lỗi, gửi tin nhắn phòng và nhắn riêng. Docker.<br>- Docs: docs/protocol-design.md, phần mô hình đồng thời và khoá trong docs/architecture.md |
|Hà Anh Khôi |- Server: quản lý phòng (xem danh sách, tạo, tham gia, rời phòng), khoá phòng, thông báo vào/rời phòng.<br>- Client CLI: các lệnh, luồng đọc socket, PING nền, phát hiện mất kết nối tới server, hiển thị tin nhiều phòng.<br>- Docs: lệnh phòng và sequence diagram của phòng trong docs/protocol-design.md, dữ liệu dùng chung của phòng trong docs/architecture.md |
|Đỗ Đăng Huy |- Server: heartbeat/timeout, phát hiện ngắt kết nối và dọn phiên, thông báo online/offline, SQLite, đăng ký/đăng nhập, danh sách người online và thành viên phòng.<br>- Kiểm thử: load test nhiều client, kill -9, client im lặng, dữ liệu rác.<br>- Docs: docs/testing-guide.md, phần triển khai trong docs/architecture.md |
 
---
 
## 9. Risks
 
| Risk | Mitigation |
|------|------------|
|Kiến thức lập trình mạng còn hạn chế, khó khăn trong trả lời các câu hỏi vấn đáp |Chọn các chức năng quan trọng, liên quan đến lĩnh vực môn học; dùng AI để hỗ trợ giải thích và cung cấp kiến thức cần thiết |
|Thời gian ngắn (khoảng 1 tháng), phạm vi hệ thống hoàn chỉnh lớn |Giới hạn phạm vi hệ thống vừa phải, dùng AI hỗ trợ công việc |
|Tranh chấp (race condition)/khoá chết (deadlock) | Hạn chế số khóa; nếu cần hai khóa thì luôn lấy theo một thứ tự cố định; không giữ khóa dữ liệu chung khi gửi qua socket|
|Mật khẩu và tin nhắn đi qua mạng không được mã hoá |Chỉ dùng trong mạng nội bộ, không đưa ra Internet; mật khẩu lưu trong database dạng đã băm |
|Phụ thuộc giữa các thành viên |Chốt protocol và danh sách hàm sớm; mỗi người dùng bản tạm trong lúc chờ phần thật |

---
 
## 10. Instructor Feedback
 
*(Filled in after M1 review.)*