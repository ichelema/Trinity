#!/usr/bin/env python
"""Test del benchmark A/B/D del tag opzionale del gate pre-retain (ICH-85).

Copre SOLO le parti senza rete/DB: costruzione degli item A/B/D, le metriche
di frammentazione/dup-rate calcolate da righe finte, la ripresa degli
artefatti (assignments gia' presenti vengono saltati) e la tabella di report.
Le fasi che parlano con la rete o col DB (export/retain/wait/consolidate/
measure) non sono esercitate qui: lo script vero va lanciato a mano (vedi
benchmark/hindsight_gate_tag_bench.py, --dry-run per uno smoke test sicuro)."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
BENCH_PATH = HERE / "benchmark" / "hindsight_gate_tag_bench.py"


def load_bench():
    spec = importlib.util.spec_from_file_location("gate_tag_bench_test", BENCH_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"impossibile caricare {BENCH_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_gate_row(tag="", action="retain", reason="durable_decision", context="", latency_ms=1.0, error=None):
    """Stessa forma del dict restituito da ask_gate_tag."""
    return {"tag": tag, "action": action, "reason": reason, "context": context,
            "latency_ms": latency_ms, "error": error}


class GateTagVocabularyTests(unittest.TestCase):
    """Vocabolario CHIUSO del tag: schema/prompt estesi sopra quelli di
    produzione, validazione che rifiuta il free-form, merge senza duplicati,
    ask_gate_tag con API finta (una sola chiamata, stesso nome schema)."""

    def setUp(self):
        self.bench = load_bench()
        self.vocab = ["topic:data", "topic:config"]

    def test_vocabulary_is_closed_and_low_cardinality(self):
        vocab = self.bench.GATE_TAG_VOCABULARY
        self.assertEqual(len(vocab), 8)
        self.assertEqual(len(set(vocab)), 8)
        self.assertTrue(all(v.startswith("topic:") for v in vocab))
        self.assertNotIn("topic:other", vocab)
        for v in vocab:
            self.assertIn(v, self.bench.GATE_TAG_DESCRIPTIONS)

    def test_schema_extends_production_schema_with_tag_enum(self):
        schema = self.bench.gate_tag_schema(self.vocab)
        prod = self.bench.GATE_SCHEMA
        self.assertEqual(schema["properties"]["tag"]["enum"], sorted(self.vocab))
        self.assertIn("tag", schema["required"])
        self.assertIs(schema["additionalProperties"], False)
        # lo schema di produzione resta intatto (nessun campo tag)
        self.assertNotIn("tag", prod["properties"])
        self.assertNotIn("tag", prod["required"])

    def test_prompt_extends_production_prompt(self):
        prompt = self.bench.gate_tag_prompt(self.vocab)
        self.assertTrue(prompt.startswith(self.bench.GATE_PROMPT))
        for value in self.vocab:
            self.assertIn(value, prompt, value)
            self.assertIn(self.bench.GATE_TAG_DESCRIPTIONS[value], prompt, value)
        self.assertNotIn("8. tag", self.bench.GATE_PROMPT)

    def test_validate_gate_tag_rejects_free_form(self):
        self.assertEqual(self.bench.validate_gate_tag("topic:data", self.vocab), "topic:data")
        for bad in ("debugging", "topic:foo", "", None, 3, ["topic:config"]):
            self.assertEqual(self.bench.validate_gate_tag(bad, self.vocab), "", bad)

    def test_merge_gate_tags(self):
        merge = self.bench.merge_gate_tags
        self.assertEqual(merge(["claude-code", "repo:T"], "topic:data"),
                         ["claude-code", "repo:T", "topic:data"])
        self.assertEqual(merge(["claude-code", "topic:data"], "topic:data"),
                         ["claude-code", "topic:data"])
        self.assertEqual(merge(["claude-code"], ""), ["claude-code"])
        self.assertEqual(merge(["a", "b", "a"], "c"), ["a", "b", "c"])

    def test_ask_gate_tag_single_call_and_out_of_enum_discarded(self):
        captured = []

        def fake_api(model, system, user, schema_name, schema, timeout):
            captured.append((model, schema_name, schema))
            return {"action": "retain", "reason": "durable_decision", "preview": "x",
                    "duplicate_of": [], "context": "dominio",
                    "tag": fake_api.tag}, 12.5

        cfg = {"retain_gate_model": "m", "retain_gate_timeout": 5}
        with mock.patch.object(self.bench, "api_json", side_effect=fake_api):
            fake_api.tag = "topic:data"
            row = self.bench.ask_gate_tag("finestra", cfg, self.vocab)
            self.assertEqual(row["tag"], "topic:data")
            self.assertEqual(row["action"], "retain")
            self.assertIsNone(row["error"])
            fake_api.tag = "topic:nonexistent"
            row = self.bench.ask_gate_tag("finestra", cfg, self.vocab)
            self.assertEqual(row["tag"], "")
            self.assertEqual(row["action"], "retain")
            self.assertIsNone(row["error"])
        self.assertEqual(len(captured), 2)
        self.assertEqual(captured[0][0], "m")
        self.assertEqual(captured[0][1], "retain_gate_decision")
        self.assertIn("tag", captured[0][2]["properties"])

    def test_ask_gate_tag_error_gives_untagged_row(self):
        def boom(*a, **kw):
            raise TimeoutError("timeout")

        with mock.patch.object(self.bench, "api_json", side_effect=boom):
            row = self.bench.ask_gate_tag("finestra", {}, self.vocab)
        self.assertEqual(row["tag"], "")
        self.assertIn("TimeoutError", row["error"])


class BuildVariantItemsTests(unittest.TestCase):
    """Costruzione degli item A/B/D: tags, observation_scopes, document_id
    preservato, nessun branch:, topic vuoto -> D si comporta come A."""

    def setUp(self):
        self.bench = load_bench()
        self.doc = {
            "document_id": "doc-123",
            "content": "contenuto della finestra",
            "context": "contesto tecnico",
            "timestamp": "2026-08-01T00:00:00Z",
            "metadata": {"cwd": "/home/x", "session_id": "s1"},
        }

    def test_variant_a_has_only_claude_code_and_repo_tags(self):
        items = self.bench.build_variant_items(self.doc, "")
        self.assertEqual(items["a"]["tags"], ["claude-code", "repo:Trinity"])
        self.assertNotIn("observation_scopes", items["a"])
        for tag in items["a"]["tags"]:
            self.assertFalse(tag.startswith("branch:"))

    def test_document_id_and_content_preserved_across_variants(self):
        items = self.bench.build_variant_items(self.doc, "topic:debugging")
        for variant in ("a", "b", "d"):
            self.assertEqual(items[variant]["document_id"], "doc-123")
            self.assertEqual(items[variant]["content"], "contenuto della finestra")
            self.assertEqual(items[variant]["context"], "contesto tecnico")
            self.assertEqual(items[variant]["timestamp"], "2026-08-01T00:00:00Z")

    def test_repo_from_metadata_overrides_fallback(self):
        doc = dict(self.doc, metadata={"repo": "OtherRepo"})
        items = self.bench.build_variant_items(doc, "")
        self.assertIn("repo:OtherRepo", items["a"]["tags"])

    def test_variant_b_appends_tag_when_present(self):
        items = self.bench.build_variant_items(self.doc, "topic:debugging")
        self.assertEqual(items["b"]["tags"], ["claude-code", "repo:Trinity", "topic:debugging"])
        self.assertNotIn("observation_scopes", items["b"])

    def test_variant_d_has_explicit_observation_scopes_when_tag_present(self):
        items = self.bench.build_variant_items(self.doc, "topic:debugging")
        self.assertEqual(items["d"]["tags"], ["claude-code", "repo:Trinity", "topic:debugging"])
        self.assertEqual(
            items["d"]["observation_scopes"],
            [["claude-code", "repo:Trinity"], ["claude-code", "repo:Trinity", "topic:debugging"]],
        )

    def test_empty_topic_makes_b_and_d_identical_to_a(self):
        items = self.bench.build_variant_items(self.doc, "")
        self.assertEqual(items["a"]["tags"], items["b"]["tags"])
        self.assertEqual(items["a"]["tags"], items["d"]["tags"])
        self.assertNotIn("observation_scopes", items["b"])
        self.assertNotIn("observation_scopes", items["d"])

    def test_variants_do_not_share_mutable_tag_lists(self):
        # Mutare i tag di una variante non deve toccare le altre (no alias).
        items = self.bench.build_variant_items(self.doc, "topic:data")
        items["a"]["tags"].append("mutated")
        self.assertNotIn("mutated", items["b"]["tags"])
        self.assertNotIn("mutated", items["d"]["tags"])


class PartitionMetricsTests(unittest.TestCase):
    """Metriche di frammentazione (partitions/singleton/proof) da righe finte."""

    def setUp(self):
        self.bench = load_bench()

    def test_partition_key_normalizes_order_and_dedup(self):
        self.assertEqual(
            self.bench.partition_key(["b", "a", "a"]),
            self.bench.partition_key(["a", "b"]),
        )

    def test_compute_fact_metrics_counts_partitions_and_singletons(self):
        rows = [
            {"tags": ["claude-code", "repo:Trinity"]},
            {"tags": ["claude-code", "repo:Trinity"]},
            {"tags": ["claude-code", "repo:Trinity", "topic:data"]},
            {"tags": ["claude-code", "repo:Trinity", "topic:debugging"]},
        ]
        m = self.bench.compute_fact_metrics(rows)
        self.assertEqual(m["n_facts"], 4)
        self.assertEqual(m["partitions"], 3)  # {claude-code+repo}, {+topic:data}, {+topic:debugging}
        self.assertEqual(m["singleton_partitions"], 2)
        self.assertAlmostEqual(m["docs_per_partition_avg"], 4 / 3, places=3)

    def test_compute_fact_metrics_empty_input(self):
        m = self.bench.compute_fact_metrics([])
        self.assertEqual(m["n_facts"], 0)
        self.assertEqual(m["partitions"], 0)
        self.assertEqual(m["singleton_partitions"], 0)
        self.assertEqual(m["docs_per_partition_avg"], 0.0)

    def test_compute_proof_stats(self):
        stats = self.bench.compute_proof_stats([1, 1, 3, 5])
        self.assertEqual(stats["avg"], 2.5)
        self.assertEqual(stats["max"], 5)
        self.assertIn(stats["p50"], (1.0, 3.0))  # percentile discreta, dipende dall'arrotondamento

    def test_compute_proof_stats_empty(self):
        stats = self.bench.compute_proof_stats([])
        self.assertEqual(stats, {"avg": 0.0, "max": 0, "p50": 0.0})

    def test_compute_topic_distribution_counts_only_topic_tags(self):
        rows = [
            ["claude-code", "repo:Trinity", "topic:data"],
            ["claude-code", "repo:Trinity", "topic:data"],
            ["claude-code", "repo:Trinity", "topic:debugging"],
            ["claude-code", "repo:Trinity"],
        ]
        dist = self.bench.compute_topic_distribution(rows)
        self.assertEqual(dist, {"topic:data": 2, "topic:debugging": 1})

    def test_compute_observation_scope_split(self):
        rows = [
            ["claude-code", "repo:Trinity"],
            ["claude-code", "repo:Trinity", "topic:data"],
            ["claude-code", "repo:Trinity", "topic:evaluation"],
        ]
        split = self.bench.compute_observation_scope_split(rows)
        self.assertEqual(split, {"with_topic": 2, "without_topic": 1})

    def test_compute_observation_scope_split_empty(self):
        self.assertEqual(
            self.bench.compute_observation_scope_split([]),
            {"with_topic": 0, "without_topic": 0},
        )


class DupRateTopkTests(unittest.TestCase):
    def setUp(self):
        self.bench = load_bench()

    def test_detects_near_duplicate_pair(self):
        topk = [
            ["il gate produce un tag topic:* opzionale", "il gate produce un tag topic:*  opzionale!!"],
        ]
        self.assertEqual(self.bench.dup_rate_topk(topk), 1.0)

    def test_no_duplicates_below_threshold(self):
        topk = [["testo completamente diverso A", "altro testo B senza alcuna somiglianza rilevante"]]
        self.assertEqual(self.bench.dup_rate_topk(topk), 0.0)

    def test_mixed_queries_average_correctly(self):
        topk = [
            ["stesso identico testo", "stesso identico testo"],
            ["testo unico uno", "testo differente due"],
        ]
        self.assertEqual(self.bench.dup_rate_topk(topk), 0.5)

    def test_empty_input(self):
        self.assertEqual(self.bench.dup_rate_topk([]), 0.0)

    def test_single_result_never_duplicate(self):
        self.assertEqual(self.bench.dup_rate_topk([["solo un risultato"]]), 0.0)


class ResumeArtifactsTests(unittest.TestCase):
    """Ripresa degli artefatti: gli assignment gia' presenti vengono saltati."""

    def setUp(self):
        self.bench = load_bench()

    def test_pending_docs_for_tagging_skips_existing_ids(self):
        docs = [{"document_id": "a"}, {"document_id": "b"}, {"document_id": "c"}]
        pending = self.bench.pending_docs_for_tagging(docs, {"a", "c"})
        self.assertEqual([d["document_id"] for d in pending], ["b"])

    def test_pending_docs_for_tagging_all_new(self):
        docs = [{"document_id": "a"}, {"document_id": "b"}]
        pending = self.bench.pending_docs_for_tagging(docs, set())
        self.assertEqual(len(pending), 2)

    def test_pending_items_for_variant_skips_sent_ids(self):
        items = [{"document_id": "x"}, {"document_id": "y"}, {"document_id": "z"}]
        pending = self.bench.pending_items_for_variant(items, {"y"})
        self.assertEqual([it["document_id"] for it in pending], ["x", "z"])

    def test_batch_items_splits_into_chunks(self):
        items = [{"document_id": str(i)} for i in range(45)]
        batches = self.bench.batch_items(items, 20)
        self.assertEqual([len(b) for b in batches], [20, 20, 5])

    def test_batch_items_empty(self):
        self.assertEqual(self.bench.batch_items([], 20), [])

    def test_tag_phase_resumes_and_skips_already_tagged_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs_file = Path(tmp) / "docs.jsonl"
            assign_file = Path(tmp) / "assignments.jsonl"
            artifacts = Path(tmp)
            docs = [
                {"document_id": "d1", "content": "uno"},
                {"document_id": "d2", "content": "due"},
            ]
            with docs_file.open("w", encoding="utf-8") as f:
                for d in docs:
                    f.write(json.dumps(d) + "\n")
            # d1 e' gia' stato etichettato in un run precedente.
            with assign_file.open("w", encoding="utf-8") as f:
                f.write(json.dumps({"document_id": "d1", "tag": "topic:data", "action": "retain",
                                     "reason": "durable_decision", "context": "", "latency_ms": 1.0,
                                     "error": None}) + "\n")

            calls = []

            def fake_ask_gate_tag(content, cfg, vocabulary=None):
                calls.append(content)
                return fake_gate_row(tag="topic:debugging", action="retain")

            with mock.patch.object(self.bench, "DOCS_FILE", docs_file), mock.patch.object(
                self.bench, "ASSIGN_FILE", assign_file
            ), mock.patch.object(self.bench, "ARTIFACTS", artifacts), mock.patch.object(
                self.bench, "ask_gate_tag", side_effect=fake_ask_gate_tag
            ):
                rc = self.bench.tag_phase({"retain_gate_model": "test"}, workers=1)

            self.assertEqual(rc, 0)
            # Solo d2 (content "due") e' stato rivalutato: d1 era gia' in assignments.
            self.assertEqual(calls, ["due"])
            rows = self.bench.read_jsonl(assign_file)
            ids = {r["document_id"] for r in rows}
            self.assertEqual(ids, {"d1", "d2"})

    def test_tag_phase_noop_when_all_docs_already_tagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs_file = Path(tmp) / "docs.jsonl"
            assign_file = Path(tmp) / "assignments.jsonl"
            with docs_file.open("w", encoding="utf-8") as f:
                f.write(json.dumps({"document_id": "d1", "content": "uno"}) + "\n")
            with assign_file.open("w", encoding="utf-8") as f:
                f.write(json.dumps({"document_id": "d1", "tag": "", "action": "skip",
                                     "reason": "trivial_or_ephemeral", "context": "", "latency_ms": 1.0,
                                     "error": None}) + "\n")

            def boom(*a, **kw):
                raise AssertionError("ask_gate_tag non doveva essere chiamato")

            with mock.patch.object(self.bench, "DOCS_FILE", docs_file), mock.patch.object(
                self.bench, "ASSIGN_FILE", assign_file
            ), mock.patch.object(self.bench, "ask_gate_tag", side_effect=boom):
                rc = self.bench.tag_phase({}, workers=1)
            self.assertEqual(rc, 0)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.bench = load_bench()

    def _metrics(self):
        base = {
            "n_documents": 10, "n_facts": 20, "n_observations": 5,
            "observations_per_fact": 0.25, "partitions": 4, "singleton_partitions": 1,
            "docs_per_partition_avg": 5.0, "MRR": 0.5, "R@1": 0.4, "R@3": 0.6,
            "dup_rate_topk": 0.1,
            "proof_count": {"avg": 2.0, "max": 4, "p50": 2.0},
            "observation_scope_split": {"with_topic": 2, "without_topic": 3},
        }
        return {"a": dict(base), "b": dict(base, partitions=6), "d": dict(base, partitions=8)}

    def test_report_contains_header_and_all_variant_columns(self):
        meta = {
            "n_documents": 10, "n_tagged": 7, "n_untagged": 3, "n_errors": 1,
            "gate_model": "gpt-5.6-luna", "topic_distribution": {"topic:data": 4, "topic:debugging": 3},
        }
        text = self.bench.build_report(self._metrics(), meta)
        self.assertIn("N documenti: 10", text)
        self.assertIn("N taggati: 7", text)
        self.assertIn("gpt-5.6-luna", text)
        self.assertIn("topic:data: 4", text)
        self.assertIn("| Metrica | A | B | D |", text)
        self.assertIn("Nessuna decisione automatica", text)

    def test_report_without_topic_distribution(self):
        meta = {"n_documents": 0, "n_tagged": 0, "n_untagged": 0, "n_errors": 0, "gate_model": "", "topic_distribution": {}}
        text = self.bench.build_report(self._metrics(), meta)
        self.assertIn("(nessuna)", text)

    def test_report_phase_writes_file_and_reads_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp)
            metrics_file = artifacts / "metrics.json"
            report_file = artifacts / "report.md"
            docs_file = artifacts / "docs.jsonl"
            assign_file = artifacts / "assignments.jsonl"
            metrics_file.write_text(json.dumps(self._metrics()), encoding="utf-8")
            docs_file.write_text(json.dumps({"document_id": "d1"}) + "\n", encoding="utf-8")
            assign_file.write_text(
                json.dumps({"document_id": "d1", "tag": "topic:data", "error": None}) + "\n", encoding="utf-8"
            )
            with mock.patch.object(self.bench, "METRICS_FILE", metrics_file), mock.patch.object(
                self.bench, "REPORT_FILE", report_file
            ), mock.patch.object(self.bench, "DOCS_FILE", docs_file), mock.patch.object(
                self.bench, "ASSIGN_FILE", assign_file
            ), mock.patch.object(self.bench, "ARTIFACTS", artifacts):
                rc = self.bench.report_phase({"retain_gate_model": "test-model"})
            self.assertEqual(rc, 0)
            self.assertTrue(report_file.exists())
            self.assertIn("test-model", report_file.read_text(encoding="utf-8"))

    def test_report_phase_fails_without_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            metrics_file = Path(tmp) / "missing.json"
            with mock.patch.object(self.bench, "METRICS_FILE", metrics_file):
                rc = self.bench.report_phase({})
            self.assertEqual(rc, 1)


class MiscHelpersTests(unittest.TestCase):
    def setUp(self):
        self.bench = load_bench()

    def test_default_source_bank_from_api_url(self):
        cfg = {"api_url": "http://127.0.0.1:8888/v1/default/banks/trinity-project"}
        self.assertEqual(self.bench.default_source_bank(cfg), "trinity-project")

    def test_default_source_bank_falls_back_when_empty(self):
        self.assertEqual(self.bench.default_source_bank({"api_url": ""}), "trinity-project")

    def test_repo_from_metadata_missing_key(self):
        self.assertEqual(self.bench.repo_from_metadata({}, "Trinity"), "Trinity")
        self.assertEqual(self.bench.repo_from_metadata(None, "Trinity"), "Trinity")
        self.assertEqual(self.bench.repo_from_metadata({"repo": "  "}, "Trinity"), "Trinity")
        self.assertEqual(self.bench.repo_from_metadata({"repo": "Foo"}, "Trinity"), "Foo")


if __name__ == "__main__":
    unittest.main()
