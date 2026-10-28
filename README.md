# G8 ID – Trạm định danh thùng / pallet (Python + MongoDB, v2.4.11)

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
4. Nhấp đúp **`cai_dat_may_moi.bat`** trong thư mục phần mềm, bấm *Yes* ở hộp thoại quyền
   Administrator. File này làm hết các bước cần file bat (chạy lại nhiều lần cũng không sao):
   cài thư viện Python (`install.bat`), mở firewall cổng 8500 (`tools\open_firewall.bat`), chống
   Windows nhận nhầm cân là chuột serial (`tools\fix_serial_mouse.bat`, mục 4), tạo 2 biểu tượng
   *Chạy phần mềm* / *Chạy mô phỏng* trên Desktop, hỏi có cài thời gian quét đầu đọc không
   (`tools\scanner_timeout.bat`), cuối cùng chạy `check_env.bat`. Xong thì **khởi động lại máy** một lần.
5. Sửa `config.json`: `station_id`, `desk_no` (số thứ tự bàn định danh), cổng COM cân / đầu đọc,
   `pallet_done_url` (số bàn, cổng COM, máy in, PLC cũng sửa được ở thẻ **Cài đặt**, xem mục 4).
6. **PLC / đèn tháp**: cài MX Component 5, tạo Logical Station (mục 4). Hiện các trạm dùng
   Logical Station **0** (`devices.plc.station_number`), để `devices.plc.progid` rỗng.
7. **Đầu đọc**: nếu ở bước 4 chưa cài (chưa cắm / chưa sửa cổng COM), tắt G8 ID rồi chạy
   `tools\scanner_timeout.bat` một lần (mục 4); hai dòng phải `[OK]`.
8. Tắt hẳn `VTP_Induction.exe` cũ (không dùng chung được cổng 8500 và cổng COM).
9. Xử lý các dòng `[LỖI]` của `check_env.bat` (chạy lại được bất cứ lúc nào).
10. **Chạy**: biểu tượng *Chạy phần mềm* (`chay_dinh_danh.bat`) → Chrome mở `http://127.0.0.1:8600`. Để cửa sổ đen mở (thu nhỏ).
    Tự chạy khi đăng nhập Windows: đặt shortcut của `chay_dinh_danh.bat` vào `shell:startup`.

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
Chạy `install.bat`, mở `chay_dinh_danh.bat` ở thư mục mới, sửa shortcut trong `shell:startup` (nếu có).
Chạy ổn rồi mới xoá thư mục cũ.

## 2. Cập nhật phiên bản mới

1. **Đóng G8 ID** (cửa sổ đen `chay_dinh_danh.bat`) và công cụ mô phỏng.
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
5. Mở `chay_dinh_danh.bat`.

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
| `chay_dinh_danh.bat` | Chạy phần mềm + mở Chrome. Chết bất thường thì tự chạy lại sau 3 s. |
| `chay_mo_phong.bat` | Công cụ mô phỏng (`http://127.0.0.1:8700`). Chỉ chạy khi phần mềm ở **MANUAL** / **HYBRID**. |
| `HUONG_DAN_VAN_HANH.pdf` | Hướng dẫn kỹ thuật vận hành: biểu tượng *Chạy phần mềm* (`chay_dinh_danh.bat`) và *Chạy mô phỏng* (`chay_mo_phong.bat`). Nguồn: `docs\huong_dan_van_hanh.py`. |
| `check_env.bat` | Kiểm tra máy (Python, thư viện, COM, máy in, MX Component, firewall) → `logs\check_env.txt`. |
| `run_tests.bat` | 26 bài kiểm tra tự động (~3 phút), chạy được ngay trên máy trạm. |
| `cai_dat_may_moi.bat` | Cài đặt máy trạm mới (mục 1, bước 4). |
| `install.bat` | Cài thư viện Python. |
| `tools\scanner_timeout.bat` | Gửi lệnh cấu hình xuống đầu đọc (mục 4). |
| `tools\restart_ch340.bat` | Khởi động lại cổng CH340 bị kẹt, không cần gỡ/cài driver. |
| `tools\reinstall_ch340.bat` | Gỡ và cài lại driver CH340 tự động (mục 4). |

