#!/usr/bin/env ruby
# frozen_string_literal: true

# Bonifica la cache dei plugin Claude Code rimuovendo le copie-versione orfane.
#
# Ogni `claude plugin update` salva uno snapshot completo del plugin in
#   ~/.claude/plugins/cache/<marketplace>/<plugin>/<versione>/
# e non ripulisce mai le versioni precedenti: la cache cresce di ~10 MB a ogni
# bump. Questo script tiene SOLO la versione attiva (quella indicata in
# installed_plugins.json) ed elimina le sottocartelle-versione orfane.
#
# Idempotente: se non ci sono orfane non fa nulla. Pensato come step post-update
# (vedi task mise `clean-plugin-cache`).

require "json"
require "fileutils"

# Ruby gira nativo Windows: la home con .claude è in USERPROFILE, non in $HOME (MSYS).
base = ENV["USERPROFILE"] || Dir.home
plugins_dir = File.join(base, ".claude", "plugins")
installed = File.join(plugins_dir, "installed_plugins.json")

abort "installed_plugins.json non trovato: #{installed}" unless File.exist?(installed)

# Dimensione ricorsiva di una cartella, in byte.
def dir_size(path)
  Dir.glob(File.join(path, "**", "*"), File::FNM_DOTMATCH)
     .select { |f| File.file?(f) }
     .sum { |f| File.size(f) }
end

data = JSON.parse(File.read(installed))
removed = 0
freed = 0

data.fetch("plugins", {}).each do |key, entries|
  Array(entries).each do |entry|
    active = entry["version"]
    install_path = entry["installPath"].to_s.tr("\\", "/")
    next if active.nil? || install_path.empty?

    plugin_dir = File.dirname(install_path) # .../<marketplace>/<plugin>
    next unless Dir.exist?(plugin_dir)

    Dir.children(plugin_dir).each do |ver|
      path = File.join(plugin_dir, ver)
      next unless File.directory?(path)
      next if ver == active # mai toccare la versione attiva

      size = dir_size(path)
      FileUtils.rm_rf(path)
      removed += 1
      freed += size
      puts "[#{key}] rimossa versione orfana #{ver} (#{(size / 1_048_576.0).round(1)} MB)"
    end
  end
end

if removed.zero?
  puts "Cache pulita: nessuna versione orfana da rimuovere."
else
  puts "Rimosse #{removed} versioni orfane, recuperati #{(freed / 1_048_576.0).round(1)} MB."
end
