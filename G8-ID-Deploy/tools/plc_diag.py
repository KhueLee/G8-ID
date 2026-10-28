"""Chẩn đoán kết nối PLC (cáp USB-SERIAL CH340 + MX Component) - kiem_tra_plc.bat.

Chạy khi PLC báo lỗi (0x01808009, 0x0180800C, 0x01808201...). Tự làm theo thứ tự:
  1. Kiểm tra trước: quyền Admin, G8 ID có đang chạy không, MX Component, tiết kiệm điện USB.
  2. Nhận diện cổng: cáp CH340 đang ở COM mấy, trạng thái / driver / cổng USB vật lý, số bản ghi
     CH340 cũ (mỗi bản ghi giữ chỗ một số COM), tên thiết bị nhân, cổng COM ghi trong MX Component.
  3. Test case:
       T1 mở cổng thô (pyserial) ở các tốc độ: phân biệt "bị chiếm" / "không có" / "kẹt DCB"
       T2 cổng bị chiếm thì tìm tiến trình giữ cổng (handle64.exe nếu có, không thì đoán theo tên)
       T3 MX Component Open + đọc M10 và các bit nút
       T4 chạy bền: đọc nút mỗi 200 ms như G8 ID trong N giây (mặc định 120 s)
       T5 khi T3/T4 lỗi: thử lại cổng thô ngay để biết cổng bị chiếm hay CH340 kẹt
       T6 tắt / bật lại CH340 (giống rút cắm cáp, cần Admin) rồi thử lại
       T7 sự kiện Windows (Kernel-PnP, UserPnp) của CH340 trong 24 giờ và trong lúc test
  4. Kết luận + việc cần làm, ghi logs\\kiem_tra_plc-YYYYMMDD-HHMMSS.txt để gửi người hỗ trợ.

Tham số: --giay N (thời gian chạy bền, 0 = bỏ T4), --khong-reset (bỏ T6).
Phải THOÁT G8 ID trước: G8 ID đang giữ cổng thì chỉ làm được phần kiểm tra không mở cổng.
"""
import argparse
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CH340_IDS = ("USB\\VID_1A86&PID_7523", "USB\\VID_1A86&PID_5523", "USB\\VID_4348&PID_5523")
BAUDS = (9600, 19200, 38400, 57600, 115200)
# Tiến trình hay giữ cổng COM của PLC khi không có handle64.exe để hỏi thẳng Windows.
SUSPECTS = {
    "actutltype64.exe": "MX Component (G8 ID / chương trình khác đang Open PLC, hoặc còn sót sau khi tắt ngang)",
    "actutltype.exe": "MX Component 32-bit",
    "commsetting.exe": "Communication Settings Utility",
    "gd2.exe": "GX Works2",
    "gxw3.exe": "GX Works3",
    "gppw.exe": "GX Developer",
    "putty.exe": "PuTTY", "teraterm.exe": "Tera Term", "ttermpro.exe": "Tera Term",
    "hterm.exe": "HTerm", "realterm.exe": "RealTerm",
    "vtp_induction.exe": "bản WinForms cũ (VTP_Induction)",
}

lines = []
findings = []          # (mức, nội dung, việc cần làm)


def out(level, text):
    line = "[%-8s] %s" % (level, text) if level else text
    lines.append(line)
    print(line, flush=True)


def head(title):
    out("", "")
    out("", "== %s ==" % title)


def finding(level, text, action=""):
    findings.append((level, text, action))


def ps(script, timeout=60):
    """Chạy PowerShell, trả JSON đã giải mã (script phải in ConvertTo-Json) hoặc None."""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                            "[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + script],
                           capture_output=True, timeout=timeout)
        txt = r.stdout.decode("utf-8", "ignore").strip()
        if not txt:
            return None
        data = json.loads(txt)
        return data
    except Exception as e:
        out("INFO", "PowerShell lỗi: %s" % e)
        return None


def as_list(v):
    return [] if v is None else (v if isinstance(v, list) else [v])


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def port_busy(port):
    import socket
    s = socket.socket()
    s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", int(port))) == 0
    finally:
        s.close()


# ---- 2. nhận diện cổng ----------------------------------------------------------
_PS_CH340 = r"""
$ids = @('USB\VID_1A86&PID_7523*','USB\VID_1A86&PID_5523*','USB\VID_4348&PID_5523*')
$all = @(Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object { $i = $_.InstanceId; ($ids | Where-Object { $i -like $_ }).Count -gt 0 })
$res = foreach ($d in $all) {
  $p = @{}
  foreach ($k in 'DEVPKEY_Device_DriverVersion','DEVPKEY_Device_LocationInfo','DEVPKEY_Device_Parent','DEVPKEY_Device_ProblemCode') {
    try { $p[$k] = (Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName $k -ErrorAction Stop).Data } catch { $p[$k] = $null }
  }
  [pscustomobject]@{ id = $d.InstanceId; name = $d.FriendlyName; status = "$($d.Status)"; present = [bool]$d.Present;
    driver = $p['DEVPKEY_Device_DriverVersion']; location = $p['DEVPKEY_Device_LocationInfo'];
    parent = $p['DEVPKEY_Device_Parent']; problem = $p['DEVPKEY_Device_ProblemCode'] }
}
@($res) | ConvertTo-Json -Depth 3
"""


