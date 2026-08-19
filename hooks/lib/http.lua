-- http.lua — Client HTTP/HTTPS per Lua. Trasporto: curl.
-- Nessuna dipendenza compilata. JSON via dkjson (opzionale).

local M = {}

local IS_WIN = package.config:sub(1, 1) == "\\"

local function shell_quote(s)
  if IS_WIN then return '"' .. s:gsub('"', '\\"') .. '"' end
  return "'" .. s:gsub("'", "'\\''") .. "'"
end

local function tmppath()
  if IS_WIN then
    return (os.getenv("TEMP") or os.getenv("TMP") or ".") ..
           "\\lua_http_" .. tostring({}):sub(8)
  end
  return os.tmpname()
end

local function parse_head(raw)
  local status = tonumber(raw:match("HTTP/%d[%.%d]* (%d+)"))
  local headers = {}
  for line in raw:gmatch("([^\r\n]+)") do
    local k, v = line:match("^([^:]+):%s*(.*)")
    if k then headers[k:lower()] = v:gsub("%s+$", "") end
  end
  return status, headers
end

local function do_request(method, url, req_headers, body, opts)
  local parts = { "curl", "-s", "-S", "-i", "-X", method }

  local timeout = opts and opts.timeout
  if timeout then
    parts[#parts + 1] = "--max-time"
    parts[#parts + 1] = tostring(timeout)
  end

  if opts and opts.follow then parts[#parts + 1] = "-L" end

  req_headers = req_headers or {}
  for k, v in pairs(req_headers) do
    parts[#parts + 1] = "-H"
    parts[#parts + 1] = shell_quote(k .. ": " .. v)
  end

  local body_tmp
  if body and #body > 0 then
    body_tmp = tmppath()
    local f = io.open(body_tmp, "wb")
    if not f then return nil, "impossibile creare file temporaneo" end
    f:write(body)
    f:close()
    parts[#parts + 1] = "--data-binary"
    parts[#parts + 1] = "@" .. shell_quote(body_tmp)
  end

  parts[#parts + 1] = shell_quote(url)

  local pipe = io.popen(table.concat(parts, " "), "r")
  if not pipe then
    if body_tmp then os.remove(body_tmp) end
    return nil, "impossibile eseguire curl"
  end
  local raw = pipe:read("*a")
  pipe:close()
  if body_tmp then os.remove(body_tmp) end

  if not raw or #raw == 0 then return nil, "nessuna risposta da curl" end

  -- con -L (redirect), curl stampa più blocchi di header;
  -- l'ultimo blocco HTTP è quello della risposta finale
  local head, resp_body
  local last_sep = nil
  local pos = 1
  while true do
    local s, e = raw:find("\r?\n\r?\n", pos)
    if not s then break end
    local after = raw:sub(e + 1)
    if after:match("^HTTP/") then
      pos = e + 1
    else
      head = raw:sub(1, s - 1)
      -- prendi solo l'ultimo blocco di header
      local last_http = head:match(".*()HTTP/")
      if last_http then head = head:sub(last_http) end
      resp_body = after
      break
    end
  end

  if not head then
    head = raw:match("^(.-)\r?\n\r?\n")
    resp_body = raw:match("\r?\n\r?\n(.*)$") or ""
  end
  if not head then return nil, "risposta malformata" end

  local status, resp_headers = parse_head(head)
  return { status = status, headers = resp_headers, body = resp_body or "" }
end

----------------------------------------------------------------------------
-- API pubblica
----------------------------------------------------------------------------

function M.request(method, url, opts)
  opts = opts or {}
  return do_request(method:upper(), url, opts.headers, opts.body, opts)
end

function M.get(url, opts)    return M.request("GET", url, opts) end
function M.post(url, opts)   return M.request("POST", url, opts) end
function M.put(url, opts)    return M.request("PUT", url, opts) end
function M.delete(url, opts) return M.request("DELETE", url, opts) end
function M.patch(url, opts)  return M.request("PATCH", url, opts) end

----------------------------------------------------------------------------
-- JSON helper (encode/decode automatico se dkjson è accanto a questo file)
----------------------------------------------------------------------------

local has_json, json
do
  has_json, json = pcall(require, "dkjson")
  if not has_json then
    local src = debug.getinfo(1, "S").source:match("^@?(.*)")
    local dir = src:match("^(.*)[/\\]") or "."
    has_json, json = pcall(dofile, dir .. "/dkjson.lua")
  end
end

function M.json(method, url, data, opts)
  opts = opts or {}
  local h = opts.headers or {}
  h["Content-Type"] = h["Content-Type"] or "application/json"
  h["Accept"]       = h["Accept"]       or "application/json"
  opts.headers = h
  if data ~= nil then
    if not has_json then return nil, "dkjson non trovato, impossibile codificare" end
    opts.body = json.encode(data)
  end
  local resp, err = M.request(method, url, opts)
  if not resp then return nil, err end
  if has_json and resp.body and #resp.body > 0 then
    local decoded = json.decode(resp.body)
    if decoded then resp.data = decoded end
  end
  return resp
end

return M
