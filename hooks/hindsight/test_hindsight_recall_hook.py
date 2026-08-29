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
al prompt successivo da un VERO processo python detached lanciato dall'hook
recall (`hindsight-retain-worker.py --queued`, gate stubbato dallo stesso mock
via HS_OPENAI_URL ereditata dall'env dell'hook): POST /memories, oppure
pending + domanda in coda alla risposta fusa nello stesso JSON del recall —
o, se il gate e' piu' lento del budget di pickup, raccolta al prompt dopo.
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
    recall_calls = 0
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
    # Istanti (inizio, fine) delle richieste RITARDATE, per provare che il gate
    # del figlio e il recall dell'hook si sovrappongono nel tempo senza dover
    # cronometrare l'hook da fuori (ICH-109).
    recall_spans: list = []
    gate_spans: list = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        cls = type(self)
        if self.path.endswith("/memories/recall"):
            cls.recall_calls += 1
            if cls.recall_delay_s and "budget" in self._json(body):
                start = time.monotonic()
                time.sleep(cls.recall_delay_s)
                cls.recall_spans.append((start, time.monotonic()))
            self._send(200, json.dumps({"results": cls.recall_results}))
        elif self.path.endswith("/memories"):
            cls.retain_posts.append(json.loads(body.decode("utf-8")))
            self._send(200, json.dumps({"success": True}))
        elif self.path.endswith("/chat/completions") and self._schema_name(body) == "retain_gate_decision":
            cls.gate_calls += 1
            if cls.gate_delay_s:
                start = time.monotonic()
                time.sleep(cls.gate_delay_s)
                cls.gate_spans.append((start, time.monotonic()))
            decision = {"durable_claims": [], "covered_by": [], "context": "", **cls.gate_spec}
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
        MockBackend.recall_calls = 0
        MockBackend.classifier_spec = []
        MockBackend.classifier_calls = 0
        MockBackend.gate_spec = {}
        MockBackend.gate_calls = 0
        MockBackend.retain_posts = []
        MockBackend.recall_delay_s = 0.0
        MockBackend.gate_delay_s = 0.0
        MockBackend.recall_spans = []
        MockBackend.gate_spans = []

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except OSError:
            # Un figlio detached ancora vivo ricrea la dir mentre la si
            # cancella (_write_outbox fa makedirs exist_ok): su Windows sarebbe
            # un ERROR spurio a test gia' passato (ICH-109).
            shutil.rmtree(self.tmp.name, ignore_errors=True)

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
            # Come per il retain sotto: l'e2e prova l'hook, non l'interruttore
            # master, quindi il recall va acceso a prescindere dalla config.
            "HS_CFG_RECALL_ENABLED": "true",
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
        # Diagnostica esplicita: senza, un figlio detached oltre il budget di
        # pickup fa morire il test con un KeyError che non dice perche'.
        self.assertIsNotNone(
            output, "l'hook non ha emesso nulla: figlio detached oltre il budget di pickup?"
        )
        self.assertIn(
            "hookSpecificOutput",
            output,
            f"nessun contesto nell'output dell'hook: {json.dumps(output, ensure_ascii=False)[:200]}",
        )
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
        # Come _queue_files nel worker: l'outbox del gate (<session>.out.json)
        # vive nella stessa dir ma non e' un'entry di coda. Se l'hook e' uscito
        # prima del pickup (macchina lenta) resta su disco, e senza questo
        # filtro le asserzioni "coda consumata" lo conterebbero (ICH-109).
        return sorted(
            path
            for path in glob.glob(os.path.join(self.queue_dir, "*.json"))
            if not path.endswith(".out.json")
        )

    def retain_pending_files(self):
        return glob.glob(os.path.join(self.retain_pending_dir, "*.json"))

    def context_with_gate_question(self, output, question):
        """Contesto di un prompt in cui la domanda del gate deve uscire SUBITO.
        Esce subito solo se il figlio detached rientra nel budget di pickup;
        oltre il budget la domanda esce al prompt dopo — comportamento di
        design, coperto da test_slow_gate_... Sotto carico questo test non ha
        piu' nulla da verificare e si salta, ma solo dopo aver letto la domanda
        nell'outbox del figlio: se il gate non l'ha prodotta affatto resta un
        fallimento (ICH-109).

        La domanda si cerca in modo tollerante, senza passare da context(): un
        prompt il cui pending viene scartato emette solo systemMessage, e li'
        l'assertIn di context() fallirebbe prima che si possa decidere."""
        context = ((output or {}).get("hookSpecificOutput") or {}).get("additionalContext", "")
        if question not in context:
            # Nota: questo skip non distingue "figlio lento" da "pickup
            # in-budget rotto". Distinguerli qui richiede di indovinare i tempi
            # di un processo staccato; la proprieta' e' invece coperta in modo
            # deterministico e in-process da test_hindsight_retain_gate.py
            # (gate_output/retain_at_prompt), che gira nello stesso check.
            with open(self.wait_for_outbox(20.0), encoding="utf-8") as handle:
                late = json.dumps(json.load(handle), ensure_ascii=False)
            self.assertIn(
                question, late, "il gate non ha prodotto la domanda, ne' in tempo ne' in ritardo"
            )
            self.skipTest("figlio detached oltre il budget: la domanda esce al prompt dopo")
        return context

    def wait_for_retain_posts(self, count, timeout_s=25.0):
        """Il gate differito gira in un processo detached che POSTa *prima* di
        scrivere l'outbox: se l'hook e' uscito prima del suo pickup (macchina
        lenta o carica) la POST arriva dopo il ritorno di run_hook, e senza
        questa attesa finirebbe nel test successivo (ICH-109)."""
        deadline = time.monotonic() + timeout_s
        while len(MockBackend.retain_posts) < count:
            self.assertLess(
                time.monotonic(),
                deadline,
                f"attese {count} POST del retain, arrivate {len(MockBackend.retain_posts)}",
            )
            time.sleep(0.1)
        self.assertEqual(len(MockBackend.retain_posts), count)

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

    def test_retain_pending_discard_says_when_question_was_not_asked(self):
        # Claude ha OMESSO la domanda in coda alla risposta (l'ultimo testo
        # assistant non la contiene): la notifica di scarto non deve fingere
        # una domanda mai vista. Con la domanda nel transcript: notifica classica.
        self.save_retain_pending("Salvo la decisione e2e.")
        transcript = self.write_transcript("risposta senza domanda finale")
        output = self.run_hook(self.PROMPT, transcript_path=transcript)
        self.assertIn(
            "memoria in attesa scartata (domanda non posta da Claude) — Salvo la decisione e2e.",
            output["systemMessage"],
        )
        self.save_retain_pending("Salvo la decisione e2e.")
        transcript = self.write_transcript(
            "risposta\n\nVuoi che salvi questa memoria? — Salvo la decisione e2e. (sì/no)"
        )
        output = self.run_hook(self.PROMPT, transcript_path=transcript)
        self.assertIn(
            "memoria in attesa scartata — Salvo la decisione e2e.", output["systemMessage"]
        )
        self.assertNotIn("domanda non posta", output["systemMessage"])

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
                # gate_calls lo incrementa il figlio, come la POST: si aspetta
                # prima, o un figlio lento fa fallire qui invece che nell'attesa.
                self.wait_for_retain_posts(1)
                self.assertEqual(MockBackend.gate_calls, 1)
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
        question = "Vuoi che salvi questa memoria? — Forse salvo la scelta e2e. (sì/no)"
        context = self.context_with_gate_question(output, question)
        self.assertIn(question, context)
        self.assertIn("as the very last thing in your reply", context)
        self.assertIn("lambda memo", context)
        # La domanda e' anche VISIBILE nel terminale (systemMessage), cosi'
        # l'utente la vede anche se Claude la omettesse in coda alla risposta.
        self.assertEqual(
            output["systemMessage"],
            "Hindsight: Vuoi che salvi questa memoria? — Forse salvo la scelta e2e. (sì/no)",
        )
        self.assertNotIn("decision", output)
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertEqual(MockBackend.retain_posts, [])
        self.assertEqual(len(self.retain_pending_files()), 1)
        self.assertEqual(self.queue_files(), [])
        # Senza contenuto recall l'istruzione esce da sola (path finish()).
        MockBackend.recall_results = []
        self.enqueue()
        alone = self.run_hook(self.PROMPT)
        self.assertIn(
            "as the very last thing in your reply",
            self.context_with_gate_question(alone, question),
        )

    def test_queued_uncertain_plus_recall_medium_same_prompt_yes_resolves_to_retain(self):
        # Doppia domanda nello stesso prompt (caso raro ma reale, preesistente:
        # poteva gia' capitare con lo Stop bloccante): gate uncertain sul turno
        # precedente + memorie medium dal recall. Attesi: UN solo JSON con
        # entrambe le istruzioni; al "si'" successivo la priorita' e'
        # deterministica: vince il retain (POST eseguita) e il pending medium
        # viene scartato senza iniezione — lo stesso "si'" non autorizza entrambi.
        MockBackend.gate_spec = {
            "action": "uncertain",
            "reason": "borderline",
            "preview": "Forse salvo la doppia domanda e2e.",
            "context": "dominio doppia domanda e2e",
        }
        MockBackend.recall_results = [
            {"text": "mu memo", "type": "world", "scores": {"reranker": 0.1}},
        ]
        MockBackend.classifier_spec = [
            {"index": 0, "confidence": "medium", "reason": "plausible_but_uncertain"},
        ]
        self.enqueue()
        output = self.run_hook(self.PROMPT)
        question = "Vuoi che salvi questa memoria? — Forse salvo la doppia domanda e2e. (sì/no)"
        context = self.context_with_gate_question(output, question)
        self.assertIn(question, context)
        self.assertIn("consenso richiesto", context)
        self.assertNotIn("mu memo", context)
        self.assertEqual(len(self.retain_pending_files()), 1)
        self.assertEqual(len(self.pending_files()), 1)
        self.assertEqual(MockBackend.retain_posts, [])

        consented = self.run_hook("sì")
        self.assertIn("memoria salvata", consented["systemMessage"])
        self.assertNotIn("mu memo", json.dumps(consented, ensure_ascii=False))
        self.assertEqual(len(MockBackend.retain_posts), 1)
        self.assertEqual(self.retain_pending_files(), [])
        self.assertEqual(self.pending_files(), [])  # medium scartato, non iniettato
        # un secondo "si'" non trova piu' nulla: consumo singolo su entrambi
        self.assertIsNone(self.run_hook("sì"))

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

    def test_recall_disabled_emits_nothing_and_never_queries_the_bank(self):
        # recall_enabled false — il valore committato in hindsight.config.json,
        # quindi il ramo che gira davvero: l'hook esce a 0 senza contesto e
        # senza interrogare il bank. Con il recall acceso lo stesso input
        # inietterebbe "nu memo" (0.95 supera la soglia) e manderebbe l'unico
        # candidato sotto soglia, "xi memo" (indice 1), al classificatore.
        MockBackend.recall_results = [
            {"text": "nu memo", "type": "world", "scores": {"reranker": 0.95}},
            {"text": "xi memo", "type": "world", "scores": {"reranker": 0.5}},
        ]
        MockBackend.classifier_spec = [
            {"index": 1, "confidence": "high", "reason": "directly_actionable"},
        ]
        output = self.run_hook(self.PROMPT, extra_env={"HS_CFG_RECALL_ENABLED": "false"})
        self.assertIsNone(output)
        # recall_calls diretto: senza, una regressione che interroga il bank e
        # butta via i risultati prima di classificarli passerebbe inosservata —
        # e col recall spento nessun prompt deve uscire dalla macchina.
        self.assertEqual(MockBackend.recall_calls, 0)
        self.assertEqual(MockBackend.classifier_calls, 0)
        self.assertEqual(self.pending_files(), [])

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
        # WP-D/WP-E: il gate differito gira in un PROCESSO detached PARALLELO
        # al recall dell'hook (che ne aspetta l'outbox entro il budget di
        # pickup). Con gate e recall che dormono entrambi DELAY secondi il
        # tempo aggiunto e' ~DELAY (parallelo, + l'avvio del figlio) invece di
        # ~2*DELAY (il vecchio design seriale). Si misura contro una baseline
        # senza ritardi nello stesso ambiente (avvio bash+python varia da
        # macchina a macchina): soglia a meta' strada tra parallelo (+DELAY) e
        # seriale (+2*DELAY), cioe' +1.5*DELAY, con DELAY=2s -> 1s di margine
        # per lato.
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
        self.wait_for_retain_posts(1)

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
        self.wait_for_retain_posts(1)
        self.assertEqual(MockBackend.gate_calls, 1)
        self.assertEqual(self.queue_files(), [])
        # i ritardi sono stati davvero pagati (almeno una volta)...
        self.assertGreaterEqual(elapsed, DELAY)
        # ...ma il recall NON ha aspettato che il gate finisse. Si guardano gli
        # istanti registrati dal mock invece del tempo di parete: quello misura
        # anche l'avvio di bash+python, che sotto carico sfora il budget di
        # pickup e trasformava un hook seriale in uno skip (ICH-109). Qui il
        # confronto e' fra due eventi dello stesso orologio: se l'hook fosse
        # seriale il recall partirebbe solo dopo la fine del gate.
        if not MockBackend.gate_spans:
            self.skipTest("gate non eseguito in questo run (outbox della baseline raccolto): misura inconcludente")
        recall_start, recall_end = MockBackend.recall_spans[-1]
        gate_start, gate_end = MockBackend.gate_spans[-1]
        self.assertLess(
            recall_start,
            gate_end,
            f"hook seriale? recall {recall_start:.2f}-{recall_end:.2f}, "
            f"gate {gate_start:.2f}-{gate_end:.2f} (DELAY={DELAY}s)",
        )
        print(f"\n[parallelismo] baseline={baseline:.2f}s con ritardi={elapsed:.2f}s (DELAY={DELAY}s)")

    def outbox_path(self, session_id="e2e-session"):
        return os.path.join(self.queue_dir, session_id + ".out.json")

    def wait_for_outbox(self, timeout_s: float, session_id="e2e-session") -> str:
        """Aspetta che il processo detached scriva l'outbox (e quindi sia
        finito col lavoro): serve al test lento e a non lasciare figli vivi
        al teardown."""
        deadline = time.monotonic() + timeout_s
        path = self.outbox_path(session_id)
        while not os.path.exists(path):
            self.assertLess(time.monotonic(), deadline, f"outbox {path} mai comparso")
            time.sleep(0.1)
        return path

    def test_slow_gate_does_not_stall_prompt_and_is_picked_up_next_prompt(self):
        # WP-E: un gate PIU' LENTO del budget di pickup (RETAIN_PICKUP_BUDGET_S,
        # 6s da T0) non deve trattenere il prompt: l'hook esce senza la
        # domanda, il processo detached (VERO python, lanciato dall'hook)
        # continua e scrive l'outbox; il prompt successivo lo raccoglie e
        # mostra la domanda ORA, saltando il consenso (il prompt normale NON
        # deve scartare il pending come "new_prompt"); il "si'" del prompt
        # dopo ancora esegue la POST. Il figlio eredita l'env dell'hook
        # (HS_OPENAI_URL/API_URL puntano al mock: gate_calls e retain_posts
        # lo dimostrano). Gate timeout alzato: 5s farebbe scattare il
        # fail-closed prima del ritardo artificiale.
        GATE_DELAY = 12.0
        PICKUP_BUDGET = 6.0  # RETAIN_PICKUP_BUDGET_S in hindsight-recall.sh
        slow_env = {"HS_CFG_RETAIN_GATE_TIMEOUT": "25"}
        MockBackend.gate_spec = {
            "action": "uncertain",
            "reason": "borderline",
            "preview": "Forse salvo la scelta lenta e2e.",
            "context": "dominio lento e2e",
        }
        t0 = time.monotonic()
        self.assertIsNone(self.run_hook(self.PROMPT, extra_env=slow_env))  # niente in coda
        baseline = time.monotonic() - t0

        MockBackend.gate_delay_s = GATE_DELAY
        MockBackend.recall_delay_s = 0.5
        self.enqueue()
        t0 = time.monotonic()
        first = self.run_hook(self.PROMPT, extra_env=slow_env)
        elapsed = time.monotonic() - t0
        # L'hook aspetta l'outbox al massimo fino a T0+budget e poi esce: ben
        # sotto il ritardo del gate (un hook che aspettasse il gate ci
        # metterebbe >= GATE_DELAY + avvio del figlio). Doppio limite: relativo
        # alla baseline (avvio bash+python della macchina, +3s di tolleranza) e
        # assoluto (sotto GATE_DELAY, che un hook bloccato non puo' battere).
        self.assertLess(
            elapsed,
            baseline + PICKUP_BUDGET + 3.0,
            f"l'hook ha aspettato il gate lento? baseline={baseline:.2f}s primo run={elapsed:.2f}s",
        )
        self.assertLess(elapsed, GATE_DELAY)
        # ...e senza la domanda: il gate non ha ancora risposto
        self.assertNotIn("Vuoi che salvi", json.dumps(first or {}, ensure_ascii=False))
        self.assertEqual(self.retain_pending_files(), [])  # niente pending, non ancora
        # Il figlio finisce per conto suo: outbox su disco (gate 12s + avvio).
        t1 = time.monotonic()
        self.wait_for_outbox(GATE_DELAY + 15.0)
        waited = time.monotonic() - t1
        # L'entry la consuma il figlio: si verifica dopo l'outbox, o un avvio
        # lento la trova ancora in coda al ritorno dell'hook (ICH-109).
        self.assertEqual(self.queue_files(), [])
        self.assertEqual(MockBackend.gate_calls, 1)
        self.assertEqual(len(self.retain_pending_files()), 1)  # pending scritto dal figlio
        self.assertEqual(MockBackend.retain_posts, [])
        # Prompt successivo, NORMALE: la domanda esce adesso (systemMessage
        # visibile + istruzione in additionalContext) e il pending resta —
        # il consenso e' stato saltato, altrimenti questo prompt lo avrebbe
        # scartato con la notifica "memoria in attesa scartata".
        MockBackend.gate_delay_s = 0.0
        MockBackend.recall_delay_s = 0.0
        second = self.run_hook(self.PROMPT, extra_env=slow_env)
        self.assertEqual(
            second["systemMessage"],
            "Hindsight: Vuoi che salvi questa memoria? — Forse salvo la scelta lenta e2e. (sì/no)",
        )
        self.assertIn("as the very last thing in your reply", self.context(second))
        self.assertNotIn("scartata", json.dumps(second, ensure_ascii=False))
        self.assertNotIn("asks_consent", json.dumps(second))
        self.assertFalse(os.path.exists(self.outbox_path()))  # raccolto e cancellato
        self.assertEqual(len(self.retain_pending_files()), 1)
        self.assertEqual(MockBackend.gate_calls, 1)  # nessuna nuova valutazione
        # "si'": la POST del pending parte, pending consumato.
        third = self.run_hook("sì", extra_env=slow_env)
        self.assertIn("memoria salvata", third["systemMessage"])
        self.assertEqual(len(MockBackend.retain_posts), 1)
        self.assertEqual(MockBackend.retain_posts[0]["items"][0]["context"], "dominio lento e2e")
        self.assertEqual(self.retain_pending_files(), [])
        print(
            f"\n[gate lento] baseline={baseline:.2f}s primo run={elapsed:.2f}s "
            f"(budget {PICKUP_BUDGET}s, gate {GATE_DELAY}s), outbox dopo altri {waited:.2f}s"
        )

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
            env={**os.environ, "XDG_CACHE_HOME": cache_home,
                 "HS_CFG_RETAIN_ENABLED": "true"},
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
            env={**os.environ, "XDG_CACHE_HOME": cache_home,
                 "HS_CFG_RETAIN_ENABLED": "true"},
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        self.assertEqual(proc.stdout.strip(), "{}")
        self.assertEqual(
            len(glob.glob(os.path.join(cache_home, "trinity", "hs-retain-queue", "*.json"))), 1
        )
        # Senza EPOCHREALTIME (bash < 5, es. macOS /bin/bash 3.2): l'hook non
        # deve morire su set -u e il nome deve restare a 16 cifre, cosi' ordina
        # in modo cronologico insieme alle entry scritte da bash 5. Si simula
        # con `unset` in un bash che poi sourcia lo script.
        proc = subprocess.run(
            [BASH, "-c", 'unset EPOCHREALTIME; . "$0"', STOP_HOOK], input=hook_input,
            env={**os.environ, "XDG_CACHE_HOME": cache_home,
                 "HS_CFG_RETAIN_ENABLED": "true"},
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "{}")
        names = sorted(
            os.path.basename(p)
            for p in glob.glob(os.path.join(cache_home, "trinity", "hs-retain-queue", "*.json"))
        )
        self.assertEqual(len(names), 2)
        for name in names:
            stamp = name.split("-", 1)[0]
            self.assertTrue(stamp.isdigit() and len(stamp) == 16, name)

    def test_stop_hook_skips_queue_when_retain_disabled(self):
        # retain_enabled false: nessuno consuma la coda, quindi l'hook non deve
        # accodare - le entry scadrebbero a 24h e lo sweep del worker le
        # segnalerebbe come drain mancato. Sempre '{}' su stdout.
        cache_home = os.path.join(self.tmp.name, "xdg-cache-off")
        proc = subprocess.run(
            [BASH, STOP_HOOK],
            input=json.dumps({"session_id": "off", "transcript_path": "/x.jsonl", "cwd": "/y"}),
            env={**os.environ, "XDG_CACHE_HOME": cache_home,
                 "HS_CFG_RETAIN_ENABLED": "false"},
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "{}")
        self.assertEqual(
            glob.glob(os.path.join(cache_home, "trinity", "hs-retain-queue", "*.json")), []
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