def ch340_devices():
    devs = as_list(ps(_PS_CH340))
    for d in devs:
        m = re.search(r"\((COM\d+)\)", d.get("name") or "")
        d["com"] = m.group(1).upper() if m else ""
    return devs


def serialcomm():
    """{COMn: tên thiết bị nhân} từ HKLM\\HARDWARE\\DEVICEMAP\\SERIALCOMM."""
    import winreg
    res = {}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM") as k:
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(k, i)
                except OSError:
                    break
                res[str(val).upper()] = name
                i += 1
    except OSError:
        pass
    return res


def mx_station_port(station):
    """Cổng COM của Logical Station trong registry MX Component 5. Trả (số COM, khoá) hoặc (None, "").

    Communication Settings Utility ghi ở SWnD5-ACT\\COMMUTL\\LogicalStNo_NNNN\\<kiểu nối>\\PortNumber
    (đã thấy ở trạm ST01: ...\\LogicalStNo_0000\\STECMOPEN\\PortNumber = 12).
    """
    import winreg
    base = r"Software\MITSUBISHI\SWnD5-ACT\COMMUTL\LogicalStNo_%04d" % int(station)

    def walk(root, path, view, depth):
        try:
            k = winreg.OpenKey(root, path, 0, winreg.KEY_READ | view)
        except OSError:
            return None
        with k:
            try:
                val = winreg.QueryValueEx(k, "PortNumber")[0]
                if isinstance(val, int) and val > 0:
                    return val, path
            except OSError:
                pass
            i = 0
            while depth < 3:
                try:
                    sub = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                hit = walk(root, path + "\\" + sub, view, depth + 1)
                if hit:
                    return hit
        return None

    for root, rname in ((winreg.HKEY_LOCAL_MACHINE, "HKLM"), (winreg.HKEY_CURRENT_USER, "HKCU")):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            hit = walk(root, base, view, 0)
            if hit:
                return hit[0], rname + "\\" + hit[1]
    return None, ""


# ---- test cổng thô ---------------------------------------------------------------
def classify_serial_error(e):
    """Lỗi pyserial -> (loại, mô tả). loại: busy | missing | dcb | other."""
    msg = str(e)
    m = re.search(r"OSError\((\d+),[^,]*,\s*None,\s*(\d+)\)|PermissionError\((\d+),[^,]*,\s*None,\s*(\d+)\)"
                  r"|FileNotFoundError\((\d+),[^,]*,\s*None,\s*(\d+)\)", msg)
    win = None
    if m:
        nums = [g for g in m.groups() if g]
        win = int(nums[-1]) if nums else None
    low = msg.lower()
    if win == 5 or "access is denied" in low or "permissionerror" in low:
        return "busy", "cổng đang bị tiến trình khác giữ (Access denied)"
    if win == 2 or "filenotfounderror" in low or "cannot find the file" in low:
        return "missing", "cổng không tồn tại"
    if "cannot configure port" in low or win in (22, 31, 87, 121, 1167, 995):
        return "dcb", "mở được cổng nhưng không đặt được thông số (DCB) - CH340 / driver kẹt"
    return "other", msg


def raw_test(port, bauds=BAUDS):
    """Mở / đóng thử cổng ở từng tốc độ. Trả {baud: (loại, mô tả)}; loại 'ok' = được."""
    import serial
    res = {}
    for b in bauds:
        try:
            s = serial.Serial(port, b, timeout=0.2)
            s.close()
            res[b] = ("ok", "mở / đóng được")
        except Exception as e:
            res[b] = classify_serial_error(e)
            if res[b][0] in ("busy", "missing"):
                break           # các tốc độ khác cũng vậy
    return res


def summarize_raw(res):
    kinds = {k for k, _ in res.values()}
    if kinds == {"ok"}:
        return "ok"
    for k in ("busy", "missing", "dcb", "other"):
        if k in kinds:
            return k
    return "ok"


def log_raw(port, res, prefix="T1"):
    for b, (k, msg) in res.items():
        out("OK" if k == "ok" else "LỖI", "%s %s @%d: %s" % (prefix, port, b, msg))


