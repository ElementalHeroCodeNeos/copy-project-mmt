# Testing Guide & Test Evidence

> Part 1 shows **how** to test a networked system. Part 2 is **your evidence** — graded under B1/B2.
> All results must come from actually running your system (see `INSTRUCTION.md` §7).

---

## Part 1 — How to Test

### 1.1 Manual testing with raw tools

Talk to the server directly before the client exists:

```bash
nc localhost 5000            # TCP
python scripts/nc.py         # nhóm dùng script này (Windows không có sẵn nc)
# mỗi dòng là một message JSON, kết thúc bằng Enter (\n):
{"command": "PING", "requestId": "1", "payload": {}}
{"command": "REGISTER", "payload": {"username": "huy", "password": "matkhau123"}}
{"command": "LOGIN", "payload": {"username": "huy", "password": "matkhau123"}}
{"command": "LIST_ONLINE", "payload": {}}
{"command": "QUIT", "payload": {}}
```

`telnet localhost 5000` also works for TCP text protocols.

### 1.1b Test tự động (unittest)

```bash
python -m unittest discover tests -v          # toàn bộ (~1 phút)
python -m unittest tests.test_robustness -v   # nhiều client, kill, im lặng, rác
```

Mỗi test tích hợp chạy một server thật (tiến trình con) trên một cổng trống, với database rỗng
trong thư mục tạm, nên không đụng dữ liệu thật và chạy cùng lúc với server Docker được.

| File | Kiểm tra gì |
|------|-------------|
| `tests/test_protocol.py` | Tách message (`FrameBuffer`): bị cắt đôi, dính nhau, quá 64 KB; mã hoá/giải mã JSON |
| `tests/test_dispatch.py` | Điều phối lệnh: lệnh lạ 400, chưa đăng nhập 401, thiếu/sai `payload` 400, lỗi handler 500 |
| `tests/test_session.py` | Khoá gửi, gửi lỗi thì đánh dấu phiên chết, danh sách online |
| `tests/test_auth.py` | Băm mật khẩu (salt, NFC, so sánh an toàn) |
| `tests/test_storage.py` | SQLite: trùng khoá, khoá ngoại, giao dịch, 20 luồng đăng ký trùng tên |
| `tests/test_presence.py` | Dọn phiên, báo online/offline đúng người, `LIST_ONLINE`, `LIST_MEMBERS` |
| `tests/test_messages.py` | `ROOM_MSG`, `PRIVATE_MSG` (unit) |
| `tests/test_server.py` | Server thật: dữ liệu rác, 413, 503, timeout, client gửi nhỏ giọt, `REGISTER`/`LOGIN`/`QUIT`, online/offline, tin nhắn |
| `tests/test_robustness.py` | Server thật: 30 client cùng lúc, tiến trình client bị kill, client đã đăng nhập im lặng, 200 KB byte ngẫu nhiên |

### 1.2 Concurrency / load test

Prove the server serves many clients at once. Example script (adapt the message to your protocol and framing):

Nhóm dùng `tests/load_test.py` (dựa trên mẫu của thầy, sửa cho protocol của nhóm): mỗi client
`REGISTER` → `LOGIN` → `PING`, giữ kết nối 2 s để chồng lên các client khác, rồi `QUIT`. Client
đọc đủ một dòng (`FrameBuffer`), không chỉ một lần `recv()`.

```bash
docker compose up --build -d server
python tests/load_test.py                 # 50 client
N_CLIENTS=110 python tests/load_test.py   # vượt MAX_CLIENTS=100: 10 client phải nhận 503
```

Lưu ý Windows: chạy `docker compose` trong PowerShell (trong Git Bash bị lỗi quyền khi build và
không tìm thấy `docker-credential-desktop`). Trong PowerShell đặt biến bằng `$env:N_CLIENTS="110"`.

If the server were iterative, total time would grow with N; with real concurrency all clients are served in parallel.

### 1.3 Abnormal disconnects

| Scenario | How | Expected |
|----------|-----|----------|
| Client killed | `Ctrl+C`, `kill -9 <pid>`, or `docker kill <container>` | Server detects EOF/reset, cleans up the session, keeps serving others |
| Client goes silent | connect and send nothing | Server times out the connection (if your protocol defines it) |
| Garbage input | `head -c 100000 /dev/urandom \| nc localhost 5000` | Server rejects / closes that connection, does not crash or run out of memory |
| Server stops | `docker compose stop server` | Client shows a clear error; optionally retries with backoff |

### 1.4 Simulating a bad network

Inside a Linux container that has `iproute2` and the `NET_ADMIN` capability
(`cap_add: [NET_ADMIN]` in `docker-compose.yml`):

```bash
tc qdisc add dev eth0 root netem delay 100ms 20ms   # latency + jitter
tc qdisc change dev eth0 root netem loss 5%          # packet loss
tc qdisc del dev eth0 root                           # restore
```

---

## Part 2 — Our Test Evidence

