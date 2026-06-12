#!/usr/bin/env ruby
# frozen_string_literal: true

# Benchmark velocita' + qualita' della memoria Hindsight su piu' provider LLM.
# Approccio A: sequenziale, un bank dedicato (univoco per run) per ogni provider.
# Per ogni config: ferma hindsight -> lo riavvia con env provider override ->
# attende /health -> retain sincrono del corpus -> recall delle query ->
# raccoglie latenza / token / fatti estratti / recall hit-rate.
#
# Uso:  ruby test/hindsight_bench.rb
# Output: tabella a video + test/bench_results/<runid>/ (JSON per config + summary.csv)

require "json"
require "net/http"
require "uri"
require "time"
require "fileutils"

BASE          = "http://localhost:8888"
SCRIPTS_DIR   = "C:/msys64/home/EN27553/.local/share/mise/installs/python/3.13.13/Scripts"
HINDSIGHT_EXE = "#{SCRIPTS_DIR}/hindsight-local-mcp.exe"
PWSH          = "C:/Appl/PowerShell/pwsh.exe"
PORT          = 8888
RUN_ID        = Time.now.strftime("%Y%m%d-%H%M%S")
# Path relativi alla cartella dello script (__dir__): il benchmark e' rilocabile senza
# rompere i riferimenti — corpus e risultati vivono accanto al .rb.
BENCH_DIR     = __dir__
CORPUS_PATH   = "#{BENCH_DIR}/bench_corpus.json"
OUT_DIR       = "#{BENCH_DIR}/bench_results/#{RUN_ID}"
LOG_DIR       = "#{OUT_DIR}/server_logs"

# Timeout generosi: i reasoning model (gpt-oss, deepseek) sono lenti sul retain sincrono.
RETAIN_TIMEOUT = 240
RECALL_TIMEOUT = 120
HEALTH_TIMEOUT = 60

# Prezzi INDICATIVI in $/1M token (input, output). Servono solo per una stima di costo;
# verifica sempre i prezzi correnti del provider. nil = costo non calcolato (n/d).
def read_user_env(name)
  out = `"#{PWSH}" -NoProfile -Command "[Environment]::GetEnvironmentVariable('#{name}','User')"`.strip
  out.empty? ? nil : out
end

OPENAI_KEY = ENV["OPENAI_API_KEY"] || read_user_env("OPENAI_API_KEY")
GROQ_KEY   = read_user_env("GROQ_API_KEY")
OR_KEY     = read_user_env("OPENROUTER_API_KEY")

CONFIGS = [
  { slug: "openai-nano",     label: "OpenAI gpt-4.1-nano",        provider: "openai",
    base_url: nil,                               model: "gpt-4.1-nano",
    key: OPENAI_KEY, price_in: 0.10, price_out: 0.40 },
  # Groq e OpenRouter sono provider NATIVI in Hindsight: conoscono gia' il loro endpoint,
  # quindi base_url resta nil. La chiave arriva via HINDSIGHT_API_LLM_API_KEY.
  # max_ctok: tetto max_completion_tokens. Il default Hindsight (64000) supera il cap
  # fisico di Llama-3.3-70B (32768) -> HTTP 400. 8000 e' sotto il cap e basta all'output reale.
  { slug: "groq-llama70b",   label: "Groq Llama-3.3-70B",         provider: "groq",
    base_url: nil,                               model: "llama-3.3-70b-versatile",
    key: GROQ_KEY,   price_in: 0.59, price_out: 0.79, max_ctok: 8000 },
  # max_ctok: cappa l'output (gpt-oss-20b e' un reasoning model: senza tetto puo' emettere
  # molti token di reasoning). DEVE essere > RETAIN_CHUNK_SIZE (default 3000) o il server
  # rifiuta di avviarsi → usiamo 4000.
  # pace_s: attesa tra chiamate LLM consecutive. 10s simula un uso quotidiano "a raffica"
  # (retain ravvicinati). NB: sul free tier 10s NON basta a ricaricare gli ~4700 token che
  # ogni chiamata prenota (in 10s il bucket rigenera solo ~1330 tok), quindi il rate-limit
  # riapparira' — ed e' proprio il comportamento realistico che si vuole osservare.
  { slug: "groq-gptoss20b",  label: "Groq gpt-oss-20b",           provider: "groq",
    base_url: nil,                               model: "openai/gpt-oss-20b",
    key: GROQ_KEY,   price_in: nil,  price_out: nil, max_ctok: 4000, pace_s: 10 },
  { slug: "or-deepseek-v4f", label: "OpenRouter DeepSeek-V4-Flash", provider: "openrouter",
    base_url: nil,                               model: "deepseek/deepseek-v4-flash",
    key: OR_KEY,     price_in: nil,  price_out: nil },
].freeze

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