def find_owner(kernel_name):
    """Tiến trình đang giữ thiết bị. Ưu tiên handle64.exe (Sysinternals), không có thì đoán.

    Trả (cách, [tiến trình], kết quả thô của handle64 hoặc ""). handle64 không thấy ai (kể cả
    System) mà cổng vẫn Access denied = driver CH340 kẹt ở trạng thái "đang mở".
    """
    exe = None
    for c in (os.path.join(ROOT, "tools", "handle64.exe"), os.path.join(ROOT, "tools", "handle.exe")):
        if os.path.exists(c):
            exe = c
            break
    exe = exe or shutil.which("handle64.exe") or shutil.which("handle.exe")
    owners = []
    if exe and kernel_name:
        try:
            r = subprocess.run([exe, "-accepteula", "-nobanner", "-a", kernel_name.split("\\")[-1]],
                               capture_output=True, text=True, errors="ignore", timeout=60)
            for ln in r.stdout.splitlines():
                m = re.match(r"\s*(\S+)\s+pid:\s*(\d+)", ln)
                if m:
                    owners.append("%s (pid %s)" % (m.group(1), m.group(2)))
            raw = (r.stdout + r.stderr).strip() or "(không in gì, mã thoát %s)" % r.returncode
            return "handle", sorted(set(owners)), raw
        except Exception as e:
            out("INFO", "Chạy %s lỗi: %s" % (exe, e))
    try:
        r = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True,
                           errors="ignore", timeout=30)
        for ln in r.stdout.splitlines():
            parts = [p.strip('"') for p in ln.split('","')]
            if parts and parts[0].lower() in SUSPECTS:
                owners.append("%s (pid %s) - %s" % (parts[0], parts[1] if len(parts) > 1 else "?",
                                                    SUSPECTS[parts[0].lower()]))
    except Exception:
        pass
    return "guess", owners, ""


def log_owner(port, how, owners, raw, prefix="T2"):
    out("LỖI" if owners else "INFO", "%s tiến trình giữ %s (%s): %s" % (
        prefix, port, "handle64" if how == "handle" else
        "đoán theo tên, chép handle64.exe vào tools\\ để chắc chắn", ", ".join(owners) or "không thấy ai"))
    for ln in raw.splitlines()[:15]:
        out("", "           handle64> " + ln)


# ---- MX Component ---------------------------------------------------------------
class MxSession:
    """Chạy MX Component trong một luồng STA riêng (như G8 ID), trả kết quả từng bước."""

    def __init__(self, cfg):
        from app.devices.plc_mx import MxPlc
        self.drv = MxPlc(dict(cfg, keepalive_s=0))

    def run(self, seconds, poll_s, buttons, on_progress=None):
        box = {}
        t = threading.Thread(target=self._run, args=(seconds, poll_s, buttons, box, on_progress),
                             name="plc-diag", daemon=True)
        t.start()
        t.join(seconds + 90)
        if t.is_alive():
            box.setdefault("error", "MX Component treo, không trả lời sau %d s" % (seconds + 90))
            box["hung"] = True
        return box

    def _run(self, seconds, poll_s, buttons, box, on_progress):
        import pythoncom
        from app.devices.plc_mx import MxError, describe
        pythoncom.CoInitialize()
        plc = None
        try:
            t0 = time.time()
            try:
                plc, box["via"] = self.drv._open()
            except MxError as e:
                box.update(stage="open", rc=e.rc, error=str(e))
                return
            except Exception as e:
                box.update(stage="open", error=str(e))
                return
            box["open_ms"] = int((time.time() - t0) * 1000)
            try:
                box["m10"] = self.drv._get(plc, "M10")
                box["buttons"] = {n: self.drv._get(plc, d) for n, d in buttons.items()}
            except MxError as e:
                box.update(stage="read", rc=e.rc, error=str(e))
                return
            except Exception as e:
                box.update(stage="read", error=str(e))
                return
            if seconds <= 0:
                return
            start = time.time()
            n, worst, total, last_note = 0, 0.0, 0.0, start
            devs = list(buttons.values()) or ["M10"]
            while time.time() - start < seconds:
                for d in devs:
                    t1 = time.time()
                    try:
                        self.drv._get(plc, d)
                    except MxError as e:
                        box.update(stage="soak", rc=e.rc, error=str(e), after_s=round(time.time() - start, 1))
                        return
                    except Exception as e:
                        box.update(stage="soak", error=str(e), after_s=round(time.time() - start, 1))
                        return
                    dt = time.time() - t1
                    n, total, worst = n + 1, total + dt, max(worst, dt)
                box.update(reads=n, avg_ms=round(total / n * 1000, 1), max_ms=round(worst * 1000, 1))
                if on_progress and time.time() - last_note >= 15:
                    last_note = time.time()
                    on_progress(int(time.time() - start), n)
                time.sleep(poll_s)
            box["soak_ok_s"] = seconds
        finally:
            if plc is not None:
                try:
                    plc.Close()
                except Exception:
                    pass
            plc = None
            box["describe"] = describe(box["rc"]) if "rc" in box else ""
            pythoncom.CoUninitialize()


