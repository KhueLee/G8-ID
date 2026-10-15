===============================================================================
 G8 ID - TRẠM ĐỊNH DANH THÙNG / PALLET
 Bản Python + MongoDB, v2.1.0
===============================================================================

Thay cho phần mềm WinForms VTP_Induction.exe. Giữ nguyên quy trình, câu thông báo,
bố cục màn hình và driver thiết bị của bản cũ; giao diện chạy trên Google Chrome.


-------------------------------------------------------------------------------
 1. CÀI ĐẶT TRÊN MỘT MÁY TRẠM (LÀM MỘT LẦN)
-------------------------------------------------------------------------------

 1) Cài Python 3.10 trở lên, 64-bit, tick "Add python.exe to PATH".
    (Bộ thư viện offline trong wheels\ dành cho Python 3.13 64-bit; phiên bản khác
    thì install.bat tự tải qua internet.)
 2) Chép cả thư mục G8-ID-Deploy vào máy (ví dụ D:\G8-ID-Deploy).
 3) Chạy install.bat.
 4) Sửa config.json: station_id, cổng COM của cân / đầu đọc, địa chỉ pallet_done_url.
    (Cổng COM và máy in cũng sửa được trong thẻ Cài đặt.)
 5) Chuột phải -> Run as administrator:
      - tools\open_firewall.bat     : mở cổng 8500 cho hệ thống gửi lệnh.
      - tools\fix_serial_mouse.bat  : xem mục 5, rồi khởi động lại máy.
 6) Chạy check_env.bat và xử lý các dòng [LỖI].
 7) Tắt hẳn VTP_Induction.exe cũ (hai phần mềm không dùng chung được cổng 8500
    và cổng COM).
 8) Đầu đọc mới / chưa cài: khi G8 ID đang tắt, chạy tools\scanner_timeout.bat một
    lần. Nó gửi lệnh Honeywell của bản cũ TRGSTO300000. (thời gian tự tắt quét
    300 s, lưu vào đầu đọc) rồi TRGSTO?. để đọc lại; cả hai dòng phải báo [OK].
 9) Muốn tự chạy khi đăng nhập Windows: tạo shortcut của run_app.bat trong
    shell:startup.

MongoDB KHÔNG CẦN CÀI: mongodb\bin\mongod.exe (bản 4.4, chạy được cả trên CPU không
có AVX) được phần mềm tự bật, chỉ nghe ở 127.0.0.1, dữ liệu nằm trong data\db. Nếu
máy đã có MongoDB chạy sẵn ở cổng 27017 thì phần mềm dùng luôn cái đó.


-------------------------------------------------------------------------------
 2. CÁC FILE .BAT
-------------------------------------------------------------------------------

 run_app.bat
    Chạy phần mềm + mở Chrome tại http://127.0.0.1:8600. Cửa sổ đen phải để mở
    (thu nhỏ). Phần mềm chết bất thường thì tự chạy lại sau 3 giây.

 run_simulator.bat
    Công cụ mô phỏng, giao diện web http://127.0.0.1:8700. Chỉ chạy được khi
    phần mềm chính ở MANUAL.

 run_tests.bat
    Bộ kiểm tra tự động (19 bài, ~2 phút). Dùng thư mục tạm và cổng riêng nên
    chạy được ngay trên máy trạm.

 check_env.bat
    Kiểm tra máy: Python, thư viện, cổng COM, máy in, MX Component, firewall...
    Ghi logs\check_env.txt.

 install.bat
    Cài thư viện Python.

Giao diện nghe ở 0.0.0.0:8600. Mật khẩu thẻ Cài đặt mặc định: 1234 (đổi trong thẻ
Cài đặt).


-------------------------------------------------------------------------------
 3. AUTO / MANUAL VÀ CÔNG CỤ MÔ PHỎNG
-------------------------------------------------------------------------------

 - AUTO  : thiết bị thật, database g8id, gửi pallet tới server thật.
 - MANUAL: thiết bị nối tới công cụ mô phỏng, database riêng g8id_manual, gửi
           pallet tới server giả trong công cụ mô phỏng. Cổng 8500 chỉ nhận lệnh
           từ chính máy đó (lệnh thật của WMS bị trả 503 để không rơi vào dữ liệu
           mô phỏng). Màn hình có dải vàng cảnh báo.
 - Đổi chế độ: thẻ Cài đặt -> "Chuyển AUTO / Chuyển MANUAL" (phải đang STOP).
 - run_simulator.bat từ chối chạy nếu phần mềm chính đang AUTO.
 - Chuyển về AUTO VÀ bấm Bắt đầu ở AUTO đều bị chặn chừng nào cửa sổ
   run_simulator.bat còn mở (kể cả khi công cụ mô phỏng đã dừng nhưng cửa sổ
   chưa đóng).

