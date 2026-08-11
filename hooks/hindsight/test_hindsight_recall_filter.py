#!/usr/bin/env python

from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
import unittest
from unittest import mock

from lib import hindsight_config
from lib.hindsight_recall_filter import (
    CLASSIFIER_SCHEMA,
    consent_decision,
    consume_pending,
    discard_pending,
    discard_pending_if_present,
    load_pending,
    read_with_deadline,
    result_score,
    route_results,
    save_pending,
)


class ConfigTests(unittest.TestCase):
    def test_non_object_and_invalid_numeric_overrides_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            cfg = dict(hindsight_config.DEFAULTS)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump([], handle)
            self.assertEqual(hindsight_config._merge_json(cfg, path), set())

            with open(path, "w", encoding="utf-8") as handle:
                json.dump({
                    "recall_pending_ttl": [],
                    "recall_result_filter_threshold": {},
                    "recall_result_filter_timeout": "bad",
                }, handle)
            hindsight_config._merge_json(cfg, path)
            self.assertEqual(cfg["recall_pending_ttl"], hindsight_config.DEFAULTS["recall_pending_ttl"])
            self.assertEqual(
                cfg["recall_result_filter_threshold"],
                hindsight_config.DEFAULTS["recall_result_filter_threshold"],
            )
            self.assertEqual(
                cfg["recall_result_filter_timeout"],
                hindsight_config.DEFAULTS["recall_result_filter_timeout"],
            )


class DeadlineTests(unittest.TestCase):
    def test_read_deadline_stops_slow_stream(self):
        class SlowResponse:
            fp = None

            def read(self, _size):
                return b"x"

        with mock.patch("lib.hindsight_recall_filter.time.monotonic", side_effect=[1.0, 2.0]):
            with self.assertRaises(TimeoutError):
                read_with_deadline(SlowResponse(), 1.5)


class RoutingTests(unittest.TestCase):
    def test_threshold_is_inclusive_and_score_is_strictly_numeric(self):
        self.assertEqual(result_score({"scores": {"reranker": 0.8}}), 0.8)
        self.assertIsNone(result_score({"scores": {"reranker": "0.9"}}))
        self.assertIsNone(result_score({"scores": {}}))
        self.assertIsNone(result_score({"scores": "degraded"}))
        self.assertIsNone(result_score({"scores": 1}))
        self.assertIsNone(result_score({"scores": {"reranker": float("nan")}}))
        self.assertIsNone(result_score({"scores": {"reranker": float("inf")}}))
        self.assertEqual(
            result_score({"_rerank_score": 0.61, "scores": {"reranker": 0.95}}),
            0.95,
        )

        calls = []

        def api(*args):
            calls.append(args)
            return {
                "classifications": [
                    {"index": 1, "confidence": "low", "reason": "irrelevant"},
                    {"index": 2, "confidence": "medium", "reason": "plausible_but_uncertain"},
                ]
            }, 12.0

        results = [
            {"text": "bypass", "scores": {"reranker": 0.8}},
            {"text": "missing"},
            {"text": "textual", "scores": {"reranker": "0.9"}},
        ]
        routed = route_results("prompt", results, "model", 0.8, 3, api)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][4], CLASSIFIER_SCHEMA)
        self.assertEqual([r["text"] for r in routed["automatic"]], ["bypass"])
        self.assertEqual([r["text"] for r in routed["optional"]], ["textual"])
        self.assertEqual([r["text"] for r in routed["discarded"]], ["missing"])

    def test_routes_high_medium_low_in_one_call(self):
        def api(*_args):
            return {
                "classifications": [
                    {"index": 0, "confidence": "high", "reason": "directly_actionable"},
                    {"index": 1, "confidence": "medium", "reason": "plausible_but_uncertain"},
                    {"index": 2, "confidence": "low", "reason": "tangential"},
                ]
            }, 5.5

        routed = route_results(
            "prompt", [{"text": "h"}, {"text": "m"}, {"text": "l"}], "model", 0.8, 3, api
        )
        self.assertEqual(routed["automatic"][0]["route"], "classifier_high")
        self.assertEqual(routed["optional"][0]["route"], "classifier_medium")
        self.assertEqual(routed["discarded"][0]["route"], "classifier_low")
        self.assertEqual(routed["latency_ms"], 5.5)

    def test_classifier_errors_fail_open(self):
        failures = [
            RuntimeError("timeout"),
            None,
        ]
        for failure in failures:
            with self.subTest(failure=failure):
                def api(*_args):
                    if failure:
                        raise failure
                    return {"classifications": []}, 1.0

                source = [{"text": "a"}, {"text": "b"}]
                routed = route_results("prompt", source, "model", 0.8, 3, api)
                self.assertEqual([r["route"] for r in routed["automatic"]], ["fail_open", "fail_open"])
                self.assertTrue(routed.get("error"))


