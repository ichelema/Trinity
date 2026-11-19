// Test di scripts/pi-sync: bun test test/pi-sync.test.mjs
import { afterAll, describe, expect, test } from "bun:test";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PATCHES } from "../scripts/pi-sync/patches.mjs";
import {
  AGENTS,
  GENERATED,
  PROMPTS,
  REPO,
  applyPatches,
  applyRules,
  checkAgentsDocs,
  generate,
  lint,
  parseFrontmatter,
  sync,
} from "../scripts/pi-sync/pi-sync.mjs";

const source = (rel) => readFileSync(join(REPO, rel), "utf8");
const EXPECTED = [
  ...PROMPTS.map((p) => `prompts/${p.split("/").pop()}`),
  ...AGENTS.map((a) => `agents/${a.name}.md`),
].sort();

const tmp = mkdtempSync(join(tmpdir(), "pi-sync-test-"));
afterAll(() => rmSync(tmp, { recursive: true, force: true }));

// Tutti i file sotto `dir`, come percorsi relativi con `/`, ordinati.
const tree = (dir, base = "") =>
  readdirSync(join(dir, base), { withFileTypes: true })
    .flatMap((e) => (e.isDirectory() ? tree(dir, `${base}${e.name}/`) : [`${base}${e.name}`]))
    .sort();

describe("parseFrontmatter sui file reali", () => {
  test("blocco `>-` degli agenti", () => {
    const { data, body } = parseFrontmatter(source("agents/deep-reasoner.md"));
    expect(data.description).toStartWith("Analisi ad alto ragionamento: architettura, debug complesso");
    expect(data.description).toEndWith("se il task lo chiede esplicitamente.");
    expect(data.description).not.toContain("\n");
    expect(data.model).toBe("fable");
    expect(data["gpt-model"]).toBe("claude-gpt-6-2-sol-xhigh");
    expect(data.color).toBe("purple");
    expect(body).toStartWith("# deep-reasoner\n");
  });

  test("scalare su più righe rientrate dei command", () => {
    const { data, body } = parseFrontmatter(source("commands/workflow/2_work-issue.md"));
    expect(data.description).toStartWith("Prende in carico una o più issue Linear");
    expect(data.description).not.toContain("\n");
    expect(data["argument-hint"]).toBe("<issue-id...> <model> [auto [review|loop]]");
    expect(data["disable-model-invocation"]).toBe("true");
    expect(body.trim()).toStartWith("Prendi in carico le issue Linear indicate");
  });

  test("valore tra virgolette e lista", () => {
    expect(parseFrontmatter(source("commands/explain.md")).data["argument-hint"]).toBe("[cosa non è chiaro]");
    expect(parseFrontmatter(source("commands/workflow/5_remove-worktree.md")).data.arguments).toEqual(["worktree_name"]);
  });

  test("blocchi `|` e `>` (in Trinity oggi non compaiono)", () => {
    const { data } = parseFrontmatter("---\na: |\n  x\n   y\n\nb: >\n  p\n  q\nc: |-\n  z\n---\ncorpo\n");
    expect(data).toEqual({ a: "x\n y\n", b: "p q\n", c: "z" });
  });

  test("ogni sorgente usato ha una description", () => {
    for (const rel of [...PROMPTS, ...AGENTS.map((a) => `agents/${a.source}.md`)]) {
      expect(parseFrontmatter(source(rel)).data.description, rel).toMatch(/\S/);
    }
  });

  test("senza frontmatter e riga non riconosciuta", () => {
    expect(parseFrontmatter("solo corpo\n")).toEqual({ data: {}, body: "solo corpo\n" });
    expect(() => parseFrontmatter("---\nnon una chiave\n---\n")).toThrow("riga non riconosciuta");
  });
});

