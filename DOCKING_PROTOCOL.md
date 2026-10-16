# G8 ID – Docking protocol (giao tiếp trạm định danh ↔ WMS / WCS / RCS)

Phiên bản phần mềm trạm: **2.1.0**. Tài liệu mô tả đúng hành vi của mã nguồn hiện tại
(`G8-ID-Deploy/app/webui.py`, `app/engine.py`). Mục 8 liệt kê các điểm cần đối tác xác nhận.

## 1. Tổng quan

| Mã | Bản tin | Chiều | Địa chỉ |
|---|---|---|---|
| IF-01 | Nhận lệnh sản xuất | Hệ thống gửi lệnh → Trạm | `POST http://<IP trạm>:8500/ids/orderTask/` |
| IF-04 | Hủy lệnh | Hệ thống gửi lệnh → Trạm | `POST http://<IP trạm>:8500/ids/cancelTask/` |
| IF-05 | Kết quả định danh pallet | WMS → Trạm | `POST http://<IP trạm>:8500/ids/confirm_product/` |
| IF-03 | Pallet đã định danh xong | Trạm → identify-service | `POST <pallet_done_url>` – hiện `http://192.168.110.189:8060/identify-service/ids/pallet_identify_done` |

- Mỗi máy trạm (12 máy) có IP riêng; lệnh gửi tới trạm nào thì trạm đó xử lý.
- Chỉ báo trên màn hình trạm: **WCS** = cổng 8500 đang nhận lệnh; **RCS** = kết quả lần gửi
  IF-03 gần nhất (xanh thành công, đỏ lỗi, cam chưa gửi).
- IF-02 (`storage_product`, cổng 8070) và bản tin kết thúc lệnh `status: 8` trong tài liệu cũ
  **không còn dùng** (không có trong `VTP_Induction.exe` đang chạy).

### Trình tự một lệnh

```
WMS/WCS                     Trạm                                  identify-service
   | IF-01 orderTask          |                                          |
   |------------------------->|  200 {1000, SUCCESS}                     |
   |<-------------------------|                                          |
   |                          |  cân – in tem – đọc mã từng thùng        |
   |                          |  công nhân bấm ĐỊNH DANH                 |
   |                          |  IF-03 pallet_identify_done ------------>|
   |                          |<----------------------------- HTTP 2xx   |
   |                          |  pallet xong → pallet kế tiếp            |
   | IF-05 confirm_product    |  (tuỳ chọn, WMS báo kết quả cuối)        |
   |------------------------->|                                          |
```

## 2. Quy ước chung (cổng 8500)

- HTTP, JSON UTF-8, **không xác thực**. Đường dẫn chấp nhận có hoặc không có `/` cuối.
- Tên trường **không phân biệt hoa/thường**; một số trường nhận thêm tên khác (ghi ở từng bảng).
- Mọi phản hồi có dạng `{"code": <số>, "desc": "<chuỗi>"}`. `desc` tiếng Việt được mã hoá
  dạng `\uXXXX` (JSON hợp lệ).

| Trường hợp | HTTP | Phản hồi |
|---|---|---|
| Xử lý được | 200 | `{"code":1000,"desc":"SUCCESS"}` |
| Không phải POST | 405 | `{"code":1001,"desc":"Only POST is allowed"}` |
| Body rỗng | 400 | `{"code":1001,"desc":"Empty body"}` |
| JSON sai cú pháp / không phải object | 400 | `{"code":1001,"desc":"Invalid JSON"}` |
| Dữ liệu không hợp lệ | 400 | `{"code":1001,"desc":"<lý do>"}` (từng bản tin bên dưới) |
| Trạm đang chế độ MANUAL (mô phỏng) | 503 | `{"code":1001,"desc":"Station is in MANUAL (simulation) mode"}` |
| Lỗi nội bộ trạm | 500 | `{"code":1001,"desc":"Server error"}` |

Ở chế độ MANUAL trạm chỉ nhận bản tin từ chính máy đó (127.0.0.1); bên gửi nhận 503 thì gửi lại
sau.

## 3. IF-01 – Nhận lệnh sản xuất

`POST http://<IP trạm>:8500/ids/orderTask/`

