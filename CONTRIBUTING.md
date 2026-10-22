# Contribuire a YouTube Producer

La repo è privata e la usano le persone invitate come collaboratori. Ogni commit su `main` arriva a tutti con il prossimo aggiornamento del plugin (README, «Aggiornare»): per questo su `main` si entra solo con una pull request.

**Non fare mai `git push` su `main`.** Su una repo privata di un account personale i collaboratori hanno sempre il permesso di scrittura, e la protezione del branch richiede un piano GitHub a pagamento: se manca, GitHub non ti ferma. La regola la teniamo noi: lavora sempre su un branch e apri una PR (sotto). Se per sbaglio hai fatto push su `main`, avvisa subito il proprietario della repo.

## Flusso: branch e pull request

1. Clona la repo (servono `gh auth login` e `gh auth setup-git`):
   ```bash
   gh repo clone MikeIdeas2025/youtube-producer ~/youtube-producer && cd ~/youtube-producer
   ```
   È anche il `repo_path` di default delle PR di apprendimento `learn/…`; se la cloni altrove, scrivi il percorso in `repo_path` (README, «Configurazione»).
2. Crea un branch da `main` aggiornato, con un nome che dica cosa fai: `feat/<cosa>`, `fix/<cosa>`, `docs/<cosa>`, `knowledge/<cosa>`. Per esempio `fix/capitoli-oltre-un-ora`.
3. Lavora e prova in locale (sotto). Commit piccoli, messaggi brevi in italiano all'imperativo («Correggi il crop degli Shorts sul campo largo»).
4. Apri la PR verso `main` con `gh pr create`. Nella descrizione: cosa cambia, perché, come l'hai provato (comandi e risultati), cosa cambia per chi usa il plugin (serve rilanciare `/youtube:setup`? cambia un comportamento dell'agente?) e, se tocchi `plugins/youtube/`, cosa cambia per chi lo usa con Codex ([Versione Codex](#versione-codex)).
5. Revisione di un'altra persona con accesso alla repo. Si fa merge solo con i test verdi e le domande chiuse. Preferito lo squash merge: un commit per PR su `main`.
6. Dopo il merge, chi vuole la versione nuova lancia `claude plugin marketplace update youtube-producer`, poi `claude plugin update youtube@youtube-producer`, e riavvia Claude Code (README, «Aggiornare»); poi `/youtube:setup` se la PR cambia dipendenze o lockfile. Con Codex: `codex plugin marketplace upgrade youtube-producer`, poi una conversazione nuova (CODEX.md, «Aggiornare»).

Non si modifica mai la copia installata in `~/.claude/plugins/` o in `~/.codex/plugins/`: si sovrascrive al primo aggiornamento e nessun altro vede la modifica.

## Provare in locale

Dalla radice della repo:

```bash
claude plugin validate ./plugins/youtube --strict    # manifest, comandi, agenti, hook
claude plugin validate .                             # il marketplace (se tocchi .claude-plugin/marketplace.json)
claude --plugin-dir ./plugins/youtube                # sessione con il plugin del tuo branch al posto di quello installato
```

L'unico avviso ammesso è «version: No version specified»: è voluto (niente `version` in `plugin.json`, la versione è il commit). Con `--strict` quel solo avviso fa uscire «Validation failed»: va bene così, purché non ci sia nient'altro. Ogni altro avviso o errore si corregge prima della PR.

Nella sessione con `--plugin-dir`:

- `/youtube:setup doctor` deve dare tutti i «must» verdi; se hai cambiato `install.sh`, `pyproject.toml`, `uv.lock` o i `package-lock.json`, prima `bash plugins/youtube/scripts/yt/install.sh` (piano) e poi `--yes`;
- se hai toccato il guard: `bash plugins/youtube/scripts/yt/bin/guard.sh --selftest` deve passare tutto;
- `yt-config` deve stampare i percorsi del tuo checkout;
- prova la skill che hai cambiato su un caso vero e piccolo, fino al gate: `/youtube:producer …` oppure `/youtube:<skill> …`, su un tuo canale di prova.

**Test del toolkit.** I test stanno in `plugins/youtube/scripts/yt/tests/`: sono script con assert semplici (niente pytest) che lavorano in cartelle temporanee, quindi non toccano i tuoi dati. Si lanciano con il Python del venv del plugin:

```bash
PY="$(yt-config --get venv_python)"
for t in plugins/youtube/scripts/yt/tests/test_*.py; do "$PY" "$t" || break; done
"$PY" plugins/youtube/scripts/yt/tests/test_learn.py thompson    # solo i test il cui nome contiene «thompson»
```

Il ciclo comprende anche i test della versione Codex (`test_codex*.py`), che girano pure con il `python3` di sistema ([Versione Codex](#versione-codex)).

Per il kit del pre-test delle thumbnail: `python3 plugins/youtube/docs/yt/templates/pretest-kit/analizza.py selftest`.

Se la PR tocca trascrizione, montaggio, Shorts o thumbnail, fai girare anche la catena end-to-end (ordine in `plugins/youtube/scripts/yt/README.md`) su un estratto di pochi minuti di un tuo video, tenuto fuori dal checkout, e riporta nella PR i numeri prima e dopo (loudness, errori di trascrizione sui nomi, controlli del QA).

## Versione Codex

Lo stesso plugin gira anche in Codex di OpenAI (guida per chi lo usa: `CODEX.md`). La fonte resta una sola: agente, dispatcher e skill di Claude Code, toolkit e knowledge pack. In Codex un plugin non può portare agenti e i comandi di Claude Code non diventano skill da soli, quindi Codex riceve delle skill brevi che dicono al modello di leggere a runtime i file di Claude Code e di applicarli con una guida di traduzione. Claude Code non legge nessuno dei file qui sotto.

| File | Cosa contiene | Come si cambia |
|---|---|---|
| `.agents/plugins/marketplace.json` | il marketplace per Codex (Codex lo legge al posto di `.claude-plugin/marketplace.json`) | a mano |
| `plugins/youtube/.codex-plugin/plugin.json` | il manifest per Codex: nome, versione, skill in `codex/skills/`, hook in `codex/hooks.json`, `commands: []` | a mano |
| `plugins/youtube/codex/skills/<nome>/SKILL.md` e `agents/openai.yaml` | una skill Codex per ogni `commands/<nome>.md` | **generati**, mai a mano |
| `plugins/youtube/codex/toolkit-commands.txt` | i nomi dei comandi di `bin/`, per gli shim e per il guard di Codex | **generato** |
| `plugins/youtube/codex/references/codex-host.md` | come valgono in Codex le istruzioni scritte per Claude Code: strumenti, gate, guard, sandbox, setup | a mano |
| `plugins/youtube/codex/hooks.json` | i tre hook di Codex | a mano, **congelato** (sotto) |
| `plugins/youtube/scripts/codex/build_skills.py` | il generatore | a mano |
| `plugins/youtube/scripts/yt/bin/codex-shims.sh` | i comandi `yt-*` per Codex (Codex non copia i symlink di `bin/`) | a mano |

**Rigenerare le skill di Codex.** Ogni volta che cambi un `commands/*.md` (anche solo `description` o `argument-hint`), la tabella del Passo 1 di `agents/producer.md` o i comandi in `bin/`, dalla radice della repo:

```bash
python3 plugins/youtube/scripts/codex/build_skills.py            # riscrive codex/skills/ e codex/toolkit-commands.txt
python3 plugins/youtube/scripts/codex/build_skills.py --check    # deve uscire con 0: niente di vecchio, mancante o in più
python3 plugins/youtube/scripts/yt/tests/test_codex_skills.py    # test di sincronia; basta il python3 di sistema
python3 plugins/youtube/scripts/yt/tests/test_codex_runtime.py   # copia installata da Codex, shim, guard (anche MCP e data dir), hook congelati
```

Committa i file generati insieme alla modifica che li ha cambiati. Se dimentichi di rigenerare, `--check` e il test di sincronia falliscono. Sul tuo Mac, se c'è Codex, il test lancia anche i validatori di OpenAI in sola lettura; altrimenti quella parte viene saltata.

**Regole della versione Codex.**

- **Una skill nuova** (`commands/<nome>.md`, «Proporre una skill nuova» sotto) in Codex esiste solo se il generatore la conosce: aggiungi la sua voce in `TITLES`, `SHORT` (25–64 caratteri) e `DEFAULT_PROMPTS` di `build_skills.py` e rigenera. Il generatore si ferma se manca una voce, o se `commands/` e la tabella del Passo 1 di `agents/producer.md` non coincidono.
- **Le skill Codex restano corte** (errore sopra i 7.500 byte): quando l'utente chiama una skill, Codex passa al modello solo i primi 8.000 byte del `SKILL.md`, senza avvisarlo. Il metodo resta nei file di Claude Code; negli involucri non si copia.
- **Righe non troppo lunghe nei file che le skill leggono** (`commands/`, `agents/`, `docs/yt/knowledge/`, `docs/yt/templates/`, `codex/references/`): in Codex si leggono a blocchi di 120 righe, e Codex taglia a metà l'output di un comando oltre circa 10.000 token. `test_codex_skills.py` fallisce se un blocco supera i 24 KB.
- **Uno strumento nuovo** nel frontmatter `tools:` di `agents/producer.md` va aggiunto alla tabella «Traduzione» di `codex/references/codex-host.md`.
- **Mai una cartella `plugins/youtube/skills/`**: Claude Code la caricherebbe e avresti skill doppie. Il generatore si ferma se la trova.
- **La versione.** Per Claude Code la versione è il commit; Codex vuole un numero, che usa per la cartella della cache. In ogni PR che tocca `plugins/youtube/` alza di una patch `version` in `plugins/youtube/.codex-plugin/plugin.json` (per esempio 1.0.0 → 1.0.1).
- **`codex/hooks.json` non si cambia.** Codex chiede di riapprovare gli hook quando ne cambiano evento, matcher, comando, timeout o messaggio di stato: ogni collega che usa Codex dovrebbe rifarlo. Se una modifica è inevitabile, scrivilo nella PR e aggiorna `FROZEN_HOOKS` in `test_codex_runtime.py`, che altrimenti fallisce. Le regole del guard si cambiano in `guard.sh`, che per l'approvazione non conta.
- **Gli script condivisi** (`scripts/yt/bin/_run`, `_paths.sh`, `guard.sh`, `session-hint.sh`, `scripts/yt/install.sh`, `lib/config.py`, `lib/ytcore.py`, `lib/doctor.py`) in Claude Code devono fare quello che facevano. Quello che serve solo a Codex sta dietro l'opzione `--codex`, dietro la forma diretta `_run <comando>`, dietro la variabile `CODEX_SESSION_ID` o dietro una copia del toolkit nella cache dei plugin di Codex. Un'eccezione voluta: nel guard le regole sui lanciatori (N: `_run <comando>`, `bash <script>`), sulle shell annidate con le opzioni unite (`bash -lc`, `sh -ec`), su `find -exec` e sulle parole chiave della shell (`if`, `then`, `do`, `{`) valgono anche per l'agente di Claude Code, che così diventa solo più stretto. `guard.sh --selftest` copre anche le regole di Codex.
- **I validatori di OpenAI** sul manifest vero (`~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/youtube`) segnalano tre errori attesi: `hooks`, `commands` e `skills` che non punta a `skills/`. Valgono per i plugin dell'elenco pubblico di OpenAI, non per l'installazione da una repo; il loader di Codex li accetta.

**Provare il tuo branch in Codex.** Codex legge un marketplace locale direttamente dalla cartella, ma copia il plugin nella sua cache quando lo installi: dopo ogni modifica va reinstallato. Prova sempre in una conversazione aperta fuori dal clone (per esempio in `~/youtube-studio`): dentro il clone Codex vede anche il marketplace della repo e ne trova due con lo stesso nome.

```bash
# una volta: al posto del marketplace di GitHub, il tuo clone (sul branch della PR)
codex plugin remove youtube@youtube-producer
codex plugin marketplace remove youtube-producer
codex plugin marketplace add ~/youtube-producer
codex plugin add youtube@youtube-producer
# dopo ogni modifica: reinstalla, poi apri una conversazione nuova
codex plugin remove youtube@youtube-producer && codex plugin add youtube@youtube-producer
# alla fine: torna alla versione di tutti
codex plugin remove youtube@youtube-producer
codex plugin marketplace remove youtube-producer
codex plugin marketplace add MikeIdeas2025/youtube-producer
codex plugin add youtube@youtube-producer
```

Se dopo il cambio di marketplace Codex chiede di nuovo di approvare gli hook, approvali (CLI `/hooks`). Nella conversazione di prova: `$youtube:setup doctor`, poi «mostrami yt-config» (`codex_guard` deve dire `"active": true`), poi la skill che hai cambiato su un caso piccolo, fino al gate.

## Regole

- **Niente media.** Video, audio, sottotitoli, trascrizioni, frame, render: mai nella repo, nemmeno «di prova».
- **Niente segreti.** `client_secret.json`, `api_key`, token OAuth, `.env`, chiavi: mai, nemmeno in un commit poi cancellato (resta nella storia). Se succede, avvisa subito: la chiave va revocata e rigenerata.
- **Niente dati di clienti** e niente nomi, numeri o note di lavoro di clienti, neanche negli esempi.
- **Niente profili di canale.** I profili (`<slug>.md`), i glossari e le confusioni dei canali vivono nei `channels_dirs` di chi li usa. In `docs/yt/channels/` c'è e resta solo `_template.md`.
- **Niente brand di canale.** Token, logo, font, template thumbnail (`<slug>-*.html`), preset ASS e stili Remotion di un canale vivono solo nei `brands_dirs` di chi li usa (default `~/.config/youtube-producer/brands/<slug>/`). Nella repo c'è un solo brand, `demo`, neutro; i template incorporati e le composizioni Remotion restano generici e leggono i brand a runtime (`knowledge/07-thumbnails.md` §8).
- **Niente dati di apprendimento.** Playbook, glossari e confusioni appresi, golden set delle thumbnail e riferimenti di nicchia vivono in `<studio_dir>/data/` di chi lavora. Nella repo arrivano solo le regole, con una PR `learn/…` revisionata (sotto).
- **Niente persone vere negli esempi.** Gli esempi usano canali e persone inventati (il podcast «Il Caffè dei Maker», «Giulia», «Paolo», «Sara»…) e numeri dichiarati come illustrativi.
- **Niente percorsi personali.** Mai `/Users/<nome>/…`: nei comandi si usano i nomi nudi (`yt-ingest`), `yt-config --get <chiave>` per i percorsi di runtime, `${CLAUDE_PLUGIN_ROOT}` nei file di agente e comandi, nomi relativi dentro il knowledge pack.
- **Lingua.** Il corpo delle skill e del knowledge pack è in **inglese** (è il metodo, istruzioni per l'agente); la parte «Integrazione» delle skill, i deliverable, i brief dei gate e i messaggi all'utente sono in **italiano**. Non tradurre il metodo, non scrivere deliverable in inglese.
- **Se cambi un comportamento, aggiorna la conoscenza.** Una regola nuova dell'agente o di una skill va anche nel file del knowledge pack che la governa, e nel `DESIGN.md` se tocca un contratto (comandi, schemi JSON, gate, sicurezza, licenze). Un fatto di piattaforma nuovo va in `01-platform-facts.md` con URL e data di verifica; un numero senza fonte non entra (`10-evidence-ledger.md`).
- **Regole dure.** Niente modifiche generative a volti e voci, consenso per profilo, niente servizi a pagamento dentro l'agente, niente upload né pubblicazione, gate G1/G2/G3, OAuth in sola lettura. Una PR che le allenta non passa.
- **Dipendenze**: versioni fissate in `uv.lock`, `package-lock.json` e `install.sh`. Aggiornarle è una PR a sé, con la prova di `/youtube:setup update`.
- **Codice di terzi**: solo dopo averlo letto per intero, a SHA fissato, con licenza e nota in `docs/yt/vendor/` (`NOTICE.md`). Repo senza licenza o AGPL: solo idee, riscritte.

## Le PR di apprendimento (`learn/…`)

L'agente impara da solo in locale (Tier A) e, per i canali che lo permettono, scrive una **proposta di miglioramento** quando una lezione ha abbastanza prove (Tier B, `plugins/youtube/docs/yt/knowledge/13-learning-loop.md` §9). Il Tier B è spento di default: si accende mettendo il canale in `learning_pr_channels` del `config.yaml` e `share_lessons: true` nel suo profilo, che deve avere `kind: own`. Le proposte diventano PR così:

1. `/youtube:producer` mostra le proposte in attesa e chiede **una volta per gruppo** se aprire la PR (salvo `learning_auto_pr: true` nel `config.yaml` di chi lancia). Mai l'agente da solo: il guard gli impedisce `propose-pr`, push e merge.
2. `yt-learn propose-pr` lavora nel clone indicato da `repo_path` (default `~/youtube-producer`): serve pulito (niente modifiche non committate né file nuovi non tracciati). Crea `learn/<AAAA-MM-GG>-<slug>` da `origin/main` aggiornato, applica i cambi, passa il filtro di privacy e `claude plugin validate`, fa commit e push **solo del branch** e apre la PR con `gh`, **in bozza**. Non fa mai push su `main`, non fa merge, non attiva l'auto-merge.
3. La descrizione della PR dice, in italiano, per ogni proposta: file e sezione, il cambio esatto, le prove (quanti lavori o esiti, quale segnale: scelte dell'operatore o esiti del pubblico), gli id locali delle prove, se tocca una regola dura (deve dire «nessuna» o «stringe una soglia») e l'esito del filtro di privacy.

**Cosa controlla chi rivede**:

- **Prove**: il numero di casi regge? Una lezione da 3 lavori dello stesso tipo è un indizio, non una legge: il testo del cambio deve dirlo con la stessa prudenza (`10-evidence-ledger.md`). Niente conclusioni sugli esiti con meno di 4 video.
- **Regole dure**: niente che tocchi volti, consenso, servizi a pagamento, upload, pubblicazione, gate, nomi pubblici, bordi del crop. Una soglia QA può solo stringersi; se la PR la allenta, serve una decisione scritta nella PR.
- **Privacy**: nessuna immagine con persone, nessun file del golden set o dei riferimenti, nessun testo di transcript, nessun nome di ospiti o di canali, nessun dato di clienti o di canali personali, nessun percorso personale.
- **Coerenza**: se cambia una regola di una skill, il file del knowledge pack che la governa deve dire lo stesso (e viceversa).

**Unire o chiudere.** La PR nasce in bozza: prima del merge va segnata pronta (`gh pr ready`). Si unisce con lo squash merge, come le altre PR. Una PR si può correggere sul branch prima del merge o chiudere con un commento che dice perché: al prossimo `/youtube:learn` la proposta risulta respinta e la lezione locale resta, a meno che il motivo non dica che è sbagliata (allora `/youtube:producer togli la lezione …`). Una PR unita per errore si annulla con una PR di revert, mai con un push diretto su `main`.

## Proporre una skill nuova

1. Apri una issue o una PR in bozza con: cosa fa, quando si usa (le frasi con cui la chiederesti), cosa produce, a quale gate si ferma, cosa resta fuori (per non duplicare un'altra skill).
2. Crea `plugins/youtube/commands/<nome>.md` (diventa `/youtube:<nome>`) seguendo la struttura delle altre: frontmatter `description` e `argument-hint` → «Integrazione» in italiano (lingua, parametri, dove salva, agente, confini, quando usarla) → `## Input` con `$ARGUMENTS` → in inglese «Identity and standard», «Inputs to load», procedura, «Gates», «Quality bar», «Output standards» con il formato di ritorno dell'agente, un «Worked example» con dati inventati.
3. Collega la skill all'agente: una riga nella tabella di routing di `plugins/youtube/agents/producer.md` (e in un flusso se fa parte di una pipeline) e un esempio in `commands/producer.md`.
4. Se porta metodo nuovo, mettilo nel knowledge pack (un file esistente o un `14-…` nuovo) e citane le sezioni dalla skill. Aggiungi una sezione «Learning» che dica cosa registra e quali priori legge (`13-learning-loop.md` §4.2).
5. Aggiorna la tabella delle skill in `plugins/youtube/docs/yt/DESIGN.md` §5, `plugins/youtube/docs/yt/README.md` e il `README.md` della repo.
6. Se servono comandi nuovi del toolkit: `lib/<cmd>.py` con stdout = un solo JSON (`ok`, `outputs`, `warnings`), `--help` in italiano, symlink `bin/yt-<cmd>` → `../scripts/yt/bin/_run` nella `bin/` del plugin, riga nel `scripts/yt/README.md`.
7. Per Codex: le voci della skill in `build_skills.py`, poi rigenera e lancia il test di sincronia ([Versione Codex](#versione-codex)). Un comando nuovo del toolkit entra da solo in `codex/toolkit-commands.txt` quando rigeneri.
8. Prova con `claude --plugin-dir ./plugins/youtube` e `claude plugin validate ./plugins/youtube --strict` (solo l'avviso sulla versione è ammesso), poi apri la PR.