- Giao diện nghe ở `0.0.0.0:8600`; mật khẩu thẻ Cài đặt mặc định **1234**.
- **AUTO**: thiết bị thật, DB `g8id`, gửi pallet tới server thật.
  **MANUAL**: thiết bị và server giả của công cụ mô phỏng, DB riêng `g8id_manual`; cổng 8500 chỉ
  nhận lệnh từ chính máy (lệnh WMS bị trả 503). Đổi ở thẻ Cài đặt khi đang STOP. Không chuyển /
  chạy AUTO được khi cửa sổ `chay_mo_phong.bat` còn mở.
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
| Cân | Cổng *USB Serial Port* (cáp FTDI), 9600 8N1. Quá 2 s không có số → “MẤT TÍN HIỆU CÂN”; cổng vẫn giữ mở, có số lại là chạy tiếp (không tự đóng / mở lại cổng); chỉ đọc cổng lỗi (rút cáp) mới mở lại. |
| Đầu đọc Honeywell | Cổng *USB Serial Device*, 9600 8N1. Bật quét `16 54 0D`, tắt `16 55 0D`; thời gian chờ đọc mã ở thẻ Cài đặt (mặc định 5000 ms). |
| Máy in Godex EZ520+ | USB qua `drivers\EZio64.dll`. |
| PLC Mitsubishi | Cáp *USB-SERIAL CH340*, MX Component 5, đèn tháp M0 đỏ / M1 xanh / M2 vàng / M10 tắt. Nút trên tủ: **M20 START / M22 STOP / M21 ĐỊNH DANH** (đọc mỗi 200 ms). |

**Chọn cổng COM ở thẻ Cài đặt → Thiết bị**
- **Tự dò** (mặc định): mỗi lần khởi động và mỗi lần *Lưu + kết nối lại*, phần mềm tìm cổng có tên
  Windows (Device Manager → Ports) chứa mẫu `detect` trong `config.json`: cân = `USB Serial Port`,
  đầu đọc = `USB Serial Device`, PLC = `CH340`. Số COM có đổi (cắm lỗ USB khác) thì vẫn tìm ra.
  Không thấy, hoặc thấy nhiều cổng khớp, thì thiết bị để None, Trang chủ báo *CHƯA TÌM THẤY CỔNG
  COM: …* và phải chọn cổng thủ công. Máy in Godex đi USB nên không dò cổng COM.
- Máy đặc biệt dùng cổng khác: chọn thẳng một cổng (thủ công, `auto: false`); phần mềm giữ đúng
  cổng đó, không dò nữa. Cổng chọn tay không bị thiết bị Tự dò lấy mất.
- Ô *Cổng* chỉ liệt kê các cổng COM Windows đang thấy, kèm tên thiết bị, cộng thêm **None** (không
  dùng thiết bị đó, phần mềm không mở cổng). Cắm thêm cáp thì bấm *Dò lại cổng COM*. Cổng trong
  `config.json` mà không còn trên máy hiện là *KHÔNG CÓ TRÊN MÁY*.
- Một cổng chỉ gán cho một thiết bị: cổng đã gán cho thiết bị khác bị khoá, ghi *[đang dùng: …]*;
  muốn chuyển thì đặt thiết bị kia về None trước. Lưu mà trùng cổng sẽ bị từ chối. Cổng COM của
  máy in chỉ tính khi *Kiểu kết nối* = COM; của PLC chỉ tính khi bật *Dùng PLC*.
- PLC đặt cổng COM trong *Communication Settings Utility*; ô *Cổng COM của Logical Station* chỉ để
  ghi lại cổng đó cho phần mềm không gán trùng (`devices.plc.com_port`).
