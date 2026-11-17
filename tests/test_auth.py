"""Unit test cho server/src/auth.py (bước 3).

    python -m unittest tests.test_auth -v
"""

import sys
import time
import unicodedata
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server" / "src"))

import auth  # noqa: E402


class HashPasswordTest(unittest.TestCase):
    def test_correct_password_verifies(self):
        h, s = auth.hash_password("matkhau123")
        self.assertTrue(auth.verify_password("matkhau123", h, s))

    def test_wrong_password_fails(self):
        h, s = auth.hash_password("matkhau123")
        self.assertFalse(auth.verify_password("matkhau124", h, s))
        self.assertFalse(auth.verify_password("", h, s))

    def test_same_password_gets_different_salt_and_hash(self):
        h1, s1 = auth.hash_password("matkhau123")
        h2, s2 = auth.hash_password("matkhau123")
        self.assertNotEqual(s1, s2)
        self.assertNotEqual(h1, h2)

    def test_given_salt_reproduces_hash(self):
        h, s = auth.hash_password("matkhau123")
        self.assertEqual(auth.hash_password("matkhau123", s), (h, s))

    def test_output_is_hex_of_expected_length(self):
        h, s = auth.hash_password("matkhau123")
        self.assertEqual(len(s), auth.SALT_BYTES * 2)
        self.assertEqual(len(h), 64)  # sha256 = 32 byte = 64 ký tự hex
        bytes.fromhex(h)
        bytes.fromhex(s)

    def test_vietnamese_nfc_and_nfd_match(self):
        nfc = unicodedata.normalize("NFC", "mậtkhẩu")
        nfd = unicodedata.normalize("NFD", "mậtkhẩu")
        self.assertNotEqual(nfc, nfd)  # hai chuỗi khác nhau thật
        h, s = auth.hash_password(nfc)
        self.assertTrue(auth.verify_password(nfd, h, s))

    def test_corrupt_hex_raises(self):
        with self.assertRaises(ValueError):
            auth.verify_password("matkhau123", "khong-phai-hex", "00" * 16)

    def test_print_hash_time(self):
        """Không assert: chỉ in thời gian một lần băm để ghi vào notes."""
        start = time.perf_counter()
        auth.hash_password("matkhau123")
        elapsed = time.perf_counter() - start
        print(f"\n  [đo] một lần băm ({auth.ITERATIONS} vòng): {elapsed:.3f} s", file=sys.stderr)


if __name__ == "__main__":
    unittest.main()
