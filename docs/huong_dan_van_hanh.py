"""Tạo G8-ID-Deploy/HUONG_DAN_VAN_HANH.pdf - hướng dẫn kỹ thuật vận hành dùng 2 biểu tượng
"Chạy phần mềm" (chay_dinh_danh.bat) và "Chạy mô phỏng" (chay_mo_phong.bat).

Chạy: python docs/huong_dan_van_hanh.py   (cần reportlab; font Arial của Windows)
"""
import os
import time

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (CondPageBreak, KeepTogether, ListFlowable, ListItem, PageBreak,
                                Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "G8-ID-Deploy", "HUONG_DAN_VAN_HANH.pdf")
FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")

pdfmetrics.registerFont(TTFont("Arial", os.path.join(FONTS, "arial.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Bold", os.path.join(FONTS, "arialbd.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Italic", os.path.join(FONTS, "ariali.ttf")))
pdfmetrics.registerFont(TTFont("Arial-BoldItalic", os.path.join(FONTS, "arialbi.ttf")))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic",
                              boldItalic="Arial-BoldItalic")

INK = colors.HexColor("#1d2330")
MUTED = colors.HexColor("#5a6270")
BRAND = colors.HexColor("#1f5fae")
AMBER = colors.HexColor("#7a4b00")
LINE = colors.HexColor("#c9ced6")
SOFT = colors.HexColor("#eef2f7")
WARN_BG = colors.HexColor("#fff4d6")
WARN_LINE = colors.HexColor("#e0a800")
OK_GREEN = colors.HexColor("#1e8a1e")
BAD_RED = colors.HexColor("#c62828")
ORANGE = colors.HexColor("#d97a00")

base = ParagraphStyle("base", fontName="Arial", fontSize=10.5, leading=14.5, textColor=INK)
small = ParagraphStyle("small", parent=base, fontSize=9, leading=12, textColor=MUTED)
cell = ParagraphStyle("cell", parent=base, fontSize=9.5, leading=12.5)
cellb = ParagraphStyle("cellb", parent=cell, fontName="Arial-Bold")
title = ParagraphStyle("title", parent=base, fontName="Arial-Bold", fontSize=22, leading=27,
                       textColor=BRAND)
subtitle = ParagraphStyle("subtitle", parent=base, fontSize=11.5, leading=16, textColor=MUTED)
h1 = ParagraphStyle("h1", parent=base, fontName="Arial-Bold", fontSize=16, leading=20,
                    textColor=colors.white)
h2 = ParagraphStyle("h2", parent=base, fontName="Arial-Bold", fontSize=12.5, leading=16,
                    textColor=BRAND, spaceBefore=10, spaceAfter=4)
note = ParagraphStyle("note", parent=base, fontSize=10, leading=14)
center = ParagraphStyle("center", parent=cellb, alignment=TA_CENTER)


def P(text, style=base):
    return Paragraph(text, style)


def section(text, color):
    t = Table([[P(text, h1)]], colWidths=[174 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), color),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (-1, -1), 7),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    return [Spacer(1, 4), t, Spacer(1, 6)]


def steps(items, start=1):
    return [ListFlowable([ListItem(P(x), leftIndent=16, value=i)
                         for i, x in enumerate(items, start)],
                        bulletType="1", start=start, bulletFontName="Arial-Bold",
                        bulletFontSize=10.5, leftIndent=16, spaceBefore=2)]


def bullets(items):
    return [ListFlowable([ListItem(P(x), leftIndent=14) for x in items], bulletType="bullet",
                        start="•", bulletFontName="Arial", leftIndent=14, spaceBefore=2)]


