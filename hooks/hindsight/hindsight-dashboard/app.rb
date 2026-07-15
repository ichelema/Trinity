# frozen_string_literal: true

require "roda"
require "json"
require "time"
require "pathname"
require "thread"

# Default portabile: <plugin_root>/logs/hindsight-debug.log, calcolato relativo a
# questo file (.../hooks/hindsight/hindsight-dashboard/app.rb → 3 livelli su = plugin root).
# Coerente con lib/hindsight_debug.py, che scrive lì quando debug_log_file e' vuoto in config.
DEFAULT_LOG_PATH = ENV.fetch("LOG_FILE", File.expand_path("../../../logs/hindsight-debug.log", __dir__))
# Cartella consentita a /api/open. L'endpoint non ha autenticazione: senza questo
# vincolo una richiesta puo' far aprire QUALSIASI file leggibile dall'utente (es.
# ~/.ssh/config), che /api/events poi serve riga per riga nel campo raw.
# LOG_FILE resta libero: e' l'operatore a impostarlo, non una richiesta HTTP.
ALLOWED_LOG_DIR = File.expand_path("../../../logs", __dir__)
MAX_INITIAL_LIMIT = Integer(ENV.fetch("MAX_INITIAL_LIMIT", "5000"))
DEFAULT_INITIAL_LIMIT = Integer(ENV.fetch("INITIAL_LIMIT", "500"))
POLL_INTERVAL = Float(ENV.fetch("POLL_INTERVAL", "0.6"))

module Shutdown
  @running = true

  class << self
    def running?
      @running
    end

    def stop!
      @running = false
    end
  end
end

# Local dashboard: make Ctrl+C deterministic even when SSE clients are connected.
# Puma normally tries a graceful shutdown, but long-lived streaming responses can
# keep the process alive. We first ask tail loops to stop, then force-exit shortly
# after so the terminal is released.
unless ENV["RACK_ENV"] == "test"
  SIGNAL_EXIT_CODES = { "INT" => 130, "TERM" => 143 }.freeze

  SIGNAL_EXIT_CODES.each do |sig, code|
    Signal.trap(sig) do
      Shutdown.stop!
      Thread.new do
        warn "\n#{sig}: stopping hindsight-dashboard..."
        sleep 0.35
        exit!(code)
      end
    end
  end
end

module JsonResponse
  module_function

  def ok(payload)
    [200, { "Content-Type" => "application/json; charset=utf-8" }, [JSON.generate(payload)]]
  end

  def error(status, message, extra = {})
    [status, { "Content-Type" => "application/json; charset=utf-8" }, [JSON.generate({ error: message }.merge(extra))]]
  end
end

class LogState
  class PathNotAllowed < StandardError; end

  @mutex = Mutex.new
  @path = DEFAULT_LOG_PATH
  @version = 0

  class << self
    def path
      @mutex.synchronize { @path }
    end

    def version
      @mutex.synchronize { @version }
    end

    def set_path(path)
      normalized = normalize_path(path)
      raise PathNotAllowed unless allowed?(normalized)

      @mutex.synchronize do
        @path = normalized
        @version += 1
      end
      normalized
    end

    def normalize_path(path)
      p = path.to_s.strip
      p = p.sub(%r{\A/d/}i, "D:/")
      p = p.sub(%r{\A/c/}i, "C:/")
      p.tr("\\", "/")
    end

    # Il controllo sta qui e non nella rotta: e' l'unico punto che scrive @path, e
    # /api/events legge @path senza validare. Validare dopo la scrittura lascerebbe
    # lo stato gia' avvelenato. expand_path collassa anche i ".." (non i symlink).
    def allowed?(path)
      File.expand_path(path).start_with?(ALLOWED_LOG_DIR + "/")
    end
  end
end

