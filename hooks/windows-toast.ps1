$ErrorActionPreference = "SilentlyContinue"

$raw = $input | Out-String
$message = "Claude richiede la tua attenzione"
$session = ""      # nome progetto (cwd)
$sessionId = ""    # UUID della sessione

# Log temporaneo del payload grezzo: serve a confermare i campi reali al 1o test.
if ($raw.Trim()) { $raw | Out-File "$env:TEMP\hs-toast-payload.log" -Encoding utf8 }

if ($raw.Trim()) {
    try {
        $json = ConvertFrom-Json $raw
        if ($json.message) {
            $message = $json.message
        }
        # "nome sessione" = nome cartella progetto (cwd); fallback: session_id breve
        if ($json.cwd) { $session = Split-Path $json.cwd -Leaf }
        if ($json.session_id) { $sessionId = $json.session_id }
    } catch {}
}

Import-Module BurntToast

$title = if ($session) { "Claude Code - $session" } else { "Claude Code" }

$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add($title)
$lines.Add($message)
if ($sessionId) { $lines.Add("Sessione: $sessionId") }

New-BurntToastNotification `
    -Text $lines.ToArray() `
    -AppLogo "E:\msys64\home\Sphynx\claude.png" `
    -ExpirationTime (Get-Date).AddSeconds(3)

exit 0
