#!/usr/bin/env ruby
# frozen_string_literal: true
#
# api-check.rb — Confronta la versione INSTALLATA di hindsight-api e
# hindsight-api-slim con l'ultima pubblicata su PyPI.
#
# A differenza del Control Plane (cp-check.rb), qui NON c'è un pin di versione:
# il task `install-hindsight` del .mise.toml fa `pip install --upgrade hindsight-api`,
# quindi la "single source of truth" è la versione effettivamente installata nel
# Python di mise. La leggiamo a runtime via importlib.metadata invece di pinnarla
# da qualche parte, così la soglia si alza da sola dopo ogni upgrade.
#
# Uso:   mise run api-check
# Exit:  0  = sei già all'ultima (o avanti) su TUTTI i pacchetti
#        10 = è disponibile un aggiornamento per almeno un pacchetto
#        1  = errore (rete, parsing, python non raggiungibile)
#
# Stampa sempre un blocco JSON con un record per pacchetto (installed/latest/update_available).

require "json"
require "net/http"
require "uri"
require "rubygems" # Gem::Version

PKGS = %w[hindsight-api hindsight-api-slim].freeze

# Versioni da NON segnalare anche se più recenti dell'installata: rilasci noti ma
# scartati (es. una release con un bug che ti costringe a restare indietro). Vuota
# di default — qui di solito non serve, perché la baseline è già la versione
# installata. Override a runtime (lista separata da virgole, applicata a entrambi):
#   API_IGNORE_VERSIONS="0.7.2,0.7.3"
IGNORED_VERSIONS = (ENV["API_IGNORE_VERSIONS"] || "").split(",").map(&:strip).reject(&:empty?)

# Legge in un colpo solo le versioni installate dei pacchetti chiesti, interrogando
# il Python di mise (lo stesso che `pip install` aggiorna, perché gira nel suo PATH).
# Usa importlib.metadata — non avvia il server, è istantaneo. Pacchetto assente → nil.
def installed_versions(pkgs)
  pylist = "[" + pkgs.map { |p| "'#{p}'" }.join(", ") + "]"
  script = <<~PY
    import json, importlib.metadata as md
    def v(p):
        try:
            return md.version(p)
        except Exception:
            return None
    print(json.dumps({p: v(p) for p in #{pylist}}))
  PY

  out = IO.popen(["python", "-"], "r+") do |io|
    io.write(script)
    io.close_write
    io.read
  end
  raise "python ha risposto exit #{$?.exitstatus} (PATH mise?)" unless $?.success?

  JSON.parse(out)
rescue JSON::ParserError => e
  raise "output di python non è JSON valido: #{e.message} — #{out.inspect}"
end

# Ultima versione su PyPI. Net::HTTP usa OpenSSL, che rispetta SSL_CERT_FILE
# (impostato nell'[env] del .mise.toml a C:/certs/cacert.pem) → sopravvive al
# MITM TLS del proxy ENINET, esattamente come fa cp-check.rb verso npm.
def latest_version(pkg)
  uri = URI("https://pypi.org/pypi/#{pkg}/json")
  res = Net::HTTP.start(uri.host, uri.port, use_ssl: true, open_timeout: 10, read_timeout: 10) do |http|
    http.get(uri.request_uri)
  end
  raise "PyPI ha risposto HTTP #{res.code} per #{pkg}" unless res.is_a?(Net::HTTPSuccess)

  JSON.parse(res.body).fetch("info").fetch("version")
end

begin
  installed = installed_versions(PKGS)

  records = PKGS.map do |pkg|
    inst = installed[pkg]
    latest = latest_version(pkg)

    if inst.nil?
      # Non installato: lo segnaliamo, ma non è un "update" (non c'è una baseline).
      { "package" => pkg, "installed" => nil, "latest" => latest,
        "update_available" => false, "not_installed" => true }
    else
      # Soglia = max(installata, eventuali versioni ignorate). Update solo se la
      # latest la supera davvero.
      baseline = ([inst] + IGNORED_VERSIONS).map { |v| Gem::Version.new(v) }.max
      update = Gem::Version.new(latest) > baseline
      { "package" => pkg, "installed" => inst, "latest" => latest,
        "update_available" => update }
    end
  end

  any_update = records.any? { |r| r["update_available"] }

  puts JSON.pretty_generate(
    "packages" => records,
    "ignored" => IGNORED_VERSIONS,
    "update_available" => any_update,
    "checked_at" => Time.now.utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
  )
  exit(any_update ? 10 : 0)
rescue StandardError => e
  warn "api-check: ERRORE — #{e.class}: #{e.message}"
  exit 1
end
