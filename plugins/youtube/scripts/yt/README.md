# Toolkit di YouTube Producer

Strumenti locali che l'agente `youtube:producer` (plugin `youtube`: `/youtube:producer`, comandi `/youtube:*`) usa per
produrre video YouTube: ingest e analisi del girato, trascrizione italiana con tempi per parola, diarizzazione, montaggio
da EDL con master 4K e timeline FCPXML, loudness, sottotitoli, capitoli, Shorts 9:16, grafica Remotion o HyperFrames,
thumbnail con Apple Vision e analytics del canale. Tutto gira sul Mac: niente upload, niente servizi a pagamento.

Design e contratti: `docs/yt/DESIGN.md` del plugin (§8 CLI e schemi JSON).
Knowledge e template del profilo canale: `docs/yt/` del plugin (vedi il suo README).

## Installazione e layout (plugin)

- **Setup**: `/youtube:setup` lancia `install.sh` (anche `yt-install`): senza `--yes` stampa il piano con le dimensioni e
  non cambia nulla; con `--yes` installa solo ciò che manca (idempotente, niente sudo, niente `curl | sh`). Opzioni:
  `--with-senko` (diarizzazione, ~560 MB), `--with-rembg` (matting di yt-portrait, ~1,3 GB), `--with-mediapipe`
  (espressioni di yt-portrait, ~200 MB), `--skip-system` (non installa formule Homebrew né modelli, li verifica
  soltanto), `--data DIR`, `--force`. Requisiti: Mac Apple Silicon, Homebrew (se manca, lo script dà le istruzioni
  ufficiali e si ferma), Google Chrome; per compilare `thumbvision` servono gli Xcode Command Line Tools
  (`xcode-select --install`), altrimenti si usa il binario incluso (macOS 26).
- **Data dir del plugin** (`${CLAUDE_PLUGIN_DATA}` = `~/.claude/plugins/data/youtube-youtube-producer/`, resta tra gli
  aggiornamenti): `venv/` (uv sync --frozen da `pyproject.toml` + `uv.lock`), `node/` (Playwright, npm ci dal
  `package-lock`), `remotion/` (copia del progetto Remotion + node_modules; i sorgenti restano nel plugin e vengono
  sincronizzati a ogni render), `bin/thumbvision` (compilato con swiftc), `.setup-ok` (commit, data, impronta dei lock),
  `pycache/` (bytecode Python via `PYTHONPYCACHEPREFIX`, impostato da `_run`: la cartella del plugin resta intatta).
  Ordine di risoluzione: `YT_DATA` → `CLAUDE_PLUGIN_DATA` (solo `youtube-…`, non `youtube-inline`) → percorso della
  cache dei plugin → `scripts/yt/.venv` (checkout di sviluppo, layout storico) →
  `~/.claude/plugins/data/youtube-youtube-producer` (`bin/_paths.sh`, `lib/config.py`: stessa logica nei due file).
- **Fuori dalla data dir** (condivisi, mai toccati se presenti): formule Homebrew, modelli in `~/.whisper-models/`
  (revisioni Hugging Face fissate, SHA256 verificato), venv facoltativi `~/.venvs/senko` e `~/.venvs/rembg`
  (versioni esatte in `setup/*-constraints.txt`).
- **PATH**: `bin/` del plugin è nel PATH del tool Bash mentre il plugin è attivo e contiene symlink relativi
  `yt-* → ../scripts/yt/bin/_run`, `thumbvision` (preferisce il build della data dir, ripiego sul binario incluso) e
  `yt-install → ../scripts/yt/install.sh`: i comandi si chiamano per nome nudo (`yt-ingest …`).
- **Hook** (`hooks/hooks.json`): PreToolUse su Bash → `guard.sh` (si applica solo all'agente `<plugin>:producer`, con il
  nome del plugin letto da `.claude-plugin/plugin.json`); SessionStart → `session-hint.sh` (una riga che suggerisce
  `/youtube:setup` se il marcatore manca o i lock sono cambiati, più al massimo una riga sull'apprendimento quando c'è
  qualcosa di dovuto; muto altrimenti). Stampa un oggetto JSON: `systemMessage` per l'operatore e
  `hookSpecificOutput.additionalContext` per Claude.
