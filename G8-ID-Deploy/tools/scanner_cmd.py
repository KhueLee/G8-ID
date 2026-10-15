"""Gửi lệnh cấu hình (menu command) xuống đầu đọc mã vạch Honeywell qua cổng COM (scanner_cmd.bat).

Mỗi lệnh có dạng 16 4D 0D + <lệnh> + kết thúc: "." = lưu vĩnh viễn vào đầu đọc, "!" = chỉ tạm thời,
"?" = hỏi giá trị hiện tại. Đây là 2 lệnh bản cũ để lại (resource\\Cai thoi gian quet pda.txt):
  TRGSTO300000.  đặt thời gian tự tắt quét = 300000 ms, để phần mềm (16 55 0D) quyết định lúc dừng
  TRGSTO?.       đọc lại để kiểm tra
Lệnh "." ghi vào bộ nhớ đầu đọc nên chỉ cần chạy một lần cho mỗi máy.

Phải đóng phần mềm G8 ID trước (cổng COM chỉ một chương trình mở được). Cổng / baudrate lấy từ
config.json -> devices.barcode.

  python tools\\scanner_cmd.py                     -> gửi TRGSTO300000. rồi TRGSTO?.
  python tools\\scanner_cmd.py "TRGSTO?." ...      -> gửi các lệnh tự chọn
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PREFIX = b"\x16M\r"
DEFAULT = ["TRGSTO300000.", "TRGSTO?."]


def main(commands):
    import serial
    from app import config
    cfg = config.load()["devices"]["barcode"]
    print("Đầu đọc: %s @%s %s%s%s" % (cfg["port"], cfg["baudrate"], cfg["bytesize"],
                                      cfg["parity"], cfg["stopbits"]))
    try:
        ser = serial.Serial(cfg["port"], int(cfg["baudrate"]), bytesize=int(cfg["bytesize"]),
                            parity=cfg["parity"], stopbits=float(cfg["stopbits"]), timeout=0.2)
    except Exception as e:
        print("[LỖI] Không mở được %s: %s" % (cfg["port"], e))
        print("      Đóng phần mềm G8 ID (và công cụ mô phỏng) rồi chạy lại.")
        return 1
    bad = 0
    with ser:
        for cmd in commands:
            data = PREFIX + cmd.encode("ascii")
            ser.reset_input_buffer()
            ser.write(data)
            reply, deadline = b"", time.time() + 2.0
            while time.time() < deadline:
                chunk = ser.read(64)
                if chunk:
                    reply += chunk
                elif reply:
                    break
            # Đầu đọc trả lại lệnh, thêm 06 (ACK) nếu nhận, 15 (NAK) nếu sai, 05 (ENQ) nếu không hỗ trợ.
            if b"\x06" in reply:
                state = "OK"
            elif reply:
                state, bad = "TỪ CHỐI", bad + 1
            else:
                state, bad = "KHÔNG TRẢ LỜI", bad + 1
            print("[%s] gửi %-16s (%s) -> %r" % (state, cmd, data.hex(" ").upper(), reply))
    if bad:
        print("Có lệnh không thành công: kiểm tra cổng/baudrate trong config.json và loại đầu đọc.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or DEFAULT))
