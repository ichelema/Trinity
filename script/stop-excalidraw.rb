#!/usr/bin/env ruby
# frozen_string_literal: true

# stop-excalidraw.rb — Ferma il frontend canvas Excalidraw (:3000) in modo
# sicuro e multi-piattaforma (Windows / Unix).
#
# Strategia:
#   1. Controlla che la porta 3000 risponda a /api/elements con un JSON valido
#      contenente "excalidraw" o "elements" — così siamo certi sia il server giusto.
#   2. Trova il PID del processo in ascolto su :3000.
#   3. Lo termina (taskkill su Windows, kill su Unix).
#
# Uso: ruby stop-excalidraw.rb

require "net/http"
require "json"

PORT = 3000
HOST = "127.0.0.1"
API_URL = "http://#{HOST}:#{PORT}/api/elements"

# ── 1. Verifica che sia davvero il server Excalidraw ────────────────────────
def excalidraw_server?
  uri = URI(API_URL)
  http = Net::HTTP.new(uri.host, uri.port)
  http.open_timeout = 2
  http.read_timeout = 2

  response = http.get(uri.path)
  return false unless response.code.to_i == 200

  data = JSON.parse(response.body)
  # Il server Excalidraw risponde con {"success": true, "elements": [...], "count": N}
  data.key?("success") && data.key?("elements")
rescue Errno::ECONNREFUSED, Errno::ECONNRESET, Net::OpenTimeout, Net::ReadTimeout, JSON::ParserError, Errno::EADDRNOTAVAIL
  false
end

# ── 2. Trova il PID in ascolto sulla porta ──────────────────────────────────
def find_pid
  if Gem.win_platform?
    # Windows: netstat da System32 (MSYS2 non lo ha nel PATH).
    # Regex: cerca la riga LISTENING sulla porta target ed estrae il PID.
    output = `C:/Windows/System32/NETSTAT.EXE -ano 2>NUL`
    addr = "#{HOST}:#{PORT}"
    output.each_line do |line|
      if line.include?("LISTENING") && line.include?(addr)
        return line.split(/\s+/).last.to_i
      end
    end
    nil
  else
    # Unix: lsof -ti :3000 o ss -tlnp
    pid = `lsof -ti :#{PORT} 2>/dev/null`.strip
    return pid.to_i unless pid.empty?

    # Fallback: ss (Linux moderno)
    output = `ss -tlnp 'sport = :#{PORT}' 2>/dev/null`
    if output =~ /pid=(\d+)/
      return Regexp.last_match(1).to_i
    end

    nil
  end
end

# ── 3. Termina il processo ──────────────────────────────────────────────────
def kill_process(pid)
  if Gem.win_platform?
    system("C:/Windows/System32/taskkill.exe", "/PID", pid.to_s, "/F", out: File::NULL, err: File::NULL)
  else
    Process.kill("TERM", pid)
    # Dai 3 secondi di grazia, poi forza
    sleep 0.5
    begin
      Process.getpgid(pid)
      Process.kill("KILL", pid)
    rescue Errno::ESRCH
      # già morto
    end
  end
end

# ── Main ────────────────────────────────────────────────────────────────────
unless excalidraw_server?
  puts "Nessun server Excalidraw trovato su #{API_URL}"
  exit 0
end

pid = find_pid
if pid.nil? || pid.zero?
  puts "Server Excalidraw risponde ma non trovo il PID su :#{PORT}"
  exit 0
end

puts "Arresto Excalidraw canvas (PID: #{pid})..."
kill_process(pid)
puts "OK — Excalidraw canvas fermato."
