#!/usr/bin/env lua
-- ponytail — Claude Code SessionStart activation hook. Versione Lua.

local script_dir = (arg[0] or "."):match("^(.*)[/\\]") or "."
local json = dofile(script_dir .. "/../lib/dkjson.lua")
local config = dofile(script_dir .. "/ponytail-config.lua")
local instructions = dofile(script_dir .. "/ponytail-instructions.lua")

local claude_dir = config.get_claude_dir()
local settings_path = claude_dir .. "/settings.json"
local nudge_flag = claude_dir .. "/.ponytail-statusline-nudged"

local mode = config.get_default_mode()
if mode == "off" then
  config.clear_mode()
  io.stdout:write("OK")
  os.exit(0)
end

config.set_mode(mode)
local output = instructions.get_instructions(mode)

-- Nudge statusline mancante, al massimo una volta (flag file).
local has_statusline = false
local raw = config.file_read(settings_path)
if raw then
  raw = raw:gsub("^\239\187\191", "") -- strip UTF-8 BOM
  local ok, settings = pcall(json.decode, raw)
  if ok and type(settings) == "table" and settings.statusLine then
    has_statusline = true
  end
end

if not has_statusline and not config.file_exists(nudge_flag) then
  config.file_write(nudge_flag, "")
  local script_path = claude_dir .. "/statusline_new.sh"
  if config.is_shell_safe(script_path) then
    local command = 'bash "' .. script_path .. '"'
    local snippet = '"statusLine": { "type": "command", "command": ' .. json.encode(command) .. ' }'
    output = output .. "\n\n" ..
      "CONFIGURAZIONE STATUSLINE NECESSARIA: il plugin ponytail include un badge statusline che mostra la modalità attiva " ..
      "(es. [PONYTAIL]). Non è ancora configurato. " ..
      "Per abilitarlo, aggiungi questo a " .. settings_path .. ": " ..
      snippet .. " " ..
      "Proponi proattivamente di configurarlo per l'utente alla prima interazione."
  else
    output = output .. "\n\n" ..
      "CONFIGURAZIONE STATUSLINE NECESSARIA: il plugin ponytail include un badge statusline che mostra la modalità attiva. " ..
      "Il suo path di installazione contiene caratteri non sicuri da includere in un comando shell, quindi configuralo manualmente: " ..
      'aggiungi un comando statusLine di tipo "command" che esegue ' .. script_path ..
      " in " .. settings_path .. ", citando/effettuando l'escape del path per la tua shell. " ..
      "Proponi proattivamente di configurarlo per l'utente alla prima interazione."
  end
end

io.stdout:write(output)
