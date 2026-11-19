#!/usr/bin/env bun
// pi-sync: genera i prompt e gli agenti di pi dai command workflow e dagli agenti Trinity.
//
//   bun scripts/pi-sync/pi-sync.mjs [--out <dir>]      (oppure: mise run pi-sync)
//
// Destinazione di default: $(chezmoi source-path)/dot_pi/agent. Scrive solo i file elencati in
// PROMPTS e AGENTS, mai altro. Passi: regole globali (RULES), sostituzioni ancorate per file
// (patches.mjs), lint. Se un'ancora o il lint fallisce esce con 1 senza scrivere niente.
// Non lancia `chezmoi apply`.

import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { PATCHES } from "./patches.mjs";

export const REPO = resolve(import.meta.dir, "../..");
export const GENERATED = "trinity scripts/pi-sync (modifica il sorgente Trinity)";

// Command Trinity → prompts/<stesso nome>.md.
export const PROMPTS = [
  "commands/workflow/0_create-issue.md",
  "commands/workflow/1_create-worktree.md",
  "commands/workflow/2_work-issue.md",
  "commands/workflow/2_work-simplify.md",
  "commands/workflow/2_work-verify.md",
  "commands/workflow/3_independent-review.md",
  "commands/workflow/4_review-fix-loop.md",
  "commands/workflow/5_remove-worktree.md",
  "commands/issue-cycle.md",
];

const RW = "read, write, edit, bash, grep, find, ls";
const RO = "read, bash, grep, find, ls";
const REVIEWER = { source: "reviewer", tools: RO, extensions: false, allowed_subagents: "none", max_turns: 40 };

// Agenti pi → agents/<name>.md. Il corpo viene da agents/<source>.md, il frontmatter da qui.
// `description` sostituisce quella di Trinity, `note` la segue. In pi il modello si sceglie
// scegliendo l'agente: nella chiamata non si passano né model né thinking.
export const AGENTS = [
  { name: "DeepReasoner", source: "deep-reasoner", model: "openai-codex/gpt-6.2-astra", thinking: "high", tools: RW, max_turns: 50 },
  {
    name: "DeepSeek",
    source: "deep-reasoner",
    model: "deepseek/deepseek-flash",
    thinking: "high",
    tools: RW,
    max_turns: 50,
    description:
      "Gemello di DeepReasoner su DeepSeek (stesso prompt): secondo parere da un'altra famiglia di modelli. Usalo solo quando il prompt o l'utente lo chiede esplicitamente; altrimenti usa DeepReasoner.",
  },
  { name: "FastWorker", source: "fast-worker", model: "openai-codex/gpt-6.1-terra", thinking: "high", tools: RW, max_turns: 50 },
  { name: "BulkWorker", source: "bulk-worker", model: "anthropic/claude-haiku-5-5", thinking: "high", tools: RW },
  // thinking high: su deepseek-flash il livello medium non esiste.
  { name: "Scoper", source: "scoper", model: "deepseek/deepseek-flash", thinking: "high", tools: "read, grep, find, ls, bash", extensions: false, max_turns: 60 },
  { name: "ReviewerOpus", ...REVIEWER, model: "anthropic/claude-opus-5-5", thinking: "high" },
  {
    name: "Reviewer",
    ...REVIEWER,
    model: "openai-codex/gpt-6.2-sol",
    thinking: "high",
    note: "Gira su GPT: usalo solo quando il prompt o l'utente chiede la review GPT; altrimenti usa ReviewerOpus.",
  },
  {
    name: "ReviewerSoft",
    ...REVIEWER,
    model: "anthropic/claude-sonnet-5-5",
    thinking: "xhigh",
    note: "Gira su Sonnet con thinking xhigh, per i modi soft e verify di 3_independent-review: usalo solo quando il prompt o l'utente lo chiede; altrimenti usa ReviewerOpus.",
  },
  { name: "ArchScanner", source: "arch-scanner", model: "anthropic/claude-opus-5-5", thinking: "max", tools: "read, write, bash, grep, find, ls", allowed_subagents: "general-purpose" },
  { name: "DocumentationWriter", source: "documentation-writer", tools: "read, write, bash, grep, find, ls" },
  { name: "PerformanceOptimizer", source: "performance-optimizer", tools: "read, edit, bash, grep, find, ls" },
];