# ---- sự kiện Windows -------------------------------------------------------------
def pnp_events(since_epoch):
    script = r"""
$t = [DateTime]::FromFileTimeUtc([long]%d).ToLocalTime()
$ev = @()
$ev += Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Kernel-PnP/Configuration'; StartTime=$t} -ErrorAction SilentlyContinue
$ev += Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-UserPnp'; StartTime=$t} -ErrorAction SilentlyContinue
@($ev | Where-Object { $_.Message -match 'VID_1A86|VID_4348|CH340|CH341' } | Sort-Object TimeCreated |
  ForEach-Object { [pscustomobject]@{ t = $_.TimeCreated.ToString('dd/MM HH:mm:ss'); id = $_.Id;
    lvl = $_.LevelDisplayName; msg = (($_.Message -split "`r?`n")[0]) } }) | ConvertTo-Json -Depth 3
""" % int((since_epoch + 11644473600) * 10000000)
    return as_list(ps(script, timeout=120))


PNP_MEANING = {400: "cấu hình thiết bị (Windows nhận cáp)", 410: "thiết bị khởi động",
               411: "LỖI khởi động thiết bị", 420: "thiết bị bị xoá / rút ra",
               430: "cần cài đặt thêm", 441: "LỖI thiết bị", 20001: "cài driver",
               20003: "thêm dịch vụ driver"}


def log_events(evs, label):
    if not evs:
        out("INFO", "%s: không có sự kiện CH340 nào" % label)
        return
    out("INFO", "%s: %d sự kiện CH340" % (label, len(evs)))
    for e in evs[-40:]:
        out("WARN" if e.get("lvl") not in ("Information", "Thông tin") else "INFO",
            "  %s  %-5s %s | %s" % (e["t"], e["id"], PNP_MEANING.get(e["id"], ""), (e.get("msg") or "")[:110]))


# ---- tiết kiệm điện USB ----------------------------------------------------------
def usb_selective_suspend():
    """(AC, DC) của USB selective suspend trong gói điện hiện tại: 1 = bật, 0 = tắt."""
    try:
        r = subprocess.run(["powercfg", "/q", "SCHEME_CURRENT", "2a737441-1930-4402-8d77-b2bebba308a3",
                            "48e6b7a6-50f5-4782-a5d4-53bb8f07e226"],
                           capture_output=True, text=True, errors="ignore", timeout=20)
        vals = re.findall(r":\s*0x([0-9a-fA-F]{8})\s*$", r.stdout, re.M)
        if len(vals) >= 2:
            return int(vals[-2], 16), int(vals[-1], 16)
    except Exception:
        pass
    return None


def power_off_allowed(instance_ids):
    """Thiết bị nào (CH340 và hub phía trên) đang cho Windows tắt để tiết kiệm điện."""
    if not instance_ids:
        return []
    arr = ",".join("'%s'" % i.replace("'", "''").upper() for i in instance_ids)
    script = r"""
$want = @(%s)
@(Get-CimInstance -Namespace root\wmi -ClassName MSPower_DeviceEnable -ErrorAction SilentlyContinue |
  Where-Object { $n = $_.InstanceName.ToUpper(); $_.Enable -and ($want | Where-Object { $n.StartsWith($_) }).Count -gt 0 } |
  ForEach-Object { $_.InstanceName }) | ConvertTo-Json
""" % arr
    return as_list(ps(script))


def parents_chain(dev_id, depth=4):
    chain, cur = [], dev_id
    for _ in range(depth):
        p = ps("try { (Get-PnpDeviceProperty -InstanceId '%s' -KeyName DEVPKEY_Device_Parent -ErrorAction Stop).Data "
               "| ConvertTo-Json } catch { }" % cur.replace("'", "''"))
        if not p or not str(p).upper().startswith("USB\\"):
            break
        chain.append(str(p))
        cur = str(p)
    return chain


def restart_device(dev_id):
    script = ("Disable-PnpDevice -InstanceId '%s' -Confirm:$false -ErrorAction Stop; Start-Sleep 2;"
              "Enable-PnpDevice -InstanceId '%s' -Confirm:$false -ErrorAction Stop; 'ok' | ConvertTo-Json"
              % (dev_id.replace("'", "''"), dev_id.replace("'", "''")))
    return ps(script, timeout=60) == "ok"