describe("regole globali", () => {
  test("slash command e percorsi del plugin", () => {
    // biome-ignore lint/suspicious/noTemplateCurlyInString: è il segnaposto letterale dei command Trinity
    const text ="`/trinity:workflow:2_work-issue`, `${CLAUDE_PLUGIN_ROOT}/commands/workflow/5_remove-worktree.md`, `${CLAUDE_PLUGIN_ROOT}/commands/issue-cycle.md`";
    expect(applyRules(text)).toBe(
      "`/2_work-issue`, `~/.pi/agent/prompts/5_remove-worktree.md`, `~/.pi/agent/prompts/issue-cycle.md`",
    );
  });

  test("nomi degli agenti: con prefisso, nudi, non nei percorsi", () => {
    expect(applyRules("trinity:reviewer, gpt-bridge:reviewer, gpt-bridge:deep-reasoner")).toBe("ReviewerOpus, Reviewer, DeepSeek");
    expect(applyRules("(quelli vanno a fast-worker o deep-reasoner)")).toBe("(quelli vanno a FastWorker o DeepReasoner)");
    expect(applyRules("agents/deep-reasoner.md e il reviewer")).toBe("agents/deep-reasoner.md e il reviewer");
    // Un nome sconosciuto resta com'è: lo ferma il lint.
    expect(applyRules("trinity:sconosciuto")).toBe("trinity:sconosciuto");
  });

  test("argomento nominato di 5_remove-worktree", () => {
    expect(applyRules("con `$worktree_name` = `x`; rimuovi `$worktree_name`")).toBe("con nome del worktree = `x`; rimuovi `$1`");
  });
});

describe("patch ancorate", () => {
  test("ancora presente una volta: sostituita, senza interpretare `$`", () => {
    const errors = [];
    expect(applyPatches("uno due tre", [{ find: "due", replace: "$& $1" }], "f.md", errors)).toBe("uno $& $1 tre");
    expect(errors).toEqual([]);
  });

  test("ancora mancante: errore con file e prima riga dell'ancora, testo intatto", () => {
    const errors = [];
    expect(applyPatches("uno due tre", [{ find: "quattro\ncinque", replace: "x" }], "commands/f.md", errors)).toBe("uno due tre");
    expect(errors).toEqual(["commands/f.md: ancora non trovata: «quattro»"]);
  });

  test("ancora doppia: errore", () => {
    const errors = [];
    applyPatches("due e due", [{ find: "due", replace: "x" }], "commands/f.md", errors);
    expect(errors).toEqual(["commands/f.md: ancora trovata 2 volte: «due»"]);
  });
});

describe("lint", () => {
  const prompt = (body) => new Map([["prompts/2_work-issue.md", `---\ndescription: "x"\n---\n\n${body}\n`]]);

  test("file pulito", () => {
    expect(lint(prompt("Dividi `$ARGUMENTS`; `subagent_type: ReviewerOpus`, `subagent_type: Explore`."))).toEqual([]);
  });

  test("token vietato, con file e riga", () => {
    // Tre righe di frontmatter e una vuota: il token sta alla riga 6.
    expect(lint(prompt("riga\nvia proxy LiteLLM"))).toEqual(["prompts/2_work-issue.md:6: token vietato «LiteLLM»"]);
  });

  test("subagent_type che non è un agente pi", () => {
    expect(lint(prompt("`subagent_type: Scopritore`"))[0]).toContain("subagent_type «Scopritore» non è un agente pi");
  });

  test("segnaposto che pi sostituirebbe", () => {
    expect(lint(prompt('awk "{print $2}" e "$@"')).map((e) => e.match(/«(.+?)»/)[1])).toEqual(["$2", "$@"]);
  });

  test("model o effort passati nella chiamata", () => {
    expect(lint(prompt("con `subagent_type: ReviewerOpus` e `model: sonnet`"))[0]).toContain("parametro di chiamata «model: sonnet»");
  });

  test("frontmatter di un agente: chiavi Trinity e model senza provider", () => {
    const errors = lint(new Map([["agents/X.md", "---\nname: X\nmodel: sonnet\neffort: high\nmaxTurns: 3\n---\n\ncorpo\n"]]));
    expect(errors).toEqual([
      "agents/X.md: chiave «effort» vietata nel frontmatter",
      "agents/X.md: chiave «maxTurns» vietata nel frontmatter",
      "agents/X.md: model «sonnet» senza provider",
    ]);
  });
});

