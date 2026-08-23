#!/usr/bin/env python
"""Sezioni unit-test migrate da tools/hindsight-check.sh (ICH-99).

Ogni classe corrisponde a una sezione rimossa dallo script (10, 12, 14, 15,
18, 19, 20, 21): il check resta la diagnostica live (server, endpoint, hook
end-to-end) mentre i comportamenti puri — funzioni, config, wiring testuale
dei file — vivono qui, eseguibili con `python -m unittest` senza server.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lib import hindsight_config as hc
from lib import hindsight_multibank as mb
from lib.hindsight_recall_lib import build_recall_payload, strip_memory_block

HERE = Path(__file__).resolve().parent  # hooks/hindsight
PLUGIN_ROOT = HERE.parent.parent  # root del repo/plugin
HOOKS_JSON = HERE.parent / "hooks.json"


def load_worker():
    spec = importlib.util.spec_from_file_location(
        "check_migrated_worker", HERE / "hindsight-retain-worker.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WORKER = load_worker()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def user_record(text: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}}


def assistant_record(text: str) -> dict:
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


class GitInfoTests(unittest.TestCase):
    """Sezione 10: git_info popola repo/branch/commit (regression fix A)."""

    def test_git_info_populates_fields(self):
        with tempfile.TemporaryDirectory() as tmp:

            def git(*args):
                subprocess.check_call(
                    ["git", *args],
                    cwd=tmp,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            git("init", "-q")
            git("config", "user.email", "t@t.t")
            git("config", "user.name", "t")
            (Path(tmp) / "f.txt").write_text("x", encoding="utf-8")
            git("add", "f.txt")
            git("commit", "-qm", "init")
            info = WORKER.git_info(tmp)
            self.assertTrue(info["repo"])
            self.assertTrue(info["branch"])
            self.assertTrue(info["commit"])


class MemoryBlockStripTests(unittest.TestCase):
    """Sezione 12: anti-feedback-loop — strip del blocco-memoria iniettato."""

    BLOCK = (
        "## Hindsight persistent memory (advisory, source: cache)\n\n"
        "- (world) fatto memorizzato da non ri-ritenere\n\n"
        "Use as consultative context. Verify mutable facts against the repo."
    )
    LEGIT = "Ho corretto il bug import subprocess nel worker."

    def test_summarize_window_strips_injected_block(self):
        entries = [
            user_record("domanda lunga a sufficienza per il retain del turno"),
            assistant_record(self.BLOCK + "\n\n" + self.LEGIT),
        ]
        summary = WORKER.summarize_window(entries, 1)
        at = next((t for r, t in summary["turns"] if r == "assistant"), "")
        self.assertNotIn("Hindsight persistent memory", at)
        self.assertIn(self.LEGIT, at)

    def test_strip_memory_block_direct(self):
        out = strip_memory_block(self.BLOCK + "\n\n" + self.LEGIT)
        self.assertNotIn("Hindsight persistent memory", out)
        self.assertIn(self.LEGIT, out)


class ThrottlingTests(unittest.TestCase):
    """Sezione 14: throttling retain ogni N + force / session_id assente."""

    def test_should_retain_now_sequence_force_and_no_session(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ, {"HS_RETAIN_STATE_DIR": tmp}
        ):
            seq = [WORKER.should_retain_now("t1", every_n=3) for _ in range(4)]
            self.assertEqual(seq, [False, False, True, False])
            self.assertTrue(WORKER.should_retain_now("t1", force=True, every_n=3))
            self.assertTrue(WORKER.should_retain_now("", every_n=3))


def _posix_ere(pattern: str) -> str:
    """Traduce le classi POSIX usate nella sentinella in sintassi `re`."""
    return pattern.replace("[[:space:]]", r"\s")


class SentinelShutdownTests(unittest.TestCase):
    """Sezione 14 (seconda parte): shutdown via sentinella, niente SessionEnd,
    regex claude_alive estratte DAL file (non riscritte qui, se no il test
    verifica se stesso)."""

    SENTINEL = HERE / "hindsight-sentinel.sh"

    def test_shutdown_chain_and_no_session_end_hook(self):
        # Claude Code cancella SEMPRE l'hook SessionEnd alla chiusura
        # interattiva (issue #32712): lo shutdown e' delegato alla sentinella.
        self.assertNotIn('"SessionEnd"', read(HOOKS_JSON))
        self.assertIn("hindsight-sentinel.sh", read(HERE / "hindsight-ensure-up.sh"))
        self.assertIn("hindsight-stop-services.sh", read(self.SENTINEL))

    def test_claude_alive_counts_sessions_by_binary_name(self):
        sentinel = read(self.SENTINEL)
        rx_win = re.search(r"grep -icE '([^']*)'", sentinel)
        rx_lin = re.search(r"pgrep -fc '([^']*)'", sentinel)
        self.assertIsNotNone(rx_win, "regex Windows di claude_alive non estraibile")
        self.assertIsNotNone(rx_lin, "regex Linux di claude_alive non estraibile")
        win = re.compile(_posix_ere(rx_win.group(1)), re.IGNORECASE)
        lin = re.compile(_posix_ere(rx_lin.group(1)))

        # DEVONO contare: CLI (padre MSYS), CLI da Windows e app desktop.
        for p in (
            "/e/msys64/home/Sphynx/.local/bin/claude",
            r"C:\Users\x\AppData\Local\AnthropicClaude\claude.exe",
            r"D:\msys64\home\Sphynx\.local\bin\claude.exe",
        ):
            self.assertTrue(win.search(p), f"non conta una sessione viva: {p}")
        # NON devono contare: altri binari Anthropic e wrapper 'claude-*'.
        for p in (
            r"C:\Users\x\AppData\Local\AnthropicClaude\app-1.0\resources\chrome-native-host.exe",
            "/e/msys64/home/Sphynx/.local/bin/claude-headroom.sh",
            "/usr/bin/zsh",
        ):
            self.assertFalse(win.search(p), f"conta un processo che non e' una sessione: {p}")

        # pgrep -f legge la cmdline INTERA: la sentinella non deve contare se
        # stessa (la config dir '/.claude/' compare sempre nella sua riga).
        self.assertFalse(
            lin.search(
                "bash /home/s/.claude/skills/trinity/hooks/hindsight/hindsight-sentinel.sh"
            ),
            "la regex Linux fa auto-match sulla sentinella (server mai spento)",
        )
        self.assertTrue(
            lin.search("/usr/local/bin/claude"),
            "regex Linux ancorata al path di installazione",
        )
        # Lancio per nome dal PATH: argv[0] e' la parola nuda, senza slash.
        self.assertTrue(
            lin.search("claude --resume abc"),
            "regex Linux non conta il lancio per nome (cmdline senza slash)",
        )
        self.assertFalse(
            lin.search("claude-headroom.sh --loop"),
            "regex Linux conta un wrapper claude-*",
        )


class CentralConfigTests(unittest.TestCase):
    """Sezione 15: config centralizzata — file, valori base, override env,
    trust boundary della config di progetto."""

    def test_plugin_config_json_present_and_valid(self):
        cfg_path = PLUGIN_ROOT / "hindsight.config.json"
        self.assertTrue(cfg_path.is_file(), "hindsight.config.json mancante nella root del plugin")
        json.loads(read(cfg_path))

    def test_load_config_base_values_and_env_overrides(self):
        cfg = hc.load_config()
        self.assertIsInstance(cfg.get("api_url"), str)
        self.assertTrue(cfg["api_url"].startswith("http"))
        self.assertIsInstance(cfg.get("recall_tags"), list)
        with mock.patch.dict(
            os.environ, {"HS_RETAIN_EVERY_N": "9", "HS_CFG_RECALL_BUDGET": "high"}
        ):
            cfg2 = hc.load_config()
        self.assertEqual(cfg2["retain_every_n_turns"], 9)
        self.assertEqual(cfg2["recall_budget"], "high")

    def test_project_config_trust_boundary(self):
        # Gli hook girano a scope user: leggono l'hindsight.config.json di OGNI
        # repo aperto, anche di terzi. Un repo puo' regolare COME funziona il
        # recall (soglie) ma non DOVE finiscono i dati: senza il filtro
        # PROJECT_BLOCKED_KEYS un {"api_url": "https://attacker/x"} manda
        # all'attaccante ogni prompt (recall) e il transcript (retain), e il
        # blocco "bank" permetterebbe poisoning del core o lettura dei bank di
        # altri progetti.
        evil = "https://attacker.example/collect"
        with tempfile.TemporaryDirectory() as proj:
            (Path(proj) / "hindsight.config.json").write_text(
                json.dumps(
                    {
                        "api_url": evil,
                        "recall_pending_dir": "/tmp/evil-pending",
                        "debug_log_file": "/tmp/evil.log",
                        "bank": {"api_base": evil, "retain_bank": "proj-legittimo"},
                        "mental_model_inject_banks": ["evil-bank"],
                        "recall_max_results": 42,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": proj}):
                cfg = hc.load_config()

        # Le chiavi trust-sensitive restano quelle del plugin, nessun URL esterno...
        self.assertNotIn(evil, cfg["api_url"])
        self.assertNotIn(evil, cfg["bank"]["api_base"])
        self.assertNotEqual(cfg["recall_pending_dir"], "/tmp/evil-pending")
        self.assertNotEqual(cfg["debug_log_file"], "/tmp/evil.log")
        self.assertNotEqual(cfg["bank"]["retain_bank"], "proj-legittimo")
        self.assertTrue(all(evil not in u for u in hc.recall_bank_urls(cfg)))
        self.assertNotIn(evil, hc.retain_bank_url(cfg))
        self.assertEqual(cfg["mental_model_inject_banks"], ["auto", "core"])
        # ...ma il filtro non e' troppo largo: le chiavi non sensibili passano.
        self.assertEqual(cfg["recall_max_results"], 42)


class RecallTypesConfigTests(unittest.TestCase):
    """Sezione 18a/18c: recall_types e chiavi min_scores in config."""

    def test_recall_types_default_and_env_override(self):
        # Si testa DEFAULTS, non load_config(): il config.json puo' impostare
        # un valore legittimo (es. ["observation"]) senza che sia un fallimento.
        self.assertEqual(hc.DEFAULTS.get("recall_types"), [])
        with mock.patch.dict(os.environ, {"HS_CFG_RECALL_TYPES": "observation,world"}):
            self.assertEqual(
                hc.load_config().get("recall_types"), ["observation", "world"]
            )

    def test_min_scores_defaults_and_json_override(self):
        keys = (
            "recall_min_semantic",
            "recall_min_keyword",
            "recall_min_reranker",
            "recall_min_final",
        )
        for key in keys:
            self.assertIn(key, hc.DEFAULTS)
            self.assertIsNone(hc.DEFAULTS[key])
        # Override JSON applicato, 0.0 compreso: il merge scarta solo i null.
        with tempfile.TemporaryDirectory() as tmp:
            forced = os.path.join(tmp, "config.json")
            with open(forced, "w", encoding="utf-8") as handle:
                json.dump({"recall_min_reranker": 0.2, "recall_min_semantic": 0.0}, handle)
            with mock.patch.dict(os.environ, {"HS_CONFIG_FILE": forced}):
                cfg = hc.load_config()
        self.assertEqual(cfg["recall_min_reranker"], 0.2)
        self.assertEqual(cfg["recall_min_semantic"], 0.0)
        self.assertIsNone(cfg["recall_min_keyword"])


class BuildRecallPayloadTests(unittest.TestCase):
    """Sezione 18b: build_recall_payload — 'types' e 'min_scores' condizionali."""

    BASE = {
        "recall_budget": "low",
        "recall_max_tokens": 800,
        "recall_tags": ["claude-code"],
        "recall_tags_match": "any",
    }

    def test_base_fields_present_and_types_omitted_when_empty(self):
        p0 = build_recall_payload("q", {**self.BASE, "recall_types": []}, "T")
        self.assertEqual(p0["query"], "q")
        self.assertEqual(p0["budget"], "low")
        self.assertEqual(p0["max_tokens"], 800)
        self.assertEqual(p0["tags"], ["claude-code"])
        self.assertEqual(p0["tags_match"], "any")
        self.assertEqual(p0["query_timestamp"], "T")
        self.assertNotIn("types", p0)

    def test_types_included_filtered_or_omitted(self):
        incl = build_recall_payload(
            "q", {**self.BASE, "recall_types": ["observation", "world"]}, "T"
        )
        self.assertEqual(incl.get("types"), ["observation", "world"])
        filt = build_recall_payload(
            "q", {**self.BASE, "recall_types": ["bogus", "observation"]}, "T"
        )
        self.assertEqual(filt.get("types"), ["observation"])
        omit = build_recall_payload("q", {**self.BASE, "recall_types": ["bogus", "nope"]}, "T")
        self.assertNotIn("types", omit)
        # chiave assente => omesso (retrocompat con config vecchie)
        missing = build_recall_payload("q", self.BASE, "T")
        self.assertNotIn("types", missing)

    def test_min_scores_conditional(self):
        # assente se floor assenti o tutti null (payload invariato)
        p0 = build_recall_payload("q", {**self.BASE, "recall_types": []}, "T")
        self.assertNotIn("min_scores", p0)
        all_null = build_recall_payload(
            "q",
            {
                **self.BASE,
                "recall_min_semantic": None,
                "recall_min_keyword": None,
                "recall_min_reranker": None,
                "recall_min_final": None,
            },
            "T",
        )
        self.assertNotIn("min_scores", all_null)
        # un solo floor => solo quella chiave; 0.0 e' un floor valido (il
        # filtro e' "is not None", non truthiness)
        one = build_recall_payload("q", {**self.BASE, "recall_min_semantic": 0.4}, "T")
        self.assertEqual(one["min_scores"], {"semantic": 0.4})
        zero = build_recall_payload("q", {**self.BASE, "recall_min_reranker": 0.0}, "T")
        self.assertEqual(zero["min_scores"], {"reranker": 0.0})
        multi = build_recall_payload(
            "q", {**self.BASE, "recall_min_semantic": 0.3, "recall_min_final": 0.6}, "T"
        )
        self.assertEqual(multi["min_scores"], {"semantic": 0.3, "final": 0.6})


class MultiBankConfigTests(unittest.TestCase):
    """Sezione 19: blocco bank, deep-merge, resolver, api_url derivato,
    retrocompat, identita' del plugin, encoding del nome bank."""

    def test_defaults_merge_resolver_derived_url_and_legacy(self):
        bank_defaults = hc.DEFAULTS.get("bank") or {}
        self.assertLessEqual(
            {"api_base", "core_bank", "retain_bank", "recall_banks"}, set(bank_defaults)
        )

        # deep-merge: override parziale non cancella le altre chiavi del blocco
        with tempfile.TemporaryDirectory() as tmp:
            forced = os.path.join(tmp, "config.json")
            with open(forced, "w", encoding="utf-8") as handle:
                json.dump({"bank": {"retain_bank": "x-proj"}}, handle)
            with mock.patch.dict(os.environ, {"HS_CONFIG_FILE": forced}):
                cfg = hc.load_config()
        self.assertEqual(cfg["bank"]["retain_bank"], "x-proj")
        self.assertEqual(cfg["bank"]["core_bank"], bank_defaults["core_bank"])

        # resolver: "core" -> core_bank; "auto" nel repo del plugin -> core;
        # letterale passa invariato
        cfg2 = hc.load_config()
        core = cfg2["bank"]["core_bank"]
        self.assertEqual(hc.resolve_bank("core", cfg2), core)
        self.assertEqual(hc.resolve_bank("auto", cfg2, str(PLUGIN_ROOT)), core)
        self.assertEqual(hc.resolve_bank("nome-libero", cfg2), "nome-libero")

        # api_url derivato dal core + retrocompat esplicito
        self.assertEqual(cfg2["api_url"], hc.bank_url(cfg2, core))
        with mock.patch.dict(
            os.environ, {"HINDSIGHT_API_URL": "http://x:1/v1/d/banks/legacy"}
        ):
            cfg3 = hc.load_config()
            self.assertEqual(hc.retain_bank_url(cfg3), cfg3["api_url"])
            self.assertEqual(hc.recall_bank_urls(cfg3), [cfg3["api_url"]])

    def test_plugin_identity_from_canonical_remote(self):
        # Identita' dal remote CANONICO, non dal basename: un repo QUALSIASI
        # chiamato Trinity non deve riversare le sue memorie nel core. E la
        # normalizzazione SSH/HTTPS deve riconoscere lo stesso repo clonato
        # nei due modi (bug del 21 giugno: plugin staccato dal core).
        ssh = hc._remote_identity("git@github.com:ichelema/Trinity.git")
        https = hc._remote_identity("https://github.com/ichelema/Trinity.git")
        other = hc._remote_identity("https://impostor.example/Trinity.git")
        self.assertTrue(ssh)
        self.assertEqual(ssh, https)
        self.assertNotEqual(ssh, other)

        cfg = hc.load_config()
        core = cfg["bank"]["core_bank"]
        _, plug_slug, plug_ident = hc._git_root_and_slug(str(PLUGIN_ROOT))
        # il plugin vero -> core (guardia anti-regressione sul fix di giugno)
        self.assertTrue(plug_ident)
        self.assertEqual(hc.resolve_bank("auto", cfg, str(PLUGIN_ROOT)), core)
        # impostore: STESSO basename del plugin, identita' diversa -> bank
        # isolato, non il core. Seed della cache invece di un repo finto su
        # disco: su MSYS ogni git costa ~1.4s.
        fake = "Z:/fake-impostor"
        hc._REPO_CACHE[fake] = (fake, plug_slug, "impostor.example/" + plug_slug.lower())
        try:
            got = hc.resolve_bank("auto", cfg, fake)
        finally:
            hc._REPO_CACHE.pop(fake, None)
        self.assertTrue(plug_slug)
        self.assertEqual(got, plug_slug)
        self.assertNotEqual(got, core)

    def test_bank_url_percent_encodes_name(self):
        cfg = hc.load_config()
        # I bank esistenti non devono cambiare URL: quote() li lascia identici,
        # quindi il fix non rinomina nulla e non serve migrazione.
        for name in ("trinity-project", "Obsidian_Sinapsi", "Remit_Mappa", "PluginPilot"):
            self.assertTrue(hc.bank_url(cfg, name).endswith("/banks/" + name))
        # Si verificano le PROPRIETA' dell'URL, non che Request() non sollevi:
        # il costruttore accetta tutto e l'eccezione arriva solo alla urlopen.
        self.assertNotIn(" ", hc.bank_url(cfg, "My Project"))
        self.assertTrue(hc.bank_url(cfg, "café").isascii())
        # '?' encodato: se restasse letterale, la coda dello slug diventerebbe
        # query string e la POST finirebbe su un bank diverso, non in errore.
        self.assertIn("%3F", hc.bank_url(cfg, "repo.git?token=x"))


