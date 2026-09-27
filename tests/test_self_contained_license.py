import sys
import os
import sqlite3
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import license_guard

fd, tmp_db = tempfile.mkstemp(suffix=".db")
os.close(fd)
try:
    conn = sqlite3.connect(tmp_db)
    license_guard.init_license_tables(conn)

    # 1. 签发一张 365 天行星套餐卡密 (ANY)
    code = license_guard.encode_short_code(2, 365, "ANY")
    print("1. 签发的 80-bit 自包含短码:", code)

    # 2. 模拟断网/授权中心不可达状态下的离线兜底激活
    success, msg, status = license_guard.save_license_key(conn, code, auth_url="http://192.0.2.1:9999")
    print("2. 离线兜底激活结果:", success, "| 提示:", msg)
    assert success, "应该离线激活成功"

    # 3. 检查当前授权状态
    curr_status = license_guard.get_current_license_status(conn)
    print("3. 当前授权状态:", curr_status["active"], "| 套餐:", curr_status.get("plan_name"),
          "| 配额: 服/节/户 =", curr_status.get("max_servers"), curr_status.get("max_nodes"), curr_status.get("max_users"),
          "| 剩余天数:", curr_status.get("days_left"))
    assert curr_status["active"] == True
    assert curr_status["plan_name"] == "行星套餐"
    assert curr_status["max_servers"] == -1

    # 4. 模拟防伪校验（篡改卡密字符）
    tampered_code = code[:-1] + ("A" if code[-1] != "A" else "B")
    success_t, msg_t, _ = license_guard.save_license_key(conn, tampered_code, auth_url="http://192.0.2.1:9999")
    print("4. 篡改卡密测试:", success_t, "| 提示:", msg_t)
    assert not success_t, "篡改卡密必须被拒绝"

    # 5. 模拟在线吊销同步
    conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_revoked', '1')")
    conn.commit()
    rev_status = license_guard.get_current_license_status(conn)
    print("5. 吊销测试状态:", rev_status["active"], "| 类型:", rev_status["type"], "| 提示:", rev_status["message"])
    assert rev_status["active"] == False
    assert rev_status["type"] == "revoked"

    print(">>> 全部单元验证通过！<<<")
finally:
    conn.close()
    if os.path.exists(tmp_db):
        try:
            os.remove(tmp_db)
        except Exception:
            pass
