"""Loader di configurazione condiviso per gli hook Hindsight.

Fonte unica di verita' per i valori tunabili (URL bank, parametri recall/retain/
reflect). Ordine di caricamento (gli ultimi vincono):
  1. DEFAULTS hardcoded qui sotto
  2. hindsight.config.json del PLUGIN (root del plugin) -- la base
  3. hindsight.config.json del PROGETTO ($CLAUDE_PROJECT_DIR), se presente --
     override per-progetto a MERGE: sovrascrive solo le chiavi che contiene
  4. override da variabili d'ambiente (retrocompatibilita' coi nomi gia' usati)
HS_CONFIG_FILE forza un singolo file (test/retrocompat), saltando 2 e 3.

Uso da Python:   from hindsight_config import load_config; cfg = load_config()
Uso da bash:     python hindsight_config.py --get api_url
                 python hindsight_config.py --banks    # URL retain/recall risolti
                 python hindsight_config.py            # dump completo (debug)

Multi-bank: il blocco "bank" (api_base, core_bank, retain_bank, recall_banks)
sostituisce il vecchio api_url come fonte di verita'. Le keyword "auto"/"core"
sono risolte da resolve_bank(); retain_bank_url() e recall_bank_urls() danno
gli URL pronti per worker e recall hook. Un api_url esplicito in un override
(file o env) vince sul blocco bank (retrocompat single-bank).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse

def cache_dir() -> str:
    """Directory delle cache/stato per-utente: $XDG_CACHE_HOME/trinity, fallback
    ~/.cache/trinity. La crea 0700 se manca (idempotente) e ne ritorna il path.

    NON /tmp, per due motivi distinti:
      - sicurezza: su Linux /tmp e' 1777 e si svuota al reboot, quindi un altro
        utente puo' creare per primo i file che poi rileggiamo (path di interpreti
        -> esecuzione di codice; risultati di recall -> lettura delle memorie e
        iniezione di testo nel contesto). Sotto $HOME 0700 non ci entra nessuno.
      - correttezza: un literal "/tmp/..." su Python nativo Windows si risolve come
        <drive-corrente>:\\tmp\\..., quindi la cache si frammentava per disco.
    expanduser("~") e' Python-safe anche su Windows; $HOME in forma MSYS ("/e/...")
    non lo sarebbe."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    # Slash avanti: il path finisce anche in bash (es. --get recall_cache_dir), dove
    # i backslash di os.path.join sarebbero escape. Windows accetta entrambi.
    d = os.path.join(base, "trinity").replace("\\", "/")
    try:
        os.makedirs(d, mode=0o700, exist_ok=True)
    except OSError:
        pass
    return d