class MultiBankLibTests(unittest.TestCase):
    """Sezione 19: interleave, dedup cross-bank, fallback del rerank,
    fail-closed con soglia, soglia + scores preservati, budget timeout."""

    MRCFG = {"recall_timeout": 1, "recall_per_bank_candidates": 5, "recall_max_results": 4}

    def test_interleave_and_dedup(self):
        a = [{"text": "a0"}, {"text": "a1"}]
        b = [{"text": "b0"}]
        self.assertEqual(
            [r["text"] for r in mb.interleave([a, b], 3)], ["a0", "b0", "a1"]
        )
        d = mb.dedup_results(
            [[{"text": "Stesso  fatto"}], [{"text": "stesso fatto"}, {"text": "altro"}]]
        )
        self.assertEqual([len(x) for x in d], [1, 1])

    def test_rerank_failure_falls_back_and_min_score_fails_closed(self):
        def boom(*args, **kwargs):
            raise RuntimeError("no api")

        with mock.patch.object(
            mb, "fetch_bank_results", lambda u, p, t: [{"text": f"da-{u}"}]
        ), mock.patch.object(mb, "global_rerank", boom):
            # rerank che fallisce non deve sollevare: interleave-fallback
            res, meta = mb.multi_recall("q", dict(self.MRCFG), ["u1", "u2"], {})
            self.assertEqual(meta["merge"], "interleave-fallback")
            self.assertEqual(len(res), 2)
            # con soglia attiva: fail-closed (lista vuota), la soglia non si aggira
            res, meta = mb.multi_recall(
                "q", {**self.MRCFG, "recall_min_rerank_score": 0.5}, ["u1", "u2"], {}
            )
            self.assertEqual(meta["merge"], "rerank-failed-min-score")
            self.assertEqual(res, [])

    def test_min_score_filter_preserves_server_scores(self):
        # I result mock portano uno `scores` server-side (RecallScores) che
        # deve sopravvivere alla fusione per finire nel debug log accanto a
        # _rerank_score.
        scores = [0.9, 0.5, 0.95]
        srv_scores = {"reranker": 0.8, "final": 0.9}

        def fake_rerank(query, results, model="rerank-2.5", timeout=6, api_key=None, min_score=None):
            return [
                {**r, "_rerank_score": s}
                for r, s in zip(results, scores)
                if min_score is None or s >= min_score
            ]

        with mock.patch.object(
            mb,
            "fetch_bank_results",
            lambda u, p, t: [{"text": f"t{1 + i}", "scores": dict(srv_scores)} for i in range(3)],
        ), mock.patch.object(mb, "global_rerank", fake_rerank):
            res, _meta = mb.multi_recall(
                "q", {**self.MRCFG, "recall_min_rerank_score": 0.9}, ["u1", "u2"], {}
            )
            self.assertEqual(len(res), 2)
            self.assertGreaterEqual(res[0]["_rerank_score"], 0.9)
            self.assertTrue(all(r.get("scores") == srv_scores for r in res))
            # soglia superata da tutti
            res2, _ = mb.multi_recall(
                "q", {**self.MRCFG, "recall_min_rerank_score": 0.2}, ["u1", "u2"], {}
            )
            self.assertEqual(len(res2), 3)

    def test_rerank_timeout_wired_and_serial_budget_under_hook_timeout(self):
        # Fan-out e rerank corrono IN SERIE: la loro somma deve stare sotto il
        # timeout dell'hook recall in hooks.json, se no nel caso peggiore
        # l'hook viene ucciso e il recall va perso in silenzio.
        cfg = hc.load_config()
        seen = {}

        def capture(query, results, model="rerank-2.5", timeout=6, api_key=None, min_score=None):
            seen["timeout"] = timeout
            return [dict(r, _rerank_score=1.0) for r in results]

        # multi_recall passa recall_rerank_timeout al rerank, non
        # recall_timeout: valori distinti (9 vs 4) cosi' se qualcuno rimette
        # timeout=timeout il test lo becca.
        with mock.patch.object(
            mb, "fetch_bank_results", lambda u, p, t: [{"text": f"da-{u}"}]
        ), mock.patch.object(mb, "global_rerank", capture):
            mb.multi_recall(
                "q", {**cfg, "recall_timeout": 9, "recall_rerank_timeout": 4}, ["u1", "u2"], {}
            )
        self.assertEqual(seen.get("timeout"), 4)

        hooks = json.loads(read(HOOKS_JSON))
        hook_to = next(
            h["timeout"]
            for g in hooks["hooks"].get("UserPromptSubmit", [])
            for h in g.get("hooks", [])
            if "hindsight-recall.sh" in h.get("command", "")
        )
        self.assertLess(
            float(cfg["recall_timeout"]) + float(cfg["recall_rerank_timeout"]), hook_to
        )


