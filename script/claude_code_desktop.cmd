@echo off
set DISABLE_TELEMETRY=1
set DO_NOT_TRACK=1
set CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY=1

set ANTHROPIC_API_KEY=
set ANTHROPIC_AUTH_TOKEN=
set CLAUDE_CODE_OAUTH_TOKEN=

set TERM=xterm-256color
set COLORTERM=truecolor
set LANG=en_US.UTF-8
set LC_ALL=en_US.UTF-8

set MSYSTEM=UCRT64
set CHERE_INVOKING=1
set MSYS2_PATH_TYPE=strict
set HOME=C:\msys64\home\%USERNAME%
set CLAUDE_CONFIG_DIR=C:\msys64\home\%USERNAME%\.claude
set CLAUDE_CODE_GIT_BASH_PATH=C:\msys64\usr\bin\bash.exe
set CLAUDE_ENV_FILE=/d/AI/Claude/Trinity/script/desktop-msys2-env.sh

start "" /D "D:\AI\Claude\Trinity" "C:\Users\en27553\AppData\Local\AnthropicClaude\claude.exe"