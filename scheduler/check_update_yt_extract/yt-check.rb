#!/usr/bin/env ruby
# frozen_string_literal: true
#
# yt-check.rb — Confronta la versione INSTALLATA del plugin yt-extract
# (git clone in E:/AI/tools/claude-code-youtube-extract) con l'ultima
# release pubblicata su GitHub (muckybuzzwoo/claude-code-youtube-extract).
#
# La versione locale viene letta dal CHANGELOG.md del clone (prima riga ## [X.Y.Z]).
# La versione remota viene letta dall'API GitHub /releases/latest, con fallback
# a /tags se non esistono release formali.
#
# Uso:   mise run yt-check
# Exit:  0  = sei già all'ultima (o avanti)
#        10 = è disponibile un aggiornamento su GitHub
#        1  = errore (rete, parsing, clone non trovato)

require "json"
require "net/http"
require "uri"
require "rubygems" # Gem::Version

REPO      = "muckybuzzwoo/claude-code-youtube-extract"
# Sovrascrivibile via env per host diversi (es. Linux con clone in altra posizione).
CLONE_DIR = ENV.fetch("YT_CLONE_DIR", "E:/AI/tools/claude-code-youtube-extract")

# Legge la versione dalla prima riga ## [X.Y.Z] del CHANGELOG.md locale.
def installed_version
  changelog = File.join(CLONE_DIR, "CHANGELOG.md")
  raise "CHANGELOG.md non trovato in #{CLONE_DIR}" unless File.exist?(changelog)

  m = File.read(changelog).match(/^##\s+\[(\d+\.\d+\.\d+)\]/)
  raise "Versione non trovata nel CHANGELOG.md" unless m

  m[1]
end

# Ultima versione su GitHub.
# Prova /releases/latest (release formale con tag), poi /tags come fallback.
# Net::HTTP + SSL_CERT_FILE del .mise.toml → supera il MITM aziendale.
def latest_github_version
  uri = URI("https://api.github.com/repos/#{REPO}/releases/latest")
  res = Net::HTTP.start(uri.host, uri.port, use_ssl: true, open_timeout: 10, read_timeout: 10) do |http|
    http.get(uri.request_uri, "User-Agent" => "Trinity-scheduler/1.0")
  end

  if res.is_a?(Net::HTTPSuccess)
    tag = JSON.parse(res.body).fetch("tag_name", nil)
    return tag.sub(/\Av/, "") if tag && !tag.empty?
  end

  # Fallback: lista dei tag in ordine di creazione (primo = più recente).
  uri = URI("https://api.github.com/repos/#{REPO}/tags")
  res = Net::HTTP.start(uri.host, uri.port, use_ssl: true, open_timeout: 10, read_timeout: 10) do |http|
    http.get(uri.request_uri, "User-Agent" => "Trinity-scheduler/1.0")
  end
  raise "GitHub API ha risposto HTTP #{res.code}" unless res.is_a?(Net::HTTPSuccess)

  tags = JSON.parse(res.body)
  raise "Nessun tag trovato su #{REPO}" if tags.empty?

  tags.first.fetch("name").sub(/\Av/, "")
end

begin
  inst   = installed_version
  latest = latest_github_version

  update = Gem::Version.new(latest) > Gem::Version.new(inst)

  puts JSON.pretty_generate(
    "repo"             => REPO,
    "installed"        => inst,
    "installed_from"   => CLONE_DIR,
    "latest_github"    => latest,
    "update_available" => update,
    "checked_at"       => Time.now.utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
  )
  exit(update ? 10 : 0)
rescue StandardError => e
  warn "yt-check: ERRORE — #{e.class}: #{e.message}"
  exit 1
end