class LogEvent
  class << self
    def parse(line, line_no: nil, source: "file", seq: nil)
      raw = scrub(line.to_s).strip
      data = JSON.parse(raw)
      build(data, raw:, line_no:, source:, seq:)
    rescue JSON::ParserError => e
      data = {
        "event" => "parse_error",
        "error" => e.message,
        "raw" => raw
      }
      build(data, raw:, line_no:, source:, seq:)
    end

    def build(data, raw:, line_no:, source:, seq:)
      event = string_field(data, "event", "unknown")
      level = level_for(data)
      message = message_for(data)
      memories = data["memories"].is_a?(Array) ? data["memories"] : []

      {
        id: event_id(source:, line_no:, seq:, raw:),
        source: source,
        line: line_no,
        seq: seq,
        ts_raw: string_field(data, "ts", ""),
        event: event,
        level: level,
        status: string_field(data, "status", ""),
        cache: string_field(data, "cache", ""),
        n_results: data.key?("n_results") ? data["n_results"] : "",
        doc_id: string_field(data, "doc_id", ""),
        message: message,
        memories_count: memories.length,
        css_class: css_class_for(data, level),
        data: data,
        raw: raw
      }
    end

    def match?(event, wanted_events:, grep:)
      if wanted_events.any? && !wanted_events.include?(event[:event])
        return false
      end

      needle = grep.to_s.strip.downcase
      return true if needle.empty?

      [
        event[:event],
        event[:level],
        event[:message],
        event[:raw]
      ].join("\n").downcase.include?(needle)
    end

    def level_for(data)
      event = string_field(data, "event", "unknown")
      status = integer_field(data, "status")

      if event.end_with?("_error") || event == "parse_error" || (status && status >= 400)
        "ERROR"
      elsif event.end_with?("_skip")
        "SKIP"
      elsif event == "retain_result"
        "OK"
      else
        "INFO"
      end
    end

    def css_class_for(data, level)
      event = string_field(data, "event", "unknown")

      case level
      when "ERROR" then "row-error"
      when "SKIP" then "row-skip"
      when "OK" then "row-ok"
      else
        case event
        when "recall" then "row-recall"
        when "retain" then "row-retain"
        else "row-info"
        end
      end
    end

    def message_for(data)
      event = string_field(data, "event", "unknown")

      case event
      when "recall"
        string_field(data, "query", "")
      when "recall_error"
        "error=#{string_field(data, "error", "")} query=#{string_field(data, "query", "")}".strip
      when "recall_skip"
        "reason=#{string_field(data, "reason", "")} prompt_len=#{string_field(data, "prompt_len", "")}".strip
      when "retain"
        string_field(data, "prompt", "")
      when "retain_result"
        retain_result_message(data)
      when "retain_skip"
        "reason=#{string_field(data, "reason", "")} session=#{string_field(data, "session", "")}".strip
      when "parse_error"
        string_field(data, "raw", "")
      else
        JSON.generate(data)
      end
    end

    def retain_result_message(data)
      response = string_field(data, "response", "")
      parsed = JSON.parse(response)
      parts = []
      parts << "success=#{parsed["success"]}" if parsed.key?("success")
      parts << "bank=#{parsed["bank_id"]}" if parsed["bank_id"]
      parts << "items=#{parsed["items_count"]}" if parsed.key?("items_count")
      parts << "op=#{parsed["operation_id"]}" if parsed["operation_id"]
      parts.join(" ")
    rescue JSON::ParserError, TypeError
      response
    end

    def string_field(data, key, fallback = "")
      value = data[key]
      value.nil? ? fallback : value.to_s
    end

    def integer_field(data, key)
      value = data[key]
      return nil if value.nil? || value == ""

      Integer(value)
    rescue ArgumentError, TypeError
      nil
    end

    def event_id(source:, line_no:, seq:, raw:)
      if line_no
        "#{source}-line-#{line_no}"
      elsif seq
        "#{source}-seq-#{seq}"
      else
        "#{source}-#{raw.hash}"
      end
    end

    def scrub(value)
      value.encode("UTF-8", invalid: :replace, undef: :replace, replace: "�")
    end
  end
end

class LogReader
  class << self
    def status(path)
      if File.file?(path)
        stat = File.stat(path)
        {
          path: path,
          exists: true,
          size: stat.size,
          mtime: stat.mtime.iso8601,
          readable: File.readable?(path)
        }
      else
        {
          path: path,
          exists: false,
          size: 0,
          mtime: nil,
          readable: false
        }
      end
    rescue SystemCallError => e
      {
        path: path,
        exists: false,
        size: 0,
        mtime: nil,
        readable: false,
        error: e.message
      }
    end

    def read(path, limit:, wanted_events:, grep:)
      limit = [[limit.to_i, 1].max, MAX_INITIAL_LIMIT].min
      rows = []
      counts = Hash.new(0)
      level_counts = Hash.new(0)
      total_lines = 0
      tail_offset = 0
      last_event = nil

      unless File.file?(path)
        return {
          path: path,
          status: status(path),
          events: [],
          counts: {},
          level_counts: {},
          total_lines: 0,
          limit: limit,
          tail_offset: 0,
          last_ts: nil
        }
      end

      File.open(path, "rb") do |file|
        file.each_line do |line|
          total_lines += 1
          event = LogEvent.parse(line, line_no: total_lines, source: "file")
          counts[event[:event]] += 1
          level_counts[event[:level]] += 1
          last_event = event

          next unless LogEvent.match?(event, wanted_events:, grep:)

          rows << event
          rows.shift while rows.length > limit
        end

        # Byte offset esatto fino a cui /api/events ha letto.
        # Lo stream SSE riparte da qui: evita il buco tra caricamento iniziale e tail live.
        tail_offset = file.pos
      end

      {
        path: path,
        status: status(path),
        events: rows,
        counts: counts.sort.to_h,
        level_counts: level_counts.sort.to_h,
        total_lines: total_lines,
        limit: limit,
        tail_offset: tail_offset,
        last_ts: last_event && last_event[:ts_raw]
      }
    rescue SystemCallError => e
      {
        path: path,
        status: status(path).merge(error: e.message),
        events: [],
        counts: {},
        level_counts: {},
        total_lines: 0,
        limit: limit,
        tail_offset: 0,
        last_ts: nil
      }
    end
  end
end

