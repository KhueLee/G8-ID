"""In tên chương trình (màu xanh lá) ở dòng đầu cửa sổ CMD. Gọi từ chay_dinh_danh.bat / chay_mo_phong.bat."""
import os
import sys

NAMES = {
    "app": "PHẦN MỀM ĐỊNH DANH SẢN PHẨM – G8 ID",
    "sim": "PHẦN MỀM MÔ PHỎNG ĐỊNH DANH – G8 ID (chỉ chạy thử)",
}

if __name__ == "__main__":
    os.system("")                         # bật mã màu ANSI cho cửa sổ CMD
    print("\x1b[1;92m=== %s ===\x1b[0m" % NAMES[sys.argv[1] if len(sys.argv) > 1 else "app"])
