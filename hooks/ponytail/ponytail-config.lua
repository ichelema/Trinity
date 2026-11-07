-- ponytail-config.lua — configurazione + stato runtime condivisi.
-- JSON con dkjson.

local source = debug.getinfo(1, "S").source
local script_dir = source:match("^@(.*)[/\\]") or "."
local json = dofile(script_dir .. "/../lib/dkjson.lua")

local DEFAULT_MODE = "full"
local VALID_MODES = { off = true, lite = true, full = true, review = true }
local RUNTIME_MODES = { off = true, lite = true, full = true }

local home = os.getenv("HOME") or os.getenv("USERPROFILE") or ""

-- --- helper I/O e filesystem ---

local function dirname(p) return p:match("^(.*)[/\\]") or "." end

local function mkdir_p(d)
  if package.config:sub(1, 1) == "\\" then
    os.execute('mkdir "' .. d .. '" 2>NUL')
  else
    os.execute('mkdir -p "' .. d .. '" 2>/dev/null')
  end
end

local function file_read(p)
  local f = io.open(p, "rb")
  if not f then return nil end
  local c = f:read("*a")
  f:close()
  return c
end

local function file_write(p, data)
  local f = io.open(p, "wb")
  if not f then return false end
  f:write(data)
  f:close()
  return true
end

local function file_exists(p)
  local f = io.open(p, "rb")
  if f then f:close() return true end
  return false
end

-- --- configurazione ---

local function normalize_mode(mode)
  if type(mode) ~= "string" then return nil end
  local n = mode:gsub("^%s+", ""):gsub("%s+$", ""):lower()
  return RUNTIME_MODES[n] and n or nil
end

local function normalize_config_mode(mode)
  if type(mode) ~= "string" then return nil end
  local n = mode:gsub("^%s+", ""):gsub("%s+$", ""):lower()
  return VALID_MODES[n] and n or nil
end

local function normalize_persisted_mode(mode)
  return normalize_mode(mode) or normalize_config_mode(mode)
end

local function is_deactivation_command(text)
  local t = tostring(text or ""):gsub("^%s+", ""):gsub("%s+$", ""):lower()
  t = t:gsub("[.!?%s]+$", "")
  return t == "stop ponytail" or t == "normal mode"
end

local function is_shell_safe(p)
  return type(p) == "string" and p:match("^[%w _%.%-:/\\~]+$") ~= nil
end

local function get_config_dir()
  local xdg = os.getenv("XDG_CONFIG_HOME")
  if xdg then return xdg .. "/ponytail" end
  return home .. "/.config/ponytail"
end

local function get_config_path()
  return get_config_dir() .. "/config.json"
end

local function get_claude_dir()
  return os.getenv("CLAUDE_CONFIG_DIR") or (home .. "/.claude")
end

local function get_default_mode()
  local m = (os.getenv("PONYTAIL_DEFAULT_MODE") or ""):lower()
  if RUNTIME_MODES[m] then return m end
  local raw = file_read(get_config_path())
  if raw then
    raw = raw:gsub("^\239\187\191", "") -- strip BOM
    local ok, cfg = pcall(json.decode, raw)
    if ok and type(cfg) == "table" then
      local dm = tostring(cfg.defaultMode or ""):lower()
      if RUNTIME_MODES[dm] then return dm end
    end
  end
  return DEFAULT_MODE
end

local function write_default_mode(mode)
  local normalized = normalize_mode(mode)
  if not normalized then return nil end
  local config_path = get_config_path()
  mkdir_p(dirname(config_path))
  local f = io.open(config_path, "wb")
  if f then
    f:write('{\n  "defaultMode": "' .. normalized .. '"\n}\n')
    f:close()
  end
  return normalized
end

-- --- input dell'hook (JSON su stdin) ---

local function read_input()
  local raw = (io.read("*a") or ""):gsub("^\239\187\191", "") -- strip BOM
  local ok, data = pcall(json.decode, raw)
  if ok and type(data) == "table" then return data end
  return {}
end

-- --- stato runtime per sessione (ponytail-state/<session_id>, "off" compreso) ---

local state_dir = get_claude_dir() .. "/ponytail-state"

-- session_id arriva dallo stdin dell'hook: solo caratteri da nome file, altrimenti nessuno stato
local function state_file(sid)
  if type(sid) == "string" and sid:match("^[%w%-]+$") then return state_dir .. "/" .. sid end
  return nil
end

local function read_mode(sid)
  local p = state_file(sid)
  local m = p and file_read(p)
  if m then m = m:gsub("^%s+", ""):gsub("%s+$", "") end
  if m and m ~= "" then return m end
  return nil
end

local function set_mode(sid, mode)
  local p = state_file(sid)
  if not p then return end
  mkdir_p(state_dir)
  file_write(p, mode)
end

-- Un file per sessione: senza pulizia la cartella cresce senza limite.
-- ponytail: forfiles non provato su Windows, controllare se ponytail-state cresce
local function prune_states(days)
  if not is_shell_safe(state_dir) then return end
  if package.config:sub(1, 1) == "\\" then
    os.execute('forfiles /p "' .. state_dir:gsub("/", "\\") .. '" /d -' .. days .. ' /c "cmd /c del @path" >NUL 2>NUL')
  else
    os.execute('find "' .. state_dir .. '" -type f -mtime +' .. days .. ' -delete 2>/dev/null')
  end
end

return {
  DEFAULT_MODE = DEFAULT_MODE,
  normalize_mode = normalize_mode,
  normalize_persisted_mode = normalize_persisted_mode,
  is_deactivation_command = is_deactivation_command,
  is_shell_safe = is_shell_safe,
  get_config_dir = get_config_dir,
  get_config_path = get_config_path,
  get_claude_dir = get_claude_dir,
  get_default_mode = get_default_mode,
  write_default_mode = write_default_mode,
  -- helper
  dirname = dirname,
  mkdir_p = mkdir_p,
  file_read = file_read,
  file_write = file_write,
  file_exists = file_exists,
  read_input = read_input,
  -- runtime state
  read_mode = read_mode,
  set_mode = set_mode,
  prune_states = prune_states,
}