Chạy ngày 2026-11-18 trên máy Windows 11 của nhóm (Python 3.13 trên host; server trong Docker:
Python 3.12-slim). Kết quả chép nguyên từ output.

| # | Test | Method | Result (paste output / screenshot link) | Pass? |
|:-:|------|--------|------------------------------------------|:-----:|
| 1 | N concurrent clients | `tests/load_test.py` với server trong Docker, N = 50, 90, 110 | N=50: `50/50 thành công trong 3.82 s` (tới PING_RESPONSE: nhỏ nhất 0.97 s, trung vị 1.51 s, lớn nhất 1.81 s). N=90: `90/90 thành công trong 6.42 s`. N=110: `100/110 thành công trong 7.01 s`, 10 client còn lại nhận `{"command": "ERROR", "code": 503, "message": "Server đã đủ 100 client, thử lại sau"}`; log server: `WARNING [MainThread] server: Từ chối 172.18.0.1:44228: đã đủ 100 client` | ✅ |
| 1b | Nhiều client nhắn cùng lúc | `test_robustness.ManyClientsTest`: 30 luồng cùng đăng ký, đăng nhập, rồi cùng gửi `ROOM_MSG` | `30 client: đăng ký + đăng nhập + gửi xong sau 2.47 s, mỗi client nhận đủ 30 tin sau 2.48 s`. 60 lần băm mật khẩu (~0,44 s mỗi lần, ~26 s nếu chạy lần lượt) xong trong 2,47 s: các luồng chạy song song. Mọi dòng nhận được đều là JSON hợp lệ (không có hai luồng ghi xen vào một socket) | ✅ |
| 2 | Client killed mid-session | `test_robustness.FailureTest.test_killed_client_process_is_cleaned_up`: client chạy ở tiến trình riêng, đăng nhập rồi bị `kill()` (SIGKILL trên Linux, TerminateProcess trên Windows) | Bạn cùng phòng nhận `{"command": "NOTIFY_OFFLINE", "data": {"username": "huy"}}`; đăng nhập lại cùng tài khoản được ngay; server vẫn chạy. Thêm `test_server.test_abrupt_disconnect_notifies_offline` (đóng bằng RST) | ✅ |
| 2b | Client đã đăng nhập im lặng | `FailureTest.test_silent_logged_in_client_times_out_and_goes_offline` (`READ_TIMEOUT_SEC=2`) | Server đóng kết nối im lặng; bạn cùng phòng (vẫn PING đều) nhận `NOTIFY_OFFLINE` và không bị ngắt nhầm. Thêm `test_server.test_trickling_client_is_closed_after_timeout` (gửi nhỏ giọt từng byte vẫn bị đóng) | ✅ |
| 3 | Malformed / oversized message | `FailureTest.test_random_garbage_does_not_hurt_others` (200 KB `os.urandom`); `test_server.test_garbage_gets_400_and_connection_stays`, `test_too_large_gets_413_then_closed` | Byte ngẫu nhiên: server đóng kết nối đó, client khác vẫn `LIST_ONLINE` được, server không chết. JSON hỏng → `ERROR 400 "JSON không hợp lệ"`, giữ kết nối; quá giới hạn → `ERROR 413` rồi đóng | ✅ |
| 4 | Feature: Đăng ký, đăng nhập | `test_server` (9 test `test_register_*`, `test_login_*`); `test_storage.test_concurrent_register_same_username_only_one_wins` | REGISTER: 201/400/409; sai mật khẩu và tài khoản không tồn tại cùng trả 401 với một câu; 409 khi kết nối đã đăng nhập hoặc tài khoản đang online nơi khác; 20 luồng đăng ký cùng tên → đúng 1 thành công | ✅ |
| 5 | Feature: Online/offline, QUIT | `test_presence` (10 test); `test_server.test_login_notifies_roommates`, `test_quit_*`, `test_list_online_and_members` | Chỉ bạn cùng phòng đang online nhận `NOTIFY_ONLINE`/`NOTIFY_OFFLINE`; `QUIT` trả 200 rồi đóng, message gửi sau `QUIT` bị bỏ qua | ✅ |
| 6 | Toàn bộ test tự động | `python -m unittest discover tests` | `Ran 140 tests in 61.794s` / `OK (skipped=1)` | ✅ |

**Lỗi phát hiện nhờ test và cách sửa**

- Sau khi có băm mật khẩu thật (~0,44 s mỗi lần), 3 test nhiều người dùng bị ngắt kết nối. Test đặt
  `READ_TIMEOUT_SEC=2`, người đăng nhập đầu tiên phải chờ người sau đăng ký và đăng nhập quá 2 s,
  nên server ngắt đúng như thiết kế. Sửa cách test: đăng ký hết rồi mới đăng nhập (`logins()`).
- Một test QUIT ban đầu dùng `wait_closed()`. Hàm này bỏ qua dữ liệu nhận được, nên test vẫn qua
  kể cả khi server trả thêm message sau QUIT. Sửa: đọc message tiếp theo và chờ server đóng.

*(Phòng và client CLI: Khôi bổ sung khi xong phần của mình.)*
