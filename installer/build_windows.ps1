param(
    [string]$PythonPath = "c:\Users\21483\.conda\envs\lis_sac_ml\python.exe",
    [string]$BaderExe = "",
    [string]$ISCCPath = "",
    [switch]$RequireBader
)

$ErrorActionPreference = "Stop"

$InstallerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $InstallerDir "..")
$DistDir = Join-Path $ProjectRoot "dist"
$RuntimeBaderDir = Join-Path $InstallerDir "runtime\bader_engine"
$IconPath = Join-Path $InstallerDir "BaderChargeAnalyzer.ico"

function Resolve-ToolPath {
    param(
        [string]$ExplicitPath,
        [string]$CommandName,
        [string[]]$Fallbacks
    )

    if ($ExplicitPath -and (Test-Path -LiteralPath $ExplicitPath)) {
        return (Resolve-Path -LiteralPath $ExplicitPath).Path
    }

    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    foreach ($path in $Fallbacks) {
        if (Test-Path -LiteralPath $path) {
            return (Resolve-Path -LiteralPath $path).Path
        }
    }

    throw "Cannot find $CommandName. Install it or pass the path explicitly."
}

function Test-WindowsExecutable {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }

    $stream = [System.IO.File]::OpenRead($Path)
    try {
        if ($stream.Length -lt 2) {
            return $false
        }
        $first = $stream.ReadByte()
        $second = $stream.ReadByte()
        return ($first -eq 0x4D -and $second -eq 0x5A)
    }
    finally {
        $stream.Dispose()
    }
}

function Resolve-BaderExe {
    param([string]$ExplicitPath)

    $candidates = @()
    if ($ExplicitPath) {
        $candidates += $ExplicitPath
    }
    $candidates += @(
        (Join-Path $ProjectRoot "bader.exe"),
        (Join-Path $ProjectRoot "bader_engine\bader.exe")
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-WindowsExecutable $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    throw "A Windows bader.exe is required for the release installer. The repository root bader file is not enough if it is a Linux ELF binary. Pass -BaderExe C:\path\to\bader.exe."
}

function Resolve-AppPngIcon {
    $rootPngs = Get-ChildItem -LiteralPath $ProjectRoot -File -Filter "*.png"
    $largeRootIcon = $rootPngs |
        Where-Object { $_.Length -gt 1000000 -and $_.Name -notlike "*备份*" -and $_.Name -notlike "*backup*" } |
        Select-Object -First 1
    if ($largeRootIcon) {
        return $largeRootIcon.FullName
    }

    $assetIcon = Join-Path $ProjectRoot "assets\bader_icon.png"
    if (Test-Path -LiteralPath $assetIcon) {
        return (Resolve-Path -LiteralPath $assetIcon).Path
    }

    throw "Cannot find an application PNG icon."
}

Push-Location $ProjectRoot
try {
    $Python = Resolve-ToolPath -ExplicitPath $PythonPath -CommandName "python.exe" -Fallbacks @()
    $ISCC = Resolve-ToolPath -ExplicitPath $ISCCPath -CommandName "ISCC.exe" -Fallbacks @(
        "C:\Users\21483\AppData\Local\Programs\Inno Setup 6\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )

    if (Test-Path -LiteralPath $RuntimeBaderDir) {
        Remove-Item -LiteralPath $RuntimeBaderDir -Recurse -Force
    }

    $ResolvedBader = $null
    if ($BaderExe -or $RequireBader) {
        $ResolvedBader = Resolve-BaderExe -ExplicitPath $BaderExe
    }
    elseif (Test-WindowsExecutable (Join-Path $ProjectRoot "bader.exe")) {
        $ResolvedBader = (Resolve-Path -LiteralPath (Join-Path $ProjectRoot "bader.exe")).Path
    }
    elseif (Test-WindowsExecutable (Join-Path $ProjectRoot "bader_engine\bader.exe")) {
        $ResolvedBader = (Resolve-Path -LiteralPath (Join-Path $ProjectRoot "bader_engine\bader.exe")).Path
    }

    if ($ResolvedBader) {
        New-Item -ItemType Directory -Force -Path $RuntimeBaderDir | Out-Null
        Copy-Item -LiteralPath $ResolvedBader -Destination (Join-Path $RuntimeBaderDir "bader.exe") -Force
        Write-Host "Bundled Bader executable: $ResolvedBader"
    }
    else {
        Write-Host "No Windows bader.exe bundled. The installer will support importing and analyzing existing ACF.dat files."
    }

    $PngIcon = Resolve-AppPngIcon
    & $Python -c "import sys; from PIL import Image; from pathlib import Path; img=Image.open(Path(sys.argv[1])).convert('RGBA'); img.save(Path('installer/BaderChargeAnalyzer.ico'), sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])" $PngIcon
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to generate installer icon."
    }

    & $Python -m PyInstaller --clean --noconfirm "installer\bader_charge_analyzer.spec"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed."
    }

    $AppExe = Join-Path $DistDir "BaderChargeAnalyzer\BaderChargeAnalyzer.exe"
    if (-not (Test-Path -LiteralPath $AppExe)) {
        throw "PyInstaller did not create $AppExe."
    }

    & $ISCC "installer\setup.iss"
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup build failed."
    }

    Write-Host "Build complete."
    Write-Host "Portable app: $AppExe"
    Write-Host "Installer: $(Join-Path $DistDir 'BaderChargeAnalyzer_Setup_v0.1.0.exe')"
}
finally {
    Pop-Location
}
