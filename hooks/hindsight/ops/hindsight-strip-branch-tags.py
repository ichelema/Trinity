#!/usr/bin/env python
"""Migrazione ICH-85: rimuove i tag `branch:*` residui dalle memorie Hindsight.

Contesto: il retain automatico taggava ogni memoria con `branch:<nome-branch>`
(convenzione dismessa: da ICH-85 il codice non lo scrive piu'). Sul DB restano
pero' migliaia di righe gia' taggate — questo script le ripulisce SENZA
cancellare o alterare documenti/memorie: stesso id, stesso content/text/
context/metadata, stessi timestamp, stessi altri tag (solo l'ordine relativo
dei tag superstiti e' preservato, i `branch:*` semplicemente spariscono).

Perche' SQL diretto e non l'endpoint supportato (PATCH
/v1/default/banks/{bank}/documents/{id} con `tags`): quel percorso e' stato
ispezionato e SCARTATO. Il PATCH propaga si' i tag ai memory_units del
documento, ma come effetto collaterale CANCELLA le observation derivate dal
documento, le rimette in coda di consolidation (ri-estrazione LLM) e tocca
`updated_at`. Per una migrazione che deve toccare SOLO la colonna `tags` di
migliaia di righe, senza rigenerare nulla e senza spostare `updated_at`,
l'unica via pulita e' un UPDATE diretto sulla colonna array.

Tabelle toccate (hanno `tags text[]` e possono contenere `branch:*`):
documents, memory_units, invalidated_memory_units. Le tabelle directives e
mental_models hanno anch'esse `tags`, ma nella pratica non hanno mai
contenuto `branch:*` (non passano dal retain automatico): il dry-run le
conta comunque per completezza, non vengono mai scritte.

Flusso consigliato:
  1. hindsight-strip-branch-tags.py --dry-run
       (sola lettura: quante righe, quali bank, quali valori di branch:*)
  2. mise run db-dump
       (backup pg_dump -Fc + sidecar .meta.json col watermark)
  3. hindsight-strip-branch-tags.py --apply --backup <dump>
       (guardia sul backup, conferma interattiva, UPDATE in transazione,
       undo file scritto PRIMA dell'UPDATE, verifica automatica alla fine)
  4. hindsight-strip-branch-tags.py --verify --undo <undo.json>
       (ricontrollo indipendente, in un secondo momento se serve)

Reversibilita': --apply scrive SEMPRE un undo JSON (tags_before per ogni
riga toccata) prima di eseguire l'UPDATE — se l'apply fallisce a meta',
l'undo file esiste comunque e descrive lo stato pre-migrazione delle righe
gia' snapshottate. --revert <undo.json> ripristina `tags = tags_before` riga
per riga (idempotente). Il dump completo di `mise run db-dump` resta la rete
di sicurezza di ultima istanza (restore integrale via `mise run db-restore`).

Modalita' (mutuamente esclusive; --dry-run e' il default se nessuna e' data):
  --dry-run                     sola lettura, scrive un report JSON
  --apply --backup <dump.dump>  applica l'UPDATE (richiede la guardia backup)
  --verify [--undo <file.json>] controlla lo stato attuale del DB
  --revert <undo.json>          ripristina tags_before dall'undo file

ATTENZIONE: questo script scrive sul DB reale solo con --apply o --revert.
Richiede sempre conferma interattiva, salvo --yes.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

try:
    import psycopg2
    import psycopg2.extras
except ImportError:  # pragma: no cover - ambiente senza psycopg2
    psycopg2 = None

MIGRATE_TABLES = ("documents", "memory_units", "invalidated_memory_units")
COMPLETENESS_TABLES = ("directives", "mental_models")
ALL_TABLES = MIGRATE_TABLES + COMPLETENESS_TABLES

HERE = os.path.dirname(os.path.abspath(__file__))
HINDSIGHT_ROOT = os.path.dirname(HERE)  # hooks/hindsight
DEFAULT_REPORT_DIR = os.path.join(HINDSIGHT_ROOT, "data", "migrations")


# --------------------------------------------------------------------------
# Funzioni pure (nessun I/O): testate senza DB in
# test_hindsight_strip_branch_tags.py.
# --------------------------------------------------------------------------

def strip_branch_tags(tags: list[str] | None) -> list[str]:
    """Rimuove i tag che iniziano per 'branch:', preservando l'ordine degli
    altri. Nessun branch:* -> lista invariata (nuova lista, stesso contenuto).
    None o vuota -> lista vuota."""
    if not tags:
        return []
    return [t for t in tags if not t.startswith("branch:")]


def build_dry_run_report(
    watermark: str,
    totals_by_table: dict[str, dict[str, int]],
    interested_rows_by_table: dict[str, list[dict]],
) -> dict:
    """Assembla il report dry-run a partire da dati gia' letti dal DB dal
    chiamante (nessun I/O qui). totals_by_table: tabella -> bank_id -> conteggio
    di TUTTE le righe. interested_rows_by_table: tabella -> righe con almeno
    un tag branch:* (id/bank_id/tags). Nel JSON finiscono anche gli id delle
    righe interessate (interested_ids_by_bank): il dry-run elenca OGNI
    documento/memoria che la migrazione toccherebbe, non solo i conteggi."""
    tables_report: dict[str, dict] = {}
    total_interested = 0
    all_tags: set[str] = set()
    for table, totals in totals_by_table.items():
        rows = interested_rows_by_table.get(table, [])
        interested_by_bank: dict[str, int] = {}
        interested_ids_by_bank: dict[str, list[str]] = {}
        tags_by_bank: dict[str, dict[str, int]] = {}
        for row in rows:
            bank = row["bank_id"]
            interested_by_bank[bank] = interested_by_bank.get(bank, 0) + 1
            interested_ids_by_bank.setdefault(bank, []).append(str(row["id"]))
            for tag in row.get("tags") or []:
                if tag.startswith("branch:"):
                    all_tags.add(tag)
                    bank_tags = tags_by_bank.setdefault(bank, {})
                    bank_tags[tag] = bank_tags.get(tag, 0) + 1
        total_interested += len(rows)
        tables_report[table] = {
            "totals_by_bank": totals,
            "interested_by_bank": interested_by_bank,
            "interested_ids_by_bank": interested_ids_by_bank,
            "branch_tags_by_bank": tags_by_bank,
        }
    return {
        "watermark": watermark,
        "total_interested_rows": total_interested,
        "distinct_branch_tags": sorted(all_tags),
        "tables": tables_report,
    }


def check_backup(
    dump_size,
    meta,
    watermark_db: str,
    allow_stale: bool,
    pg_restore_list,
) -> list[str]:
    """Guardia sul backup PRIMA di qualunque scrittura. Ritorna la lista dei
    problemi trovati (vuota = tutto ok). Pura rispetto all'I/O sui file: il
    chiamante ha gia' letto dump_size (None se il file non esiste) e meta
    (dict del .meta.json, None se assente/illeggibile); pg_restore_list e' un
    callable SENZA argomenti iniettato dal chiamante (nei test un finto, nel
    main un vero subprocess) che esegue `pg_restore --list <dump>` e ritorna
    (returncode, output testuale)."""
    problems: list[str] = []
    if dump_size is None:
        problems.append("il file di backup non esiste")
        return problems
    if dump_size <= 0:
        problems.append("il file di backup e' vuoto (size 0)")
        return problems
    if meta is None:
        problems.append("il file .meta.json del backup non esiste o non e' leggibile")
        return problems
    if "max_write_at" not in meta:
        problems.append("il .meta.json non contiene la chiave 'max_write_at'")
        return problems

    rc, out = pg_restore_list()
    if rc != 0:
        problems.append(f"pg_restore --list ha fallito (exit {rc}): {out.strip()}")
        return problems
    if "documents" not in out:
        problems.append("pg_restore --list non elenca la tabella 'documents'")
    if "memory_units" not in out:
        problems.append("pg_restore --list non elenca la tabella 'memory_units'")
    if problems:
        return problems

    backup_wm = meta["max_write_at"] or ""
    # Confronto lessicografico su timestamp ISO (stesso fuso, come hs-db-lib.sh):
    # se il DB ha scritture DOPO il backup, il backup non le copre.
    if watermark_db and watermark_db > backup_wm and not allow_stale:
        problems.append(
            "il DB ha scritture piu' recenti del backup "
            f"(DB: {watermark_db}, backup: {backup_wm}) - rilancia 'mise run db-dump', "
            "oppure passa --allow-stale-backup se sai cosa stai facendo"
        )
    return problems


def verify_snapshot(
    snapshot_rows: list[dict],
    current_rows: dict[tuple, dict],
    snapshot_totals: dict[str, dict[str, int]],
    current_totals: dict[str, dict[str, int]],
) -> list[str]:
    """Confronta lo snapshot pre-apply con lo stato attuale del DB. Ritorna la
    lista dei problemi trovati (vuota = tutto ok).

    snapshot_rows: [{"table", "id", "bank_id", "tags_before", "fingerprint"}].
    current_rows: (table, id) -> {"tags", "fingerprint"} letti ORA dal DB
    (chiave assente = riga non trovata). snapshot_totals/current_totals:
    tabella -> bank_id -> conteggio di righe. Pura: non sa (ne' le importa)
    se il chiamante ha limitato il conteggio a created_at <= watermark — lo
    fa fetch_current_state, per ignorare righe scritte da altri processi
    dopo lo snapshot senza nascondere una riga vecchia cancellata."""
    problems: list[str] = []
    for row in snapshot_rows:
        key = (row["table"], row["id"])
        cur = current_rows.get(key)
        if cur is None:
            problems.append(f"riga mancante: {row['table']}/{row['id']}")
            continue
        if cur["fingerprint"] != row["fingerprint"]:
            problems.append(
                f"la riga {row['table']}/{row['id']} e' cambiata oltre ai tag "
                "(fingerprint diverso)"
            )
            continue
        expected_tags = strip_branch_tags(row["tags_before"])
        if cur["tags"] != expected_tags:
            problems.append(
                f"tags inattesi per {row['table']}/{row['id']}: "
                f"atteso {expected_tags}, trovato {cur['tags']}"
            )
    for table, banks in snapshot_totals.items():
        cur_banks = current_totals.get(table, {})
        for bank_id, count in banks.items():
            cur_count = cur_banks.get(bank_id)
            if cur_count != count:
                problems.append(
                    f"conteggio righe cambiato per {table}/{bank_id}: "
                    f"atteso {count}, trovato {cur_count}"
                )
        for bank_id in cur_banks:
            if bank_id not in banks:
                problems.append(
                    f"nuovo bank_id comparso in {table} dopo lo snapshot: {bank_id}"
                )
    return problems


# --------------------------------------------------------------------------
# Piccole utility (I/O minimo, nessuna logica di dominio)
# --------------------------------------------------------------------------

def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_report(report_dir: str, kind: str, data: dict) -> str:
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, f"strip-branch-tags-{kind}-{now_stamp()}.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def confirm(message: str) -> bool:
    """Conferma interattiva. Senza terminale (stdin non tty) rifiuta SEMPRE:
    --yes e' l'unico modo per procedere in modo non interattivo (uno stdin
    pipe/redirect non conta come consenso)."""
    if not sys.stdin.isatty():
        return False
    try:
        resp = input(message)
    except EOFError:
        return False
    return resp.strip().lower() in ("y", "yes")


def _natural_version_key(bin_dir: str):
    version = os.path.basename(os.path.dirname(bin_dir))
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", version)]


def resolve_pgbin() -> str | None:
    """Directory bin di pg0. Ordine: HS_PGBIN (usato cosi' com'e') -> ricerca
    sotto USERPROFILE, poi HOMEDRIVE+HOMEPATH, poi HOME, in
    .pg0/installation/<versione>/bin, prendendo la versione piu' alta (sort
    naturale) sulla prima base che produce risultati. None se non si trova
    nulla — il chiamante stampa un errore chiaro."""
    env_bin = os.environ.get("HS_PGBIN")
    if env_bin:
        return env_bin
    bases = []
    if os.environ.get("USERPROFILE"):
        bases.append(os.environ["USERPROFILE"])
    if os.environ.get("HOMEDRIVE") and os.environ.get("HOMEPATH"):
        bases.append(os.environ["HOMEDRIVE"] + os.environ["HOMEPATH"])
    if os.environ.get("HOME"):
        bases.append(os.environ["HOME"])
    for base in bases:
        dirs = glob.glob(os.path.join(base, ".pg0", "installation", "*", "bin"))
        if dirs:
            dirs.sort(key=_natural_version_key)
            return dirs[-1]
    return None


def run_pg_restore_list(pgbin: str | None, dump_path: str):
    """(returncode, output) di `pg_restore --list <dump_path>`. returncode=1 e
    messaggio esplicativo se pg_restore non si trova (nessuna eccezione)."""
    if not pgbin:
        return 1, (
            "pg_restore non trovato: binari Postgres pg0 non individuati. "
            "Imposta HS_PGBIN o verifica l'installazione di pg0."
        )
    exe = "pg_restore.exe" if os.name == "nt" else "pg_restore"
    pg_restore = os.path.join(pgbin, exe)
    if not os.path.isfile(pg_restore):
        return 1, f"pg_restore non trovato in {pgbin}"
    try:
        proc = subprocess.run(
            [pg_restore, "--list", dump_path],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as e:  # noqa: BLE001 - qualunque fallimento e' un "problema" da riportare
        return 1, f"pg_restore --list fallito: {e}"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


# --------------------------------------------------------------------------
# Adapter DB: un metodo esplicito per ogni operazione. I test lo sostituiscono
# con un finto in-memory con la stessa interfaccia.
# --------------------------------------------------------------------------

def db_params() -> dict:
    return dict(
        host=os.environ.get("HS_PGHOST", "127.0.0.1"),
        port=int(os.environ.get("HS_PGPORT", "5432")),
        user=os.environ.get("HS_PGUSER", "hindsight"),
        password=os.environ.get("HS_PGPASSWORD", "hindsight"),
        dbname=os.environ.get("HS_PGDATABASE", "hindsight"),
    )


def open_conn(readonly: bool = False):
    conn = psycopg2.connect(**db_params())
    conn.autocommit = False
    if readonly:
        cur = conn.cursor()
        cur.execute("SET TRANSACTION READ ONLY")
        cur.close()
    return conn


class HsDbAdapter:
    """Wrapper psycopg2 minimale sulle query di questo script."""

    def __init__(self, conn):
        self.conn = conn

    def _cursor(self):
        return self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def fetch_watermark(self) -> str:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT COALESCE(GREATEST(
                (SELECT max(GREATEST(created_at, updated_at)) FROM documents),
                (SELECT max(GREATEST(created_at, updated_at)) FROM memory_units),
                (SELECT max(GREATEST(created_at, updated_at)) FROM banks),
                (SELECT max(GREATEST(created_at, updated_at)) FROM directives),
                (SELECT max(GREATEST(created_at, updated_at, invalidated_at))
                 FROM invalidated_memory_units)
            )::text, '')
        """)
        row = cur.fetchone()
        cur.close()
        return row[0] or ""

    def fetch_totals(self, table: str) -> dict[str, int]:
        assert table in ALL_TABLES, table
        cur = self.conn.cursor()
        cur.execute(f"SELECT bank_id, count(*) FROM {table} GROUP BY bank_id")
        out = {bank_id: n for bank_id, n in cur.fetchall()}
        cur.close()
        return out

    def fetch_totals_until(self, table: str, watermark: str) -> dict[str, int]:
        """Come fetch_totals, ma conta solo le righe con created_at <= watermark
        (il testo ISO prodotto da fetch_watermark, es. '2026-08-17
        00:01:44.1602+00' — il cast a timestamptz lo accetta cosi' com'e').
        Serve a confrontare 'prima' e 'dopo' la migrazione ignorando righe
        NUOVE scritte nel frattempo da altri processi (retain di altre
        sessioni, observation della consolidation, un bank creato da un
        benchmark): senza questo filtro il conteggio totale cresce per
        ragioni che non c'entrano con la migrazione e verify_snapshot
        segnalerebbe falsi allarmi ("conteggio righe cambiato", "nuovo
        bank_id comparso"). Una riga VECCHIA (created_at <= watermark) che
        sparisce invece fa scendere il conteggio anche con questo filtro,
        quindi resta rilevata. watermark vuoto (DB senza scritture, primo
        avvio) -> nessun filtro, equivalente a fetch_totals."""
        assert table in MIGRATE_TABLES, table
        if not watermark:
            return self.fetch_totals(table)
        cur = self.conn.cursor()
        cur.execute(
            f"SELECT bank_id, count(*) FROM {table} "
            "WHERE created_at <= %s::timestamptz GROUP BY bank_id",
            (watermark,),
        )
        out = {bank_id: n for bank_id, n in cur.fetchall()}
        cur.close()
        return out

    def fetch_interested_rows(self, table: str) -> list[dict]:
        """Righe con almeno un tag branch:*: id, bank_id, tags (nessun fingerprint,
        serve solo al report dry-run)."""
        assert table in ALL_TABLES, table
        cur = self._cursor()
        cur.execute(f"""
            SELECT id::text AS id, bank_id, tags
            FROM {table}
            WHERE EXISTS (SELECT 1 FROM unnest(tags) x WHERE x LIKE 'branch:%%')
        """)
        out = [dict(r) for r in cur.fetchall()]
        cur.close()
        return out

    def fetch_interested_count(self, table: str) -> int:
        assert table in ALL_TABLES, table
        cur = self.conn.cursor()
        cur.execute(f"""
            SELECT count(*) FROM {table}
            WHERE EXISTS (SELECT 1 FROM unnest(tags) x WHERE x LIKE 'branch:%%')
        """)
        n = cur.fetchone()[0]
        cur.close()
        return n

    def snapshot_rows(self, table: str) -> list[dict]:
        """Righe interessate con fingerprint (tutto tranne tags), per l'undo
        file e la verifica post-apply."""
        assert table in MIGRATE_TABLES, table
        cur = self._cursor()
        cur.execute(f"""
            SELECT id::text AS id, bank_id, tags AS tags_before,
                   md5((to_jsonb(t) - 'tags')::text) AS fingerprint
            FROM {table} t
            WHERE EXISTS (SELECT 1 FROM unnest(tags) x WHERE x LIKE 'branch:%%')
        """)
        out = [dict(r) for r in cur.fetchall()]
        cur.close()
        return out

    def update_table(self, table: str) -> int:
        """UPDATE della sola colonna tags: rimuove i branch:*, preserva
        l'ordine degli altri (WITH ORDINALITY), non tocca nient'altro (niente
        updated_at). Ritorna il numero di righe modificate."""
        assert table in MIGRATE_TABLES, table
        cur = self.conn.cursor()
        cur.execute(f"""
            UPDATE {table}
            SET tags = ARRAY(
                SELECT x FROM unnest(tags) WITH ORDINALITY AS u(x, n)
                WHERE x NOT LIKE 'branch:%%'
                ORDER BY n
            )
            WHERE EXISTS (SELECT 1 FROM unnest(tags) x WHERE x LIKE 'branch:%%')
        """)
        n = cur.rowcount
        cur.close()
        return n

    def fetch_rows_by_ids(self, table: str, ids: list[str]) -> dict[str, dict]:
        """id -> {bank_id, tags, fingerprint} per la verifica post-apply. Chiavi
        assenti nel dict di ritorno = righe non trovate (cancellate?)."""
        assert table in MIGRATE_TABLES, table
        if not ids:
            return {}
        cur = self._cursor()
        cur.execute(f"""
            SELECT id::text AS id, bank_id, tags,
                   md5((to_jsonb(t) - 'tags')::text) AS fingerprint
            FROM {table} t
            WHERE id::text = ANY(%s)
        """, (list(ids),))
        out = {r["id"]: {"bank_id": r["bank_id"], "tags": r["tags"],
                         "fingerprint": r["fingerprint"]} for r in cur.fetchall()}
        cur.close()
        return out

    def revert_rows(self, table: str, rows: list[dict]) -> tuple[int, int]:
        """Ripristina tags = tags_before riga per riga. Ritorna (ripristinate,
        mancanti). Idempotente: ripetuto ripristina di nuovo lo stesso valore."""
        assert table in MIGRATE_TABLES, table
        restored = 0
        missing = 0
        cur = self.conn.cursor()
        for row in rows:
            cur.execute(
                f"UPDATE {table} SET tags = %s WHERE id::text = %s AND bank_id = %s",
                (row["tags_before"], row["id"], row["bank_id"]),
            )
            if cur.rowcount == 1:
                restored += 1
            else:
                missing += 1
        cur.close()
        return restored, missing