const BUILTIN_AGENTS = ["general-purpose", "Explore", "Plan"];

// trinity:reviewer chiamato con model sonnet / effort xhigh diventa ReviewerSoft: lo decidono le
// patch, qui c'è il default.
const AGENT_NAMES = {
  "trinity:deep-reasoner": "DeepReasoner",
  "trinity:fast-worker": "FastWorker",
  "trinity:bulk-worker": "BulkWorker",
  "trinity:scoper": "Scoper",
  "trinity:reviewer": "ReviewerOpus",
  "trinity:arch-scanner": "ArchScanner",
  "gpt-bridge:reviewer": "Reviewer",
  "gpt-bridge:deep-reasoner": "DeepSeek",
};
// Nomi nudi: solo quelli con il trattino. «reviewer» e «scoper» sono anche parole comuni.
const BARE_NAMES = {
  "deep-reasoner": "DeepReasoner",
  "fast-worker": "FastWorker",
  "bulk-worker": "BulkWorker",
  "arch-scanner": "ArchScanner",
  "documentation-writer": "DocumentationWriter",
  "performance-optimizer": "PerformanceOptimizer",
};

// Regole globali [regex, sostituzione], applicate in ordine a ogni sorgente prima delle patch.
const RULES = [
  // Slash command: in pi il nome del template è il nome del file.
  [/\/trinity:workflow:/g, "/"],
  [/\/trinity:issue-cycle\b/g, "/issue-cycle"],
  // Percorsi del plugin.
  [/\$\{CLAUDE_PLUGIN_ROOT\}\/skills\/linear\//g, "~/.pi/agent/skills/linear/"],
  [/\$\{CLAUDE_PLUGIN_ROOT\}\/commands\/(?:workflow\/)?/g, "~/.pi/agent/prompts/"],
  // Cartelle di lavoro.
  [/\.claude\/worktrees\//g, ".pi/worktrees/"],
  [/(\$HOME|~)\/\.claude\/tmp/g, "$1/.pi/agent/tmp"],
  // Argomento nominato di 5_remove-worktree. Negli altri file diventa prosa: lì pi sostituirebbe
  // un `$1` con il primo argomento di quel prompt.
  [/`\$worktree_name` = /g, "nome del worktree = "],
  [/\$worktree_name/g, () => "$1"],
  // Nome del prodotto.
  [/`claude -p`/g, "`pi -p`"],
  [/nella shell di Claude/g, "nella shell dell'agente"],
  [/sessione Claude Code/g, "sessione di pi"],
  [/quando Claude Code(\s+)compatta/g, "quando pi$1compatta"],
  // Tool.
  [/\bcon Grep\b/g, "con grep"],
  // Etichetta del modello negli esempi.
  [/(ICH-[\d-]+)-fable/g, "$1-sol"],
  [/`fable` → /g, "`sol` → "],
  [/review\+<base-name>-fable/g, "review+<base-name>-opus"],
  // Agenti: prima i nomi con prefisso, poi quelli nudi (non dentro un percorso).
  [/\b(?:trinity|gpt-bridge):[a-z][a-z-]*/g, (m) => AGENT_NAMES[m] ?? m],
  [new RegExp(`(?<![\\w/.:-])(?:${Object.keys(BARE_NAMES).join("|")})(?![\\w-]|\\.md)`, "g"), (m) => BARE_NAMES[m]],
];

// Token vietati in ogni file generato.
const FORBIDDEN = [
  "trinity:",
  "gpt-bridge",
  "CLAUDE_PLUGIN_ROOT",
  ".claude/worktrees",
  "~/.claude/",
  "AskUserQuestion",
  "SendMessage",
  "LiteLLM",
  "Hindsight",
  "claude -p",
  "Claude Code",
  "Implementer",
];
const FORBIDDEN_AGENT_KEYS = ["effort", "maxTurns", "gpt-model"];
const BARE_MODELS = ["fable", "sonnet", "opus", "haiku", "inherit"];

// Segnaposto che pi sostituisce nel corpo di un template (stessa regex di pi, anche nei blocchi di
// codice) e quelli previsti per file. Tutto il resto è un errore.
const TEMPLATE_TOKEN = /\$\{(?:\d+|ARGUMENTS|@):-[^}]*\}|\$\{@:\d+(?::\d+)?\}|\$(?:ARGUMENTS|@|\d+)/g;
const TEMPLATE_TOKENS = {
  "prompts/0_create-issue.md": ["$ARGUMENTS"],
  "prompts/1_create-worktree.md": ["$ARGUMENTS"],
  "prompts/2_work-issue.md": ["$ARGUMENTS"],
  "prompts/2_work-simplify.md": ["$ARGUMENTS"],
  "prompts/2_work-verify.md": ["$ARGUMENTS"],
  "prompts/3_independent-review.md": ["$ARGUMENTS"],
  "prompts/4_review-fix-loop.md": ["$ARGUMENTS"],
  "prompts/5_remove-worktree.md": ["$1", "$ARGUMENTS"],
  "prompts/issue-cycle.md": ["$ARGUMENTS"],
};

// Parser minimo del frontmatter: `chiave: valore`, valori tra virgolette, blocchi `>` e `|` (con
// `-` finale), scalari su più righe rientrate e liste `- voce`. I valori restano stringhe.
export function parseFrontmatter(text) {
  const m = /^---\n([\s\S]*?)\n---[ \t]*(?:\n|$)/.exec(text);
  if (!m) return { data: {}, body: text };
  const data = {};
  const lines = m[1].split("\n");
  let i = 0;
  while (i < lines.length) {
    if (/^\s*(?:#.*)?$/.test(lines[i])) {
      i++;
      continue;
    }
    const head = /^([A-Za-z_][\w-]*):(?:[ \t]+(.*))?$/.exec(lines[i]);
    if (!head) throw new Error(`frontmatter: riga non riconosciuta: «${lines[i]}»`);
    const block = [];
    for (i++; i < lines.length && /^(?:[ \t]+\S.*|[ \t]*)$/.test(lines[i]); i++) block.push(lines[i]);
    data[head[1]] = scalar((head[2] ?? "").trim(), block);
  }
  return { data, body: text.slice(m[0].length) };
}

function scalar(raw, block) {
  while (block.length && !block.at(-1).trim()) block.pop();
  const lines = block.map((l) => l.trim());
  if (/^[>|]-?$/.test(raw)) {
    const indent = Math.min(...block.filter((l) => l.trim()).map((l) => /^[ \t]*/.exec(l)[0].length));
    const text = block.map((l) => l.slice(indent)).join("\n");
    // `>` piega gli a capo singoli in spazi, `|` li tiene; senza `-` resta un a capo finale.
    const value = raw[0] === "|" ? text : text.replace(/(?<!\n)\n(?!\n)/g, " ").replace(/\n\n/g, "\n");
    return raw.endsWith("-") ? value : `${value}\n`;
  }
  if (!raw && lines.length && lines.every((l) => l.startsWith("- "))) return lines.map((l) => l.slice(2).trim());
  const value = [raw, ...lines].filter(Boolean).join(" ");
  if (/^".*"$/.test(value)) return JSON.parse(value);
  if (/^'.*'$/.test(value)) return value.slice(1, -1).replaceAll("''", "'");
  return value;
}

export function applyRules(text) {
  return RULES.reduce((t, [re, to]) => t.replace(re, to), text);
}

// Sostituzioni ancorate, in ordine: ogni `find` deve comparire esattamente una volta nel testo
// già passato dalle regole globali e dalle patch precedenti.
export function applyPatches(text, patches, file, errors) {
  for (const patch of patches) {
    const find = patch.find.replace(/\r\n/g, "\n");
    const count = text.split(find).length - 1;
    if (count === 1) text = text.replace(find, () => patch.replace.replace(/\r\n/g, "\n"));
    else errors.push(`${file}: ancora ${count ? `trovata ${count} volte` : "non trovata"}: «${find.split("\n")[0]}»`);
  }
  return text;
}

// Le stringhe libere vanno tra virgolette (una stringa JSON è YAML valido); gli altri valori
// vengono dalla tabella e sono scalari semplici.
function frontmatter(fields) {
  const lines = Object.entries(fields)
    .filter(([, value]) => value !== undefined)
    .map(([key, value]) => `${key}: ${value}`);
  return `---\n${lines.join("\n")}\ngenerated: ${GENERATED}\n---\n\n`;
}

const quote = (value) => (value === undefined ? undefined : JSON.stringify(value));
const finish = (head, body) => `${head}${body.trim()}\n`;

// Genera tutti i file in memoria. Ritorna { files: Map<percorso relativo, contenuto>, errors }.
export function generate(patches = PATCHES) {
  const read = (rel) => readFileSync(join(REPO, rel), "utf8").replace(/\r\n/g, "\n");
  const translate = (source, text) => applyPatches(applyRules(text), patches[source] ?? [], source, errors);
  const files = new Map();
  const sources = new Set([...PROMPTS, ...AGENTS.map((a) => `agents/${a.source}.md`)]);
  // Una chiave sbagliata in patches.mjs non verrebbe mai applicata, in silenzio.
  const errors = Object.keys(patches)
    .filter((key) => !sources.has(key))
    .map((key) => `patches.mjs: «${key}» non è un sorgente di pi-sync`);
  for (const source of PROMPTS) {
    const { data, body } = parseFrontmatter(translate(source, read(source)));
    const head = frontmatter({ description: quote(data.description), "argument-hint": quote(data["argument-hint"]) });
    // Marcatore per l'estensione collapse-command: mostra `▸ /comando args` al posto del prompt.
    const marker = `<!-- pi:cmd /${basename(source, ".md")} $ARGUMENTS -->`;
    files.set(`prompts/${basename(source)}`, finish(head, `${marker}\n\n${body.trim()}`));
  }
  for (const agent of AGENTS) {
    const source = `agents/${agent.source}.md`;
    // Il titolo con il nome Trinity prende il nome dell'agente pi (i gemelli hanno il proprio).
    const titled = read(source).replace(new RegExp(`^# ${agent.source}$`, "m"), `# ${agent.name}`);
    const { data, body } = parseFrontmatter(translate(source, titled));
    const head = frontmatter({
      name: agent.name,
      description: quote(agent.description ?? [data.description, agent.note].filter(Boolean).join(" ")),
      model: agent.model,
      thinking: agent.thinking,
      tools: agent.tools,
      extensions: agent.extensions,
      allowed_subagents: agent.allowed_subagents,
      prompt_mode: "append",
      max_turns: agent.max_turns,
      color: data.color,
    });
    files.set(`agents/${agent.name}.md`, finish(head, body));
  }
  return { files, errors: [...new Set(errors)] };
}

const lineOf = (text, index) => text.slice(0, index).split("\n").length;

// Controlli che bloccano la scrittura. Ritorna l'elenco degli errori.
export function lint(files) {
  const errors = [];
  const agents = new Set([...BUILTIN_AGENTS, ...AGENTS.map((a) => a.name)]);
  for (const [file, text] of files) {
    for (const token of FORBIDDEN) {
      const at = text.indexOf(token);
      if (at >= 0) errors.push(`${file}:${lineOf(text, at)}: token vietato «${token}»`);
    }
    for (const m of text.matchAll(/subagent_type:\s*([A-Za-z][\w:-]*)/g)) {
      if (!agents.has(m[1])) errors.push(`${file}:${lineOf(text, m.index)}: subagent_type «${m[1]}» non è un agente pi`);
    }
    if (file.startsWith("prompts/")) {
      for (const m of text.matchAll(TEMPLATE_TOKEN)) {
        if (!TEMPLATE_TOKENS[file]?.includes(m[0])) {
          errors.push(`${file}:${lineOf(text, m.index)}: segnaposto «${m[0]}» non previsto: pi lo sostituirebbe`);
        }
      }
      // In pi il modello non si passa nella chiamata: un nome nudo verrebbe risolto a caso.
      for (const m of text.matchAll(/`((?:model|effort): [^`]+)`/g)) {
        errors.push(`${file}:${lineOf(text, m.index)}: parametro di chiamata «${m[1]}»: in pi si sceglie l'agente`);
      }
    } else {
      const { data } = parseFrontmatter(text);
      for (const key of FORBIDDEN_AGENT_KEYS) {
        if (key in data) errors.push(`${file}: chiave «${key}» vietata nel frontmatter`);
      }
      if (BARE_MODELS.includes(data.model)) errors.push(`${file}: model «${data.model}» senza provider`);
    }
  }
  return errors;
}

// Solo lettura: gli AGENTS*.md della destinazione non sono di pi-sync, ma devono parlare degli
// stessi agenti. Ritorna avvisi che non bloccano.
export function checkAgentsDocs(out) {
  if (!existsSync(out)) return [];
  const warnings = [];
  for (const name of readdirSync(out).filter((n) => /^AGENTS.*\.md/.test(n)).sort()) {
    readFileSync(join(out, name), "utf8")
      .split("\n")
      .forEach((line, i) => {
        for (const token of ["Implementer", "trinity:"]) {
          if (line.includes(token)) warnings.push(`${name}:${i + 1}: contiene «${token}»`);
        }
      });
  }
  return warnings;
}

// Genera, controlla e scrive in `out`. Con errori non scrive niente.
export function sync(out, patches = PATCHES) {
  const { files, errors } = generate(patches);
  errors.push(...lint(files));
  if (errors.length) return { errors, written: [], unchanged: [] };
  const written = [];
  const unchanged = [];
  for (const [file, text] of files) {
    const path = join(out, file);
    if (existsSync(path) && readFileSync(path, "utf8") === text) {
      unchanged.push(file);
      continue;
    }
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, text);
    written.push(file);
  }
  return { errors, written, unchanged };
}

