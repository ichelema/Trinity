const fs = require('fs');
const path = require('path');
const { getClaudeDir } = require('./ponytail-config');

const STATE_FILE = '.ponytail-active';

const stateDir = getClaudeDir();

const statePath = path.join(stateDir, STATE_FILE);

function setMode(mode) {
  fs.mkdirSync(path.dirname(statePath), { recursive: true });
  fs.writeFileSync(statePath, mode);
}

function clearMode() {
  try { fs.unlinkSync(statePath); } catch (e) {}
}

// Live mode written by activate/mode-tracker. Absent flag = ponytail off.
function readMode() {
  try {
    return fs.readFileSync(statePath, 'utf8').trim() || null;
  } catch (e) {
    return null;
  }
}

// Native Claude: SessionStart accepts raw stdout, but SubagentStart needs the
// hookSpecificOutput JSON form or the context is dropped.
function writeHookOutput(event, context = '') {
  if (event === 'SubagentStart') {
    process.stdout.write(JSON.stringify(
      { hookSpecificOutput: { hookEventName: event, additionalContext: context } }));
    return;
  }
  process.stdout.write(context);
}

module.exports = {
  clearMode,
  readMode,
  setMode,
  writeHookOutput,
};
