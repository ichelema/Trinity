#!/usr/bin/env lua
-- ponytail — Claude Code SubagentStart hook. Versione Lua.

local script_dir = (arg[0] or "."):match("^(.*)[/\\]") or "."
local json = dofile(script_dir .. "/../lib/dkjson.lua")
local config = dofile(script_dir .. "/ponytail-config.lua")
local instructions = dofile(script_dir .. "/ponytail-instructions.lua")

local input = config.read_input()
local mode = config.read_mode(input.session_id)
if not mode or mode == "off" then
  os.exit(0)
end

local function inject()
  local ctx = instructions.get_instructions(mode)
  local payload = { hookSpecificOutput = { hookEventName = "SubagentStart", additionalContext = ctx } }
  io.stdout:write(json.encode(payload))
end

-- Matcher (subset: alternation |, anchor ^$, substring; case-insensitive).
local function match_agent(pat, text)
  local t = text:lower()
  for alt in pat:gmatch("[^|]+") do
    local a = alt
    local anchored_start = false
    local anchored_end = false
    if a:sub(1, 1) == "^" then anchored_start = true; a = a:sub(2) end
    if a:sub(-1) == "$" then anchored_end = true; a = a:sub(1, -2) end
    a = a:lower()
    if anchored_start and anchored_end then
      if t == a then return true end
    elseif anchored_start then
      if t:sub(1, #a) == a then return true end
    elseif anchored_end then
      if t:sub(-#a) == a then return true end
    else
      if t:find(a, 1, true) then return true end
    end
  end
  return false
end

local matcher_src = os.getenv("PONYTAIL_SUBAGENT_MATCHER")
-- Regex complesse (chars non supportati dal subset) → fallisci open, inietta sempre.
if matcher_src and matcher_src:match("[%*%+%?%(%)%[%]{}%.%\\]") then
  matcher_src = nil
end

if not matcher_src or matcher_src == "" then
  inject()
  os.exit(0)
end

-- Matcher settato → salta solo su mismatch certo di agent_type.
local agent_type = tostring(input.agent_type or ""):gsub("^%s+", ""):gsub("%s+$", "")

if agent_type ~= "" and not match_agent(matcher_src, agent_type) then
  os.exit(0)
end
inject()