def fetch_current_state(adapter: HsDbAdapter, snapshot_rows: list[dict], tables, watermark: str = ""):
    """(current_rows, current_totals) per verify_snapshot, letti ORA dal DB.
    I totali sono limitati a created_at <= watermark (fetch_totals_until):
    senza questo filtro righe scritte DOPO lo snapshot da altri processi
    (retain di altre sessioni, consolidation, un bank creato da un
    benchmark) farebbero scattare falsi allarmi in verify_snapshot. watermark
    vuoto -> nessun filtro (comportamento invariato)."""
    ids_by_table: dict[str, list[str]] = {}
    for row in snapshot_rows:
        ids_by_table.setdefault(row["table"], []).append(row["id"])
    current_rows: dict[tuple, dict] = {}
    for table, ids in ids_by_table.items():
        for rid, data in adapter.fetch_rows_by_ids(table, ids).items():
            current_rows[(table, rid)] = data
    current_totals = {table: adapter.fetch_totals_until(table, watermark) for table in tables}
    return current_rows, current_totals


# --------------------------------------------------------------------------
# Comandi
# --------------------------------------------------------------------------

def print_dry_run_summary(report: dict, out_path: str) -> None:
    print(f"[strip-branch-tags] watermark DB: {report['watermark'] or '(nessuna scrittura)'}")
    print(f"[strip-branch-tags] righe con tag branch:*: {report['total_interested_rows']}")
    print(f"[strip-branch-tags] valori branch:* distinti: {len(report['distinct_branch_tags'])}")
    for table in ALL_TABLES:
        info = report["tables"].get(table)
        if not info:
            continue
        interested = sum(info["interested_by_bank"].values())
        totals = sum(info["totals_by_bank"].values())
        print(f"  {table}: {interested} righe interessate su {totals} totali")
        for bank, n in sorted(info["interested_by_bank"].items()):
            print(f"    bank={bank}: {n} righe")
            for tag, count in sorted(info["branch_tags_by_bank"].get(bank, {}).items(),
                                      key=lambda kv: -kv[1]):
                print(f"      {tag}: {count}")
    print(f"[strip-branch-tags] report scritto: {out_path}")
    if report["total_interested_rows"] == 0:
        print("[strip-branch-tags] nessuna riga interessata: niente da migrare")