- **Codex** (`.codex-plugin/`, `codex/`; guida in `CODEX.md` nella radice della repo): Codex installa il plugin senza
  symlink e senza `bin/` nel PATH. `bin/codex-shims.sh` crea in `<data_dir>/shims/` il lanciatore `.yt-shim` e un link
  per ogni nome di `codex/toolkit-commands.txt` (lo lancia `install.sh --codex`; poi `--check`, `--print-path-line`,
  `--add-path`, `--print-config`); prima degli shim vale la forma diretta `bin/_run <yt-comando> …`. Data dir:
  `~/.codex/plugins/data/youtube-youtube-producer` (stessa regola della cache). Hook in `codex/hooks.json`:
  `guard.sh --codex pre` (PreToolUse su Bash, apply_patch e strumenti MCP, acceso per sessione; ogni chiamata
  rinfresca il marcatore che `yt-config` legge in `codex_guard`), `guard.sh --codex prompt` (UserPromptSubmit),
  `session-hint.sh --codex` (SessionStart, con `$youtube:`). `--print-config` non mette mai la data dir tra le
  cartelle scrivibili: venv, node, shim e thumbvision girano anche fuori dalla sandbox, e il guard (C1) ne blocca
  le scritture dalla conversazione.
- **Configurazione dell'operatore** (facoltativa): `~/.config/youtube-producer/config.yaml` con `operator`,
  `vault_path` (facoltativo), `channels_dirs` (profili canale, default `~/.config/youtube-producer/channels`),
  `brands_dirs` (brand, default `~/.config/youtube-producer/brands`), `studio_dir` (default `~/youtube-studio`),
  `repo_path` (clone della repo del plugin, default `~/youtube-producer`) e le chiavi `learning_*`; si crea con
  `yt-config --init --operator NOME [--vault PATH]`. `yt-config` stampa il JSON con tutti i percorsi effettivi
  (`plugin_root`, `data_dir`, `venv_python`, `studio_dir`, `vault_path`, `channels_dirs`, `channels`,
  `default_channel`, `brands_dirs`, `brands`, `deliverables_mode`, `operator`, …); `yt-config --channel SLUG` aggiunge
  le consegne di quel canale (`deliverables_mode`, `deliverables_dir`). Variabili: `YT_DATA`, `YT_STUDIO`, `YT_VAULT`,
  `YT_CHANNELS_DIRS`, `YT_BRANDS_DIRS` (separate da «:»), `YT_OPERATOR`, `YT_CONFIG`, `YT_REPO_PATH`.
- **Canali**: il plugin non include profili. Si copia `docs/yt/channels/_template.md` in
  `~/.config/youtube-producer/channels/<slug>.md` (o lo crea `/youtube:setup`), con accanto `<slug>.glossary.txt` e,
  se servono, `<slug>.confusions.json`. Con un solo profilo quello è il canale predefinito (`default_channel`); con
  più profili il canale va indicato, mai indovinato.
- **Consegne**: per default le note vanno in `deliver/notes/` della cartella di lavoro (dell'episodio, oppure
  `<studio_dir>/work/<slug>/deliver/notes/` per il lavoro di canale). Vanno in un vault Obsidian solo se l'operatore
  imposta `vault_path` E il profilo del canale indica `vault.deliverables` (cartella relativa al vault): `guard.sh`
  consente all'agente di scrivere nel vault solo lì.
- **Brand**: il plugin include un solo brand neutro, `demo` (`assets/brands/demo`: token ink/paper/accent + due
  secondari, Anton per i titoli e Inter per il testo, layout generico a una camera), il preset ASS `default`
  (`assets/ass/default.json`) e i template thumbnail generici `duo`, `ritratto`, `scena`, `prova`, `generic`
  (`node/templates/`, helper comune `_common.js`). Il brand di un canale vive fuori dal plugin in
  `<brands_dir>/<slug>/`: `tokens.json` (obbligatorio), `fonts/` (TTF/OTF + licenze), `logo/`,
  `templates/<slug>-*.html` (thumbnail di `yt-thumb-render`, cercati prima di `node/templates`), `ass/<preset>.json`
  (preset di `yt-captions`/`yt-clips`, cercati prima di `assets/ass`), `remotion.json` (stile delle composizioni di
  `yt-remotion`: vedi `remotion/README.md`), `layout.json` (geometria del master, da `yt-clips layout --measure --write`).
  Un canale senza brand proprio usa `demo`. `yt-doctor` controlla i brand trovati e, con `--channel`, quello del canale.

## Regole comuni

- Ogni comando `bin/yt-<cmd>` è un symlink a `bin/_run`, che esegue `lib/<cmd>.py` nel venv della data dir (Python 3.12);
  senza venv risponde `ok:false` con l'indicazione di eseguire `/youtube:setup` (solo `yt-config` gira anche col python3
  di sistema).
