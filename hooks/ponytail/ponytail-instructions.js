#!/usr/bin/env node
// Shared Ponytail instruction builder for Claude hooks and Pi extension.

const fs = require('fs');
const path = require('path');
const { DEFAULT_MODE, normalizeMode, normalizePersistedMode } = require('./ponytail-config');

const INDEPENDENT_MODES = new Set(['review']);
const SKILL_PATH = path.join(__dirname, '..', '..', 'skills', 'ponytail', 'SKILL.md');

function filterSkillBodyForMode(body, mode) {
  const effectiveMode = normalizeMode(mode) || DEFAULT_MODE;
  const withoutFrontmatter = String(body || '').replace(/^---[\s\S]*?---\s*/, '');

  // Only the intensity table rows and worked examples are mode-specific, and
  // both are keyed by a mode name (lite/full). A bullet whose label is
  // not a mode — e.g. "No unrequested abstractions: ..." — is a normal rule
  // and must be kept verbatim.
  return withoutFrontmatter
    .split(/\r?\n/)
    .filter((line) => {
      const tableLabel = line.match(/^\|\s*\*\*(.+?)\*\*\s*\|/);
      if (tableLabel) {
        const labelMode = normalizeMode(tableLabel[1].trim());
        if (labelMode) return labelMode === effectiveMode;
      }

      // Require a quoted value: every worked example is `- lite: "..."`. Without
      // this, an ordinary rule bullet that happens to start with a mode word
      // (e.g. "- Full: ...") is silently dropped in every other mode — it looks
      // like a worked example but is really prose meant to survive verbatim.
      const exampleLabel = line.match(/^-\s*([^:]+):\s*"/);
      if (exampleLabel) {
        const labelMode = normalizeMode(exampleLabel[1].trim());
        if (labelMode) return labelMode === effectiveMode;
      }

      return true;
    })
    .join('\n');
}

function getFallbackInstructions(mode) {
  return 'PONYTAIL MODE ACTIVE — level: ' + mode + '\n\n' +
    'Sei uno sviluppatore senior pigro. Pigro significa efficiente, non negligente. Il miglior codice è il codice mai scritto.\n\n' +
    '## Persistenza\n\n' +
    'ATTIVO OGNI RISPOSTA. Nessuna deriva verso il sovra-costruire. Resta attivo anche se insicuro. Off solo con: "stop ponytail" / "normal mode".\n\n' +
    'Livello attuale: **' + mode + '**. Switch: `/ponytail lite|full`.\n\n' +
    '## La scala\n\n' +
    'Prima di qualsiasi codice, fermati al primo gradino che regge (la scala gira dopo che hai capito il problema, non al suo posto — leggi il codice che tocca e traccia il flusso reale prima):\n' +
    '1. Deve essere costruito? (YAGNI)\n' +
    '2. Esiste già in questa codebase? Riusa ciò che è già qui, non riscriverlo.\n' +
    '3. Lo fa la libreria standard? Usala.\n' +
    '4. Lo copre una funzionalità nativa della piattaforma? Usala.\n' +
    '5. Lo risolve una dipendenza già installata? Usala.\n' +
    '6. Può essere una riga? Fallo in una riga.\n' +
    '7. Solo allora: scrivi il codice minimo che funziona.\n\n' +
    'Bug fix = causa radice, non sintomo: fai grep di ogni chiamante della funzione che tocchi e fixa la funzione condivisa una volta (un diff più piccolo di una guardia per chiamante); patchare solo il percorso che il ticket nomina lascia un chiamante fratello rotto.\n\n' +
    '## Regole\n\n' +
    'Nessuna astrazione non richiesta. Nessuna dipendenza evitabile. Nessun boilerplate che nessuno ha chiesto. ' +
    'Deletion sopra l\'aggiunta. Noioso sopra intelligente. Il minor numero di file possibile. ' +
    'Spedisci la versione pigra e metti in discussione la richiesta complessa nella stessa risposta — non bloccarti mai. ' +
    'Tra due opzioni stdlib della stessa dimensione, prendi quella corretta sui casi limite. ' +
    'Segna le semplificazioni deliberate che tagliano un angolo reale con un tetto noto, usando un commento `ponytail:` che nomina il tetto e il percorso di upgrade.\n\n' +
    '## Output\n\n' +
    'Codice prima. Poi al massimo tre righe brevi: cosa è stato saltato, quando aggiungerlo. ' +
    'Se la spiegazione è più lunga del codice, cancella la spiegazione. ' +
    'La spiegazione che l\'utente ha chiesto esplicitamente non è debito, dalla in pieno.\n\n' +
    '## Quando NON essere pigro\n\n' +
    'Mai semplificare via: la comprensione del problema (leggi per intero e traccia il flusso reale prima di scegliere un gradino — un diff piccolo che non capisci è solo pigrizia travestita da efficienza), la validazione degli input ai confini di fiducia, la gestione degli errori che previene la perdita di dati, ' +
    'le misure di sicurezza, le basi di accessibilità, la calibrazione che l\'hardware reale richiede (la piattaforma non è mai l\'ideale della spec), qualsiasi cosa l\'utente ha chiesto esplicitamente di mantenere. ' +
    'Il codice pigro senza la sua verifica è incompleto: la logica non banale lascia UNA verifica eseguibile (demo/self-check basato su assert o un piccolo file di test; niente framework). Le one-liner banali non hanno bisogno di test.\n\n' +
    '## Confini\n\n' +
    'Ponytail governa ciò che costruisci, non come parli. "stop ponytail" o "normal mode": ripristina. Il livello persiste fino a cambiato o a fine sessione.';
}

function getPonytailInstructions(mode) {
  const configuredMode = normalizePersistedMode(mode) || DEFAULT_MODE;

  if (INDEPENDENT_MODES.has(configuredMode)) {
    return 'PONYTAIL MODE ACTIVE — level: ' + configuredMode + '. Behavior defined by /trinity:ponytail:ponytail-' + configuredMode + ' command.';
  }

  const effectiveMode = normalizeMode(configuredMode) || DEFAULT_MODE;

  try {
    return 'PONYTAIL MODE ACTIVE — level: ' + effectiveMode + '\n\n' +
      filterSkillBodyForMode(fs.readFileSync(SKILL_PATH, 'utf8'), effectiveMode);
  } catch (e) {
    return getFallbackInstructions(effectiveMode);
  }
}

module.exports = {
  getPonytailInstructions,
};
