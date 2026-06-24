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
    -AppLogo "E:\msys64\home\Sphynx\claude.png" `
    -ExpirationTime (Get-Date).AddSeconds(3)

exit 0
