-- ponytail-instructions.lua — costruttore del ruleset ponytail.
-- Port fedele di ponytail-instructions.js.

local source = debug.getinfo(1, "S").source
local script_dir = source:match("^@(.*)[/\\]") or "."
local config = dofile(script_dir .. "/ponytail-config.lua")

local SKILL_PATH = script_dir .. "/../../skills/ponytail/SKILL.md"

-- Filtra il corpo di SKILL.md per il livello attivo: le righe della tabella
-- intensità e gli esempi con etichetta di un altro livello vengono rimosse.
local function filter_skill_body(body, mode)
  local s = tostring(body or ""):gsub("\r\n", "\n"):gsub("\r", "\n")
  s = s:gsub("^%-%-%-.-%-%-%-%s*", "")
  local lines = {}
  local pos = 1
  while true do
    local nl = s:find("\n", pos, true)
    local line
    if nl then
      line = s:sub(pos, nl - 1)
      pos = nl + 1
    else
      line = s:sub(pos)
      pos = nil
    end
    local keep = true
    local table_label = line:match("^|%s*%*%*(.-)%*%*%s*|")
    if table_label then
      local lm = config.normalize_mode(table_label)
      if lm and lm ~= mode then keep = false end
    else
      local example_label = line:match("^%-%s*([^:]+):%s*\"")
      if example_label then
        local lm = config.normalize_mode(example_label)
        if lm and lm ~= mode then keep = false end
      end
    end
    if keep then lines[#lines + 1] = line end
    if not pos then break end
  end
  return table.concat(lines, "\n")
end

local function fallback(mode)
  return "PONYTAIL MODE ACTIVE — level: " .. mode .. "\n\n" ..
    "Sei uno sviluppatore senior pigro. Pigro significa efficiente, non negligente. Il miglior codice è il codice mai scritto.\n\n" ..
    "## Persistenza\n\n" ..
    'ATTIVO OGNI RISPOSTA. Nessuna deriva verso il sovra-costruire. Resta attivo anche se insicuro. Off solo con: "stop ponytail" / "normal mode".\n\n' ..
    "Livello attuale: **" .. mode .. "**. Switch: `/ponytail lite|full`.\n\n" ..
    "## La scala\n\n" ..
    "Prima di qualsiasi codice, fermati al primo gradino che regge (la scala gira dopo che hai capito il problema, non al suo posto — leggi il codice che tocca e traccia il flusso reale prima):\n" ..
    "1. Deve essere costruito? (YAGNI)\n" ..
    "2. Esiste già in questa codebase? Riusa ciò che è già qui, non riscriverlo.\n" ..
    "3. Lo fa la libreria standard? Usala.\n" ..
    "4. Lo copre una funzionalità nativa della piattaforma? Usala.\n" ..
    "5. Lo risolve una dipendenza già installata? Usala.\n" ..
    "6. Può essere una riga? Fallo in una riga.\n" ..
    "7. Solo allora: scrivi il codice minimo che funziona.\n\n" ..
    "Bug fix = causa radice, non sintomo: fai grep di ogni chiamante della funzione che tocchi e fixa la funzione condivisa una volta (un diff più piccolo di una guardia per chiamante); patchare solo il percorso che il ticket nomina lascia un chiamante fratello rotto.\n\n" ..
    "## Regole\n\n" ..
    "Nessuna astrazione non richiesta. Nessuna dipendenza evitabile. Nessun boilerplate che nessuno ha chiesto. " ..
    "Deletion sopra l'aggiunta. Noioso sopra intelligente. Il minor numero di file possibile. " ..
    "Spedisci la versione pigra e metti in discussione la richiesta complessa nella stessa risposta — non bloccarti mai. " ..
    "Tra due opzioni stdlib della stessa dimensione, prendi quella corretta sui casi limite. " ..
    "Segna le semplificazioni deliberate che tagliano un angolo reale con un tetto noto, usando un commento `ponytail:` che nomina il tetto e il percorso di upgrade.\n\n" ..
    "## Output\n\n" ..
    "Codice prima. Poi al massimo tre righe brevi: cosa è stato saltato, quando aggiungerlo. " ..
    "Se la spiegazione è più lunga del codice, cancella la spiegazione. " ..
    "La spiegazione che l'utente ha chiesto esplicitamente non è debito, dalla in pieno.\n\n" ..
    "## Quando NON essere pigro\n\n" ..
    "Mai semplificare via: la comprensione del problema (leggi per intero e traccia il flusso reale prima di scegliere un gradino — un diff piccolo che non capisci è solo pigrizia travestita da efficienza), la validazione degli input ai confini di fiducia, la gestione degli errori che previene la perdita di dati, " ..
    "le misure di sicurezza, le basi di accessibilità, la calibrazione che l'hardware reale richiede (la piattaforma non è mai l'ideale della spec), qualsiasi cosa l'utente ha chiesto esplicitamente di mantenere. " ..
    "Il codice pigro senza la sua verifica è incompleto: la logica non banale lascia UNA verifica eseguibile (demo/self-check basato su assert o un piccolo file di test; niente framework). Le one-liner banali non hanno bisogno di test.\n\n" ..
    "## Confini\n\n" ..
    'Ponytail governa ciò che costruisci, non come parli. "stop ponytail" o "normal mode": ripristina. Il livello persiste fino a cambiato o a fine sessione.'
end

local function get_instructions(mode)
  local configured = config.normalize_persisted_mode(mode) or config.DEFAULT_MODE
  if configured == "review" then
    return "PONYTAIL MODE ACTIVE — level: review. Behavior defined by /trinity:ponytail:ponytail-review command."
  end
  local effective = config.normalize_mode(configured) or config.DEFAULT_MODE
  local body = config.file_read(SKILL_PATH)
  if body then
    return "PONYTAIL MODE ACTIVE — level: " .. effective .. "\n\n" .. filter_skill_body(body, effective)
  end
  return fallback(effective)
end

return {
  get_instructions = get_instructions,
}
