#!/usr/bin/env ruby
# frozen_string_literal: true

# Hook PostToolUse — converte un .excalidraw esportato dal canvas MCP nel formato
# nativo Obsidian Excalidraw (.excalidraw.md) e lo PUBBLICA nel vault, rimuovendo
# il grezzo. `export_scene` ha così una semantica unica: "porta in Obsidian".
# Destinazione (ENV OBSIDIAN_VAULT): cartella di default "Excalidraw/" oppure la
# sottocartella di export (relativa al cwd), replicata nel vault; conflitti con
# backup .bak. Senza OBSIDIAN_VAULT ripiega sul .md locale senza rimuovere il grezzo.
#
# Il canvas MCP usa un dialetto semplificato (label sulla shape, start/end con id);
# Excalidraw standard vuole bound text + startBinding/endBinding + metadati completi
# (seed, roundness, stile…). Questo script traduce dal dialetto MCP allo standard.
#
# Rispetto alla conversione interna del server (export_to_excalidraw_url) qui:
#   - il bound text è centrato sulle dimensioni REALI stimate (il server lo ancora
#     in alto a sinistra con width gonfiata → testo decentrato nell'embed statico);
#   - seed/versionNonce sono DETERMINISTICI (CRC32 dell'id), non Math.random:
#     stesso input → stesso output, diff stabili e file testabile;
#   - NON emettiamo "index" fractional: quello del server ("a0","a1",…,"a10") è
#     lessicograficamente disordinato per >10 elementi; il plugin lo rigenera.
#
# Trasformazioni:
#   shape.label.text       → bound text (containerId + boundElements), centrato
#   arrow/line.label.text  → bound text al midpoint dell'elemento lineare
#   arrow/line.start/end   → startBinding/endBinding
#   default Excalidraw completi su ogni elemento (stile, seed, roundness…)
#   ## Text Elements + delimitatori %% attorno al blocco Drawing
#
# Tipi gestiti: rectangle, ellipse, diamond, arrow, line, freedraw, image, text.
# Le immagini referenziano i binari in raw["files"], che vengono preservati.

require "json"
require "zlib"
require "fileutils"
require "pathname"

LINE_HEIGHT = 1.25

# Campi specifici del server MCP da non propagare nel JSON Excalidraw.
SERVER_FIELDS = %w[createdAt updatedAt syncedAt syncTimestamp source version].freeze

