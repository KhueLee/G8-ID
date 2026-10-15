# G8-ID – Trạm định danh thùng / pallet

Phần mềm cho máy trạm công nhân: cân thùng, in tem (Godex), đọc mã vạch, gom thùng thành pallet
và gửi kết quả định danh về WMS. Bản này viết lại phần mềm WinForms cũ `VTP_Induction.exe`
bằng **Python + MongoDB**, giao diện chạy trên **Google Chrome**, giữ nguyên quy trình thao tác
và driver thiết bị của bản cũ, đồng thời xử lý các lỗi treo/crash của bản cũ.

## Cấu trúc repo

| Thư mục / file | Nội dung |
|---|---|
| [`G8-ID-Deploy/`](G8-ID-Deploy/) | **Sản phẩm triển khai** – chép nguyên thư mục này lên máy trạm (khoảng 12 máy). Hướng dẫn đầy đủ: [`G8-ID-Deploy/README.md`](G8-ID-Deploy/README.md) |
| `resource/` | Tài liệu và bộ cài của phần mềm cũ (bản `Debug` của `VTP_Induction.exe`, tài liệu hệ thống `G8ID-Tai-lieu-he-thong`, script SQL `g8.sql`, driver CH340…) – chỉ để tham khảo |
| `Request.txt` | Yêu cầu gốc cho bản viết lại |

## Chạy nhanh (trên máy trạm)

1. Cài Python 3.10+ 64-bit (khuyên dùng 3.13 để cài thư viện offline từ `wheels\`).
2. Chạy `G8-ID-Deploy\install.bat`, sửa `config.json` (mã trạm, cổng COM, URL server).
3. Chạy `check_env.bat` để kiểm tra máy, sau đó `run_app.bat`.

| Cổng | Dùng cho |
|---|---|
| `8600` | Giao diện web cho công nhân (`http://127.0.0.1:8600`) |
| `8500` | Nhận lệnh từ WMS (`/ids/orderTask/`, `/ids/cancelTask/`, `/ids/confirm_product/`) |
| `8700` | Công cụ mô phỏng (`run_simulator.bat`, chỉ chạy khi phần mềm ở chế độ MANUAL) |

MongoDB 4.4 đi kèm trong `G8-ID-Deploy\mongodb\bin`, phần mềm tự bật, chỉ nghe ở `127.0.0.1`.

## Kiểm tra

```bat
G8-ID-Deploy\run_tests.bat
```

Bộ kiểm tra tự động dùng thiết bị mô phỏng, thư mục tạm và cổng riêng nên chạy được ngay trên
máy trạm mà không ảnh hưởng dữ liệu thật.

## Log

Toàn bộ log nằm ở `G8-ID-Deploy\logs\` (`app-*`, `http-*`, `device-*`, `crash.log`…), mỗi ngày
một file. Khi cần hỗ trợ, gửi kèm các file log của ngày xảy ra lỗi.

Chi tiết về chế độ AUTO/MANUAL, cách xử lý lỗi CH340, PLC qua MX Component 5, chống tràn MongoDB
và các điểm còn cần xác nhận: xem [`G8-ID-Deploy/README.md`](G8-ID-Deploy/README.md).