Chạy thử một lệnh:
   Cài đặt -> Chuyển MANUAL -> run_simulator.bat -> "Gửi lệnh sản xuất"
   -> trên màn hình chính bấm Bắt đầu -> "Đặt thùng lên cân" / "Nhấc thùng ra"
   (hoặc tick "Công nhân ảo") -> đủ thùng thì bấm Định danh.


-------------------------------------------------------------------------------
 4. LỖI CỦA BẢN CŨ VÀ CÁCH XỬ LÝ TRONG BẢN NÀY
-------------------------------------------------------------------------------

 [1] Đang chạy thì crash
     Nguyên nhân : Lỗi trong luồng nền/timer không được bắt; lỗi SQL hiện
                   MessageBox từ luồng nền.
     Bản này     : Mọi luồng đều bắt lỗi và ghi log; lỗi vòng xử lý ->
                   "LỖI HỆ THỐNG: ...", đèn đỏ, về STOP; tiến trình chết thì
                   run_app.bat tự chạy lại, tiến độ lấy lại từ MongoDB.

 [2] Crash / bấm X thì treo giao diện
     Nguyên nhân : Luồng nền gọi Invoke vào giao diện trong khi giao diện đang
                   chờ luồng đó; Thread.Abort; đóng cổng COM trong lúc sự kiện
                   DataReceived đang chạy.
     Bản này     : Giao diện là trang web, tách hẳn khỏi phần xử lý. Mọi chỗ chờ
                   đều ngắt được: Dừng giữa lúc đang đọc mã vạch mất 0,3 s (đo
                   trong bài kiểm tra).

 [3] Khởi động chờ 1-2 phút kết nối SQL
     Nguyên nhân : SQL Server Express khởi động chậm sau khi bật máy.
     Bản này     : mongod kèm theo: sẵn sàng sau khoảng 3 s (đo trên máy dựng).

 [4] Tắt phần mềm phải gỡ/cài lại driver CH340
     Nguyên nhân : Phần mềm treo khi đóng -> bị kill khi cổng COM còn mở dở.
     Bản này     : Thoát bằng nút "Thoát phần mềm", Ctrl+C, dấu X hay tắt máy
                   đều đi qua cùng một bước: tắt đèn, đóng cổng cân/đầu đọc/máy
                   in/PLC, tắt mongod.

 [5] Bật máy phải gỡ/cài lại driver CH340
     Nguyên nhân : GIẢ THUYẾT, CHƯA KIỂM CHỨNG TẠI HIỆN TRƯỜNG: cân phát dữ liệu
                   liên tục nên Windows nhận nhầm là "chuột serial" lúc khởi
                   động và chiếm cổng COM.
     Bản này     : tools\fix_serial_mouse.bat (xem mục 5). Ngoài ra cổng mở lỗi
                   thì phần mềm tự thử lại (3 -> 30 s) nên không cần mở lại phần
                   mềm.

 [6] Cân treo, phải bấm Apply trên cân
     Nguyên nhân : Chưa rõ (cân hay đường truyền).
     Bản này     : Quá 2 s không có số -> báo "MẤT TÍN HIỆU CÂN", không dùng số
                   cũ; quá 10 s -> tự đóng/mở lại cổng COM. Nếu vẫn phải bấm
                   Apply thì lỗi nằm ở cân: bật "raw_device": true trong
                   config.json để ghi byte thô vào logs\raw-*.log và gửi lại.


-------------------------------------------------------------------------------
 5. LỖI CỔNG CH340 KHI BẬT MÁY
-------------------------------------------------------------------------------

check_env.bat báo nếu có cổng COM đang bị nhận là "Serial BallPoint / Serial Mouse"
và nếu dịch vụ sermouse chưa tắt. tools\fix_serial_mouse.bat tắt dịch vụ đó (một
giá trị registry, có ghi lệnh hoàn tác trong file). Nếu sau đó cổng vẫn kẹt:
tools\restart_ch340.bat khởi động lại thiết bị CH340 mà không cần gỡ/cài driver.
Driver CH340 gốc nằm ở drivers\CH34x_Install_Windows_v3_4.EXE.


