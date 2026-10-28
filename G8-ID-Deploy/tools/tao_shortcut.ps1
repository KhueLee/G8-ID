# Tao / kiem tra 2 bieu tuong tren Desktop cho ky thuat van hanh (goi tu cai_dat_may_moi.bat, update.bat).
# Chay lai nhieu lan cung khong sao: bieu tuong da co va tro dung thu muc nay thi giu nguyen, thieu
# hoac tro thu muc khac (cai lai o cho khac) thi tao lai. Bieu tuong ten cu "Chạy phần mềm" (truoc
# v2.4.8) tro toi chay_dinh_danh.bat thi xoa, thay bang "Chạy định danh".
# File luu UTF-8 co BOM de PowerShell 5.1 doc dung ten tieng Viet.
# -Desktop: thu muc thay cho Desktop (chi de thu, khong xet Desktop chung cua moi nguoi dung).
param([string]$Root, [string]$Desktop)

$Root = (Resolve-Path $Root).Path
if ($Desktop) {
    $desktop, $public = $Desktop, $null
} else {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $public = [Environment]::GetFolderPath('CommonDesktopDirectory')
}
$shell = New-Object -ComObject WScript.Shell
$links = @(
    @{ Name = 'Chạy định danh'; Bat = 'chay_dinh_danh.bat'; Old = @('Chạy phần mềm') },
    @{ Name = 'Chạy mô phỏng'; Bat = 'chay_mo_phong.bat'; Old = @() }
)

# WScript.Shell khong doc / luu duoc duong dan co dau: chep ra ten tam ASCII de doc dich cua bieu tuong.
function Get-LinkTarget([string]$path) {
    $tmp = Join-Path $env:TEMP ('g8id_chk_' + [guid]::NewGuid().ToString('N') + '.lnk')
    try {
        Copy-Item -LiteralPath $path -Destination $tmp -Force
        return $shell.CreateShortcut($tmp).TargetPath
    } catch {
        return ''
    } finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
}

function Find-Link([string]$name) {
    foreach ($dir in @($desktop, $public)) {
        if (-not $dir) { continue }
        $p = Join-Path $dir ($name + '.lnk')
        if (Test-Path -LiteralPath $p) { return $p }
    }
    return $null
}

$bad = 0
foreach ($l in $links) {
    try {
        $target = Join-Path $Root $l.Bat
        if (-not (Test-Path $target)) { throw "Khong thay $target" }

        foreach ($old in $l.Old) {
            $p = Find-Link $old
            if ($p -and ((Get-LinkTarget $p) -like ('*\' + $l.Bat))) {
                try {
                    Remove-Item -LiteralPath $p -Force -ErrorAction Stop
                    Write-Host ('Da xoa bieu tuong ten cu: ' + $old)
                } catch {
                    Write-Host ('[!] Khong xoa duoc bieu tuong ten cu ' + $p + ' - xoa tay')
                }
            }
        }

        $have = Find-Link $l.Name
        if ($have -and ((Get-LinkTarget $have) -eq $target)) {
            Write-Host ('Da co: ' + $l.Name)
            continue
        }
        $tmp = Join-Path $desktop ('g8id_' + $l.Bat + '.lnk')
        $final = Join-Path $desktop ($l.Name + '.lnk')
        $lnk = $shell.CreateShortcut($tmp)
        $lnk.TargetPath = $target
        $lnk.WorkingDirectory = $Root
        $lnk.Save()
        Move-Item -LiteralPath $tmp -Destination $final -Force
        if ($have -and $have -ne $final) { Remove-Item -LiteralPath $have -Force -ErrorAction SilentlyContinue }
        Write-Host (($(if ($have) { 'Da sua (tro sai thu muc): ' } else { 'Da tao: ' })) + $l.Name + '  ->  ' + $target)
    } catch {
        Write-Host ('[LOI] Khong tao duoc bieu tuong ' + $l.Name + ': ' + $_)
        $bad++
    }
}
exit $(if ($bad) { 1 } else { 0 })