# ---- chính -----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Chẩn đoán kết nối PLC (CH340 + MX Component)")
    ap.add_argument("--giay", type=int, default=120, help="số giây chạy bền T4 (0 = bỏ)")
    ap.add_argument("--khong-reset", action="store_true", help="không tắt / bật lại CH340 (T6)")
    args = ap.parse_args()
    t_start = time.time()

    from app import config
    from app.devices import PLC_BUTTONS
    cfg = config.load()
    pcfg = cfg["devices"]["plc"]
    buttons = {k: str(v).strip() for k, v in (pcfg.get("buttons", PLC_BUTTONS) or {}).items()
               if str(v or "").strip()}
    poll_s = max(0.05, float(pcfg.get("button_poll_ms", 200) or 200) / 1000.0)

    out("INFO", "G8 ID - chẩn đoán PLC lúc %s | trạm %s | Logical Station %s"
        % (time.strftime("%d/%m/%Y %H:%M:%S"), cfg["station_id"], pcfg.get("station_number", 0)))

    # 1. Kiểm tra trước
    head("1. KIỂM TRA TRƯỚC")
    admin = is_admin()
    out("OK" if admin else "CẢNH BÁO", "Quyền Administrator: %s" % (
        "có" if admin else "KHÔNG - bỏ qua T6 (tắt / bật lại CH340); nên chuột phải -> Run as administrator"))
    running = port_busy(cfg["ui"]["port"])
    out("LỖI" if running else "OK", "G8 ID %s (cổng %s)" % ("ĐANG CHẠY" if running else "không chạy",
                                                             cfg["ui"]["port"]))
    if running:
        finding("LỖI", "G8 ID đang chạy nên không test được cổng / MX Component",
                "Thoát G8 ID (thẻ Cài đặt -> Thoát) rồi chạy lại kiem_tra_plc.bat")
    if not pcfg.get("enabled", True):
        out("CẢNH BÁO", "PLC đang TẮT trong cấu hình (devices.plc.enabled = false)")
    from app.devices.plc_mx import _mx5_server_path
    mx_exe = _mx5_server_path()
    out("OK" if mx_exe else "LỖI", "MX Component 5 (ActUtlType64): %s" % (mx_exe or "CHƯA CÀI"))
    if not mx_exe:
        finding("LỖI", "Chưa cài MX Component 5", "Cài MX Component 5, tạo Logical Station")

    ss = usb_selective_suspend()
    if ss is None:
        out("INFO", "Không đọc được USB selective suspend")
    else:
        on = ss[0] or ss[1]
        out("CẢNH BÁO" if on else "OK", "USB selective suspend: cắm điện=%s, pin=%s" % (
            "BẬT" if ss[0] else "tắt", "BẬT" if ss[1] else "tắt"))
        if on:
            finding("CẢNH BÁO", "USB selective suspend đang bật - Windows có thể ngắt cáp CH340",
                    "Control Panel -> Power Options -> Change plan settings -> Advanced -> USB settings "
                    "-> USB selective suspend = Disabled")

    # 2. Nhận diện cổng
    head("2. NHẬN DIỆN CỔNG")
    devs = ch340_devices()
    present = [d for d in devs if d.get("present")]
    ghosts = [d for d in devs if not d.get("present")]
    for d in present:
        out("OK" if d["status"] == "OK" else "LỖI",
            "CH340 %s | trạng thái %s%s | driver %s | vị trí USB %s" % (
                d["com"] or "?", d["status"],
                " (mã lỗi %s)" % d["problem"] if d.get("problem") else "",
                d.get("driver") or "?", d.get("location") or "?"))
        out("INFO", "  %s" % d["id"])
    if ghosts:
        out("CẢNH BÁO" if len(ghosts) >= 2 else "INFO",
            "%d bản ghi CH340 cũ không còn cắm (%s) - mỗi lần cáp bị nhận lại Windows cấp số COM mới"
            % (len(ghosts), ", ".join(d["com"] or "?" for d in ghosts)))
        if len(ghosts) >= 2:
            finding("CẢNH BÁO", "Cáp CH340 đã bị Windows nhận lại nhiều lần (%d bản ghi cũ: %s)"
                    % (len(ghosts), ", ".join(d["com"] or "?" for d in ghosts)),
                    "Cắm cáp vào đúng một cổng USB cố định; ghim số COM ở Device Manager -> Port "
                    "Settings -> Advanced, và để Logical Station trùng số đó")

    cfg_port = str(pcfg.get("com_port") or "").upper()
    if not present:
        out("LỖI", "Không thấy cáp CH340 nào đang cắm")
        finding("LỖI", "Windows không thấy cáp PLC (CH340)",
                "Kiểm tra cáp USB, cắm thẳng cổng sau máy; nếu Device Manager có dấu chấm than thì "
                "chạy tools\\reinstall_ch340.bat")
    plc_dev = None
    if len(present) == 1:
        plc_dev = present[0]
    elif present:
        plc_dev = next((d for d in present if d["com"] == cfg_port), None)
        out("CẢNH BÁO", "Có %d cáp CH340 đang cắm (%s) - chọn %s theo config.json"
            % (len(present), ", ".join(d["com"] for d in present), plc_dev["com"] if plc_dev else "?"))
        plc_dev = plc_dev or present[0]
    port = plc_dev["com"] if plc_dev else ""
    if port:
        out("INFO", "Cổng PLC dùng để test: %s (config.json ghi %s)" % (port, cfg_port or "trống"))
    kernel = serialcomm().get(port, "")
    out("INFO", "Tên thiết bị nhân của %s: %s" % (port or "?", kernel or "không thấy trong SERIALCOMM"))

    station = pcfg.get("station_number", 0)
    st_num, st_key = mx_station_port(station)
    if st_num is None:
        out("INFO", "Không đọc được cổng COM của Logical Station %s từ registry - xem tay trong "
                    "Communication Settings Utility, phải là %s" % (station, port or "cổng CH340"))
    else:
        st_port = "COM%d" % st_num
        same = not port or st_port == port
        out("OK" if same else "LỖI", "Logical Station %s trỏ %s%s (%s)" % (
            station, st_port, "" if not port else " - khớp cáp CH340" if same else
            " - KHÁC cáp CH340 đang ở %s" % port, st_key))
        if not same:
            finding("LỖI", "Logical Station %s trỏ %s nhưng cáp PLC đang ở %s" % (station, st_port, port),
                    "Communication Settings Utility (Run as administrator) -> Logical Station %s -> "
                    "COM port = %s, Connection test; hoặc ghim CH340 về %s ở Device Manager"
                    % (station, port, st_port))

    if plc_dev and plc_dev["status"] == "OK":
        ids = [plc_dev["id"]] + parents_chain(plc_dev["id"])
        allowed = power_off_allowed(ids)
        out("CẢNH BÁO" if allowed else "OK", "Cho phép Windows tắt thiết bị để tiết kiệm điện: %s"
            % (", ".join(allowed) if allowed else "không (CH340 và hub phía trên)"))
        if allowed:
            finding("CẢNH BÁO", "Windows được phép tắt CH340 / USB hub để tiết kiệm điện",
                    "Device Manager -> từng thiết bị trên -> Power Management -> bỏ tick "
                    "'Allow the computer to turn off this device'")

    # 3. Test case
    head("3. TEST CASE")
    mx_box = {}
    if running:
        out("INFO", "Bỏ qua T1-T6 vì G8 ID đang chạy")
    elif not port:
        out("INFO", "Bỏ qua T1-T6 vì không có cổng CH340")
    else:
        raw = raw_test(port)
        log_raw(port, raw)
        kind = summarize_raw(raw)
        if kind == "busy":
            how, owners, raw_out = find_owner(kernel)
            log_owner(port, how, owners, raw_out)
            if owners:
                finding("LỖI", "Cổng %s đang bị tiến trình khác giữ: %s" % (port, ", ".join(owners)),
                        "Đóng chương trình đó (còn sót ActUtlType64.exe thì: taskkill /f /im "
                        "ActUtlType64.exe) rồi chạy lại")
            else:
                # Không ai giữ handle mà vẫn Access denied: driver CH340 kẹt "đang mở" sau lần treo trước.
                finding("LỖI", "%s báo bị chiếm nhưng không tiến trình nào giữ cổng%s - driver CH340 kẹt "
                        "ở trạng thái đang mở (thường sau một lần chip treo giữa chừng)"
                        % (port, " (handle64 xác nhận)" if how == "handle" else ""),
                        "Tắt / bật lại CH340: tools\\restart_ch340.bat (Admin) hoặc rút cắm cáp. Bị lặp lại "
                        "sau vài phút chạy = chip / cáp CH340 treo -> thay cáp FTDI / Mitsubishi chính hãng")
                new_port = restart_retest(plc_dev, port, admin, args)
                if new_port:
                    port, kernel, kind = new_port, serialcomm().get(new_port, ""), "ok"
        elif kind == "dcb":
            finding("LỖI", "%s mở được nhưng không đặt được thông số (DCB) ngay từ đầu - CH340 / driver kẹt"
                    % port, "Rút cáp 5 s cắm lại đúng cổng cũ; không được thì tools\\reinstall_ch340.bat")
        elif kind == "ok":
            out("OK", "T2 không có tiến trình nào giữ %s" % port)

        if kind == "ok" and mx_exe:
            out("INFO", "T3/T4 MX Component Open + đọc %s, chạy bền %d s (mỗi %d ms)..."
                % (", ".join(buttons.values()) or "M10", args.giay, int(poll_s * 1000)))
            mx_box = MxSession(pcfg).run(args.giay, poll_s, buttons,
                                         lambda s, n: out("INFO", "  ... %d s, %d lần đọc OK" % (s, n)))
            if "error" not in mx_box:
                out("OK", "T3 Open OK (%s, %d ms), M10=%s, nút %s" % (
                    mx_box.get("via"), mx_box.get("open_ms", 0), mx_box.get("m10"), mx_box.get("buttons")))
                if args.giay:
                    out("OK", "T4 chạy bền %d s: %d lần đọc, trung bình %s ms, lâu nhất %s ms" % (
                        args.giay, mx_box.get("reads", 0), mx_box.get("avg_ms"), mx_box.get("max_ms")))
                    if (mx_box.get("max_ms") or 0) > 1000:
                        finding("CẢNH BÁO", "Có lần PLC trả lời chậm %s ms" % mx_box["max_ms"],
                                "Kiểm tra cáp / nhiễu trên đường RS-232/422")
            else:
                stage = {"open": "T3 Open", "read": "T3 đọc", "soak": "T4 chạy bền"}.get(mx_box.get("stage"), "MX")
                out("LỖI", "%s lỗi%s: %s" % (stage, " sau %s s" % mx_box["after_s"] if "after_s" in mx_box else "",
                                             mx_box["error"]))
                diagnose_mx_failure(mx_box, port, kernel, plc_dev, admin, args, pcfg)
        elif kind == "ok":
            out("INFO", "Bỏ qua T3/T4 vì chưa cài MX Component")

    # T7 sự kiện
    head("4. SỰ KIỆN WINDOWS CỦA CH340 (T7)")
    log_events(pnp_events(t_start - 86400), "24 giờ qua")
    during = pnp_events(t_start)
    if during and "error" in mx_box:
        finding("LỖI", "Windows ghi nhận CH340 bị ngắt / nhận lại trong lúc test (%d sự kiện)" % len(during),
                "Cáp USB bị mất nguồn hoặc nhiễu: cắm cổng sau, tắt tiết kiệm điện USB, đi dây tránh "
                "động lực, gắn ferrite; vẫn bị thì thay cáp (FTDI / Mitsubishi chính hãng)")

    report(cfg)
    return 1 if any(f[0] == "LỖI" for f in findings) else 0