-------------------------------------------------------------------------------
 5a. PLC / ĐÈN THÁP QUA MX COMPONENT 5
-------------------------------------------------------------------------------

Driver app\devices\plc_mx.py viết theo "MX Component Version 5 Reference Manual"
(SH-082395ENG, Mitsubishi Electric) và theo đúng cách bản cũ dùng (CPLC.cs):

 - Control dùng : ActUtlType64 (kiểu "utility setting", mục 9.1): chỉ có
                  ActLogicalStationNumber và ActPassword. Mọi thông số truyền
                  thông (loại CPU, USB/Ethernet, IP...) nằm trong Logical Station
                  tạo bằng Communication Settings Utility.
 - Kết nối      : Open() trả 0 là được, khác 0 là mã lỗi (mục 11.3, chương 13).
                  Báo "đã Open" (0xF0000003 / 0x01808001) thì Close() rồi Open()
                  lại.
 - Đèn tháp     : SetDevice("M0"/"M1"/"M2"/"M10", 0 hoặc 1) - M0 đỏ, M1 xanh,
                  M2 vàng, M10 tắt, như bản cũ.
 - Dò kết nối   : GetDevice("M10") mỗi 5 s; lỗi -> chỉ báo PLC đỏ, tự
                  Close/Open lại (3 -> 60 s).
 - Luồng        : Control là STA (mục 11.1) -> chỉ một luồng riêng chạm vào nó;
                  PLC treo không làm treo cân - in.
 - Thoát        : Tắt đèn rồi Close() (sổ tay cảnh báo kill tiến trình đang
                  truyền thông có thể làm kẹt tiến trình khác).

Cài đặt trên máy trạm:
 1) Cài MX Component 5, mở Communication Settings Utility BẰNG Run as
    administrator, tạo Logical Station tới PLC (bấm Connection test trong đó phải
    đạt).
 2) Nhập số Logical Station vào thẻ Cài đặt -> "PLC / đèn tháp" (hoặc config.json
    -> devices.plc.station_number). PLC có remote password thì điền
    devices.plc.password.
 3) check_env.bat phải báo: [OK] MX Component: ActUtlType64 (MX Component 5)

ActUtlType64 là chương trình COM riêng (ActUtlType64.exe) nên dùng được với Python
64-bit đang cài. Lỗi PLC hiện kèm mã và nghĩa tiếng Việt ở chỉ báo PLC (rê chuột)
và trong device-*.log, ví dụ:
   Open lỗi 0xF0000002 (không đọc được Logical Station ...)

ActUtlType64 KHÔNG CÓ IDispatch nên không gọi được bằng win32com.client.Dispatch
(báo "No such interface supported"). Driver gọi qua thư viện comtypes với interface
IActUtlType64 lấy từ thư viện kiểu nhúng trong ActUtlType64.exe (đường dẫn đọc từ
registry). Đã thử ở trạm: Open()/Close() trả 0 với Logical Station 0. Chưa thử ở
trạm: SetDevice bật đèn và GetDevice dò kết nối (comtypes trả (lData, mã lỗi)). Nếu
GetDevice không gọi được theo kiểu đó, phần mềm tự tắt bước dò kết nối và ghi một
dòng cảnh báo; đèn tháp vẫn chạy. Hãy gửi lại device-*.log sau lần chạy đầu.


-------------------------------------------------------------------------------
 6. LOG - GỬI KÈM KHI CẦN HỖ TRỢ
-------------------------------------------------------------------------------

Thư mục logs\, mỗi ngày một file, tự xóa sau 30 ngày (log.keep_days):

 app-YYYYMMDD.log
    Toàn bộ diễn biến. Mỗi lượt thùng có mã lượt:
    [f061eeac po=... pallet=... thung=...] - lọc theo mã thùng/pallet là ra đủ
    cân, in, đọc mã.

 http-YYYYMMDD.log
    Mọi bản tin vào (cổng 8500) và ra (server), ĐỦ BODY và mã phản hồi.

 device-YYYYMMDD.log
    Kết nối / mất kết nối / mở lại cổng của từng thiết bị.

 raw-YYYYMMDD.log
    Byte thô của cân, đầu đọc (chỉ khi bật raw_device).

 crash.log, restart.log
    Lỗi làm chết tiến trình; các lần run_app.bat tự khởi động lại.

 sim-*.log, mongod.log, check_env.txt
    Công cụ mô phỏng, MongoDB, kết quả kiểm tra máy.