# ---------- gestione processo hindsight ----------

def stop_hindsight
  # Kill per PORTA, non per nome: il launcher .exe spawna un python.exe che tiene la
  # socket; killare il solo launcher lascerebbe il vecchio server in ascolto su :8888,
  # e wait_healthy si aggancerebbe a quello (bug del primo run: tutte le config
  # finivano sullo stesso server openai). Stop-Process per OwningProcess elimina la radice.
  ps = "$ErrorActionPreference='SilentlyContinue';" \
       "Get-NetTCPConnection -LocalPort #{PORT} -State Listen |" \
       "Select-Object -ExpandProperty OwningProcess | Sort-Object -Unique |" \
       "ForEach-Object { Stop-Process -Id $_ -Force }"
  system(PWSH, "-NoProfile", "-Command", ps, out: File::NULL, err: File::NULL)
  # Attende che la porta sia EFFETTIVAMENTE libera prima di proseguire.
  20.times do
    code, = http_get("/health", 2)
    return if code.zero?
    sleep 0.5
  end
end

def start_hindsight(cfg, log_path)
  env = {
    "PYTHONUTF8"                 => "1",
    "PATH"                       => "#{SCRIPTS_DIR}#{File::PATH_SEPARATOR}#{ENV['PATH']}",
    "HINDSIGHT_API_LLM_PROVIDER" => cfg[:provider],
    "HINDSIGHT_API_LLM_MODEL"    => cfg[:model],
    "HINDSIGHT_API_LLM_API_KEY"  => cfg[:key].to_s,
    "HINDSIGHT_API_LLM_TIMEOUT"  => RETAIN_TIMEOUT.to_s,
  }
  # Se base_url e' nil (provider openai nativo), cancella un eventuale BASE_URL ereditato
  # dall'ambiente passando nil (Process.spawn rimuove la chiave dal processo figlio).
  env["HINDSIGHT_API_LLM_BASE_URL"] = cfg[:base_url]
  # Tetto opzionale sui completion token per provider con cap o limiti TPM stretti.
  env["HINDSIGHT_API_RETAIN_MAX_COMPLETION_TOKENS"] = cfg[:max_ctok].to_s if cfg[:max_ctok]

  pid = Process.spawn(env, HINDSIGHT_EXE, "--port", PORT.to_s, "--log-level", "info",
                      out: log_path, err: log_path)
  Process.detach(pid)
  pid
end

# Conferma dal log che il server attivo usa DAVVERO il provider/model atteso.
# Senza questo controllo un riavvio fallito passa inosservato e i numeri sono falsi.
def verify_active_provider(log_path, exp_provider, exp_model)
  return [false, "log assente"] unless File.exist?(log_path)

  log = File.read(log_path)
  return [false, "provider non valido (crash all'avvio)"] if log.include?("Invalid LLM provider")

  m = log.match(/LLM: provider=(\S+?), model=(\S+)/)
  return [false, "riga provider non trovata nel log"] unless m

  actual_provider = m[1]
  actual_model = m[2].sub(/,.*/, "")
  if actual_provider == exp_provider && actual_model == exp_model
    [true, "provider=#{actual_provider}, model=#{actual_model}"]
  else
    [false, "atteso #{exp_provider}/#{exp_model}, attivo #{actual_provider}/#{actual_model}"]
  end
end

def wait_healthy(timeout)
  deadline = Time.now + timeout
  while Time.now < deadline
    code, body = http_get("/health", 3)
    if code == 200 && body.to_s.include?("healthy")
      return true
    end
    sleep 1
  end
  false
end

# ---------- metriche ----------

def bank_node_count(bank)
  code, body = http_get("/v1/default/banks/#{bank}/stats", 10)
  return 0 unless code == 200

  JSON.parse(body)["total_nodes"].to_i
