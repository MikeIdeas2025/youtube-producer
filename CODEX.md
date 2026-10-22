# YouTube Producer con Codex

Questa guida è per chi usa **Codex** di OpenAI al posto di Claude Code: l'app ChatGPT per Mac (dove Codex è una delle modalità) oppure la **Codex CLI** nel Terminale. Il plugin è lo stesso e arriva dalla stessa repo privata: stesse skill, stesso toolkit locale (`yt-*`), stessi profili, brand e cartelle di lavoro, stessi gate G1 e G2. **Non pubblica mai nulla**: caricare il video, impostare le thumbnail e lanciare un test A/B restano compiti tuoi, in YouTube Studio (G3).

Cosa fa il plugin, come sono fatti i profili dei canali, i brand, la configurazione e l'accesso a Google lo spiega il [README](README.md): qui c'è solo quello che in Codex cambia. Dove il README scrive `/youtube:<skill>`, in Codex scrivi **`$youtube:<skill>`**.

Le istruzioni sono state provate con la Codex CLI 0.155.0-alpha.16, quella inclusa nell'app ChatGPT per Mac 26.917, e confrontate con la documentazione di OpenAI consultata il 22 ottobre 2026. `brew install --cask codex` installa una versione più nuova (0.162.1 al 22 ottobre 2026) che con questo plugin non è ancora stata provata. Codex cambia spesso nomi e menu: se una voce non corrisponde, cerca quella con lo stesso significato e segnalacelo, con la versione che usi ([Feedback](README.md#feedback)). Nell'app le voci compaiono di solito in italiano: qui le trovi in italiano, con l'inglese tra parentesi.

## Indice