- Node: `ytcore.node_bin()` e `install.sh` usano lo stesso ordine (`YT_NODE`, PATH, nvm v22, `node@22` di Homebrew
  keg-only, `node` di Homebrew) e preferiscono la v22; altrimenti il primo ≥ 20. Il PATH non serve: i processi node
  partono con `ytcore.node_env()`.
- **stdout = un solo JSON** `{"ok", "outputs", "warnings", …}`; i log umani vanno su stderr; errore → `ok:false` ed exit 1.
- `WORKDIR` = cartella dell'episodio, come percorso o `<canale>/<cartella>` (relativo a `<studio_dir>/work`, default
  `~/youtube-studio/work`).
- Idempotenti: se gli output sono più recenti degli input saltano (`--force` per rifare).
- Tempi in secondi; `source` = timeline del girato, `output` = timeline del montato (`edit/assembled.timeline.json`).
- ffmpeg sempre `ffmpeg-full` per percorso assoluto; HEVC 4K decodificato con VideoToolbox.
- **Decoder AAC** (decodifica dei sorgenti, policy unica `ytcore.aac_decoder_policy`): lo decide `yt-ingest` per ogni
  sorgente e lo scrive in `inventory.json` (`audio_decode`) e in `project.json` (`audio_decoder`); tutti gli altri
  comandi lo leggono da lì. Decoder nativo di FFmpeg (float: i picchi > 0 dBFS restano) se non dà errori o se tutti i
  suoi errori cadono entro ±3 s da uno span corrotto del video (lì l'audio è comunque perso: diventa silenzio e il
  timeline resta quello del contenitore). Altrimenti `aac_at` (AudioToolbox: niente errori, ma sempre s16, picchi
  tagliati a 0 dBFS). File del toolkit (proxy, montato, consegne, Shorts) → nativo. Ogni decodifica del sorgente usa
  `aresample` async (`ytcore.AUDIO_ASYNC`) e intermedi audio float32. Forzatura: `YT_AAC_DECODER=native|aac_at|auto`.
- **Codifica** AAC (altra cosa): consegna `deliver/*-master.mp4` e `yt-loudnorm … .m4a` con l'encoder `aac_at`
  CBR 320k; Shorts (192k) e proxy (128k) con l'encoder `aac` nativo.
- `--help` di ogni comando è in italiano ed è la documentazione completa.

## Comandi