rescue StandardError
  0
end

def regex_hit?(blob, pattern)
  Regexp.new(pattern, Regexp::IGNORECASE).match?(blob)
end

# ---------- benchmark di una config ----------

def run_config(cfg, corpus)
  bank = "bench-#{cfg[:slug]}-#{RUN_ID}"
  log_path = "#{LOG_DIR}/#{cfg[:slug]}.log"

  puts "\n=== #{cfg[:label]}  (#{cfg[:model]}) ==="
  if cfg[:key].nil? || cfg[:key].empty?
    puts "  SALTATA: API key mancante"
    return { slug: cfg[:slug], label: cfg[:label], model: cfg[:model], skipped: "missing api key" }
  end

  print "  riavvio hindsight con provider=#{cfg[:provider]}... "
  stop_hindsight
  start_hindsight(cfg, log_path)
  unless wait_healthy(HEALTH_TIMEOUT)
    puts "FALLITO (health timeout)"
    return { slug: cfg[:slug], label: cfg[:label], model: cfg[:model], error: "health timeout" }
  end
  ok, detail = verify_active_provider(log_path, cfg[:provider], cfg[:model])
  unless ok
    puts "FALLITO (#{detail})"
    return { slug: cfg[:slug], label: cfg[:label], model: cfg[:model], error: detail }
  end
  puts "ok [#{detail}]"

  base_nodes = bank_node_count(bank) # 0 per bank nuovo

  # --- RETAIN ---
  retain_lat = []
  tok_in = tok_out = 0
  retain_errors = 0
  corpus["documents"].each_with_index do |doc, i|
    # Pacing per provider rate-limited (Groq free tier): attende il refill del bucket TPM
    # tra un retain e l'altro, cosi' ogni chiamata parte con budget pieno e niente 429.
    # Salta l'attesa sul primo doc (bucket gia' pieno all'inizio).
    sleep cfg[:pace_s] if cfg[:pace_s] && i.positive?
    payload = { items: [{ content: doc["content"], document_id: doc["id"], context: "benchmark" }], async: false }
    t0 = Time.now
    code, body = http_post("/v1/default/banks/#{bank}/memories", payload, RETAIN_TIMEOUT)
    dt = Time.now - t0
    if code == 200
      retain_lat << dt
      usage = (JSON.parse(body)["usage"] rescue nil)
      if usage
        tok_in  += usage["input_tokens"].to_i
        tok_out += usage["output_tokens"].to_i
      end
      print "."
    else
      retain_errors += 1
      print "x"
      File.write("#{OUT_DIR}/#{cfg[:slug]}.retain_error.txt", "HTTP #{code}\n#{body}\n", mode: "a")
    end
  end
  puts ""

  facts_extracted = bank_node_count(bank) - base_nodes

  # --- RECALL ---
  recall_lat = []
  total_expected = 0
  total_hits = 0
  queries_full = 0
  recall_detail = []
  corpus["queries"].each do |q|
    # Anche il recall e' LLM-backed → consuma TPM. Pacing pure qui (il retain ha appena
    # svuotato il bucket), altrimenti le prime query andrebbero in 429.
    sleep cfg[:pace_s] if cfg[:pace_s]
    payload = { query: q["query"], types: %w[world experience observation], budget: "mid", max_tokens: 2048 }
    t0 = Time.now
    code, body = http_post("/v1/default/banks/#{bank}/memories/recall", payload, RECALL_TIMEOUT)
    dt = Time.now - t0
    hits = 0
    blob = ""
    if code == 200
      recall_lat << dt
      results = (JSON.parse(body)["results"] rescue [])
      blob = results.map { |r| r["text"].to_s }.join("\n").downcase
      q["expected"].each { |pat| hits += 1 if regex_hit?(blob, pat) }
    end
    exp = q["expected"].length
    total_expected += exp
    total_hits += hits
    full = hits >= q["min_hits"].to_i
    queries_full += 1 if full
    recall_detail << { id: q["id"], hits: hits, expected: exp, min_hits: q["min_hits"], full: full, latency_s: dt.round(3) }
    print(full ? "+" : "-")
  end
  puts ""

  cost = nil
  if cfg[:price_in] && cfg[:price_out]
    cost = (tok_in / 1_000_000.0 * cfg[:price_in]) + (tok_out / 1_000_000.0 * cfg[:price_out])
  end

  avg = ->(a) { a.empty? ? nil : (a.sum / a.size) }

  {
    slug: cfg[:slug], label: cfg[:label], model: cfg[:model], bank: bank,
    retain_docs: corpus["documents"].length, retain_errors: retain_errors,
    retain_lat_avg_s: avg.call(retain_lat)&.round(3),
    retain_lat_max_s: retain_lat.max&.round(3),
    facts_extracted: facts_extracted,
    facts_per_doc: (facts_extracted.to_f / corpus["documents"].length).round(2),
    tokens_in: tok_in, tokens_out: tok_out, tokens_total: tok_in + tok_out,
    cost_usd: cost&.round(5),
    recall_lat_avg_s: avg.call(recall_lat)&.round(3),
    recall_hit_rate: total_expected.zero? ? 0.0 : (total_hits.to_f / total_expected).round(3),
    queries_full: queries_full, queries_total: corpus["queries"].length,
    recall_detail: recall_detail,
  }
