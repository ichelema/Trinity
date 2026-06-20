#!/usr/bin/env ruby
# frozen_string_literal: true

# Benchmark del RERANKER di Hindsight, a parita' di LLM ed EMBEDDER.
# Confronta tre configurazioni di reranking tenendo fissi:
#   - LLM di extraction: gpt-4.1-nano (openai)
#   - Embedder: Gemini 1536d  (EREDITATO dall'[env] del .mise.toml, NON impostato qui)
# Reranker variati:
#   - local       -> bge-reranker-v2-m3 (baseline reale di produzione)
#   - zeroentropy -> zerank-2
#   - rrf         -> nessun reranker, solo fusione RRF del retrieval grezzo (controllo)
#
# Metrica RANK-AWARE su ground truth document_id (vedi bench_corpus_rerank.json):
#   MRR, recall@1, recall@3, recall@5 + latenza media di recall.
#
# >>> LANCIARE SEMPRE VIA:  mise run rerank-bench  <<<
# Lanciato a mano da una shell nuda, il server partirebbe con l'embedder di DEFAULT
# (bge-small-en-v1.5, 384d): il confronto sarebbe su un embedder sbagliato. Lo script
# ABORTISCE se rileva embeddings=local proprio per impedire questo errore.
#
# NB: come il vecchio hindsight_bench.rb, ferma/riavvia il server di produzione su :8888
# durante il run (~5-10 min) e lo ripristina alla fine. Crea un bank di bench effimero
# (rerank-bench-<runid>) che resta nel Postgres: innocuo, cancellabile a posteriori.

require "json"
require "net/http"
require "uri"
require "time"
require "fileutils"

BASE = "http://localhost:8888"
# Path derivati a runtime (niente C:/msys64, versione o drive cablati): MSYS2_ROOT
# per la home MSYS, `mise where python` per la Scripts dir, `which` per pwsh.
# Il Ruby di mise è nativo Windows -> backtick via cmd.
MISE_BIN = "#{ENV['MSYS2_ROOT'].tr("\\", "/")}/home/#{ENV['USERNAME']}/.local/bin/mise.exe"
SCRIPTS_DIR = "#{`"#{MISE_BIN}" where python 2>NUL`.strip.tr("\\", "/")}/Scripts"
HINDSIGHT_EXE = "#{SCRIPTS_DIR}/hindsight-local-mcp.exe"
PWSH = `which pwsh.exe 2>NUL`.lines.first.to_s.strip.tr("\\", "/")
PWSH = "pwsh.exe" if PWSH.empty?
PORT = 8888
RUN_ID = Time.now.strftime("%Y%m%d-%H%M%S")
BENCH_DIR = __dir__
CORPUS_PATH = "#{BENCH_DIR}/bench_corpus_rerank.json"
OUT_DIR = "#{BENCH_DIR}/bench_results_rerank/#{RUN_ID}"
LOG_DIR = "#{OUT_DIR}/server_logs"

RETAIN_TIMEOUT = 120
RECALL_TIMEOUT = 120
HEALTH_TIMEOUT = 90 # il reranker locale ha un cold-start fino a ~50s

LLM_PROVIDER = "openai"
LLM_MODEL = "gpt-4.1-nano"

RERANKERS = [
  { slug: "local", label: "Local bge-reranker-v2-m3", provider: "local" },
  { slug: "zeroentropy", label: "ZeroEntropy zerank-2", provider: "zeroentropy" },
  { slug: "rrf", label: "Nessun reranker (RRF)", provider: "rrf" },
].freeze

# ---------- env Windows (registro) ----------

def read_user_env(name)
  out = `"#{PWSH}" -NoProfile -Command "[Environment]::GetEnvironmentVariable('#{name}','User')"`.strip
  out.empty? ? nil : out
end

OPENAI_KEY = ENV["OPENAI_API_KEY"] || read_user_env("OPENAI_API_KEY")
ZE_KEY = ENV["ZEROENTROPY_API_KEY"] || read_user_env("ZEROENTROPY_API_KEY")

# ---------- HTTP helpers ----------

