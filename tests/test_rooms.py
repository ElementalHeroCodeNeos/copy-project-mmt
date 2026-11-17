"""Unit test cho server/src/rooms.py (Khôi, bước 15).

    python -m unittest tests.test_rooms -v
"""

import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server" / "src"))

import rooms  # noqa: E402
import storage  # noqa: E402
from dispatch import CommandError  # noqa: E402


class RoomsTest(unittest.TestCase):
    def setUp(self):
        storage.init_db(":memory:")
        for n in ("khoi", "huy", "kiet"):
            storage.create_user(n, "h", "s")

    def assertCode(self, code, fn, *args):
        with self.assertRaises(CommandError) as ctx:
            fn(*args)
        self.assertEqual(ctx.exception.code, code)

    def test_name_rule(self):
        for ok in ("lab", "nhom-14", "a_b", "x" * 20):
            rooms.check_name(ok)
        for bad in ("ab", "x" * 21, "Lab", "phòng", "lab 1", ""):
            self.assertCode(400, rooms.check_name, bad)

    def test_create_and_duplicate(self):
        rooms.create("lab", "khoi")
        self.assertEqual(rooms.members_of("lab"), ["khoi"])
        self.assertCode(409, rooms.create, "lab", "huy")

    def test_join(self):
        rooms.create("lab", "khoi")
        self.assertEqual(rooms.join("lab", "huy"), ["khoi", "huy"])
        self.assertCode(409, rooms.join, "lab", "huy")
        self.assertCode(404, rooms.join, "khong_co", "huy")

    def test_leave_and_auto_delete(self):
        rooms.create("lab", "khoi")
        rooms.join("lab", "huy")
        self.assertEqual(rooms.leave("lab", "khoi"), (False, ["huy"]))
        self.assertCode(403, rooms.leave, "lab", "kiet")
        self.assertEqual(rooms.leave("lab", "huy"), (True, []))
        self.assertFalse(rooms.room_exists("lab"))
        self.assertCode(404, rooms.leave, "lab", "huy")

    def test_interface_for_others(self):
        rooms.create("lab", "khoi")
        rooms.create("web", "khoi")
        self.assertTrue(rooms.is_member("lab", "khoi"))
        self.assertFalse(rooms.is_member("lab", "huy"))
        self.assertEqual(rooms.rooms_of("khoi"), ["lab", "web"])

    def test_lock_works_for_missing_room_and_is_released(self):
        with rooms.lock("khong_ton_tai"):
            self.assertFalse(rooms.room_exists("khong_ton_tai"))
        self.assertFalse(rooms.lock("lab").locked())
        with self.assertRaises(CommandError):
            rooms.join("khong_co", "huy")
        self.assertFalse(rooms.lock("lab").locked())  # lỗi trong khoá vẫn nhả khoá

    def test_join_races_with_last_leave(self):
        """Người cuối rời (phòng bị xoá) cùng lúc người khác vào: không bao giờ có thành viên
        của một phòng không tồn tại. Lặp nhiều lần cho hai luồng có cơ hội chen nhau."""
        for i in range(200):
            room = f"r{i:03d}"
            rooms.create(room, "khoi")
            start = threading.Barrier(2)
            result = {}

            def leaver():
                start.wait()
                result["leave"] = rooms.leave(room, "khoi")

            def joiner():
                start.wait()
                try:
                    rooms.join(room, "huy")
                    result["join"] = 200
                except CommandError as exc:
                    result["join"] = exc.code

            threads = [threading.Thread(target=leaver), threading.Thread(target=joiner)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            if result["join"] == 200 and result["leave"] == (False, ["huy"]):
                # huy vào trước: phòng còn huy
                self.assertEqual(rooms.members_of(room), ["huy"])
            else:
                # khoi rời trước: phòng bị xoá, huy phải nhận 404, không được "vào" phòng đã xoá
                self.assertEqual((result["leave"], result["join"]), ((True, []), 404))
                self.assertFalse(rooms.room_exists(room))
                self.assertFalse(rooms.is_member(room, "huy"))


if __name__ == "__main__":
    unittest.main()