```json
{
  "Task_ID": "1-188580023__18:16:23.159836",
  "PO_ID": 188580023,
  "PO_Name": "PO-188580023",
  "WH_Code": "WH01",
  "Line_ID": "LINE_01",
  "fromSystem": "WMS",
  "info_detail": [
    {
      "Pallet_ID": "LPN00977",
      "Location": "S02.135.1",
      "Item_Code": "SP-A",
      "Item_Name": "SAN PHAM A",
      "Carton_List": ["a|b|c|d|e|f|g|h|i|TP0000101|k", "TP0000102"],
      "Ctn": 60, "Qty": 720, "Pcs": 0, "Inner_Carton": 12, "Inner_Pallet": 60,
      "Weight_ref": 300,
      "MFG_Date": "15/10/2026"
    }
  ]
}
```

**Cấp lệnh**

| Trường | Kiểu | Bắt buộc | Ý nghĩa / trạm dùng để |
|---|---|---|---|
| `PO_ID` | số nguyên > 0 (nhận cả chuỗi số) | có | Mã lệnh; gửi lại trong IF-03 |
| `Task_ID` | chuỗi | nên có | Mã tác vụ; gửi lại trong IF-03; khoá hủy lệnh IF-04 |
| `info_detail` | mảng (tên khác: `InforDetail`, `infor_detail`) | có, ≥ 1 phần tử | Mỗi phần tử là một pallet |
| `WH_Code` | chuỗi | | Mã kho; in trên tem thùng; gửi lại trong IF-03 |
| `Line_ID` | chuỗi (`LineId`, `LineProduction`) | | Dây chuyền; mặc định `LINE_01`; gửi lại trong IF-03 |
| `PO_Name` | chuỗi | | Tên lệnh (pallet có `PO_Name` riêng thì dùng của pallet) |
| `fromSystem` | chuỗi (`From_System`) | | Chỉ lưu |
| `Weight_ref`, `MFG_Date` | | | Giá trị mặc định cho các pallet không có trường này |

**Cấp pallet (`info_detail[]`)**

| Trường | Kiểu | Bắt buộc | Ý nghĩa / trạm dùng để |
|---|---|---|---|
| `Pallet_ID` | chuỗi (`PalletId`) | có | Mã pallet; in trên tem thùng; `palletID` của IF-03 |
| `Carton_List` | mảng chuỗi (`CartonList`) | có, ≥ 1 | Mỗi chuỗi là một thùng (quy tắc tách mã bên dưới) |
| `Location` | chuỗi | | Vị trí sàn của pallet, hiện trên màn hình |
| `Item_Code` / `Item_Name` | chuỗi | | Tên sản phẩm trên màn hình và tem (ưu tiên `Item_Name`) |
| `Weight_ref` | số (gam) | | > 0 thì dùng làm khối lượng chuẩn khi cân; không có thì dùng cài đặt của trạm |
| `MFG_Date` | chuỗi | | Ngày sản xuất |
| `Ctn`, `Qty`, `Pcs`, `Inner_Carton`, `Inner_Pallet`, `Pallet_Current` | số | | Lưu; số thùng thực tế lấy theo độ dài `Carton_List` |

**Tách mã thùng:** mỗi chuỗi trong `Carton_List` được cắt khoảng trắng rồi tách theo `|`. Có từ
11 phần trở lên thì mã thùng là **phần thứ 10**; ít hơn thì dùng nguyên chuỗi. Chuỗi gốc được lưu
kèm.

**Kiểm tra – từ chối cả lệnh (400, không nạp pallet nào):**

| `desc` | Khi |
|---|---|
| `order_id invalid` | `PO_ID` thiếu hoặc ≤ 0 |
| `Lệnh sản xuất không có dữ liệu chi tiết.` | `info_detail` thiếu, rỗng hoặc không phải mảng |
| `Thiếu Pallet_ID trong info_detail` | Một pallet không có `Pallet_ID` |
| `Pallet <id> không có Carton_List` | `Carton_List` thiếu hoặc rỗng |
| `Mã thùng trống hoặc trùng trong lệnh: <mã>` | Mã thùng rỗng hoặc lặp trong cùng lệnh |
| `Mã thùng <mã> đang nằm trong lệnh khác` | Mã thùng đang thuộc một pallet chưa xong ở trạm |

