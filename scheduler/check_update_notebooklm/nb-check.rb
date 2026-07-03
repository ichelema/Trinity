#!/usr/bin/env ruby
# frozen_string_literal: true
#
# nb-check.rb — Confronta la versione INSTALLATA di notebooklm-py
# (flat-extract in E:/AI/tools/notebooklm) con l'ultima pubblicata su PyPI.
#
# notebooklm-py non è installato col pip di mise ma estratto manualmente in
# modalità exe-free, quindi leggiamo la versione direttamente dal dist-info
# nella cartella di installazione invece di usare importlib.metadata.
# La soglia si alza da sola dopo ogni upgrade: niente da toccare qui.
#
# Uso:   mise run nb-check
# Exit:  0  = sei già all'ultima (o avanti)
#        10 = è disponibile un aggiornamento su PyPI
#        1  = errore (rete, parsing, dist-info non trovato)

require "json"
require "net/http"
require "uri"
require "rubygems" # Gem::Version

PKG      = "notebooklm-py"
INST_DIR = "E:/AI/tools/notebooklm"

# Legge la versione dal campo "Version:" nel METADATA del dist-info.
# Il dist-info si chiama notebooklm_py-X.Y.Z.dist-info; facciamo un glob
# per trovarlo automaticamente senza dover aggiornare questo script dopo ogni upgrade.
def installed_version
  pattern = File.join(INST_DIR, "notebooklm_py-*.dist-info", "METADATA")
  files = Dir.glob(pattern)
  raise "Nessun dist-info trovato in #{INST_DIR} (cerca: #{pattern})" if files.empty?

  # Se ne trovasse più d'uno (residui di upgrade), prende il più recente per nome.
  metadata = File.read(files.sort.last)
  m = metadata.match(/^Version:\s*(.+)$/)
  raise "Campo 'Version:' non trovato nel METADATA" unless m

  m[1].strip
end

# Versione più recente su PyPI.
# Net::HTTP usa OpenSSL, che rispetta SSL_CERT_FILE (impostato nell'[env] del
# .mise.toml a C:/certs/cacert.pem) → sopravvive al MITM TLS del proxy ENINET.
def latest_pypi_version
  uri = URI("https://pypi.org/pypi/#{PKG}/json")
  res = Net::HTTP.start(uri.host, uri.port, use_ssl: true, open_timeout: 10, read_timeout: 10) do |http|
    http.get(uri.request_uri)
  end
  raise "PyPI ha risposto HTTP #{res.code} per #{PKG}" unless res.is_a?(Net::HTTPSuccess)

  JSON.parse(res.body).fetch("info").fetch("version")
end

begin
  inst   = installed_version
  latest = latest_pypi_version

  update = Gem::Version.new(latest) > Gem::Version.new(inst)

  puts JSON.pretty_generate(
    "package"          => PKG,
    "installed"        => inst,
    "installed_from"   => "#{INST_DIR} (flat-extract exe-free, non pip)",
    "latest_pypi"      => latest,
    "update_available" => update,
    "checked_at"       => Time.now.utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
  )
  exit(update ? 10 : 0)
rescue StandardError => e
  warn "nb-check: ERRORE — #{e.class}: #{e.message}"
  exit 1
end
