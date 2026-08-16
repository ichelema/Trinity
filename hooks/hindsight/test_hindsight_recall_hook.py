"""E2e deterministico di hindsight-recall.sh (audit ICH-66, finding B7; ICH-73).

Recall, classificatore e POST /memories sono mockati da un server HTTP locale;
l'hook viene eseguito come vero subprocess bash con HOOK_INPUT su stdin. Copre
i rami che vivono solo nel corpo dell'hook: regola high+medium, consenso/pending
end-to-end, fail-open su classificatore rotto e su save_pending impossibile, e
il consenso del RETAIN pending (ICH-73): scarto visibile su prompt nuovo, context
dalla proposta di Claude nel transcript o dalla risposta `context: ...`, sempre
con UN SOLO oggetto JSON su stdout.

ICH-86: copre anche il retain DIFFERITO — lo Stop hook (hindsight-retain.sh,
eseguito anch'esso come subprocess) accoda soltanto; l'entry viene valutata
dall'hook recall al prompt successivo (gate stubbato dallo stesso mock via
HS_OPENAI_URL): POST /memories, oppure pending + domanda in coda alla risposta
fusa nello stesso JSON del recall.
"""

import glob
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from lib.hindsight_retain_gate import save_retain_pending

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HOOKS_DIR, "hindsight-recall.sh")
STOP_HOOK = os.path.join(HOOKS_DIR, "hindsight-retain.sh")
# Path esplicito: su Windows CreateProcess cerca in System32 PRIMA del PATH e
# "bash" diventerebbe la bash WSL. shutil.which cerca solo nel PATH (MSYS).
BASH = shutil.which("bash") or "bash"