def cmd_dry_run(args) -> int:
    conn = open_conn(readonly=True)
    try:
        adapter = HsDbAdapter(conn)
        totals_by_table = {t: adapter.fetch_totals(t) for t in ALL_TABLES}
        interested_rows_by_table = {t: adapter.fetch_interested_rows(t) for t in ALL_TABLES}
        watermark = adapter.fetch_watermark()
        conn.rollback()
    finally:
        conn.close()

    report = build_dry_run_report(watermark, totals_by_table, interested_rows_by_table)
    report["generated_at"] = now_iso()
    out_path = write_report(args.report_dir, "dryrun", report)
    print_dry_run_summary(report, out_path)
    return 0


def cmd_apply(args) -> int:
    # Fase 1 (sola lettura): idempotenza PRIMA della guardia sul backup.
    conn = open_conn(readonly=True)
    try:
        adapter = HsDbAdapter(conn)
        counts = {t: adapter.fetch_interested_count(t) for t in MIGRATE_TABLES}
        watermark_db = adapter.fetch_watermark()
        conn.rollback()
    finally:
        conn.close()
    total = sum(counts.values())
    if total == 0:
        print("[strip-branch-tags] nessuna riga da migrare (nessun tag branch:* trovato)")
        return 0

    # Fase 2: guardia sul backup (nessuna scrittura, nessuna nuova connessione DB).
    dump_size = os.path.getsize(args.backup) if os.path.isfile(args.backup) else None
    meta = load_json(args.backup + ".meta.json")
    pgbin = resolve_pgbin()
    problems = check_backup(
        dump_size, meta, watermark_db, args.allow_stale_backup,
        lambda: run_pg_restore_list(pgbin, args.backup),
    )
    if problems:
        print("[strip-branch-tags] RIFIUTATO: guardia sul backup fallita:")
        for p in problems:
            print(f"  - {p}")
        return 2

    # Fase 3: conferma interattiva.
    if not args.yes and not confirm(f"scrivo {total} righe, continuo? [y/N] "):
        print("[strip-branch-tags] annullato (nessuna conferma)")
        return 2

    # Fase 4 (sola lettura): snapshot + undo file PRIMA di qualunque UPDATE.
    conn = open_conn(readonly=True)
    try:
        adapter = HsDbAdapter(conn)
        snapshot_rows: list[dict] = []
        totals_before: dict[str, dict[str, int]] = {}
        for t in MIGRATE_TABLES:
            for row in adapter.snapshot_rows(t):
                snapshot_rows.append({"table": t, **row})
            # Scoperto al watermark: righe scritte da altri processi PRIMA che
            # l'undo venga salvato ma dopo il conteggio di Fase 1 non devono
            # entrare nel confronto "prima/dopo" (vedi fetch_current_state).
            totals_before[t] = adapter.fetch_totals_until(t, watermark_db)
        conn.rollback()
    finally:
        conn.close()

    undo = {
        "created_at": now_iso(),
        "watermark_before_apply": watermark_db,
        "backup": os.path.abspath(args.backup),
        "totals_before": totals_before,
        "rows": snapshot_rows,
    }
    undo_path = write_report(args.report_dir, "undo", undo)
    print(f"[strip-branch-tags] undo file scritto ({len(snapshot_rows)} righe): {undo_path}")

    # Fase 5: UPDATE in una transazione.
    conn = open_conn(readonly=False)
    try:
        adapter = HsDbAdapter(conn)
        updated = {}
        try:
            for t in MIGRATE_TABLES:
                updated[t] = adapter.update_table(t)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()
    print("[strip-branch-tags] UPDATE eseguito: " +
          ", ".join(f"{t}={n}" for t, n in updated.items()))

    # Fase 6 (sola lettura): verifica automatica.
    conn = open_conn(readonly=True)
    try:
        adapter = HsDbAdapter(conn)
        current_rows, current_totals = fetch_current_state(
            adapter, snapshot_rows, MIGRATE_TABLES, watermark_db
        )
        problems = verify_snapshot(snapshot_rows, current_rows, totals_before, current_totals)
        conn.rollback()
    finally:
        conn.close()
    if problems:
        print("[strip-branch-tags] VERIFICA FALLITA dopo l'apply:")
        for p in problems:
            print(f"  - {p}")
        print(f"[strip-branch-tags] usa l'undo file per ripristinare: {undo_path}")
        return 1
    print(f"[strip-branch-tags] OK: {len(snapshot_rows)} righe migrate e verificate")
    print(f"[strip-branch-tags] undo file (per --revert, se servisse): {undo_path}")
    return 0


