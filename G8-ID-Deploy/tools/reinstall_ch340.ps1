# Go va cai lai driver CH340 (CH341SER 3.4) cho moi cap USB-SERIAL CH340 dang cam.
# Goi tu reinstall_ch340.bat (quyen Administrator). Dung pnputil cua Windows, khong can bam nut.
# Driver lay tu drivers\CH341SER (giai nen tu drivers\CH34x_Install_Windows_v3_4.EXE).
param([string]$Root)

$inf = Join-Path $Root 'drivers\CH341SER\CH341SER.INF'
$logDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
Start-Transcript -Path (Join-Path $logDir ('reinstall_ch340-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')) | Out-Null

# Dung cac ma trong CH341SER.INF. Khong loc theo VID_1A86 chung: WCH con lam USB hub, card mang.
function Get-Ch340 {
    Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object {
        $_.InstanceId -like 'USB\VID_1A86&PID_7523*' -or $_.InstanceId -like 'USB\VID_1A86&PID_5523*' -or
        $_.InstanceId -like 'USB\VID_4348&PID_5523*' }
}

function Show-Ch340([string]$title) {
    Write-Host ''
    Write-Host "== $title =="
    $d = Get-Ch340 | Where-Object { $_.Present }
    if (-not $d) { Write-Host '(khong thay thiet bi CH340 nao dang cam)'; return }
    $d | Format-Table Status, FriendlyName, InstanceId -AutoSize | Out-String -Width 200 | Write-Host
}

function Invoke-PnpUtil([string[]]$argv) {
    Write-Host ('> pnputil ' + ($argv -join ' '))
    & pnputil.exe @argv | ForEach-Object { Write-Host "    $_" }
    return $LASTEXITCODE
}

try {
    if (-not (Test-Path $inf)) { throw "Khong thay $inf" }

    # G8 ID va MX Component dang giu cong COM thi go driver se treo / khong sach.
    $port = 8600
    try {
        $cfg = Get-Content (Join-Path $Root 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($cfg.ui.port) { $port = [int]$cfg.ui.port }
    } catch { }
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "G8 ID dang chay (cong $port). Hay THOAT G8 ID (the Cai dat -> Thoat) roi chay lai file nay."
    }

    Show-Ch340 'TRUOC KHI GO'
    $devices = @(Get-Ch340)

    # 1. Go driver: xoa moi goi CH341SER trong Driver Store (oemNN.inf), go khoi thiet bi.
    Write-Host ''
    Write-Host '== 1. GO DRIVER CH341SER =='
    $pkgs = @(Get-WindowsDriver -Online -ErrorAction SilentlyContinue |
              Where-Object { $_.OriginalFileName -like '*\ch341ser.inf' })
    if (-not $pkgs) { Write-Host '(Driver Store khong co goi CH341SER nao)' }
    foreach ($p in $pkgs) {
        Write-Host ("Goi {0}  phien ban {1}" -f $p.Driver, $p.Version)
        Invoke-PnpUtil @('/delete-driver', $p.Driver, '/uninstall', '/force') | Out-Null
    }

    # 2. Xoa thiet bi (ke ca ban ghi cu khong con cam) de Windows nhan lai tu dau.
    Write-Host ''
    Write-Host '== 2. XOA THIET BI CH340 =='
    $canRemove = $true
    foreach ($d in $devices) {
        $rc = Invoke-PnpUtil @('/remove-device', $d.InstanceId)
        if ($rc -ne 0) { $canRemove = $false }
    }

    # 3. Cai lai driver tu drivers\CH341SER.
    Write-Host ''
    Write-Host '== 3. CAI DRIVER CH341SER 3.4 =='
    $rc = Invoke-PnpUtil @('/add-driver', $inf, '/install')
    # 0 = OK, 3010 = OK nhung can khoi dong lai, 259 = da them vao Driver Store nhung chua co thiet bi khop
    if ($rc -notin 0, 3010, 259) { throw "Cai driver loi (pnputil ma $rc)" }
    if ($rc -eq 3010) { Write-Host '[!] Windows bao can KHOI DONG LAI MAY de driver co hieu luc.' }

    # 4. Cho Windows do lai phan cung de thiet bi nhan driver moi.
    Write-Host ''
    Write-Host '== 4. DO LAI THIET BI =='
    $rc = Invoke-PnpUtil @('/scan-devices')
    if ($rc -ne 0 -or -not $canRemove) {
        # Windows cu (truoc 10 2004) khong co /scan-devices, /remove-device: tat / bat lai thiet bi.
        foreach ($d in (Get-Ch340 | Where-Object { $_.Present })) {
            Write-Host ('Tat / bat lai: ' + $d.FriendlyName)
            Disable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false -ErrorAction SilentlyContinue
            Start-Sleep 2
            Enable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep 5

    Show-Ch340 'SAU KHI CAI LAI'
    $now = @(Get-Ch340 | Where-Object { $_.Present })
    $bad = @($now | Where-Object { $_.Status -ne 'OK' })
    if ($now.Count -eq 0) {
        Write-Host '[!] Khong thay CH340 nao. Rut ra cam lai cap USB, roi kiem tra Device Manager.'
        exit 1
    }
    if ($bad.Count) {
        Write-Host '[!] Con thiet bi chua OK. Rut ra cam lai cap USB do, hoac khoi dong lai may.'
        exit 1
    }
    Write-Host '[OK] Da go va cai lai driver CH340. Kiem tra so COM o tren khop config.json /'
    Write-Host '     Logical Station cua MX Component, roi mo lai G8 ID (run_app.bat).'
    exit 0
} catch {
    Write-Host ''
    Write-Host ('[LOI] ' + $_)
    exit 1
} finally {
    Stop-Transcript | Out-Null
}