end

# ---------- main ----------

FileUtils.mkdir_p(LOG_DIR)
corpus = JSON.parse(File.read(CORPUS_PATH))
puts "Benchmark Hindsight — run #{RUN_ID}"
puts "Corpus: #{corpus['documents'].length} documenti, #{corpus['queries'].length} query"
puts "Output: #{OUT_DIR}"

# BENCH_ONLY=slug1,slug2 limita il run ad alcune config (utile per smoke test).
only = (ENV["BENCH_ONLY"] || "").split(",").map(&:strip).reject(&:empty?)
selected = only.empty? ? CONFIGS : CONFIGS.select { |c| only.include?(c[:slug]) }

results = []
begin
  selected.each do |cfg|
    r = run_config(cfg, corpus)
    results << r
    File.write("#{OUT_DIR}/#{cfg[:slug]}.json", JSON.pretty_generate(r))
  end
ensure
  # Ripristina la config di PRODUZIONE (openai gpt-4.1-nano) e riavvia hindsight,
  # cosi' la memoria reale non resta su un provider di test.
  puts "\n--- ripristino config di produzione (openai gpt-4.1-nano) ---"
  prod = { slug: "prod-restore", provider: "openai", base_url: nil, model: "gpt-4.1-nano", key: OPENAI_KEY }
  stop_hindsight
  start_hindsight(prod, "#{LOG_DIR}/prod-restore.log")
  puts(wait_healthy(HEALTH_TIMEOUT) ? "  hindsight riavviato in produzione: ok" : "  ATTENZIONE: hindsight non risponde, riavvialo con: mise run start-hindsight (dalla root del repo)")
end

# ---------- report ----------

cols = %w[label model retain_lat_avg_s retain_lat_max_s facts_per_doc tokens_total cost_usd recall_lat_avg_s recall_hit_rate queries_full]
csv = [cols.join(",")]
results.each do |r|
  csv << cols.map { |c| r[c.to_sym] }.join(",")
end
File.write("#{OUT_DIR}/summary.csv", csv.join("\n") + "\n")

puts "\n================ RIEPILOGO ================"
fmt = "%-28s %10s %10s %9s %9s %12s %10s %9s"
puts format(fmt, "Provider", "retain_avg", "retain_max", "fatti/doc", "tok_tot", "costo$", "rec_avg", "hit_rate")
results.each do |r|
  next if r[:skipped] || r[:error]

  puts format(fmt,
              r[:label][0, 28],
              r[:retain_lat_avg_s] || "-",
              r[:retain_lat_max_s] || "-",
              r[:facts_per_doc] || "-",
              r[:tokens_total] || "-",
              r[:cost_usd] || "n/d",
              r[:recall_lat_avg_s] || "-",
              "#{(r[:recall_hit_rate] * 100).round}%  #{r[:queries_full]}/#{r[:queries_total]}")
end
results.each do |r|
  puts "  ! #{r[:label]}: #{r[:skipped] || r[:error]}" if r[:skipped] || r[:error]
end
puts "\nDettaglio + CSV in: #{OUT_DIR}"
