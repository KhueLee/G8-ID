"""Thiết bị tại trạm. AUTO/HYBRID = thiết bị thật (driver cũ), MANUAL = nối tới công cụ mô phỏng."""
import logging

log = logging.getLogger("device")

# Nút vật lý trên PLC, như TForm.timerPLCButtonScan_Tick của VTP_Induction.exe (quét 200 ms).
PLC_BUTTONS = {"start": "M20", "stop": "M22", "identify": "M21"}


class ButtonEdges:
    """Bắt sườn lên (0 -> 1) của các nút PLC: giữ nút không kích lặp. Lần đọc đầu sau khi nối
    (hoặc sau reset) chỉ ghi nhận mức hiện tại, không kích - bit đang sẵn 1 không tự Bắt đầu."""

    def __init__(self):
        self.prev = None

    def reset(self):
        self.prev = None

    def feed(self, levels):
        """levels: {tên nút: bool}. Trả danh sách nút vừa được nhấn."""
        prev, self.prev = self.prev, dict(levels)
        if prev is None:
            return []
        return [n for n, v in levels.items() if v and not prev.get(n)]


class DeviceSet:
    def __init__(self, scale, barcode, printer, plc):
        self.scale, self.barcode, self.printer, self.plc = scale, barcode, printer, plc
        self.notes = {}          # thiết bị -> lý do tự dò cổng không ra (hiện thay chi tiết lỗi)

    def all(self):
        return [self.scale, self.barcode, self.printer, self.plc]

    def start(self):
        for d in self.all():
            d.start()

    def stop(self):
        """Đóng sạch mọi cổng. Mỗi thiết bị đóng riêng, lỗi cái này không chặn cái kia."""
        for d in self.all():
            try:
                d.stop()
            except Exception:
                log.exception("Lỗi khi đóng %s", type(d).__name__)

    def status(self):
        st = {"plc": self.plc.status(), "printer": self.printer.status(),
              "scale": self.scale.status(), "barcode": self.barcode.status()}
        for d, note in self.notes.items():
            if not st[d]["ok"]:
                st[d] = dict(st[d], detail="Tự dò: " + note)
        return st


def build(cfg, manual):
    if manual:
        from . import sim
        base = "http://%s:%s" % ("127.0.0.1", cfg["simulator"]["port"])
        return DeviceSet(sim.SimScale(base), sim.SimBarcode(base), sim.SimPrinter(base),
                         sim.SimPlc(base))
    from .barcode import SerialBarcode
    from .plc_mx import MxPlc
    from .printer_godex import GodexPrinter
    from .scale import SerialScale
    from ..config import com_ports
    d = cfg["devices"]
    raw = bool(cfg["log"].get("raw_device"))
    # Cổng của cân / đầu đọc / máy in: PLC không bao giờ khởi động lại cáp trùng các cổng này.
    others = lambda: [p for k, p in com_ports(d).items() if k != "plc"]
    return DeviceSet(SerialScale(d["scale"], raw), SerialBarcode(d["barcode"], raw),
                     GodexPrinter(d["printer"]), MxPlc(d["plc"], others))
