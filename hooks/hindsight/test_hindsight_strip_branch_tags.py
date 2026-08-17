#!/usr/bin/env python
"""Test della migrazione ICH-85 (rimozione tag branch:* dal DB Hindsight).

Copre le funzioni pure senza DB (strip_branch_tags, build_dry_run_report,
check_backup, verify_snapshot) e l'orchestrazione dei comandi (--apply,
--verify, --revert) con un adapter DB finto in-memory al posto di psycopg2:
nessuna connessione reale, nessuna scrittura sul DB vero."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPT_PATH = HERE / "ops" / "hindsight-strip-branch-tags.py"


def load_module():
    spec = importlib.util.spec_from_file_location("strip_branch_tags_under_test", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"impossibile caricare {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = load_module()


# --------------------------------------------------------------------------
# Funzioni pure
# --------------------------------------------------------------------------

class StripBranchTagsTests(unittest.TestCase):
    def test_removes_branch_tags_preserving_order(self):
        self.assertEqual(
            mod.strip_branch_tags(["claude-code", "repo:Trinity", "branch:master", "procedure"]),
            ["claude-code", "repo:Trinity", "procedure"],
        )

    def test_no_branch_tags_is_noop(self):
        tags = ["claude-code", "repo:Trinity", "procedure"]
        out = mod.strip_branch_tags(tags)
        self.assertEqual(out, tags)
        self.assertIsNot(out, tags)  # nuova lista, non alias

    def test_empty_and_none(self):
        self.assertEqual(mod.strip_branch_tags([]), [])
        self.assertEqual(mod.strip_branch_tags(None), [])

    def test_only_branch_tags_becomes_empty(self):
        self.assertEqual(mod.strip_branch_tags(["branch:master", "branch:foo"]), [])

    def test_multiple_branch_values_all_removed(self):
        self.assertEqual(
            mod.strip_branch_tags(["a", "branch:x", "b", "branch:y", "c"]),
            ["a", "b", "c"],
        )


class BuildDryRunReportTests(unittest.TestCase):
    def test_counts_per_bank_and_table_and_distinct_tags(self):
        totals_by_table = {
            "documents": {"trinity-project": 10, "other-bank": 2},
            "memory_units": {"trinity-project": 50},
        }
        interested_rows_by_table = {
            "documents": [
                {"id": "d1", "bank_id": "trinity-project", "tags": ["branch:master", "x"]},
                {"id": "d2", "bank_id": "trinity-project", "tags": ["branch:master"]},
                {"id": "d3", "bank_id": "trinity-project", "tags": ["branch:feature-1"]},
            ],
            "memory_units": [
                {"id": "m1", "bank_id": "trinity-project", "tags": ["branch:master"]},
            ],
        }
        report = mod.build_dry_run_report("2026-08-17T00:00:00Z", totals_by_table, interested_rows_by_table)

        self.assertEqual(report["watermark"], "2026-08-17T00:00:00Z")
        self.assertEqual(report["total_interested_rows"], 4)
        self.assertEqual(report["distinct_branch_tags"], ["branch:feature-1", "branch:master"])

        docs = report["tables"]["documents"]
        self.assertEqual(docs["totals_by_bank"], {"trinity-project": 10, "other-bank": 2})
        self.assertEqual(docs["interested_by_bank"], {"trinity-project": 3})
        self.assertEqual(
            docs["branch_tags_by_bank"]["trinity-project"],
            {"branch:master": 2, "branch:feature-1": 1},
        )

        mus = report["tables"]["memory_units"]
        self.assertEqual(mus["interested_by_bank"], {"trinity-project": 1})

    def test_no_interested_rows(self):
        report = mod.build_dry_run_report(
            "", {"directives": {"trinity-project": 5}}, {"directives": []}
        )
        self.assertEqual(report["total_interested_rows"], 0)
        self.assertEqual(report["distinct_branch_tags"], [])
        self.assertEqual(report["tables"]["directives"]["interested_by_bank"], {})


class CheckBackupTests(unittest.TestCase):
    def ok_pg_restore_list(self):
        return lambda: (0, "documents\nmemory_units\ndirectives\n")

    def test_missing_file(self):
        problems = mod.check_backup(None, {"max_write_at": "2026-01-01T00:00:00Z"}, "", False,
                                     self.ok_pg_restore_list())
        self.assertIn("non esiste", problems[0])

    def test_zero_size_file(self):
        problems = mod.check_backup(0, {"max_write_at": "2026-01-01T00:00:00Z"}, "", False,
                                     self.ok_pg_restore_list())
        self.assertIn("vuoto", problems[0])

    def test_missing_meta(self):
        problems = mod.check_backup(1024, None, "", False, self.ok_pg_restore_list())
        self.assertIn("meta.json", problems[0])

    def test_meta_without_max_write_at(self):
        problems = mod.check_backup(1024, {"host": "x"}, "", False, self.ok_pg_restore_list())
        self.assertIn("max_write_at", problems[0])

    def test_pg_restore_fails(self):
        problems = mod.check_backup(
            1024, {"max_write_at": "2026-01-01T00:00:00Z"}, "", False,
            lambda: (1, "errore boh"),
        )
        self.assertTrue(any("pg_restore" in p for p in problems))

    def test_pg_restore_output_missing_documents(self):
        problems = mod.check_backup(
            1024, {"max_write_at": "2026-01-01T00:00:00Z"}, "", False,
            lambda: (0, "memory_units\ndirectives\n"),
        )
        self.assertTrue(any("documents" in p for p in problems))

    def test_stale_backup_rejected(self):
        problems = mod.check_backup(
            1024, {"max_write_at": "2026-01-01T00:00:00Z"},
            "2026-01-02T00:00:00Z",  # DB piu' recente del backup
            False, self.ok_pg_restore_list(),
        )
        self.assertTrue(any("piu' recenti" in p for p in problems))

    def test_stale_backup_allowed_with_flag(self):
        problems = mod.check_backup(
            1024, {"max_write_at": "2026-01-01T00:00:00Z"},
            "2026-01-02T00:00:00Z",
            True, self.ok_pg_restore_list(),
        )
        self.assertEqual(problems, [])

    def test_all_ok(self):
        problems = mod.check_backup(
            1024, {"max_write_at": "2026-01-01T00:00:00Z"},
            "2026-01-01T00:00:00Z",  # backup allineato al DB
            False, self.ok_pg_restore_list(),
        )
        self.assertEqual(problems, [])


class VerifySnapshotTests(unittest.TestCase):
    def snapshot_row(self, table="documents", rid="d1", bank="trinity-project",
                      tags_before=None, fp="fp-1"):
        return {
            "table": table, "id": rid, "bank_id": bank,
            "tags_before": tags_before or ["a", "branch:master"],
            "fingerprint": fp,
        }

    def test_ok_when_tags_stripped_and_fingerprint_unchanged(self):
        snap = [self.snapshot_row()]
        current = {("documents", "d1"): {"tags": ["a"], "fingerprint": "fp-1"}}
        totals = {"documents": {"trinity-project": 5}}
        problems = mod.verify_snapshot(snap, current, totals, totals)
        self.assertEqual(problems, [])

    def test_altered_row_detected_via_fingerprint(self):
        snap = [self.snapshot_row()]
        # fingerprint diverso: qualcos'altro oltre ai tag e' cambiato
        current = {("documents", "d1"): {"tags": ["a"], "fingerprint": "fp-ALTERED"}}
        totals = {"documents": {"trinity-project": 5}}
        problems = mod.verify_snapshot(snap, current, totals, totals)
        self.assertEqual(len(problems), 1)
        self.assertIn("cambiata", problems[0])

    def test_missing_row_detected(self):
        snap = [self.snapshot_row()]
        totals = {"documents": {"trinity-project": 5}}
        problems = mod.verify_snapshot(snap, {}, totals, totals)
        self.assertEqual(len(problems), 1)
        self.assertIn("mancante", problems[0])

    def test_wrong_tags_detected(self):
        snap = [self.snapshot_row(tags_before=["a", "branch:master"])]
        # tags attuali NON sono lo strip corretto (branch:master ancora presente)
        current = {("documents", "d1"): {"tags": ["a", "branch:master"], "fingerprint": "fp-1"}}
        totals = {"documents": {"trinity-project": 5}}
        problems = mod.verify_snapshot(snap, current, totals, totals)
        self.assertEqual(len(problems), 1)
        self.assertIn("tags inattesi", problems[0])

    def test_totals_mismatch_detected(self):
        snap = [self.snapshot_row()]
        current = {("documents", "d1"): {"tags": ["a"], "fingerprint": "fp-1"}}
        problems = mod.verify_snapshot(
            snap, current,
            {"documents": {"trinity-project": 5}},
            {"documents": {"trinity-project": 4}},  # una riga sparita
        )
        self.assertTrue(any("conteggio righe cambiato" in p for p in problems))

    def test_new_bank_after_snapshot_detected(self):
        snap = [self.snapshot_row()]
        current = {("documents", "d1"): {"tags": ["a"], "fingerprint": "fp-1"}}
        problems = mod.verify_snapshot(
            snap, current,
            {"documents": {"trinity-project": 5}},
            {"documents": {"trinity-project": 5, "new-bank": 1}},
        )
        self.assertTrue(any("new-bank" in p for p in problems))


# --------------------------------------------------------------------------
# Adapter finto in-memory per testare l'orchestrazione dei comandi senza DB.
# --------------------------------------------------------------------------

class FakeAdapter:
    """Store condiviso: self.tables[table] = list di dict {id, bank_id, tags,
    created_at, ...altri campi...}. Il fingerprint e' calcolato su tutto
    tranne 'tags', come md5((to_jsonb(t) - 'tags')::text) nella query reale."""

    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables

    @staticmethod
    def _fingerprint(row: dict) -> str:
        payload = {k: v for k, v in row.items() if k != "tags"}
        return hashlib.md5(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def _interested(self, table):
        return [r for r in self.tables.get(table, [])
                if any(t.startswith("branch:") for t in r["tags"])]

    def fetch_watermark(self) -> str:
        return "2026-08-17T00:00:00Z"

    def fetch_totals(self, table):
        counts: dict[str, int] = {}
        for row in self.tables.get(table, []):
            counts[row["bank_id"]] = counts.get(row["bank_id"], 0) + 1
        return counts

    def fetch_totals_until(self, table, watermark):
        """Come fetch_totals ma solo created_at <= watermark (confronto
        stringa: nei test i timestamp sono gia' ISO ordinabili)."""
        if not watermark:
            return self.fetch_totals(table)
        counts: dict[str, int] = {}
        for row in self.tables.get(table, []):
            if row.get("created_at", "") <= watermark:
                counts[row["bank_id"]] = counts.get(row["bank_id"], 0) + 1
        return counts

    def fetch_interested_rows(self, table):
        return [{"id": r["id"], "bank_id": r["bank_id"], "tags": list(r["tags"])}
                for r in self._interested(table)]

    def fetch_interested_count(self, table):
        return len(self._interested(table))

    def snapshot_rows(self, table):
        return [{"id": r["id"], "bank_id": r["bank_id"], "tags_before": list(r["tags"]),
                  "fingerprint": self._fingerprint(r)}
                for r in self._interested(table)]

    def update_table(self, table):
        n = 0
        for row in self._interested(table):
            row["tags"] = mod.strip_branch_tags(row["tags"])
            n += 1
        return n

    def fetch_rows_by_ids(self, table, ids):
        idset = set(ids)
        return {r["id"]: {"bank_id": r["bank_id"], "tags": list(r["tags"]),
                          "fingerprint": self._fingerprint(r)}
                for r in self.tables.get(table, []) if r["id"] in idset}

    def revert_rows(self, table, rows):
        by_id = {r["id"]: r for r in self.tables.get(table, [])}
        restored = missing = 0
        for row in rows:
            target = by_id.get(row["id"])
            if target is not None and target["bank_id"] == row["bank_id"]:
                target["tags"] = list(row["tags_before"])
                restored += 1
            else:
                missing += 1
        return restored, missing


class RaisingUpdateAdapter(FakeAdapter):
    """Come FakeAdapter, ma update_table esplode: simula un crash a meta'
    apply per verificare che l'undo file sia gia' su disco PRIMA dell'update."""

    def update_table(self, table):
        raise RuntimeError("boom durante l'UPDATE")


# Stesso valore ritornato da FakeAdapter.fetch_watermark(): tutte le righe
# iniziali dello store sono PRIMA di questo istante (scritte prima
# dell'apply); i test sulle scritture concorrenti aggiungono righe con
# created_at DOPO, per verificare che fetch_totals_until le ignori.
WATERMARK = "2026-08-17T00:00:00Z"
BEFORE_WATERMARK = "2026-08-16T12:00:00Z"
AFTER_WATERMARK = "2026-08-18T00:00:00Z"


def make_store():
    """Store iniziale: 2 documents, 2 memory_units, 1 invalidated_memory_unit,
    con tag branch:* su alcuni, altri campi (es. 'text') da controllare intatti
    dopo la migrazione. created_at di tutte le righe iniziali < WATERMARK."""
    return {
        "documents": [
            {"id": "d1", "bank_id": "trinity-project",
             "tags": ["claude-code", "repo:Trinity", "branch:master"],
             "original_text": "testo documento 1", "created_at": BEFORE_WATERMARK},
            {"id": "d2", "bank_id": "trinity-project",
             "tags": ["claude-code"], "original_text": "testo documento 2",
             "created_at": BEFORE_WATERMARK},
        ],
        "memory_units": [
            {"id": "m1", "bank_id": "trinity-project",
             "tags": ["procedure", "branch:master"], "text": "fatto uno",
             "created_at": BEFORE_WATERMARK},
            {"id": "m2", "bank_id": "trinity-project",
             "tags": ["branch:feature-x"], "text": "fatto due",
             "created_at": BEFORE_WATERMARK},
        ],
        "invalidated_memory_units": [
            {"id": "i1", "bank_id": "trinity-project",
             "tags": ["branch:master"], "text": "fatto invalidato",
             "created_at": BEFORE_WATERMARK},
        ],
        "directives": [],
        "mental_models": [],
    }


class ApplyVerifyRevertTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.report_dir = os.path.join(self.tmp.name, "reports")

        # Backup + sidecar validi, allineati al watermark del FakeAdapter.
        self.backup_path = os.path.join(self.tmp.name, "hindsight-fake.dump")
        with open(self.backup_path, "wb") as f:
            f.write(b"not a real dump, only presence/size checked by the fake guard")
        with open(self.backup_path + ".meta.json", "w", encoding="utf-8") as f:
            json.dump({"host": "test", "dumped_at": "x",
                       "max_write_at": "2026-08-17T00:00:00Z",
                       "database": "hindsight"}, f)

        patches = [
            mock.patch.object(mod, "resolve_pgbin", return_value=None),
            mock.patch.object(mod, "run_pg_restore_list",
                              return_value=(0, "documents\nmemory_units\n")),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def patch_db(self, adapter):
        """Sostituisce open_conn/HsDbAdapter con una connessione finta no-op e
        l'adapter passato (stessa istanza per ogni fase, come richiesto per
        condividere lo store in-memory tra le connessioni 'aperte' dai vari
        comandi)."""
        fake_conn = SimpleNamespace(commit=lambda: None, rollback=lambda: None,
                                     close=lambda: None)
        patches = [
            mock.patch.object(mod, "open_conn", return_value=fake_conn),
            mock.patch.object(mod, "HsDbAdapter", side_effect=lambda conn: adapter),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def apply_args(self, **overrides):
        base = dict(apply=True, verify=False, revert=None, dry_run=False,
                    backup=self.backup_path, undo=None, report_dir=self.report_dir,
                    allow_stale_backup=False, yes=True)
        base.update(overrides)
        return SimpleNamespace(**base)

    def verify_args(self, **overrides):
        base = dict(apply=False, verify=True, revert=None, dry_run=False,
                    backup=None, undo=None, report_dir=self.report_dir,
                    allow_stale_backup=False, yes=True)
        base.update(overrides)
        return SimpleNamespace(**base)

    def revert_args(self, undo_path, **overrides):
        base = dict(apply=False, verify=False, revert=undo_path, dry_run=False,
                    backup=None, undo=None, report_dir=self.report_dir,
                    allow_stale_backup=False, yes=True)
        base.update(overrides)
        return SimpleNamespace(**base)

    def latest_report(self, kind):
        files = sorted(Path(self.report_dir).glob(f"strip-branch-tags-{kind}-*.json"))
        self.assertTrue(files, f"nessun report '{kind}' trovato in {self.report_dir}")
        with open(files[-1], encoding="utf-8") as f:
            return json.load(f), files[-1]

    def test_apply_updates_tags_and_preserves_other_columns(self):
        store = make_store()
        adapter = FakeAdapter(store)
        self.patch_db(adapter)

        rc = mod.cmd_apply(self.apply_args())
        self.assertEqual(rc, 0)

        # branch:* rimosso, altri tag preservati nell'ordine
        d1 = next(r for r in store["documents"] if r["id"] == "d1")
        self.assertEqual(d1["tags"], ["claude-code", "repo:Trinity"])
        self.assertEqual(d1["original_text"], "testo documento 1")  # colonna intatta

        d2 = next(r for r in store["documents"] if r["id"] == "d2")
        self.assertEqual(d2["tags"], ["claude-code"])  # nessun branch: nessun cambiamento

        m1 = next(r for r in store["memory_units"] if r["id"] == "m1")
        self.assertEqual(m1["tags"], ["procedure"])
        self.assertEqual(m1["text"], "fatto uno")

        i1 = next(r for r in store["invalidated_memory_units"] if r["id"] == "i1")
        self.assertEqual(i1["tags"], [])
        self.assertEqual(i1["text"], "fatto invalidato")

        undo, _ = self.latest_report("undo")
        self.assertEqual(len(undo["rows"]), 4)  # d1, m1, m2, i1 (d2 non ha branch:*)
        ids = {r["id"] for r in undo["rows"]}
        self.assertEqual(ids, {"d1", "m1", "m2", "i1"})

    def test_second_apply_is_noop_before_backup_guard(self):
        store = make_store()
        adapter = FakeAdapter(store)
        self.patch_db(adapter)
        self.assertEqual(mod.cmd_apply(self.apply_args()), 0)

        # Backup ORA non valido (rimosso): se la seconda apply guardasse il
        # backup prima del conteggio, fallirebbe con exit 2 invece che 0.
        os.remove(self.backup_path)
        rc = mod.cmd_apply(self.apply_args(backup=self.backup_path))
        self.assertEqual(rc, 0)

    def test_undo_file_written_before_update_even_if_update_crashes(self):
        store = make_store()
        adapter = RaisingUpdateAdapter(store)
        self.patch_db(adapter)

        with self.assertRaises(RuntimeError):
            mod.cmd_apply(self.apply_args())

        undo, _ = self.latest_report("undo")
        self.assertEqual(len(undo["rows"]), 4)
        # e i dati non sono stati toccati (l'update non e' mai arrivato al commit)
        d1 = next(r for r in store["documents"] if r["id"] == "d1")
        self.assertIn("branch:master", d1["tags"])

    def test_verify_ok_after_apply(self):
        store = make_store()
        adapter = FakeAdapter(store)
        self.patch_db(adapter)
        self.assertEqual(mod.cmd_apply(self.apply_args()), 0)
        undo, undo_path = self.latest_report("undo")

        rc = mod.cmd_verify(self.verify_args(undo=str(undo_path)))
        self.assertEqual(rc, 0)

    def test_verify_fails_if_row_altered_after_apply(self):
        store = make_store()
        adapter = FakeAdapter(store)
        self.patch_db(adapter)
        self.assertEqual(mod.cmd_apply(self.apply_args()), 0)
        _, undo_path = self.latest_report("undo")

        # Alterazione fuori banda di una colonna non-tags dopo l'apply.
        d1 = next(r for r in store["documents"] if r["id"] == "d1")
        d1["original_text"] = "TESTO CAMBIATO A MANO"

        rc = mod.cmd_verify(self.verify_args(undo=str(undo_path)))
        self.assertEqual(rc, 1)

    def test_verify_fails_if_row_missing_after_apply(self):
        store = make_store()
        adapter = FakeAdapter(store)
        self.patch_db(adapter)
        self.assertEqual(mod.cmd_apply(self.apply_args()), 0)
        _, undo_path = self.latest_report("undo")

        store["documents"] = [r for r in store["documents"] if r["id"] != "d1"]

        rc = mod.cmd_verify(self.verify_args(undo=str(undo_path)))
        self.assertEqual(rc, 1)

    def test_verify_without_undo_flags_remaining_branch_tags(self):
        store = make_store()  # nessun apply: i branch:* ci sono ancora
        adapter = FakeAdapter(store)
        self.patch_db(adapter)

        rc = mod.cmd_verify(self.verify_args())
        self.assertEqual(rc, 1)

    def test_verify_ignores_rows_and_bank_written_after_watermark(self):
        """Scritture 'concorrenti' arrivate DOPO watermark_before_apply (un
        retain di un'altra sessione sullo stesso bank, un bank nuovo creato
        da un benchmark) non devono far fallire la verify: fetch_totals_until
        le esclude dal confronto, altrimenti sarebbero falsi allarmi
        ('conteggio righe cambiato' / 'nuovo bank_id comparso')."""
        store = make_store()
        adapter = FakeAdapter(store)
        self.patch_db(adapter)
        self.assertEqual(mod.cmd_apply(self.apply_args()), 0)
        undo, undo_path = self.latest_report("undo")
        self.assertEqual(undo["watermark_before_apply"], WATERMARK)

        store["memory_units"].append({
            "id": "m3", "bank_id": "trinity-project", "tags": ["nuovo"],
            "text": "fatto arrivato dopo l'apply", "created_at": AFTER_WATERMARK,
        })
        store["documents"].append({
            "id": "d-new-bank", "bank_id": "benchmark-bank", "tags": [],
            "original_text": "documento di un bank nuovo",
            "created_at": AFTER_WATERMARK,
        })

        rc = mod.cmd_verify(self.verify_args(undo=str(undo_path)))
        self.assertEqual(rc, 0)

    def test_verify_detects_old_row_deleted_after_apply_via_totals(self):
        """d2 non ha mai avuto branch:* (non e' nello snapshot riga-per-riga)
        ma esisteva PRIMA del watermark: la sua cancellazione deve comunque
        far fallire la verify tramite il conteggio totale per bank, che e'
        l'unica rete di sicurezza per righe fuori dallo snapshot."""
        store = make_store()
        adapter = FakeAdapter(store)
        self.patch_db(adapter)
        self.assertEqual(mod.cmd_apply(self.apply_args()), 0)
        _, undo_path = self.latest_report("undo")

        store["documents"] = [r for r in store["documents"] if r["id"] != "d2"]

        rc = mod.cmd_verify(self.verify_args(undo=str(undo_path)))
        self.assertEqual(rc, 1)

    def test_revert_restores_tags_before_and_verify_detects_branch_again(self):
        store = make_store()
        original = copy.deepcopy(store)
        adapter = FakeAdapter(store)
        self.patch_db(adapter)
        self.assertEqual(mod.cmd_apply(self.apply_args()), 0)
        _, undo_path = self.latest_report("undo")

        rc = mod.cmd_revert(self.revert_args(str(undo_path)))
        self.assertEqual(rc, 0)

        d1 = next(r for r in store["documents"] if r["id"] == "d1")
        orig_d1 = next(r for r in original["documents"] if r["id"] == "d1")
        self.assertEqual(d1["tags"], orig_d1["tags"])
        m1 = next(r for r in store["memory_units"] if r["id"] == "m1")
        orig_m1 = next(r for r in original["memory_units"] if r["id"] == "m1")
        self.assertEqual(m1["tags"], orig_m1["tags"])

        # verify senza undo ritrova i branch:* (tornati presenti col revert)
        rc = mod.cmd_verify(self.verify_args())
        self.assertEqual(rc, 1)

    def test_revert_reports_missing_rows(self):
        store = make_store()
        adapter = FakeAdapter(store)
        self.patch_db(adapter)
        self.assertEqual(mod.cmd_apply(self.apply_args()), 0)
        _, undo_path = self.latest_report("undo")

        # Una delle righe migrate viene cancellata prima del revert.
        store["memory_units"] = [r for r in store["memory_units"] if r["id"] != "m1"]

        with mock.patch("builtins.print") as fake_print:
            rc = mod.cmd_revert(self.revert_args(str(undo_path)))
        self.assertEqual(rc, 0)
        messages = " ".join(str(c) for c in fake_print.call_args_list)
        self.assertIn("mancanti", messages)


class ConfirmTests(unittest.TestCase):
    def test_non_tty_stdin_always_refuses(self):
        with mock.patch("sys.stdin.isatty", return_value=False):
            self.assertFalse(mod.confirm("continuo? [y/N] "))

    def test_tty_stdin_accepts_y(self):
        with mock.patch("sys.stdin.isatty", return_value=True), \
             mock.patch("builtins.input", return_value="y"):
            self.assertTrue(mod.confirm("continuo? [y/N] "))

    def test_tty_stdin_rejects_other_input(self):
        with mock.patch("sys.stdin.isatty", return_value=True), \
             mock.patch("builtins.input", return_value="nope"):
            self.assertFalse(mod.confirm("continuo? [y/N] "))


class ParseArgsTests(unittest.TestCase):
    def test_defaults_to_dry_run(self):
        args = mod.parse_args([])
        self.assertTrue(args.dry_run)

    def test_apply_requires_backup(self):
        with self.assertRaises(SystemExit):
            mod.parse_args(["--apply"])

    def test_backup_without_apply_rejected(self):
        with self.assertRaises(SystemExit):
            mod.parse_args(["--backup", "x.dump"])

    def test_undo_without_verify_rejected(self):
        with self.assertRaises(SystemExit):
            mod.parse_args(["--undo", "x.json"])

    def test_apply_and_verify_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            mod.parse_args(["--apply", "--backup", "x.dump", "--verify"])


if __name__ == "__main__":
    unittest.main()
