// pi-sync: sostituzioni ancorate per file, applicate dopo le regole globali di pi-sync.mjs.
//
// Chiave: percorso del sorgente Trinity. Ogni `find` è scritto com'è DOPO le regole globali (per
// esempio `ReviewerOpus`, non `trinity:reviewer`) e deve comparire esattamente una volta. Se
// Trinity riscrive quel punto il generatore si ferma: aggiorna l'ancora qui. Tieni le ancore
// corte: tutto quello che non sta in un'ancora segue il sorgente da solo.
//
// Rese pi usate qui:
// - shell: in pi ogni comando parte in una shell nuova, quindi `cd "<dir>" && <comando>`;
// - Agent: il modello si sceglie scegliendo l'agente; chi aspetta il risultato passa
//   `run_in_background: false`;
// - permission-gate: `rm -r` passa solo come comando a sé su un percorso scritto per esteso
//   sotto `$HOME/.pi/agent/tmp`, quindi l'appoggio dei reviewer sta lì e non nel worktree.

// Rimando di 2_work-simplify e 2_work-verify alla sezione di 2_work-issue sul worktree.
const WORKTREE_COMMANDS = {
  find: `Dopo le verifiche entra nel worktree e, quando restituisci il controllo, escine come in
\`/2_work-issue\` («Entrata e uscita dal worktree»).`,
  replace: `Quando un comando deve girare dentro il worktree scrivi \`cd "<wt-path>" && <comando>\` nello stesso
comando: in pi ogni comando parte in una shell nuova. Quando restituisci il controllo ferma i
processi in background avviati nel worktree, come in \`/2_work-issue\` («Comandi dentro il worktree»).`,
};