def diagnose_mx_failure(box, port, kernel, plc_dev, admin, args, pcfg):
    """T5 + T6: MX lỗi -> xem ngay cổng thô để biết bị chiếm hay CH340 kẹt, rồi thử tắt / bật lại."""
    rc = box.get("rc", 0)
    if box.get("hung"):
        finding("LỖI", "MX Component treo không trả lời",
                "taskkill /f /im ActUtlType64.exe; khởi động lại máy nếu vẫn treo")
        return
    if box.get("stage") == "open" and rc == 0xF0000002:
        finding("LỖI", "Không có Logical Station %s" % pcfg.get("station_number", 0),
                "Tạo Logical Station trong Communication Settings Utility (Run as administrator)")
        return
    if rc == 0x0180840B:
        finding("LỖI", "Cổng USB tốt nhưng PLC không trả lời (0x0180840B)",
                "Kiểm tra giắc cắm vào PLC, nguồn PLC, tốc độ / CPU trong Logical Station, nhiễu đường RS-232/422")
        return
    time.sleep(1)
    raw = raw_test(port)
    log_raw(port, raw, "T5")
    kind = summarize_raw(raw)
    soak = box.get("stage") == "soak"
    if kind == "ok":
        if box.get("stage") == "open" and rc == 0x01808009:
            finding("LỖI", "Cổng %s tốt nhưng MX Component không mở được cổng (0x01808009) - "
                    "Logical Station đang trỏ sai cổng COM" % port,
                    "Communication Settings Utility -> Logical Station %s -> COM port = %s"
                    % (pcfg.get("station_number", 0), port))
        else:
            finding("LỖI", "MX Component lỗi %s nhưng cổng %s vẫn mở được" % (box.get("describe"), port),
                    "Logical Station %s có thể trỏ sai cổng (vd. cổng Bluetooth / Intel AMT) - phải là %s; "
                    "kiểm tra CPU, tốc độ bằng Connection test" % (pcfg.get("station_number", 0), port))
        return
    if kind == "busy":
        how, owners, raw_out = find_owner(kernel)
        log_owner(port, how, owners, raw_out, "T5")
        if owners:
            finding("LỖI", "Sau lỗi MX, cổng %s bị tiến trình khác giữ: %s" % (port, ", ".join(owners)),
                    "Đóng chương trình đó; còn sót ActUtlType64.exe thì taskkill /f /im ActUtlType64.exe")
            return
        finding("LỖI", "CH340 KẸT: %s (%s), sau đó %s báo bị chiếm nhưng không tiến trình nào giữ - "
                "driver kẹt ở trạng thái đang mở" % (
                    "chạy được %s s rồi lỗi" % box.get("after_s") if soak else "Open lỗi",
                    box.get("describe"), port),
                "Chip / driver CH340 bị treo - thường do nhiễu điện hoặc cáp CH340 kém. Đi dây USB tránh "
                "động lực, gắn ferrite, cắm cổng sau; thay cáp FTDI / Mitsubishi chính hãng")
    elif kind == "missing":
        finding("LỖI", "Cổng %s BIẾN MẤT %s - Windows đã ngắt cáp CH340" % (
            port, "sau %s s chạy" % box.get("after_s") if soak else "khi Open"),
            "Nguồn USB / nhiễu: cắm cổng sau máy, tắt tiết kiệm điện USB, đi dây tránh động lực; "
            "vẫn bị thì thay cáp")
    else:
        finding("LỖI", "CH340 KẸT: %s (%s), sau đó cổng mở được nhưng không đặt được thông số (DCB). "
                "Không có tiến trình nào chiếm cổng" % (
                    "chạy được %s s rồi lỗi" % box.get("after_s") if soak else "Open lỗi", box.get("describe")),
                "Chip / driver CH340 bị treo - thường do nhiễu điện hoặc cáp CH340 kém. Đi dây USB tránh "
                "động lực, gắn ferrite, cắm cổng sau; thay cáp FTDI / Mitsubishi chính hãng")

    new_port = restart_retest(plc_dev, port, admin, args)
    if not new_port:
        return
    box2 = MxSession(pcfg).run(0, 0.2, {})
    if "error" in box2:
        out("LỖI", "T6 MX Open sau khi bật lại: %s" % box2["error"])
        finding("LỖI", "Sau khi bật lại CH340, cổng thô tốt nhưng MX vẫn lỗi %s" % box2.get("describe"),
                "Số COM có thể đã đổi (%s) - sửa Logical Station cho đúng" % new_port)
    else:
        out("OK", "T6 sau khi tắt / bật lại CH340: MX Open OK")
        finding("INFO", "Tắt / bật lại CH340 là chữa được tạm thời (không cần cài lại driver)",
                "Khi bị lại: chạy tools\\restart_ch340.bat (Admin) hoặc rút cắm cáp; sửa gốc là nhiễu / cáp")


