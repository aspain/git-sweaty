param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$SetupArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$BootstrapUrl = "https://raw.githubusercontent.com/aspain/git-sweaty/main/scripts/bootstrap.sh"
$ManualSetupUrl = "https://github.com/aspain/git-sweaty#manual-setup-no-scripts"

function Write-Info {
    param([string]$Message)
    Write-Host $Message
}

function Fail {
    param([string]$Message)
    throw $Message
}

function Join-BashArgs {
    param([string[]]$Items)

    $quoted = @()
    foreach ($item in $Items) {
        if ($null -eq $item) {
            continue
        }
        if ($item -eq "") {
            $quoted += "''"
            continue
        }
        $quoted += "'" + ($item -replace "'", "'""'""'") + "'"
    }
    return ($quoted -join " ")
}

function Ensure-WslReady {
    $wslCommand = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if ($null -eq $wslCommand) {
        Write-Info "Windows setup uses the WSL-backed bootstrap path."
        Write-Info "Install WSL first, then re-run setup:"
        Write-Info "  wsl --install -d Ubuntu"
        Write-Info "If you would rather avoid WSL troubleshooting, use manual setup instead:"
        Write-Info "  $ManualSetupUrl"
        Fail "WSL is required before continuing."
    }

    $distros = @(& wsl.exe -l -q 2>$null)
    $trimmedDistros = @($distros | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if ($LASTEXITCODE -ne 0 -or $trimmedDistros.Count -eq 0) {
        Write-Info "WSL is installed, but no Linux distro is ready yet."
        Write-Info "Finish WSL setup first, for example:"
        Write-Info "  wsl --install -d Ubuntu"
        Write-Info "If you would rather avoid WSL troubleshooting, use manual setup instead:"
        Write-Info "  $ManualSetupUrl"
        Fail "A WSL distro is required before continuing."
    }
}

Ensure-WslReady

$bootstrapCommand = "bash <(curl -fsSL $BootstrapUrl)"
if ($null -ne $SetupArgs -and $SetupArgs.Count -gt 0) {
    $bootstrapCommand = "$bootstrapCommand $(Join-BashArgs $SetupArgs)"
}

Write-Info "Launching setup inside WSL..."
& wsl.exe bash -lc $bootstrapCommand
if ($LASTEXITCODE -ne 0) {
    Write-Info ""
    Write-Info "If the WSL path keeps failing, use manual setup instead:"
    Write-Info "  $ManualSetupUrl"
}
exit $LASTEXITCODE