**Pallet trùng:** pallet có `Pallet_ID` đang có trong danh sách chờ / đang làm của trạm thì
**bị bỏ qua**, các pallet khác của lệnh vẫn nạp; phản hồi vẫn `200 SUCCESS` – kể cả khi mọi
pallet đều trùng và kể cả khi khác `PO_ID` / `Task_ID` (xem mục 8). Pallet đã xong hoặc đã hủy
(chuyển sang lịch sử) không còn tính là trùng.

**Ý nghĩa 200 SUCCESS:** trạm đã nhận và xếp lệnh vào hàng chờ, **chưa** có nghĩa đã làm. Trạm
làm lần lượt từng pallet theo thứ tự nhận. Trạm đang dừng thì tự bắt đầu khi có lệnh mới (cài
đặt *auto_start_on_order*). Nếu trạm bật *Hỏi khi có lệnh mới*, lệnh chờ công nhân chọn Yes/No;
chọn No thì lệnh bị bỏ và trạm không báo ngược.

## 4. IF-04 – Hủy lệnh

`POST http://<IP trạm>:8500/ids/cancelTask/`

```json
{ "Task_ID": "1-188580023__18:16:23.159836" }
```

| Trường | Ghi chú |
|---|---|
| `Pallet_ID` (`palletID`, `PalletId`) | Có thì chỉ hủy pallet này (ưu tiên cao nhất) |
| `Task_ID` | Không có `Pallet_ID` thì hủy mọi pallet của tác vụ |
| `PO_ID` | Không có hai trường trên thì hủy mọi pallet của lệnh |

- Không có trường nào → `400 {"code":1001,"desc":"Task_ID invalid"}`.
- Pallet bị hủy (kể cả đang làm dở / đang chờ gửi) chuyển sang lịch sử với trạng thái `CANCEL`;
  màn hình báo “HỦY LỆNH SẢN XUẤT-WMS YÊU CẦU”. Trạm **không** gửi IF-03 cho pallet đã hủy.
- Không tìm thấy pallet nào khớp vẫn trả `200 SUCCESS` (hủy lặp lại không lỗi).

## 5. IF-05 – Kết quả định danh pallet

`POST http://<IP trạm>:8500/ids/confirm_product/`

```json
{ "PO_ID": 188580023, "Line_ID": "LINE_01", "Pallet_ID": "LPN00977",
  "Location": "S02.135.1", "Status": "true", "Message": "" }
```

| Trường | Bắt buộc | Ghi chú |
|---|---|---|
| `PO_ID` | có, > 0 | Thiếu → `400 PO_ID invalid` |
| `Pallet_ID` (`palletID`, `PalletId`) | có | Thiếu → `400 Line_ID or Pallet_ID invalid` |
| `Line_ID` (`LineId`) | có | Thiếu → `400 Line_ID or Pallet_ID invalid` |
| `Status` | | `"true"` (không phân biệt hoa thường, nhận cả `true`) = thành công; khác = lỗi |
| `Message` | | Hiện trên màn hình khi lỗi |
| `Location` | | Chỉ ghi log |

- `Status = true`: màn hình “ĐÃ HOÀN THÀNH PALLET: <id>”; nếu pallet còn đang chờ gửi IF-03
  thì trạm đóng luôn pallet đó (không gửi IF-03 nữa).
- Khác: màn hình đỏ “LỖI GỬI ĐỊNH DANH VỀ WMS: Lỗi từ WMS: <Message>”; pallet **không** bị mở lại.
- Luôn trả `200 SUCCESS` khi đủ trường, kể cả không tìm thấy pallet.

## 6. IF-03 – Pallet đã định danh xong (trạm gửi đi)

`POST <pallet_done_url>` (cấu hình `servers.pallet_done_url` trong `config.json`),
header `Content-Type: application/json; charset=utf-8`, body UTF-8 (tiếng Việt không mã hoá).

```json
{ "Task_ID": "1-188580023__18:16:23.159836", "PO_ID": 188580023, "WH_Code": "WH01",
  "Line_ID": "LINE_01", "palletID": "LPN00977", "Ctn": 60 }
```