- Nút **Kiểm tra** dùng cấu hình đang chọn, chưa cần lưu (phải đang STOP). Phần mềm tạm đóng cổng
  của thiết bị đó rồi mở lại sau khi thử. *Cân*: nghe 3 s, đọc ra khối lượng là đạt. *Đầu đọc*: gửi
  lệnh bật quét, đưa một mã vạch vào trong 6 s; cổng tự gửi số liên tục thì báo “giống cân”.
  *Máy in*: mở kết nối EZio (muốn chắc thì *In thử*). *PLC*: Open/Close Logical Station.
  Kết quả ghi vào `app-*.log` (`Kiểm tra …`).

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
gọi qua **comtypes** với interface `IActUtlType64`. PLC lỗi không chặn sản xuất, chỉ mất đèn tháp
và nút trên tủ (vẫn bấm được nút trên màn hình); mã lỗi kèm nghĩa tiếng Việt hiện ở chỉ báo PLC và
`device-*.log`.

**Nút vật lý trên tủ** (như `timerPLCButtonScan_Tick` của `VTP_Induction.exe`): luồng PLC đọc
`devices.plc.buttons` = `{"start": "M20", "stop": "M22", "identify": "M21"}` mỗi `button_poll_ms`
(200 ms). Nút kích **một lần ở sườn lên** (bit 0 → 1, giữ nút không kích lặp); lần đọc đầu sau khi
nối PLC chỉ ghi nhận mức hiện tại. Mỗi nút làm đúng việc của nút trên màn hình (Bắt đầu / Dừng /
Định danh); không làm được thì dải thông báo hiện lý do chữ đỏ (vd. `CHƯA ĐỦ SỐ LƯỢNG HÀNG!`,
`KHÔNG CÓ LỆNH SẢN XUẤT…`). Log: `Nhấn nút START từ PLC`. PLC tự bật / tắt bit theo nút, phần mềm
chỉ đọc. Trạm nối nút vào bit khác thì sửa `buttons` trong `config.json`; để `""` = bỏ nút đó.

**Cổng CH340 kẹt khi bật máy** – giả thuyết: cân phát dữ liệu liên tục nên Windows nhận nhầm là
chuột serial. `check_env.bat` báo cổng bị nhận là *Serial Mouse*; `tools\fix_serial_mouse.bat` tắt
dịch vụ `sermouse` (có lệnh hoàn tác trong file). Driver gốc: `drivers\CH34x_Install_Windows_v3_4.EXE`.

**PLC mất kết nối → tự khởi động lại cáp CH340 của PLC** (giống rút cắm, không gỡ driver). Không làm
khi bật phần mềm, chỉ khi PLC lỗi: đang chạy mà rớt (đã nối ổn ≥ 10 s) thì khởi động lại ngay rồi Open;
Open vẫn lỗi thì chờ 3 → 6 → … 60 s, mỗi lần lại khởi động lại rồi Open. Vừa nối đã rớt thì cũng chờ lùi
dần. Chỉ đụng **đúng một thiết bị**: cáp CH340 có số COM bằng `devices.plc.com_port`; chưa biết cổng PLC,
cổng PLC trùng cổng cân / đầu đọc / máy in, hoặc không thấy cáp đó thì không làm gì. Lệnh:
`pnputil /restart-device` (một lệnh, không để thiết bị ở trạng thái "đã tắt"). Cần quyền Administrator:
`chay_dinh_danh.bat` tự xin (UAC → *Yes*); bấm *No* thì vẫn chạy, chỉ không khởi động lại cáp. Log:
`PLC: đã khởi động lại cáp USB-SERIAL CH340 (COM12)` hoặc `PLC: không khởi động lại được cáp CH340: …`
(lý do ghi một lần). Tắt: `devices.plc.ch340_restart_on_error = false`.