def box(paras, bg=WARN_BG, edge=WARN_LINE):
    t = Table([[[P(x, note) if isinstance(x, str) else x for x in paras]]], colWidths=[174 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg),
                           ("LINEBEFORE", (0, 0), (0, -1), 3, edge),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return [Spacer(1, 4), t, Spacer(1, 4)]


def table(rows, widths, head=True):
    data = [[P(c, cellb if (head and r == 0) else cell) if isinstance(c, str) else c
             for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if head else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.5, LINE),
          ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
          ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    if head:
        st.append(("BACKGROUND", (0, 0), (-1, 0), SOFT))
    t.setStyle(TableStyle(st))
    return [Spacer(1, 3), t, Spacer(1, 5)]


def header_strip():
    """Hình vẽ thanh trên cùng của màn hình chính: 6 chỉ báo + đèn tháp + nút Định danh."""
    names = ["PLC", "PRINTER", "SCALE", "BARCODE", "WCS", "RCS"]
    row = [P(n, center) for n in names] + [P('<font color="#e53935">●</font> <font color="#f2b600">●</font> <font color="#2e9e2e">●</font>', center), P("Định danh", center)]
    t = Table([row], colWidths=[16 * mm, 22 * mm, 18 * mm, 23 * mm, 16 * mm, 16 * mm,
                                22 * mm, 25 * mm])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, INK),
                           ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                           ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                                                      ("TOPPADDING", (0, 0), (-1, -1), 6),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    legend = table([
        ["Màu chỉ báo", "Ý nghĩa"],
        ['<font color="#1e8a1e"><b>Chữ xanh</b></font>', "Đã kết nối, hoạt động bình thường."],
        ['<font color="#c62828"><b>Nền đỏ</b></font>', "Mất kết nối / lỗi. Rê chuột vào chỉ báo để xem lý do."],
        ['<font color="#d97a00"><b>Cam</b></font>', "Chưa có kết quả (ví dụ RCS khi chưa gửi pallet nào)."],
    ], [32, 142])
    return [Spacer(1, 4), t, Spacer(1, 2)] + legend


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Arial", 8.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 10 * mm, "G8 ID – Hướng dẫn vận hành: Chạy phần mềm & Chạy mô phỏng")
    canvas.drawRightString(192 * mm, 10 * mm, "Trang %d" % doc.page)
    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, 13 * mm, 192 * mm, 13 * mm)
    canvas.restoreState()


