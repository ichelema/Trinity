$ErrorActionPreference = "SilentlyContinue"

$raw = $input | Out-String
$message = "Claude richiede la tua attenzione"
$project = ""   # nome cartella (cwd) -> titolo
$session = ""   # nome custom da /rename -> riga sessione

if ($raw.Trim()) {
    try {
        $json = ConvertFrom-Json $raw
        if ($json.message) { $message = $json.message }
        if ($json.cwd) { $project = Split-Path $json.cwd -Leaf }
        # Nome custom della sessione (/rename): vive nel transcript come righe
        # {"type":"custom-title","customTitle":"..."} -> prendi l'ultima.
        if ($json.transcript_path -and (Test-Path -LiteralPath $json.transcript_path)) {
            $tl = Select-String -LiteralPath $json.transcript_path -Pattern '"type":"custom-title"' | Select-Object -Last 1
            if ($tl) {
                try { $ct = ($tl.Line | ConvertFrom-Json).customTitle; if ($ct) { $session = $ct } } catch {}
            }
        }
    } catch {}
}

Import-Module BurntToast

$title = if ($project) { "Claude Code - $project" } else { "Claude Code" }

$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add($title)
$lines.Add($message)
if ($session) { $lines.Add("Sessione: $session") }

New-BurntToastNotification `
    -Text $lines.ToArray() `
    -AppLogo "E:\msys64\home\Sphynx\claude.png" `
    -ExpirationTime (Get-Date).AddSeconds(3)