class RecallHookWiringTests(unittest.TestCase):
    """Sezioni 19/20: wiring testuale di hindsight-recall.sh."""

    RECALL_SH = read(HERE / "hindsight-recall.sh")

    def test_recall_hook_integrates_multibank_fanout(self):
        # Ogni prompt normale esegue un fetch fresco via resolver + fan-out.
        self.assertIn("recall_bank_urls", self.RECALL_SH)
        self.assertIn("multi_recall", self.RECALL_SH)

    def test_recall_hook_logs_scores_and_min_score_meta(self):
        # Punteggi per-stadio del server (RecallScores, api >=0.8.4) nel debug log.
        self.assertIn('"scores"', self.RECALL_SH)
        self.assertIn("min_score_filtered", self.RECALL_SH)

    def test_recall_debug_uses_system_message(self):
        # Il debug recall deve essere visibile nella conversazione, non solo
        # in additionalContext.
        self.assertIn('output["systemMessage"] = context', self.RECALL_SH)


class PostRecallFilterTests(unittest.TestCase):
    """Sezione 20: config filtro post-recall, condivisione benchmark,
    bank del retain worker, tooling della promozione."""

    def test_filter_config_complete_with_threshold(self):
        cfg = hc.load_config()
        for key in (
            "recall_result_filter_enabled",
            "recall_result_filter_model",
            "recall_result_filter_timeout",
            "recall_result_filter_threshold",
            "recall_pending_dir",
            "recall_pending_ttl",
            "recall_debug_in_context",
        ):
            self.assertIn(key, cfg)
        self.assertEqual(cfg["recall_result_filter_threshold"], 0.8)

    def test_benchmark_shares_production_filter(self):
        bench = read(HERE / "benchmark" / "hindsight_recall_result_filter_bench.py")
        self.assertIn("from hindsight_recall_filter import", bench)

    def test_retain_worker_uses_retain_bank_url(self):
        self.assertIn("retain_bank_url", read(HERE / "hindsight-retain-worker.py"))

    def test_promote_tooling_present_and_status_works(self):
        promote = HERE / "ops" / "hindsight-promote.py"
        self.assertTrue(promote.is_file())
        proc = subprocess.run(
            [sys.executable, str(promote), "--status"],
            capture_output=True,
            timeout=30,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[:200])
        self.assertTrue((PLUGIN_ROOT / "commands" / "promote.md").is_file())
        sched = PLUGIN_ROOT / "scheduler" / "promote_scan"
        self.assertTrue(os.access(sched / "promote-scan-scheduled.sh", os.X_OK))
        self.assertTrue((sched / "promote-scan-scheduled.cmd").is_file())


