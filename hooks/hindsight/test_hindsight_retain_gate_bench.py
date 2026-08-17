#!/usr/bin/env python
"""Test delle metriche duplicate exact/semantic del benchmark retain gate."""

from __future__ import annotations

import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
BENCH_PATH = HERE / "benchmark" / "hindsight_retain_gate_bench.py"


def load_bench():
    spec = importlib.util.spec_from_file_location("retain_gate_bench_test", BENCH_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"impossibile caricare {BENCH_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResult:
    def __init__(
        self,
        action: str,
        reason: str,
        duplicate_of: list[int],
        candidates: list[dict] | None = None,
        covered_by: list[int] | None = None,
        durable_claims: list[str] | None = None,
    ):
        self.action = action
        self.reason = reason
        self.duplicate_of = duplicate_of
        self.candidates = candidates or []
        # ICH-84: di default rispecchia duplicate_of (coerente col contratto
        # derivato del gate reale, dove duplicate_of = covered_by su skip).
        self.covered_by = duplicate_of if covered_by is None else covered_by
        self.durable_claims = durable_claims or []
        self.preview = ""
        self.context = ""
        self.latency_ms = 1.0
        self.error = None


class Args:
    model = ""
    with_dedup = True
    workers = 1
    dry_run_extract = 0
    bench_bank = "unused"
    dedup_bank_url = ""


class RetainGateBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.bench = load_bench()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        results = Path(self.tmp.name) / "results.jsonl"
        self.results_patch = mock.patch.object(self.bench, "RESULTS_FILE", results)
        self.results_patch.start()
        self.addCleanup(self.results_patch.stop)
        self.config_patch = mock.patch.object(
            self.bench, "load_config", return_value={"retain_gate_model": "test"}
        )
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.banks_patch = mock.patch.object(
            self.bench, "recall_bank_urls", return_value=["http://bank"]
        )
        self.banks_patch.start()
        self.addCleanup(self.banks_patch.stop)

    def run_evaluate(self, labels, results, *, with_dedup=True, dedup_bank_url="", seen_bank_urls=None):
        windows = [
            {"id": label["id"], "content": label["id"], "turns": []}
            for label in labels
        ]

        def read_jsonl(path):
            return windows if path == self.bench.WINDOWS_FILE else labels

        def evaluate_retain(content, summary, bank_urls, cfg):
            if seen_bank_urls is not None:
                seen_bank_urls.append(bank_urls)
            return results[content]

        args = Args()
        args.with_dedup = with_dedup
        args.dedup_bank_url = dedup_bank_url
        output = io.StringIO()
        with mock.patch.object(self.bench, "read_jsonl", side_effect=read_jsonl), mock.patch.object(
            self.bench, "evaluate_retain", side_effect=evaluate_retain
        ), redirect_stdout(output):
            rc = self.bench.evaluate(args)
        return rc, output.getvalue()

    @staticmethod
    def labels():
        return [
            {
                "id": "exact",
                "expected_action": "skip",
                "duplicate_of": ["memory-exact"],
                "duplicate_kind": "exact",
            },
            {
                "id": "semantic",
                "expected_action": "skip",
                "duplicate_of": ["memory-semantic"],
                "duplicate_kind": "semantic",
            },
        ]

    def test_targets_pass_only_for_coherent_duplicate_results(self):
        results = {
            "exact": FakeResult("skip", "duplicate", [0], [{"id": "memory-exact"}]),
            "semantic": FakeResult("skip", "duplicate", [0], [{"id": "memory-semantic"}]),
        }
        rc, output = self.run_evaluate(self.labels(), results)
        self.assertEqual(rc, 0)
        self.assertIn("target >=80% PASS", output)
        self.assertIn("target >=84% PASS", output)

    def test_incoherent_duplicate_result_fails_target(self):
        results = {
            "exact": FakeResult("skip", "duplicate", [0], [{"id": "memory-exact"}]),
            "semantic": FakeResult("retain", "duplicate", [0]),
        }
        rc, output = self.run_evaluate(self.labels(), results)
        self.assertEqual(rc, 1)
        self.assertIn("target >=84% FAIL", output)

    def test_wrong_duplicate_identity_fails_target(self):
        results = {
            "exact": FakeResult("skip", "duplicate", [0], [{"id": "memory-exact"}]),
            "semantic": FakeResult("skip", "duplicate", [0], [{"id": "other-memory"}]),
        }
        rc, output = self.run_evaluate(self.labels(), results)
        self.assertEqual(rc, 1)
        self.assertIn("target >=84% FAIL", output)

    def test_rejects_missing_kind_or_category(self):
        bad_labels = [dict(self.labels()[0], duplicate_kind="other")]
        rc, output = self.run_evaluate(bad_labels, {})
        self.assertEqual(rc, 1)
        self.assertIn("duplicate_kind mancante/non valido", output)

        only_exact = [self.labels()[0]]
        rc, output = self.run_evaluate(only_exact, {})
        self.assertEqual(rc, 1)
        self.assertIn("categorie mancanti: semantic", output)

    def test_dataset_without_duplicates_keeps_exit_zero(self):
        labels = [
            {"id": "keep", "expected_action": "retain"},
            {"id": "drop", "expected_action": "skip"},
        ]
        results = {
            "keep": FakeResult("retain", "durable", []),
            "drop": FakeResult("skip", "ephemeral", []),
        }
        rc, output = self.run_evaluate(labels, results, with_dedup=False)
        self.assertEqual(rc, 0)
        self.assertIn("n/a", output)
        self.assertNotIn("target >=80% FAIL", output)

    def test_duplicate_labels_require_dedup(self):
        rc, output = self.run_evaluate(self.labels(), {}, with_dedup=False)
        self.assertEqual(rc, 1)
        self.assertIn("richiedono --with-dedup", output)

    def test_dedup_bank_url_replaces_real_banks(self):
        results = {
            "exact": FakeResult("skip", "duplicate", [0], [{"id": "memory-exact"}]),
            "semantic": FakeResult("skip", "duplicate", [0], [{"id": "memory-semantic"}]),
        }
        seen: list[list[str]] = []
        rc, _output = self.run_evaluate(
            self.labels(),
            results,
            dedup_bank_url="http://bench-bank",
            seen_bank_urls=seen,
        )
        self.assertEqual(rc, 0)
        self.assertTrue(all(urls == ["http://bench-bank"] for urls in seen))
        self.bench.recall_bank_urls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
