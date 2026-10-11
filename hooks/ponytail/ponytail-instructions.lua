-- ponytail-instructions.lua — costruttore del ruleset ponytail.
-- Legge skills/ponytail/SKILL.md e lo filtra per livello.

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
    "skills/ponytail/SKILL.md non è leggibile: applica la modifica completa più piccola che risolve il task."
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