def cmd_verify(args) -> int:
    conn = open_conn(readonly=True)
    try:
        adapter = HsDbAdapter(conn)
        remaining = {t: adapter.fetch_interested_count(t) for t in MIGRATE_TABLES}
        completeness = {t: adapter.fetch_interested_count(t) for t in COMPLETENESS_TABLES}

        problems = [f"{t}: {n} righe hanno ancora tag branch:*"
                    for t, n in remaining.items() if n > 0]

        snapshot = None
        if args.undo:
            snapshot = load_json(args.undo)
            if snapshot is None:
                print(f"[strip-branch-tags] ERRORE: undo file illeggibile: {args.undo}")
                return 1
            tables_in_snapshot = list(snapshot.get("totals_before", {}).keys()) or list(MIGRATE_TABLES)
            # Stesso watermark salvato nell'undo al momento dell'apply: righe
            # scritte DOPO (altre sessioni, consolidation, un bank di
            # benchmark) non devono contare nel confronto dei totali, anche
            # se questa verify gira molto piu' tardi.
            snapshot_watermark = snapshot.get("watermark_before_apply") or ""
            current_rows, current_totals = fetch_current_state(
                adapter, snapshot.get("rows", []), tables_in_snapshot, snapshot_watermark
            )
            problems += verify_snapshot(
                snapshot.get("rows", []), current_rows,
                snapshot.get("totals_before", {}), current_totals,
            )
        conn.rollback()
    finally:
        conn.close()

    print("[strip-branch-tags] righe ancora con branch:* per tabella:")
    for t, n in remaining.items():
        print(f"  {t}: {n}")
    print("[strip-branch-tags] tabelle di completezza (atteso 0):")
    for t, n in completeness.items():
        print(f"  {t}: {n}")
    if snapshot is not None:
        print(f"[strip-branch-tags] righe dello snapshot verificate: {len(snapshot.get('rows', []))}")
    if problems:
        print(f"[strip-branch-tags] VERIFICA FALLITA: {len(problems)} problema/i")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("[strip-branch-tags] verifica OK: nessun problema trovato")
    return 0


