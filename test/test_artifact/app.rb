require "roda"
require "json"

class App < Roda
  # Cartella da esplorare: default = root del repo Trinity (../.. da qui).
  ROOT = File.expand_path(ENV["BROWSE_ROOT"] || File.join(__dir__, "..", ".."))

  IMAGE_EXT = {
    ".png"=>"image/png", ".jpg"=>"image/jpeg", ".jpeg"=>"image/jpeg", ".gif"=>"image/gif",
    ".webp"=>"image/webp", ".svg"=>"image/svg+xml", ".bmp"=>"image/bmp", ".ico"=>"image/x-icon"
  }.freeze

  # Risolve un path relativo dentro ROOT; nil se esce dalla root (anti-traversal).
  def safe_path(rel)
    rel = rel.to_s.gsub("\\", "/").sub(%r{\A/+}, "")
    full = File.expand_path(File.join(ROOT, rel))
    (full == ROOT || full.start_with?(ROOT + "/")) ? full : nil
  end

  route do |r|
    r.root do
      response["Content-Type"] = "text/html; charset=utf-8"
      File.read(File.join(__dir__, "index.html"))
    end

    # Asset statici (highlight.js, tema CSS) da ./assets, basename anti-traversal.
    r.get "assets", String do |name|
      file = File.join(__dir__, "assets", File.basename(name))
      next(response.status = 404) unless File.file?(file)
      response["Content-Type"] = name.end_with?(".css") ? "text/css; charset=utf-8" : "application/javascript; charset=utf-8"
      File.read(file)
    end

    r.on "api" do
      response["Content-Type"] = "application/json; charset=utf-8"

      # Versione = mtime di index.html: il poll del client la confronta e ricarica.
      r.get "version" do
        { v: File.mtime(File.join(__dir__, "index.html")).to_f }.to_json
      end

      r.get "list" do
        full = safe_path(r.params["path"])
        next({ error: "path non valido" }.to_json) unless full && File.directory?(full)
        entries = Dir.children(full).map { |name|
          p = File.join(full, name)
          kind = File.directory?(p) ? "dir" : (IMAGE_EXT.key?(File.extname(name).downcase) ? "image" : "file")
          { name: name, type: kind }
        }.sort_by { |e| [e[:type] == "dir" ? 0 : 1, e[:name].downcase] }
        rel = full[ROOT.length..].to_s.sub(%r{\A/}, "")
        { path: rel, root: File.basename(ROOT), entries: entries }.to_json
      end

      r.get "file" do
        full = safe_path(r.params["path"])
        next({ error: "path non valido" }.to_json) unless full && File.file?(full)
        ext = File.extname(full).downcase
        if (ct = IMAGE_EXT[ext])
          response["Content-Type"] = ct
          File.binread(full)
        else
          size = File.size(full)
          sample = File.binread(full, 8192) || ""   # euristica: NUL nei primi 8KB ⇒ binario
          if sample.include?("\x00") || size > 2_000_000
            { binary: true, size: size }.to_json
          else
            response["Content-Type"] = "text/plain; charset=utf-8"
            File.read(full, encoding: "utf-8", invalid: :replace, undef: :replace)
          end
        end
      end
    end
  end
end
