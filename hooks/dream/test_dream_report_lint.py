"""Test del lint del report di /trinity:dream (senza server, senza file)."""
import textwrap
import unittest

import dream_report_lint as L


TEMPLATE = textwrap.dedent("""\
    # Dream report — 2026-10-07

    - Generato: 2026-10-07T03:00:00+02:00
    - Azioni proposte: {tot} (obsolete: {obs}, aggiornamenti: {agg}, nuove: {nuo}, policy: {pol}, mental model: {mmc})

    ## Obsolete
    {obsolete}
    ## Da aggiornare

    ## Nuove da salvare
    {nuove}
    ## Violazioni policy MEMORY.md
    {extra}
    ## Mental model
    {mm}""")

MM_OK = """\
- [x] **A3** · mm-refresh · rigenera i mental model
  - Pre-flaggata: necessaria se approvi qualunque azione hs-*.
"""


def report(header=(3, 1, 0, 1, 0, 1), obsolete="", nuove="", mm=True, extra=""):
    tot, obs, agg, nuo, pol, mmc = header
    return TEMPLATE.format(tot=tot, obs=obs, agg=agg, nuo=nuo, pol=pol, mmc=mmc,
                           obsolete=obsolete, nuove=nuove, extra=extra,
                           mm=MM_OK if mm else "")


A1_OK = """\
- [ ] **A1** · hs-invalidate · bank `trinity-project` · fatto `ce2d553c`
  - Cosa fa: ritira un fatto sull'account GitHub vecchio
  - Attuale: "i fork si creano sotto sphynx79"
  - Motivo: daily 2026-07-31 §"Migrazione GitHub" — "non è più sphynx79"
  - Verifica: `git remote -v` → `ichelema/Trinity.git` ✓
"""
A2_OK = """\
- [ ] **A2** · hs-retain · bank `trinity-project`
  - Cosa fa: salva il workaround per i lock di SmartGit
  - Proposta (testo esatto): "SmartGit tiene index.lock ..."
  - Tags: claude-code, repo:Trinity
  - Fonte: daily 2026-10-07 §"Lock di git da SmartGit"
  - Verifica: solo daily (fatto non verificabile sul campo)
"""


class LintTest(unittest.TestCase):
    def test_report_valido_passa_in_audit(self):
        self.assertEqual(L.lint(report(obsolete=A1_OK, nuove=A2_OK)), [])

    def test_memoria_allineata_passa(self):
        txt = "# Dream report — 2026-10-07\n\nMemoria allineata, nessuna azione proposta.\n"
        self.assertEqual(L.lint(txt), [])
        self.assertEqual(L.lint(txt, apply_mode=True), [])

    def test_id_duplicato_fallisce(self):
        dup = A2_OK.replace("**A2**", "**A1**")
        errs = L.lint(report(obsolete=A1_OK, nuove=dup))
        self.assertTrue(any("ID non sequenziali" in e for e in errs), errs)

    def test_contatore_sbagliato_fallisce(self):
        errs = L.lint(report(header=(3, 2, 0, 0, 0, 1), obsolete=A1_OK, nuove=A2_OK))
        self.assertTrue(any("contatore 'obsolete'" in e for e in errs), errs)
        self.assertTrue(any("contatore 'nuove'" in e for e in errs), errs)

    def test_totale_sbagliato_fallisce(self):
        errs = L.lint(report(header=(4, 1, 0, 1, 0, 1), obsolete=A1_OK, nuove=A2_OK))
        self.assertTrue(any("totale dichiarato 4" in e for e in errs), errs)

    def test_verifica_mancante_fallisce(self):
        senza = "\n".join(l for l in A1_OK.splitlines() if "Verifica" not in l) + "\n"
        errs = L.lint(report(obsolete=senza, nuove=A2_OK))
        self.assertIn("A1: manca 'Verifica:'", errs)

    def test_cosa_fa_mancante_fallisce(self):
        senza = "\n".join(l for l in A2_OK.splitlines() if "Cosa fa" not in l) + "\n"
        errs = L.lint(report(obsolete=A1_OK, nuove=senza))
        self.assertIn("A2: manca 'Cosa fa:'", errs)

    def test_preflag_in_audit_fallisce_ma_passa_in_apply(self):
        flag = A1_OK.replace("- [ ] **A1**", "- [x] **A1**")
        errs = L.lint(report(obsolete=flag, nuove=A2_OK))
        self.assertTrue(any("A1: pre-flaggata" in e for e in errs), errs)
        self.assertEqual(L.lint(report(obsolete=flag, nuove=A2_OK), apply_mode=True), [])

    def test_apply_rifiuta_invalidate_con_sola_daily(self):
        flag = A1_OK.replace("- [ ] **A1**", "- [x] **A1**").replace(
            "Verifica: `git remote -v` → `ichelema/Trinity.git` ✓",
            "Verifica: solo daily (fatto non verificabile sul campo)")
        errs = L.lint(report(obsolete=flag, nuove=A2_OK), apply_mode=True)
        self.assertTrue(any("A1: hs-invalidate flaggata senza verifica" in e for e in errs), errs)

    def test_apply_accetta_retain_con_sola_daily(self):
        # hs-retain non altera memorie esistenti: "solo daily" e' ammesso.
        flag = A2_OK.replace("- [ ] **A2**", "- [x] **A2**")
        self.assertEqual(L.lint(report(obsolete=A1_OK, nuove=flag), apply_mode=True), [])

    def test_apply_ignora_azioni_gia_fatte(self):
        done = A1_OK.replace("- [ ] **A1** · hs-invalidate · bank `trinity-project` · fatto `ce2d553c`",
                             "- [x] **A1** · hs-invalidate · bank `trinity-project` · fatto `ce2d553c` → FATTO 2026-10-07T03:10+02:00"
                             ).replace("Verifica: `git remote -v` → `ichelema/Trinity.git` ✓",
                                       "Verifica: solo daily")
        self.assertEqual(L.lint(report(obsolete=done, nuove=A2_OK), apply_mode=True), [])

    def test_hs_senza_bank_e_file_senza_path(self):
        no_bank = A1_OK.replace(" · bank `trinity-project`", "")
        file_bad = textwrap.dedent("""\
        - [ ] **A2** · file-delete · `memoria.md`
          - Cosa fa: cancella un file
          - Motivo: policy
          - Verifica: letto il file
        """)
        errs = L.lint(report(obsolete=no_bank, nuove=file_bad))
        self.assertIn("A1: azione Hindsight senza bank di destinazione", errs)
        self.assertIn("A2: azione file senza path completo", errs)


if __name__ == "__main__":
    unittest.main()