class MockBackend(BaseHTTPRequestHandler):
    """Un solo server per tutti gli endpoint: /memories/recall, chat/completions
    (classificatore del recall E gate del retain, distinti dal nome dello schema
    json_schema nella richiesta) e la POST /memories eseguita dal consenso del
    retain pending (ICH-73) o dal retain differito (ICH-86)."""

    recall_results: list = []
    classifier_spec: object = None  # lista di classifications | ("status", int) | "garbage"
    classifier_calls = 0
    gate_spec: dict = {}  # decisione del gate retain (action/reason/preview/context)
    gate_calls = 0
    retain_posts: list = []  # body JSON delle POST /memories, in ordine
    # Ritardi artificiali (secondi) per misurare il parallelismo gate/recall
    # (WP-D): recall_delay_s vale SOLO per il recall dell'hook (payload di
    # build_recall_payload, ha "budget"), non per la query anti-duplicato del
    # gate ({"query","limit"}): cosi' il tempo del ramo gate e' gate_delay_s e
    # quello del ramo recall e' recall_delay_s, senza sovrapposizioni.
    recall_delay_s = 0.0
    gate_delay_s = 0.0

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        cls = type(self)
        if self.path.endswith("/memories/recall"):
            if cls.recall_delay_s and "budget" in self._json(body):
                time.sleep(cls.recall_delay_s)
            self._send(200, json.dumps({"results": cls.recall_results}))
        elif self.path.endswith("/memories"):
            cls.retain_posts.append(json.loads(body.decode("utf-8")))
            self._send(200, json.dumps({"success": True}))
        elif self.path.endswith("/chat/completions") and self._schema_name(body) == "retain_gate_decision":
            cls.gate_calls += 1
            if cls.gate_delay_s:
                time.sleep(cls.gate_delay_s)
            decision = {"duplicate_of": [], "context": "", **cls.gate_spec}
            self._send(200, json.dumps({"choices": [{"message": {"content": json.dumps(decision)}}]}))
        elif self.path.endswith("/chat/completions"):
            cls.classifier_calls += 1
            if isinstance(cls.classifier_spec, tuple):
                self._send(cls.classifier_spec[1], "{}")
            elif cls.classifier_spec == "garbage":
                self._send(200, "not json at all")
            else:
                content = json.dumps({"classifications": cls.classifier_spec})
                self._send(200, json.dumps({"choices": [{"message": {"content": content}}]}))
        else:
            self._send(404, "{}")

    @staticmethod
    def _json(body: bytes) -> dict:
        try:
            data = json.loads(body.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @classmethod
    def _schema_name(cls, body: bytes) -> str:
        try:
            return cls._json(body)["response_format"]["json_schema"]["name"]
        except Exception:
            return ""

    def _send(self, status, body):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass


class HookE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockBackend)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pending_dir = os.path.join(self.tmp.name, "pending")
        self.retain_pending_dir = os.path.join(self.tmp.name, "retain-pending")
        # Coda dello Stop hook e stato del throttling del retain differito (ICH-86):
        # dir temporanee, cosi' nessun test tocca la cache reale dell'utente.
        self.queue_dir = os.path.join(self.tmp.name, "retain-queue")
        self.state_dir = os.path.join(self.tmp.name, "retain-state")
        os.makedirs(self.queue_dir)
        os.makedirs(self.state_dir)
        MockBackend.recall_results = []
        MockBackend.classifier_spec = []
        MockBackend.classifier_calls = 0
        MockBackend.gate_spec = {}
        MockBackend.gate_calls = 0
        MockBackend.retain_posts = []
        MockBackend.recall_delay_s = 0.0
        MockBackend.gate_delay_s = 0.0

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, prompt, session_id="e2e-session", transcript_path=None, extra_env=None):
        hook = {"prompt": prompt, "session_id": session_id, "cwd": self.tmp.name}
        if transcript_path is not None:
            hook["transcript_path"] = transcript_path
        hook_input = json.dumps(hook)
        env = {
            **os.environ,
            "HINDSIGHT_API_URL": f"http://127.0.0.1:{self.port}",
            "HS_OPENAI_URL": f"http://127.0.0.1:{self.port}/v1/chat/completions",
            "OPENAI_API_KEY": "test-key",
            "HS_CFG_BANK": '{"recall_banks": []}',
            "HS_CFG_RECALL_PENDING_DIR": self.pending_dir,
            "HS_RETAIN_PENDING_DIR": self.retain_pending_dir,
            "HS_CFG_RECALL_TIMEOUT": "5",
            "HS_CFG_RECALL_RESULT_FILTER_TIMEOUT": "5",
            "HS_CFG_RECALL_DEBUG_IN_CONTEXT": "false",
            # Retain differito (ICH-86): coda/stato/pending isolati, gate stubbato
            # dal mock, throttling bypassato, debug spento (la config del plugin
            # lo accende), retain acceso a prescindere dalla config di progetto.
            "HS_RETAIN_QUEUE_DIR": self.queue_dir,
            "HS_RETAIN_STATE_DIR": self.state_dir,
            "HS_RETAIN_FORCE": "1",
            "API_URL": f"http://127.0.0.1:{self.port}/banks/t",
            "HS_CFG_RETAIN_ENABLED": "true",
            "HS_CFG_RETAIN_DEBUG_IN_CONTEXT": "false",
            "HS_CFG_RETAIN_GATE_TIMEOUT": "5",
            **(extra_env or {}),
        }
        proc = subprocess.run(
            [BASH, HOOK], input=hook_input, env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        if not proc.stdout.strip():
            return None
        # stdout non vuoto deve essere UN SOLO oggetto JSON valido: due oggetti
        # (es. notifica + contesto stampati separatamente) fanno fallire il parse.
        return json.loads(proc.stdout)

    def context(self, output):
        return output["hookSpecificOutput"]["additionalContext"]

    def pending_files(self):
        return glob.glob(os.path.join(self.pending_dir, "*.json"))

    def save_retain_pending(self, preview, context="", metadata=None, api_url=None):
        """Pending del retain (gate ICH-67/73) come lo lascia il worker allo Stop:
        stessa lib e stessa dir che l'hook legge via HS_RETAIN_PENDING_DIR.
        api_url None = il MockBackend; esplicito per simulare un bank giu'."""
        item = {
            "content": "finestra e2e",
            "context": context,
            "tags": ["claude-code"],
            "timestamp": "2026-08-15T10:00:00+00:00",
            "metadata": (
                {"source": "claude-code-hook", "repo": "Trinity", "branch": "main"}
                if metadata is None
                else metadata
            ),
        }
        with mock.patch.dict(os.environ, {"HS_RETAIN_PENDING_DIR": self.retain_pending_dir}):
            saved = save_retain_pending(
                "e2e-session",
                self.tmp.name,
                api_url or f"http://127.0.0.1:{self.port}/banks/t",
                {"items": [item], "async": True},
                preview,
            )
        self.assertTrue(saved)

    def write_transcript(self, assistant_text, trailing_user=None):
        """Transcript JSONL il cui ultimo messaggio assistant e' assistant_text.
        trailing_user: prompt utente NUOVO in coda (a UserPromptSubmit il
        transcript puo' gia' contenerlo): non e' un turno completato."""
        path = os.path.join(self.tmp.name, "transcript.jsonl")
        records = [
            {"type": "user", "message": {"role": "user", "content": "domanda dell'utente"}},
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": assistant_text}],
                },
            },
        ]
        if trailing_user is not None:
            records.append(
                {"type": "user", "message": {"role": "user", "content": trailing_user}}
            )
        with open(path, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path

    def enqueue(self, session_id="e2e-session", transcript_path=None, name="1700000000000000-1.json"):
        """Entry di coda come la lascia hindsight-retain.sh allo Stop: HOOK_INPUT
        dello Stop verbatim (session_id, transcript_path, cwd)."""
        entry = {
            "session_id": session_id,
            "transcript_path": transcript_path or self.write_transcript("risposta e2e"),
            "cwd": self.tmp.name,
            "hook_event_name": "Stop",
        }
        path = os.path.join(self.queue_dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(entry, handle)
        return path

    def queue_files(self):
        return sorted(glob.glob(os.path.join(self.queue_dir, "*.json")))

    def retain_pending_files(self):
        return glob.glob(os.path.join(self.retain_pending_dir, "*.json"))

    PROMPT = "dimmi qualcosa di rilevante sul progetto per favore"

    def test_high_plus_medium_injects_only_high_without_pending(self):
        MockBackend.recall_results = [
            {"text": "alpha memo", "type": "world", "scores": {"reranker": 0.2}},
            {"text": "beta memo", "type": "world", "scores": {"reranker": 0.3}},
        ]
        MockBackend.classifier_spec = [
            {"index": 0, "confidence": "high", "reason": "directly_actionable"},
            {"index": 1, "confidence": "medium", "reason": "plausible_but_uncertain"},
        ]
        output = self.run_hook(self.PROMPT)
        context = self.context(output)
        self.assertIn("alpha memo", context)
        self.assertNotIn("beta memo", context)
        self.assertNotIn("consenso richiesto", context)
        self.assertEqual(self.pending_files(), [])

    def test_medium_only_asks_consent_then_single_consumption(self):
        MockBackend.recall_results = [
            {"text": "gamma memo", "type": "world", "scores": {"reranker": 0.1}},
        ]
        MockBackend.classifier_spec = [
            {"index": 0, "confidence": "medium", "reason": "plausible_but_uncertain"},
        ]
        output = self.run_hook(self.PROMPT)
        context = self.context(output)
        self.assertIn("consenso richiesto", context)
        self.assertNotIn("gamma memo", context)
        self.assertEqual(len(self.pending_files()), 1)

        consented = self.run_hook("sì")
        self.assertIn("gamma memo", self.context(consented))
        self.assertEqual(self.pending_files(), [])

        again = self.run_hook("sì")
        self.assertIsNone(again)  # consumo singolo: niente reiniezione

    def test_negation_discards_pending_without_injection(self):
        MockBackend.recall_results = [
            {"text": "delta memo", "type": "world", "scores": {"reranker": 0.1}},
        ]
        MockBackend.classifier_spec = [
            {"index": 0, "confidence": "medium", "reason": "plausible_but_uncertain"},
        ]
        self.run_hook(self.PROMPT)
        self.assertEqual(len(self.pending_files()), 1)
        refused = self.run_hook("non usarle")
        self.assertIsNone(refused)
        self.assertEqual(self.pending_files(), [])

    def test_medium_without_session_id_fails_open(self):
        MockBackend.recall_results = [
            {"text": "epsilon memo", "type": "world", "scores": {"reranker": 0.1}},
        ]
        MockBackend.classifier_spec = [
            {"index": 0, "confidence": "medium", "reason": "plausible_but_uncertain"},
        ]
        output = self.run_hook(self.PROMPT, session_id="")
        self.assertIn("epsilon memo", self.context(output))
        self.assertEqual(self.pending_files(), [])

    def test_broken_classifier_fails_open_with_all_results(self):
        MockBackend.recall_results = [
            {"text": "zeta memo", "type": "world", "scores": {"reranker": 0.1}},
            {"text": "eta memo", "type": "world"},
        ]
        for spec in ["garbage", ("status", 500)]:
            with self.subTest(spec=spec):
                MockBackend.classifier_spec = spec
                context = self.context(self.run_hook(self.PROMPT))
                self.assertIn("zeta memo", context)
                self.assertIn("eta memo", context)
                self.assertEqual(self.pending_files(), [])

    def test_bypass_scores_skip_the_classifier(self):
        MockBackend.recall_results = [
            {"text": "theta memo", "type": "world", "scores": {"reranker": 0.95}},
        ]
        context = self.context(self.run_hook(self.PROMPT))
        self.assertIn("theta memo", context)
        self.assertEqual(MockBackend.classifier_calls, 0)

    def test_retain_pending_discarded_on_new_prompt_is_visible(self):
        self.save_retain_pending("Salvo la decisione e2e.")
        output = self.run_hook(self.PROMPT)
        # Il pending viene scartato in modo VISIBILE (ICH-73), e il recall
        # prosegue: nessun risultato -> nessun additionalContext, ma la notifica
        # esce comunque, come unico oggetto JSON.
        self.assertIn(
            "memoria in attesa scartata — Salvo la decisione e2e.", output["systemMessage"]
        )
        self.assertNotIn("hookSpecificOutput", output)
        self.assertEqual(MockBackend.retain_posts, [])

    def test_retain_pending_discard_notice_merges_with_recall_context(self):
        # Caso limite oltre il contratto (documentato): stesso scarto, ma il
        # recall HA contenuto -> notifica e additionalContext devono uscire nello
        # STESSO oggetto JSON (path emit(), non finish()); run_hook fallirebbe
        # su due oggetti separati.
        self.save_retain_pending("Salvo la decisione e2e.")
        MockBackend.recall_results = [
            {"text": "iota memo", "type": "world", "scores": {"reranker": 0.95}},
        ]
        output = self.run_hook(self.PROMPT)
        self.assertIn(
            "memoria in attesa scartata — Salvo la decisione e2e.", output["systemMessage"]
        )
        self.assertIn("iota memo", self.context(output))
        self.assertEqual(MockBackend.retain_posts, [])

    def test_retain_pending_yes_uses_transcript_proposal(self):
        self.save_retain_pending("Salvo la decisione e2e.", context="")
        transcript = self.write_transcript(
            "Salvo questa memoria con context «dominio e2e»? (sì / no / context: …)"
        )
        output = self.run_hook("sì", transcript_path=transcript)
        message = output["systemMessage"]
        self.assertIn("memoria salvata", message)
        self.assertIn("Salvo la decisione e2e.", message)
        self.assertIn("dominio e2e", message)
        self.assertIn("proposto da Claude", message)
        self.assertEqual(len(MockBackend.retain_posts), 1)
        self.assertEqual(MockBackend.retain_posts[-1]["items"][0]["context"], "dominio e2e")
        self.assertIn("## Hindsight retain", self.context(output))

    def test_retain_pending_context_reply(self):
        self.save_retain_pending("Salvo la decisione e2e.", context="")
        output = self.run_hook("context: dominio esplicito")
        message = output["systemMessage"]
        self.assertIn("memoria salvata", message)
        self.assertIn("dominio esplicito", message)
        self.assertIn("indicato da te", message)
        self.assertEqual(len(MockBackend.retain_posts), 1)
        self.assertEqual(
            MockBackend.retain_posts[-1]["items"][0]["context"], "dominio esplicito"
        )

    def test_retain_pending_post_failure_notifies_and_keeps_pending(self):
        # Bank irraggiungibile (porta 9, nessun listener): il "sì" fallisce, l'utente
        # viene avvisato con l'invito a riprovare e il pending resta in attesa.
        self.save_retain_pending("Salvo la decisione e2e.", api_url="http://127.0.0.1:9/banks/t")
        output = self.run_hook("sì")
        message = output["systemMessage"]
        self.assertIn("NON riuscito", message)
        self.assertIn("riprovare", message)
        self.assertEqual(MockBackend.retain_posts, [])
        retain_pending = glob.glob(os.path.join(self.retain_pending_dir, "*.json"))
        self.assertEqual(len(retain_pending), 1)

    # ----- retain differito (ICH-86): coda dello Stop valutata a UserPromptSubmit -----

    def test_queued_stop_retain_posts_and_recall_unaffected(self):
        # Gate "retain" con context: POST diretta e silenziosa, entry consumata,
        # e il recall dello stesso run esce come sempre (nessun 'decision').
        # Il transcript puo' avere o no il prompt nuovo in coda: stessa finestra.
        MockBackend.gate_spec = {
            "action": "retain",
            "reason": "durable_decision",
            "preview": "Salvo la decisione differita e2e.",
            "context": "dominio differito e2e",
        }
        MockBackend.recall_results = [
            {"text": "kappa memo", "type": "world", "scores": {"reranker": 0.95}},
        ]
        for trailing in (None, self.PROMPT):
            with self.subTest(trailing_user=trailing):
                MockBackend.retain_posts = []
                MockBackend.gate_calls = 0
                transcript = self.write_transcript("risposta e2e", trailing_user=trailing)
                self.enqueue(transcript_path=transcript)
                output = self.run_hook(self.PROMPT, transcript_path=transcript)
                self.assertNotIn("decision", output)
                self.assertNotIn("systemMessage", output)
                self.assertIn("kappa memo", self.context(output))
                self.assertNotIn("Vuoi che salvi", self.context(output))
                self.assertEqual(MockBackend.gate_calls, 1)
                self.assertEqual(len(MockBackend.retain_posts), 1)
                item = MockBackend.retain_posts[0]["items"][0]
                self.assertEqual(item["context"], "dominio differito e2e")
                self.assertIn("[user] domanda dell'utente", item["content"])
                self.assertIn("[assistant] risposta e2e", item["content"])
                self.assertNotIn(self.PROMPT, item["content"])  # prompt nuovo escluso
                self.assertEqual(self.queue_files(), [])
                self.assertEqual(self.retain_pending_files(), [])

    def test_queued_stop_uncertain_asks_at_end_of_reply_merged_with_recall(self):
        # Gate "uncertain": pending salvato e istruzione in additionalContext
        # (domanda verbatim, "as the very last thing in your reply"), fusa nello
        # STESSO oggetto JSON del contesto recall — un solo print.
        MockBackend.gate_spec = {
            "action": "uncertain",
            "reason": "borderline",
            "preview": "Forse salvo la scelta e2e.",
            "context": "dominio incerto e2e",
        }
        MockBackend.recall_results = [
            {"text": "lambda memo", "type": "world", "scores": {"reranker": 0.95}},
        ]
        self.enqueue()
        output = self.run_hook(self.PROMPT)
        context = self.context(output)
        self.assertIn("Vuoi che salvi questa memoria? — Forse salvo la scelta e2e. (sì/no)", context)
        self.assertIn("as the very last thing in your reply", context)
        self.assertIn("lambda memo", context)
        self.assertNotIn("decision", output)
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertEqual(MockBackend.retain_posts, [])
        self.assertEqual(len(self.retain_pending_files()), 1)
        self.assertEqual(self.queue_files(), [])
        # Senza contenuto recall l'istruzione esce da sola (path finish()).
        MockBackend.recall_results = []
        self.enqueue()
        alone = self.run_hook(self.PROMPT)
        self.assertIn("as the very last thing in your reply", self.context(alone))

    def test_queued_stop_of_other_session_is_left_alone(self):
        MockBackend.gate_spec = {
            "action": "retain",
            "reason": "durable_decision",
            "preview": "Non dovrei essere valutato.",
            "context": "altra sessione",
        }
        other = self.enqueue(session_id="other-session")
        output = self.run_hook(self.PROMPT)
        self.assertIsNone(output)
        self.assertEqual(MockBackend.gate_calls, 0)
        self.assertEqual(MockBackend.retain_posts, [])
        self.assertEqual(self.queue_files(), [other])

    def test_queued_stop_retain_disabled_drops_entry_without_work(self):
        # retain_enabled false: l'entry viene consumata e basta — nessun gate,
        # nessuna POST, output identico al run senza coda.
        MockBackend.gate_spec = {
            "action": "retain",
            "reason": "durable_decision",
            "preview": "Non dovrei essere valutato.",
            "context": "retain spento",
        }
        self.enqueue()
        output = self.run_hook(self.PROMPT, extra_env={"HS_CFG_RETAIN_ENABLED": "false"})
        self.assertIsNone(output)
        self.assertEqual(MockBackend.gate_calls, 0)
        self.assertEqual(MockBackend.retain_posts, [])
        self.assertEqual(self.queue_files(), [])
        self.assertEqual(self.retain_pending_files(), [])

    def test_queued_gate_runs_in_parallel_with_recall(self):
        # WP-D: il gate differito gira in un thread PARALLELO al recall dentro
        # lo stesso hook. Con gate e recall che dormono entrambi DELAY secondi
        # il tempo aggiunto e' ~DELAY (parallelo) invece di ~2*DELAY (il vecchio
        # design seriale). Si misura contro una baseline senza ritardi nello
        # stesso ambiente (avvio bash+python varia da macchina a macchina):
        # soglia a meta' strada tra parallelo (+DELAY) e seriale (+2*DELAY),
        # cioe' +1.5*DELAY, con DELAY=2s -> 1s di margine per lato.
        DELAY = 2.0
        MockBackend.gate_spec = {
            "action": "retain",
            "reason": "durable_decision",
            "preview": "Salvo la decisione parallela e2e.",
            "context": "dominio parallelo e2e",
        }
        MockBackend.recall_results = [
            {"text": "mu memo", "type": "world", "scores": {"reranker": 0.95}},
        ]
        self.enqueue()
        t0 = time.monotonic()
        baseline_output = self.run_hook(self.PROMPT)
        baseline = time.monotonic() - t0
        self.assertIn("mu memo", self.context(baseline_output))
        self.assertEqual(len(MockBackend.retain_posts), 1)

        MockBackend.retain_posts = []
        MockBackend.gate_calls = 0
        MockBackend.recall_delay_s = DELAY
        MockBackend.gate_delay_s = DELAY
        self.enqueue()
        t0 = time.monotonic()
        output = self.run_hook(self.PROMPT)
        elapsed = time.monotonic() - t0
        # stesso esito funzionale: recall iniettato, POST del retain fatta,
        # coda consumata, un solo JSON
        self.assertIn("mu memo", self.context(output))
        self.assertNotIn("systemMessage", output)
        self.assertEqual(MockBackend.gate_calls, 1)
        self.assertEqual(len(MockBackend.retain_posts), 1)
        self.assertEqual(self.queue_files(), [])
        # i ritardi sono stati davvero pagati (almeno una volta)...
        self.assertGreaterEqual(elapsed, DELAY)
        # ...ma NON due volte: parallelo, non seriale
        self.assertLess(
            elapsed,
            baseline + 1.5 * DELAY,
            f"hook seriale? baseline={baseline:.2f}s con ritardi={elapsed:.2f}s (DELAY={DELAY}s)",
        )
        print(f"\n[parallelismo] baseline={baseline:.2f}s con ritardi={elapsed:.2f}s (DELAY={DELAY}s)")

    def test_stop_hook_enqueues_hook_input_verbatim(self):
        # hindsight-retain.sh (Stop): risponde '{}' e scrive UNA entry con il
        # HOOK_INPUT verbatim sotto $XDG_CACHE_HOME/trinity/hs-retain-queue/.
        cache_home = os.path.join(self.tmp.name, "xdg-cache")
        hook_input = json.dumps({
            "session_id": "stop-session",
            "transcript_path": "/x/transcript.jsonl",
            "cwd": "/y",
            "hook_event_name": "Stop",
            "stop_hook_active": False,
        })
        proc = subprocess.run(
            [BASH, STOP_HOOK], input=hook_input,
            env={**os.environ, "XDG_CACHE_HOME": cache_home},
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), {})
        self.assertEqual(proc.stdout.strip(), "{}")
        queue = glob.glob(os.path.join(cache_home, "trinity", "hs-retain-queue", "*.json"))
        self.assertEqual(len(queue), 1)
        with open(queue[0], encoding="utf-8") as handle:
            self.assertEqual(handle.read(), hook_input)
        # HOOK_INPUT vuoto: '{}' e nessuna entry nuova.
        proc = subprocess.run(
            [BASH, STOP_HOOK], input="",
            env={**os.environ, "XDG_CACHE_HOME": cache_home},
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        self.assertEqual(proc.stdout.strip(), "{}")
        self.assertEqual(
            len(glob.glob(os.path.join(cache_home, "trinity", "hs-retain-queue", "*.json"))), 1
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