def http_get(path, timeout)
  uri = URI("#{BASE}#{path}")
  Net::HTTP.start(uri.host, uri.port, open_timeout: 5, read_timeout: timeout) do |h|
    res = h.get(uri.request_uri, "Accept" => "application/json")
    [res.code.to_i, res.body]
  end
rescue StandardError => e
  [0, e.message]
end

def http_post(path, payload, timeout)
  uri = URI("#{BASE}#{path}")
  Net::HTTP.start(uri.host, uri.port, open_timeout: 5, read_timeout: timeout) do |h|
    req = Net::HTTP::Post.new(uri.request_uri, "Content-Type" => "application/json", "Accept" => "application/json")
    req.body = JSON.generate(payload)
    res = h.request(req)
    [res.code.to_i, res.body]
  end
rescue StandardError => e
  [0, e.message]
end

# ---------- processo hindsight ----------

def stop_hindsight
  ps = "$ErrorActionPreference='SilentlyContinue';" \
       "Get-NetTCPConnection -LocalPort #{PORT} -State Listen |" \
       "Select-Object -ExpandProperty OwningProcess | Sort-Object -Unique |" \
       "ForEach-Object { Stop-Process -Id $_ -Force }"
  system(PWSH, "-NoProfile", "-Command", ps, out: File::NULL, err: File::NULL)
  20.times do
    code, = http_get("/health", 2)
    return if code.zero?

    sleep 0.5
  end
end

# Avvia il server forzando SOLO LLM + reranker. L'embedder NON viene toccato: deve
# arrivare dall'[env] del .mise.toml (Gemini). Process.spawn fonde env sopra l'ambiente
# ereditato, quindi le HINDSIGHT_API_EMBEDDINGS_* di mise restano attive.
def start_hindsight(reranker_provider, log_path)
  env = {
    "PYTHONUTF8" => "1",
    "PATH" => "#{SCRIPTS_DIR}#{File::PATH_SEPARATOR}#{ENV["PATH"]}",
    "HINDSIGHT_API_LLM_PROVIDER" => LLM_PROVIDER,
    "HINDSIGHT_API_LLM_MODEL" => LLM_MODEL,
    "HINDSIGHT_API_LLM_API_KEY" => OPENAI_KEY.to_s,
    "HINDSIGHT_API_RERANKER_PROVIDER" => reranker_provider,
  }
  if reranker_provider == "zeroentropy"
    env["HINDSIGHT_API_RERANKER_ZEROENTROPY_API_KEY"] = ZE_KEY.to_s
    env["HINDSIGHT_API_RERANKER_ZEROENTROPY_MODEL"] = "zerank-2"
  end
  pid = Process.spawn(env, HINDSIGHT_EXE, "--port", PORT.to_s, "--log-level", "info",
                      out: log_path, err: log_path)
  Process.detach(pid)
  pid
end

def wait_healthy(timeout)
  deadline = Time.now + timeout
  while Time.now < deadline
    code, body = http_get("/health", 3)
    return true if code == 200 && body.to_s.include?("healthy")

    sleep 1
  end
  false
end

# Legge dal log il reranker e l'embedder effettivamente attivi. Restituisce
# [ok, descrizione, embedder]. ok=false se il reranker non e' quello atteso.
def verify_config(log_path, exp_reranker)
  return [false, "log assente", nil] unless File.exist?(log_path)

  log = File.read(log_path)
  rr = log.match(/Reranker: provider=(\S+)/)
  em = log.match(/Embeddings: provider=(\S+)/)
  return [false, "riga Reranker non trovata (crash avvio?)", nil] unless rr

  reranker = rr[1].sub(/,.*/, "")
  embedder = em ? em[1].sub(/,.*/, "") : "?"
  mm = log.match(/Reranker: initializing \S+ provider with model (\S+)/)
  model = mm ? mm[1] : "-"
  ok = (reranker == exp_reranker)
  [ok, "reranker=#{reranker} (model=#{model}), embeddings=#{embedder}", embedder]
end

# ---------- fasi ----------

