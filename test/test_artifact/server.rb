require_relative "app"

host = "127.0.0.1"
port = (ENV["PORT"] || 8123).to_i

begin
  require "rackup/handler/webrick"            # Rack 3
  handler = Rackup::Handler::WEBrick
rescue LoadError
  require "rack/handler/webrick"              # Rack 2
  handler = Rack::Handler::WEBrick
end

puts "File browser → http://#{host}:#{port}   (root: #{App::ROOT})"
handler.run(App.freeze.app, Host: host, Port: port)