Thẻ "Lịch sử Log" xem và lọc được các file này ngay trên màn hình.


-------------------------------------------------------------------------------
 7. DỮ LIỆU MONGODB (CHỐNG TRÀN)
-------------------------------------------------------------------------------

 - pallets, parcels: chỉ chứa lệnh đang làm / đang chờ. Pallet xong hoặc bị hủy
   là chuyển sang pallets_his, parcels_his (thay cho trigger SQL của bản cũ).
 - *_his tự xóa sau 90 ngày, event_log sau 30 ngày (TTL index), thêm trần 300.000
   bản ghi mỗi bảng, kiểm tra mỗi giờ. Sửa ở config.json -> mongo.
 - Mọi truy vấn trên màn hình đi theo index và có giới hạn số dòng. Bộ nhớ đệm
   của mongod giới hạn 0,25 GB.
 - Thẻ "Thông số" hiện số bản ghi và dung lượng hiện tại.


-------------------------------------------------------------------------------
 8. GIAO TIẾP VỚI HỆ THỐNG KHÁC
-------------------------------------------------------------------------------

 NHẬN LỆNH
    POST http://<IP trạm>:8500/ids/orderTask/
    Phản hồi giống bản cũ (1000 SUCCESS, Only POST is allowed, Empty body,
    Invalid JSON, order_id invalid, Server error).

 HỦY LỆNH
    POST ...:8500/ids/cancelTask/
    Body có Task_ID (cũng nhận PO_ID hoặc Pallet_ID); thiếu -> 400 Task_ID
    invalid. Pallet của lệnh chuyển sang lịch sử với trạng thái CANCEL, màn hình
    báo "HỦY LỆNH SẢN XUẤT-WMS YÊU CẦU".

 KẾT QUẢ ĐỊNH DANH
    POST ...:8500/ids/confirm_product/
    Body: PO_ID, Line_ID, Pallet_ID, Location, Status, Message.
    Thiếu -> 400 PO_ID invalid / Line_ID or Pallet_ID invalid.
    Status = "true" -> "ĐÃ HOÀN THÀNH PALLET: ..." (pallet còn chờ gửi thì đóng
    luôn); khác -> "LỖI GỬI ĐỊNH DANH VỀ WMS: Lỗi từ WMS: <Message>".

 GỬI PALLET
    POST pallet_done_url, body {Task_ID, PO_ID, WH_Code, Line_ID, palletID, Ctn}.
    HTTP 2xx là thành công; lỗi thì giữ pallet và gửi lại mỗi 30 s.


-------------------------------------------------------------------------------
 9. NHỮNG ĐIỂM CẦN ANH XÁC NHẬN
-------------------------------------------------------------------------------