def restart_retest(plc_dev, port, admin, args):
    """T6: tắt / bật lại CH340 (giống rút cắm cáp) rồi mở thử cổng. Trả cổng mới nếu mở được, không thì ""."""
    if args.khong_reset or not admin or not plc_dev:
        out("INFO", "T6 bỏ qua (%s)" % ("--khong-reset" if args.khong_reset else
                                        "không có quyền Admin" if not admin else "không có thiết bị"))
        return ""
    out("INFO", "T6 tắt / bật lại %s ..." % plc_dev["name"])
    if not restart_device(plc_dev["id"]):
        out("LỖI", "T6 không tắt / bật lại được thiết bị")
        return ""
    time.sleep(5)
    new = next((d for d in ch340_devices() if d["id"] == plc_dev["id"] and d.get("present")), None)
    new_port = new["com"] if new else ""
    if new_port and new_port != port:
        out("CẢNH BÁO", "T6 số COM đổi %s -> %s - sửa Logical Station cho khớp" % (port, new_port))
    if not new_port:
        out("LỖI", "T6 không thấy lại CH340 sau khi bật lại")
        finding("LỖI", "Tắt / bật lại CH340 không nhận lại được", "Rút cáp cắm lại; không được thì reinstall_ch340.bat")
        return ""
    raw = raw_test(new_port)
    log_raw(new_port, raw, "T6")
    if summarize_raw(raw) != "ok":
        finding("LỖI", "Tắt / bật lại CH340 không hết lỗi", "Rút cáp cắm lại; không được thì "
                "tools\\reinstall_ch340.bat; vẫn lỗi thì thay cáp")
        return ""
    out("OK", "T6 sau khi tắt / bật lại, %s mở được" % new_port)
    return new_port


def report(cfg):
    head("KẾT LUẬN")
    order = {"LỖI": 0, "CẢNH BÁO": 1, "INFO": 2}
    if not findings:
        out("OK", "Không thấy lỗi: cáp CH340, cổng COM và MX Component đều chạy được trong lúc test.")
        out("INFO", "Lỗi ở trạm chỉ xuất hiện khi chạy lâu -> chạy lại với --giay 900, hoặc lúc máy "
                    "móc trên dây chuyền đang chạy.")
    for i, (lv, text, act) in enumerate(sorted(findings, key=lambda f: order.get(f[0], 3)), 1):
        out(lv, "%d. %s" % (i, text))
        if act:
            out("", "     -> %s" % act)
    try:
        from app import config
        log_dir = config.path(cfg["log"]["dir"])
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, "kiem_tra_plc-%s.txt" % time.strftime("%Y%m%d-%H%M%S"))
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print("\nĐã ghi báo cáo vào %s" % path)
    except OSError as e:
        print("Không ghi được báo cáo: %s" % e)


if __name__ == "__main__":
    sys.exit(main())