Vẫn phải gỡ / cài lại driver sau khi bật máy (PLC báo `Open lỗi 0x0180800C` dù đúng COM): thoát
G8 ID, chuột phải `tools\reinstall_ch340.bat` → *Run as administrator*. Tool gỡ mọi gói
CH341SER khỏi Driver Store, xoá các thiết bị CH340, cài lại driver 3.4 từ `drivers\CH341SER`
(giải nén từ bộ cài gốc, chữ ký Microsoft WHQL) bằng `pnputil`, rồi in bảng cổng COM. Log ở
`logs\reinstall_ch340-*.log`. Kiểm tra số COM vẫn khớp `config.json` và Logical Station của MX
Component rồi mở lại `chay_dinh_danh.bat`.

**Chẩn đoán PLC tự động** – `kiem_tra_plc.bat` (thoát G8 ID trước, chuột phải → *Run as
administrator*): tự tìm cổng của cáp CH340, kiểm tra tiết kiệm điện USB và các bản ghi CH340 cũ,
mở cổng thô (pyserial) để phân biệt *bị chiếm* / *không có* / *kẹt DCB*, Open MX Component, đọc
nút mỗi 200 ms trong 120 s như G8 ID. Lỗi giữa chừng thì thử lại cổng thô, tắt / bật lại CH340 và
đọc sự kiện Kernel-PnP để kết luận. Báo cáo ở `logs\kiem_tra_plc-*.txt`. Chạy lâu hơn:
`kiem_tra_plc.bat --giay 900`. Chép `handle64.exe` (Sysinternals) vào `tools\` thì tool chỉ ra
đúng tiến trình đang giữ cổng.

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
- Cache mongod giới hạn 0,25 GB. Thẻ **Cài đặt** → *Thông tin trạm* hiện số bản ghi và dung lượng.

## 7. Giao tiếp với hệ thống khác

Đặc tả đầy đủ (trường, mã lỗi, gửi lại, điểm cần xác nhận) cho đối tác WMS / WCS / RCS:
[DOCKING_PROTOCOL.md](DOCKING_PROTOCOL.md).

| | |
|---|---|
| Nhận lệnh | `POST http://<IP trạm>:8500/ids/orderTask/` → `1000 SUCCESS` / `1001 <lý do>` |
| Dừng PO | `POST …:8500/ids/cancelTask/`, body có `Task_ID` (hoặc `PO_ID` / `Pallet_ID`): hủy các pallet chờ của PO, giữ pallet đang làm để ĐỊNH DANH nốt |
| Kết quả định danh | `POST …:8500/ids/confirm_product/`, body `PO_ID`, `Line_ID`, `Pallet_ID`, `Location`, `Status`, `Message` |
| Gửi pallet | `POST pallet_done_url`, body `{Task_ID, PO_ID, WH_Code, Line_ID, palletID, Ctn}`; HTTP 2xx = xong, lỗi thì gửi lại mỗi 30 s |

## 8. Còn chờ xác nhận / chưa thử ở hiện trường

1. `cancelTask`, `confirm_product`: dựng lại từ chuỗi trong `VTP_Induction.exe` (không có trong
   tài liệu và mã nguồn) – cần một bản tin thật của WMS để đối chiếu tên trường.
2. Lệnh có `Pallet_ID` đang có trong danh sách bị bỏ qua nhưng vẫn trả `1000 SUCCESS` cho WMS,
   kể cả khi khác PO / Task – chờ quyết định có trả lỗi hay không.
3. PLC: đã `Open` / `Close` được ở trạm; bật đèn (`SetDevice`), dò kết nối và đọc nút M20 / M21 / M22
   (`GetDevice`) chưa xác nhận trên PLC thật – địa chỉ nút lấy từ `VTP_Induction.exe`.
4. `tools\scanner_timeout.bat`: mới thử với cổng COM giả.
5. Máy in Godex: đã nạp `EZio64.dll` và kết nối; nên dùng *In thử tem* ở thẻ Cài đặt lần đầu.
6. *In PDF mã hiện tại* (thẻ Thông số) mở trang tem 70x40 mm trong Chrome để in / *Lưu dưới dạng PDF*;
   chưa thử in trang này ra máy Godex qua driver Windows.