def retain_corpus(bank, corpus)
  errors = 0
  corpus["documents"].each do |doc|
    payload = { items: [{ content: doc["content"], document_id: doc["id"], context: "benchmark" }], async: false }
    code, = http_post("/v1/default/banks/#{bank}/memories", payload, RETAIN_TIMEOUT)
    if code == 200
      print "."
    else
      errors += 1
      print "x"
    end
  end
  puts " (#{errors} errori)"
  errors
end

# Misura un reranker sul bank gia' popolato. La prima recall e' un warm-up scartato
# (assorbe il cold-start del modello). Score per query: posizione (1-based) del primo
# risultato il cui document_id e' tra i relevant_ids -> reciprocal rank.
def score_reranker(bank, corpus)
  http_post("/v1/default/banks/#{bank}/memories/recall",
            { query: corpus["queries"].first["query"], budget: "mid", max_tokens: 2048 }, RECALL_TIMEOUT)

  rrs = []
  r1 = r3 = r5 = 0
  lat = []
  detail = []
  corpus["queries"].each do |q|
    payload = { query: q["query"], budget: "mid", max_tokens: 2048 }
    t0 = Time.now
    code, body = http_post("/v1/default/banks/#{bank}/memories/recall", payload, RECALL_TIMEOUT)
    dt = Time.now - t0
    results = code == 200 ? (JSON.parse(body)["results"] rescue []) : []
    lat << dt if code == 200

    rel = q["relevant_ids"]
    pos = nil
    results.each_with_index do |r, i|
      if rel.include?(r["document_id"])
        pos = i + 1
        break
      end
    end
    rrs << (pos ? 1.0 / pos : 0.0)
    r1 += 1 if pos && pos <= 1
    r3 += 1 if pos && pos <= 3
    r5 += 1 if pos && pos <= 5
    detail << { id: q["id"], pos: pos, n_results: results.size, latency_s: dt.round(3) }
    print(pos.nil? ? "-" : (pos <= 3 ? "+" : "~"))
  end
  puts ""

  n = corpus["queries"].size
  {
    mrr: (rrs.sum / n).round(3),
    recall_at_1: (r1.to_f / n).round(3),
    recall_at_3: (r3.to_f / n).round(3),
    recall_at_5: (r5.to_f / n).round(3),
    recall_lat_avg_s: lat.empty? ? nil : (lat.sum / lat.size).round(3),
    queries: n,
    detail: detail,
  }
end

# ---------- main ----------

FileUtils.mkdir_p(LOG_DIR)
corpus = JSON.parse(File.read(CORPUS_PATH))
abort "OPENAI_API_KEY mancante (registro/env)." if OPENAI_KEY.nil? || OPENAI_KEY.empty?

# Modalita' dry-run (DRY=1): sottoinsieme coerente per testare la catena in pochi minuti.
# Prende le prime DRY_QUERIES query e SOLO i documenti che referenziano (relevant + hard
# negatives) piu' 3 doc di rumore, cosi' lo scoring resta sensato.
DRY = !ENV["DRY"].to_s.empty?
if DRY
  nq = (ENV["DRY_QUERIES"] || "3").to_i
  q_sub = corpus["queries"].first(nq)
  needed = q_sub.flat_map { |q| q["relevant_ids"] + q["hard_negative_ids"] }.uniq
  noise = corpus["documents"].select { |d| d["cluster"] == "noise" }.first(3).map { |d| d["id"] }
  keep = (needed + noise).uniq
  corpus["documents"] = corpus["documents"].select { |d| keep.include?(d["id"]) }
  corpus["queries"] = q_sub
end

