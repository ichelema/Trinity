#!/usr/bin/env ruby
# frozen_string_literal: true
#
# cp-check.rb — Segnala quando esce una NUOVA release del Control Plane
# Hindsight su npm.
#
# Il pin di versione nel mise.toml non esiste più (rimosso il 2026-07-31,
# commit 5723fd0): il task `control-plane` lancia sempre l'ultima via
# `npx --yes`, quindi non c'è niente da "alzare" a mano. Questo check serve
# solo ad accorgersi che una release nuova esiste — per leggerne i breaking
# changes e valutare `mise run install-hindsight` per allineare l'API.
#
# La baseline è l'ultima versione già vista, salvata in cp-last-seen.state
# accanto a questo script (gitignored via *.state). Si auto-avanza a ogni
# rilevamento: una release nuova viene segnalata una volta sola.
# Primo run (file di stato assente): seed silenzioso alla latest, exit 0.
#
# Uso:   mise run cp-check
# Exit:  0  = nessuna novità rispetto all'ultima vista
#        10 = è uscita una release nuova (segnalata ora, poi silenzio)
#        1  = errore (rete, parsing)
#
# Stampa sempre un blocco JSON con last_seen/latest/update_available.

require "json"
require "net/http"
require "uri"
require "rubygems" # Gem::Version

PKG = "@vectorize-io/hindsight-control-plane"
STATE_FILE = File.join(__dir__, "cp-last-seen.state")

def last_seen_version
  return nil unless File.exist?(STATE_FILE)

  v = File.read(STATE_FILE).strip
  v.empty? ? nil : v
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
  last_seen = last_seen_version
  latest = latest_version

  # Primo run senza stato: la latest è già quella che npx userebbe comunque,
  # segnalarla non avrebbe senso → seed silenzioso.
  update = !last_seen.nil? && Gem::Version.new(latest) > Gem::Version.new(last_seen)

  puts JSON.pretty_generate(
    "package" => PKG,
    "last_seen" => last_seen,
    "latest" => latest,
    "update_available" => update,
    "checked_at" => Time.now.utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
  )

  # Stato aggiornato DOPO la stampa: se la scrittura fallisce l'output resta
  # comunque completo (lezione da hindsight-failcheck.sh).
  File.write(STATE_FILE, "#{latest}\n") if last_seen.nil? || update

  exit(update ? 10 : 0)
rescue StandardError => e
  warn "cp-check: ERRORE — #{e.class}: #{e.message}"
  exit 1
end
