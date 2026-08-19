#!/usr/bin/env lua
-- ponytail — UserPromptSubmit hook: traccia la modalità ponytail attiva. Versione Lua.

local script_dir = (arg[0] or "."):match("^(.*)[/\\]") or "."
local json = dofile(script_dir .. "/../lib/dkjson.lua")
local config = dofile(script_dir .. "/ponytail-config.lua")

local input = io.read("*a") or ""

local data = {}
do
  local ok, parsed = pcall(json.decode, input)
  if ok and type(parsed) == "table" then data = parsed end
end
local prompt = tostring(data.prompt or ""):lower()
prompt = prompt:gsub("^%s+", ""):gsub("%s+$", "")

local mode_switched = false
local deactivated = false

if prompt:match("^[/@$]ponytail") or prompt:match("^[/@$]trinity:ponytail") then
  local parts = {}
  for w in prompt:gmatch("%S+") do parts[#parts + 1] = w end
  local cmd = parts[1] or ""
  cmd = cmd:gsub("^[@$]", "/"):gsub("^/trinity:", "/")
  local arg = parts[2] or ""
  local arg2 = parts[3] or ""

  local mode
  local is_report = false

  if cmd == "/ponytail-review" or cmd == "/ponytail:ponytail-review" then
    mode = "review"
  elseif cmd == "/ponytail" or cmd == "/ponytail:ponytail" then
    if arg == "default" then
      if arg2 == "off" or arg2 == "lite" or arg2 == "full" then
        config.write_default_mode(arg2)
        io.stdout:write("PONYTAIL DEFAULT SET — new sessions start in " .. arg2 .. ".")
      end
      os.exit(0)
    end
    if arg == "lite" then mode = "lite"
    elseif arg == "full" then mode = "full"
    elseif arg == "off" then mode = "off"
    elseif arg == "" then
      is_report = true
      mode = config.read_mode() or config.get_default_mode()
    else
      mode = config.get_default_mode()
    end
  end

  if is_report then
    io.stdout:write("PONYTAIL MODE ACTIVE — level: " .. tostring(mode))
  elseif mode and mode ~= "off" then
    config.set_mode(mode)
    mode_switched = true
    io.stdout:write("PONYTAIL MODE CHANGED — level: " .. tostring(mode))
  elseif mode == "off" then
    config.clear_mode()
    deactivated = true
    io.stdout:write("PONYTAIL MODE OFF")
  end
end

if not mode_switched and not deactivated then
  if config.is_deactivation_command(prompt) then
    config.clear_mode()
    io.stdout:write("PONYTAIL MODE OFF")
  end
end
