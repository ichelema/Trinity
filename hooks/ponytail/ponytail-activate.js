#!/usr/bin/env node
// ponytail — Claude Code SessionStart activation hook
//
// Runs on every session start:
//   1. Writes flag file at $CLAUDE_CONFIG_DIR/.ponytail-active (defaults to ~/.claude; statusline reads this)
//   2. Emits ponytail ruleset as hidden SessionStart context
//   3. Detects missing statusline config and emits setup nudge

const fs = require('fs');
const path = require('path');
const { getDefaultMode, getClaudeDir, isShellSafe } = require('./ponytail-config');
const { getPonytailInstructions } = require('./ponytail-instructions');
const {
  clearMode,
  setMode,
  writeHookOutput,
} = require('./ponytail-runtime');

const claudeDir = getClaudeDir();
const settingsPath = path.join(claudeDir, 'settings.json');

const mode = getDefaultMode();

// "off" mode — skip activation entirely, don't write flag or emit rules
if (mode === 'off') {
  clearMode();
  writeHookOutput('SessionStart', 'OK');
  process.exit(0);
}

// 1. Write flag file
try {
  setMode(mode);
} catch (e) {
  // Silent fail -- flag is best-effort, don't block the hook
}

// 2. Emit the ponytail ruleset, filtered to the active intensity level.
let output = getPonytailInstructions(mode);

// 3. Detect missing statusline config — nudge Claude to help set it up
try {
  let hasStatusline = false;
  if (fs.existsSync(settingsPath)) {
    // Strip UTF-8 BOM some editors prepend on Windows (breaks JSON.parse)
    const raw = fs.readFileSync(settingsPath, 'utf8').replace(/^\uFEFF/, '');
    const settings = JSON.parse(raw);
    if (settings.statusLine) {
      hasStatusline = true;
    }
  }

  // Nudge at most once — the flag file marks that the user has already seen
  // (and implicitly declined) the statusline setup offer. Repeating it every
  // session start turns a helpful hint into a nag.
  const nudgeFlagPath = path.join(claudeDir, '.ponytail-statusline-nudged');
  if (!hasStatusline && !fs.existsSync(nudgeFlagPath)) {
    try { fs.writeFileSync(nudgeFlagPath, ''); } catch (e) { /* best-effort */ }
    const scriptPath = path.join(claudeDir, 'statusline_new.sh');
    if (isShellSafe(scriptPath)) {
      const command = `bash "${scriptPath}"`;
      const statusLineSnippet =
        '"statusLine": { "type": "command", "command": ' + JSON.stringify(command) + ' }';
      output += "\n\n" +
        "CONFIGURAZIONE STATUSLINE NECESSARIA: il plugin ponytail include un badge statusline che mostra la modalità attiva " +
        "(es. [PONYTAIL]). Non è ancora configurato. " +
        "Per abilitarlo, aggiungi questo a " + settingsPath + ": " +
        statusLineSnippet + " " +
        "Proponi proattivamente di configurarlo per l'utente alla prima interazione.";
    } else {
      // ponytail: il path di installazione contiene metacaratteri di shell — non includerlo in uno
      // snippet di comando; fai in modo che l'agente lo configuri a mano.
      output += "\n\n" +
        "CONFIGURAZIONE STATUSLINE NECESSARIA: il plugin ponytail include un badge statusline che mostra la modalità attiva. " +
        "Il suo path di installazione contiene caratteri non sicuri da includere in un comando shell, quindi configuralo manualmente: " +
        "aggiungi un comando statusLine di tipo \"command\" che esegue " + scriptPath +
        " in " + settingsPath + ", citando/effettuando l'escape del path per la tua shell. " +
        "Proponi proattivamente di configurarlo per l'utente alla prima interazione.";
    }
  }
} catch (e) {
  // Silent fail — don't block session start over statusline detection
}

try {
  writeHookOutput('SessionStart', output);
} catch (e) {
  // Silent fail — stdout closed/EPIPE at hook exit must not surface as a hook failure
}