Mã nguồn trong g8-identification-area-master.zip CŨ HƠN file VTP_Induction.exe đang
cài trên máy trạm (exe có thêm cancelTask, confirm_product, nút định danh pallet, đọc
mã 2 lần, Weight_ref, MFG_Date...). Phần có trong mã nguồn được làm theo mã nguồn;
phần chỉ có trong exe được dựng lại từ các chuỗi trích trong exe, nên các điểm sau
là SUY ĐOÁN:

 1) Bản tin cancelTask và confirm_product không có trong tài liệu
    G8ID-Tai-lieu-he-thong (tài liệu chỉ mô tả IF-01 orderTask, IF-02, IF-03 và ghi
    "cổng 8500 chỉ có đúng đường dẫn này") và cũng không có trong mã nguồn. Hai bản
    tin này được dựng lại từ các chuỗi còn trong VTP_Induction.exe: câu trả lời lỗi
    (Task_ID invalid, PO_ID invalid, Line_ID or Pallet_ID invalid), dòng log
    (Cancel Task_ID=..., PO=..., PO_Name=..., Line=..., From=... và ...,
    Location=..., Status=..., Message=...), câu SQL xóa theo Task_ID và các thông
    báo màn hình. Tên trường là suy ra từ đó, CHƯA ĐỐI CHIẾU VỚI MỘT BẢN TIN THẬT -
    nhờ anh gửi một bản tin mẫu của WMS (lấy trong http-*.log sau lần chạy đầu
    cũng được).
    Một điểm chưa rõ: bản cũ coi pallet là xong khi server trả HTTP 2xx hay phải
    chờ confirm_product có Status = true. Hiện tại: HTTP 2xx là xong;
    confirm_product báo lỗi sau đó thì chỉ hiện thông báo đỏ và ghi log, không mở
    lại pallet.

 2) Gửi pallet: theo exe là công nhân bấm nút sau thông báo "ĐÃ HOÀN THÀNH PALLET -
    HÃY BẤM NÚT ĐỊNH DANH", gửi tới :8060/identify-service/ids/pallet_identify_done.
    Đổi sang tự gửi: Cài đặt -> "Gửi pallet về server" -> "Tự động".
    Lời gọi :8070/storage_product và bản tin kết thúc lệnh status: 8 của mã nguồn
    cũ không còn trong exe nên KHÔNG làm.

 3) Tên trường trong lệnh cho các mục mới (Item_Name, PO_Name, MFG_Date,
    Weight_ref, Pallet_Current) lấy theo tên cột SQL. Lệnh có Weight_ref > 0 thì
    dùng làm khối lượng chuẩn, không thì dùng giá trị trong Cài đặt.

 4) Hộp thoại "Có tiếp nhận lệnh sản xuất mới không?" có trong mã nguồn nhưng
    không còn trong exe -> mặc định tắt (lệnh vào là xếp hàng chờ). Bật lại trong
    Cài đặt.

 5) PLC / MX Component 5: đã lập trình theo sổ tay (mục 5a) nhưng CHƯA CHẠY THỬ
    VỚI MX COMPONENT VÀ PLC THẬT. Cần anh cho biết số Logical Station đang dùng
    trên máy trạm. Máy chỉ có MX Component 4 (32-bit) thì phải cài Python 32-bit.
    PLC lỗi không chặn sản xuất, chỉ mất đèn tháp.

 6) Máy in Godex, cân, đầu đọc thật: chưa có thiết bị để in / cân / quét thật. Đã
    thử: nạp được EZio64.dll, driver cân và đầu đọc chạy đúng với cổng COM giả
    (bài kiểm tra tự động). Lần đầu ở hiện trường nên dùng "In thử tem" trong thẻ
    Cài đặt và xem device-*.log.

 7) In lại toàn bộ tem pallet (mới ở v2.1.0, cần mật khẩu, phải đang STOP):
    - Pallet đang làm: thẻ Cài đặt -> "In lại toàn bộ tem pallet đang làm".
    - Pallet đã xong: thẻ Thông số -> "Lịch sử pallet" -> nút "In lại tem".
    - In lại tem của CÁC THÙNG ĐÃ ĐẠT (đúng khối lượng đã cân), sau đó tem pallet
      nếu pallet đã chốt và đang bật "In + quét mã pallet". Thùng chưa cân/in đạt
      không được in, để không có tem cho thùng chưa qua kiểm tra - khác bản cũ ở
      chỗ nút "In tất cả" của bản cũ lấy mọi mã của pallet; nếu anh cần đúng như
      cũ thì báo lại.
    - Tiến độ hiện ở dòng thông báo Trang chủ (ĐANG IN LẠI TEM PALLET ...: 3/13);
      bấm Dừng để hủy; máy in lỗi thì dừng và báo đúng mã thùng. Không Bắt đầu
      được khi đang in lại. Mỗi tem ghi một dòng [REPRINT] trong app-*.log.
    - Đã chạy với máy in mô phỏng (bài kiểm tra tự động); chưa in ra máy Godex
      thật và chưa bấm thử các nút mới trên Chrome.

 8) Tính năng trong exe CHƯA LÀM: xuất PDF danh sách tem.
    Đã có: in lại tem thùng gần nhất, tra lịch sử pallet, nạp lại pallet từ lịch
    sử, hủy pallet.


-------------------------------------------------------------------------------
 10. CẤU TRÚC THƯ MỤC
-------------------------------------------------------------------------------

 app\           phần mềm chính (engine.py = nghiệp vụ, devices\ = driver,
                static\ = giao diện)
 simulator\     công cụ mô phỏng
 tests\         bộ kiểm tra tự động
 tools\         kiểm tra máy, sửa lỗi cổng CH340, mở firewall
 drivers\       EZio64/32.dll (Godex), G8_Label.bmp, bộ cài CH340
 mongodb\bin\   mongod.exe 4.4.29
 wheels\        thư viện Python cài offline
 config.json    cấu hình trạm
 data\          dữ liệu
 logs\          log
