# YouTube Producer — plugin YouTube per Claude Code e Codex

**YouTube Producer** è un agente per Claude Code e Codex che lavora come producer e strategist di un canale YouTube, sul tuo Mac. Da un episodio registrato ricava il video montato con la timeline per Final Cut o Resolve, i sottotitoli italiani, i capitoli, gli Shorts, tre thumbnail con il controllo di leggibilità e un piano di test. Legge anche i numeri del canale, fa audit e strategia, scrive la traccia dell'intervista e i primi 30 secondi.

Prima delle scelte importanti si ferma e aspetta te: sono i **gate** G1 (prima di tagliare) e G2 (prima dei render finali). **Non pubblica mai nulla**: caricare il video, impostare le thumbnail e lanciare un test A/B restano compiti tuoi, in YouTube Studio (G3).

La repo è privata. È un marketplace di Claude Code e di Codex (`youtube-producer`) con un solo plugin: `youtube`. Nel plugin non c'è nessun canale precaricato: alla prima configurazione crei il profilo del tuo.

## Usarlo con Codex

Il plugin funziona anche con **Codex** di OpenAI (l'app ChatGPT per Mac o la Codex CLI), dalla stessa repo e con lo stesso toolkit locale. Le skill si chiamano con `$` al posto di `/` e alcune cose funzionano in modo diverso: installazione, permessi e differenze sono in **[CODEX.md](CODEX.md)**. Il resto di questo README vale per Claude Code.

| | Come lo chiami | Chi lavora | Guard (controllo sui comandi) | Guida |
|---|---|---|---|---|
| **Claude Code** | `/youtube:producer …` | un agente separato, con strumenti e memoria propri | hook del plugin, solo per l'agente; se non parte, l'agente non può usare la shell | questo README |
| **Codex** (app ChatGPT o CLI) | `$youtube:producer …`, anche per rispondere ai gate | la conversazione stessa: in Codex i plugin non portano agenti | hook del plugin da approvare una volta, vale per tutta la conversazione; se non parte, le skill non lanciano comandi su media, dati e vault | [CODEX.md](CODEX.md) |

Gate G1 e G2, pubblicazione sempre a mano, file in locale, profili, brand e cartelle di lavoro sono gli stessi. Se usi tutti e due sullo stesso Mac, condividono configurazione, lavoro e dati appresi.

## Indice

- [Usarlo con Codex](#usarlo-con-codex)
- [Cosa fa](#cosa-fa)
- [Come funziona](#come-funziona)
- [Requisiti](#requisiti)
- [Installazione](#installazione)
- [Dove lanciare Claude Code e i permessi](#dove-lanciare-claude-code-e-i-permessi)
- [Prova veloce (20 minuti)](#prova-veloce-20-minuti)
- [Primi passi](#primi-passi)
- [Come rispondere a un gate](#come-rispondere-a-un-gate)
- [Configurazione](#configurazione)
- [Come impara](#come-impara)
- [Dati e privacy](#dati-e-privacy)
- [Accesso ai numeri di YouTube (facoltativo)](#accesso-ai-numeri-di-youtube-facoltativo)
- [Aggiornare](#aggiornare)
- [Problemi frequenti](#problemi-frequenti)
- [Disinstallare](#disinstallare)
- [Licenze e crediti](#licenze-e-crediti)
- [Feedback](#feedback)
- [Struttura della repo](#struttura-della-repo)

## Cosa fa

Usa sempre il punto d'ingresso, `/youtube:producer`, seguito da quello che ti serve scritto normalmente: capisce la richiesta, sceglie la skill e lancia l'agente. Le skill singole della tabella esistono per chi conosce già il flusso; anche se le scrivi a mano, rimandano all'agente, perché solo lì valgono il controllo sui comandi e la memoria del canale.

| Skill | A cosa serve | Esempio di richiesta |
|---|---|---|
| `/youtube:producer <richiesta>` | **Punto d'ingresso.** Capisce la richiesta, lancia l'agente, ti mostra i riepiloghi dei gate e riporta le tue decisioni all'agente | `/youtube:producer monta l'episodio da ~/Movies/ep12/master.mp4` |
| `/youtube:setup` | Installazione, configurazione, controllo dell'ambiente (il «doctor»), creazione del profilo di un canale, aggiornamenti | `/youtube:setup onboard --channel=caffe-maker --kind=own` |
| `/youtube:channel-audit` | Audit del canale: quali dati sono disponibili, situazione attuale, confronto dei video a pari età (per esempio dopo 28 giorni), titoli e thumbnail, anomalie e **un** problema principale da risolvere | `/youtube:producer fai l'audit del mio canale` |
| `/youtube:strategy` | Posizionamento, temi fissi, formati, metriche, appuntamenti con la community, calendario di 8–12 settimane con un esperimento a settimana | `/youtube:producer strategia per i prossimi 3 mesi` |
| `/youtube:research` | Video esplosi nei canali simili, concorrenti, analisi dei primi 30–60 secondi di un video, commenti, cosa cerca il pubblico in italiano | `/youtube:producer quali video sono esplosi nei canali simili al mio?` |
| `/youtube:review` | Numeri a 48 ore, settimanali, mensili, trimestrali: retention, titoli e thumbnail, test A/B, Shorts, esperimenti | `/youtube:producer com'è andato l'ultimo episodio a 48 ore` |
| `/youtube:story` | Dal girato alla storia (momenti migliori, scaletta, montaggio su carta), traccia dell'intervista prima di registrare, script per i video in solitaria | `/youtube:producer traccia d'intervista per l'ospite di giovedì` |
| `/youtube:hook` | 10 aperture in 5 stili, con una griglia di valutazione, e 3 cold open montati dal girato | `/youtube:producer tre cold open per ~/Movies/ep12/master.mp4` |
| `/youtube:edit` | Montaggio long-form: tagli approvati al G1, audio a −14 LUFS, grafiche, sottotitoli, master 4K e timeline FCPXML | `/youtube:producer monta l'episodio 12, master 4K` |
| `/youtube:shorts` | Shorts dal girato: momenti candidati con punteggio, scelta al G2, formato 9:16, sottotitoli impressi, controllo dei fotogrammi, piano di pubblicazione | `/youtube:producer 5 Shorts da ~/Movies/ep12/master.mp4` |
| `/youtube:chapters` | Capitoli validati e agganciati alle pause, anche sugli episodi già pubblicati | `/youtube:producer capitoli per i video già pubblicati` |
| `/youtube:thumbnail` | 3 proposte su idee diverse, volti veri scontornati, template grafici, controllo di leggibilità, scelta al G2 e piano di test | `/youtube:producer tre thumbnail per ~/Movies/ep12/master.mp4, titolo «Dodici mesi da sola su un SaaS»` |
| `/youtube:learn` | Cosa ha imparato l'agente sul canale: esiti, preferenze, lezioni, proposte di miglioramento | `/youtube:producer cosa hai imparato sulle thumbnail?` |

**Gate delegati.** Se a un gate non vuoi fermarti, dillo in modo esplicito: «G1 delegato: scegli tu» oppure «vai fino al G2 con le scelte consigliate». L'agente scrive comunque il riepilogo e fa comunque la revisione critica, poi applica le scelte che ti avrebbe consigliato e te le elenca. Un problema grave lo ferma lo stesso.

## Come funziona

- L'agente (`youtube:producer`) legge il metodo dal knowledge pack del plugin e usa una trentina di comandi `yt-*` che girano sul tuo Mac: ffmpeg, whisper.cpp con Parakeet per la trascrizione, Senko per capire chi parla, Playwright e Chrome per le thumbnail, Remotion o HyperFrames per le grafiche, VideoToolbox per l'encode.
- **Tre gate.** Al **G1**, prima di tagliare, ti mostra la strategia del montaggio, i tagli, i cold open e i rischi. Al **G2**, prima dei render finali di Shorts e thumbnail, ti mostra candidati, punteggi e anteprime. Ogni gate arriva come **brief**: un riepilogo con le opzioni e le decisioni numerate che ti chiede ([Come rispondere a un gate](#come-rispondere-a-un-gate)). Il **G3** è la pubblicazione: la fai tu, con la checklist che l'agente ti prepara.
- L'accesso a YouTube è in sola lettura per costruzione (OAuth con i soli permessi di lettura): l'agente non carica video, non cambia titoli o thumbnail, non lancia test A/B.
- I file restano sul Mac; quello che l'agente legge per lavorare passa da Claude. Video, audio, trascrizioni e lavoro restano in locale e nessun file viene caricato su servizi esterni. Gli estratti del trascritto, i fotogrammi e i numeri che l'agente legge passano invece da Claude (Anthropic), come in ogni sessione di Claude Code ([Dati e privacy](#dati-e-privacy)).
- Niente servizi a pagamento dentro l'agente. Se una chiamata a pagamento servisse davvero, l'agente ti scrive la richiesta con il costo e la decidi tu, una chiamata alla volta.
- Un controllo sui comandi, il **guard** (`guard.sh`, un hook del plugin), blocca i comandi pericolosi dell'agente: pubblicazioni nel cloud, cookie di yt-dlp, `curl | sh`, API a pagamento, cancellazione degli originali, push e merge sulla repo. Vale solo per l'agente, non per le tue sessioni. Il guard blocca e basta: non approva niente al posto tuo, i permessi di Claude Code restano quelli che imposti tu.
- **Dove finiscono i file.** Ogni episodio ha una cartella di lavoro `~/youtube-studio/work/<canale>/<data>-<slug>/` con analisi, montaggio, consegne (`deliver/`), Shorts, thumbnail, controlli (`qa/`) e note (`deliver/notes/`). Gli originali restano dove sono: nella cartella di lavoro ci sono solo collegamenti. Le note che non riguardano un video (audit, strategia, review) vanno in `~/youtube-studio/work/<canale>/deliver/notes/`. Per aprire la cartella di un canale nel Finder: `open ~/youtube-studio/work/<canale>`.

## Requisiti

- **Mac con Apple Silicon** (M1 o successivi) e **macOS 14 Sonoma o successivo** (consigliato macOS 15: alcune misure estetiche delle thumbnail ci sono solo da lì). Sui Mac Intel non funziona.
- **Google Chrome** installato: serve a renderizzare le thumbnail.
- **Claude Code ≥ 2.1.295**: controlla con `claude --version`; se è più vecchio, `claude update`.
- **Homebrew** (https://brew.sh) e **Xcode Command Line Tools** (`xcode-select --install`).
- **GitHub CLI** (`gh`) autenticata con l'account GitHub invitato sulla repo privata `MikeIdeas2025/youtube-producer` (passo 1 dell'installazione).
- **Spazio disco**: almeno **10 GB liberi per installare** (circa 5 GB per modelli e dipendenze, circa 7 GB con tutti gli extra) e almeno **60 GB liberi per lavorare** sul disco che contiene `~/youtube-studio`: un episodio 4K produce file intermedi da 15–25 GB per passata, e sotto questa soglia le skill di produzione non partono. Se sul Mac non hai tanto spazio, la cartella di lavoro può stare su un SSD esterno ([Prova veloce](#prova-veloce-20-minuti), punto 1).
- `jq` (incluso in macOS 15 e successivi; su macOS 14 `brew install jq`).

## Installazione

Sette passi, in quest'ordine. Il setup vero e proprio lo fa `/youtube:setup` dentro Claude Code.

**1. Accetta l'invito.** Ti arriva un'email da GitHub («invited you to collaborate on MikeIdeas2025/youtube-producer»). Accettalo dall'email oppure da https://github.com/MikeIdeas2025/youtube-producer/invitations, collegato all'account GitHub a cui è stato mandato. L'invito scade dopo 7 giorni: se è scaduto, chiedi di rimandarlo. Senza questo passo l'installazione fallisce con «repository not found».

**2. Collega GitHub al terminale.**

```bash
brew install gh          # se non ce l'hai
gh auth login            # GitHub.com → HTTPS → accedi dal browser con l'account invitato
gh auth setup-git        # così git, e quindi Claude Code, clonano la repo privata con le tue credenziali
```

**3. Aggiungi il marketplace e installa il plugin.** Nel terminale:

```bash
claude plugin marketplace add MikeIdeas2025/youtube-producer
claude plugin install youtube@youtube-producer
```

In alternativa, un solo comando che aggiunge il marketplace e installa il plugin: `claude plugin install youtube --marketplace MikeIdeas2025/youtube-producer`. Dentro Claude Code funzionano anche `/plugin marketplace add MikeIdeas2025/youtube-producer` e poi `/plugin install youtube@youtube-producer`.

**4. Riavvia Claude Code.** Chiudilo e riaprilo: i comandi `/youtube:*` e gli hook del plugin si caricano all'avvio. Alla prima sessione dovresti vedere un avviso del plugin che ti chiede di lanciare il setup; se non lo vedi, vai avanti lo stesso.

**5. Lancia il setup.** In Claude Code:

```
/youtube:setup
```

Controlla i requisiti, ti mostra il piano di installazione (senza toccare nulla) e installa ciò che manca: lanciare `/youtube:setup` vale come OK per l'installazione di base. Installa le formule Homebrew (`ffmpeg-full`, `whisper-cpp`, `yt-dlp`, `auto-editor`), i modelli di trascrizione, l'ambiente Python, i pacchetti Node per Playwright e Remotion e `thumbvision`. Ci vogliono diversi minuti, e Claude Code ti chiederà alcuni permessi ([Dove lanciare Claude Code e i permessi](#dove-lanciare-claude-code-e-i-permessi)). Rilanciarlo è sicuro: installa solo ciò che manca.

**6. Scegli gli extra.** `/youtube:setup` li propone a parte e chiede un OK per ognuno:

| Extra | A cosa serve | Spazio | Senza |
|---|---|---|---|
| Senko | capire chi parla. Serve a `/youtube:story` e `/youtube:shorts` sui podcast con più voci | ~560 MB | ti chiede chi parla quando serve |
| BiRefNet (nel piano compare come rembg) | scontorno dei ritratti per le thumbnail | ~1,3 GB | usa Apple Vision, con bordi peggiori |
| MediaPipe | espressioni dei volti per scegliere i frame delle thumbnail, e controllo che il bianco e nero non alteri i volti | ~200 MB + un modello da 4 MB | solo la geometria di Apple Vision; il controllo dei punti del volto resta un avviso |
| Plugin HyperFrames | grafiche animate (lower third, card), sottotitoli dietro il soggetto, rimontaggio dei talking head. È il motore grafico di default | dipende dalla versione | niente grafiche animate finché non confermi la licenza Remotion per il tuo canale ([Licenze](#licenze-e-crediti)); montaggio, sottotitoli e thumbnail funzionano lo stesso |
| Plugin `/watch` | fotogrammi e sottotitoli per analizzare i primi secondi dei video di altri canali | piccolo | analisi solo dai sottotitoli |

Se hai un podcast, conviene installarli tutti. I plugin di terzi si installano con un comando che `/youtube:setup` ti mostra; dopo averne installato uno, riavvia Claude Code.

**7. Rispondi alle domande di configurazione.** `/youtube:setup` ti chiede il tuo nome (lo usa per rivolgersi a te), se tieni le note in un vault Obsidian (facoltativo) e se proporrai miglioramenti al plugin. Scrive `~/.config/youtube-producer/config.yaml` ([Configurazione](#configurazione)), fa il doctor e ti propone di creare il profilo del primo canale ([Primi passi](#primi-passi)).

**Hai finito quando** il riepilogo «Stato ambiente» del setup dice **«must ko 0»**, cioè nessun controllo obbligatorio fallito. Un esito giallo va bene se dipende da cose facoltative: l'accesso Google che non hai ancora configurato, un extra che non hai installato. Un esito rosso per spazio disco sotto i 60 GB va risolto prima di lavorare ([Problemi frequenti](#problemi-frequenti)). Puoi ricontrollare quando vuoi con `/youtube:setup doctor`.

## Dove lanciare Claude Code e i permessi

L'agente lancia molti comandi (`yt-ingest`, `yt-transcribe`, ffmpeg…) e scrive fuori dalla cartella in cui hai aperto Claude Code: in `~/youtube-studio` (lavoro) e in `~/.config/youtube-producer` (profili e brand). Legge inoltre il girato dove lo tieni (`~/Movies`, `~/Downloads`, un disco esterno). In modalità normale Claude Code ti chiede il permesso per ognuna di queste azioni, anche quando l'agente lavora in background.

- **Apri Claude Code dalla cartella di lavoro**, così la maggior parte dei file è «dentro» la sessione:

  ```bash
  mkdir -p ~/youtube-studio && cd ~/youtube-studio && claude
  ```

  Per le altre cartelle usa `/add-dir` nella sessione (per esempio `/add-dir ~/.config/youtube-producer` e `/add-dir ~/Movies`), oppure la lista permanente qui sotto.
- **Riduci le richieste di permesso** con una lista di regole in `~/.claude/settings.json` (se il file esiste già, aggiungi solo le voci che mancano dentro `permissions`):

  ```json
  {
    "permissions": {
      "allow": [
        "Bash(yt-*)",
        "Bash(thumbvision *)",
        "Read(~/youtube-studio/**)",
        "Edit(~/youtube-studio/**)",
        "Write(~/youtube-studio/**)",
        "Edit(~/.config/youtube-producer/**)",
        "Write(~/.config/youtube-producer/**)"
      ],
      "additionalDirectories": ["~/youtube-studio", "~/.config/youtube-producer"]
    }
  }
  ```

  Le altre richieste (ffmpeg, `jq`, letture del girato) continuano ad arrivare: leggile prima di approvarle. Se ne neghi una, l'agente di solito si ferma e ti dice cosa non ha potuto fare; rilancia la richiesta dopo aver dato il permesso.
- **Non usare mai la modalità `bypassPermissions`** (né `--dangerously-skip-permissions`) con questo plugin: il guard blocca solo i comandi pericolosi che conosce, non sostituisce i permessi.
- **macOS e le cartelle protette.** Se un comando risponde «Operation not permitted» su `~/Downloads`, `~/Desktop`, `~/Documents` o un disco esterno, è macOS che blocca l'accesso: in Impostazioni di Sistema → Privacy e sicurezza → File e cartelle (o Accesso completo al disco) abilita l'app da cui lanci Claude Code (Terminale, iTerm o l'app Claude), poi riavviala.

## Prova veloce (20 minuti)

Per provarlo prima di usarlo su un episodio vero. Ti serve una clip di 3–5 minuti in cui parli solo tu, registrata con il telefono o la webcam.

1. **Controlla lo spazio.** `/youtube:setup doctor`. Se l'esito è rosso per lo spazio disco (sotto i 60 GB liberi), sposta la cartella di lavoro su un disco esterno: in `~/.config/youtube-producer/config.yaml` scrivi `studio_dir: "/Volumes/<nome del disco>/youtube-studio"` e rilancia il doctor.
2. **Crea un profilo di prova.**

   ```
   /youtube:setup onboard --channel=prova --kind=own
   ```

   Rispondi solo alle domande che sai; il resto resta `[DA COMPILARE]` e va bene così per una prova.
3. **Chiedi i capitoli**, il lavoro più rapido:

   ```
   /youtube:producer capitoli per ~/Movies/prova.mp4, nessun ospite: ci sono solo io
   ```

   «Nessun ospite» evita la domanda sulla liberatoria (sotto, [Primi passi](#3-prime-richieste)). L'agente importa la clip, la trascrive e ti restituisce i capitoli da incollare nella descrizione.
4. **Poi gli Shorts**, per vedere un gate:

   ```
   /youtube:producer 3 Shorts da ~/Movies/prova.mp4, nessun ospite
   ```

   Si ferma al G2 con i candidati e le anteprime del taglio 9:16. Rispondi per esempio «1 e 3, il 2 no» ([Come rispondere a un gate](#come-rispondere-a-un-gate)) e aspetta i render in `~/youtube-studio/work/prova/…/shorts/`.
5. **Pulisci.** Quando hai finito, cancella la cartella di prova (`~/youtube-studio/work/prova/`), il profilo (`~/.config/youtube-producer/channels/prova.md` e `prova.glossary.txt`) e il brand (`~/.config/youtube-producer/brands/prova/`), oppure tienili per altre prove.

Ogni richiesta è una sessione lunga per il tuo piano Claude: l'agente lavora con molto ragionamento e legge parecchio. Un episodio intero consuma molto più di una clip di prova: parti dalle clip corte.

## Primi passi

### 1. Crea il profilo del tuo canale

```
/youtube:setup onboard --channel=<slug>
```

Lo slug è un nome corto, minuscolo e senza spazi (per esempio `caffe-maker`): lo userai ovunque. Il comando ti chiede il tipo di canale (o lo passi con `--kind`), copia il template in `~/.config/youtube-producer/channels/<slug>.md` e ti fa le domande per compilarlo. Crea anche `<slug>.glossary.txt`, dove aggiungi i nomi propri che la trascrizione sbaglia (il tuo nome, quello del canale, i prodotti, il gergo).

**Quale tipo scegliere.**

| `--kind` | Quando | Cosa cambia |
|---|---|---|
| `own` | un canale di progetto o di brand, anche se lo gestisci da solo | è l'unico tipo che può proporre miglioramenti al plugin ([Come impara](#come-impara)) |
| `personal` | il canale con il tuo nome e la tua faccia | «il mio canale» nelle richieste indica questo profilo; è l'unico tipo che ammette ritocchi AI sul volto del titolare, se lui li autorizza nel profilo |
| `client` | il canale di un cliente | regole più strette: consenso scritto del cliente, grafiche consegnate solo come file finiti o con HyperFrames |

I campi del profilo che contano di più:

| Campo | Cosa scrivere |
|---|---|
| `channel.handle`, `channel.url` | l'handle e l'indirizzo del canale |
| `audience`, `positioning` | per chi è il canale e cosa promette, in una frase |
| `voice` | registro (tu o voi), nomi pubblici di chi conduce, parole vietate |
| `copy_rules` | regole di scrittura: punteggiatura dei titoli, nomi degli strumenti, maiuscole |
| `thumbnails` | template di default: `duo` (ospite + host) va bene per un podcast con ospiti; **se nel canale non ci sono ospiti, metti `thumbnails.default_template: ritratto`**; per un cliente `generic`. Poi etichetta del formato ed etichetta dell'host |
| `consent` | `release_required: true` di default: senza liberatoria confermata niente passa il G1. Si cambia solo con una decisione scritta del titolare del canale |
| `recording` | come registri: master già montato (modalità M) o file separati per camera e microfono (modalità I) |

Quello che non sai resta `[DA COMPILARE]`: l'agente te lo chiede quando serve. Se lavori su un solo canale, l'agente usa sempre quel profilo; se ne hai più di uno, ti chiede su quale lavorare (o lo scrivi nella richiesta).

### 2. Il brand (facoltativo)

Senza brand il plugin usa `demo`: una palette neutra (inchiostro, carta e tre accenti), Anton per i titoli e Inter per il testo, il nome «Il tuo canale» come scritta del logo e un simbolo segnaposto. L'onboarding crea `~/.config/youtube-producer/brands/<slug>/` partendo da `demo`. Poi apri `tokens.json` e cambia **almeno** `name` e `wordmark.text` con il nome del canale, altrimenti nelle thumbnail compare «Il tuo canale». Colori e font vanno presi dal brand kit o dal CSS del sito, mai a occhio. Metti il tuo logo in `logo/` (oppure togli la voce `logo` da `tokens.json` e resta solo la scritta). Puoi aggiungere font (con la loro licenza), un preset dei sottotitoli e template propri: il contratto della cartella è in `plugins/youtube/docs/yt/knowledge/07-thumbnails.md` §8. Finché non lo fai, il canale lavora con il look di `demo` e l'agente lo dice nei brief.

### 3. Prime richieste

Cinque esempi concreti. Scrivili così, con i tuoi percorsi:

```
/youtube:producer fai l'audit del canale e dimmi qual è il problema principale
/youtube:producer capitoli per il video https://www.youtube.com/watch?v=XXXXXXXXXXX
/youtube:producer 5 Shorts da ~/Movies/ep12/master.mp4
/youtube:producer tre thumbnail per ~/Movies/ep12/master.mp4, titolo «Dodici mesi da sola su un SaaS»
/youtube:producer monta l'episodio da ~/Movies/ep12/master.mp4: master 4K, sottotitoli e capitoli
```

**La domanda sulla liberatoria.** Per montaggio, Shorts e thumbnail l'agente ti chiede se c'è la liberatoria degli ospiti e cosa copre (con `release_required: true`, il default). Se non rispondi, fa analisi e storia e poi si ferma, senza cold open, Shorts o thumbnail. Se nel video ci sei solo tu, rispondi «nessun ospite, ci sono solo io», oppure scrivilo già nella richiesta.

**Cosa aspettarti la prima volta.** Trascrizione e analisi di un episodio di un'ora richiedono qualche decina di minuti, quasi tutti in background. L'agente si ferma al G1 (o al G2) con un brief: rispondi con le tue scelte, o delega il gate. Le consegne finiscono in `deliver/` della cartella di lavoro, le note in `deliver/notes/`.

## Come rispondere a un gate

Quando l'agente si ferma, Claude Code ti mostra il brief: un riepilogo con le opzioni e, in fondo, le **decisioni numerate** che ti servono. Il brief è salvato anche in `<cartella di lavoro>/qa/gate-G1.md` (o `gate-G2.md`). Un esempio, accorciato:

```
## G1 — Approvazione prima del taglio
Cold open: consigliato V1 (82, 34 s) · V2 (78, 41 s) · V3 (75, 27 s)
Tagli proposti: 1) 02:10–03:05 divagazione · 2) 18:40–19:30 ripetizione · 3) 41:00–42:15 saluti lunghi
Decisioni richieste: 1) cold open  2) tagli  3) capitoli
```

Rispondi in chiaro, una riga per decisione:

```
1) cold open V2; 2) tagli ok tranne il 3, che resta; 3) capitoli ok
```

- Puoi rispondere anche solo ad alcune decisioni: l'agente ti chiede le altre. Un «ok» o un «vai» generico non basta: per ogni decisione serve la tua scelta.
- Se preferisci che scelga lui: «G1 delegato: scegli tu». Applica le scelte che ti aveva consigliato e te le elenca.
- Dopo la risposta l'agente riparte in background; i risultati finiscono in `deliver/` (o in `shorts/` e `thumbs/`) e Claude Code ti avvisa quando ha finito.

## Configurazione

Il file è facoltativo: `~/.config/youtube-producer/config.yaml`. Lo crea `/youtube:setup`; per rivederlo o rifarlo, `/youtube:setup config`. Esempio:

```yaml
operator: "Giulia"                       # il nome con cui l'agente si rivolge a te
vault_path: null                         # null = niente vault: le note vanno in deliver/notes/ della cartella di lavoro
studio_dir: "~/youtube-studio"           # cartelle di lavoro, cache, data/yt.db, secrets/ (default); anche su un disco esterno
channels_dirs:                           # dove stanno i profili dei tuoi canali
  - "~/.config/youtube-producer/channels"
brands_dirs:                             # dove stanno i brand dei tuoi canali
  - "~/.config/youtube-producer/brands"
repo_path: "~/youtube-producer"          # solo se proponi miglioramenti al plugin (Tier B, sotto)
# learning_pr_channels: []               # canali le cui lezioni possono diventare PR (vuoto = nessuno, default)
# learning_auto_pr: false                # true = apre la PR delle proposte senza chiederti conferma (il merge resta umano)
# learning_min_evidence: 3               # lavori concordi prima che una lezione diventi una proposta
```

- **Vault Obsidian.** Se imposti `vault_path` e nel profilo del canale indichi una cartella in `vault.deliverables`, le note di quel canale vanno lì (sempre file nuovi, mai sovrascritti). Altrimenti restano in `deliver/notes/`.
- **Vedere la configurazione effettiva.** In Claude Code chiedi «mostrami yt-config», oppure scrivi `!yt-config` (JSON completo) o `!yt-config --get studio_dir` (un solo valore). Il `!` davanti lancia il comando dalla sessione: i comandi `yt-*` esistono solo dentro Claude Code, non nel Terminale (in Codex ci sono anche nel Terminale, con la riga PATH: [CODEX.md](CODEX.md)).
- **Override per una sessione**: `YT_STUDIO`, `YT_VAULT` (vuota = nessun vault), `YT_CHANNELS_DIRS` e `YT_BRANDS_DIRS` (percorsi separati da «:»), `YT_DATA`, `YT_OPERATOR`, `YT_REPO_PATH`, `YT_CONFIG` (un altro file di configurazione).

**Dove vive cosa.**

| Cosa | Dove |
|---|---|
| Plugin installato | `~/.claude/plugins/` (non modificarlo mai a mano: si sovrascrive al primo aggiornamento) |
| Dipendenze (venv, Node, thumbvision, MediaPipe) | `~/.claude/plugins/data/youtube-youtube-producer/` |
| Modelli di trascrizione | `~/.whisper-models/` |
| Extra Senko e BiRefNet | `~/.venvs/senko/`, `~/.venvs/rembg/` |
| Profili, glossari e brand dei tuoi canali | `~/.config/youtube-producer/` |
| Lavoro, database, dati appresi, segreti | `~/youtube-studio/` (`work/`, `data/`, `secrets/`) |
| Memoria dell'agente (note per canale, strumenti, calibrazioni) | `~/.claude/agent-memory/youtube-producer/MEMORY.md` |

## Come impara

L'agente migliora a ogni video, con più attenzione sulle thumbnail. Il metodo completo è in `plugins/youtube/docs/yt/knowledge/13-learning-loop.md`.

- **Da solo, sul tuo Mac (Tier A, sempre attivo).** Dopo ogni lavoro registra cosa ha proposto, cosa hai scelto o scartato (con le tue parole), le tue correzioni (una parola del trascritto, un taglio, un titolo di capitolo, un gancio) e, nelle review, come sono andati i video a 7 e 28 giorni. Da qui aggiorna, per ogni canale, preferenze, lezioni e un playbook che rilegge all'inizio del lavoro successivo. Le correzioni dei nomi nel trascritto finiscono da sole nel glossario appreso del canale. Ogni consiglio che viene da quello che ha imparato ti dice su quanti casi si basa e quanto è affidabile, e tra le opzioni ce n'è sempre una «di esplorazione», cioè una scelta meno provata per continuare a imparare.
- **Con la tua revisione (Tier B, facoltativo, spento di default).** Una lezione con prove sufficienti può diventare una proposta di miglioramento per il plugin, cioè una pull request sulla repo. Succede solo per i canali che elenchi in `learning_pr_channels` e il cui profilo ha `kind: own` e `share_lessons: true`; mai per clienti o canali personali. La PR nasce in bozza nel tuo clone della repo (`repo_path`), dopo il tuo OK, e la unisce una persona, mai l'agente. Prima clona la repo: `gh repo clone MikeIdeas2025/youtube-producer ~/youtube-producer`.
- **Cosa non impara mai**: le regole fisse (niente modifiche generative ai volti, consenso, niente servizi a pagamento nell'agente, niente upload, niente pubblicazione, gate G1 e G2, nomi pubblici, bordi del ritaglio). Le soglie di qualità può solo renderle più severe.
- **Comandi**: `/youtube:learn` (o «cosa hai imparato sulle thumbnail?») per il rapporto. All'avvio di Claude Code un avviso del plugin ti ricorda esiti da leggere o proposte in attesa, solo quando c'è qualcosa.

## Dati e privacy

- **Cosa resta sul Mac.** Video, audio, trascrizioni, cartelle di lavoro e database restano sul tuo Mac: l'agente non carica file su servizi esterni e non usa servizi a pagamento. Servizi come Higgsfield o ElevenLabs solo su tua richiesta esplicita, nella sessione principale, con il costo davanti e un OK per ogni chiamata.
- **Cosa passa da Claude.** L'agente è Claude: per lavorare legge a blocchi il trascritto (`analysis/transcript.packed.txt`), guarda alcuni fotogrammi e i numeri del canale. Questi contenuti arrivano ad Anthropic come in ogni sessione di Claude Code, alle condizioni del tuo piano Claude. Non dire agli ospiti che «resta tutto sul Mac»: di' che i file restano in locale e che un assistente AI (Claude, di Anthropic) ne legge degli estratti per montare.
- **Consenso degli ospiti.** Di default serve una liberatoria confermata prima del G1. La checklist di cosa deve coprire è in `plugins/youtube/docs/yt/knowledge/11-compliance-safety.md` §6.4: cita Anthropic tra i fornitori terzi, con il trasferimento extra-UE (punti 7 e 8). Non è un parere legale.
- **YouTube in sola lettura.** OAuth con i soli permessi `youtube.readonly` e `yt-analytics.readonly`.
- **Segreti** (`client_secret.json`, `api_key`, token) solo in `~/youtube-studio/secrets/` (cartella accessibile solo a te): mai in chat, mai in una repo.
- **Persone nelle thumbnail.** Solo pixel veri: scontorno, grafica attorno alla figura, una correzione di luce uguale su tutta la figura o un bianco e nero uniforme. Mai modifiche generative a volti, espressioni o corpi.
- **Niente nella repo**: video, audio, sottotitoli e trascrizioni, `yt.db`, profili, glossari e brand dei canali, dati di clienti, dati di apprendimento. Restano sul tuo Mac.

## Accesso ai numeri di YouTube (facoltativo)

Senza accesso Google il plugin lavora lo stesso: montaggio, Shorts, thumbnail, capitoli e ricerca pubblica con yt-dlp. Per leggere retention, sorgenti di traffico e CTR del tuo canale serve un progetto Google Cloud con OAuth in sola lettura. Fallo il giorno in cui colleghi il canale: i dati di CTR si recuperano solo per i 30 giorni precedenti.

1. Segui la guida passo passo `plugins/youtube/docs/yt/SETUP-GOOGLE.md` (circa 15 minuti): alla fine hai `client_secret.json` e una chiave API.
2. Metti i due file in `~/youtube-studio/secrets/` (la chiave in un file chiamato `api_key`).
3. Nel prompt di Claude Code scrivi `!yt-auth --channel <slug>`: si apre il browser, accedi con l'account Google che gestisce il canale e scegli **il canale** (non l'account personale, se il canale è un Brand Account).
4. Lancia `/youtube:setup onboard --channel=<slug>`: verifica l'accesso, scrive l'id del canale nel profilo e prepara i report giornalieri.

Finché mancano `client_secret.json` e `api_key`, il doctor li mostra come avviso (giallo): è normale.

## Aggiornare

Nel terminale, in quest'ordine:

```bash
claude plugin marketplace update youtube-producer   # rilegge il marketplace dalla repo
claude plugin update youtube@youtube-producer       # porta il plugin all'ultimo commit di main
```

Poi **riavvia Claude Code** (la versione nuova si carica solo al riavvio) e lancia **`/youtube:setup install`**: installa solo ciò che manca, e se le dipendenze non sono cambiate finisce in pochi secondi. All'avvio un avviso del plugin te lo ricorda quando le dipendenze sono cambiate, ma lancialo comunque dopo ogni aggiornamento. Gli extra che hai già restano.

Non ci sono numeri di versione: ogni commit su `main` è una versione nuova. Un aggiornamento non tocca i tuoi dati: profili, brand, lavoro e quello che l'agente ha imparato stanno fuori dal plugin.

## Problemi frequenti

| Problema | Cosa fare |
|---|---|
| I comandi `/youtube:*` non compaiono | Riavvia Claude Code. Poi `claude plugin list`: `youtube@youtube-producer` deve essere installato e abilitato (se è disabilitato: `claude plugin enable youtube@youtube-producer`). Se manca, ripeti il passo 3 |
| «Repository not found» all'installazione | Non hai accettato l'invito (passo 1), l'hai accettato con un altro account GitHub, oppure manca `gh auth setup-git` (passo 2). Controlla con `gh repo view MikeIdeas2025/youtube-producer` |
| L'installazione prova a clonare via SSH e fallisce («Permission denied (publickey)») | Hai una chiave SSH di un altro account GitHub. Rilancia `gh auth setup-git` e riprova; se non basta, `gh auth login` scegliendo HTTPS con l'account invitato |
| L'avviso «manca il setup» continua a comparire | Lancia `/youtube:setup install` (non solo `/youtube:setup`, che con il setup già fatto fa solo il doctor) e riavvia Claude Code. Se resta, scrivi `!yt-config` e controlla `data_dir`, `setup_ok` e `setup_current` |
| Un comando dell'agente viene bloccato dal guard | È voluto: il guard ferma pubblicazioni, API a pagamento, cancellazioni degli originali, push e merge. Se l'operazione ti serve davvero ed è sicura, falla tu nella sessione principale o nel terminale |
| Troppe richieste di permesso, o l'agente si ferma dopo un permesso negato | Vedi [Dove lanciare Claude Code e i permessi](#dove-lanciare-claude-code-e-i-permessi): apri Claude Code da `~/youtube-studio` e aggiungi la lista di regole |
| «Operation not permitted» leggendo il girato | macOS blocca l'accesso alla cartella: Impostazioni di Sistema → Privacy e sicurezza → File e cartelle, abilita l'app da cui lanci Claude Code e riavviala |
| «Permission denied» su un comando `yt-*` | Si sono persi i bit di esecuzione dei comandi del plugin: `/youtube:setup install` li ripristina. Se il problema resta, reinstalla: `claude plugin uninstall youtube@youtube-producer --keep-data`, poi `claude plugin install youtube@youtube-producer`, poi riavvia Claude Code |
| Il doctor dice spazio disco insufficiente | Servono almeno 60 GB liberi sul disco della cartella di lavoro. Libera spazio cancellando i file intermedi di episodi già consegnati (in `~/youtube-studio/work/…/edit/` e `analysis/proxy.mp4`), mai la cartella `src/` né gli originali; oppure sposta `studio_dir` su un disco esterno ([Prova veloce](#prova-veloce-20-minuti), punto 1) |
| MediaPipe manca (avviso su espressioni o punti del volto) | Rilancia `/youtube:setup` e accetta MediaPipe quando lo propone, oppure chiedi «installa MediaPipe». Senza, le thumbnail si fanno lo stesso con Apple Vision |
| Le thumbnail non si renderizzano | Controlla che Google Chrome sia installato e aggiornato, poi `/youtube:setup doctor` |
| Due plugin con comandi `yt-*` sullo stesso Mac | Se hai anche un altro plugin che porta comandi `yt-*` (per esempio una versione precedente di questo toolkit), tieni abilitato **uno solo**: `claude plugin disable <altro-plugin>`, poi riavvia. Con due attivi può partire il comando sbagliato |
| L'accesso Google scade ogni settimana | La schermata di consenso del progetto Google è in modalità «Test»: pubblicala («In produzione»), come spiega `SETUP-GOOGLE.md` |

Per tutto il resto: `/youtube:setup doctor` dice cosa manca e cosa ne risente.

## Disinstallare

```bash
claude plugin uninstall youtube@youtube-producer               # rimuove plugin e dipendenze
claude plugin uninstall youtube@youtube-producer --keep-data   # rimuove il plugin ma tiene le dipendenze installate
claude plugin marketplace remove youtube-producer              # facoltativo: toglie anche il marketplace
```

La disinstallazione non tocca i tuoi dati. Se vuoi togliere tutto, a mano e solo se non ti servono più: `~/youtube-studio/` (lavoro, database, segreti, dati appresi), `~/.config/youtube-producer/` (profili e brand), `~/.claude/agent-memory/youtube-producer/` (memoria dell'agente), `~/.whisper-models/`, `~/.venvs/senko/`, `~/.venvs/rembg/`. Le formule Homebrew (`ffmpeg-full`, `whisper-cpp`, `yt-dlp`, `auto-editor`) toglile con `brew uninstall` solo se non le usi per altro.

## Licenze e crediti

- Attribuzioni e obblighi di licenza di tutto il materiale di terzi: `plugins/youtube/docs/yt/vendor/NOTICE.md` (video-use MIT, HyperFrames Apache-2.0, auto-editor, Senko, modelli whisper e Silero MIT, MediaPipe Apache-2.0, font SIL OFL Anton e Inter, dati delle misure di YouTube di Engaged Views CC BY 4.0).
- La trascrizione può usare NVIDIA Parakeet TDT 0.6B v3, con licenza CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).
- **Remotion** (grafiche dei template dei canali propri) è gratuito per singoli e organizzazioni **fino a 3 persone, collaboratori inclusi**; oltre serve una licenza Company. Il plugin lo usa solo per canali `own` o `personal` dopo che hai confermato il conteggio nel profilo (`graphics_licence.status`); altrimenti usa HyperFrames, gratuito (Apache-2.0). Ai clienti si consegnano solo file finiti. Dettagli: `plugins/youtube/docs/yt/vendor/REMOTION_LICENSE_NOTE.md`.
- `ffmpeg-full` è GPL: è solo uno strumento, i video prodotti non sono vincolati.

## Feedback

Il plugin è in prova: ogni segnalazione serve. Apri una issue sulla repo, la legge il proprietario (@MikeIdeas2025):

```bash
gh issue create --repo MikeIdeas2025/youtube-producer
```

oppure da https://github.com/MikeIdeas2025/youtube-producer/issues. Scrivi cosa hai chiesto (il comando o la frase), cosa ti aspettavi, cosa è successo, la versione di Claude Code (`claude --version`) o di Codex (`codex --version`, o la versione dell'app) e, se c'entra l'ambiente, l'output di `/youtube:setup doctor` (in Codex `$youtube:setup doctor`). Non allegare mai video, audio, trascrizioni di ospiti, token o chiavi.

Vuoi proporre una modifica? Le regole sono in `CONTRIBUTING.md`: lavora sempre su un branch e apri una pull request, mai un push diretto su `main`.

## Struttura della repo

```
.claude-plugin/marketplace.json        marketplace «youtube-producer» per Claude Code (un plugin: youtube)
.agents/plugins/marketplace.json       lo stesso marketplace per Codex
README.md · CODEX.md · CONTRIBUTING.md
plugins/youtube/                       il plugin (radice = ${CLAUDE_PLUGIN_ROOT})
  .claude-plugin/plugin.json           nome «youtube», senza versione (la versione è il commit)
  .codex-plugin/plugin.json            manifest per Codex: nome «youtube», versione (serve alla cache di Codex), skill e hook in codex/
  agents/producer.md                   l'agente (youtube:producer)
  agents/thumb-cold-reader.md          il lettore a freddo delle thumbnail
  commands/producer.md                 /youtube:producer, il punto d'ingresso
  commands/<skill>.md                  le 12 skill: /youtube:setup, /youtube:edit, /youtube:shorts…, /youtube:learn
  hooks/hooks.json                     guard sul Bash dell'agente; avviso di setup all'avvio (Claude Code)
  bin/                                 comandi yt-* nel PATH di Claude Code
  codex/                               solo per Codex: skills/ (generate da commands/), hooks.json, references/codex-host.md
  evals/                               valutazioni delle skill
  scripts/yt/                          toolkit: install.sh, lib/ (Python), node/ (template thumbnail), remotion/, swift/, assets/ (font, brand demo, preset sottotitoli); bin/codex-shims.sh crea i comandi yt-* per Codex
  scripts/codex/build_skills.py        genera codex/skills/ da commands/ (CONTRIBUTING.md, «Versione Codex»)
  docs/yt/
    DESIGN.md                          design doc
    knowledge/                         knowledge pack 01–13 (metodo in inglese, deliverable in italiano)
    channels/_template.md              template del profilo canale
    templates/                         brief per la troupe, messaggio all'ospite, pre-test delle thumbnail
    SETUP-GOOGLE.md                    accesso Google in sola lettura
    vendor/                            licenze e attribuzioni
```
