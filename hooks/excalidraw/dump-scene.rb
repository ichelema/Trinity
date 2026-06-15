#!/usr/bin/env ruby
# frozen_string_literal: true

# Helper deterministico per il workflow "file-edit".
#
# Scarica la scena dal canvas MCP (GET /api/elements) e scrive un .excalidraw
# valido in locale, SENZA passare da `export_scene` — che ora pubblica nel vault
# e rimuove il grezzo. Serve a ottenere il JSON da modificare a mano e poi
# reimportare con `import_scene(mode: "replace")`.
#
# Produce lo stesso formato di `export_scene` (dialetto MCP: label sulla shape,
# start/end con id), quindi è un rimpiazzo diretto nel flusso file-edit.
#
# Uso:  ruby dump-scene.rb <output.excalidraw> [server_url]
# Server di default: $EXPRESS_SERVER_URL oppure http://127.0.0.1:3000

require "json"
require "net/http"
require "uri"

out = ARGV[0]
unless out && out.end_with?(".excalidraw")
  warn "dump-scene: specifica un path di output che termina in .excalidraw"
  exit 1
end
base = ARGV[1] || ENV["EXPRESS_SERVER_URL"] || "http://127.0.0.1:3000"

def fetch_json(url)
  res = Net::HTTP.get_response(URI(url))
  res.is_a?(Net::HTTPSuccess) ? JSON.parse(res.body) : nil
rescue StandardError
  nil
end

elements_data = fetch_json("#{base}/api/elements")
if elements_data.nil?
  warn "dump-scene: impossibile contattare il canvas su #{base} (il server è attivo?)"
  exit 1
end

elements = elements_data["elements"] || []
files_data = fetch_json("#{base}/api/files")
files = (files_data && files_data["files"]) || {}

scene = {
  "type" => "excalidraw",
  "version" => 2,
  "source" => "mcp-excalidraw-server",
  "elements" => elements,
  "appState" => { "viewBackgroundColor" => "#ffffff", "gridSize" => nil },
  "files" => files
}

File.write(out, JSON.pretty_generate(scene), encoding: "UTF-8")
puts "dump-scene: #{elements.size} elementi → #{out}"