# ── Misura testo (stima per-glifo, headless) ────────────────────────────────
# Il server MCP non misura i testi (tiene solo label.text) e nemmeno il server
# stesso ha un canvas: stimiamo per categoria di glifo, più accurato di un
# fattore medio costante, per centrare il bound text già nel JSON salvato.
def char_width_ratio(char)
  case char
  when " "                then 0.28
  when /[iIl.,!|:;'`]/    then 0.30
  when /[ftrJ()\[\]{}\-]/ then 0.40
  when /[mwMW]/           then 0.90
  when /[A-Z0-9]/         then 0.62
  else                         0.50
  end
end

def measure_text(text, font_size, font_family)
  lines = text.to_s.split("\n")
  lines = [""] if lines.empty?
  mono = font_family == 3 # monospace: larghezza uniforme
  widest = lines.map do |line|
    mono ? line.length * 0.60 : line.chars.sum { |c| char_width_ratio(c) }
  end.max
  width  = (widest * font_size).round
  height = (lines.size * font_size * LINE_HEIGHT).round
  [[width, 1].max, [height, 1].max]
end

# ── Helpers ─────────────────────────────────────────────────────────────────
def label_text(shape)
  shape.dig("label", "text")&.strip
end

def text_element_entry(id, text)
  "#{text.strip} ^#{id}"
end

# Estrae [x, y] da un punto, tollerando sia [x, y] sia {"x"=>, "y"=>}.
def point_xy(point)
  return [point[0], point[1]] if point.is_a?(Array)
  return [point["x"], point["y"]] if point.is_a?(Hash)

  [0, 0]
end

# Intero deterministico nel range Excalidraw (0..2^31-1) da una stringa-seme.
# Sostituisce Math.random() del server: stesso id → stesso valore.
def det_int(seed)
  Zlib.crc32(seed) % 2_147_483_647
end

# Normalizza fontFamily a un id numerico (Excalidraw vuole un numero).
FONT_FAMILIES = {
  "virgil" => 1, "hand" => 1, "handwritten" => 1,
  "helvetica" => 2, "sans" => 2, "sans-serif" => 2, "normal" => 2,
  "cascadia" => 3, "mono" => 3, "monospace" => 3, "code" => 3,
  "excalifont" => 5, "nunito" => 6, "lilita" => 7, "lilita one" => 7,
  "comic" => 8, "comic shanns" => 8
}.freeze
def normalize_font_family(font_family)
  return font_family if font_family.is_a?(Numeric)
  return (FONT_FAMILIES[font_family.downcase] || 1) if font_family.is_a?(String)

  1
end

# Default di stile/metadati comuni a ogni elemento Excalidraw standard.
# I valori già presenti nel "core" hanno la precedenza (vedi merge col blocco):
# non sovrascriviamo ciò che l'utente ha impostato. seed/versionNonce derivati
# dall'id → deterministici.
def base_defaults(id)
  {
    "angle" => 0,
    "strokeColor" => "#1e1e1e",
    "backgroundColor" => "transparent",
    "fillStyle" => "solid",
    "strokeWidth" => 2,
    "strokeStyle" => "solid",
    "roughness" => 1,
    "opacity" => 100,
    "groupIds" => [],
    "frameId" => nil,
    "roundness" => nil,
    "seed" => det_int("seed:#{id}"),
    "version" => 1,
    "versionNonce" => det_int("nonce:#{id}"),
    "isDeleted" => false,
    "link" => nil,
    "locked" => false
  }
end

# Unisce il core (campi specifici, in testa per leggibilità) con i default
# mancanti: per le chiavi in comune vince il core.
def with_defaults(core, id)
  core.merge(base_defaults(id)) { |_key, from_core, _from_defaults| from_core }
end

# ── Decoratori (dialetto MCP → elemento Excalidraw standard completo) ────────
def decorate_shape(el, bound_elements)
  with_defaults({
    "id" => el["id"], "type" => el["type"],
    "x" => el["x"], "y" => el["y"],
    "width" => el["width"], "height" => el["height"],
    "strokeColor" => el["strokeColor"] || "#1e1e1e",
    "backgroundColor" => el["backgroundColor"] || "transparent",
    "fillStyle" => el["fillStyle"] || "solid",
    "strokeWidth" => el["strokeWidth"] || 2,
    "strokeStyle" => el["strokeStyle"] || "solid",
    "roughness" => el["roughness"] || 1,
    "opacity" => el["opacity"] || 100,
    "roundness" => el["roundness"] || { "type" => 3 },
    "boundElements" => (bound_elements.empty? ? nil : bound_elements)
  }, el["id"])
end

# Elemento lineare (arrow e line condividono points + binding). La differenza è
# solo l'arrowhead: l'arrow ha la punta in coda, la line no.
def decorate_linear(el, bound_elements, is_arrow)
  pts = el["points"] || [[0, 0], [0, 0]]
  xs = pts.map { |p| point_xy(p)[0] }
  ys = pts.map { |p| point_xy(p)[1] }
  with_defaults({
    "id" => el["id"], "type" => el["type"],
    "x" => el["x"], "y" => el["y"],
    "width" => el["width"] || (xs.max - xs.min),
    "height" => el["height"] || (ys.max - ys.min),
    "strokeColor" => el["strokeColor"] || "#1e1e1e",
    "backgroundColor" => el["backgroundColor"] || "transparent",
    "fillStyle" => el["fillStyle"] || "solid",
    "strokeWidth" => el["strokeWidth"] || 2,
    "strokeStyle" => el["strokeStyle"] || "solid",
    "roughness" => el["roughness"] || 1,
    "opacity" => el["opacity"] || 100,
    "roundness" => el.key?("roundness") ? el["roundness"] : { "type" => 2 },
    "points" => pts,
    "lastCommittedPoint" => el["lastCommittedPoint"],
    "startBinding" => el["startBinding"],
    "endBinding" => el["endBinding"],
    "startArrowhead" => el["startArrowhead"],
    "endArrowhead" => el.key?("endArrowhead") ? el["endArrowhead"] : (is_arrow ? "arrow" : nil),
    "elbowed" => el["elbowed"] || false,
    "boundElements" => (bound_elements.empty? ? nil : bound_elements)
  }, el["id"])
end

# Tratto a mano libera: points + pressures + simulatePressure.
def decorate_freedraw(el)
  with_defaults({
    "id" => el["id"], "type" => "freedraw",
    "x" => el["x"], "y" => el["y"],
    "width" => el["width"], "height" => el["height"],
    "strokeColor" => el["strokeColor"] || "#1e1e1e",
    "backgroundColor" => el["backgroundColor"] || "transparent",
    "fillStyle" => el["fillStyle"] || "solid",
    "strokeWidth" => el["strokeWidth"] || 2,
    "strokeStyle" => el["strokeStyle"] || "solid",
    "roughness" => el["roughness"] || 1,
    "opacity" => el["opacity"] || 100,
    "roundness" => nil,
    "points" => el["points"] || [],
    "pressures" => el["pressures"] || [],
    "simulatePressure" => el.key?("simulatePressure") ? el["simulatePressure"] : true,
    "lastCommittedPoint" => el["lastCommittedPoint"],
    "boundElements" => el["boundElements"]
  }, el["id"])
end

# Immagine: riferisce un file in `files` (top-level) via fileId. Niente tratto
# handdrawn (roughness 0). I dati binari restano in raw["files"], preservati così.
def decorate_image(el)
  with_defaults({
    "id" => el["id"], "type" => "image",
    "x" => el["x"], "y" => el["y"],
    "width" => el["width"], "height" => el["height"],
    "strokeColor" => el["strokeColor"] || "transparent",
    "backgroundColor" => el["backgroundColor"] || "transparent",
    "fillStyle" => el["fillStyle"] || "solid",
    "strokeWidth" => el["strokeWidth"] || 1,
    "strokeStyle" => el["strokeStyle"] || "solid",
    "roughness" => el["roughness"] || 0,
    "opacity" => el["opacity"] || 100,
    "roundness" => nil,
    "fileId" => el["fileId"],
    "scale" => el["scale"] || [1, 1],
    "status" => el["status"] || "saved",
    "crop" => el["crop"],
    "boundElements" => el["boundElements"]
  }, el["id"])
end

# Bound text centrato in (cx, cy) con dimensioni reali stimate.
def bound_text(id, container_id, cx, cy, text, font_size, font_family, stroke_color)
  tw, th = measure_text(text, font_size, font_family)
  with_defaults({
    "id" => id, "type" => "text",
    "x" => (cx - tw / 2.0).round, "y" => (cy - th / 2.0).round,
    "width" => tw, "height" => th,
    "strokeColor" => stroke_color || "#1e1e1e",
    "strokeWidth" => 1,
    "roundness" => nil,
    "boundElements" => nil,
    "text" => text, "originalText" => text,
    "fontSize" => font_size, "fontFamily" => font_family,
    "textAlign" => "center", "verticalAlign" => "middle",
    "autoResize" => true, "lineHeight" => LINE_HEIGHT,
    "containerId" => container_id
  }, id)
end

# Text element libero (non bound): preserva allineamento e posizione proprie.
def decorate_text(el)
  ff = normalize_font_family(el["fontFamily"])
  fs = el["fontSize"] || 20
  txt = el["text"].to_s
  tw, th = measure_text(txt, fs, ff)
  with_defaults({
    "id" => el["id"], "type" => "text",
    "x" => el["x"], "y" => el["y"],
    "width" => el["width"] || tw, "height" => el["height"] || th,
    "strokeColor" => el["strokeColor"] || "#1e1e1e",
    "strokeWidth" => 1,
    "roundness" => nil,
    "boundElements" => el["boundElements"],
    "text" => txt, "originalText" => el["originalText"] || txt,
    "fontSize" => fs, "fontFamily" => ff,
    "textAlign" => el["textAlign"] || "left",
    "verticalAlign" => el["verticalAlign"] || "top",
    "autoResize" => true, "lineHeight" => LINE_HEIGHT,
    "containerId" => el["containerId"]
  }, el["id"])
end

# Elementi non gestiti specificamente (line, image…): default + pulizia campi server.
def decorate_generic(el)
  cleaned = el.reject { |k, _| SERVER_FIELDS.include?(k) }
  with_defaults(cleaned, el["id"])
end

def build_markdown(input_path)
  raw = JSON.parse(File.read(input_path, encoding: "UTF-8"))
  elements = raw["elements"] || []

  new_elements = []
  text_entries = []

  # Mappa shape → arrow IDs per popolare boundElements
  arrow_refs = Hash.new { |h, k| h[k] = [] }
  elements.each do |el|
    next unless el["type"] == "arrow"

    sid = el.dig("start", "id")
    eid = el.dig("end", "id")
    arrow_refs[sid] << el["id"] if sid
    arrow_refs[eid] << el["id"] if eid
  end

  elements.each do |el|
    case el["type"]
    when "rectangle", "ellipse", "diamond"
      text = label_text(el)
      bound = arrow_refs[el["id"]].map { |aid| { "id" => aid, "type" => "arrow" } }

      if text && !text.empty?
        lid = "#{el["id"]}-label"
        fs = el["fontSize"] || 14
        ff = normalize_font_family(el["fontFamily"])
        cx = el["x"] + el["width"] / 2.0
        cy = el["y"] + el["height"] / 2.0
        label_el = bound_text(lid, el["id"], cx, cy, text, fs, ff, el["strokeColor"])
        bound << { "id" => lid, "type" => "text" }

        text_entries << text_element_entry(lid, text)
        new_elements << decorate_shape(el, bound) << label_el
      else
        new_elements << decorate_shape(el, bound)
      end

    when "arrow", "line"
      is_arrow = el["type"] == "arrow"
      sid = el.dig("start", "id")
      eid = el.dig("end", "id")
      el["startBinding"] = { "elementId" => sid, "focus" => 0, "gap" => 8 } if sid
      el["endBinding"]   = { "elementId" => eid, "focus" => 0, "gap" => 8 } if eid

      text = label_text(el)

      if text && !text.empty?
        # Le label degli elementi lineari sono bound text al midpoint, non una
        # proprietà "text" sull'elemento (che non verrebbe renderizzata).
        lid = "#{el["id"]}-label"
        fs = el["fontSize"] || 16
        ff = normalize_font_family(el["fontFamily"])
        points = el["points"] || [[0, 0]]
        x0, y0 = point_xy(points.first)
        x1, y1 = point_xy(points.last)
        cx = el["x"] + (x0 + x1) / 2.0
        cy = el["y"] + (y0 + y1) / 2.0
        label_el = bound_text(lid, el["id"], cx, cy, text, fs, ff, "#1e1e1e")

        text_entries << text_element_entry(lid, text)
        new_elements << decorate_linear(el, [{ "id" => lid, "type" => "text" }], is_arrow) << label_el
      else
        new_elements << decorate_linear(el, [], is_arrow)
      end

    when "freedraw"
      new_elements << decorate_freedraw(el)

    when "image"
      new_elements << decorate_image(el)

    when "text"
      t = el["text"]&.strip
      text_entries << text_element_entry(el["id"], t) if t && !t.empty?
      new_elements << decorate_text(el)

    else
      new_elements << decorate_generic(el)
    end
  end

  text_block = text_entries.map { |e| "\n#{e}" }.join

  output = <<~MD
    ---

    excalidraw-plugin: parsed
    tags: [excalidraw]

    ---
    ==⚠  Switch to EXCALIDRAW VIEW in the MORE OPTIONS menu of this document. ⚠== You can decompress Drawing data with the command palette: 'Decompress current Excalidraw file'. For more info check in plugin settings under 'Saving'

    # Excalidraw Data

    ## Text Elements#{text_block}

    %%
    ## Drawing
    ```json
    #{JSON.pretty_generate({
      "type" => raw["type"] || "excalidraw",
      "version" => raw["version"] || 2,
      "source" => raw["source"] || "mcp-excalidraw-server",
      "elements" => new_elements,
      "appState" => raw["appState"] || { "viewBackgroundColor" => "#ffffff", "gridSize" => nil },
      "files" => raw["files"] || {}
    })}
    ```
    %%
  MD

  [output, elements.size, text_entries.size]
end

# Calcola la destinazione nel vault a partire dal path di export.
# - vault = ENV["OBSIDIAN_VAULT"] (assente ⇒ nessuna pubblicazione, fallback locale);
# - sottocartella = path dell'export relativo al cwd; se l'export è nella root del
#   progetto (o fuori da esso) si usa la cartella di default "Excalidraw".
def vault_destination(input_path, cwd)
  vault = ENV["OBSIDIAN_VAULT"]
  return nil if vault.nil? || vault.strip.empty?

  base = File.basename(input_path, ".excalidraw")
  src_dir  = Pathname.new(File.dirname(input_path).tr("\\", "/"))
  base_dir = Pathname.new(cwd.to_s.tr("\\", "/"))
  rel = (src_dir.relative_path_from(base_dir).to_s rescue ".")
  subdir = (rel == "." || rel.start_with?("..")) ? "Excalidraw" : rel
  File.join(vault.tr("\\", "/"), subdir, "#{base}.excalidraw.md")
end

# Pubblica il .excalidraw.md nel vault (backup .bak sui conflitti) e rimuove il
# .excalidraw grezzo. Se OBSIDIAN_VAULT non è impostato, ripiega sul .md locale
# accanto al grezzo (che NON viene rimosso).
def publish(input_path, markdown, cwd, n_el, n_txt)
  dest = vault_destination(input_path, cwd)

  unless dest
    local = input_path.sub(/\.excalidraw\z/, ".excalidraw.md")
    File.write(local, markdown, encoding: "UTF-8")
    puts "excalidraw-to-obsidian: OBSIDIAN_VAULT non impostato → #{File.basename(local)} in locale (grezzo non rimosso)"
    return
  end

  FileUtils.mkdir_p(File.dirname(dest))
  FileUtils.cp(dest, "#{dest}.bak") if File.exist?(dest) # backup prima di sovrascrivere
  File.write(dest, markdown, encoding: "UTF-8")
  File.delete(input_path) if File.exist?(input_path) # rimuove il grezzo temporaneo
  puts "excalidraw-to-obsidian: pubblicato in #{dest} (#{n_el} elem, #{n_txt} testi); grezzo rimosso"
end

# ── Main ────────────────────────────────────────────────────────────────────
# Il path del .excalidraw arriva in due modi:
#   - da stdin, come JSON dell'hook (tool_input.filePath) → uso normale (PostToolUse);
#   - da ARGV[0], come path diretto → uso manuale da terminale / fallback.
# ARGV ha la precedenza; lo stdin viene letto solo se non è un terminale
# interattivo, per non bloccare l'esecuzione manuale in attesa di input.
input = ARGV[0]
cwd = Dir.pwd

if input.nil? && !$stdin.tty?
  hook_input = JSON.parse($stdin.read) rescue {}
  input = hook_input.dig("tool_input", "filePath")
  cwd = hook_input["cwd"] || cwd
end

unless input && input.end_with?(".excalidraw")
  puts "excalidraw-to-obsidian: nessun filePath .excalidraw, skip"
  exit 0
end

# Il filePath può essere relativo al cwd: risolvilo se necessario.
unless File.exist?(input)
  candidate = File.join(cwd, input)
  input = candidate if File.exist?(candidate)
end

unless File.exist?(input)
  puts "excalidraw-to-obsidian: file non trovato: #{input}"
  exit 0
end

begin
  markdown, n_el, n_txt = build_markdown(input)
  publish(input, markdown, cwd, n_el, n_txt)
rescue JSON::ParserError => e
  puts "excalidraw-to-obsidian: JSON non valido in #{File.basename(input)}: #{e.message}"
  exit 0
rescue StandardError => e
  puts "excalidraw-to-obsidian: errore conversione: #{e.message}"
  exit 0
end
