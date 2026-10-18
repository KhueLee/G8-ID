"""Thiết bị tại trạm. AUTO/HYBRID = thiết bị thật (driver cũ), MANUAL = nối tới công cụ mô phỏng."""
import logging

log = logging.getLogger("device")


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
    d = cfg["devices"]
    raw = bool(cfg["log"].get("raw_device"))
    return DeviceSet(SerialScale(d["scale"], raw), SerialBarcode(d["barcode"], raw),
                     GodexPrinter(d["printer"]), MxPlc(d["plc"]))