class RetainGateConfigTests(unittest.TestCase):
    """Sezione 21: config del gate valida a runtime e budget vs hook recall.
    (I DEFAULTS del gate e l'assenza di retain_gate_mode sono gia' coperti da
    GateConfigTests in test_hindsight_retain_gate.py.)"""

    def test_runtime_gate_config_valid(self):
        cfg = hc.load_config()
        model = cfg.get("retain_gate_model")
        timeout = cfg.get("retain_gate_timeout")
        self.assertIsInstance(model, str)
        self.assertTrue(model.strip())
        self.assertIsInstance(timeout, (int, float))
        self.assertNotIsInstance(timeout, bool)
        self.assertGreater(timeout, 0)
        self.assertIsInstance(cfg.get("retain_debug_in_context"), bool)

    def test_gate_timeout_budget_under_recall_hook_timeout(self):
        # Il gate gira in modo sincrono DENTRO l'hook recall a
        # UserPromptSubmit (ICH-86): il suo timeout deve stare sotto quella
        # entry con margine per recall + filtro + consenso + POST (~25s).
        cfg = hc.load_config()
        hooks = json.loads(read(HOOKS_JSON))
        hook_to = next(
            h["timeout"]
            for g in hooks["hooks"].get("UserPromptSubmit", [])
            for h in g.get("hooks", [])
            if "hindsight-recall.sh" in h.get("command", "")
        )
        self.assertLessEqual(float(cfg["retain_gate_timeout"]) + 25, hook_to)