class TailSession
  def initialize(path:, version:, wanted_events:, grep:, start_offset: nil)
    @path = path
    @version = version
    @wanted_events = wanted_events
    @grep = grep
    @offset = sanitize_offset(start_offset, path)
    @buffer = +""
    @seq = 0
  end

  def run(out)
    write_event(out, "ready", { path: @path, offset: @offset, version: @version })

    until out.closed? || !Shutdown.running?
      refresh_path_if_changed(out)
      tick(out)
      interruptible_sleep(POLL_INTERVAL)
    end
  rescue IOError, Errno::EPIPE, Errno::ECONNRESET
    nil
  end

  private

  def interruptible_sleep(seconds)
    deadline = Process.clock_gettime(Process::CLOCK_MONOTONIC) + seconds.to_f
    while Shutdown.running? && Process.clock_gettime(Process::CLOCK_MONOTONIC) < deadline
      sleep 0.05
    end
  end

  def refresh_path_if_changed(out)
    current_version = LogState.version
    return if current_version == @version

    @path = LogState.path
    @version = current_version
    @offset = safe_size(@path)
    @buffer.clear
    write_event(out, "opened", { path: @path, offset: @offset, version: @version })
  end

  def tick(out)
    unless File.file?(@path)
      write_event(out, "missing", { path: @path })
      return
    end

    size = safe_size(@path)
    if size < @offset
      @offset = 0
      @buffer.clear
      write_event(out, "rotated", { path: @path, offset: @offset })
    end

    return if size <= @offset

    chunk = nil
    File.open(@path, "rb") do |f|
      f.seek(@offset)
      chunk = f.read
      @offset = f.pos
    end

    return if chunk.nil? || chunk.empty?

    chunk = LogEvent.scrub(chunk)
    text = @buffer + chunk
    lines = text.lines

    if !text.end_with?("\n") && !lines.empty?
      @buffer = lines.pop
    else
      @buffer.clear
    end

    lines.each do |line|
      next if line.strip.empty?

      @seq += 1
      event = LogEvent.parse(line, source: "live", seq: @seq)
      next unless LogEvent.match?(event, wanted_events: @wanted_events, grep: @grep)

      write_event(out, "log", event)
    end
  rescue SystemCallError => e
    write_event(out, "tail_error", { path: @path, error: e.message })
  end

  def sanitize_offset(value, path)
    size = safe_size(path)
    return size if value.nil? || value.to_s.strip.empty?

    offset = Integer(value)
    return 0 if offset.negative?
    return size if offset > size

    offset
  rescue ArgumentError, TypeError
    size
  end

  def safe_size(path)
    File.file?(path) ? File.size(path) : 0
  rescue SystemCallError
    0
  end

  def write_event(out, name, payload)
    out << "event: #{name}\n"
    out << "data: #{JSON.generate(payload)}\n\n"
  end
end

class HindsightDashboard < Roda
  plugin :streaming

  def parse_json_body(request)
    body = request.body.read.to_s
    return {} if body.strip.empty?

    JSON.parse(body)
  rescue JSON::ParserError
    {}
  end

  def parse_wanted_events(value)
    value.to_s.split(",").map(&:strip).reject(&:empty?)
  end

  route do |r|
    r.root do
      response["Content-Type"] = "text/html; charset=utf-8"
      File.read(File.expand_path("public/index.html", __dir__))
    end

    r.on "api" do
      r.get "status" do
        r.halt JsonResponse.ok(LogReader.status(LogState.path))
      end

      r.post "open" do
        payload = parse_json_body(r)
        path = payload["path"].to_s

        if path.strip.empty?
          r.halt JsonResponse.error(422, "missing path")
        end

        begin
          normalized = LogState.set_path(path)
        rescue LogState::PathNotAllowed
          r.halt JsonResponse.error(403, "path fuori da #{ALLOWED_LOG_DIR}")
        end
        r.halt JsonResponse.ok(LogReader.status(normalized).merge(version: LogState.version))
      end

      r.get "events" do
        limit = Integer(r.params.fetch("limit", DEFAULT_INITIAL_LIMIT)) rescue DEFAULT_INITIAL_LIMIT
        wanted_events = parse_wanted_events(r.params["events"])
        grep = r.params.fetch("grep", "")
        payload = LogReader.read(LogState.path, limit:, wanted_events:, grep:)
        r.halt JsonResponse.ok(payload)
      end

      r.get "stream" do
        wanted_events = parse_wanted_events(r.params["events"])
        grep = r.params.fetch("grep", "")
        start_offset = r.params["offset"]

        response["Content-Type"] = "text/event-stream; charset=utf-8"
        response["Cache-Control"] = "no-cache, no-transform"
        response["Connection"] = "keep-alive"
        response["X-Accel-Buffering"] = "no"

        session = TailSession.new(
          path: LogState.path,
          version: LogState.version,
          wanted_events: wanted_events,
          grep: grep,
          start_offset: start_offset
        )

        stream do |out|
          begin
            session.run(out)
          ensure
            out.close unless out.closed?
          end
        end
      end
    end

    r.halt JsonResponse.error(404, "not found")
  end
end
