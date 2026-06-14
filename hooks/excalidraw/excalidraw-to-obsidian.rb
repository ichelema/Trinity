#!/usr/bin/env ruby
# frozen_string_literal: true

# Hook PostToolUse — converte automaticamente un .excalidraw esportato dal canvas MCP
# nel formato nativo Obsidian Excalidraw (.excalidraw.md).
#
# Trasformazioni:
#   shape.label.text  → elemento text separato con containerId + boundElements
#   arrow.label.text  → arrow.text
#   arrow.start/end   → arrow.startBinding/endBinding
#   ## Text Elements  → allineata con gli ID JSON
#   %%                → aggiunti attorno al blocco Drawing

require "json"

def label_text(shape)
  shape.dig("label", "text")&.strip
end

def text_element_entry(id, text)
  "#{text.lines.first.strip} ^#{id}"
end

def convert(input_path, output_path)
  raw = JSON.parse(File.read(input_path, encoding: "UTF-8"))
  elements = raw["elements"]

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

      # Popola boundElements con frecce
      el["boundElements"] ||= []
      arrow_refs[el["id"]].each do |aid|
        unless el["boundElements"].any? { |be| be["id"] == aid }
          el["boundElements"] << { "id" => aid, "type" => "arrow" }
        end
      end

      if text && !text.empty?
        lid = "#{el["id"]}-label"
        label_el = {
          "id" => lid, "type" => "text", "containerId" => el["id"],
          "x" => el["x"] + 10, "y" => el["y"] + 10,
          "width" => el["width"] - 20, "height" => el["height"] - 20,
          "text" => text, "fontSize" => el["fontSize"] || 14,
          "fontFamily" => el["fontFamily"], "textAlign" => "center", "verticalAlign" => "middle"
        }.compact

        el["boundElements"] << { "id" => lid, "type" => "text" }
        el.delete("label")
        el.delete("fontSize")
        el.delete("fontFamily")

        text_entries << text_element_entry(lid, text)
        new_elements << el << label_el
      else
        new_elements << el
      end

    when "arrow"
      text = label_text(el)
      el["text"] = text if text
      el.delete("label")

      sid = el.dig("start", "id")
      eid = el.dig("end", "id")
      el["startBinding"] = { "elementId" => sid, "focus" => 0, "gap" => 8 } if sid
      el["endBinding"]   = { "elementId" => eid, "focus" => 0, "gap" => 8 } if eid
      el.delete("start")
      el.delete("end")

      new_elements << el

    when "text"
      t = el["text"]&.strip
      text_entries << text_element_entry(el["id"], t) if t && !t.empty?
      new_elements << el

    else
      new_elements << el
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
      "appState" => raw["appState"] || { "viewBackgroundColor" => "#ffffff", "gridSize" => nil }
    })}
    ```
    %%
  MD

  File.write(output_path, output)
  puts "excalidraw-to-obsidian: #{File.basename(input_path)} → #{File.basename(output_path)} (#{elements.size} elem, #{text_entries.size} testi)"
end

# ── Main ────────────────────────────────────────────────────────────────────
# L'hook riceve l'input JSON via stdin con i dettagli del tool call.
# Estrae il filePath dai parametri e converte.
raw_input = $stdin.read
hook_input = JSON.parse(raw_input) rescue {}
tool_input = hook_input.dig("tool_input") || {}

input = tool_input["filePath"]
unless input && input.end_with?(".excalidraw")
  puts "excalidraw-to-obsidian: nessun filePath .excalidraw, skip"
  exit 0
end

# Il filePath può essere relativo al cwd del progetto: risolvilo se necessario.
unless File.exist?(input)
  cwd = hook_input["cwd"] || Dir.pwd
  candidate = File.join(cwd, input)
  input = candidate if File.exist?(candidate)
end

unless File.exist?(input)
  puts "excalidraw-to-obsidian: file non trovato: #{input}"
  exit 0
end

output = input.sub(/\.excalidraw\z/, ".excalidraw.md")
convert(input, output)
