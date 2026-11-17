"""Unit test cho server/src/storage.py (bước 4).

    python -m unittest tests.test_storage -v
"""

import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server" / "src"))

import storage  # noqa: E402


class StorageTest(unittest.TestCase):
    def setUp(self):
        storage.init_db(":memory:")  # mỗi test một database rỗng trong bộ nhớ

    def add_users(self, *names):
        for n in names:
            self.assertTrue(storage.create_user(n, "h", "s"))

    # --- tài khoản -----------------------------------------------------------

    def test_create_and_get_user(self):
        self.assertTrue(storage.create_user("huy", "abcd", "0011"))
        self.assertEqual(storage.get_user("huy"),
                         {"username": "huy", "pw_hash": "abcd", "salt": "0011"})

    def test_duplicate_user_returns_false_and_keeps_old(self):
        self.assertTrue(storage.create_user("huy", "h1", "s1"))
        self.assertFalse(storage.create_user("huy", "h2", "s2"))
        self.assertEqual(storage.get_user("huy")["pw_hash"], "h1")

    def test_unknown_user_is_none(self):
        self.assertIsNone(storage.get_user("khong_co"))

    def test_concurrent_register_same_username_only_one_wins(self):
        """20 luồng cùng đăng ký một username: đúng một lần thành công (thread-safe)."""
        results = []
        start = threading.Barrier(20)

        def register(i):
            start.wait()  # cho cả 20 luồng xuất phát cùng lúc
            results.append(storage.create_user("trung", f"h{i}", f"s{i}"))

        threads = [threading.Thread(target=register, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 19)

    # --- phòng ---------------------------------------------------------------

    def test_create_room_adds_creator(self):
        self.add_users("huy")
        self.assertTrue(storage.create_room("lab", "huy"))
        self.assertTrue(storage.room_exists("lab"))
        self.assertEqual(storage.list_members("lab"), ["huy"])

    def test_duplicate_room_returns_false_and_changes_nothing(self):
        self.add_users("huy", "khoi")
        storage.create_room("lab", "huy")
        self.assertFalse(storage.create_room("lab", "khoi"))
        self.assertEqual(storage.list_members("lab"), ["huy"])

    def test_create_room_with_unknown_creator_creates_nothing(self):
        """Khoá ngoại báo lỗi ở câu INSERT thứ hai; giao dịch rollback cả câu thứ nhất."""
        with self.assertRaises(sqlite3.IntegrityError):
            storage.create_room("lab", "khong_co")
        self.assertFalse(storage.room_exists("lab"))

    def test_add_member_duplicate_returns_false(self):
        self.add_users("huy", "khoi")
        storage.create_room("lab", "huy")
        self.assertTrue(storage.add_member("lab", "khoi"))
        self.assertFalse(storage.add_member("lab", "khoi"))

    def test_add_member_to_missing_room_raises(self):
        """Vi phạm khoá ngoại không bị nhầm thành "đã là thành viên" (chốt bước 4, 3A)."""
        self.add_users("huy")
        with self.assertRaises(sqlite3.IntegrityError):
            storage.add_member("khong_co", "huy")

    def test_leave_room_keeps_room_while_members_remain(self):
        self.add_users("huy", "khoi")
        storage.create_room("lab", "huy")
        storage.add_member("lab", "khoi")
        self.assertEqual(storage.leave_room("lab", "huy"), (True, False))
        self.assertEqual(storage.list_members("lab"), ["khoi"])

    def test_last_member_leaving_deletes_room(self):
        self.add_users("huy")
        storage.create_room("lab", "huy")
        self.assertEqual(storage.leave_room("lab", "huy"), (True, True))
        self.assertFalse(storage.room_exists("lab"))
        self.assertEqual(storage.rooms_of_user("huy"), [])

    def test_leave_room_not_member(self):
        self.add_users("huy", "khoi")
        storage.create_room("lab", "huy")
        self.assertEqual(storage.leave_room("lab", "khoi"), (False, False))
        self.assertEqual(storage.leave_room("khong_co", "huy"), (False, False))

    def test_is_member(self):
        self.add_users("huy", "khoi")
        storage.create_room("lab", "huy")
        self.assertTrue(storage.is_member("lab", "huy"))
        self.assertFalse(storage.is_member("lab", "khoi"))
        self.assertFalse(storage.is_member("khong_co", "huy"))

    def test_list_members_in_join_order(self):
        self.add_users("zed", "anh", "minh")
        storage.create_room("lab", "zed")
        storage.add_member("lab", "minh")
        storage.add_member("lab", "anh")
        self.assertEqual(storage.list_members("lab"), ["zed", "minh", "anh"])
        self.assertEqual(storage.list_members("khong_co"), [])

    def test_list_rooms_with_member_count(self):
        self.add_users("huy", "khoi")
        storage.create_room("web", "huy")
        storage.create_room("lab", "huy")
        storage.add_member("lab", "khoi")
        self.assertEqual(storage.list_rooms(),
                         [{"name": "lab", "members": 2}, {"name": "web", "members": 1}])

    def test_rooms_of_user(self):
        self.add_users("huy", "khoi")
        storage.create_room("web", "huy")
        storage.create_room("lab", "huy")
        storage.create_room("game", "khoi")
        self.assertEqual(storage.rooms_of_user("huy"), ["lab", "web"])
        self.assertEqual(storage.rooms_of_user("nobody"), [])


class FileDatabaseTest(unittest.TestCase):
    """Database trong file thật: tự tạo thư mục, mở lại vẫn còn dữ liệu."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="chat-test-")

    def tearDown(self):
        storage.init_db(":memory:")  # đóng file trước khi xoá (Windows không xoá file đang mở)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_creates_directory_and_persists(self):
        path = os.path.join(self.tmp, "chua_co", "chat.db")
        storage.init_db(path)
        self.assertTrue(os.path.exists(path))
        storage.create_user("huy", "h", "s")
        storage.create_room("lab", "huy")

        storage.init_db(path)  # như server khởi động lại
        self.assertIsNotNone(storage.get_user("huy"))
        self.assertEqual(storage.list_members("lab"), ["huy"])


if __name__ == "__main__":
    unittest.main()
