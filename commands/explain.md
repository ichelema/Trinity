---
description: Rispiega in modo più semplice l'ultima risposta o un punto non chiaro, con un esempio concreto e le soluzioni a confronto
argument-hint: "[cosa non è chiaro]"
disable-model-invocation: true
---

# Explain

L'utente non ha capito una tua risposta: un problema, un'analisi, una scelta che gli hai chiesto di
fare. Spiegala di nuovo da un'altra angolazione, partendo da un esempio concreto. Non andare avanti
con il lavoro.

## Cosa spiegare

- Con un argomento: spiega solo il punto indicato in `$ARGUMENTS`.
- Senza argomento: spiega la tua ultima risposta. Se chiedeva una decisione, spiega cosa serve
  sapere per prenderla.

Se non capisci quale punto non è chiaro, chiedilo con una sola domanda breve. Non rispiegare tutto
a caso.

## Regole

- Usa i fatti che hai già raccolto: non riaprire l'analisi. Rileggi un file, il codice o l'output di
  un comando solo se non sei sicuro di un fatto. Una spiegazione chiara su un fatto sbagliato è
  peggio di nessuna spiegazione.
- Segna ciò che non hai controllato: «probabile, non verificato».
- Se rispiegando trovi che la risposta originale era sbagliata o incompleta, e non solo poco chiara,
  dillo subito all'inizio e correggila.
- Sola lettura: non modificare file, non cambiare stati (git, PR, Linear), non avviare subagenti.
- Cambia angolazione, non riformulare la risposta precedente: parti da cosa fa e cosa vede l'utente,
  non da come è fatto il codice.
- Spiega ogni termine tecnico la prima volta che lo usi, in una frase. Lascia fuori nomi di
  funzioni, file e righe quando non servono a capire; se servono come prova, mettili in fondo.
- Usa sempre lo stesso nome per la stessa cosa: un nome scelto all'inizio resta quello fino alla
  fine.
- Resta in circa una schermata. Se il tema è grande, spiega prima il nucleo e offri di approfondire
  una parte.

## Struttura della risposta

Usa le sezioni che servono, in quest'ordine. Salta quelle che non si applicano: per esempio «Le
soluzioni» quando non c'è niente da scegliere.

1. **Il problema in breve**: 2–3 frasi senza gergo. Cosa succede, a chi, con quale effetto.
2. **Esempio concreto**: passi numerati dal punto di vista dell'utente: cosa fa, cosa vede, dove va
   storto. Metti i comandi reali in un blocco di codice con il linguaggio. Chiudi con il passo che
   rimette le cose a posto, se esiste.
3. **Un diagramma**: solo se un flusso o una disposizione si capiscono meglio guardandoli. Usa
   `mermaid` per sequenze e flussi, un blocco `figure` per layout e linee del tempo. Un solo
   diagramma; il testo non ripete cosa il diagramma mostra già.
4. **Quando capita**: le condizioni, la frequenza, la gravità. Dì anche quando NON capita.
5. **Perché è così**: la causa in parole semplici. Se le soluzioni ovvie non funzionano, una riga
   per ognuna: cosa sarebbe e perché non va.
6. **Le soluzioni**: una tabella `| Soluzione | Cosa cambia | Cosa vedi tu | Limite |`, una riga per
   opzione. Poi la raccomandazione, con il motivo in una o due frasi.
7. **La domanda**: se una decisione è aperta, chiudi con una sola domanda secca nel testo. Non usare
   `AskUserQuestion`: la finestra di dialogo copre la spiegazione appena scritta.

Dopo la risposta fermati. Riprendi il lavoro solo quando l'utente risponde.

## Esempio di forma

Caso: l'utente non ha capito perché una pipe CLI resta appesa quando un plugin è aperto in due pane.

```markdown
## Il problema in breve
Ogni pane ha una sua copia del plugin, e ogni copia chiede i permessi per conto suo. Tu rispondi
«y» solo nel pane che vedi; l'altra copia resta in attesa, e ogni `zellij pipe` aspetta anche lei.

## Esempio concreto
1. Apri una sessione nuova senza permessi già scritti.
2. Premi `y` nel rail largo: il rail parte.
3. Lanci `zellij action pipe ...`: il comando non torna più.
4. Riavvii la sessione: ora funziona, perché il permesso è nella cache.

## Le soluzioni
| Soluzione | Cosa cambia | Cosa vedi tu | Limite |
|---|---|---|---|
| Fix nell'host | ... | ... | ... |
| Solo doc | ... | ... | ... |

Consiglio la prima: la causa è nell'host, e lì la correzione è pulita.

Quale preferisci?
```
