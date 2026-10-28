# Tao 2 bieu tuong tren Desktop cho ky thuat van hanh (goi tu cai_dat_may_moi.bat).
# File luu UTF-8 co BOM de PowerShell 5.1 doc dung ten tieng Viet.
param([string]$Root)

$Root = (Resolve-Path $Root).Path
$desktop = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell
$links = @(
    @{ Name = 'Chạy phần mềm'; Bat = 'chay_dinh_danh.bat' },
    @{ Name = 'Chạy mô phỏng'; Bat = 'chay_mo_phong.bat' }
)
try {
    foreach ($l in $links) {
        $target = Join-Path $Root $l.Bat
        if (-not (Test-Path $target)) { throw "Khong thay $target" }
        # WScript.Shell khong luu duoc ten co dau: luu ten tam ASCII roi doi ten.
        $tmp = Join-Path $desktop ('g8id_' + $l.Bat + '.lnk')
        $final = Join-Path $desktop ($l.Name + '.lnk')
        $lnk = $shell.CreateShortcut($tmp)
        $lnk.TargetPath = $target
        $lnk.WorkingDirectory = $Root
        $lnk.Save()
        Move-Item -LiteralPath $tmp -Destination $final -Force
        Write-Host ('Da tao: ' + $l.Name + '  ->  ' + $target)
    }
    exit 0
} catch {
    Write-Host ('[LOI] Khong tao duoc bieu tuong: ' + $_)
    exit 1
}