def cmd_revert(args) -> int:
    undo = load_json(args.revert)
    if undo is None:
        print(f"[strip-branch-tags] ERRORE: undo file illeggibile: {args.revert}")
        return 1
    rows = undo.get("rows", [])
    if not rows:
        print("[strip-branch-tags] undo file senza righe: nulla da ripristinare")
        return 0
    if not args.yes and not confirm(f"ripristino {len(rows)} righe da {args.revert}, continuo? [y/N] "):
        print("[strip-branch-tags] annullato (nessuna conferma)")
        return 2

    rows_by_table: dict[str, list[dict]] = {}
    for row in rows:
        rows_by_table.setdefault(row["table"], []).append(row)

    conn = open_conn(readonly=False)
    try:
        adapter = HsDbAdapter(conn)
        restored_total = 0
        missing_total = 0
        try:
            for t, trows in rows_by_table.items():
                restored, missing = adapter.revert_rows(t, trows)
                restored_total += restored
                missing_total += missing
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()
    print(f"[strip-branch-tags] revert completato: {restored_total} righe ripristinate, "
          f"{missing_total} mancanti (gia' cancellate dal DB)")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ICH-85: rimuove i tag branch:* da documents/memory_units/"
                     "invalidated_memory_units nel DB Hindsight, senza toccare "
                     "nient'altro. Vedi la docstring del modulo per il flusso "
                     "consigliato (--dry-run -> mise run db-dump -> --apply -> "
                     "--verify).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                       help="sola lettura: report su cosa verrebbe cambiato (default)")
    mode.add_argument("--apply", action="store_true",
                       help="applica l'UPDATE (richiede --backup)")
    mode.add_argument("--verify", action="store_true",
                       help="verifica lo stato attuale del DB (opzionale --undo)")
    mode.add_argument("--revert", metavar="UNDO_JSON",
                       help="ripristina tags_before dall'undo file indicato")
    parser.add_argument("--backup", metavar="DUMP_PATH",
                         help="dump di sicurezza gia' fatto con 'mise run db-dump' "
                              "(richiesto con --apply)")
    parser.add_argument("--undo", metavar="UNDO_JSON",
                         help="undo file da usare con --verify per un controllo "
                              "riga-per-riga (oltre al controllo 'zero branch:* rimasti')")
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR,
                         help=f"cartella dei report (default: {DEFAULT_REPORT_DIR})")
    parser.add_argument("--allow-stale-backup", action="store_true",
                         help="ignora un backup piu' vecchio dell'ultima scrittura nel DB "
                              "(--apply)")
    parser.add_argument("--yes", action="store_true",
                         help="non chiedere conferma interattiva (--apply/--revert)")
    args = parser.parse_args(argv)

    if not (args.dry_run or args.apply or args.verify or args.revert):
        args.dry_run = True
    if args.apply and not args.backup:
        parser.error("--apply richiede --backup <path.dump>")
    if args.backup and not args.apply:
        parser.error("--backup e' valido solo con --apply")
    if args.undo and not args.verify:
        parser.error("--undo e' valido solo con --verify")
    if args.allow_stale_backup and not args.apply:
        parser.error("--allow-stale-backup e' valido solo con --apply")
    return args


def main() -> int:
    args = parse_args()
    if psycopg2 is None:
        print("[strip-branch-tags] ERRORE: modulo psycopg2 non disponibile", file=sys.stderr)
        return 1
    try:
        if args.apply:
            return cmd_apply(args)
        if args.verify:
            return cmd_verify(args)
        if args.revert:
            return cmd_revert(args)
        return cmd_dry_run(args)
    except psycopg2.OperationalError as e:
        print(f"[strip-branch-tags] ERRORE: database non raggiungibile: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