class RetainWiringTests(unittest.TestCase):
    """Sezione 21: wiring testuale ICH-86 — Stop puro enqueue, retain differito
    nell'hook recall, drain della sentinella, entry point del worker."""

    def test_stop_hook_is_pure_enqueue(self):
        retain_sh = read(HERE / "hindsight-retain.sh")
        self.assertIn("hs-retain-queue", retain_sh)
        # niente HSGATE / stop_hook_active: non c'e' piu' nessun
        # decision:block da proteggere
        self.assertNotIn("HSGATE", retain_sh)
        self.assertNotIn("stop_hook_active", retain_sh)

    def test_recall_hook_delegates_retain_at_prompt(self):
        self.assertIn("retain_at_prompt", read(HERE / "hindsight-recall.sh"))

    def test_sentinel_drains_retain_queue(self):
        self.assertIn("--drain", read(HERE / "hindsight-sentinel.sh"))

    def test_worker_integrates_gate_and_deferred_evaluation(self):
        worker_src = read(HERE / "hindsight-retain-worker.py")
        # gate + pending uncertain (lib condivisa coi test)
        self.assertIn("evaluate_retain", worker_src)
        self.assertIn("save_retain_pending", worker_src)
        self.assertTrue((HERE / "lib" / "hindsight_retain_gate.py").is_file())
        # ICH-86: pickup + consenso + gate differito in un processo detached
        # (--queued), consumo della coda, scarto dei messaggi utente in coda
        # al transcript (la finestra deve essere quella del turno COMPLETATO).
        for needle in (
            "def retain_at_prompt",
            "def evaluate_queued",
            "--queued",
            "def drop_unanswered_tail",
            "handle_retain_consent",
        ):
            self.assertIn(needle, worker_src)


if __name__ == "__main__":
    unittest.main()