export const PATCHES = {
  "commands/workflow/2_work-issue.md": [
    {
      find: `### Entrata e uscita dal worktree

Dopo le verifiche qui sotto entra nel worktree con un comando a sé: \`cd "<wt-path>"\`. Così la
statusline mostra il worktree; i comandi restano comunque con \`git -C\` e path assoluti.

Ogni volta che restituisci il controllo (fine lavoro, domanda all'utente, errore che ti ferma),
ferma i processi in background avviati nel worktree, poi esci con un comando a sé:

\`\`\`bash
repo_root="$(git -C "<wt-path>" rev-parse --path-format=absolute --git-common-dir)"; cd "\${repo_root%/.git}" && pwd
\`\`\`

Su Windows git non cancella una directory che fa da cwd alla shell (\`Device or resource busy\` allo
step 5).`,
      replace: `### Comandi dentro il worktree

In pi ogni comando parte in una shell nuova, dalla directory della sessione: un \`cd\` dato come
comando a sé non vale per il comando successivo. Quando un comando deve girare dentro il worktree
scrivi \`cd "<wt-path>" && <comando>\` nello stesso comando, ogni volta. I comandi Git restano con
\`git -C\`; per leggere, modificare e scrivere file usa sempre path assoluti sotto \`<wt-path>\`.

Ogni volta che restituisci il controllo (fine lavoro, domanda all'utente, errore che ti ferma),
ferma i processi in background avviati nel worktree: su Windows git non cancella una directory che
fa da cwd a un processo (\`Device or resource busy\` allo step 5).`,
    },
    {
      find: `(se la
sessione è già Sonnet, fallo tu: FastWorker è lo stesso modello).`,
      replace: `(se la
sessione gira già sul modello di FastWorker, fallo tu).`,
    },
    {
      find: `(GPT via LiteLLM, se disponibile) e confronta le due conclusioni prima di scegliere.`,
      replace: `(stesso prompt su un'altra famiglia di modelli): lancia i due agenti nello stesso messaggio,
ciascuno con \`run_in_background: false\`, e confronta le due conclusioni prima di scegliere.`,
    },
    {
      find: `Poi esci dal worktree come indicato in «Entrata e uscita dal worktree».`,
      replace: `Poi ferma i processi in background avviati nel worktree, come indicato in «Comandi dentro il
worktree».`,
    },
    {
      find: `- prima della review, «Proxy LiteLLM (solo \`loop\`)» e l'ultimo paragrafo di «Modello di
  implementazione»;`,
      replace: `- prima della review, il controllo sul modello della sessione di «Modello di implementazione»;`,
    },
    {
      find: `Alla fine esci dal worktree, poi stampa la tabella di «Verifica finale» senza la riga «Prossimo`,
      replace: `Alla fine ferma i processi in background avviati nel worktree, poi stampa la tabella di «Verifica
finale» senza la riga «Prossimo`,
    },
  ],

  "commands/workflow/2_work-simplify.md": [WORKTREE_COMMANDS],

  "commands/workflow/2_work-verify.md": [
    WORKTREE_COMMANDS,
    {
      find: `): Blast Radius
lascia cancellare senza conferma solo lì.`,
      replace: `):
la permission policy di pi lascia cancellare solo lì. Per cancellarla usa un comando a sé con il
percorso stampato da \`mktemp\` scritto per esteso, \`rm -rf "$HOME/.pi/agent/tmp/verify.<suffisso>"\`:
niente variabili oltre a \`$HOME\`, niente \`~\`, niente glob.`,
    },
    {
      find: `\`.claude/skills/verifier-*\`, \`.claude/skills/run-*\` e \`.claude/skills/verify/\`. Usa quella che`,
      replace: `\`verifier-*\`, \`run-*\` e \`verify/\` sotto \`.claude/skills/\`, \`.pi/skills/\` e \`.agents/skills/\`. Usa
quella che`,
    },
    { find: `sia vuoto. Poi esci dal worktree.`, replace: `sia vuoto.` },
  ],

  "commands/workflow/3_independent-review.md": [
    // I prompt di pi non cambiano modello: la review la fa un agente a modello fisso e la
    // sessione orchestra. hard = ReviewerOpus + verify di ReviewerSoft, soft = ReviewerSoft.
    // Nel modo hard il primo lancio è in background: solo così il risultato riporta l'Agent ID
    // che serve a `resume` (un lancio bloccante restituisce il testo senza ID).
    {
      find: `- \`hard\`: esegui la review tu, come descritto sotto.
- \`soft\`: non fare tu la review. Lancia il tool Agent con \`subagent_type: ReviewerOpus\`,
  \`model: sonnet\` ed \`effort: xhigh\`. Nel prompt digli di leggere
  \`~/.pi/agent/prompts/3_independent-review.md\` e di seguirlo con gli stessi
  argomenti senza \`soft\` al posto di \`$ARGUMENTS\`. Poi mostra il suo report senza cambiarlo.`,
      replace: `In pi un prompt non può cambiare il modello della sessione: la review la fa un agente con modello
fisso. Se hai il tool Agent sei la sessione principale: non fare tu la review, orchestra.

- \`hard\`: la review la fa \`ReviewerOpus\`, il verify dei candidati \`ReviewerSoft\`.
  1. Lancia il tool Agent con \`subagent_type: ReviewerOpus\` e \`run_in_background: true\`: il
     risultato riporta l'\`Agent ID\`, che ti serve per riprenderlo. Nel prompt digli di leggere
     \`~/.pi/agent/prompts/3_independent-review.md\`, di seguirlo con gli stessi argomenti senza
     \`hard\` al posto di \`$ARGUMENTS\` e di fermarsi ai candidati come descritto in «Chi fa il
     verify» (sezione 7), perché il verify lo lancia la sessione principale.
  2. Aspetta il suo output con \`get_subagent_result\` (\`agent_id\` = quell'ID, \`wait: true\`).
  3. Se ti ha restituito dei candidati, segui «Chi fa il verify»: lanci \`ReviewerSoft\` e poi
     riprendi il reviewer con gli esiti. Se ti ha restituito già il report (nessun candidato, o
     verdetto \`BLOCCATO\`), salta questo passo.
  4. Mostra il report del reviewer senza cambiarlo.
- \`soft\`: lancia il tool Agent con \`subagent_type: ReviewerSoft\` e \`run_in_background: false\`. Nel
  prompt digli di leggere \`~/.pi/agent/prompts/3_independent-review.md\` e di seguirlo con gli
  stessi argomenti senza \`soft\` al posto di \`$ARGUMENTS\`. Poi mostra il suo report senza cambiarlo.

Se non hai il tool Agent sei il reviewer: esegui la review tu, come descritto sotto.`,
    },
    // L'appoggio del reviewer sta fuori dal worktree: niente più esclusione nello status.
    { find: ` -- . ':!.review-tmp'`, replace: `` },
    { find: `fuori da \`<rev-path>/.review-tmp/\`;`, replace: `fuori da \`<tmp-path>\` (definita sotto);` },
    {
      find: `cambiato, ignorando la cartella \`<rev-path>/.review-tmp/\`: è l'unico posto dove puoi creare file
di appoggio (script, output di test, benchmark).`,
      replace: `cambiato. I file di appoggio (script, output di test, benchmark) vanno solo in \`<tmp-path>\`, una
cartella fuori dal worktree: \`$HOME/.pi/agent/tmp/<nome>\`, dove \`<nome>\` è il nome della directory
di \`<rev-path>\` (es. \`review+ICH-97-sol\`).
Creala con \`mkdir -p\`.`,
    },
    {
      find: `- **Convenzioni.** Trova i \`CLAUDE.md\` che governano i file modificati: quello in \`<rev-path>\`,
  cioè la radice del repository nella versione della PR, e ogni \`CLAUDE.md\` o \`CLAUDE.local.md\` in
  una directory tra \`<rev-path>\` e un file modificato (vale solo per i file al suo livello o
  sotto). Non salire sopra \`<rev-path>\`: il worktree sta dentro il checkout principale, i cui
  \`CLAUDE.md\` sono di un'altra versione. Non usare \`~/.claude/CLAUDE.md\`: è privato, e le regole
  citate finiscono nella PR e nelle issue. Leggi quelli che esistono e cerca violazioni chiare
  delle regole che riguardano il codice. Segnala una violazione solo se puoi citare la regola
  esatta, con il path del suo \`CLAUDE.md\`, e la riga che la viola: niente deduzioni sullo
  «spirito» del documento.`,
      replace: `- **Convenzioni.** Trova gli \`AGENTS.md\` o \`CLAUDE.md\` del progetto che governano i file
  modificati: quelli in \`<rev-path>\`, cioè la radice del repository nella versione della PR, e ogni
  \`AGENTS.md\`, \`CLAUDE.md\` o \`CLAUDE.local.md\` in una directory tra \`<rev-path>\` e un file
  modificato (vale solo per i file al suo livello o sotto). Non salire sopra \`<rev-path>\`: il
  worktree sta dentro il checkout principale, i cui file sono di un'altra versione. Non usare
  \`~/.pi/agent/AGENTS.md\`: è privato, e le regole citate finiscono nella PR e nelle issue. Leggi
  quelli che esistono e cerca violazioni chiare delle regole che riguardano il codice. Segnala una
  violazione solo se puoi citare la regola esatta, con il path del suo file, e la riga che la
  viola: niente deduzioni sullo «spirito» del documento.`,
    },
    // Il reviewer non ha il tool Agent: nel modo hard il verify lo lancia la sessione, che poi
    // riprende il reviewer (resume) per il report.
    {
      find: `**Chi fa il verify.** Chi ha trovato un candidato tende a confermarlo. Se hai il tool Agent,
lancialo **una sola volta**, con \`subagent_type: ReviewerOpus\` e \`model: sonnet\`, e passagli
tutti i candidati insieme. Nel prompt metti:`,
      replace: `**Chi fa il verify.** Chi ha trovato un candidato tende a confermarlo. Nel modo \`hard\` il verify lo
fa quindi un altro agente, \`ReviewerSoft\`, e lo lancia la sessione principale: il reviewer non ha
il tool Agent.

Se sei il reviewer e la sessione principale ti ha chiesto di fermarti ai candidati: non fare il
verify e non fare la «Pulizia». Restituisci \`<rev-path>\`, \`<tmp-path>\`, la baseline della sezione
3, i requisiti a cui si riferiscono i candidati e i candidati numerati, con \`file:riga\`, sintesi e
scenario o costo. Poi fermati: la sessione ti riprende con gli esiti.

Se sei la sessione principale: lancia il tool Agent **una sola volta**, con
\`subagent_type: ReviewerSoft\` e \`run_in_background: false\`, e passagli tutti i candidati insieme.
Nel prompt metti:`,
    },
    {
      find: `  \`<rev-path>/.review-tmp/verify/\`: prima di rispondere cancella quella cartella e nient'altro;`,
      replace: `  \`<tmp-path>/verify/\`: prima di rispondere cancella quella cartella e nient'altro, con \`rm -rf\` e
  il percorso scritto per esteso;`,
    },
    {
      find: `La risposta è valida se ha una riga per ogni candidato e ogni \`REFUTED\` cita \`file:riga\`. Se manca
la riga di un candidato, o un \`REFUTED\` non ha la prova, fai tu il verify di quel candidato. Se
manca il tool Agent (per esempio quando giri come \`ReviewerOpus\` nel modo \`soft\`, in
\`/4_review-fix-loop\` o in \`/issue-cycle\`) o il subagente fallisce, fai tu il verify di tutti i
candidati.`,
      replace: `Poi riprendi il reviewer: tool Agent con \`resume\` = il suo \`Agent ID\`,
\`subagent_type: ReviewerOpus\` e \`run_in_background: false\`, e nel prompt la risposta del verify
senza cambiarla; se il verify è fallito, diglielo.

Se sei il reviewer e la sessione ti riprende con gli esiti: la risposta è valida se ha una riga per
ogni candidato e ogni \`REFUTED\` cita \`file:riga\`. Se manca la riga di un candidato, o un \`REFUTED\`
non ha la prova, fai tu il verify di quel candidato. Se nessuno ti ha chiesto di fermarti ai
candidati (per esempio nel modo \`soft\`, in \`/4_review-fix-loop\` o in \`/issue-cycle\`) o il verify è
fallito, fai tu il verify di tutti i
candidati.`,
    },
    {
      find: `Come ultima azione prima di restituire il report cancella \`<rev-path>/.review-tmp/\`, sempre:
\`git worktree remove\` rifiuta un worktree con file non tracciati e \`--force\` è vietato.`,
      replace: `Come ultima azione prima di restituire il report cancella \`<tmp-path>\`, sempre, con un comando a sé
e il percorso scritto per esteso: \`rm -rf "$HOME/.pi/agent/tmp/<nome>"\`. La permission policy di pi
lascia passare \`rm -r\` solo così: sotto \`$HOME/.pi/agent/tmp\`, senza altre variabili, senza \`~\` e
senza glob.`,
    },
    {
      find: `(ha \`disable-model-invocation: true\`, non puoi invocarlo come slash command)`,
      replace: `(pi espande i template solo dall'editor: non puoi invocarlo come slash command)`,
    },
    { find: `  (subagente o tu, inline);`, replace: `  (\`ReviewerSoft\` o tu, inline);` },
  ],

  "commands/workflow/4_review-fix-loop.md": [
    { find: `(ReviewerOpus su Fable, Reviewer su GPT)`, replace: `(ReviewerOpus su Opus, Reviewer su GPT)` },
    // In pi i due reviewer sono agenti nativi: niente proxy e niente controllo che la mod sia caricata.
    {
      find: `\`ReviewerOpus\` su
Fable e \`Reviewer\` sul modello GPT fissato da \`gpt-model\` in \`agents/reviewer.md\` (via
proxy LiteLLM, servito dalla mod gpt-bridge). Se \`Reviewer\` non compare tra i
subagent_type disponibili, la mod non è caricata: fermati e dillo all'utente prima di creare i
worktree.`,
      replace: `\`ReviewerOpus\`
(review \`opus\`) e \`Reviewer\` (review \`gpt\`). Il modello di ciascuno è fissato nel suo file in
\`~/.pi/agent/agents/\`.`,
    },
    {
      find: `Il command ha
   \`disable-model-invocation: true\`: né tu né un subagente`,
      replace: `Pi espande i template
   solo dall'editor: né tu né un subagente`,
    },
    {
      find: `   in \`<review-wt-path>/.review-tmp/\`, mai altrove.`,
      replace: `   nella cartella della sua review sotto \`$HOME/.pi/agent/tmp/\` (la definisce
   \`3_independent-review\`), mai altrove.`,
    },
    { find: `   - review \`fable\`: tool Agent con`, replace: `   - review \`opus\`: tool Agent con` },
    {
      find: `     \`fable\`. Il subagente gira su GPT via proxy LiteLLM con tool e permessi nativi, e compare nel
     pannello degli agenti come l'altro.`,
      replace: `     \`opus\`.`,
    },
    // L'avviso di indipendenza confronta il modello fisso dei reviewer con quello della sessione
    // (variabili PI_* della shell dei tool) e con l'etichetta <model>.
    {
      find: `   Lancia le due Agent nello stesso messaggio, così girano in parallelo. Se \`<model>\` coincide con
   uno dei due modelli di review (\`fable\` o \`gpt\`), segnalalo: quella review gira sullo stesso
   modello che ha scritto il codice ed è meno indipendente.`,
      replace: `   Prima di lanciarle controlla l'indipendenza delle review:

   \`\`\`bash
   printf 'sessione: %s/%s\\n' "$PI_PROVIDER" "$PI_MODEL"
   grep -H -m1 '^model:' "$HOME/.pi/agent/agents/ReviewerOpus.md" "$HOME/.pi/agent/agents/Reviewer.md"
   \`\`\`

   Se il modello di un reviewer coincide con quello della sessione, o il suo nome contiene
   \`<model>\` (l'etichetta di chi ha scritto il codice: \`opus\` in \`claude-opus-5-5\`, \`sol\` in
   \`gpt-6.2-sol\`), segnalalo: quella review gira sullo stesso modello che ha scritto il codice ed è
   meno indipendente.

   Poi lancia le due Agent nello stesso messaggio, ciascuna con \`run_in_background: false\`: girano
   in parallelo e ricevi i due report completi.`,
    },
    {
      find: `- prima del primo fix entra con un comando a sé, \`cd "<wt-path>"\`; dopo il push, o se ti fermi
  prima, esci con \`cd "<repo-root>"\`: lo step 5 non può cancellare la cwd della sessione;`,
      replace: `- in pi ogni comando parte in una shell nuova: quando un comando deve girare dentro il worktree
  scrivi \`cd "<wt-path>" && <comando>\` nello stesso comando;`,
    },
  ],

  "commands/workflow/5_remove-worktree.md": [
    {
      find: `Se la cwd corrente è dentro il worktree da
rimuovere (\`git rev-parse --show-toplevel\` = path del worktree, confronta i due path dopo
\`cygpath -m\`), esci con un comando a sé, \`cd "<repo-root>"\`, e verifica con \`pwd\`: su Windows git
non cancella una directory che fa da cwd alla shell (\`Device or resource busy\`, vedi più sotto).`,
      replace: `Se la sessione di pi è
stata avviata dentro il worktree da rimuovere (\`git rev-parse --show-toplevel\` = path del worktree,
confronta i due path dopo \`cygpath -m\`), fermati e chiedi all'utente di rilanciare pi dalla root:
in pi ogni comando parte dalla directory della sessione e un \`cd\` non la cambia. Su Windows git non
cancella una directory che fa da cwd a un processo (\`Device or resource busy\`, vedi più sotto), e
senza quella directory pi non può più eseguire comandi.`,
    },
    {
      find: `spostati sulla root vista con la **stessa lettera dell'entry** (\`cd /e/AI/Claude/Trinity\`):
git confronta i path testualmente e non risolve i \`subst\`.`,
      replace: `lavora dalla root vista con la **stessa lettera dell'entry**, premettendo il \`cd\` a ogni
comando (\`cd /e/AI/Claude/Trinity && <comando>\`): git confronta i path testualmente e non risolve i
\`subst\`.`,
    },
    // Fuori da $HOME/.pi/agent/tmp il permission-gate blocca `rm -r`: lo esegue l'utente.
    {
      find: `Non ripetere il comando: chiudi chi la tiene e poi
cancella la sola directory con \`rm -rf "<wt-path>"\`.`,
      replace: `Non ripetere il comando. Resta da cancellare la sola
directory, con \`rm -rf "<wt-path>"\`, dopo aver chiuso chi la tiene: la permission policy di pi
blocca \`rm -r\` fuori da \`~/.pi/agent/tmp\` e non va aggirata, quindi mostra il comando all'utente,
che lo esegue a mano.`,
    },
    {
      find: `La cartella non è più un worktree:
\`rm -rf "<repo-root>/.pi/worktrees/$1"\`. Prima controlla che dentro non ci siano`,
      replace: `La cartella non è più un worktree e
va cancellata con \`rm -rf "<repo-root>/.pi/worktrees/$1"\`: la permission policy di pi blocca \`rm -r\`
fuori da \`~/.pi/agent/tmp\` e non va aggirata, quindi mostra il comando all'utente, che lo esegue a
mano. Prima controlla che dentro non ci siano`,
    },
    {
      find: `in \`CLAUDE.md\` (es. «dopo ogni merge chiudi il
  lotto»).`,
      replace: `in \`AGENTS.md\` o \`CLAUDE.md\` del progetto
  (es. «dopo ogni merge chiudi il lotto»).`,
    },
    {
      find: `chiedi all'utente se aggiornarli e se salvare
  decisioni e cause radice in Hindsight;`,
      replace: `chiedi all'utente se aggiornarli;`,
    },
  ],

  "commands/issue-cycle.md": [
    {
      find: `Gli step hanno
\`disable-model-invocation: true\`: non puoi invocarli come slash command.`,
      replace: `Pi espande i template
solo dall'editor: non puoi invocare gli step come slash command.`,
    },
    {
      find: `/issue-cycle loop master ICH-97 ICH-98 fable    # modello esplicito`,
      replace: `/issue-cycle loop master ICH-97 ICH-98 sol      # modello esplicito`,
    },
    {
      find: `- Non usare \`AskUserQuestion\` e non chiudere il turno per aspettare una risposta.`,
      replace: `- Non fare domande all'utente e non chiudere il turno per aspettare una risposta.`,
    },
    {
      find: `Se la sessione gira su Fable, annota che la review Fable gira sullo stesso modello che ha scritto
il codice ed è meno indipendente: conta il modello della sessione, non \`<model>\`. In \`loop\` questo
controllo sostituisce quello su \`<model>\` di \`4_review-fix-loop.md\`.`,
      replace: `Confronta il modello della sessione con quello fisso dei reviewer che userai (\`review\`: solo
\`ReviewerOpus\`; \`loop\`: anche \`Reviewer\`):

\`\`\`bash
printf 'sessione: %s/%s\\n' "$PI_PROVIDER" "$PI_MODEL"
grep -H -m1 '^model:' "$HOME/.pi/agent/agents/ReviewerOpus.md" "$HOME/.pi/agent/agents/Reviewer.md"
\`\`\`

Se coincidono, annota che quella review gira sullo stesso modello che ha scritto il codice ed è
meno indipendente: conta il modello della sessione, non \`<model>\`. In \`loop\` questo controllo
sostituisce quello di \`4_review-fix-loop.md\`.`,
    },
    // In pi la review GPT non passa da un proxy: la sezione non serve.
    {
      find: `### Proxy LiteLLM (solo \`loop\`)

La review GPT dello step 4 usa il proxy LiteLLM:

\`\`\`bash
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:4000/health/liveliness   # deve essere 200
\`\`\`

Se la risposta non è \`200\`, prosegui con la sola review Fable: in ogni round dello step 4 crea solo
il worktree \`review+<base-name>-opus\`. Annotalo in «Questioni aperte». Ripeti il controllo
all'inizio della review di ogni issue: il proxy può partire o fermarsi durante il ciclo.

`,
      replace: ``,
    },
    // In pi la directory della sessione non cambia mai: niente ritorno alla root.
    {
      find: `Alla fine del ciclo, anche dopo un'interruzione, controlla con \`pwd\` che la sessione sia nella root
del repository; se non lo è, esegui \`cd "<repo-root>"\` come comando a sé. La issue seguente parte
dalla root.

`,
      replace: ``,
    },
    {
      find: `- \`review\`: tool Agent con \`subagent_type: ReviewerOpus\`. Nel prompt digli di leggere`,
      replace: `- \`review\`: tool Agent con \`subagent_type: ReviewerOpus\` e \`run_in_background: false\`. Nel prompt
  digli di leggere`,
    },
    {
      find: `La cartella \`<review-path>/.review-tmp/\` è materiale di appoggio del reviewer: cancellala prima
della rimozione, come fa lo step 3. Se lo step 5 trova altri file`,
      replace: `La cartella di appoggio del reviewer sta fuori dal worktree, in
\`$HOME/.pi/agent/tmp/<nome del worktree di review>\`: se esiste ancora, cancellala come fa lo
step 3. Se lo step 5 trova file`,
    },
  ],

  "agents/reviewer.md": [
    {
      find: `appoggio solo nella cartella \`.review-tmp/\` del worktree di review; se l'orchestratore ti indica
  una sua sottocartella, usa solo quella. Prima del report cancella la cartella che hai usato, mai
  la sua cartella padre.`,
      replace: `appoggio solo nella cartella della review sotto \`$HOME/.pi/agent/tmp/\`, fuori dal worktree; se
  l'orchestratore ti indica una sua sottocartella, usa solo quella. Prima del report cancella la
  cartella che hai usato, mai la sua cartella padre.`,
    },
  ],

  // In pi le regole globali stanno in AGENTS.md, che l'agente eredita (prompt_mode: append).
  "agents/fast-worker.md": [{ find: `\`core-behavior\``, replace: `le regole operative di \`AGENTS.md\`` }],

  "agents/arch-scanner.md": [
    {
      find: `tutti in un unico messaggio così girano in
parallelo.`,
      replace: `tutti in un unico messaggio e ciascuno con
\`run_in_background: false\`, così girano in parallelo e ne aspetti i
risultati.`,
    },
  ],
};