## 9. Phiên bản

Số phiên bản (`VERSION` trong `app\config.py`) tăng mỗi lần cập nhật phần mềm. Xem bản đang chạy ở góc
đồng hồ trên thanh đầu (`dd/mm/yyyy · v2.4.11 · ST02 · Bàn 1 · AUTO`) hoặc thẻ Cài đặt → *Thông tin trạm*.

| Bản | Thay đổi |
|---|---|
| 2.4.11 | Cân: **bỏ tự đóng / mở lại cổng khi cân im lặng** (đã có ở 2.4.8, bị gỡ theo khi quay về ở 2.4.9) – im lặng thì giữ cổng, báo mất tín hiệu, ghi log một lần; chỉ đọc cổng lỗi (rút cáp) mới mở lại. |
| 2.4.10 | PLC mất kết nối → **tự khởi động lại cáp CH340 của PLC** (`pnputil /restart-device`, chỉ cáp ở cổng PLC, không đụng cân / đầu đọc / máy in), rồi Open lại; Open lỗi thì chờ 3 → 60 s rồi lặp lại. Không khởi động lại khi bật phần mềm. `chay_dinh_danh.bat` tự xin quyền Administrator. |
| 2.4.9 | **Quay về mã 2.4.6.** Gỡ 2.4.7 (G8 ID tự tắt / bật lại cáp PLC CH340, tự xin quyền Administrator – trạm ST01 báo `Disable-PnpDevice : Generic failure` rồi mất cả PLC, cân, đầu đọc) và 2.4.8 (biểu tượng "Chạy định danh", bỏ đóng / mở lại cổng cân). Biểu tượng Desktop đã tạo giữ nguyên, vẫn chạy được. |
| 2.4.2 | **WMS/WCS dừng PO giữa chừng** (`cancelTask`): mở rộng từ `Task_ID` / `Pallet_ID` / `PO_ID` ra cả PO (cùng `PO_ID` hoặc `PO_Name`, vì WCS gửi mỗi pallet một `Task_ID`). Pallet chờ (`WAIT`) bị hủy – WMS chỉ gán trước, chưa sản xuất. Pallet đang làm được giữ: vẫn cân / in / đọc tiếp, nút ĐỊNH DANH (màn hình và nút trên tủ) sáng ngay, bấm lúc nào cũng được – gửi IF-03 với `Ctn` = số thùng đạt thực tế, định danh xong là hết PO; 0 thùng đạt thì chỉ đóng pallet (`CANCEL`), không gửi. Trước đây hủy luôn cả pallet đang làm, thùng đã in không được báo về server. |
| 2.4.1 | **Nút vật lý trên tủ qua PLC** như bản cũ: M20 = START, M22 = STOP, M21 = ĐỊNH DANH, quét 200 ms, kích ở sườn lên (giữ nút không lặp, bit đang 1 lúc nối PLC không tự Bắt đầu). Làm đúng việc của nút trên màn hình; lỗi hiện ở dải thông báo. Địa chỉ bit sửa được ở `devices.plc.buttons`. Công cụ mô phỏng có 3 nút giả lập trong ô PLC. |
| 2.4.0 | Lệnh WCS: đọc **`GW`** (kg / thùng, vd. `1.637`) đổi ra gam (1637 g) làm khối lượng chuẩn khi cân – trước đây chỉ đọc `Weight_ref` nên lệnh WCS thật luôn cân theo cài đặt trạm (300 g); `Weight_ref` (gam) vẫn nhận và dùng trước `GW`. `Pallet_Current` lấy ở cấp lệnh (đúng bản tin WCS), không có mới tìm trong `info_detail`; hiện ở thẻ Thông số cùng khối lượng chuẩn. Ngày sản xuất: sửa tay được cả khi lệnh đã có thùng đạt – áp dụng từ thùng in tiếp theo trở đi cho mọi pallet còn lại của lệnh, tem đã in giữ ngày cũ (lệnh làm qua nhiều ngày). Tem: dòng **"Mã lệnh"** in `PO_Name` (vd. `VAS-091026-3`, thiếu thì `PO_ID`) thay cho `WH_Code`; nhãn tiếng Việt có dấu ("Quy cách : 6 chiếc", "Mã lệnh", "NSX"), dữ liệu từ lệnh in nguyên như WCS gửi. Trang *In PDF mã hiện tại* in giống vậy. |
| 2.3.3 | Tem: dòng "Ma Pallet" đổi thành **"Quy cach : N chiec"** – số chiếc / thùng lấy theo `Inner_Carton` của lệnh; lệnh không gửi `Inner_Carton` thì lấy `Qty / Ctn` (chia hết), không có cả hai thì để trống. Trang *In PDF mã hiện tại* in giống vậy. |
| 2.3.2 | Tem: logo G8HOME mới (`drivers/G8_Label.bmp`, đen trắng 100x55 điểm, nằm trong khu logo cũ cạnh số thứ tự thùng). Trang *In PDF mã hiện tại* dùng cùng ảnh logo thay cho chữ "G8HOME". |
| 2.3.1 | Tem: **mã QR và dải dưới cùng đều là nguyên phần tử `Carton_List`** WMS gửi (vd. `TRU_V01_10W_AT\|\|\|\|\|\|\|48\|0\|G8HOME…\|\|001\|…\|01`) để nhà máy đọc mã sản phẩm. Đầu đọc quét tem → phần mềm tách mã định danh (phần thứ 10) rồi mới so khớp với thùng đang làm. Chuỗi dài: mã QR tự nhỏ ô lại cho vừa khung (64 ký tự = 33 ô x 7 điểm ~ 29 mm), chữ dải dưới tự thu cho vừa 1 dòng (~2 mm). Trang *In PDF mã hiện tại* in giống vậy. |
| 2.3.0 | Tem: bỏ ngày in (khu trên mã QR chỉ còn giờ in); tên sản phẩm chữ to hơn, in đậm, tối đa 3 dòng; dải dưới cùng là mã định danh WMS gửi xuống = nội dung mã QR. Trang chủ: *Số thùng hoàn thành* tính theo lệnh – tổng thùng đã làm / tổng thùng cần làm của mọi pallet thuộc lệnh (pallet đã xong tính đủ số thùng của pallet, pallet nạp lại từ lịch sử không bị đếm 2 lần). |
| 2.2.0 | Trang chủ: bỏ ô log, cột thông tin rộng hơn 1,8 lần, chữ to gấp đôi; dải thông báo dưới cùng cao gấp đôi, chữ dài tự xuống 2 dòng. Cài đặt: thêm *Cài đặt vận hành* – sửa tay ngày sản xuất (NSX) của lệnh chưa định danh; thông tin trạm chuyển từ thẻ Thông số sang. Thông số: bố cục và nút như phần mềm cũ (In PDF mã hiện tại, Thành công ảo, Tải lệnh mới, Xóa lệnh đang làm, Gửi định danh, Thực hiện lại, Tải mã định danh, In lại mã định danh). Bấm Định danh / Gửi định danh: gửi ngay, không hỏi xác nhận. Tem: bỏ khối lượng, thêm NSX; giờ in lên trên mã QR, mã định danh xuống dải dưới cùng, bỏ chữ "Ten SP" / "Ma SP", tên SP in 2 dòng. Thư viện mới `segno` (mã QR trang PDF) – `update.bat` tự chạy `install.bat`. |
| 2.1.0 | Bản thay thế `VTP_Induction.exe`: Python + MongoDB, giao diện Chrome, mô phỏng, HYBRID, tự dò cổng COM. |

## 10. Cấu trúc thư mục

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
