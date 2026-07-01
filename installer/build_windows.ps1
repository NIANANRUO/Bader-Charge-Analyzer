param(
    [string]$PythonPath = "c:\Users\21483\.conda\envs\lis_sac_ml\python.exe",
    [string]$BaderExe = "",
    [string]$ISCCPath = ""
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

Push-Location $ProjectRoot
try {
    $Python = Resolve-ToolPath -ExplicitPath $PythonPath -CommandName "python.exe" -Fallbacks @()
    $ResolvedBader = Resolve-BaderExe -ExplicitPath $BaderExe
    $ISCC = Resolve-ToolPath -ExplicitPath $ISCCPath -CommandName "ISCC.exe" -Fallbacks @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )

    New-Item -ItemType Directory -Force -Path $RuntimeBaderDir | Out-Null
    Copy-Item -LiteralPath $ResolvedBader -Destination (Join-Path $RuntimeBaderDir "bader.exe") -Force

    & $Python -c "from PIL import Image; from pathlib import Path; img=Image.open(Path('图标.png')).convert('RGBA'); img.save(Path('installer/BaderChargeAnalyzer.ico'), sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
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