function defaultOut() {
  let source;
  try {
    const result = Bun.spawnSync(["chezmoi", "source-path"]);
    if (result.exitCode === 0) source = result.stdout.toString().trim();
  } catch {
    // chezmoi non installato: stesso errore di un exit code diverso da zero.
  }
  if (!source) throw new Error("`chezmoi source-path` è fallito: passa la destinazione con --out <dir>");
  return join(source, "dot_pi/agent");
}

function main(argv) {
  if (argv.length && (argv.length !== 2 || argv[0] !== "--out")) {
    console.error("Uso: bun scripts/pi-sync/pi-sync.mjs [--out <dir>]");
    return 2;
  }
  const out = resolve(argv[1] ?? defaultOut());
  console.log(`pi-sync: sorgente ${REPO}`);
  console.log(`pi-sync: destinazione ${out}`);
  const { errors, written, unchanged } = sync(out);
  if (errors.length) {
    console.error(`pi-sync: ${errors.length} errori, nessun file scritto`);
    for (const error of errors) console.error(`  ${error}`);
    return 1;
  }
  for (const file of written) console.log(`  scritto    ${file}`);
  console.log(`pi-sync: lint pulito, ${written.length} file scritti, ${unchanged.length} invariati`);
  for (const warning of checkAgentsDocs(out)) console.log(`  avviso (file non gestito da pi-sync) ${warning}`);
  return 0;
}

if (import.meta.main) {
  try {
    process.exit(main(process.argv.slice(2)));
  } catch (error) {
    console.error(`pi-sync: ${error.message}`);
    process.exit(1);
  }
}
