#!/usr/bin/env ruby
# frozen_string_literal: true
#
# cp-check.rb — Confronta la versione del Control Plane Hindsight pinnata nel
# .mise.toml (task `control-plane`) con l'ultima pubblicata su npm.
#
# La versione pinnata è la single source of truth: la leggiamo dal .mise.toml
# (pattern `hindsight-control-plane@X.Y.Z`) invece di duplicarla qui, così non
# può divergere dal task che effettivamente avvia il Control Plane.
#
# Uso:   mise run cp-check
# Exit:  0  = sei già all'ultima (o avanti)
#        10 = è disponibile un aggiornamento  (comodo da testare in script/cron)
#        1  = errore (rete, parsing, pin non trovato)
#
# Stampa sempre un blocco JSON con pinned/latest/update_available.

require "json"
require "net/http"
require "uri"
require "rubygems" # Gem::Version

PKG = "@vectorize-io/hindsight-control-plane"
# Il task control-plane (e quindi il pin) vive nel mise.toml alla root di questo repo.
# Path da TRINITY_PLUGIN_DIR se presente (env utente), altrimenti risoluzione relativa:
# scheduler/check_update_*/ -> ../.. = root del repo.
PLUGIN_DIR = ENV.fetch("TRINITY_PLUGIN_DIR") { File.expand_path("../..", __dir__) }
MISE_TOML = File.join(PLUGIN_DIR, "mise.toml")

# Versioni da NON segnalare anche se più recenti del pin: rilasci noti ma scartati.
# La 0.7.0 ha il bug i18n del redirect-loop (vedi il task control-plane nel .mise.toml):
# senza questa lista il check segnalerebbe la 0.7.0 come "novità" a ogni giro, in eterno.
# La 0.7.1 e la 0.7.2 NON sono il fix: loop i18n ancora presente (cp-redirect-test → curl exit 47).
# 0.7.1 verificata il 2026-05-29, 0.7.2 il 2026-06-05. Aggiunte qui per non segnalarle in eterno.
# Quando esce un fix vero (es. 0.7.3) lo supera e scatta l'alert. Override a runtime:
#   CP_IGNORE_VERSIONS="0.7.0,0.7.1,0.7.2,0.7.4"   (lista separata da virgole)
IGNORED_VERSIONS = (ENV["CP_IGNORE_VERSIONS"] || "0.7.0,0.7.1,0.7.2").split(",").map(&:strip).reject(&:empty?)

def pinned_version
  raise "‹.mise.toml› non trovato in #{MISE_TOML}" unless File.exist?(MISE_TOML)

  toml = File.read(MISE_TOML)
  m = toml.match(/hindsight-control-plane@(\d+\.\d+\.\d+(?:[-+][\w.]+)?)/)
  raise "pin `hindsight-control-plane@X.Y.Z` non trovato nel .mise.toml" unless m

  m[1]
end

def latest_version
  # Endpoint "abbreviated" del registry npm: niente auth, payload minimo.
  # Net::HTTP usa OpenSSL, che rispetta SSL_CERT_FILE (impostato nell'[env] del
  # .mise.toml a C:/certs/cacert.pem) → sopravvive al MITM TLS del proxy ENINET.
  uri = URI("https://registry.npmjs.org/#{PKG}/latest")
  res = Net::HTTP.start(uri.host, uri.port, use_ssl: true, open_timeout: 10, read_timeout: 10) do |http|
    http.get(uri.request_uri)
  end
  raise "registry npm ha risposto HTTP #{res.code}" unless res.is_a?(Net::HTTPSuccess)

  JSON.parse(res.body).fetch("version")
end

begin
  pinned = pinned_version
  latest = latest_version

  # Soglia = la versione più alta già vista e scartata (il pin + le ignorate).
  # Segnaliamo un update solo per ciò che la supera davvero.
  baseline = ([pinned] + IGNORED_VERSIONS).map { |v| Gem::Version.new(v) }.max
  update = Gem::Version.new(latest) > baseline

  puts JSON.pretty_generate(
    "package" => PKG,
    "pinned" => pinned,
    "ignored" => IGNORED_VERSIONS,
    "latest" => latest,
    "update_available" => update,
    "checked_at" => Time.now.utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
  )
  exit(update ? 10 : 0)
rescue StandardError => e
  warn "cp-check: ERRORE — #{e.class}: #{e.message}"
  exit 1
end
