# frozen_string_literal: true

require_relative "app"

use Rack::Static,
  urls: ["/assets"],
  root: File.expand_path("public", __dir__)

run HindsightDashboard.freeze.app