| Comando | Uso essenziale | Cosa fa |
|---|---|---|
| `yt-doctor` | `yt-doctor [--channel SLUG] [--json]` | Controlla binari, modelli, plugin, font, brand, segreti, guard.sh (must: autotest + sonda via stdin), setup della data dir, configurazione e profili, spazio disco. Exit 1 se manca un "must" |
| `yt-config` | `yt-config [--channel SLUG] [--get CHIAVE] [--init --operator NOME [--vault P] [--studio D] [--channels-dir D] [--brands-dir D] [--repo D]]` | Percorsi effettivi del plugin, configurazione dell'operatore, profili e consegne (JSON); `--init` crea `~/.config/youtube-producer/config.yaml` |
| `yt-install` | `yt-install [--yes] [--with-senko] [--with-rembg] [--with-mediapipe] [--skip-system]` | Setup idempotente (= `install.sh`): piano con dimensioni, poi installazione |
| `yt-new` | `yt-new --channel SLUG --slug S --src FILE… [--date D] [--kind podcast] [--glossary "A,B"] [--workdir P]` | Crea la cartella di lavoro, `project.json` e i symlink in `src/` (originali mai copiati né toccati); `--kind` di default dal `video_kind` del profilo, altrimenti `other` |
| `yt-ingest` | `yt-ingest WORKDIR [--no-proxy] [--frames-every 20] [--no-integrity]` | Integrità (`corrupt_spans`), loudness, bilanciamento L/R, `audio16k.wav`/`audio48k.wav`, proxy 720p, frame campione |
| `yt-frames` | `yt-frames WORKDIR (--times 75.2,1:02:03 \| --every N) [--size full\|1080\|540] [--format png] [--out DIR]` | Estrae frame con seek accurato al frame |
| `yt-glossary` | `yt-glossary WORKDIR [--doc NOTA.md…] [--web web.json] [--yt-db DB --video-id ID] [--budget 110]` | Glossario dell'episodio PRIMA della trascrizione da fonti verificabili (project.json, note di preparazione, web curato dall'agente con URL, glossario e `<canale>.confusions.json` del canale) con provenienza, punteggio, alias, contesti e fatti sulle unità → `analysis/glossary.json` (letto da `yt-transcribe` e `yt-postcorrect`) |
| `yt-transcribe` | `yt-transcribe WORKDIR [--prompt-extra "A,B"] [--timing auto\|parakeet\|whisper] [--prompt-budget N] [--engine whisper\|parakeet] [--no-postcorrect] [--reflag]` | Testo whisper.cpp large-v3-turbo + VAD con prompt a priorità (episodio → MRR/ARR → glossary.json → canale P1/P2; ≤480 car. o N token), **tempi delle parole da Parakeet TDT v3** allineato sul testo (parole a >0,5 s dal vero: 23,6 % → 2,8 % su un episodio di prova; ~75 s in più), post-correzione vincolata dei nomi, `unit_review` sulle unità dopo una cifra (mai risolte), flag `filler`/`discourse` (`flags_version: 2`) → `transcript.words.json` + `.srt` + **lista d'ascolto** `transcript.review.json` + modello `resolutions.json`. I transcript della pipeline precedente restano validi (niente ritrascrizione senza `--force`) |
| `yt-postcorrect` | `yt-postcorrect WORKDIR [--dry-run] [--decisions F] [--window 60]` | Correzione dei NOMI contro il glossario, precisione prima di tutto (0 correzioni sbagliate su 48 esecuzioni nella prova): regole AUTO, sospetti in `postcorrect.candidates.json`, decisioni dell'agente in `corrections.decisions.json` (anche annullamenti), registro `corrections.json`; mai numeri né unità |
| `yt-speakers` | `yt-speakers WORKDIR [--num-speakers N] [--map S0="Nome",S1=…]` | Diarizzazione Senko, `speaker` su ogni parola, nomi in `project.json` |
| `yt-pack` | `yt-pack WORKDIR [--gap 0.5]` | Transcript compatto a frasi per l'LLM (`transcript.packed.txt`) |
| `yt-timeline-view` | `yt-timeline-view WORKDIR --at T \| --find "parola" [--source src\|edit]` | PNG filmstrip + forma d'onda + parole, per decidere un taglio |
| `yt-remotion` | `yt-remotion render\|still COMP --props F.json --out X.mov\|.mp4\|.png` | Grafica brand (LowerThird, ChapterCard, ColdOpenTitle, IntroSting, EndPlate, ShortCaptions, ThumbnailStill) con i token del brand (default `demo`); `.mov` = ProRes 4444 alpha |
| `yt-edl-render` | `yt-edl-render WORKDIR [--preset master4k\|1080p\|proxy] [--deliver]` | Monta `edit/edl.json` (zoom, overlay, musica con ducking) → `assembled.mov` + timeline; `--deliver` → `deliver/<slug>-master.mp4` |
| `yt-loudnorm` | `yt-loudnorm IN OUT [--target -14 --tp -1.5] [--balance auto\|mono\|none]` | Loudness a due passaggi (lineare se possibile) e correzione L/R, con report JSON |
| `yt-captions` | `yt-captions WORKDIR --format srt,vtt\|ass\|json [--draft] [--edit light\|verbatim] [--builder v2\|v1] [--range a,b] [--style PRESET] [--drop-fillers]` | Sottotitoli sul timeline di output. srt/vtt: costruttore v2 con car/s stimati sul tempo a schermo (obiettivo 17, tetto 20 elencato), rotture sintattiche italiane, tempi Netflix (2 frame o ≥0,5 s), edit leggero di default, turni riparati in memoria; MRR/ARR e slot manuali = `[[segnaposto]]` finché non sono in `analysis/resolutions.json`: consegna **bloccata (exit 2)** senza `--draft`. `--builder v1` = costruttore precedente, identico byte per byte. ASS karaoke per Shorts (preset del canale o del suo brand, altrimenti `default`), JSON per Remotion: `--drop-fillers` toglie solo i `filler`, mai i `discourse` |
| `yt-chapters` | `yt-chapters WORKDIR [--draft edit/chapters.draft.json]` | Capitoli YouTube validati e agganciati alle pause → `deliver/chapters.txt` + `.json` |
| `yt-export-nle` | `yt-export-nle WORKDIR [--format fcpxml,edl] [--chapter-markers]` | Timeline FCPXML 1.10 (Final Cut, Resolve, Kdenlive) ed EDL CMX3600 dal montaggio |
| `yt-clips` | `yt-clips windows\|select\|render\|layout WORKDIR …` | Motore Shorts: finestre da valutare, selezione da `scores.json`, render 1080×1920 con sottotitoli (tolti solo i `filler`; i segnali discorsivi restano). Senza layout misurato: una camera a tutto quadro, crop speaker sul volto; con un master composito: `layout --measure … --write` salva la geometria nel brand del canale (mai nel plugin) |
| `thumbvision` | `thumbvision score IMG… \| faces IMG… \| cutout IMG --out PNG [--roi …] \| saliency IMG…` | Apple Vision on-device: qualità volto, occhi/bocca, geometria dell'espressione, box, scontorno con alpha, salienza |
| `yt-portrait` | `yt-portrait scan WORKDIR [--from --to] [--layout auto\|inset\|wide\|full] [--seat right\|all] [--source FILE] [--expr auto\|vision\|mediapipe]` · `yt-portrait cut WORKDIR --t T[,T…] [--roi auto\|inset\|wide-right…\|full] [--face-frac F\|max] [--display-cap c\|b\|legacy] [--preset cu\|hs\|bust] [--keep-holes]` · `yt-portrait duo WORKDIR --t T` · `yt-portrait cut - --image STILL` · `yt-portrait plate WORKDIR --t T [--fill nconv\|columns]` · `yt-portrait selftest` | Ritratti dell'ospite senza AI generativa (thumbnail v2). `scan`: una passata VideoToolbox sul master (o su un file di camera stretta, offset dall'audio), coppie di frame ogni 0,5 s, thumbvision, risoluzione effettiva del volto, classi d'espressione (sorriso, risata, intenso, sorpresa, neutro, scettico; MediaPipe se installato con `install.sh --with-mediapipe`, altrimenti geometria Vision), frame a metà parola esclusi, `scan_expr.jpg` una riga per classe; `--seat all` anche i posti del campo largo e i momenti duo. `cut`: frame esatto a 16 bit, matte BiRefNet-portrait (ripiego Apple Vision), buchi della lente riempiti col sorgente, spline36 + nitidezza solo luma, PNG alla misura finale (disegnato 1:1), tetto al display: volto a 1280 px ≤ 2,0× la risoluzione effettiva (`b` = 1,5×), con `--face-frac max` il più grande entro il tetto e il dettaglio servito stimato ≥ 569; bordi dritti dichiarati, prova di conservazione del volto. `duo`: ospite + host dallo stesso istante. `plate`: fondale della location senza persone (`--fill columns`: muro a pannelli ricostruito per colonne, niente sagome «fantasma») |
| `yt-thumb-render` | `yt-thumb-render --data concepts.json --out DIR [--template T] [--engine html\|remotion] [--display-cap 2.0\|1.5] [--spotify]` | Thumbnail 3840×2160 PNG + JPEG <2 MB dai template: telaio v2 `duo`, `ritratto`, `scena`, `prova` (titolo Anton, testi, colori e wordmark dai token del brand, solo HTML) e `generic`; i template di brand `<slug>-*` da `<brands_dir>/<slug>/templates` vincono sui generici. Controlli (07 §12.4): gancio 3–6 parole e mai un frammento nominale, righe ≥ 12 %, testo sul volto, coppie vietate, bordi dritti, tetto al display (2,0× effettivo a 1280), dettaglio servito, volto ≥ 35 % sui claim e ≥ 30 % nel duo, stacco volto–intorno, pixel del volto invariati, pelle ΔE00 dopo il tono (`grade: natural`, default) oppure, col `grade: mono` (livello 2b, facoltativo), stessa curva su persone e plate e landmark invariati, buchi del matte, un solo accento (`accent: auto` sceglie l'accento del brand con più contrasto), cerchio d'accento, stacco dal feed scuro, wordmark. Uscita 0 = ok, 3 = render con controlli falliti, 1 = nessun render. `--spotify` scrive anche il 1920×1080. `--engine remotion` solo per i brand propri (licenza) |
| `yt-thumb-qa` | `yt-thumb-qa IMG… --out DIR [--grid DIR_COMPETITOR] [--title T] [--no-landmarks] [--report-only]` | Foglio di leggibilità (5 dimensioni, grigi, sfocata), mock della griglia YouTube chiaro/scuro, controlli v2 bloccanti sui render col sidecar (volto, stacco volto–intorno, dettaglio servito, righe del gancio), stacco della tile dalla pagina scura (ΔL* ≥ 25 o un tratto chiaro continuo ≥ 10 % del perimetro) e chiara, cerchio d'accento ↔ capelli/volto, livello 2b del grade mono (curva unica su persone e plate, volto dalla curva comune, niente colore sulle persone, landmark MediaPipe), colorfulness, esito dei controlli del render e `<stem>_100.png` (volti e bordi dritti al 100%) |
| `yt-collect` | `yt-collect --channel SLUG [--what inventory,analytics,retention,reporting] [--tier 0\|1\|2]` | Inventario e analytics in `<studio_dir>/data/yt.db` (yt-dlp senza credenziali, Data API, OAuth) |
| `yt-outliers` | `yt-outliers --channel SLUG \| --peers FILE [--window 25] [--md F]` | Video sopra/sotto la norma (views / mediana dei precedenti, stesso formato) |
| `yt-research` | `yt-research captions\|meta URL… [--out DIR] [--thumb]` | Sottotitoli e metadati di video pubblici, con guardrail (niente cookie, pause, max 20 URL) |
| `yt-db` | `yt-db status \| init \| purge \| query "SELECT …" \| add TABELLA '{json}'` | Manutenzione del DB (registri A/B, hook, clip, previsioni) |
| `yt-auth` | `yt-auth --channel SLUG [--check]` | OAuth in sola lettura per il canale (token in `<studio_dir>/secrets/`) |
| `yt-reporting-setup` | `yt-reporting-setup --channel SLUG [--list] [--dry-run]` | Crea i job della Reporting API (CTR e impressioni; backfill di soli 30 giorni) alla versione più alta offerta (oggi `channel_basic_a3`; `a2` tenuto se ancora offerto); non cancella mai job |
| `yt-learn` | `yt-learn ingest WD` · `decision WD --gate G2 --text "…"` · `correction --kind transcript --from A --to B` · `job WD --status S` · `update\|report\|playbook --channel C` · `outcome pull` · `lesson …` · `propose …` · `propose-pr [--dry-run]` (solo sessione principale) | Ciclo di apprendimento (knowledge 13): eventi append-only, priori per canale (Beta con prior del knowledge, Elo K ≤ 16, Thompson), lezioni, glossario e confusioni appresi in `<studio>/data/learned/`, soglie solo più severe, playbook `<studio>/data/learned/<canale>.md`. Tier B (proposte e PR draft su `learn/…`) solo su opt-in: canale in `learning_pr_channels` E profilo `kind: own` con `share_lessons: true`. I priori delle thumbnail li legge da `yt-thumb-learn` |
| `yt-thumb-learn` | `yt-thumb-learn learn WD` · `rank --channel C --data concepts.json` · `choice WD --chosen V` · `publish WD --video ID --arm A=V` · `outcomes` · `postmortem --video ID` · `golden list\|check` · `refs plan\|refresh` | Motore delle thumbnail (13 §4.3, 07 §16): record per concept e render con caratteristiche e QA, scelte G2 a coppie, esiti (CTR, pari età, A/B), **fonte unica dei priori thumbnail**, ranking 2 sfruttamento + 1 esplorazione, golden set `<studio>/data/thumb-golden/`, riferimenti di nicchia ≤ 30 giorni |
| `bin/guard.sh` | hook PreToolUse; `guard.sh --selftest` | Blocca i comandi vietati dal design §10 (vedi sotto) |

## Pipeline tipica (podcast con ospite, dal master)

Esempio con un canale immaginario, «Il Caffè dei Maker» (profilo `caffe-maker`), conduttrice Giulia e ospite Paolo:

```bash
W=caffe-maker/2026-10-13-paolo
yt-doctor --channel caffe-maker
yt-new --channel caffe-maker --slug paolo --src ~/Downloads/registrazione.mp4 --glossary "Acme Robotics,Paolo Bianchi"
yt-ingest $W                      # corrupt_spans, loudness, L/R, wav, proxy, frame
yt-glossary $W --doc "<nota di preparazione>.md" --web $W/analysis/web.json   # glossario con fonti (prima dell'ASR)
yt-transcribe $W && yt-speakers $W && yt-speakers $W --map S0="Giulia",S1="Paolo Bianchi"
#   l'agente rivede analysis/postcorrect.candidates.json → analysis/corrections.decisions.json
yt-postcorrect $W                 # applica le decisioni (registro in analysis/corrections.json)
#   l'operatore ascolta gli slot di analysis/transcript.review.json → analysis/resolutions.json
yt-pack $W                        # l'agente legge transcript.packed.txt → story, hook, cold open
#   l'agente scrive edit/edl.json → GATE G1 (l'operatore approva prima di tagliare)
yt-remotion render LowerThird --props lt.json --out $W/edit/overlays/lower-third.mov   # o HyperFrames
yt-edl-render $W --preset proxy   # anteprima veloce
yt-edl-render $W --preset master4k --deliver    # master HEVC + mix −14 LUFS (yt-loudnorm in automatico)
yt-captions $W --format srt,vtt --draft   # bozza per la revisione; senza --draft solo a slot risolti
yt-chapters $W                    # da edit/chapters.draft.json
yt-export-nle $W                  # FCPXML + EDL in deliver/
yt-clips windows $W               # l'agente valuta → shorts/scores.json
yt-clips select $W --max 5        # → GATE G2
yt-clips render $W --all
yt-portrait scan $W                      # candidati del volto dell'ospite (fogli in thumbs/portrait/)
yt-portrait cut $W --t 84.0 --face-frac max --preset hs --name ospite_84   # alla misura finale, tetto al display 2,0× effettivo
yt-portrait plate $W --t 1153 --name sfondo                # fondale della location per scena / duo
yt-thumb-render --data $W/thumbs/concepts.json --out $W/thumbs/renders --spotify   # → GATE G2
yt-thumb-qa $W/thumbs/renders/*.png --out $W/thumbs/qa --grid <competitor>
#   G3: pubblicazione sempre manuale, mai dall'agente
```

`project.json.status` avanza da solo: `new → ingested → transcribed → edit → delivered` (mai all'indietro).

## Dove vive lo stato

| Cosa | Dove |
|---|---|
| Dipendenze del toolkit | data dir del plugin `~/.claude/plugins/data/youtube-youtube-producer/` (`venv/`, `node/`, `remotion/`, `bin/thumbvision`, `.setup-ok`) |
| Configurazione dell'operatore | `~/.config/youtube-producer/config.yaml` (+ profili canale in `~/.config/youtube-producer/channels/`, brand in `~/.config/youtube-producer/brands/`) |
| Cartelle di lavoro | `~/youtube-studio/work/<canale>/<YYYY-MM-DD>-<slug>/` (`studio_dir` configurabile; `src/ analysis/ edit/ deliver/ thumbs/ shorts/ qa/ logs/`, design §8.1) |
| Note e consegne | `deliver/notes/` della cartella di lavoro (o `<studio_dir>/work/<slug>/deliver/notes/`); nel vault solo con `vault_path` + `vault.deliverables` nel profilo |
| Test e fixture | `~/youtube-studio/work/_fixtures/`, `~/youtube-studio/work/_test/` |
| Cache | `~/youtube-studio/cache/` (transcript per hash dell'audio, research, bbox overlay, public dir temporanee di Remotion) |
| Database | `~/youtube-studio/data/yt.db` (SQLite, `yt-db status`); report Reporting API in `~/youtube-studio/data/reports/` |
| Apprendimento | `~/youtube-studio/data/learned/` (playbook, glossario e confusioni appresi per canale), `thumb-golden/`, `proposals/` |
| Segreti | `~/youtube-studio/secrets/` (700): `client_secret.json`, `api_key`, `token-<canale>.json`; mai letti nei log |
| Profili canale e glossari | `channels_dirs` della configurazione (il plugin ha solo `docs/yt/channels/_template.md`): `<slug>.md` + `<slug>.glossary.txt` (livelli P1/P2/P3) + `<slug>.confusions.json` (alias ASR per yt-glossary/yt-postcorrect), il primo che esiste |
| Brand e layout | brand del canale in `<brands_dir>/<slug>/`; nel plugin solo `assets/brands/demo/` (tokens.json, layout.json generico, look LUT), preset ASS `assets/ass/default.json`, font OFL in `assets/fonts/` |
| Memoria dell'agente | memoria utente dell'agente (`memory: user`) |

`~/youtube-studio` non è versionato, non sta su iCloud e non è nel vault.

## Sicurezza: `bin/guard.sh`

Hook PreToolUse sul Bash dichiarato in `hooks/hooks.json` del plugin (gli agenti dei plugin ignorano gli hook nel
frontmatter). Gira in ogni sessione ma si applica solo se `agent_type` è `youtube:producer`: per tutti gli altri esce
subito con 0, senza avviare Python se l'input non nomina l'agente. Per l'agente è fail-closed. Blocca (exit 2, motivo
in italiano):
`hyperframes publish|cloud|lambda|cloudrun`; `yt-dlp` con `--cookies*` o `--remote-components`; `curl|wget` in pipe
verso una shell; `npx --yes|-y|skills`; chiamate a ElevenLabs, Gemini, Groq, OpenAI senza prefisso `YT_ALLOW_PAID=1`;
`rm`/`mv` (e scritture distruttive) su `…/src/…` delle cartelle di lavoro e sugli originali `~/Downloads/*.mp4|mov`;
scritture nel vault Obsidian fuori dalle cartelle `vault.deliverables` dei profili canale (e sempre in `.obsidian/`;
solo se un vault è configurato: `vault_path` o `YT_VAULT`; i percorsi di lavoro seguono `studio_dir`);
`yt-learn propose-pr` (anche dentro `python -c`), `git push`, `gh pr merge|create|ready` e `gh api` che scrive su PR o
branch (la PR di apprendimento la apre solo la sessione principale con l'OK dell'operatore, il merge è sempre umano).
Verifica: `bin/guard.sh --selftest` (regole, filtro `agent_type`, prova end-to-end via stdin con un profilo di prova;
lo esegue anche `yt-doctor`).

## Aggiornare le dipendenze (tutte con versione fissata)

- **Python**: nel checkout del repo, `cd plugins/youtube/scripts/yt && uv add --no-sync pacchetto==X.Y` (aggiorna
  `pyproject.toml` e `uv.lock`), commit, poi `/youtube:setup` (l'impronta del lock cambia: il SessionStart lo suggerisce
  da solo). Mai `pip install` nel venv.
- **Remotion** (`remotion/`, 4.0.534): `npm install --save-exact remotion@V @remotion/cli@V …` (tutti i pacchetti
  `@remotion/*` alla stessa versione), poi `npm run typecheck` e un render di prova. Alla major 5.0 ricontrollare la licenza.
- **Playwright** (`node/`, 1.64.0): `npm install --save-exact -D playwright@V`.
- **thumbvision**: `/youtube:setup` lo compila nella data dir quando `swift/thumbvision.swift` cambia. Il binario incluso
  `bin/thumbvision` (arm64, minimo macOS 26) si aggiorna a mano: `swiftc -O swift/thumbvision.swift -o bin/thumbvision`.
- **Matting di yt-portrait**: venv separato `~/.venvs/rembg` (rembg 2.0.85, pymatting 1.1.16, onnxruntime 1.31.0) con il
  solo modello `birefnet-portrait` in `~/.venvs/rembg/home/models/` (972 666 916 B; installato con l'OK dell'operatore). Il
  worker `lib/portrait_matte.py` gira lì con `-I` e `REMBG_HOME` fissato: se il modello manca si ferma (mai download
  automatici, mai `bria-rmbg`, mai backend cloud, mai `MODEL_CHECKSUM_DISABLED`) e `yt-portrait cut` ripiega su Apple Vision.
- **video-use** (`vendor/video_use/`, MIT, SHA 43cfc566): solo copia rivista a SHA fissato, con procedura e hash in
  `docs/yt/vendor/video_use_NOTICE.md` (gli hash registrati sono quelli dei file upstream prima delle patch; le
  intestazioni dei file vendor rimandano a quel NOTICE).
- **Binari Homebrew** (ffmpeg-full, whisper.cpp, yt-dlp, auto-editor), **Senko** (`~/.venvs/senko`, SHA 1bcb090) e
  **modelli** (`~/.whisper-models/`): li installa `install.sh` solo se mancano (URL a revisione fissata e SHA256 in testa
  allo script); per aggiornarli cambiare lì le costanti, poi `yt-doctor` (confronta le versioni attese).
- Pacchetti nuovi solo con versione esatta e mai con `npx --yes` (lo blocca guard.sh).

## Licenze

Remotion è gratuito per singoli e organizzazioni fino a 3 persone; oltre serve una licenza Company. Il toolkit lo
consente per i brand propri (`demo`, i brand con `"own": true` nei token, i canali con profilo `kind: own` o
`kind: personal`); per i clienti HyperFrames (Apache-2.0) o soli file finiti. video-use MIT, font SIL OFL 1.1, modelli
whisper/Silero MIT, Parakeet CC-BY-4.0, superfici delle thumbnail (`data/surfaces.json`) Engaged Views CC BY 4.0.
Dettagli e obblighi: `docs/yt/vendor/NOTICE.md`, `REMOTION_LICENSE_NOTE.md`, `video_use_NOTICE.md` e design §11.