def build():
    s = []
    # ------------------------------------------------------------------ trang đầu
    s += [P("HƯỚNG DẪN VẬN HÀNH TRẠM ĐỊNH DANH G8 ID", title), Spacer(1, 4),
          P("Dành cho kỹ thuật vận hành. Chỉ cần dùng 2 biểu tượng trên màn hình chính "
            "(Desktop) của máy trạm.", subtitle),
          P("Phiên bản phần mềm 2.1.0 · cập nhật %s" % time.strftime("%d/%m/%Y"), small),
          Spacer(1, 10)]
    s += table([
        ["Biểu tượng trên Desktop", "Mở file", "Dùng khi nào"],
        ["<b>Chạy phần mềm</b>", "chay_dinh_danh.bat",
         "Mỗi ca / mỗi lần bật máy. Đây là phần mềm định danh dùng cho <b>sản xuất thật</b>."],
        ["<b>Chạy mô phỏng</b>", "chay_mo_phong.bat",
         "Chỉ khi <b>chạy thử / kiểm tra</b>: giả lập hệ thống gửi lệnh (WMS/WCS), server nhận "
         "pallet (RCS) và – nếu cần – cả thiết bị tại bàn. <b>Không dùng khi đang sản xuất.</b>"],
    ], [42, 34, 98])
    s += box(["<b>Ba quy tắc quan trọng</b>",
              "1. Cửa sổ màu đen mở ra cùng phần mềm <b>không được đóng</b> – chỉ thu nhỏ (nút _ ). "
              "Đóng nó là tắt phần mềm.",
              "2. Sản xuất thật luôn ở chế độ <b>AUTO</b>. Nếu thấy dải màu vàng "
              "\u201cCHẾ ĐỘ MANUAL\u201d hoặc \u201cCHẾ ĐỘ HYBRID\u201d trên cùng màn hình là đang ở chế độ thử – "
              "không sản xuất.",
              "3. Muốn về AUTO phải <b>đóng hẳn</b> cửa sổ đen của \u201cChạy mô phỏng\u201d trước."])
    s += [P("Mục lục", h2)]
    s += bullets(["<b>Phần A – Chạy phần mềm</b>: mở, đọc màn hình, quy trình sản xuất, xử lý "
                  "thông báo, đổi chế độ, tắt phần mềm, cập nhật phần mềm.",
                  "<b>Phần B – Chạy mô phỏng</b>: chuẩn bị, các ô trên công cụ, chạy thử MANUAL, "
                  "chạy thử HYBRID, trở về sản xuất.",
                  "<b>Phần C – Khi cần hỗ trợ</b>: gửi gì cho kỹ thuật phần mềm."])

    # ------------------------------------------------------------------ PHẦN A
    s += [PageBreak()]
    s += section("PHẦN A – CHẠY PHẦN MỀM", BRAND)
    s += [P("A1. Mở phần mềm", h2)]
    s += steps([
        "Nhấp đúp biểu tượng <b>Chạy phần mềm</b> trên Desktop.",
        "Một cửa sổ đen hiện ra, dòng đầu màu xanh lá ghi <b>PHẦN MỀM ĐỊNH DANH SẢN PHẨM</b>. "
        "Bấm nút <b>_</b> để thu nhỏ, <b>không bấm X</b>.",
        "Sau vài giây Chrome tự mở màn hình định danh (địa chỉ <b>http://127.0.0.1:8600</b>).",
        "Chờ các chỉ báo trên thanh đầu chuyển <font color='#1e8a1e'><b>chữ xanh</b></font> "
        "(mục A2). PLC thường xanh chậm hơn vài giây.",
    ])
    s += box(["<b>Lỡ tắt Chrome?</b> Nhấp đúp <b>Chạy phần mềm</b> lần nữa – phần mềm vẫn đang chạy "
              "nên chỉ mở lại màn hình, không mất dữ liệu.",
              "<b>Phần mềm bị lỗi giữa chừng?</b> Cửa sổ đen tự khởi động lại sau 3 giây; tiến độ "
              "lệnh vẫn còn nguyên (kể cả khi mất điện)."], SOFT, BRAND)

    s += [P("A2. Đọc màn hình chính", h2),
          P("<b>Thanh trên cùng</b> – 6 chỉ báo kết nối, 3 đèn tháp và nút <b>Định danh</b>:")]
    s += header_strip()
    s += table([
        ["Chỉ báo", "Là gì"],
        ["PLC", "Bộ điều khiển đèn tháp. Lỗi PLC <b>không chặn</b> sản xuất, chỉ mất đèn tháp."],
        ["PRINTER", "Máy in tem Godex."],
        ["SCALE", "Cân điện tử."],
        ["BARCODE", "Đầu đọc mã vạch (đọc lại tem vừa in)."],
        ["WCS", "Cổng nhận lệnh sản xuất từ WMS/WCS đang mở."],
        ["RCS", "Lần gửi kết quả pallet gần nhất lên server: xanh = gửi được, đỏ = lỗi "
                "(máy tự gửi lại mỗi 30 giây), cam = chưa gửi lần nào."],
    ], [26, 148])
    s += [CondPageBreak(60 * mm), P("<b>Phần thân màn hình</b> chia 3 cột:")]
    s += table([
        ["Vùng", "Nội dung"],
        ["Cột trái", "Thùng hiện tại (đã làm / tổng), mã lệnh, mã pallet, vị trí, tên sản phẩm, "
                     "quy cách, cân nặng, số pallet và số thùng hoàn thành, ngày in trên tem."],
        ["Cột giữa", "Danh sách mã thùng của pallet đang làm (dòng xanh = thùng đang xử lý). "
                     "Bên dưới là <b>dòng thông báo</b> (có mũi tên) – luôn đọc dòng này để biết "
                     "máy đang chờ gì."],
        ["Cột phải", "Khối lượng cân; ô trạng thái lớn <b>STOP / RUN / OK / NG</b>; bộ đếm "
                     "<b>Đạt</b> / <b>Sai</b> (nút <i>Đặt lại bộ đếm</i> để về 0); nút "
                     "<b>Bắt đầu</b> và <b>Dừng</b>."],
        ["Các thẻ", "<b>Trang chủ</b> · <b>Cài đặt</b> (cần mật khẩu, mặc định 1234) · "
                    "<b>Thông số</b> (trạng thái, lịch sử pallet, in lại tem) · "
                    "<b>Lịch sử Log</b> · <b>Hướng dẫn</b> (mở tài liệu này)."],
    ], [26, 148])

    s += [CondPageBreak(80 * mm), P("A3. Quy trình sản xuất một lệnh (chế độ AUTO)", h2)]
    s += steps([
        "WMS gửi lệnh xuống trạm → danh sách thùng hiện ở cột giữa. Nếu trạm đang STOP, máy "
        "tự <b>Bắt đầu</b> (hoặc bấm <b>Bắt đầu</b>).",
        "Dòng thông báo: <b>CHỜ ĐẶT SẢN PHẨM LÊN CÂN</b> → đặt thùng lên cân.",
        "Máy tự làm: <b>CÂN SẢN PHẨM...</b> → <b>ĐANG IN TEM...</b> → dán tem đúng vị trí cho "
        "đầu đọc → <b>ĐANG ĐỌC MÃ VẠCH...</b> Số to ở góc trên tem (cạnh logo) là "
        "<b>số thứ tự của thùng trong pallet</b> (1, 2, 3 …), giống cột STT trong danh sách thùng.",
        "Thùng đạt: ô lớn <font color='#1e8a1e'><b>OK</b></font>, đèn xanh. Lấy thùng ra khỏi cân; "
        "khi thấy <b>SẴN SÀNG CHO SẢN PHẨM MỚI</b> thì đặt thùng tiếp theo.",
        "Đủ thùng của pallet: thông báo <b>ĐÃ HOÀN THÀNH PALLET - HÃY BẤM NÚT ĐỊNH DANH</b> → bấm nút "
        "<b>Định danh</b> trên thanh đầu, chọn <b>Yes</b> để gửi pallet lên server.",
        "Thấy <b>PALLET OK – TIẾP TỤC SẢN XUẤT</b> → làm pallet tiếp theo. Hết lệnh: "
        "<b>ĐÃ HOÀN TẤT LỆNH SẢN XUẤT</b>, trạm tự về STOP.",
    ])

    s += [CondPageBreak(70 * mm), P("A4. Thông báo lỗi trong lúc chạy và cách xử lý", h2)]
    s += table([
        ["Thông báo trên màn hình", "Xử lý"],
        ["SẢN PHẨM KHÔNG ĐẠT, VUI LÒNG BỎ RA KHỎI CÂN",
         "Sai khối lượng. Bỏ thùng ra, kiểm tra hàng. Đặt lại – máy cân lại cho đúng mã đó."],
        ["IN TEM THẤT BẠI, VUI LÒNG BỎ RA KHỎI CÂN",
         "Kiểm tra máy in (giấy, ribbon, nắp). Bỏ thùng ra rồi đặt lại – máy in lại đúng mã đó."],
        ["ĐANG ĐỌC MÃ VẠCH... (đứng mãi)",
         "Đầu đọc chưa thấy tem – máy <b>chờ tới khi đọc được</b>, không tự báo lỗi. Chỉnh tem vào "
         "tầm đầu đọc. Tem hỏng: bấm <b>Dừng</b>, bỏ thùng ra, bấm <b>Bắt đầu</b> và đặt lại – "
         "máy in tem mới."],
        ["KHÔNG ĐỌC ĐƯỢC MÃ VẠCH - BỎ RA KHỎI CÂN",
         "Đầu đọc đọc ra mã <b>khác</b> mã vừa in cả 2 lần (tem cũ / tem thùng khác lọt vào tầm "
         "đọc). Bỏ thùng ra, gỡ tem sai, đặt lại – máy in tem mới."],
        ["MẤT KẾT NỐI ĐẦU ĐỌC - KIỂM TRA CÁP PDA",
         "Kiểm tra cáp / nguồn đầu đọc. Nối lại được thì máy tự đọc tiếp."],
        ["VUI LÒNG LẤY HÀNG RA KHỎI CÂN", "Thùng cũ còn trên cân. Lấy ra hẳn để cân về 0."],
        ["MẤT TÍN HIỆU CÂN - KIỂM TRA KẾT NỐI CÂN",
         "Kiểm tra nguồn và cáp của cân. Máy tự nối lại khi có tín hiệu."],
        ["ĐANG CHỜ GỬI PALLET VỀ SERVER",
         "Server chưa nhận (chỉ báo RCS đỏ). Máy tự gửi lại mỗi 30 giây; nếu kéo dài, báo bộ phận "
         "IT / WMS kiểm tra mạng và server."],
        ["LỖI GỬI ĐỊNH DANH VỀ WMS: ...", "WMS từ chối pallet. Chụp màn hình gửi bộ phận WMS."],
        ["HỦY LỆNH SẢN XUẤT-WMS YÊU CẦU", "WMS đã hủy lệnh. Chờ lệnh mới."],
        ["LỖI HỆ THỐNG: ...", "Bấm Dừng → Bắt đầu. Lặp lại thì gửi log (Phần C)."],
    ], [70, 104])

    s += [CondPageBreak(60 * mm), P("A5. Bấm Bắt đầu bị từ chối", h2)]
    s += table([
        ["Hộp thông báo", "Xử lý"],
        ["KIỂM TRA LẠI KẾT NỐI MÁY IN!!", "Bật máy in, kiểm tra cáp USB. Chỉ báo PRINTER phải xanh."],
        ["KIỂM TRA LẠI KẾT NỐI PDA!!", "Kiểm tra cáp / nguồn đầu đọc. Chỉ báo BARCODE phải xanh."],
        ["KIỂM TRA LẠI KẾT NỐI TỚI CÂN!!", "Kiểm tra nguồn / cáp cân. Chỉ báo SCALE phải xanh."],
        ["KẾT NỐI ĐÈN LỖI. TIẾP TỤC HAY KHÔNG?",
         "PLC chưa nối. Chọn OK để sản xuất không có đèn tháp, báo kỹ thuật kiểm tra PLC."],
        ["KHÔNG CÓ LỆNH SẢN XUẤT. CHỜ PHẢN HỒI HỆ THỐNG!", "Chưa có lệnh từ WMS. Chờ lệnh."],
        ["CÔNG CỤ MÔ PHỎNG CHƯA ĐÓNG ...",
         "Cửa sổ đen của \u201cChạy mô phỏng\u201d còn mở. Đóng nó (mục B6) rồi bấm Bắt đầu lại."],
    ], [70, 104])

    s += [CondPageBreak(70 * mm), P("A6. Chế độ chạy", h2)]
    s += table([
        ["Chế độ", "Thiết bị tại bàn", "Lệnh & nhận pallet", "Dùng khi"],
        ["<b>AUTO</b>", "Thật", "WMS / server thật", "<b>Sản xuất</b>. Luôn để AUTO khi bàn giao ca."],
        ["<b>MANUAL</b>", "Giả lập (trên Chạy mô phỏng)", "Giả lập",
         "Thử phần mềm khi không có hoặc không muốn đụng tới thiết bị."],
        ["<b>HYBRID</b>", "Thật", "Giả lập",
         "Chạy thử thực tế tại bàn (cân, in, đọc, đèn thật) mà không gửi gì lên WMS thật."],
    ], [24, 42, 40, 68])
    s += [P("MANUAL và HYBRID dùng dữ liệu riêng, không lẫn vào dữ liệu sản xuất, và từ chối "
            "lệnh từ WMS thật. Cách đổi chế độ:")]
    s += steps(["Bấm <b>■ Dừng</b> (chỉ đổi được khi STOP).",
                "Mở thẻ <b>Cài đặt</b>, nhập mật khẩu.",
                "Ô <b>Chế độ chạy</b>: bấm <b>Chuyển AUTO</b> / <b>Chuyển MANUAL</b> / "
                "<b>Chuyển HYBRID</b>, chọn Yes."])

    s += [P("A7. Tắt phần mềm", h2)]
    s += steps(["Bấm <b>■ Dừng</b>.",
                "Thẻ <b>Cài đặt</b> → <b>Thoát phần mềm</b>. Cửa sổ đen tự đóng.",
                "Tắt máy bình thường. (Bấm X cửa sổ đen hoặc tắt máy khi phần mềm đang mở cũng "
                "không hỏng dữ liệu, nhưng nên Dừng trước.)"])

    s += [CondPageBreak(90 * mm), P("A8. Thông số trong thẻ Cài đặt", h2),
          P("Sửa rồi bấm <b>OK - Lưu thông số</b> là lưu ngay vào máy trạm, kể cả khi đang chạy "
            "(áp dụng từ thùng tiếp theo). Cập nhật phần mềm (git pull) không đụng tới các thông "
            "số này.")]
    s += table([
        ["Thông số", "Mặc định", "Ý nghĩa"],
        ["Khối lượng chuẩn (g)", "300",
         "Khối lượng đúng của một thùng. <b>Lệnh từ WCS có Weight_ref thì dùng Weight_ref</b>; "
         "chỉ khi lệnh không gửi (hoặc gửi 0) mới dùng số này. Dòng <i>Cân nặng</i> ở Trang chủ "
         "hiện số đang dùng."],
        ["Sai số cho phép (g)", "100",
         "Chỉ cấu hình ở đây (WCS không gửi), áp cho mọi lệnh. Thùng đạt khi khối lượng nằm "
         "trong <i>chuẩn ± sai số</i>."],
        ["Thời gian cân (s)", "2",
         "Cân phải đứng yên liên tục chừng này giây (2 lần đọc liền nhau lệch không quá 15 g) "
         "mới chốt khối lượng và so với chuẩn. Tránh chốt lúc thùng đang lắc."],
        ["Hỏi Yes/No khi có lệnh mới", "Tắt", "Bật thì có lệnh mới phải bấm Yes mới nhận."],
        ["Có lệnh mới thì tự Bắt đầu", "Bật", "Lệnh mới về khi trạm đang STOP thì tự chạy."],
        ["Gửi pallet về server", "Bấm nút ĐỊNH DANH",
         "<i>Tự động khi chốt pallet</i>: đủ thùng là tự gửi, không cần bấm Định danh."],
        ["Vị trí sàn (6 ô)", "S01.120.01 …",
         "Gõ tay tên các vị trí đặt pallet trên sàn. Vị trí của từng pallet do <b>WCS gửi trong "
         "lệnh</b> (Location, hiện ở dòng <i>Vị trí</i>). 3 ô đầu hiện thành VỊ TRÍ 01–03 ở Trang "
         "chủ; ô trùng với Location của pallet đang làm sẽ hiện tên để công nhân biết đặt pallet "
         "ở đâu. Ô 4–6 chỉ để lưu (giống bản cũ)."],
    ], [42, 26, 106])

    s += [CondPageBreak(70 * mm), P("A9. Cập nhật phần mềm (update.bat)", h2),
          P("Khi kỹ thuật phần mềm báo có bản mới, máy trạm cần có mạng:")]
    s += steps([
        "Tắt phần mềm (mục A7). Nếu phần mềm còn chạy, update.bat sẽ báo "
        "<b>[DUNG] Phan mem dinh danh dang chay</b> và không cập nhật.",
        "Mở thư mục phần mềm (thư mục có chay_dinh_danh.bat), nhấp đúp <b>update.bat</b>.",
        "Chờ dòng <b>[OK] Da cap nhat</b> (kèm danh sách thay đổi) hoặc "
        "<b>Da la ban moi nhat</b>. Bấm phím bất kỳ để đóng.",
        "Nhấp đúp <b>Chạy phần mềm</b> để chạy bản mới.",
    ])
    s += box(["Thông số trong thẻ Cài đặt và dữ liệu sản xuất <b>không bị ảnh hưởng</b> khi cập nhật.",
              "Nếu báo <b>[LOI] Khong cap nhat duoc</b>: kiểm tra mạng, rồi chụp màn hình cửa sổ "
              "gửi kỹ thuật phần mềm. Không tự sửa / xóa file trong thư mục phần mềm."], SOFT, BRAND)

    # ------------------------------------------------------------------ PHẦN B
    s += [PageBreak()]
    s += section("PHẦN B – CHẠY MÔ PHỎNG", AMBER)
    s += box(["\u201cChạy mô phỏng\u201d chỉ dùng để <b>chạy thử</b>. Nó chỉ mở được khi phần mềm "
              "đang ở <b>MANUAL</b> hoặc <b>HYBRID</b>, và tự tắt ngay khi phần mềm chuyển về AUTO."])
    s += [P("B1. Chuẩn bị và mở", h2)]
    s += steps([
        "Mở <b>Chạy phần mềm</b> trước (Phần A1).",
        "Đổi sang <b>MANUAL</b> hoặc <b>HYBRID</b> (mục A6). Màn hình chính hiện dải vàng.",
        "Nhấp đúp <b>Chạy mô phỏng</b>. Một cửa sổ đen thứ hai mở ra, dòng đầu màu xanh lá ghi "
        "<b>PHẦN MỀM MÔ PHỎNG ĐỊNH DANH</b> (để nguyên, thu nhỏ) và "
        "trình duyệt mở công cụ mô phỏng tại <b>http://127.0.0.1:8700</b>.",
        "Góc phải trên công cụ hiện <b>Phần mềm chính: MANUAL · STOP</b> (hoặc HYBRID) trên nền "
        "xanh là đã nối đúng.",
    ])
    s += box(["Nếu cửa sổ đen báo <b>PHẦN MỀM CHÍNH ĐANG Ở CHẾ ĐỘ AUTO</b> hoặc "
              "<b>KHÔNG KẾT NỐI ĐƯỢC PHẦN MỀM CHÍNH</b>: đóng cửa sổ đó, làm lại bước 1–2 rồi "
              "mở lại."], SOFT, BRAND)

    s += [P("B2. Các ô trên công cụ mô phỏng", h2)]
    s += table([
        ["Ô", "Dùng để", "MANUAL", "HYBRID"],
        ["Cân điện tử", "Đặt thùng / đặt thùng SAI khối lượng / nhấc thùng; tắt cân để thử mất tín hiệu.",
         "Có", "Mờ (dùng cân thật)"],
        ["Đầu đọc mã vạch", "Chọn kết quả đọc: đúng, sai 1 lần, luôn sai, không đọc được "
         "(máy chính đứng chờ ở ĐANG ĐỌC MÃ VẠCH).",
         "Có", "Mờ"],
        ["Máy in tem", "Xem các tem \u201cđã in\u201d; giả lập in lỗi.", "Có", "Mờ"],
        ["PLC / đèn tháp", "Xem màu đèn phần mềm đang bật.", "Có", "Mờ"],
        ["Hệ thống gửi lệnh (WMS / WCS)",
         "<b>Gửi lệnh sản xuất</b> (số pallet, số thùng/pallet, Weight_ref); hủy lệnh theo "
         "Task_ID; gửi bản tin JSON tùy ý.", "Có", "Có"],
        ["Server nhận pallet – RCS",
         "Chọn cách server trả lời khi bấm Định danh: 200 SUCCESS / 500 lỗi / không trả lời. "
         "Xem các pallet đã nhận.", "Có", "Có"],
        ["Công nhân ảo", "Tự đặt / nhấc thùng và tự bấm ĐỊNH DANH để chạy liên tục.",
         "Có", "Chỉ tự bấm ĐỊNH DANH"],
        ["Nhật ký mô phỏng", "Mọi việc công cụ đã làm, mới nhất ở trên.", "Có", "Có"],
    ], [34, 88, 22, 30])

    s += [CondPageBreak(70 * mm), P("B3. Chạy thử MANUAL (không cần thiết bị)", h2)]
    s += steps([
        "Ô <b>Hệ thống gửi lệnh</b>: nhập Số pallet (vd 2), Thùng/pallet (vd 3) → "
        "<b>Gửi lệnh sản xuất</b>. Màn hình chính hiện danh sách thùng và tự Bắt đầu.",
        "Ô <b>Cân điện tử</b>: bấm <b>Đặt thùng lên cân</b> → xem màn hình chính cân – in – đọc → "
        "<b>OK</b>. Bấm <b>Nhấc thùng ra</b>. Lặp lại cho từng thùng.",
        "Đủ thùng: bấm <b>Định danh</b> trên màn hình chính. Ô <b>Server nhận pallet</b> hiện bản "
        "tin pallet vừa gửi.",
        "Thử lỗi: <i>Đặt thùng SAI khối lượng</i>, chọn đầu đọc <i>Luôn đọc sai</i>, tích "
        "<i>Giả lập in lỗi</i>, bỏ chọn <i>Cân đang bật</i>, hoặc chọn server <i>500 lỗi</i> – "
        "màn hình chính phải báo đúng như bảng A4.",
        "Chạy liên tục: tích <b>Công nhân ảo</b> → công cụ tự đặt / nhấc thùng và bấm ĐỊNH DANH.",
    ])

    s += [CondPageBreak(70 * mm), P("B4. Chạy thử HYBRID (thiết bị thật tại bàn)", h2)]
    s += steps([
        "Kiểm tra trên màn hình chính: PRINTER, SCALE, BARCODE (và PLC) đều xanh – đây là thiết "
        "bị thật. Công cụ mô phỏng hiện dải xanh dương <b>CHẾ ĐỘ HYBRID</b>, 4 ô thiết bị giả bị mờ.",
        "Ô <b>Hệ thống gửi lệnh</b>: gửi một lệnh nhỏ (vd 1 pallet × 3 thùng).",
        "Thao tác như sản xuất thật (mục A3): đặt thùng thật lên cân, máy in tem thật, dán tem, "
        "đầu đọc thật đọc lại, đèn tháp thật đổi màu.",
        "Đủ thùng: bấm <b>Định danh</b>. Pallet được gửi tới "
        "<b>server giả</b> (ô Server nhận pallet) – không có gì lên WMS thật.",
        "Muốn thử server lỗi: chọn <i>500 lỗi</i> trong ô Server nhận pallet trước khi bấm "
        "Định danh; chỉ báo RCS phải đỏ và máy tự gửi lại.",
    ])

    s += [CondPageBreak(60 * mm), P("B5. Lưu ý", h2)]
    s += bullets([
        "Dữ liệu chạy thử nằm riêng, không ảnh hưởng lịch sử sản xuất.",
        "Tem in ra trong HYBRID là tem thử – thu hồi, không dán lên hàng xuất kho.",
        "Lệnh gửi từ công cụ mô phỏng có mã dạng <b>T-SIM-xxxxx</b>, pallet <b>PLxxxxxxx</b>.",
    ])

    s += [P("B6. Kết thúc chạy thử – trở về sản xuất (bắt buộc)", h2)]
    s += steps([
        "Trên màn hình chính bấm <b>■ Dừng</b>.",
        "<b>Đóng hẳn cửa sổ đen của \u201cChạy mô phỏng\u201d</b> (bấm X). Đóng tab trình duyệt "
        "công cụ mô phỏng.",
        "Thẻ <b>Cài đặt</b> → <b>Chuyển AUTO</b> → Yes.",
        "Kiểm tra: dải vàng trên cùng biến mất, thanh đầu ghi <b>AUTO</b>, các chỉ báo xanh.",
    ])
    s += box(["Nếu báo <b>CÔNG CỤ MÔ PHỎNG CHƯA ĐÓNG</b>: còn cửa sổ đen \u201cChạy mô phỏng\u201d mở ở "
              "đâu đó (kiểm tra thanh Taskbar). Đóng nó, chờ vài giây rồi bấm Chuyển AUTO lại."])

    # ------------------------------------------------------------------ PHẦN C
    s += [CondPageBreak(70 * mm)]
    s += section("PHẦN C – KHI CẦN HỖ TRỢ", MUTED)
    s += [P("Gửi cho kỹ thuật phần mềm:")]
    s += bullets([
        "Ảnh chụp màn hình lúc lỗi (thấy cả dòng thông báo và thanh chỉ báo).",
        "Thời điểm xảy ra lỗi (giờ:phút).",
        "Thư mục <b>logs</b> trong thư mục phần mềm (mỗi ngày một file). Có thể xem nhanh ở thẻ "
        "<b>Lịch sử Log</b>.",
        "Chế độ đang chạy (AUTO / MANUAL / HYBRID) – ghi ở góc đồng hồ trên thanh đầu.",
    ])
    return s


def main():
    doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm,
                            title="Hướng dẫn vận hành G8 ID", author="G8 ID",
                            subject="Chạy phần mềm và Chạy mô phỏng")
    doc.build(build(), onFirstPage=on_page, onLaterPages=on_page)
    print(OUT)


if __name__ == "__main__":
    main()