DEFAULTS = {
    "api_url": "http://127.0.0.1:8888/v1/default/banks/trinity-project",
    # Multi-bank: bank per progetto isolati che ereditano un bank CORE condiviso.
    # Hindsight non ha ereditarieta' nativa tra bank (endpoint scoped per-bank
    # nell'URL): l'aggregazione la fanno gli hook client-side.
    #   api_base     base dell'API senza il segmento /banks/<nome>
    #   core_bank    il bank condiviso (l'attuale trinity-project, nessun rebuild)
    #   retain_bank  SCALARE: la scrittura ha 1 bersaglio. Keyword: "auto" = slug
    #                del repo corrente (remote origin -> fallback basename; fuori
    #                da git, o nel repo del plugin stesso, ricade sul core);
    #                "core" o vuoto = core_bank; altro = nome bank letterale.
    #   recall_banks ARRAY: la lettura aggrega (fan-out + rerank). Il core entra
    #                SOLO se listato -> ["auto"] da solo = progetto isolato.
    # Retrocompat: un api_url esplicito (file di config o env) VINCE sul blocco
    # bank e ripristina il comportamento single-bank odierno (vedi load_config).
    "bank": {
        "api_base": "http://127.0.0.1:8888/v1/default",
        "core_bank": "trinity-project",
        "retain_bank": "auto",
        "recall_banks": ["auto", "core"],
    },
    # Interruttori master dell'automazione hook. False => l'hook esce subito,
    # senza chiamate di rete ne' estrazione LLM. Default: attivi (comportamento
    # storico invariato). Override anche via HS_CFG_RECALL_ENABLED / HS_CFG_RETAIN_ENABLED.
    "recall_enabled": True,
    "retain_enabled": True,
    # Guard dei retain falliti silenziosamente (hindsight-failcheck.sh): controlla
    # le async operation in stato "failed" e avvisa via additionalContext. False =>
    # l'hook esce subito. failcheck_window_hours: finestra temporale delle failed
    # da segnalare (evita di ripescare storia vecchia al primo avvio).
    "failcheck_enabled": True,
    "failcheck_window_hours": 24,
    "failcheck_timeout": 3,
    # Dimensione pagina della query /operations?status=failed (ordinata created_at
    # DESC): l'hook pagina finche' un record esce dalla finestra o raggiunge 'total'.
    "failcheck_page_limit": 100,
    "recall_budget": "low",
    "recall_max_tokens": 800,
    "recall_max_results": 8,
    # Multi-bank: cap separato sui risultati finali iniettati (None = usa
    # recall_max_results). Piu' bank = piu' fonti -> puo' valere alzarlo.
    "recall_max_results_multibank": None,
    # Multi-bank: candidati massimi presi da OGNI bank nel fan-out, PRIMA della
    # fusione (rerank globale / interleave) e del taglio a recall_max_results.
    "recall_per_bank_candidates": 5,
    # Soglia minima relevance_score del reranker globale (voyage/rerank-2.5). Null = disattivo
    # (nessun filtro). Un valore >=0 filtra i risultati sotto soglia, ma SOLO nel
    # percorso multi-bank (>=2 bank risolti -> multi_recall). In single-bank l'hook
    # fa la POST diretta al server e NON applica questa soglia: li' il filtro
    # equivalente e' recall_min_reranker (min_scores server-side, vedi sotto).
    "recall_min_rerank_score": None,
    # --- Floor per-stadio passati al server (hindsight-api >=0.8.4, min_scores) ---
    # Tutti None = nessun filtro (default sicuro). Agiscono nel payload di recall,
    # quindi valgono per ENTRAMBI i rami (single- e multi-bank).
    #   semantic/keyword = cutoff retrieval-level (pre-fusione, dentro le SQL arms)
    #   reranker/final   = filtri post-rerank server-side
    # NB: distinto da recall_min_rerank_score, che filtra il rerank GLOBALE
    # client-side (voyage/rerank-2.5) usato solo per fondere piu' bank.
    "recall_min_semantic": None,
    "recall_min_keyword": None,
    "recall_min_reranker": None,
    "recall_min_final": None,
    # Filtra i tipi di fatto cercati dal server. Vuoto => tutti (world+experience+
    # observation), default API. Valori validi: "world", "experience", "observation".
    "recall_types": [],
    # Entita' nei risultati recall. L'API REST le include di DEFAULT (a differenza
    # di GUI/MCP che le tengono spente): la lista entita' per-fatto e' rumore nel
    # contesto iniettato e non serve al ragionamento. False => il payload manda
    # include.entities=null e il server le spegne alla fonte (salta pure la SQL).
    "recall_include_entities": False,
    "recall_min_prompt_chars": 20,
    # Tetto MAX alla query di recall: il query-embedder rifiuta query > 500 token
    # (HTTP 400 "Query too long"). Su prompt con grossi incollati (codice, commit,
    # HTML) il recall fallirebbe silenziosamente. Tronchiamo la query (non il prompt
    # inviato a Claude) alla parte iniziale, che di norma contiene l'intento.
    # ~1500 char ≈ 375 tok di prosa; per codice (più denso) abbassare se rivedi 400.
    "recall_max_prompt_chars": 1500,
    "recall_tags": ["claude-code"],
    "recall_tags_match": "any",
    "recall_cache_ttl": 300,
    "recall_cache_dir": cache_dir() + "/hs-recall-cache",
    "recall_timeout": 6,
    # Budget separato per il rerank ZeroEntropy in multi_recall: gira IN SERIE dopo
    # il fan-out sui bank, quindi recall_timeout + recall_rerank_timeout deve stare
    # sotto il timeout dell'hook recall (hooks.json). Senza budget suo il rerank
    # riusava recall_timeout e la somma sforava il tetto dell'hook.
    "recall_rerank_timeout": 6,
    # Parametri di chunking del retain, consumati da hindsight-retain-worker.py.
    # Devono stare nei DEFAULTS o load_config li scarta dalla whitelist (riga "if
    # k in cfg"). I valori coincidono coi fallback hardcoded del worker.
    "retain_mode": "chunked",
    "retain_overlap_turns": 1,
    "retain_tool_calls": False,
    "retain_every_n_turns": 3,
    "retain_max_files": 15,
    "retain_max_cmds": 10,
    "retain_text_truncate": 2000,
    # context: dominio/i del task da mettere nel campo `context` del retain
    # (schema "claude-code/<dom1>[/<dom2>][/<dom3>]"). NB: in Hindsight il context
    # e' descrittivo (frame per l'LLM estrattore), NON strutturale: relazioni ed
    # observation-scope si reggono su entita' e tag, non sul context. Quindi qui
    # puntiamo solo a un frame d'estrazione piu' utile del vecchio repo/branch.
    #   context_extraction          master switch (False => context piano "claude-code")
    #   context_extraction_strategy "llm" usa il modello; "heuristic" deriva i domini
    #                               dai path dei file modificati (zero rete). "llm"
    #                               ricade automaticamente su "heuristic" se fallisce.
    #   context_extraction_model    modello per la strategia "llm"
    "context_extraction": False,
    "context_extraction_strategy": "llm",
    "context_extraction_model": "gpt-4.1-nano",
    "reflect_budget": "mid",
    "reflect_max_tokens": 2000,
    "recall_compose_enabled": False,
    "recall_compose_max_chars": 60,
    "recall_compose_context_turns": 1,
    "recall_compose_min_context_chars": 40,
    "recall_compose_deictics": [
        "questo",
        "questa",
        "questi",
        "queste",
        "quello",
        "quella",
        "quelli",
        "quelle",
        "qui",
        "qua",
        "adesso",
        "ora",
        "poi",
        "cosi",
        "ciò",
        "cio",
    ],
    "recall_compose_continuations": [
        "e adesso",
        "e poi",
        "e ora",
        "e quindi",
        "vai avanti",
        "continua",
        "prosegui",
        "riprova",
    ],
    "mental_model_max_tokens": 1024,
    "mental_models_inject_on_start": False,
    "mental_models_inject_ids": ["user-profile", "project-conventions"],
    # Tetto sul blocco iniettato da hindsight-mm-inject.sh: Claude Code tronca
    # l'output degli hook oltre 10.000 char (inline resta solo un preview ~2KB),
    # quindi si sta sotto con margine. Da hindsight-api 0.8.5 (issue #2756) il
    # max_tokens dei mental model e' finalmente un cap reale su tutti i percorsi
    # del reflect agent, MA non usarlo per far stare N pagine in questo budget:
    # provato il 2026-07-25 con cap 700 e 850, le pagine perdono meta' contenuto
    # (spariti i workaround specifici, non solo la coda) e l'ultima frase resta
    # mozza. Il motivo: il modello non sa contare i token, ignora il "target
    # budget" del prompt e a fermarlo e' il max_completion_tokens dell'API, che
    # taglia di netto (finish_reason=length). Per accorciare le pagine si agisce
    # sulla fonte: vincolo di formato nella source_query ("max N voci, una riga
    # ciascuna, forma sintomo -> fix, niente intro/conclusione"). Le voci il
    # modello le conta: dal 2026-07-25 le 3 pagine stanno in ~6.6k char (era
    # 10.4k) e il taglio proporzionale qui sotto non scatta piu'.
    "mental_models_inject_max_chars": 9500,
    "mental_models": [],
    # Debug: se attivo, recall/retain scrivono un evento JSONL per ispezione.
    # debug_log_file vuoto => <project_root>/logs/hindsight-debug.log (vedi hindsight_debug.py)
    "debug_log_enabled": False,
    "debug_log_file": "",
}

