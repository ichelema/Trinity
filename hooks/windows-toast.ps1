$ErrorActionPreference = "SilentlyContinue"

$raw = $input | Out-String
$message = "Claude richiede la tua attenzione"

if ($raw.Trim()) {
    try {
        $json = ConvertFrom-Json $raw
        if ($json.message) {
            $message = $json.message
        }
    } catch {}
}

Import-Module BurntToast

New-BurntToastNotification `
    -Text 'Claude Code', $message `
    -AppLogo 'C:\msys64\home\EN27553\claude.png' `
    -ExpirationTime (Get-Date).AddSeconds(3)

exit 0