- [Cosa è uguale e cosa cambia](#cosa-è-uguale-e-cosa-cambia)
- [Requisiti](#requisiti)
- [Installazione con la CLI](#installazione-con-la-cli)
- [Installazione con l'app](#installazione-con-lapp)
- [Primo setup](#primo-setup)
- [Permessi e sandbox](#permessi-e-sandbox)
- [Il guard in Codex](#il-guard-in-codex)
- [Prova veloce (20 minuti)](#prova-veloce-20-minuti)
- [Prime richieste](#prime-richieste)
- [Come rispondere a un gate](#come-rispondere-a-un-gate)
- [Come impara](#come-impara)
- [Dati e privacy](#dati-e-privacy)
- [Dove vive cosa](#dove-vive-cosa)
- [Aggiornare](#aggiornare)
- [Problemi frequenti](#problemi-frequenti)
- [Disinstallare](#disinstallare)
- [Claude Code e Codex sullo stesso Mac](#claude-code-e-codex-sullo-stesso-mac)

## Cosa è uguale e cosa cambia

**Uguale.**

- **Il toolkit**: gli stessi comandi `yt-*` girano sul tuo Mac (ffmpeg, whisper.cpp, Playwright e Chrome, Remotion, Apple Vision, VideoToolbox). Non c'è una seconda copia: Codex usa i file del plugin.
- **Il metodo**: in Codex il Producer legge gli stessi file di agente, skill e knowledge pack che legge Claude Code. Le skill di Codex sono brevi rimandi a quei file.
- **I gate**: G1 prima di tagliare, G2 prima dei render finali di Shorts e thumbnail, G3 sempre a mano. Un gate si delega solo con una frase esplicita.
- **Local-first**: video, audio, trascrizioni e lavoro restano sul Mac. Niente servizi a pagamento dentro il lavoro: se ne servisse uno, ti arriva la richiesta con il costo e decidi tu, una chiamata alla volta.
- **YouTube in sola lettura**: OAuth con i soli permessi di lettura.
- **I tuoi dati**: `~/youtube-studio` (lavoro, database, dati appresi, segreti) e `~/.config/youtube-producer` (configurazione, profili, brand) sono gli stessi. Se usi anche Claude Code sullo stesso Mac, li condividono.

**Cambia.**

| | Claude Code | Codex |
|---|---|---|
| Come chiami il Producer | `/youtube:producer …` | `$youtube:producer …` (nella CLI anche dal menu `/skills`) |
| Chi fa il lavoro | un agente separato (`youtube:producer`), con i suoi strumenti e la sua memoria | la conversazione stessa: in Codex un plugin non può portare agenti, quindi il Producer lavora nella conversazione in cui lo chiami |
| Risposta a un gate | scrivi le decisioni | scrivi `$youtube:producer` seguito dalle decisioni: Codex non tiene attiva una skill da un messaggio all'altro |
| Guard | hook del plugin, solo per l'agente; se non parte, l'agente non può usare la shell | hook del plugin da approvare una volta, che vale per tutta la conversazione dal primo uso di YouTube Producer. Se non parte, Codex lascia passare i comandi: per questo le skill controllano che sia attivo, e altrimenti si fermano |
| Strumenti | una lista chiusa, senza connettori né servizi a pagamento | quelli della conversazione, ma il guard spegne gli strumenti MCP (connettori, browser, computer use, servizi a pagamento) nelle conversazioni di YouTube Producer |
| Comandi `yt-*` | nel PATH da soli | nel PATH tramite una cartella di lanciatori (shim) creata dal setup e una riga in `~/.zprofile` |
| Permessi | regole in `~/.claude/settings.json` | sandbox di Codex: modalità **Chiedi approvazione** (*Ask for approval*), `~/youtube-studio` come cartella del progetto e alcune cartelle scrivibili in `~/.codex/config.toml`; i comandi su video e immagini girano fuori dalla sandbox, dopo la tua approvazione |
| Revisione critica e lettore a freddo delle thumbnail (un secondo modello che guarda la thumbnail senza sapere nulla del video) | sub-agenti; il lettore a freddo può solo leggere | sub-agenti di Codex che partono senza la cronologia della conversazione; se Codex non li permette, la revisione si fa nella conversazione e lo dice, il lettore a freddo risulta «non eseguito» nel brief del G2 e non viene mai simulato |
| Memoria del Producer | `~/.claude/agent-memory/youtube-producer/MEMORY.md` | `~/youtube-studio/data/codex-memory/MEMORY.md` |
| Proposte di miglioramento (PR) | le apre il dispatcher dopo il tuo OK | le lanci tu dal Terminale, con i due comandi che ti mostra il Producer |
| HyperFrames e `/watch` | plugin di Claude Code, facoltativi | non disponibili: si usano i ripieghi (Remotion dove la licenza lo consente, template HTML, yt-dlp e fotogrammi) e il brief lo dice |
| Accesso Google (`yt-auth`) | `!yt-auth` dal prompt | dal Terminale |
| Aggiornare | `claude plugin …` e riavvio | `codex plugin marketplace upgrade …`, poi riavvio dell'app o una nuova sessione della CLI |

**Cosa si perde rispetto a Claude Code, detto chiaro.**

- **Niente agente con strumenti limitati: al suo posto c'è il guard.** In Claude Code l'agente ha una lista chiusa di strumenti. In Codex il Producer lavora nella conversazione, e in una conversazione di YouTube Producer il guard spegne gli strumenti MCP e dei plugin: connettori, browser, computer use, `node_repl`, servizi generativi o a pagamento. Il browser e il computer use potrebbero arrivare a YouTube Studio con il tuo account: per questo lì sono spenti. Una chiamata a pagamento che approvi la fai in una chat nuova, con il testo che ti prepara il Producer.
- **Il guard vale per conversazione, non per agente.** Una volta acceso, controlla anche le richieste non YouTube fatte nella stessa conversazione. Per altro lavoro apri una conversazione nuova.
- **Se l'hook non parte, Codex non blocca.** Un hook non approvato, in errore o troppo lento lascia passare il comando. Per questo `yt-config` dice se il guard ha visto la conversazione negli ultimi dieci minuti, le skill non toccano media, dati e vault finché non è così, e la sandbox tiene la rete spenta e scrivibili solo le cartelle di YouTube per i comandi che girano dentro di lei.
- **I comandi su video e immagini girano fuori dalla sandbox.** La sandbox di Codex non dà accesso a GPU, encoder video, Chrome e Apple Vision, quindi trascrizione, render e thumbnail ti chiedono l'approvazione per uscirne ([Permessi e sandbox](#permessi-e-sandbox)). Per quei comandi contano il guard e quello che approvi. Per lo stesso motivo la cartella con i programmi del plugin (ambiente Python, Node, shim) non è mai scrivibile dalla sandbox.
- **Il guard non vede quello che arriva dopo in un comando già avviato.** Per questo blocca le shell e gli interpreti interattivi e i comandi che eseguono quello che arriva dal terminale. È un controllo al meglio: non riconosce ogni forma, e il Producer ha l'istruzione di non cercarne.
- **Il lettore a freddo è «cieco» perché parte senza contesto**, non perché può solo leggere, e usa il tuo modello di Codex.
- **Le risposte ai gate devono cominciare con `$youtube:producer`.**
- **Solo Mac Apple Silicon**, come per Claude Code. Le attività cloud di Codex, l'estensione per gli editor e le modalità Chat e Work di ChatGPT non possono usare il toolkit locale.

## Requisiti

- **Il Mac**: gli stessi requisiti del [README](README.md#requisiti), tranne Claude Code: Mac Apple Silicon con macOS 14 o successivo, Google Chrome, Homebrew, Xcode Command Line Tools, `jq`, almeno 10 GB liberi per installare e 60 GB per lavorare.
- **Codex**, in una di queste due forme:
  - **l'app ChatGPT per Mac**, l'app desktop di OpenAI in cui gira Codex: scaricala da https://chatgpt.com/download/ e tienila aggiornata;
  - **la Codex CLI**, versione 0.155 o successiva: `brew install --cask codex` (oppure `npm install -g @openai/codex`). Controlla con `codex --version`, aggiorna con `brew upgrade --cask codex`.

  L'estensione di Codex per VS Code o Cursor non supporta i plugin, e le attività cloud di Codex non vedono il tuo Mac: per questo plugin servono l'app o la CLI.
- **Un piano ChatGPT che include Codex**: Plus, Pro, Business, Enterprise o Edu. Con Free e Go, Codex c'è solo nell'app desktop, con un modello più piccolo e non ancora per tutti: basta per una prova, non per lavorare su episodi interi. Su Business, Enterprise ed Edu l'amministratore può limitare plugin, marketplace e hook: se qualcosa non compare, chiedi a lui.
- **GitHub CLI** (`gh`) collegata all'account invitato sulla repo privata `MikeIdeas2025/youtube-producer`, come per Claude Code. Codex clona la repo senza poterti chiedere la password, quindi le credenziali devono già funzionare: è il compito di `gh auth setup-git`.

## Installazione con la CLI

**1. Accetta l'invito.** Ti arriva un'email da GitHub («invited you to collaborate on MikeIdeas2025/youtube-producer»). Accettalo dall'email oppure da https://github.com/MikeIdeas2025/youtube-producer/invitations, con l'account a cui è stato mandato. L'invito scade dopo 7 giorni: se è scaduto, chiedi di rimandarlo.

**2. Collega GitHub al terminale.**

```bash
brew install gh          # se non ce l'hai
gh auth login            # GitHub.com → HTTPS → accedi dal browser con l'account invitato
gh auth setup-git        # così git, e quindi Codex, clonano la repo privata con le tue credenziali
```

**3. Installa Codex e accedi.**

```bash
brew install --cask codex
codex --version          # 0.155 o successiva
codex                    # al primo avvio scegli «Sign in with ChatGPT»; poi esci con /exit
```

**4. Aggiungi il marketplace e installa il plugin.**

```bash
codex plugin marketplace add MikeIdeas2025/youtube-producer
codex plugin add youtube@youtube-producer
codex plugin list        # youtube@youtube-producer deve risultare installato e abilitato
```

Se usi una chiave SSH dell'account invitato, il primo comando può essere anche `codex plugin marketplace add git@github.com:MikeIdeas2025/youtube-producer.git`.

**5. Apri Codex nella cartella di lavoro.**

```bash
mkdir -p ~/youtube-studio
codex -C ~/youtube-studio --sandbox workspace-write
```

Al primo avvio in una cartella Codex chiede «Trust this folder?»: scegli **Trust and continue**. Il flag `--sandbox workspace-write` tiene la modalità in cui i comandi del toolkit possono scrivere nelle cartelle permesse anche finché la cartella non è stata approvata; è la stessa modalità «Chiedi approvazione» dell'app ([Permessi e sandbox](#permessi-e-sandbox)).

**6. Approva gli hook del plugin.** All'avvio Codex mostra la finestra «Hooks need review». Scegli **Trust all and continue**, oppure prima **Review hooks** per vedere cosa lanciano (`guard.sh` e `session-hint.sh`, dentro il plugin). Se la finestra non compare o l'hai saltata, li ritrovi più tardi con `/hooks`.

**7. Lancia il setup.**

```
$youtube:setup
```

Il resto è in [Primo setup](#primo-setup).

## Installazione con l'app

**1–2. Invito e GitHub**: come ai punti 1 e 2 della [CLI](#installazione-con-la-cli). Servono anche per l'app, perché anche l'app clona la repo con git.

**3. Installa l'app ChatGPT per Mac** da https://chatgpt.com/download/ e accedi con il tuo account ChatGPT.

**4. Aggiungi il marketplace.** Apri **Plugin** (*Plugins*), premi **Aggiungi** (*Add*) e scegli **Aggiungi marketplace** (*Add a marketplace*). Nella finestra «Aggiungi marketplace di plugin» (*Add plugin marketplace*), nel campo **Origine** (*Source*) scrivi `MikeIdeas2025/youtube-producer` (oppure `git@github.com:MikeIdeas2025/youtube-producer.git` se usi SSH), lascia vuoti **Riferimento Git** (*Git ref*) e **Percorsi selettivi** (*Sparse paths*) e conferma con **Aggiungi marketplace** (*Add marketplace*).

Se non trovi la voce, fai lo stesso dal Terminale: l'app legge la stessa configurazione della CLI (`~/.codex/config.toml`). Con la CLI installata: `codex plugin marketplace add MikeIdeas2025/youtube-producer`. Senza CLI puoi usare quella che è dentro l'app: `/Applications/ChatGPT.app/Contents/Resources/codex plugin marketplace add MikeIdeas2025/youtube-producer`. Poi riavvia l'app.

**5. Installa il plugin.** In **Plugin** scegli il marketplace **YouTube Producer**, apri il plugin **YouTube Producer** e installalo (**Installa plugin**, *Install plugin*, oppure il pulsante **+**).

**6. Approva gli hook.** Nella pagina del plugin, la sezione **Hook** (*Hooks*) dice «3 hook devono essere esaminati prima di poter essere eseguiti» (*3 hooks need review before they can run*). Con **Rivedi** (*Review*) vedi cosa lanciano (`guard.sh` e `session-hint.sh`, dentro il plugin); poi scegli **Autorizza tutti** (*Trust all*).

**7. Riavvia l'app** (Cmd+Q e riaprila).

**8. Apri la cartella di lavoro e lancia il setup.** Crea la cartella se non c'è (`mkdir -p ~/youtube-studio` nel Terminale), aprila nell'app come cartella del progetto, scegli **Codex** (non Chat o Work: lì il toolkit locale e gli hook del plugin non girano), lascia i permessi su **Chiedi approvazione** (*Ask for approval*) e scrivi in una **Nuova chat** (*New chat*):

```
$youtube:setup
```

## Primo setup

`$youtube:setup` fa in Codex quello che fa in Claude Code, con tre differenze: l'installazione si lancia di solito dal Terminale (2), i comandi `yt-*` hanno bisogno di una riga nel profilo della shell (3) e la sandbox di Codex ha bisogno di sapere quali cartelle il toolkit può scrivere (4). **Alle domande del setup rispondi cominciando con `$youtube:setup`** (per esempio `$youtube:setup sì, aggiungi la riga`): Codex non tiene attiva una skill da un messaggio all'altro.

**1. Controlli e piano.** Controlla i requisiti (al posto di Claude Code, la versione di Codex) e ti mostra il piano di installazione, con le dimensioni e gli extra utili ai tuoi canali, senza toccare nulla. Gli extra sono Senko, BiRefNet (nel piano compare come rembg) e MediaPipe, ognuno con il suo OK, come nella tabella del [README](README.md#installazione) (punto 6). I plugin HyperFrames e `/watch` sono di Claude Code e in Codex non ci sono: il setup lo dice e passa oltre.

**2. Installazione del toolkit.** Installa le formule Homebrew (`ffmpeg-full`, `whisper-cpp`, `yt-dlp`, `auto-editor`), i modelli di trascrizione, l'ambiente Python, i pacchetti Node per Playwright e Remotion e `thumbvision`: diversi GB scaricati dalla rete, che finiscono anche fuori dalle cartelle che la sandbox lascia scrivere. Per questo hai due strade:

- **consigliata**: la lanci tu nel Terminale. Il setup ti mostra il comando esatto, extra compresi, che è di questo tipo:

  ```bash
  bash ~/.codex/plugins/cache/youtube-producer/youtube/*/scripts/yt/install.sh --codex          # piano, non cambia nulla
  bash ~/.codex/plugins/cache/youtube-producer/youtube/*/scripts/yt/install.sh --codex --yes    # installa
  # con gli extra, per esempio tutti e tre:
  bash ~/.codex/plugins/cache/youtube-producer/youtube/*/scripts/yt/install.sh --codex --yes --with-senko --with-rembg --with-mediapipe
  ```

  Ci vogliono diversi minuti. Rilanciarla è sicuro: installa solo ciò che manca. **Quando ha finito, torna nella conversazione di Codex e scrivi `$youtube:setup`**: riprende da dove sei arrivato (riga PATH, cartelle scrivibili, domande di configurazione).
- in alternativa la lancia il setup, con un solo comando fuori dalla sandbox: Codex ti chiede di approvarlo. Leggilo prima di dire sì.

**3. I comandi `yt-*`.** Codex installa i plugin senza i collegamenti ai comandi e non li mette nel PATH. L'installazione crea quindi dei piccoli lanciatori (shim) in `~/.codex/plugins/data/youtube-youtube-producer/shims/`, e il setup ti propone di aggiungere a `~/.zprofile` una riga come questa:

```bash
export PATH="$HOME/.codex/plugins/data/youtube-youtube-producer/shims:$PATH"   # YouTube Producer (Codex)
```

La aggiunge solo con il tuo OK, e Codex ti chiede di approvare la scrittura, perché il file è fuori dalla sandbox. La riga vale per le conversazioni di Codex dopo il riavvio (punto 5) e per le finestre del Terminale che apri dopo (in una già aperta: `source ~/.zprofile`): nel Terminale ti servirà per `yt-auth` e per le proposte di miglioramento. Senza la riga il plugin funziona lo stesso: il Producer chiama i comandi con il percorso completo. Gli shim seguono da soli le versioni nuove del plugin.

**4. Le cartelle scrivibili.** Il setup stampa un blocco da incollare **a mano** in `~/.codex/config.toml`: come e dove, in [Permessi e sandbox](#permessi-e-sandbox). Il plugin e il Producer non modificano quel file.

**5. Riavvio, una volta.** Quando hai fatto i punti 3 e 4: nell'app riavvia l'app (Cmd+Q e riaprila); nella CLI chiudi Codex (`/exit`) e riaprilo con `codex -C ~/youtube-studio --sandbox workspace-write`. Poi, in una conversazione nuova, scrivi di nuovo `$youtube:setup`.

**6. Configurazione, doctor e primo canale.** Se `~/.config/youtube-producer/config.yaml` non c'è ancora, il setup ti fa le domande di configurazione: il tuo nome, se tieni le note in un vault Obsidian, se proporrai miglioramenti al plugin ([Configurazione](README.md#configurazione)). Se hai già usato il plugin con Claude Code su questo Mac, il file c'è già e vale anche qui. Poi fa il doctor e ti propone di creare il profilo del primo canale. Se il profilo scrive le note nel vault, il setup ti mostra le righe da aggiungere a `writable_roots` e ti chiede un altro riavvio.

**Hai finito quando**, in una conversazione nuova, `$youtube:setup doctor` dice **«must ko 0»** (nessun controllo obbligatorio fallito) nel riepilogo «Stato ambiente»: in Codex tra i controlli obbligatori c'è anche il guard attivo nella conversazione. Lo vedi anche chiedendo «mostrami yt-config»: la voce `codex_guard` deve dire `"active": true`. Se dice `false`, gli hook non sono approvati o non girano: vedi [Problemi frequenti](#problemi-frequenti).

**Il profilo del canale e il brand** si creano come in Claude Code ([Primi passi](README.md#primi-passi)), con il dollaro al posto della barra:

```
$youtube:setup onboard --channel=<slug> --kind=own
```

**L'accesso ai numeri di YouTube** è facoltativo e funziona come nel [README](README.md#accesso-ai-numeri-di-youtube-facoltativo), tranne il passo dell'autorizzazione: `yt-auth` apre il browser, quindi lo lanci tu nel Terminale.

```bash
yt-auth --channel <slug>
# senza la riga PATH:
~/.codex/plugins/data/youtube-youtube-producer/shims/yt-auth --channel <slug>
```

## Permessi e sandbox

In Codex i comandi girano dentro una **sandbox** di macOS: possono leggere i file, ma scrivere solo nelle cartelle permesse, e di default non vanno in rete. Quando un comando deve uscire da questi limiti, Codex ti chiede l'approvazione.

**La modalità.**

- **App**: apri `~/youtube-studio` come cartella del progetto e usa **Chiedi approvazione** (*Ask for approval*; nel menu compare come «Richiedi approvazione»), la modalità di default, nel selettore dei permessi sotto il campo di scrittura.
- **CLI**: `codex -C ~/youtube-studio --sandbox workspace-write`. Con `/permissions` vedi e cambi la modalità della sessione.
- **Approva per me** (*Approve for me*) lascia gli stessi limiti, ma le richieste di approvazione le valuta un revisore automatico al posto tuo. Finché non conosci bene il plugin, resta su **Chiedi approvazione**.
- **Mai** con questo plugin: **Accesso completo** (*Full access*, `danger-full-access`), `--dangerously-bypass-approvals-and-sandbox` (o `--yolo`), `--dangerously-bypass-hook-trust`, `approval_policy = "never"`, `network_access = true` come impostazione fissa. Il guard blocca solo i comandi pericolosi che conosce: non sostituisce sandbox e approvazioni.

**Le cartelle scrivibili.** Oltre alla cartella del progetto, il toolkit scrive nella configurazione (profili e brand compresi) e nelle cartelle del vault dove vanno le note, se usi un vault. Il setup stampa il blocco con i tuoi percorsi; usa quello, non l'esempio qui sotto.

1. Apri il file: nel Terminale `open -e ~/.codex/config.toml`; nell'app anche da **Impostazioni** → **Configurazione** → **Apri config.toml** (*Settings* → *Configuration* → *Open config.toml*).
2. Incolla il blocco **in fondo** al file, dopo tutto il resto. In cima al file ci sono impostazioni come `model = …`: se il blocco finisse sopra di loro, Codex le leggerebbe come parte della sezione e smetterebbe di vederle.
3. Se nel file c'è già una sezione `[sandbox_workspace_write]`, non incollarne un'altra: aggiungi solo i percorsi che mancano alla sua lista `writable_roots`. Se nel file c'è `default_permissions`, non incollare nulla e chiedi a chi ti ha preparato la configurazione: le due impostazioni non vanno insieme.
4. Salva e riavvia l'app (Cmd+Q e riaprila) o riapri la CLI: Codex legge il file solo all'avvio.

Il blocco ha questa forma:

```toml
# YouTube Producer — cartelle che i comandi del toolkit possono scrivere
[sandbox_workspace_write]
writable_roots = [
  "/Users/<tuo-nome>/youtube-studio",
  "/Users/<tuo-nome>/.config/youtube-producer",
  # solo se usi un vault: la cartella delle note di ogni canale, mai il vault intero
  # "/Users/<tuo-nome>/<percorso del vault>/<cartella delle note del canale>",
  # esclusa la data dir del plugin: ambiente Python, Node e shim girano anche fuori dalla sandbox
]
network_access = false   # resta spento: Codex chiede il permesso ai comandi che vanno in rete
```

Il blocco vale per tutte le tue sessioni di Codex in quella modalità, ma apre solo le cartelle di YouTube. La cartella dei programmi del plugin (`~/.codex/plugins/data/youtube-youtube-producer`) resta fuori apposta: quei programmi girano anche fuori dalla sandbox, e nessun comando della conversazione deve poterli cambiare. Se tieni `studio_dir` su un disco esterno, nel blocco c'è quel percorso al posto di `~/youtube-studio`. Se `yt-doctor` dice «cartelle scrivibili (sandbox Codex)» in rosso, il blocco manca o Codex non è stato riavviato.

**I comandi che vanno in rete** chiedono l'approvazione uno alla volta, con il motivo in una riga: `yt-dlp`, `yt-collect`, `yt-research`, `yt-outliers`, `curl`, l'installazione. Codex può proporti di ricordare un prefisso di comando: decidi tu, e non farlo per comandi generici come `curl`.

**macOS e le cartelle protette.** Se un comando risponde «Operation not permitted» su `~/Downloads`, `~/Desktop`, `~/Documents` o un disco esterno, è macOS che blocca l'accesso: in Impostazioni di Sistema → Privacy e sicurezza → File e cartelle (o Accesso completo al disco) abilita l'app da cui lanci Codex (ChatGPT, oppure Terminale o iTerm per la CLI) e riavviala.

**I comandi su video e immagini girano fuori dalla sandbox.** La sandbox di Codex non dà accesso alla GPU, agli encoder video di Apple, a Chrome né ad Apple Vision. Lo abbiamo verificato con Codex 0.155 su macOS 26: dentro la sandbox la trascrizione si interrompe, l'encoder VideoToolbox non si apre, Chrome non parte e Vision non carica i suoi modelli; fuori, gli stessi comandi funzionano. Quindi per trascrizione, render, Shorts, fotogrammi, ritratti e thumbnail (tra gli altri `yt-transcribe`, `yt-ingest`, `yt-edl-render`, `yt-clips`, `yt-frames`, `yt-timeline-view`, `yt-portrait`, `yt-thumb-render`, `yt-thumb-qa`, `yt-remotion`, `thumbvision`) il Producer chiede di lanciare il comando **fuori dalla sandbox**: Codex ti mostra il comando con il motivo e tu approvi.

- Se Codex propone di ricordare il prefisso, puoi accettarlo per un comando `yt-*` preciso (per esempio `yt-transcribe`); mai per comandi generici come `bash`, `python3`, `node` o `curl`.
- Fuori dalla sandbox restano il guard e le tue approvazioni: per quei comandi la sandbox non protegge niente.
- Configurazione, apprendimento, capitoli e note (`yt-config`, `yt-learn`, `yt-new`, `yt-chapters`, `yt-pack`…) restano dentro la sandbox, con le cartelle scrivibili qui sopra.
- Per controllare le cartelle scrivibili scrivi `$youtube:setup doctor` in una conversazione di Codex: lì il doctor gira con i permessi veri della tua sessione. Non usare `codex sandbox` per questo controllo: con `-P :workspace` (provata con Codex 0.155) ignora il blocco delle cartelle scrivibili e dà per negate anche le cartelle che hai aperto.
- `codex sandbox` serve solo a vedere perché un comando su video o immagini fallisce dentro la sandbox: nel Terminale, `codex sandbox -P :workspace -C ~/youtube-studio --log-denials -- <comando>`. La documentazione di OpenAI scrive invece `codex sandbox macos --log-denials <comando>`, che con la 0.155 non funziona: se una forma dà errore, prova l'altra. Se un comando che non è in questo elenco fallisce solo dentro Codex, segnalacelo.

## Il guard in Codex

Il **guard** (`guard.sh`) è il controllo sui comandi che il plugin porta con sé. In Codex è un hook vero del plugin, come in Claude Code, ma funziona in modo diverso.

**Cosa installa il plugin.** Tre hook: uno controlla ogni comando di shell, ogni modifica ai file e ogni strumento MCP prima che parta; uno legge i tuoi messaggi per capire quando cominci a usare YouTube Producer; uno, all'avvio, ti avvisa se manca il setup o se va rifatto. Codex non fa girare gli hook di un plugin finché non li approvi ([CLI](#installazione-con-la-cli), punto 6; [app](#installazione-con-lapp), punto 6). Se dopo un aggiornamento Codex ti chiede di nuovo di approvarli, segnalacelo: non dovrebbe succedere.

**Quando si accende.** Codex non dice all'hook chi sta lanciando un comando, quindi il guard si accende **per conversazione**, al primo segno di lavoro di YouTube Producer: un messaggio con `$youtube:`, un comando del toolkit, un file dello studio o della configurazione. Da lì vale per tutta la conversazione, anche per richieste che con YouTube non c'entrano: per altro lavoro apri una conversazione nuova. Il vault da solo non lo accende, quindi le tue note Obsidian in altre conversazioni restano libere.

**Cosa blocca.** Le stesse cose che blocca in Claude Code: pubblicazioni nel cloud, cookie di yt-dlp, `curl | sh`, `npx -y`, API a pagamento senza tua richiesta esplicita, cancellazione degli originali, scritture nel vault fuori dalle cartelle delle note, `yt-learn propose-pr`, push e PR sulla repo, anche quando sono dentro un altro comando (`bash -lc '…'`, `find -exec`). In Codex in più blocca:

- le scritture nella configurazione di Codex (`~/.codex/`), nella cartella dei programmi del plugin (anche quella della versione per Claude Code, se l'hai installata), nella copia installata del plugin e nello stato del guard;
- le shell e gli interpreti interattivi aperti senza uno script, e i comandi che eseguono quello che arriva dopo dal terminale (per esempio `cat | bash`). Questo controllo è al meglio: non riconosce ogni forma;
- un altro agente lanciato dentro Codex (`codex`, `claude`, `gemini` e simili);
- le scritture con percorsi relativi senza un `cd /percorso/assoluto` prima nello stesso comando (Codex non dice all'hook in che cartella gira il comando). Il Producer impara a usare percorsi assoluti dopo il primo blocco;
- gli strumenti MCP e dei plugin (connettori, browser, computer use, `node_repl`, servizi generativi o a pagamento).

**Cosa non vede.** Il guard legge il comando, non il contenuto degli script che lancia: `bash ./script.sh` passa anche se dentro lo script c'è un `git push`. Dentro la sandbox lo script resta limitato dalla sandbox; se Codex ti chiede di lanciarlo fuori, guarda cosa fa prima di approvare.

**Quando non arriva.** Se gli hook non sono approvati, se l'amministratore del tuo spazio di lavoro permette solo gli hook gestiti da lui, o se l'hook va in errore, Codex lascia passare i comandi. Per questo:

- `yt-config` mostra `codex_guard`: `"active": true` vuol dire che il guard ha visto questa conversazione negli ultimi dieci minuti. Ogni comando passa dall'hook, quindi con gli hook attivi è sempre così; se gli hook smettono di girare (per esempio dopo un aggiornamento da riapprovare), torna `false` con `"reason": "stale"`;
- finché è `false`, il Producer non lancia comandi su media, dati, render o vault, ti spiega come approvare gli hook e ti chiede di aprire una conversazione nuova. Il lavoro che non usa la shell (una traccia d'intervista, una strategia su dati che hai già) può continuare;
- per i comandi che restano nella sandbox, il limite vero è la sandbox: rete spenta, scrivibili solo le cartelle di YouTube. I comandi su video e immagini girano fuori dalla sandbox ([Permessi e sandbox](#permessi-e-sandbox)), solo dopo la tua approvazione: lì contano il guard e quello che approvi.

Il guard non approva niente al posto tuo e non registra il contenuto dei comandi: per ogni conversazione tiene solo un file che ha per nome l'identificativo della conversazione e dentro l'ora e il tipo di segnale che l'ha acceso, in `~/Library/Application Support/youtube-producer/codex-guard/` (i file non usati da 30 giorni si cancellano da soli).

## Prova veloce (20 minuti)

Come nel [README](README.md#prova-veloce-20-minuti): ti serve una clip di 3–5 minuti in cui parli solo tu.

```
$youtube:setup doctor
$youtube:setup onboard --channel=prova --kind=own
$youtube:producer capitoli per ~/Movies/prova.mp4, nessun ospite: ci sono solo io
```

Poi gli Shorts, per vedere un gate:

```
$youtube:producer 3 Shorts da ~/Movies/prova.mp4, nessun ospite
```

Si ferma al G2 con i candidati e le anteprime del taglio 9:16. Rispondi per esempio:

```
$youtube:producer 1 e 3, il 2 no
```

e aspetta i render in `~/youtube-studio/work/prova/…/shorts/`. Per pulire, cancella `~/youtube-studio/work/prova/`, il profilo (`~/.config/youtube-producer/channels/prova.md` e `prova.glossary.txt`) e il brand (`~/.config/youtube-producer/brands/prova/`).

Ogni richiesta consuma parecchio dei limiti del tuo piano ChatGPT: il Producer legge file lunghi (skill e knowledge pack) e ragiona molto. Parti dalle clip corte.

## Prime richieste

Usa sempre `$youtube:producer` seguito da quello che ti serve, scritto normalmente: capisce la richiesta e sceglie la skill. Cinque esempi:

```
$youtube:producer fai l'audit del canale e dimmi qual è il problema principale
$youtube:producer capitoli per il video https://www.youtube.com/watch?v=XXXXXXXXXXX
$youtube:producer 5 Shorts da ~/Movies/ep12/master.mp4
$youtube:producer tre thumbnail per ~/Movies/ep12/master.mp4, titolo «Dodici mesi da sola su un SaaS»
$youtube:producer monta l'episodio da ~/Movies/ep12/master.mp4: master 4K, sottotitoli e capitoli
```

- **Le skill singole** (`$youtube:edit`, `$youtube:shorts`, `$youtube:thumbnail`, `$youtube:learn`…) esistono anche in Codex, con gli stessi nomi della tabella del [README](README.md#cosa-fa). Codex sceglie in automatico soltanto `$youtube:producer`; le altre si chiamano scrivendole. Nella CLI le trovi anche con `/skills`. Nell'app lavora sempre in **Codex** (non in Chat o Work) e scrivi il nome per intero (`$youtube:producer`); se l'app ti propone un elenco, la skill si chiama «YouTube Producer» (il setup «YouTube Producer · Setup»).
- **Il modello.** Usa il modello più capace che il tuo piano offre in Codex, con ragionamento alto: nella CLI `/model`, scegli il modello e poi **High**; Max e Ultra (sotto «More reasoning…») consumano i limiti più in fretta e per questo plugin non servono. Nell'app, il selettore del modello sotto il campo di scrittura.
- **La liberatoria degli ospiti.** Per montaggio, Shorts e thumbnail il Producer ti chiede se c'è la liberatoria e cosa copre, come in Claude Code. Se nel video ci sei solo tu, scrivilo già nella richiesta.
- **I render lunghi.** Trascrizione e render di un episodio di un'ora richiedono decine di minuti. Codex resta in attesa nella conversazione mentre i comandi lavorano; se deve chiudere la risposta, il Producer scrive `stato: render in corso`, quanto manca e come controllare. Dopo, chiedi `$youtube:producer a che punto è il render dell'episodio 12?`. Non c'è la notifica di fine lavoro che dà Claude Code.

## Come rispondere a un gate

Il brief è lo stesso di Claude Code ([README](README.md#come-rispondere-a-un-gate)) ed è salvato in `<cartella di lavoro>/qa/gate-G1.md` (o `gate-G2.md`). In fondo trovi le decisioni numerate e la riga «Per continuare rispondi con `$youtube:producer` e le tue decisioni». Rispondi così, una riga per decisione:

```
$youtube:producer 1) cold open V2; 2) tagli ok tranne il 3, che resta; 3) capitoli ok
```

- **Comincia sempre con `$youtube:producer`.** Codex non tiene attiva una skill da un messaggio all'altro: senza il prefisso potrebbe rispondere senza il metodo del Producer. Se te ne accorgi, riscrivi la risposta con il prefisso.
- Puoi rispondere solo ad alcune decisioni: il Producer ti chiede le altre. Un «ok» o un «vai» generico non basta.
- **Delega**: `$youtube:producer G1 delegato: scegli tu`. Applica le scelte che ti aveva consigliato e te le elenca; un problema grave lo ferma lo stesso.
- **Riprendere in un'altra conversazione.** Lo stato del lavoro è nei file della cartella di lavoro (`project.json` e i brief in `qa/`), quindi puoi riprendere anche domani, in una conversazione nuova: `$youtube:producer riprendi l'episodio in ~/youtube-studio/work/<canale>/<cartella>: 1) cold open V2; 2) …`.

## Come impara

Come in Claude Code ([README](README.md#come-impara)): dopo ogni lavoro il Producer registra in locale le tue scelte, le correzioni e, nelle review, gli esiti, e aggiorna per ogni canale preferenze, lezioni, glossario appreso e playbook. I dati stanno in `~/youtube-studio/data/`, gli stessi se usi anche Claude Code. `$youtube:learn` (o «cosa hai imparato sulle thumbnail?») ti dà il rapporto.

**Le proposte di miglioramento** (Tier B, facoltativo e spento di default) cambiano in un punto: in Codex la pull request non parte dalla conversazione. Il Producer ti mostra le proposte e ti chiede una volta se aprire la PR; se dici sì, ti dà due comandi da lanciare nel tuo Terminale:

```bash
yt-learn propose-pr --dry-run     # cosa cambierebbe, senza toccare nulla
yt-learn propose-pr               # crea il branch learn/…, fa push del solo branch e apre la PR in bozza
```

Lavorano nel tuo clone della repo (`repo_path`, default `~/youtube-producer`; se non c'è: `gh repo clone MikeIdeas2025/youtube-producer ~/youtube-producer`). `learning_auto_pr: true` in Codex non vale: chiede sempre.

## Dati e privacy

- **Cosa resta sul Mac.** Video, audio, trascrizioni, cartelle di lavoro e database: il toolkit gira in locale e non carica file su servizi esterni.
- **Cosa passa da OpenAI.** In Codex il Producer è il modello di OpenAI: per lavorare legge a blocchi il trascritto, guarda alcuni fotogrammi e le thumbnail, legge i numeri del canale e l'output dei comandi. Questi contenuti arrivano a OpenAI come in ogni conversazione di Codex, alle condizioni del tuo piano ChatGPT. Sui piani personali (Plus, Pro) controlla in **Impostazioni → Controlli dei dati** se le tue conversazioni possono servire ad addestrare i modelli (https://help.openai.com/en/articles/7730893-data-controls-faq); su Business, Enterprise ed Edu i dati di lavoro non si usano per l'addestramento, salvo scelte diverse dell'organizzazione.
- **Ospiti e liberatoria.** Agli ospiti di' che i file restano in locale e che un assistente AI ne legge degli estratti per montare. La checklist della liberatoria (`plugins/youtube/docs/yt/knowledge/11-compliance-safety.md` §6.4, punti 7 e 8) fa l'esempio di Anthropic: se monti con Codex, il fornitore da citare è OpenAI (tutti e due, se usi entrambi), con il trasferimento extra-UE. Non è un parere legale.
- **Segreti** (`client_secret.json`, `api_key`, token) solo in `~/youtube-studio/secrets/`: mai in chat. Il Producer ne controlla solo la presenza e i permessi, mai il contenuto.
- **Gli hook non registrano nulla** del contenuto dei comandi ([Il guard in Codex](#il-guard-in-codex)).
- **Niente nella repo**: le stesse regole del README. Profili, brand, dati di apprendimento e media restano sul tuo Mac.

## Dove vive cosa

| Cosa | Dove |
|---|---|
| Plugin installato | `~/.codex/plugins/cache/youtube-producer/youtube/<versione>/` (non modificarlo: si sovrascrive al primo aggiornamento) |
| Dipendenze (venv, Node, thumbvision, MediaPipe) e shim dei comandi `yt-*` | `~/.codex/plugins/data/youtube-youtube-producer/` |
| Modelli di trascrizione | `~/.whisper-models/` |
| Extra Senko e BiRefNet | `~/.venvs/senko/`, `~/.venvs/rembg/` |
| Configurazione, profili, glossari e brand | `~/.config/youtube-producer/` |
| Lavoro, database, dati appresi, segreti | `~/youtube-studio/` (`work/`, `data/`, `secrets/`) |
| Memoria del Producer in Codex | `~/youtube-studio/data/codex-memory/MEMORY.md` |
| Stato del guard | `~/Library/Application Support/youtube-producer/codex-guard/` |
| Configurazione di Codex (marketplace, plugin, cartelle approvate, hook approvati, sandbox) | `~/.codex/config.toml`: Codex ci scrive marketplace, plugin e approvazioni; il plugin e il Producer non lo modificano; le cartelle scrivibili le aggiungi tu |

## Aggiornare

```bash
codex plugin marketplace upgrade youtube-producer   # rilegge la repo e reinstalla il plugin
```

Poi riavvia: nella CLI chiudi e riapri Codex; nell'app riavvia l'app (Cmd+Q e riaprila). Se l'avviso all'avvio lo chiede, lancia `$youtube:setup install`: installa solo ciò che manca e, se le dipendenze non sono cambiate, finisce in pochi secondi. Gli shim seguono da soli la versione nuova e le approvazioni degli hook restano valide. L'aggiornamento non tocca i tuoi dati.

Il comando si lancia nel Terminale anche se usi solo l'app; senza CLI usa quella dentro l'app (`/Applications/ChatGPT.app/Contents/Resources/codex plugin marketplace upgrade youtube-producer`).

## Problemi frequenti

| Problema | Cosa fare |
|---|---|
| `$youtube:…` non compare o Codex non lo riconosce | Riavvia l'app (nella CLI apri una sessione nuova). Poi `codex plugin list`: `youtube@youtube-producer` deve essere installato e abilitato (nella CLI, `/plugins` e barra spaziatrice sul plugin per abilitarlo). Se manca, ripeti il punto 4 dell'installazione. Nell'app controlla di essere in Codex, non in Chat o Work. Ricorda che Codex sceglie in automatico soltanto `$youtube:producer`: le altre skill vanno scritte |
| «Repository not found», o il marketplace non si aggiunge | Non hai accettato l'invito, l'hai accettato con un altro account GitHub, oppure manca `gh auth setup-git`. Controlla con `gh repo view MikeIdeas2025/youtube-producer`. Codex non può chiederti la password: le credenziali devono già funzionare |
| Il clone via SSH fallisce («Permission denied (publickey)») | Hai una chiave SSH di un altro account: usa la forma `MikeIdeas2025/youtube-producer` (HTTPS) dopo `gh auth setup-git` |
| All'avvio Codex dice che degli hook vanno rivisti | Sono quelli del plugin: approvali (CLI: finestra «Hooks need review» → **Trust all and continue**, oppure `/hooks`; app: pagina del plugin → **Hook** → **Autorizza tutti**, *Trust all*), poi una conversazione nuova |
| Il Producer dice che il guard non è attivo (`codex_guard` con `"active": false`) e non lancia comandi | Gli hook non sono approvati o non girano più (`"reason": "stale"`: per esempio da riapprovare dopo un aggiornamento). Approvali e apri una conversazione nuova. Se lavori in un'organizzazione che permette solo gli hook gestiti dall'amministratore, gli hook dei plugin non girano mai: chiedi all'amministratore, oppure usa il plugin con Claude Code |
| `yt-config: command not found` (o un altro `yt-*`) | Manca la riga PATH, oppure l'app non è stata riavviata (nella CLI: sessione vecchia). Se gli shim non ci sono, `$youtube:setup install`. Senza riga PATH il Producer usa il percorso completo `~/.codex/plugins/data/youtube-youtube-producer/shims/yt-…`. Nel Terminale la riga vale per le finestre aperte dopo (`source ~/.zprofile` in quella aperta) |
| Un comando risponde «Toolkit non installato» | L'installazione del [Primo setup](#primo-setup) (punto 2) non è stata fatta o non è finita: rilanciala |
| L'avviso «manca il setup» continua a comparire | Lancia `$youtube:setup install` (non solo `$youtube:setup`, che con il setup già fatto riprende dai passi che mancano e poi fa il doctor), poi una conversazione nuova. Se resta, chiedi «mostrami yt-config» e controlla `data_dir`, `setup_ok` e `setup_current` |
| Un comando viene bloccato dal guard | È voluto ([Il guard in Codex](#il-guard-in-codex)). Se il messaggio dice di usare un percorso assoluto, il Producer rifà il comando così. Se l'operazione ti serve davvero ed è sicura, falla tu nel Terminale |
| Troppe richieste di approvazione, o `yt-doctor` segnala «cartelle scrivibili (sandbox Codex)» | Apri `~/youtube-studio` come cartella del progetto, incolla il blocco delle [cartelle scrivibili](#permessi-e-sandbox) in fondo a `~/.codex/config.toml` e riavvia l'app (nella CLI: riapri Codex). I comandi che vanno in rete e quelli su video e immagini (fuori dalla sandbox) chiedono comunque; per un comando `yt-*` preciso puoi far ricordare il prefisso quando Codex lo propone |
| Codex parte in sola lettura e non scrive nulla (CLI) | La cartella non è ancora stata approvata e hai aperto Codex senza `--sandbox workspace-write`: riaprilo con `codex -C ~/youtube-studio --sandbox workspace-write` e alla domanda «Trust this folder?» scegli **Trust and continue**, oppure cambia modalità con `/permissions` |
| «Operation not permitted» leggendo il girato | macOS blocca l'accesso: Impostazioni di Sistema → Privacy e sicurezza → File e cartelle, abilita l'app da cui lanci Codex e riavviala |
| Un comando del toolkit fallisce solo dentro Codex (trascrizione che si interrompe con «Abort trap», thumbnail con «browserType.launch», encode con «Could not open encoder», `thumbvision` con «ANECF error») | È la sandbox: GPU, encoder video, Chrome e Apple Vision non sono disponibili dentro la sandbox. Approva quel comando fuori dalla sandbox quando Codex lo chiede ([Permessi e sandbox](#permessi-e-sandbox)). Per vedere cosa è stato negato, nel Terminale: `codex sandbox -P :workspace -C ~/youtube-studio --log-denials -- <comando>` (oppure `codex sandbox macos --log-denials <comando>`). Questa prova ignora le cartelle scrivibili del blocco: guarda le negazioni su GPU, encoder, Chrome e Vision, non quelle sulle cartelle dello studio |
| Il Producer riparte da capo invece di applicare la tua risposta al gate | La risposta non cominciava con `$youtube:producer`: riscrivila con il prefisso. Il lavoro riprende dai file della cartella di lavoro |
| La risposta si è chiusa durante un render | `$youtube:producer a che punto è il render di …`. Se il processo non c'è più, il Producer lo rilancia: i comandi riprendono da dove possono |
| Lavori dentro il tuo clone della repo e Codex mostra due marketplace `youtube-producer` | Codex vede anche il marketplace della repo in cui sei. Apri Codex fuori dal clone (per esempio in `~/youtube-studio`) |
| MediaPipe manca, le thumbnail non si renderizzano, spazio disco insufficiente, l'accesso Google scade ogni settimana | Come in Claude Code: [Problemi frequenti del README](README.md#problemi-frequenti), con `$youtube:` al posto di `/youtube:` |

Per tutto il resto: `$youtube:setup doctor` dice cosa manca e cosa ne risente. Quando apri una issue ([Feedback](README.md#feedback)), scrivi che usi Codex, la versione (`codex --version`, oppure la versione dell'app) e se lavori con l'app o con la CLI.

## Disinstallare

```bash
codex plugin remove youtube@youtube-producer        # rimuove il plugin
codex plugin marketplace remove youtube-producer    # facoltativo: toglie anche il marketplace
```

Nell'app puoi togliere il plugin anche da **Plugin** → **Installati** (*Installed*).

Codex tiene la cartella dei dati del plugin anche dopo la disinstallazione. Se vuoi togliere tutto, a mano:

- `~/.codex/plugins/data/youtube-youtube-producer/` (ambiente Python, Node, shim);
- la riga `# YouTube Producer (Codex)` in `~/.zprofile`;
- le righe di YouTube Producer in `writable_roots` di `~/.codex/config.toml`;
- `~/Library/Application Support/youtube-producer/` (stato del guard).

I tuoi dati non si toccano: `~/youtube-studio/` (lavoro, database, segreti, dati appresi, memoria del Producer), `~/.config/youtube-producer/`, `~/.whisper-models/`, `~/.venvs/senko/`, `~/.venvs/rembg/`. Toglili solo se non ti servono più, e solo se non usi il plugin anche con Claude Code. Le formule Homebrew (`ffmpeg-full`, `whisper-cpp`, `yt-dlp`, `auto-editor`) toglile con `brew uninstall` solo se non le usi per altro.

## Claude Code e Codex sullo stesso Mac

Puoi usarli tutti e due.

- **Condividono** configurazione, profili, brand, cartelle di lavoro, database e dati appresi: un canale creato in uno si vede nell'altro, e quello che il Producer impara vale per tutti e due.
- **Ognuno ha la sua installazione del toolkit** (ambiente Python, Node, thumbvision) nella propria cartella dei dati. La prima volta in Codex lancia comunque `$youtube:setup`: formule Homebrew, modelli di trascrizione ed extra in `~/.venvs/` sono già sul Mac e non si riscaricano.
- **La memoria del Producer è separata**: in Claude Code sta in `~/.claude/agent-memory/youtube-producer/`, in Codex in `~/youtube-studio/data/codex-memory/`.
- **La riga PATH di Codex non disturba Claude Code**: dentro Claude Code i comandi `yt-*` restano quelli del plugin di Claude.
- **Non importare il plugin da Claude Code** con `/import` di Codex: installalo dal marketplace come in questa guida, così prende la versione per Codex.
- Non lavorare sullo stesso episodio con tutti e due nello stesso momento.