# Nomi env legacy gia' usati nel codebase -> chiave di config. Mantengono il
# comportamento esistente (hanno precedenza sul file JSON).
ENV_OVERRIDES = {
    "HINDSIGHT_API_URL": "api_url",
    "HINDSIGHT_CACHE_DIR": "recall_cache_dir",
    "HINDSIGHT_CACHE_TTL": "recall_cache_ttl",
    "HS_RETAIN_EVERY_N": "retain_every_n_turns",
}


def _cast(value: str, sample):
    """Converte la stringa env al tipo del default. Liste accettano JSON o CSV;
    dict (es. HS_CFG_BANK) accettano solo JSON."""
    try:
        if isinstance(sample, bool):
            return value.lower() in ("1", "true", "yes")
        if isinstance(sample, int):
            return int(value)
        if isinstance(sample, list):
            value = value.strip()
            if value.startswith("["):
                return json.loads(value)
            return [v.strip() for v in value.split(",") if v.strip()]
        if isinstance(sample, dict):
            return json.loads(value)
        return value
    except (ValueError, json.JSONDecodeError):
        return sample


def _plugin_config_path() -> str:
    """Config di default del plugin: <plugin_root>/hindsight.config.json.
    Il modulo vive in hooks/hindsight/lib/ -> la root del plugin e' 3 livelli su."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", "..", ".."))
    return os.path.join(root, "hindsight.config.json")


def _project_config_path() -> str | None:
    """Override per-progetto: <project_root>/hindsight.config.json, se presente.
    project_root = $CLAUDE_PROJECT_DIR (passato da Claude Code agli hook)."""
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if not proj:
        return None
    path = os.path.join(proj, "hindsight.config.json")
    return path if os.path.isfile(path) else None


# Chiavi che la config di PROGETTO non puo' sovrascrivere: decidono DOVE finiscono
# i dati (endpoint di rete, destinazioni su disco, routing dei bank). Un repo di
# terzi non e' una fonte fidata e gli hook girano a scope user, cioe' in OGNI
# progetto aperto: senza questo filtro un {"api_url": "https://attacker/x"} nel suo
# hindsight.config.json manda all'attaccante ogni prompt (recall) e il transcript
# (retain). Il blocco "bank" e' bloccato PER INTERO: retain_bank/core_bank
# permetterebbero di scrivere nel core condiviso (poisoning), recall_banks di
# leggere il core o i bank di altri progetti (info-leak), api_base di dirottare
# l'endpoint. Restano impostabili da config plugin/utente e da env
# (HINDSIGHT_API_URL, HS_CFG_*).
PROJECT_BLOCKED_KEYS = {"api_url", "recall_cache_dir", "debug_log_file", "bank"}


def _merge_json(cfg: dict, path: str, trusted: bool = True) -> set[str]:
    """Sovrascrive in cfg le sole chiavi note (presenti nei DEFAULTS) trovate nel
    file JSON. I valori dict (es. "bank") fanno MERGE a un livello invece di
    sostituire: un override parziale {"bank": {"retain_bank": "x"}} non deve
    cancellare api_base/core_bank della base. File assente o non valido => no-op
    (best-effort). Ritorna le chiavi applicate (per il tracking retrocompat di
    api_url in load_config).

    trusted=False (config di progetto): le chiavi in PROJECT_BLOCKED_KEYS
    (incluso l'intero blocco "bank") vengono ignorate — un repo puo' regolare
    COME funziona il recall, non DOVE finiscono i dati."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return set()
    applied: set[str] = set()
    for k, v in data.items():
        if k in cfg and v is not None:
            if not trusted and k in PROJECT_BLOCKED_KEYS:
                continue
            if isinstance(cfg[k], dict) and isinstance(v, dict):
                cfg[k] = {**cfg[k], **v}
            else:
                cfg[k] = v
            applied.add(k)
    return applied


# ---------------------------------------------------------------------------
# Resolver multi-bank: keyword ("auto"/"core"/letterale) -> nome bank -> URL.
# Usati dal recall hook (fan-out sui recall_banks) e dal retain worker
# (bersaglio di scrittura da retain_bank).
# ---------------------------------------------------------------------------

# Cache per-processo dello slug git: evita subprocess ripetuti quando "auto"
# compare piu' volte (es. retain + recall nello stesso processo di test).
_REPO_CACHE: dict[str, tuple[str, str, str]] = {}


# Cache su FILE del git-resolve. I due subprocess git (rev-parse + config) costano
# ~360ms su MSYS (fork lento) e _REPO_CACHE vive solo nel processo: ma ogni hook
# recall e' un processo nuovo, quindi senza questa cache il git si ripaga a OGNI
# prompt. TTL lungo: il remote origin (da cui deriva lo slug) cambia praticamente mai.
_REPO_CACHE_TTL = 3600


def _repo_cache_file(cwd: str) -> str:
    h = hashlib.sha256(cwd.encode("utf-8")).hexdigest()[:16]
    return os.path.join(cache_dir(), "hs-repo-cache", h + ".json")


def _remote_identity(remote: str) -> str:
    """Identita' canonica "host/owner/repo" da un URL di remote git, invariante al
    protocollo: lo STESSO repo clonato via SSH o HTTPS deve dare la stessa stringa,
    altrimenti il confronto col repo del plugin fallirebbe a seconda di come e'
    stato clonato. host e owner in minuscolo (gli host git non distinguono le
    maiuscole). Stringa vuota se il remote manca; forma non riconosciuta =>
    ritorna il valore ripulito (meglio confrontare quello che niente)."""
    clean = remote.strip().rstrip("/")
    if not clean:
        return ""
    clean = clean[:-4] if clean.endswith(".git") else clean
    # SCP-like: git@host:owner/repo
    m = re.match(r"^[^@/]+@([^:/]+):(.+)$", clean)
    if not m:
        # URL: https://host[:port]/owner/repo, ssh://git@host[:port]/owner/repo
        m = re.match(r"^(?:https?|ssh|git)://(?:[^@/]+@)?([^/]+)/(.+)$", clean)
    if not m:
        return clean.lower()
    host = m.group(1).split(":")[0].lower()  # scarta la porta: host:22 == host
    return f"{host}/{m.group(2).lower()}"


def _git_root_and_slug(cwd: str) -> tuple[str, str, str]:
    """(toplevel, slug, identity) del repo che contiene cwd.
    Slug: nome dal remote 'origin' (identificativo STABILE, invariante a spostamenti
    della cartella — stessa logica di git_info nel retain worker), fallback basename
    della toplevel. Identity: "host/owner/repo" canonico dallo STESSO remote gia'
    letto qui — deriva da quella lettura, quindi non costa un git in piu' e viaggia
    sulla stessa cache (su MSYS un git subprocess costa ~1.4s: rifarlo a ogni hook
    sarebbe una regressione visibile a ogni prompt).
    ("", "", "") fuori da un repo git (esito noto: cachato) oppure se git non
    risponde — timeout, git assente (esito ignoto: NON cachato, si ritenta)."""
    if cwd in _REPO_CACHE:
        return _REPO_CACHE[cwd]

    # Cache su file persistente tra invocazioni. Vale anche il risultato "vuoto"
    # (cwd fuori da git): evita di ri-tentare il git ogni volta. Le entry nel vecchio
    # formato a 2 campi sollevano ValueError qui sotto -> cache miss -> riscritte.
    cache_f = _repo_cache_file(cwd)
    try:
        if time.time() - os.path.getmtime(cache_f) < _REPO_CACHE_TTL:
            with open(cache_f, encoding="utf-8") as f:
                root, slug, ident = json.load(f)
            _REPO_CACHE[cwd] = (root, slug, ident)
            return root, slug, ident
    except Exception:
        pass

    def _run(args: list[str]) -> str | None:
        """Output di `git <args>`. "" se git ha RISPOSTO senza risultato (exit!=0:
        fuori da un repo, chiave assente) -> esito noto, cachabile. None se git non
        ha potuto rispondere (timeout, git assente) -> esito ignoto, da non cachare."""
        try:
            return subprocess.check_output(
                ["git", *args], cwd=cwd, stderr=subprocess.DEVNULL, timeout=5, text=True
            ).strip()
        except subprocess.CalledProcessError:
            return ""
        except Exception:
            return None

    root = _run(["rev-parse", "--show-toplevel"])
    if root is None:
        # Git muto: non sappiamo dove siamo. Ricadi sul core per QUESTA invocazione
        # ma non cachare, cosi' il prossimo hook ritenta invece di ereditare il buco.
        return "", "", ""
    slug = ""
    ident = ""
    if root:
        remote = _run(["config", "--get", "remote.origin.url"])
        if remote is None:
            # Senza remote lo slug sarebbe basename(root): stabile ma potenzialmente
            # diverso da quello del remote -> bank sbagliato cachato per un'ora.
            return "", "", ""
        if remote:
            base = re.split(r"[/:]", remote.rstrip("/"))[-1]
            slug = base[:-4] if base.endswith(".git") else base
            ident = _remote_identity(remote)
        if not slug:
            slug = os.path.basename(root)
    _REPO_CACHE[cwd] = (root, slug, ident)
    # Persisti su file (best-effort, atomico tmp+rename).
    try:
        os.makedirs(os.path.dirname(cache_f), exist_ok=True)
        tmp = cache_f + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump([root, slug, ident], f)
        os.replace(tmp, cache_f)
    except Exception:
        pass
    return root, slug, ident


def resolve_bank(name: str, cfg: dict, cwd: str | None = None) -> str:
    """Risolve una keyword del blocco bank nel nome reale del bank.
    "core" (o vuoto) -> core_bank; "auto" -> slug del repo corrente; qualsiasi
    altro valore -> nome bank letterale. "auto" ricade sul core in due casi:
      - fuori da un repo git (nessuno slug derivabile)
      - nel repo del plugin stesso (il progetto Trinity E' il progetto core:
        un bank "Trinity" separato spaccherebbe le sue memorie dal core)."""
    name = (name or "").strip()
    core = (cfg.get("bank") or {}).get("core_bank", "")
    if not name or name == "core":
        return core
    if name != "auto":
        return name
    cwd = cwd or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    _, slug, ident = _git_root_and_slug(cwd)
    if not slug:
        return core
    # Il plugin gira come skills-dir via junction/symlink (~/.claude/skills/trinity
    # -> repo): __file__ e' il path del symlink. Confrontare i git toplevel non e'
    # affidabile (git li risolve in modo inconsistente attraverso i symlink MSYS, e
    # realpath di Python su Windows non li segue affatto). Confrontiamo invece
    # l'IDENTITA' canonica del remote origin ("host/owner/repo"), invariante a
    # junction/symlink: se il repo del cwd e quello che ospita il modulo sono lo
    # stesso repo, siamo nel repo del plugin -> core (un bank "Trinity" separato
    # spaccherebbe le sue memorie dal core).
    # NON basta lo slug: un repo QUALSIASI chiamato Trinity (nome comune: su GitHub
    # ce ne sono molti) verrebbe scambiato per il plugin e riverserebbe le sue
    # memorie nel core. L'identita' completa distingue github.com/ichelema/Trinity
    # da chiunque altro.
    here = os.path.dirname(os.path.abspath(__file__))
    plugin_dir = os.path.abspath(os.path.join(here, "..", "..", ".."))
    _, _, plugin_ident = _git_root_and_slug(plugin_dir)
    # Se il plugin non avesse un remote origin, plugin_ident sarebbe "" e la
    # guardia non scatterebbe: dentro il repo del plugin si otterrebbe un bank
    # "Trinity" separato dal core (prima di a75781a si cadeva sul core). Caso
    # teorico — il plugin E' un clone con origin — ma se mai accadesse il
    # sintomo e' questo: memorie del plugin fuori dal core.
    if plugin_ident and ident == plugin_ident:
        return core
    # LIMITE NOTO (scelta deliberata in a75781a): il NOME del bank resta il solo
    # slug, quindi due repo diversi con lo stesso basename (alice/api e bob/api)
    # condividono il bank "api". La collisione non tocca piu' il core (guardia
    # per identita' qui sopra), ma tra progetti omonimi resta. Chiusura vera:
    # nome derivato dall'identita' (es. f"{slug}-{sha256(ident)[:8]}"), che pero'
    # richiede la migrazione una-tantum dei bank esistenti — da pianificare a parte.
    return slug


def bank_url(cfg: dict, bank_name: str) -> str:
    """URL scoped del bank: <api_base>/banks/<nome>.

    Il nome finisce in un segmento di path, quindi va percent-encodato: lo slug non
    e' sotto il nostro controllo (repo senza 'origin' => basename della cartella, che
    puo' avere spazi o accenti). Senza encoding urllib solleva InvalidURL sugli spazi
    e UnicodeEncodeError sugli accenti, e l'errore non emerge da nessuna parte: nel
    recall multi-bank fetch_bank_results lo inghiotte (return [] muto) e il bank di
    progetto sparisce senza traccia; nel retain la POST fallisce e la memoria e' persa.
    safe="" encoda anche '?' e '/': uno slug come "repo.git?token=x" resta un NOME e
    non degenera in query string su un altro endpoint.
    I bank esistenti sono invarianti a quote() (nessun carattere speciale): il fix non
    li rinomina e non richiede migrazione.
    """
    base = (cfg.get("bank") or {}).get("api_base", "").rstrip("/")
    return f"{base}/banks/{urllib.parse.quote(bank_name, safe='')}"


def retain_bank_url(cfg: dict, cwd: str | None = None) -> str:
    """URL del bank di SCRITTURA (da bank.retain_bank). Con api_url esplicito
    (retrocompat) restituisce quello."""
    if cfg.get("_api_url_explicit"):
        return cfg["api_url"]
    name = (cfg.get("bank") or {}).get("retain_bank", "core")
    return bank_url(cfg, resolve_bank(name, cfg, cwd))


def recall_bank_urls(cfg: dict, cwd: str | None = None) -> list[str]:
    """URL dei bank di LETTURA (da bank.recall_banks), risolti e deduplicati
    preservando l'ordine ("auto" puo' coincidere con un nome esplicito o col
    core). Con api_url esplicito (retrocompat) restituisce solo quello."""
    if cfg.get("_api_url_explicit"):
        return [cfg["api_url"]]
    names = (cfg.get("bank") or {}).get("recall_banks") or ["core"]
    out: list[str] = []
    seen: set[str] = set()
    for n in names:
        b = resolve_bank(n, cfg, cwd)
        if b and b not in seen:
            seen.add(b)
            out.append(bank_url(cfg, b))
    return out or [cfg["api_url"]]


def load_config() -> dict:
    cfg = dict(DEFAULTS)

    # 2-3. file JSON a strati (gli ultimi vincono). HS_CONFIG_FILE forza un
    # singolo file; altrimenti: config del PLUGIN (base) -> PROGETTO (override).
    applied: set[str] = set()
    forced = os.environ.get("HS_CONFIG_FILE")
    if forced:
        applied |= _merge_json(cfg, forced)
    else:
        applied |= _merge_json(cfg, _plugin_config_path())
        project_cfg = _project_config_path()
        if project_cfg:
            applied |= _merge_json(cfg, project_cfg, trusted=False)

    # 4. override env (nomi legacy + generico HS_CFG_<CHIAVE>)
    for env_name, key in ENV_OVERRIDES.items():
        val = os.environ.get(env_name)
        if val:
            cfg[key] = _cast(val, DEFAULTS[key])
            applied.add(key)
    for key in DEFAULTS:
        val = os.environ.get("HS_CFG_" + key.upper())
        if val:
            new = _cast(val, DEFAULTS[key])
            if isinstance(cfg.get(key), dict) and isinstance(new, dict):
                cfg[key] = {**cfg[key], **new}
            else:
                cfg[key] = new
            applied.add(key)

    # Retrocompat api_url: se NESSUNA fonte (file o env) lo ha impostato
    # esplicitamente, derivalo dal blocco bank (= URL del CORE): mm-inject,
    # reflect, export e check continuano a leggerlo e devono puntare al core.
    # Se invece e' esplicito, vince su tutto il blocco bank: retain_bank_url e
    # recall_bank_urls lo rispettano e ripristinano il single-bank odierno.
    cfg["_api_url_explicit"] = "api_url" in applied
    if not cfg["_api_url_explicit"]:
        cfg["api_url"] = bank_url(cfg, (cfg.get("bank") or {}).get("core_bank", ""))

    return cfg


if __name__ == "__main__":
    cfg = load_config()
    if len(sys.argv) >= 3 and sys.argv[1] == "--get":
        v = cfg.get(sys.argv[2], "")
        print(json.dumps(v) if isinstance(v, (list, dict)) else v)
    elif len(sys.argv) >= 2 and sys.argv[1] == "--banks":
        # Debug/bash: bank risolti per il cwd corrente (o CLAUDE_PROJECT_DIR).
        print(json.dumps({
            "retain": retain_bank_url(cfg),
            "recall": recall_bank_urls(cfg),
        }, indent=2))
    else:
        print(json.dumps(cfg, indent=2, ensure_ascii=False))