describe("integrazione sui sorgenti Trinity reali", () => {
  test("generazione: nessuna ancora rotta, lint pulito, file attesi", () => {
    const { files, errors } = generate();
    expect(errors).toEqual([]);
    expect(lint(files)).toEqual([]);
    expect([...files.keys()].sort()).toEqual(EXPECTED);
    for (const [file, text] of files) {
      const { data } = parseFrontmatter(text);
      expect(data.generated, file).toBe(GENERATED);
      expect(Object.keys(data), file).toEqual(
        file.startsWith("prompts/") ? expect.arrayContaining(["description", "generated"]) : expect.arrayContaining(["name", "description", "tools", "prompt_mode", "generated"]),
      );
    }
    for (const agent of AGENTS) {
      const text = files.get(`agents/${agent.name}.md`);
      const { data } = parseFrontmatter(text);
      expect([data.name, data.model, data.thinking], agent.name).toEqual([agent.name, agent.model, agent.thinking]);
      // Il titolo con il nome Trinity prende il nome dell'agente pi, anche per i gemelli.
      if (source(`agents/${agent.source}.md`).includes(`\n# ${agent.source}\n`)) expect(text).toContain(`\n# ${agent.name}\n`);
    }
  });

  test("ogni prompt inizia con il marcatore del comando per collapse-command", () => {
    const { files } = generate();
    for (const [file, text] of files) {
      if (!file.startsWith("prompts/")) continue;
      const name = file.slice("prompts/".length, -".md".length);
      expect(parseFrontmatter(text).body.trimStart().startsWith(`<!-- pi:cmd /${name} $ARGUMENTS -->\n\n`), file).toBe(true);
    }
  });

  test("sync: scrive solo i propri file, lascia gli altri, ed è idempotente", () => {
    const out = join(tmp, "out");
    const others = { "agents/Explore.md": "non mio\n", "prompts/linear.md": "non mio\n", "AGENTS_Sol.md": "usa Implementer\n" };
    for (const [rel, text] of Object.entries(others)) {
      mkdirSync(join(out, rel, ".."), { recursive: true });
      writeFileSync(join(out, rel), text);
    }
    const first = sync(out);
    expect(first.errors).toEqual([]);
    expect(first.written.sort()).toEqual(EXPECTED);
    expect(tree(out)).toEqual([...EXPECTED, ...Object.keys(others)].sort());
    for (const [rel, text] of Object.entries(others)) expect(readFileSync(join(out, rel), "utf8")).toBe(text);
    // Il controllo sugli AGENTS*.md legge soltanto e avvisa.
    expect(checkAgentsDocs(out)).toEqual(["AGENTS_Sol.md:1: contiene «Implementer»"]);

    const before = Object.fromEntries(EXPECTED.map((rel) => [rel, readFileSync(join(out, rel), "utf8")]));
    const second = sync(out);
    expect(second.written).toEqual([]);
    expect(second.unchanged.sort()).toEqual(EXPECTED);
    for (const rel of EXPECTED) expect(readFileSync(join(out, rel), "utf8")).toBe(before[rel]);
  });

  test("sync: con un'ancora rotta non scrive niente", () => {
    const out = join(tmp, "out-rotto");
    const patches = { ...PATCHES, "commands/workflow/0_create-issue.md": [{ find: "ancora che il sorgente\nnon contiene", replace: "x" }] };
    const { errors, written } = sync(out, patches);
    expect(errors).toEqual(["commands/workflow/0_create-issue.md: ancora non trovata: «ancora che il sorgente»"]);
    expect(written).toEqual([]);
    expect(existsSync(out)).toBe(false);
  });

  test("sync: con un errore di lint non scrive niente", () => {
    const out = join(tmp, "out-lint");
    // La patch reintroduce un token vietato in un prompt altrimenti pulito.
    const patches = { ...PATCHES, "commands/workflow/0_create-issue.md": [{ find: "## Perimetro", replace: "## Perimetro (LiteLLM)" }] };
    const { errors, written } = sync(out, patches);
    expect(errors).toHaveLength(1);
    expect(errors[0]).toMatch(/^prompts\/0_create-issue\.md:\d+: token vietato «LiteLLM»$/);
    expect(written).toEqual([]);
    expect(existsSync(out)).toBe(false);
  });

  test("una chiave di patches.mjs che non è un sorgente è un errore", () => {
    expect(generate({ "commands/workflow/9_inesistente.md": [] }).errors).toContain(
      "patches.mjs: «commands/workflow/9_inesistente.md» non è un sorgente di pi-sync",
    );
  });

  test("CLI: --out scrive e chiude con 0", () => {
    const out = join(tmp, "out-cli");
    const run = Bun.spawnSync(["bun", join(REPO, "scripts/pi-sync/pi-sync.mjs"), "--out", out]);
    expect(run.exitCode).toBe(0);
    expect(run.stdout.toString()).toContain(`lint pulito, ${EXPECTED.length} file scritti, 0 invariati`);
    expect(tree(out)).toEqual(EXPECTED);
  });
});
