import unittest
import sqlite3
import time
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import license_guard
from license_guard import (
    get_machine_id,
    parse_and_verify_license,
    get_current_license_status,
    save_license_key,
    _pure_python_verify,
    MASTER_PUBLIC_KEY_HEX
)
from cryptography.hazmat.primitives.asymmetric import ed25519

PRIV_HEX = "875cf2bcc0c92bb602eb6c150693ed1e308321f803b7cbf3674ec028ebea0ff3"
priv_bytes = bytes.fromhex(PRIV_HEX)
private_key = ed25519.Ed25519PrivateKey.from_private_bytes(priv_bytes)

def generate_test_license(payload: dict) -> str:
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    sig = private_key.sign(payload_bytes)
    p_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
    s_b64 = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    return f"PPLIC-{p_b64}.{s_b64}"

class TestLicenseGuard(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_machine_id_format(self):
        mid = get_machine_id()
        self.assertTrue(mid.startswith("PP-"))
        self.assertEqual(len(mid), 17)
        parts = mid.split("-")
        self.assertEqual(len(parts), 4)

    def test_valid_license(self):
        mid = get_machine_id()
        payload = {
            "id": "LIC-001",
            "type": "pro",
            "customer": "张三",
            "machine_id": mid,
            "expire_at": int(time.time()) + 86400 * 365,
            "max_nodes": 50
        }
        lic_key = generate_test_license(payload)
        verified, err = parse_and_verify_license(lic_key)
        self.assertIsNotNone(verified)
        self.assertEqual(err, "")
        self.assertEqual(verified["customer"], "张三")

    def test_pure_python_verifier_fallback(self):
        """测试在完全没有 cryptography 库时的纯 Python RFC 8032 算法"""
        mid = get_machine_id()
        payload = {"id": "LIC-FALLBACK", "type": "pro", "machine_id": mid, "expire_at": int(time.time()) + 86400}
        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        sig = private_key.sign(payload_bytes)
        pub_bytes = bytes.fromhex(MASTER_PUBLIC_KEY_HEX)
        self.assertTrue(_pure_python_verify(pub_bytes, sig, payload_bytes))

        # Tampered byte fails
        bad_sig = bytearray(sig)
        bad_sig[5] ^= 0xFF
        self.assertFalse(_pure_python_verify(pub_bytes, bytes(bad_sig), payload_bytes))

    def test_universal_any_machine(self):
        payload = {
            "id": "LIC-002",
            "type": "enterprise",
            "customer": "全网通",
            "machine_id": "ANY",
            "expire_at": int(time.time()) + 86400 * 30,
            "max_nodes": 0
        }
        lic_key = generate_test_license(payload)
        verified, err = parse_and_verify_license(lic_key)
        self.assertIsNotNone(verified)
        self.assertEqual(err, "")

    def test_tampered_license(self):
        mid = get_machine_id()
        payload = {
            "id": "LIC-003",
            "type": "pro",
            "customer": "正常客户",
            "machine_id": mid,
            "expire_at": int(time.time()) + 86400
        }
        lic_key = generate_test_license(payload)
        tampered = lic_key[:-2] + "XX"
        verified, err = parse_and_verify_license(tampered)
        self.assertIsNone(verified)
        self.assertIn("校验失败", err)

    def test_mismatched_machine(self):
        payload = {
            "id": "LIC-004",
            "type": "pro",
            "customer": "李四",
            "machine_id": "PP-9999-8888-7777",
            "expire_at": int(time.time()) + 86400
        }
        lic_key = generate_test_license(payload)
        verified, err = parse_and_verify_license(lic_key)
        self.assertIsNone(verified)
        self.assertIn("机器码不匹配", err)

    def test_expired_license(self):
        mid = get_machine_id()
        payload = {
            "id": "LIC-005",
            "type": "pro",
            "customer": "过期客户",
            "machine_id": mid,
            "expire_at": int(time.time()) - 3600
        }
        lic_key = generate_test_license(payload)
        verified, err = parse_and_verify_license(lic_key)
        self.assertIsNone(verified)
        self.assertIn("已过期", err)

    def test_db_activation_flow(self):
        mid = get_machine_id()
        # 1. Initially inactive
        status = get_current_license_status(self.conn)
        self.assertFalse(status["active"])
        self.assertEqual(status["type"], "free")

        # 2. Activate
        payload = {
            "id": "LIC-006",
            "type": "pro",
            "customer": "VIP客户",
            "machine_id": mid,
            "expire_at": int(time.time()) + 86400 * 10,
            "max_nodes": 20
        }
        lic_key = generate_test_license(payload)
        ok, msg, status = save_license_key(self.conn, lic_key)
        self.assertTrue(ok)
        self.assertTrue(status["active"])
        self.assertEqual(status["customer"], "VIP客户")
        self.assertEqual(status["days_left"], 10)

if __name__ == '__main__':
    unittest.main()
