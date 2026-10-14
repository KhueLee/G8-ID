"""Khoá liên động AUTO <-> công cụ mô phỏng.

Công cụ mô phỏng chỉ được chạy ở MANUAL; muốn về AUTO thì run_simulator.bat phải đóng hẳn.
Ba dấu hiệu độc lập, chỉ cần một cái còn là coi như CHƯA đóng:
  1. Cửa sổ .bat còn mở: cmd giữ handle ghi vào data\\simulator_bat.lock suốt thời gian
     chạy, nên không xoá được file -> .bat còn sống (kể cả khi python mô phỏng đã chết
     nhưng cửa sổ chưa tắt). Tắt cửa sổ bằng dấu X thì Windows tự nhả handle.
  2. Cổng của công cụ mô phỏng còn nghe.
  3. Công cụ mô phỏng vừa gửi nhịp tim (< 3 s).
"""
import os
import socket
import time

from . import config


def bat_window_open():
    path = config.SIM_BAT_LOCK
    if not os.path.exists(path):
        return False
    try:
        os.remove(path)        # xoá được => không ai giữ file => .bat đã đóng
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def port_open(port, host="127.0.0.1"):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        return s.connect_ex((host, int(port))) == 0
    finally:
        s.close()


def simulator_running(engine):
    """Trả về lý do (chuỗi) nếu công cụ mô phỏng chưa đóng, '' nếu đã đóng hẳn."""
    if bat_window_open():
        return "cửa sổ run_simulator.bat còn mở"
    if time.time() - engine.sim_heartbeat < 3:
        return "công cụ mô phỏng còn chạy"
    if port_open(engine.cfg["simulator"]["port"]):
        return "cổng %s còn mở" % engine.cfg["simulator"]["port"]
    return ""