| Trường | Nguồn |
|---|---|
| `Task_ID`, `PO_ID`, `WH_Code`, `Line_ID` | Lấy từ IF-01 của pallet |
| `palletID` | `Pallet_ID` |
| `Ctn` | Số thùng của pallet đã cân – in đạt |

- **Thời điểm:** mọi thùng của pallet đã đạt, sau đó công nhân bấm **ĐỊNH DANH** (mặc định)
  hoặc gửi tự động (cài đặt *Gửi pallet về server = Tự động*). Mỗi pallet gửi một bản tin.
- **Thành công:** HTTP 2xx trong 10 s (`servers.timeout_s`). **Nội dung body phản hồi không được
  kiểm tra.** Pallet chuyển sang lịch sử `DONE`, trạm làm pallet kế tiếp.
- **Lỗi** (timeout, không kết nối được, HTTP khác 2xx): pallet giữ trạng thái chờ gửi, dây chuyền
  dừng ở pallet đó, trạm **tự gửi lại mỗi 30 s** (`servers.retry_s`) tới khi thành công; dữ liệu
  còn nguyên sau khi tắt/mở phần mềm.
- **Bên nhận phải chấp nhận nhận trùng** cùng `palletID` (phản hồi mất trên đường truyền → trạm
  gửi lại).

## 7. Mạng, log, đối soát

| Cổng | Chiều | Ghi chú |
|---|---|---|
| 8500/TCP | vào trạm | IF-01, IF-04, IF-05. Mở bằng `tools\open_firewall.bat` |
| 8060/TCP | trạm ra server | IF-03 |
| 8600/TCP | nội bộ | Giao diện vận hành trên Chrome, không dành cho hệ thống khác |

Mọi bản tin vào (đủ body, IP gửi, mã phản hồi) và ra (body, HTTP status, nội dung phản hồi, thời
gian) ghi trong `G8-ID-Deploy\logs\http-YYYYMMDD.log` của từng trạm, giữ 30 ngày – dùng để đối
soát khi có tranh chấp. Có thể gửi lại một bản tin thật chép từ log bằng công cụ mô phỏng
(`chay_mo_phong.bat` → *Gửi bản tin thô*, chỉ ở chế độ MANUAL).

Mã IF-04, IF-05 là đánh số mới trong tài liệu này (tài liệu cũ chỉ có IF-01 → IF-03); IF-03 giữ
mã cũ nhưng nay gửi theo từng pallet, không còn trường `status: 8`.

## 8. Cần đối tác xác nhận

1. **IF-04 `cancelTask` và IF-05 `confirm_product`** không có trong tài liệu hệ thống cũ; tên
   trường được dựng lại từ chuỗi trong `VTP_Induction.exe`. Cần một bản tin mẫu thật cho mỗi loại.
2. **Pallet trùng khác PO / Task** (ví dụ: 4 lệnh PO khác nhau cùng `Pallet_ID = LPN00977` gửi
   liên tiếp từ 192.168.110.189) đang bị bỏ qua nhưng trả `200 SUCCESS`, nên bên gửi tưởng trạm đã
   nhận. Đề xuất: cùng `Task_ID` → `200` (gửi lặp); khác → `400 "Pallet <id> đang thuộc PO <po>"`.
   Đồng thời cần xác nhận: một `Pallet_ID` có thể xuất hiện trong nhiều lệnh cùng lúc không?
3. **IF-03 thành công** hiện chỉ dựa vào HTTP 2xx. Nếu server trả 200 kèm `code` lỗi trong body,
   trạm vẫn coi là xong – cần thống nhất có kiểm tra `code` (ví dụ `1000`) hay không.
4. **Pallet xong khi nào:** HTTP 2xx của IF-03, hay phải chờ IF-05 `Status = true`? Hiện tại:
   2xx là xong; IF-05 báo lỗi sau đó chỉ hiện thông báo, không mở lại pallet.
5. **Định dạng thật của `Carton_List`** (2–3 mẫu) và vị trí mã thùng (hiện: phần thứ 10 khi có từ
   11 phần `|`).
6. Đơn vị `Weight_ref` (trạm hiểu là gam) và định dạng `MFG_Date`.