puts "Benchmark RERANKER Hindsight — run #{RUN_ID}#{DRY ? "  [DRY-RUN]" : ""}"
puts "Corpus: #{corpus["documents"].length} doc, #{corpus["queries"].length} query"
puts "ZeroEntropy key: #{ZE_KEY && !ZE_KEY.empty? ? "presente (len=#{ZE_KEY.length})" : "ASSENTE -> zerank-2 verra saltato"}"
puts "Output: #{OUT_DIR}"

bank = "rerank-bench-#{RUN_ID}"
results = {}

begin
  # FASE 1 — retain una sola volta (il reranker non influenza il retain).
  puts "\n== FASE 1: retain corpus nel bank #{bank} =="
  stop_hindsight
  start_hindsight("local", "#{LOG_DIR}/setup.log")
  abort "Server non healthy in fase di setup." unless wait_healthy(HEALTH_TIMEOUT)
  _, detail, embedder = verify_config("#{LOG_DIR}/setup.log", "local")
  puts "  config: #{detail}"
  if embedder == "local"
    abort "ABORT: embedder='local' (default inglese 384d), non Gemini.\n" \
          "       Lancia SEMPRE con: mise run rerank-bench"
  end
  retain_corpus(bank, corpus)
  puts "  attendo la consolidation async..."
  sleep 10

  # FASE 2 — un reranker alla volta, sullo STESSO bank.
  only = (ENV["BENCH_ONLY"] || (DRY ? "local,zeroentropy" : "")).split(",").map(&:strip).reject(&:empty?)
  selected = only.empty? ? RERANKERS : RERANKERS.select { |rk| only.include?(rk[:slug]) }
  selected.each do |rk|
    if rk[:provider] == "zeroentropy" && (ZE_KEY.nil? || ZE_KEY.empty?)
      puts "\n== #{rk[:label]} == SALTATO (ZEROENTROPY_API_KEY assente)"
      results[rk[:slug]] = { label: rk[:label], error: "missing api key" }
      next
    end
    puts "\n== #{rk[:label]} =="
    log = "#{LOG_DIR}/#{rk[:slug]}.log"
    stop_hindsight
    start_hindsight(rk[:provider], log)
    unless wait_healthy(HEALTH_TIMEOUT)
      puts "  FALLITO (health timeout)"
      results[rk[:slug]] = { label: rk[:label], error: "health timeout" }
      next
    end
    ok, detail, = verify_config(log, rk[:provider])
    puts "  config: #{detail}"
    unless ok
      puts "  FALLITO (reranker inatteso)"
      results[rk[:slug]] = { label: rk[:label], error: detail }
      next
    end
    results[rk[:slug]] = score_reranker(bank, corpus).merge(label: rk[:label])
  end
ensure
  # Ripristino: riavvia il server EREDITANDO l'env di produzione (.mise.toml: Gemini + reranker).
  puts "\n--- ripristino server di produzione ---"
  stop_hindsight
  env = { "PYTHONUTF8" => "1", "PATH" => "#{SCRIPTS_DIR}#{File::PATH_SEPARATOR}#{ENV["PATH"]}" }
  pid = Process.spawn(env, HINDSIGHT_EXE, "--port", PORT.to_s, "--log-level", "info",
                      out: "#{LOG_DIR}/prod-restore.log", err: "#{LOG_DIR}/prod-restore.log")
  Process.detach(pid)
  puts(wait_healthy(HEALTH_TIMEOUT) ? "  ok" : "  ATTENZIONE: riavvia con 'mise run start-hindsight' (dalla root del repo)")
end

# ---------- report ----------

cols = %w[label mrr recall_at_1 recall_at_3 recall_at_5 recall_lat_avg_s]
csv = [cols.join(",")]
results.each_value do |r|
  csv << cols.map { |c| r[c.to_sym] }.join(",")
end
File.write("#{OUT_DIR}/summary.csv", "#{csv.join("\n")}\n")
File.write("#{OUT_DIR}/full.json", JSON.pretty_generate(results))

puts "\n================ RIEPILOGO RERANKER ================"
fmt = "%-26s %6s %8s %8s %8s %10s"
puts format(fmt, "Reranker", "MRR", "R@1", "R@3", "R@5", "lat_avg_s")
RERANKERS.each do |rk|
  r = results[rk[:slug]]
  next unless r

  if r[:error]
    puts format("%-26s  ! %s", rk[:label][0, 26], r[:error])
  else
    puts format(fmt, r[:label][0, 26], r[:mrr], r[:recall_at_1], r[:recall_at_3], r[:recall_at_5], r[:recall_lat_avg_s] || "-")
  end
end
puts "\nLegenda colonne recall: + = relevant entro pos 3, ~ = entro pos >3, - = non trovato"
puts "Dettaglio + CSV in: #{OUT_DIR}"
puts "Bank di bench effimero (cancellabile): #{bank}"
