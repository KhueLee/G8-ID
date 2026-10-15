# G8 ID – Trạm định danh thùng / pallet (Python + MongoDB, v2.1.0)

Thay cho phần mềm WinForms `VTP_Induction.exe`: giữ nguyên quy trình, thông báo, bố cục màn hình
và driver thiết bị của bản cũ; giao diện chạy trên Google Chrome. Phần mềm nằm trong thư mục
`G8-ID-Deploy`.

## 1. Cài đặt lần đầu

Làm trên từng máy trạm. Máy cần vào được github.com (lần đầu và mỗi lần cập nhật).

1. **Cài Git** – mở PowerShell:
   ```powershell
   winget install --id Git.Git -e
   ```
   (Không có `winget` thì tải *64-bit Git for Windows Setup* ở https://git-scm.com/download/win,
   cài mặc định.) Đóng PowerShell, mở lại, kiểm tra `git --version`.
2. **Cài Python 3.13 64-bit** từ https://www.python.org/downloads/windows/ – ở màn hình đầu
   tick **Add python.exe to PATH**. Kiểm tra trong PowerShell mới: `python --version`.
   (Thư viện offline trong `wheels\` dành cho 3.13 64-bit; bản Python khác thì `install.bat`
   tải qua internet.)
3. **Lấy code về**:
   ```powershell
   git clone https://github.com/KhueLee/G8-ID.git C:\G8-ID
   ```
   Phần mềm nằm ở `C:\G8-ID\G8-ID-Deploy` (gọi tắt là *thư mục phần mềm*).
4. Chạy `install.bat` trong thư mục phần mềm.
5. Sửa `config.json`: `station_id`, cổng COM cân / đầu đọc, `pallet_done_url`
   (cổng COM, máy in, PLC cũng sửa được ở thẻ **Cài đặt**).
6. Chuột phải → *Run as administrator*:
   - `tools\open_firewall.bat` – mở cổng 8500 nhận lệnh từ WMS.
   - `tools\fix_serial_mouse.bat` – chống Windows nhận nhầm cân là chuột serial (mục 4), rồi
     khởi động lại máy.
7. **PLC / đèn tháp**: cài MX Component 5, tạo Logical Station (mục 4). Hiện các trạm dùng
   Logical Station **0** (`devices.plc.station_number`), để `devices.plc.progid` rỗng.
8. **Đầu đọc**: tắt G8 ID, chạy `tools\scanner_timeout.bat` một lần (mục 4); hai dòng phải `[OK]`.
9. Tắt hẳn `VTP_Induction.exe` cũ (không dùng chung được cổng 8500 và cổng COM).
10. Chạy `check_env.bat`, xử lý các dòng `[LỖI]`.
11. **Chạy**: `run_app.bat` → Chrome mở `http://127.0.0.1:8600`. Để cửa sổ đen mở (thu nhỏ).
    Tự chạy khi đăng nhập Windows: đặt shortcut của `run_app.bat` vào `shell:startup`.

MongoDB không cần cài: phần mềm tự bật `mongodb\bin\mongod.exe` (4.4), chỉ nghe ở 127.0.0.1,
dữ liệu ở `data\db`.

### Máy đang chạy bản tải ZIP (thư mục `...\G8-ID-main\`)

Bản ZIP không `git pull` được. Làm bước 1–3 ở trên, rồi **đóng G8 ID** và chép cấu hình + dữ
liệu của trạm sang thư mục mới:
```powershell
$old = "C:\Users\Admin\Desktop\v2\G8-ID-main\G8-ID-Deploy"   # sửa theo thư mục cũ
$new = "C:\G8-ID\G8-ID-Deploy"
Copy-Item "$old\config.json" "$new\config.json" -Force
Copy-Item "$old\data" "$new\data" -Recurse -Force
```
Chạy `install.bat`, mở `run_app.bat` ở thư mục mới, sửa shortcut trong `shell:startup` (nếu có).
Chạy ổn rồi mới xoá thư mục cũ.

## 2. Cập nhật phiên bản mới

1. **Đóng G8 ID** (cửa sổ đen `run_app.bat`) và công cụ mô phỏng.
2. Sao lưu dữ liệu (khuyến nghị):
   ```powershell
   Copy-Item C:\G8-ID\G8-ID-Deploy\data "C:\G8-ID-backup\data-$(Get-Date -Format yyyyMMdd)" -Recurse
   ```
3. Kéo bản mới:
   ```powershell
   cd C:\G8-ID
   git pull
   ```
4. Chạy `install.bat` (cài thư viện mới nếu có; không có gì mới cũng không sao).
5. Mở `run_app.bat`.

`git pull` chỉ tải và thay các file đã đổi. `data\` (MongoDB) và `logs\` không nằm trên git nên
không bị đụng tới. Muốn xem trước: `git fetch` rồi `git diff --stat HEAD origin/main`.

**Nếu `git pull` báo** *Your local changes … would be overwritten* (trạm đã sửa `config.json`):
```powershell
git stash
git pull
git stash pop
```
`git stash pop` báo *CONFLICT*: mở `G8-ID-Deploy\config.json`, phần giữa `=======` và
`>>>>>>> Stashed changes` là giá trị của trạm – giữ giá trị đó, xoá ba dòng đánh dấu
(`<<<<<<<`, `=======`, `>>>>>>>`), lưu, rồi chạy `git reset` và `git stash drop`.
**Không** dùng `git reset --hard` và không xoá `data` – sẽ mất cấu hình / dữ liệu của trạm.

## 3. Vận hành

| File | Việc |
|---|---|
| `run_app.bat` | Chạy phần mềm + mở Chrome. Chết bất thường thì tự chạy lại sau 3 s. |
| `run_simulator.bat` | Công cụ mô phỏng (`http://127.0.0.1:8700`). Chỉ chạy khi phần mềm ở **MANUAL** / **HYBRID**. |
| `check_env.bat` | Kiểm tra máy (Python, thư viện, COM, máy in, MX Component, firewall) → `logs\check_env.txt`. |
| `run_tests.bat` | 20 bài kiểm tra tự động (~2 phút), chạy được ngay trên máy trạm. |
| `install.bat` | Cài thư viện Python. |
| `tools\scanner_timeout.bat` | Gửi lệnh cấu hình xuống đầu đọc (mục 4). |
| `tools\restart_ch340.bat` | Khởi động lại cổng CH340 bị kẹt, không cần gỡ/cài driver. |
| `tools\reinstall_ch340.bat` | Gỡ và cài lại driver CH340 tự động (mục 4). |

- Giao diện nghe ở `0.0.0.0:8600`; mật khẩu thẻ Cài đặt mặc định **1234**.
- **AUTO**: thiết bị thật, DB `g8id`, gửi pallet tới server thật.
  **MANUAL**: thiết bị và server giả của công cụ mô phỏng, DB riêng `g8id_manual`; cổng 8500 chỉ
  nhận lệnh từ chính máy (lệnh WMS bị trả 503). Đổi ở thẻ Cài đặt khi đang STOP. Không chuyển /
  chạy AUTO được khi cửa sổ `run_simulator.bat` còn mở.
  **HYBRID**: chạy thử thực tế tại bàn định danh — cân, đầu đọc, máy in, PLC là thiết bị thật
  (theo `config.json`), còn hệ thống bên ngoài là công cụ mô phỏng: gửi lệnh (WMS/WCS) và nhận
  pallet (RCS). Dữ liệu và giới hạn cổng 8500 giống MANUAL. Phần thiết bị giả trên công cụ mô
  phỏng bị làm mờ; công nhân ảo chỉ còn tự bấm ĐỊNH DANH.
- Đủ thùng của pallet → “ĐÃ HOÀN THÀNH PALLET - HÃY BẤM NÚT ĐỊNH DANH”; công nhân bấm **Định
  danh** thì mới gửi pallet lên server (đổi sang tự gửi: Cài đặt → *Gửi pallet về server*).
- Đèn trạng thái trên thanh đầu: xanh = tốt, nền đỏ = lỗi (rê chuột xem lý do), cam = chưa có
  kết quả. **WCS** = cổng nhận lệnh 8500 đang mở. **RCS** = lần gửi pallet gần nhất lên server
  (cam = chưa gửi lần nào từ lúc mở phần mềm / đổi chế độ; lỗi thì tự gửi lại mỗi 30 s).

## 4. Thiết bị

| Thiết bị | Cấu hình (như bản cũ) |
|---|---|
| Cân | COM4, 9600 8N1. Quá 2 s không có số → “MẤT TÍN HIỆU CÂN”; quá 10 s → tự đóng/mở lại cổng. |
| Đầu đọc Honeywell | COM3, 9600 8N1. Bật quét `16 54 0D`, tắt `16 55 0D`; thời gian chờ đọc mã ở thẻ Cài đặt (mặc định 5000 ms). |
| Máy in Godex EZ520+ | USB qua `drivers\EZio64.dll`. |
| PLC Mitsubishi | MX Component 5, đèn tháp M0 đỏ / M1 xanh / M2 vàng / M10 tắt. |

**Đầu đọc** – `tools\scanner_timeout.bat` gửi hai lệnh bản cũ để lại
(`resource\Cai thoi gian quet pda.txt`): `16 4D 0D` + `TRGSTO300000.` (tự tắt quét sau 300 s, lưu
vĩnh viễn – để phần mềm quyết định lúc dừng) và `TRGSTO?.` (đọc lại). Cổng lấy từ `config.json`.
Gửi lệnh khác: `tools\scanner_timeout.bat "TRGSTO?."`.

**PLC / MX Component 5**
1. Cài MX Component 5. Mở *Communication Settings Utility* **bằng Run as administrator**, tạo
   Logical Station tới PLC, *Connection test* phải đạt.
2. Nhập số Logical Station ở thẻ Cài đặt → *PLC / đèn tháp* (`devices.plc.station_number`); PLC có
   remote password thì điền `devices.plc.password`.
3. `check_env.bat` phải báo `[OK] MX Component: ActUtlType64 (MX Component 5)`; log khởi động có
   `Kết nối PLC OK: ActUtlType64 (MX Component 5), Logical Station 0`.

`ActUtlType64` không có IDispatch nên không gọi được bằng `win32com`; driver (`app\devices\plc_mx.py`)
gọi qua **comtypes** với interface `IActUtlType64`. PLC lỗi không chặn sản xuất, chỉ mất đèn tháp;
mã lỗi kèm nghĩa tiếng Việt hiện ở chỉ báo PLC và `device-*.log`.

**Cổng CH340 kẹt khi bật máy** – giả thuyết: cân phát dữ liệu liên tục nên Windows nhận nhầm là
chuột serial. `check_env.bat` báo cổng bị nhận là *Serial Mouse*; `tools\fix_serial_mouse.bat` tắt
dịch vụ `sermouse` (có lệnh hoàn tác trong file). Driver gốc: `drivers\CH34x_Install_Windows_v3_4.EXE`.

Vẫn phải gỡ / cài lại driver sau khi bật máy (PLC báo `Open lỗi 0x0180800C` dù đúng COM): thoát
G8 ID, chuột phải `tools\reinstall_ch340.bat` → *Run as administrator*. Tool gỡ mọi gói
CH341SER khỏi Driver Store, xoá các thiết bị CH340, cài lại driver 3.4 từ `drivers\CH341SER`
(giải nén từ bộ cài gốc, chữ ký Microsoft WHQL) bằng `pnputil`, rồi in bảng cổng COM. Log ở
`logs\reinstall_ch340-*.log`. Kiểm tra số COM vẫn khớp `config.json` và Logical Station của MX
Component rồi mở lại `run_app.bat`.

## 5. Log – gửi kèm khi cần hỗ trợ

`logs\`, mỗi ngày một file, giữ 30 ngày (`log.keep_days`). Xem / lọc được ở thẻ **Lịch sử Log**.

| File | Nội dung |
|---|---|
| `app-YYYYMMDD.log` | Toàn bộ diễn biến; mỗi lượt thùng có mã `[f061eeac po=… pallet=… thung=…]` |
| `http-YYYYMMDD.log` | Mọi bản tin vào (8500) / ra (server), đủ body và mã phản hồi |
| `device-YYYYMMDD.log` | Kết nối / mất kết nối từng thiết bị |
| `raw-YYYYMMDD.log` | Byte thô cân, đầu đọc (khi bật `"raw_device": true`) |
| `crash.log`, `restart.log` | Lỗi làm chết tiến trình; các lần tự khởi động lại |

## 6. Dữ liệu MongoDB

- `pallets`, `parcels`: chỉ lệnh đang làm / đang chờ. Pallet xong hoặc hủy chuyển sang
  `pallets_his`, `parcels_his`.
- Lịch sử tự xoá sau 90 ngày, `event_log` sau 30 ngày (TTL), trần 300.000 bản ghi mỗi bảng
  (`config.json` → `mongo`). Giảm `history_days` thì lịch sử cũ hơn bị xoá luôn.
- Cache mongod giới hạn 0,25 GB. Thẻ **Thông số** hiện số bản ghi và dung lượng.

## 7. Giao tiếp với hệ thống khác

Đặc tả đầy đủ (trường, mã lỗi, gửi lại, điểm cần xác nhận) cho đối tác WMS / WCS / RCS:
[DOCKING_PROTOCOL.md](DOCKING_PROTOCOL.md).

| | |
|---|---|
| Nhận lệnh | `POST http://<IP trạm>:8500/ids/orderTask/` → `1000 SUCCESS` / `1001 <lý do>` |
| Hủy lệnh | `POST …:8500/ids/cancelTask/`, body có `Task_ID` (hoặc `PO_ID` / `Pallet_ID`) |
| Kết quả định danh | `POST …:8500/ids/confirm_product/`, body `PO_ID`, `Line_ID`, `Pallet_ID`, `Location`, `Status`, `Message` |
| Gửi pallet | `POST pallet_done_url`, body `{Task_ID, PO_ID, WH_Code, Line_ID, palletID, Ctn}`; HTTP 2xx = xong, lỗi thì gửi lại mỗi 30 s |

## 8. Còn chờ xác nhận / chưa thử ở hiện trường

1. `cancelTask`, `confirm_product`: dựng lại từ chuỗi trong `VTP_Induction.exe` (không có trong
   tài liệu và mã nguồn) – cần một bản tin thật của WMS để đối chiếu tên trường.
2. Lệnh có `Pallet_ID` đang có trong danh sách bị bỏ qua nhưng vẫn trả `1000 SUCCESS` cho WMS,
   kể cả khi khác PO / Task – chờ quyết định có trả lỗi hay không.
3. PLC: đã `Open` / `Close` được ở trạm; bật đèn (`SetDevice`) và dò kết nối (`GetDevice`) chưa
   xác nhận.
4. `tools\scanner_timeout.bat`: mới thử với cổng COM giả.
5. Máy in Godex: đã nạp `EZio64.dll` và kết nối; nên dùng *In thử tem* ở thẻ Cài đặt lần đầu.
6. Chưa làm: xuất PDF danh sách tem.

## 9. Cấu trúc thư mục

```
G8-ID-Deploy\
  app\          phần mềm chính (engine.py nghiệp vụ, devices\ driver, static\ giao diện)
  simulator\    công cụ mô phỏng
  tests\        bộ kiểm tra tự động
  tools\        kiểm tra máy, firewall, CH340, đầu đọc
  drivers\      EZio64/32.dll (Godex), G8_Label.bmp, bộ cài CH340 (+ CH341SER\ đã giải nén)
  mongodb\bin\  mongod.exe 4.4
  wheels\       thư viện Python cài offline
  config.json   cấu hình trạm      data\  dữ liệu (không trên git)      logs\  log
resource\       tài liệu, cấu hình và bộ cài của bản cũ (tham khảo)
```