class ConsentTests(unittest.TestCase):
    def test_natural_positive_and_mixed_task(self):
        for prompt in ("sì", "Si, usale e correggi il bug", "mostramele", "va bene", "certo, mostramele"):
            with self.subTest(prompt=prompt):
                self.assertEqual(consent_decision(prompt), "positive")

    def test_unrelated_clitics_do_not_consent(self):
        for prompt in (
            "genera le metriche e mostrale in tabella",
            "prendi le chiavi e usale nel client",
            "apri i log e mostrale",
        ):
            with self.subTest(prompt=prompt):
                self.assertIsNone(consent_decision(prompt))

    def test_negative_precedes_positive(self):
        for prompt in ("no", "sì ma non usarle", "ignorale e continua", "non usale", "non mostramele"):
            with self.subTest(prompt=prompt):
                self.assertEqual(consent_decision(prompt), "negative")
        self.assertIsNone(consent_decision("correggi il bug"))
        self.assertIsNone(
            consent_decision("Il parser risponde sì quando il flag è attivo; correggilo")
        )
        self.assertIsNone(consent_decision("Il test verifica che la risposta sia no"))


class PendingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = os.path.join(self.tmp.name, "pending")
        self.memories = [{"text": "memoria", "route": "classifier_medium"}]

    def tearDown(self):
        self.tmp.cleanup()

    def test_permissions_ttl_isolation_and_single_consumption(self):
        self.assertTrue(save_pending(self.directory, "s1", "/a", self.memories, now=100))
        self.assertIsNone(load_pending(self.directory, "s1", "/b", 10, now=101))
        self.assertEqual(load_pending(self.directory, "s1", "/a", 10, now=101), self.memories)

        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(self.directory).st_mode), 0o700)
            files = [p for p in os.listdir(self.directory) if p.endswith(".json")]
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.directory, files[0])).st_mode), 0o600)

        self.assertEqual(consume_pending(self.directory, "s1", "/a", 10, now=102), self.memories)
        self.assertIsNone(consume_pending(self.directory, "s1", "/a", 10, now=103))

        save_pending(self.directory, "s1", "/a", self.memories, now=100)
        self.assertIsNone(load_pending(self.directory, "s1", "/a", 10, now=111))

    def test_discard_and_concurrent_single_consumer(self):
        save_pending(self.directory, "s1", "/a", self.memories)
        self.assertTrue(discard_pending(self.directory, "s1", "/a"))
        self.assertIsNone(load_pending(self.directory, "s1", "/a", 10))

        save_pending(self.directory, "s1", "/a", self.memories, now=100)
        self.assertTrue(discard_pending_if_present(self.directory, "s1", "/a", 10, now=101))
        self.assertFalse(discard_pending_if_present(self.directory, "s1", "/a", 10, now=102))

        save_pending(self.directory, "s1", "/a", self.memories)
        barrier = threading.Barrier(2)
        results = []

        def consume():
            barrier.wait()
            results.append(consume_pending(self.directory, "s1", "/a", 10))

        threads = [threading.Thread(target=consume) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sum(result == self.memories for result in results), 1)
        self.assertEqual(sum(result is None for result in results), 1)

    def test_invalid_pending_directory_returns_false(self):
        invalid = os.path.join(self.tmp.name, "not-a-directory")
        with open(invalid, "w", encoding="utf-8") as handle:
            handle.write("x")
        self.assertFalse(save_pending(invalid, "s1", "/a", self.memories))

    def test_lock_timeout_fails_closed(self):
        save_pending(self.directory, "s1", "/a", self.memories)
        with mock.patch("lib.hindsight_recall_filter._file_lock") as lock:
            lock.return_value.__enter__.return_value = False
            lock.return_value.__exit__.return_value = False
            self.assertIsNone(consume_pending(self.directory, "s1", "/a", 10))
            self.assertFalse(discard_pending(self.directory, "s1", "/a"))
            self.assertFalse(save_pending(self.directory, "s2", "/a", self.memories))
        self.assertEqual(load_pending(self.directory, "s1", "/a", 10), self.memories)


if __name__ == "__main__":
    unittest.main()
