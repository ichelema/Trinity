# Release del plugin Trinity

Il repository del plugin è in `$TRINITY_PLUGIN_DIR`.

- **Versione.** Sta in `.claude-plugin/plugin.json` e deve combaciare con il tag `vX.Y.Z`.
- **Bump.** `mise run release <X.Y.Z>` aggiorna `plugin.json`, crea il commit
  `chore(plugin): bump X.Y.Z` e il tag annotato `vX.Y.Z`, tutto in locale. Il push resta al passo 6
  del flusso.
- **Changelog.** Se il repository non ha `CHANGELOG.md` (oggi Trinity non lo ha), salta il passo 4 e
  la voce del changelog nella checklist: le release precedenti sono solo bump.
- **SemVer.** L'API pubblica su cui giudicare la versione sono gli hook, i comandi, le skill, i tool
  MCP e lo schema di `hindsight.config.json`.
- **Dopo il bump.** Claude Code rilegge il manifest solo al riavvio.
