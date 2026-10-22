# YouTube Producer — Design doc

**Versione**: 2026-10-22 · **Stato**: in uso come plugin Claude Code `youtube@youtube-producer`; dal 2026-10-22 anche come plugin Codex dalla stessa repo (§16)
**Ambito**: architettura, componenti, flusso dei dati, gate, apprendimento, sicurezza e licenze del plugin. Il metodo (come si fa una cosa bene) sta nel knowledge pack (`knowledge/01…13`); qui ci sono i contratti e i principi che lo tengono insieme. Dove questo documento e il `--help` di un comando del toolkit non coincidono, vince il `--help` (§8.3-bis).

## 1. Problema

Serve un agente YouTube che sappia fare strategia di canale, storytelling, montaggio professionale, thumbnail e soprattutto i primi 30 secondi, per tre tipi di canale:

1. **Canali propri** (`kind: own`): il canale tuo o del tuo team, per esempio un podcast video in italiano con episodi da 40–60 minuti in 4K.
2. **Canali personali** (`kind: personal`): il canale di una persona, spesso talking head.
3. **Canali di clienti** (`kind: client`): un profilo per canale, con regole di isolamento più strette.

Il lavoro deve girare su un Mac senza un NLE professionale obbligatorio: ffmpeg, whisper.cpp, Chrome, Playwright e Remotion bastano per consegnare il video finito, e la timeline FCPXML resta disponibile per rifinire a mano. Nessun canale è precaricato: ogni operatore crea il profilo dei suoi canali.

## 2. Decisioni (principi)

| # | Decisione | Alternative scartate | Perché |
|---|-----------|----------------------|--------|
| 1 | **Un agente** (`agents/producer.md` → `youtube:producer`), un dispatcher (`/youtube:producer`) e 12 skill (`/youtube:<skill>`) lette a runtime | un agente per skill | un solo punto che conosce gate, regole e apprendimento; le skill restano file leggibili |
| 2 | **Video finito + file progetto**: l'MP4 pronto e anche la timeline FCPXML (e una cut list CMX3600) per Final Cut, Resolve o Kdenlive | solo MP4; solo rough cut | chi vuole rifinire non riparte da zero |
| 3 | **Thumbnail da frame reali**: frame → scontorno (`yt-portrait`: BiRefNet-portrait, ripiego Apple Vision) → template HTML del brand → QA di leggibilità. Generativo solo per props e sfondi da testo, nella sessione principale, con preventivo e tetti | AI-first | fedeltà alle persone e al girato |
| 4 | **Nessun canale nel plugin**: profili nei `channels_dirs` e brand nei `brands_dirs` dell'operatore, fuori dalla repo. Nel plugin solo il template del profilo e il brand neutro `demo`. Nessun canale di default: con un solo profilo si usa quello, altrimenti l'agente chiede | un canale precaricato | i dati dei canali non entrano mai in git |
| 5 | **Due motori grafici**: **HyperFrames** (Apache-2.0) di default e per tutto ciò che si consegna ai clienti; **Remotion** per i template dei canali propri e personali solo entro la sua licenza (§11) | un motore solo | licenze diverse, usi diversi |
| 6 | **Local-first**: girato, audio e trascrizioni degli ospiti restano sul Mac come file (gli estratti che l'agente legge passano da Claude, come in ogni sessione: `11` §6.4 punti 7–8); servizi a pagamento fuori dal toolset dell'agente | API cloud di default | privacy degli ospiti, costi prevedibili |
| 7 | **Niente skill di terzi installate "vive"**: codice MIT/Unlicense copiato dopo revisione, a SHA fissato; plugin di terzi solo dal marketplace ufficiale o vagliati (`vendor/NOTICE.md`) | `npx skills add` | diversi repo contengono istruzioni rivolte all'agente |
| 8 | **Gate umani**: G1 prima di tagliare, G2 prima dei render finali di Shorts e thumbnail, G3 pubblicazione sempre manuale. G1 e G2 si delegano solo con una frase esplicita dell'operatore per quel gate; brief e critic girano comunque | agente autonomo end-to-end | la decisione editoriale resta umana |
| 9 | **Analytics gratuiti di Google, sola lettura**: Data API (chiave) + OAuth `youtube.readonly` e `yt-analytics.readonly` (Analytics + Reporting); job Reporting creati il giorno dell'autorizzazione (CTR solo lì, backfill di 30 giorni) | SaaS a pagamento | nessun permesso di scrittura per costruzione |
| 10 | **Corpo delle skill e del knowledge in inglese, deliverable in italiano** (`--lang` per cambiare) | tradurre il metodo | il metodo è un'istruzione per il modello; chi legge i deliverable è italiano |
| 11 | **Consenso per profilo**: `consent.release_required: true` di default; si cambia solo con una decisione scritta e datata del titolare del canale nel profilo. Restano sempre le regole su volti, servizi esterni e fedeltà al parlato | liberatoria facoltativa di default | tutela degli ospiti (art. 96–97 L. 633/1941, GDPR) |
| 12 | **Distribuzione come plugin Claude Code** da una repo privata (§14); dati, profili e segreti fuori dalla repo | cartella `~/.claude` condivisa | aggiornamenti con un comando, niente copie divergenti |
| 13 | **Brand fuori dal plugin**: token, logo, font, template `<slug>-*.html`, preset ASS e stili Remotion di ogni canale nei `brands_dirs`; le composizioni Remotion e i template HTML del plugin sono generici e ricevono lo stile dai token | un brand per canale dentro il toolkit | separazione tra codice e identità visiva |
| 14 | **Thumbnail v2** (`knowledge/07-thumbnails.md` §0): un telaio di serie (`duo` di default, `ritratto` per un solo volto) al posto della rotazione dei layout; gancio di 3–6 parole che è una frase completa; tetto d'ingrandimento 2,0× della risoluzione effettiva misurato a 1280 px con controllo del dettaglio nel file servito da 720 px; scala di policy sui pixel delle persone (livelli 0–2 e 2b ammessi, 3–4 non usati, 5 vietato); camera fissa stretta sull'ospite al posto della sessione foto; MediaPipe locale per le espressioni; lettore a freddo; pre-test umano per le variabili singole e A/B nativo come controllo di sicurezza | rotazione di 2–3 layout; tetto sul master 4K; contorno di default | evidenza misurata su set di riferimento pubblici (`07` §3) |
| 15 | **Grade monocromatico come opzione** (livello 2b): una sola curva su ogni pixel di persone e plate, controllata con la curva unica e i landmark invariati; default `natural` | persone sempre a colori | look editoriale senza ritocchi locali sui volti |
| 16 | **Apprendimento continuo** (§15, `knowledge/13-learning-loop.md`): Tier A automatico e locale per canale, Tier B revisionato (proposte → PR, merge umano), regole dure mai apprendibili | apprendimento solo in memoria; modifiche automatiche al knowledge | migliorare a ogni video senza perdere il controllo |
| 17 | **Due host, una fonte** (§16): la stessa repo è anche un marketplace di Codex; per Codex solo involucri generati dai comandi di Claude Code, una guida di traduzione scritta a mano, hook e shim propri. Toolkit, gate, guard e regole restano quelli | una copia delle skill per Codex; un plugin separato | niente divergenza tra le due versioni; Codex inietta solo i primi 8.000 byte di una skill |

## 3. Architettura (plugin)

```
<repo youtube-producer>/                         radice del marketplace «youtube-producer»
  .claude-plugin/marketplace.json               un plugin: youtube → ./plugins/youtube
  .agents/plugins/marketplace.json              lo stesso marketplace per Codex (§16)
  README.md · CODEX.md · CONTRIBUTING.md
  plugins/youtube/                              radice del plugin (${CLAUDE_PLUGIN_ROOT})
    .claude-plugin/plugin.json                  name «youtube», senza version (la versione è il commit)
    .codex-plugin/plugin.json                   manifest Codex: name «youtube», version semver, skills → codex/skills/, hooks → codex/hooks.json, commands: [] (§16)
    codex/                                      solo Codex: skills/<skill>/ generate da commands/, hooks.json, references/codex-host.md, toolkit-commands.txt
    scripts/codex/build_skills.py               generatore e --check delle skill Codex
    agents/producer.md                          agente → subagent_type «youtube:producer»
    agents/thumb-cold-reader.md                 lettore a freddo delle thumbnail (sola lettura) → «youtube:thumb-cold-reader»
    commands/producer.md                        dispatcher → /youtube:producer
    commands/<skill>.md                         12 skill → /youtube:setup, /youtube:edit, /youtube:shorts…, /youtube:learn
    evals/thumbnail.evals.json                  evals di /youtube:thumbnail
    hooks/hooks.json                            PreToolUse Bash → guard.sh (solo per l'agente); SessionStart → avviso di setup
    bin/                                        nel PATH di Bash col plugin attivo: symlink relativi yt-* → ../scripts/yt/bin/_run, thumbvision
    scripts/yt/                                 toolkit (uv, Python 3.12) + install.sh
      bin/_run  bin/guard.sh  bin/session-hint.sh
      lib/ytcore.py  lib/ytauth.py  lib/<cmd>.py
      swift/thumbvision.swift · vendor/video_use/ (MIT, SHA fissato)
      remotion/ (composizioni generiche, stile dai token) · node/ (Playwright)
      node/templates/                           duo.html, ritratto.html, scena.html, prova.html, generic.html, _common.js
      assets/fonts/                             font SIL OFL (Anton, Inter) con le licenze
      assets/brands/demo/                       il brand neutro: tokens.json, layout.json, look-33.cube, mono-curve.json, mono-33.cube
      assets/ass/default.json                   preset dei sottotitoli bruciati
    docs/yt/
      DESIGN.md (questo file) · README.md · SETUP-GOOGLE.md
      knowledge/01..13-*.md                     knowledge pack (§6; 13 = ciclo di apprendimento)
      channels/_template.md                     template del profilo canale (l'unico file della cartella)
      templates/                                modelli per l'operatore e la troupe (camera stretta, messaggio all'ospite, pre-test e kit)
      vendor/ · research/README.md              licenze e attribuzioni; nota sulla ricerca di base

${CLAUDE_PLUGIN_DATA} = ~/.claude/plugins/data/youtube-youtube-producer/
                                                venv Python, node_modules (Playwright, Remotion), thumbvision compilato,
                                                modelli MediaPipe, marker di setup; sopravvive agli aggiornamenti
                                                (in Codex: ~/.codex/plugins/data/youtube-youtube-producer/, più shims/ con i comandi yt-*)
~/.config/youtube-producer/config.yaml          facoltativo: operator, vault_path, channels_dirs, brands_dirs, studio_dir, repo_path, learning_*
~/.config/youtube-producer/channels/            (default di channels_dirs) i profili dei canali e i loro glossari
~/.config/youtube-producer/brands/<slug>/       (default di brands_dirs) i brand dei canali: tokens.json, logo/, fonts/, layout.json,
                                                templates/<slug>-*.html, ass/*.json, remotion.json
<studio_dir> = ~/youtube-studio/                stato runtime: NON versionato, NON iCloud, NON vault
  work/<canale>/<YYYY-MM-DD>-<slug>/            cartella di lavoro dell'episodio (§8.1); deliver/notes/ per le note
  cache/transcripts/  data/yt.db  secrets/ (700)
  data/learned/<canale>.md                      playbook appreso (generato da yt-learn), + <canale>.glossary.txt, .confusions.json
  data/thumb-golden/  data/refs/                thumbnail pubblicate (fixture di regressione) e riferimenti di nicchia (≤ 30 gg)
<repo_path> = ~/youtube-producer                clone della repo dove yt-learn propose-pr crea i branch learn/… (§15)
memoria dell'agente (memory: user)              cosa funziona per canale; una per operatore
```

Plugin di terzi facoltativi (scope user): `hyperframes@claude-plugins-official`, `watch@claude-video` (versioni fissate in `vendor/NOTICE.md`). Binari e modelli installati da `install.sh` (percorsi in `yt-doctor`): ffmpeg-full (sempre per percorso assoluto `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg`), whisper.cpp + `parakeet-cli`, modelli whisper large-v3-turbo e Silero VAD, yt-dlp, auto-editor; extra facoltativi: Senko (diarizzazione), rembg `birefnet-portrait` (scontorno), MediaPipe (espressioni e landmark).

## 4. L'agente

- **Passo 0 — Contesto**: `yt-config` (operatore, cartelle, `deliverables_mode`), il profilo del canale (se nei `channels_dirs` c'è un solo profilo si usa quello, altrimenti si chiede), il brand, il playbook appreso del canale, la memoria, `yt-doctor`.
- **Passo 1 — Routing**: richiesta → skill (tabella nel file dell'agente).
- **Passo 2 — Skill**: legge il `.md` della skill e lo applica per intero. Comandi del toolkit per nome (PATH del plugin).
- **Passo 3 — Ponti facoltativi**: se l'operatore ha una skill di packaging (titoli, descrizioni, post) la usa per quei testi; senza, consegna gli input nel pacchetto episodio. L'agente lavora fino in fondo senza ponti.
- **Passo 4 — Gate e salvataggio**: si ferma a G1/G2 con un brief decisionale (o applica una delega esplicita); le note sono file nuovi in `deliver/notes/` o nel vault (`deliverables_mode`, §14).
- **Passo 5 — Impara** (obbligatorio a ogni ritorno, anche ai gate e sui lavori bloccati): `yt-learn ingest`/`job`, correzioni, lezioni, playbook, proposte; blocco «Apprendimento» nel ritorno (§15).
- **Mai**: pubblicare, caricare, cambiare titoli o thumbnail su YouTube, usare servizi a pagamento, alterare i pixel delle persone con modelli generativi.

Frontmatter: `tools` senza MCP a pagamento, `memory: user`, `model`, `effort`, `color`. Niente `hooks` nel frontmatter: gli agenti dei plugin li ignorano; il guard è un hook del plugin (§10, §14).

## 5. Skill (`/youtube:`)

| Skill | Scopo |
|-------|-------|
| `setup` | Installazione (`install.sh`), configurazione dell'operatore, doctor, onboarding di un canale (profilo, glossario, brand, OAuth, job Reporting), aggiornamenti |
| `channel-audit` | Audit diagnose-first: livello di accesso, fotografia, tabella a età fissa, packaging, anomalie, un vincolo primario |
| `strategy` | Posizionamento, pilastri, format e series bible, cadenza, sistema di packaging, KPI tree, rituali di community, esperimenti con regola di decisione |
| `research` | `outliers`, `competitors`, `teardown` (primi 30–60 s), `comments` (Mom Test), `keywords` |
| `review` | T+48h, settimanale, mensile, trimestrale; lettura del grafico di retention; registro A/B e clip; post-mortem |
| `story` | Dall'intervista alla storia (selects, beat, ABT, paper edit), traccia d'intervista prima di registrare, script A/V per i video solo |
| `hook` | Hook Lab (10 hook, 5 famiglie, rubrica) e 3 cold open per il podcast |
| `edit` | Montaggio long-form (master composito o ISO; talking head), audio, grafica, sottotitoli, encode, FCPXML |
| `shorts` | Motore clip: finestre, punteggio, gate, crop 9:16, sottotitoli, QA, piano di pubblicazione |
| `chapters` | Capitoli validati dal transcript, anche in retro-fit sugli episodi pubblicati |
| `thumbnail` | 3 concept su 3 ipotesi → lettura a freddo → volti reali per classe d'espressione → telaio di serie → QA v2 → pre-test e A/B di sicurezza → scoreboard |
| `learn` | Ciclo di apprendimento a mano: esiti, priori, lezioni, playbook, proposte di miglioramento (la PR la apre il dispatcher), rinfresco mensile dei riferimenti |

Più il dispatcher `/youtube:producer`. Fuori scope per design: idee e copy di pubblicazione (titoli, descrizioni, post) restano all'operatore o a una sua skill di packaging; l'agente consegna gli input.

## 6. Knowledge pack (`docs/yt/knowledge/`)

`01-platform-facts` · `02-strategy-playbook` · `03-story-structures` · `04-hooks-first-30s` · `05-editing-rules` · `06-captions-italian` · `07-thumbnails` · `08-shorts-clip-engine` · `09-analytics-reading` · `10-evidence-ledger` · `11-compliance-safety` · `12-qa-gates` · `13-learning-loop`.
Ogni fatto di piattaforma porta URL e data di verifica; ogni statistica un'etichetta di evidenza (ufficiale / studio / vendor / aneddotico). I dati di un canale (baseline, posizionamento, ospiti) non entrano mai nel knowledge: `02` §12 è il modello vuoto che ogni canale compila nelle sue note.

## 7. Profili canale (`<slug>.md`)

Frontmatter YAML letto da `ytcore.load_channel(slug)`, che cerca nei `channels_dirs` di `yt-config` (in ordine) e poi in `docs/yt/channels/` del plugin (che contiene solo `_template.md`). Campi principali (schema completo nel template): `slug`, `kind: own|personal|client`, `share_lessons` (default `false`), `channel` (handle, id, token), `graphics_engine: hyperframes|remotion` con `graphics_licence`, `paid_services: []`, `voice` (registro, nomi pubblici, parole vietate, `wpm`), `copy_rules`, `brand`, `thumbnails` (leva e template di default, grade, `guest_style`, tetti), `consent` (`release_required: true` di default), `vault.deliverables` (facoltativo), `recording`, `baseline`.
Glossario per Whisper: `<slug>.glossary.txt` accanto al profilo (sezioni P1/P2/P3); confusioni note dell'ASR in `<slug>.confusions.json`.

**Brand (`brands_dirs`).** L'identità visiva di un canale si risolve per slug: `<brands_dir>/<slug>/` in ogni voce di `brands_dirs` (in ordine), poi `scripts/yt/assets/brands/<slug>/` del plugin, che contiene solo `demo`. Senza cartella propria il canale usa `demo`. Una cartella di brand può avere `tokens.json` (obbligatorio), `logo/`, `fonts/` (con le licenze), `layout.json`, i file di look e grade, `templates/<slug>-*.html`, `ass/*.json` e `remotion.json`. Contratto completo: `knowledge/07-thumbnails.md` §8.

## 8. Contratti CLI

Regole comuni a tutti i comandi `bin/yt-*` (nel PATH di Bash col plugin attivo; `yt-config` stampa i percorsi di runtime, §14):
- Argomento posizionale `WORKDIR` = cartella di lavoro (path o `<channel>/<dir>`), risolta con `ytcore.resolve_workdir`.
- **stdout = un solo oggetto JSON** `{"ok": bool, "outputs": {...}, "warnings": [...], ...}` (via `ytcore.emit`); log umani su stderr.
- Idempotenti: se l'output esiste ed è più recente degli input, salta (flag `--force` per rifare).
- Tempi in secondi float. `source` = timeline del sorgente, `output` = timeline del montato.
- ffmpeg sempre `ytcore.FFMPEG` (ffmpeg-full). Decodifica 4K HEVC con `-hwaccel videotoolbox`; decoder dell'audio AAC scelto da `yt-ingest` per ogni sorgente e letto da tutti i comandi con `ytcore.aac_decoder_policy` (`knowledge/05-editing-rules.md` §11). La codifica della consegna è `aac_at` CBR 320k.

### 8.1 Cartella di lavoro e `project.json`

```
<workdir>/src/        symlink agli originali (mai modificati, mai cancellati); src/iso/ per le camere dedicate
<workdir>/analysis/   inventory.json, audio16k.wav, audio48k.wav, transcript.*, speakers.json, glossary.json, frames/, proxy.mp4
<workdir>/edit/       edl.json, chapters.draft.json, overlays/, assembled.mov, assembled.timeline.json, mix.wav
<workdir>/deliver/    <slug>-master.mp4, <slug>.it.srt, <slug>.it.vtt, chapters.txt, <slug>.fcpxml, <slug>.edl, notes/
<workdir>/thumbs/     concepts.json, frames/, portrait/, cutouts/, plates/, renders/, qa/, cold/, props/, pretest/
<workdir>/shorts/     windows.json, scores.json, clips.json, layout_spans.json, short_NN.mp4, qa/
<workdir>/qa/         report.md, timeline_view/*.png
<workdir>/logs/
```

`project.json` (esempio inventato):
```json
{
  "version": 1, "channel": "caffe-maker", "slug": "ep12-sara-riva", "date": "2026-11-05",
  "title_working": "…", "kind": "podcast|talking-head|other",
  "main_source": "A",
  "sources": {"A": {"path": "/abs/path/master.mp4", "role": "master|camera|mic", "sha256_fast": "…"}},
  "glossary_extra": ["Sara Riva", "Studiodent"],
  "speakers": {"S0": "Giulia Conti", "S1": "Marco Bassi", "S2": "Sara Riva"},
  "gates": {"G1": "pending|approved|rejected", "G2": "pending"},
  "status": "new|ingested|transcribed|story|edit|delivered",
  "created": "…", "updated": "…"
}
```

### 8.2 Comandi

| Comando | Argomenti | Output |
|---|---|---|
| `yt-config` | `[--get KEY] [--init --operator NOME …]` | percorsi di runtime e configurazione effettiva (JSON) |
| `yt-doctor` | `[--channel X] [--json]` | stato di binari, versioni, modelli, plugin, font, segreti, token, spazio disco (≥ 60 GB). Exit ≠ 0 se manca un must |
| `yt-new` | `--channel X --slug S --src FILE... [--date D] [--kind K] [--glossary T,T]` | crea workdir + `project.json`, symlink in `src/` |
| `yt-ingest` | `WORKDIR [--proxy] [--frames-every 20]` | `analysis/inventory.json` (ffprobe, `corrupt_spans`, loudness EBU R128, bilanciamento L/R, true peak, decisione del decoder AAC), `audio16k.wav`, `audio48k.wav`, `proxy.mp4`, `frames/` |
| `yt-glossary` | `WORKDIR [--doc NOTA] [--web FILE]` | `analysis/glossary.json` (termini con provenienza, alias dalle confusioni) |
| `yt-transcribe` | `WORKDIR [--engine whisper|parakeet] [--prompt-extra TXT] [--prompt-budget N]` | `analysis/transcript.words.json` (testo whisper, tempi Parakeet), `transcript.srt`, lista d'ascolto, cache per hash |
| `yt-postcorrect` | `WORKDIR [--decisions FILE] [--dry-run]` | correzioni vincolate dei nomi, `analysis/corrections.json` |
| `yt-speakers` | `WORKDIR [--num-speakers N] [--map S0=Nome,…]` | `analysis/speakers.json`, campo `speaker` nelle parole |
| `yt-pack` | `WORKDIR [--gap 0.5]` | `analysis/transcript.packed.txt` |
| `yt-frames` | `WORKDIR --times t1,t2… | --every N [--from --to] [--out DIR] [--size full|1080|540]` | JPG/PNG estratti (decodifica VideoToolbox) |
| `yt-timeline-view` | `WORKDIR --at T [--window 3] [--source edit|src]` | `qa/timeline_view/<T>.png` filmstrip + waveform |
| `yt-edl-render` | `WORKDIR [--edl edit/edl.json] [--preset master4k|1080p|proxy] [--deliver]` | `edit/assembled.mov` + `edit/assembled.timeline.json`; master di consegna |
| `yt-loudnorm` | `IN OUT [--target -14 --tp -1.5 --lra 11] [--balance auto|mono|none]` | audio normalizzato a due passaggi + report |
| `yt-captions` | `WORKDIR [--timeline …] --format srt|vtt|ass|json [--style …] [--range a,b] [--draft]` | sottotitoli sul timeline di output |
| `yt-chapters` | `WORKDIR --draft edit/chapters.draft.json [--timeline …]` | `deliver/chapters.txt` validato e agganciato ai silenzi |
| `yt-clips` | `windows|select|render|layout WORKDIR …` | `shorts/windows.json`, `clips.json`, `short_NN.mp4`, `layout.json` del brand |
| `yt-remotion` | `render|still|list COMPOSITION --props FILE --out FILE [--codec prores|h264] [--scale N]` | render Remotion (overlay alpha ProRes 4444 o MP4/PNG) |
| `yt-portrait` | `scan|cut|duo|plate WORKDIR …` | classi d'espressione, ritagli al tetto di visualizzazione (anche ospite + host dallo stesso istante), plate della scena |
| `yt-thumb-render` | `--template T --data FILE --out DIR [--engine html|remotion]` | PNG 3840×2160 + JPEG < 2 MB + sidecar `.render.json`; exit ≠ 0 su un errore dei pre-check |
| `yt-thumb-qa` | `IMAGES… --out DIR [--grid DIR|auto] [--no-landmarks]` | foglio QA (tile dal file servito, chiaro, grigi, sfocata, catena del telefono) + controlli (JSON `checks`) + mock della griglia |
| `yt-export-nle` | `WORKDIR [--format fcpxml,edl]` | `deliver/<slug>.fcpxml` e `<slug>.edl` dall'EDL |
| `yt-collect` | `--channel X [--what inventory,analytics,retention,reporting] [--since D] [--tier 0]` | tabelle in `<studio_dir>/data/yt.db` |
| `yt-outliers` | `--channel X | --peers FILE [--window 25]` | tabella outlier (views / mediana dei video precedenti a pari età) |
| `yt-research` | `captions|meta URL… [--out DIR]` | sottotitoli/metadati via yt-dlp con guardrail (niente cookie, pause) |
| `yt-auth` / `yt-reporting-setup` | `--channel X [--check|--list]` | OAuth sola lettura / job Reporting |
| `yt-db` | `status|init|purge|query|add …` | il database locale |
| `thumbvision` | `score IMG… | faces IMG… | cutout IMG --out PNG [--mode person|subject]` | JSON qualità volto, occhi/bocca, box; PNG con alpha |
| `yt-learn` | `report|ingest|job|decision|correction|outcomes|update|lesson|playbook|propose|propose-pr|retract …` | registro dell'apprendimento, playbook e glossario appresi, proposte; `propose-pr` solo nella sessione principale |
| `yt-thumb-learn` | `ingest|rank|choice|publish|outcomes|update|priors|postmortem|golden|refs|due|playbook|proposals …` | apprendimento delle thumbnail: feature, preferenze a coppie, golden set, esiti, riferimenti di nicchia |
| `yt-install` | `[--yes] [--with-senko] [--with-rembg] [--with-mediapipe]` | `install.sh`: senza `--yes` mostra solo il piano |

### 8.3 Schemi JSON

`transcript.words.json`:
```json
{"language": "it", "engine": "whisper.cpp large-v3-turbo", "prompt": "…", "duration": 3000.0, "flags_version": 2,
 "words": [{"i": 0, "w": "Quindi", "start": 0.00, "end": 0.32, "p": 0.91, "speaker": "S1", "discourse": true}],
 "segments": [{"start": 0.0, "end": 28.06, "text": "…", "speaker": "S1"}]}
```

`edl.json`:
```json
{"version": 1, "fps": 30, "canvas": {"w": 3840, "h": 2160},
 "sources": {"A": "src/master.mp4"},
 "segments": [{"id": "s1", "src": "A", "in": 812.40, "out": 851.20, "label": "cold-open-1",
               "fade_in": 0.03, "fade_out": 0.03, "zoom": null}],
 "overlays": [{"file": "edit/overlays/lower-third.mov", "at": 41.0, "x": 0, "y": 0}],
 "music": [{"file": "…", "at": 0.0, "gain_db": -20, "duck": true}],
 "audio": {"balance": "auto", "loudness": {"I": -14, "TP": -1.5, "LRA": 11}}}
```
`zoom` facoltativo: `{"scale": 1.15, "cx": 0.5, "cy": 0.4}` (punch-in).

`assembled.timeline.json`: `{"segments": [{"id": "s1", "out_start": 0.0, "out_end": 38.8, "src": "A", "src_in": 812.40}]}` — mappa output↔source per sottotitoli, capitoli, clip.

`chapters.draft.json`: `[{"t": 0, "title": "…"}, {"t": 312.5, "title": "…"}]` (timeline indicato da `"timeline": "output|source"`).

`shorts/windows.json`: `[{"id": "w001", "start": 0, "end": 90, "text": "…", "speakers": ["S1"]}]`.
`shorts/scores.json` (scritto dall'agente): `[{"id": "w001", "score": 0-100, "sub": {"hook": .., "payoff": .., "standalone": .., "emotion": ..}, "in": 12.3, "out": 58.9, "hook_text": "≤10 parole", "why": "…"}]`.
`shorts/clips.json`: clip finali deduplicate (overlap > 50% scartato), ordinate, con `crop: inset|speaker|stack` e `crop_box`.

`thumbs/concepts.json` (v2): `[{"id": "A", "lever": "claim|proof|duo|name", "template": "duo", "hook": "3–6 parole, frase completa", "keyword": "…", "accent": "auto", "people": [{"cutout|frame": "path", "role": "guest|host", "name": "…", "title": "…"}], "host_tag": "con …", "meta_line": "EVENTO / ANNO", "format_label": "IL PODCAST DEI MAKER", "show_logo": "wordmark", "grade": "natural|mono", "guest_style": "none|graphic", "plate": {"source": "scene|flat|prop", "path": "…"}, "expression_class": "…", "payoff_at": 123.4, "title_pair": "…", "hypothesis": "…"}]`. Schema e significato dei campi: `knowledge/07-thumbnails.md` §1.1.

`thumbvision score` → `[{"file": "…", "faces": [{"box": [x,y,w,h], "quality": 0-1, "eyes_open": 0-1, "mouth_open": 0-1}], "sharpness": .., "best_face_quality": ..}]` (box normalizzati 0–1, origine in alto a sinistra).

### 8.3-bis Allineamento al toolkit reale

**Quando design e `--help` non coincidono, vince il `--help`.** Differenze note:
- `yt-clips` vuole il **sottocomando prima**: `yt-clips windows|select|render|layout WORKDIR …`.
- La geometria del layout sta nel `layout.json` del brand (`<brands_dir>/<slug>/`, o quello generico di `demo`); i tratti inset/wide per episodio in `shorts/layout_spans.json`.
- `yt-export-nle` scrive sia FCPXML (1.10/1.11) sia CMX3600 `.edl`, in Python puro (niente auto-editor).
- `yt-thumb-qa` produce le tile 720/500/360/216/168 su scuro (dal file servito 720×405), 216/168/360 su chiaro, grigio e sfocato, la catena del telefono (720 → 1180), più una griglia 3×3 con 8 vicini; i controlli (`07` §13.1) bloccano solo i render con sidecar.
- `yt-thumb-render`: template incorporati `duo`, `ritratto`, `scena`, `prova`, `generic` più i `<slug>-*.html` dei brand nei `brands_dirs` (`07` §8); motore HTML di default, Remotion `ThumbnailStill` su richiesta. Esce con codice ≠ 0 quando un controllo di `07` §12.4 è un errore.
- Audio di consegna: AAC `aac_at` CBR 320k (YouTube suggerisce 384k; per il parlato la differenza non è udibile).
- `yt-export-nle`: `--format fcpxml,edl` (default: tutti e due), `--fcpxml-version 1.10|1.11`, `--chapter-markers`, `--tc-start`, `--name`.
- `yt-ingest`: proxy automatico sopra il 1080p (`--proxy`/`--no-proxy`), `--no-integrity`, `--source`, `--merge-gap`, `--sw`; decide il decoder AAC per sorgente (`audio_decode` in `inventory.json`, `audio_decoder` in `project.json`) e tutti gli altri comandi lo leggono.
- `yt-captions`: più formati insieme (`--format srt,vtt`), `--timeline none`, `--range` con `--no-rebase`, `--hook`, `--accent`, `--accent-word`, `--position`, `--drop-fillers`, `--out`.
- `yt-chapters`: `--draft` ha un default; `--timeline none`, `--draft-timeline`, `--window` (default 3), `--max-title` (default 60), `--no-snap`; scrive anche `deliver/chapters.json`.
- `yt-remotion`: `list|render|still`; composizioni LowerThird, ChapterCard, ColdOpenTitle, IntroSting, EndPlate, ShortCaptions, ThumbnailStill.
- `yt-new`: in più `--roles --main --title --speakers --workdir --force`.
- `yt-loudnorm`: `--balance` anche `automix|left|right|average|rebalance`, `--chain none|gentle`, `--channels`, `--analyze`, `--report`.
- `yt-edl-render`: `--deliver --deliver-codec copy|hevc|h264 --quality --no-fast --intermediate --jobs`.
- `yt-reporting-setup`: `--list`, `--dry-run`; per ogni tipo chiede la versione `_aN` più alta offerta dal canale e non cancella mai job esistenti.
- `thumbvision`: in più `version`; `score --roi --no-aesthetics --id-threshold`; `cutout --instance --point --roi --exclude --matte --feather`.
- `yt-collect`, `yt-outliers`, `yt-research`: molti flag oltre al design (`--tier`, `--url`, `--min-baseline`, `--basis`, `--age-adjust`, `--langs`, `--thumb`…): l'elenco vero è il loro `--help`.

### 8.4 SQLite `<studio_dir>/data/yt.db`

Tabelle: `channels`, `videos` (id, channel, title, published_at, duration, format: long|short|live, is_podcast), `video_stats_daily`, `analytics_28d`, `retention`, `traffic_sources`, `reach_daily` (impressioni e CTR dalla Reporting API), `peers`, `peer_videos` (purge a 30 giorni, policy API), `ab_tests`, `hooks`, `clips_log`, `predictions`, più le tabelle dell'apprendimento (eventi, feature di concept e render, preferenze, esiti, priori, lezioni, proposte: nomi e colonne in `lib/ytdb.py` e `lib/learn.py`), scritte solo da `yt-learn` e `yt-thumb-learn`.

## 9. Pipeline

Le pipeline end-to-end (episodio di podcast, talking head, audit di canale, Shorts dal catalogo) sono nei flussi del file dell'agente. Due modalità di montaggio, scritte nel profilo (`recording.mode_current`): **M** = post-produzione di un master già montato (spesso un layout composito con finestra e inset), **I** = ricostruzione dagli ISO delle camere e dalle tracce dei microfoni (`knowledge/05-editing-rules.md` §8–§9).

Flusso tipico di un episodio: `yt-new` → `yt-ingest` → `yt-glossary` → `yt-transcribe` → `yt-postcorrect` → `yt-speakers` → `yt-pack` → storia e cold open (`/youtube:story`, `/youtube:hook`) → **G1** → `yt-edl-render` (proxy, poi master) → audio, grafica, sottotitoli, capitoli → critic → consegna e FCPXML; in parallelo Shorts e thumbnail fino a **G2**; **G3** è la pubblicazione, sempre a mano.

## 10. Sicurezza

`guard.sh` (hook `PreToolUse` su Bash del plugin, `hooks/hooks.json`, `onFailure: block`, timeout 10 s) blocca: `hyperframes (publish|cloud|lambda|cloudrun)`; `yt-dlp` con `--cookies*` o `--remote-components`; `curl|wget … | sh|bash`; `npx --yes` e `npx skills`; chiamate a `api.elevenlabs.io`, `generativelanguage.googleapis.com`, `api.groq.com`, `api.openai.com` salvo `YT_ALLOW_PAID=1`; `rm` dentro `*/src/` delle cartelle di lavoro e sugli originali in `~/Downloads`; con un vault configurato, copie e redirezioni Bash nel vault fuori dalle cartelle dei deliverable; `yt-learn propose-pr`, push su `main` e merge delle PR. Gli hook di un plugin valgono per ogni sessione: `guard.sh` legge il JSON dell'hook da stdin ed esce subito con 0 se il campo `agent_type` non è `youtube:producer`, senza loggare niente di sensibile. L'hook copre solo Bash: le scritture con Write/Edit restano disciplina dell'agente (regole nel file dell'agente e in `knowledge/11-compliance-safety.md`). Per l'agente l'hook è fail-closed: se `guard.sh` manca o non è eseguibile, l'agente non può usare Bash. Il critic (sub-agente `general-purpose`) non è coperto: i suoi limiti stanno nel brief. Env: `HYPERFRAMES_NO_TELEMETRY=1`, `DO_NOT_TRACK=1`, `REMOTION_DISABLE_TELEMETRY` se supportato, `WATCH_ENGINE=local`. `guard.sh --selftest` verifica le regole. In Codex lo stesso `guard.sh` è collegato in `codex/hooks.json` (`--codex`): si accende per sessione invece che per agente, controlla anche le patch e gli strumenti MCP, aggiunge le regole C1–C5 e, poiché Codex lascia passare i comandi quando un hook fallisce, è affiancato dal controllo `codex_guard` di `yt-config` e dalla sandbox di Codex (§16).

## 11. Licenze

- **Remotion 4.x**: gratuito per singoli e organizzazioni fino a 3 persone; oltre serve una licenza Company. Se il cliente riceve solo l'MP4 non è utente Remotion (FAQ ufficiale). Con i termini 5.0 contano anche i collaboratori. **Regola**: Remotion solo per i canali `own` e `personal` finché chi ci lavora resta entro 3 persone, collaboratori inclusi (`graphics_licence` nel profilo, confermato dall'operatore); per i clienti solo file finiti, oppure HyperFrames (Apache-2.0). Ricontrollare a ogni aggiornamento major e quando il team cresce. Nota completa: `vendor/REMOTION_LICENSE_NOTE.md`.
- **HyperFrames**: Apache-2.0. **video-use**: MIT. **auto-editor**: Unlicense ma con funzioni a pagamento (render > 3200×1800 o multi-sorgente): usato solo per analisi ed export.
- **ffmpeg-full**: GPL (solo strumento, gli output non sono vincolati).
- Font del plugin: SIL OFL 1.1 (Anton, Inter); i font dei brand seguono la licenza del proprietario e restano nei `brands_dirs`. Modelli: whisper (MIT), Silero VAD (MIT), Parakeet (CC-BY-4.0, attribuire), MediaPipe Face Landmarker (Apache-2.0).
- Idee da repo senza licenza o AGPL: solo riscritte con parole nostre, nessun copia-incolla. Dettaglio: `vendor/NOTICE.md`.

## 12. Criteri di successo

1. `yt-doctor` verde su ogni Mac che installa il plugin (`/youtube:setup`).
2. Su un master di intervista di prova: ingest con `corrupt_spans` rilevati, trascrizione italiana con glossario (nomi propri corretti), capitoli validati, 3 cold open, un montato breve renderizzato con loudness −14 ±0,5 LUFS, FCPXML che si apre, uno Short 1080×1920 con sottotitoli, 3 thumbnail con QA.
3. L'agente si ferma a G1 e G2 (salvo delega esplicita) e non pubblica mai nulla.
4. Nessun dato di canali, persone o clienti, nessun segreto e nessun media nella repo; nessun brand di canale (solo `demo`).
5. Ogni lavoro lascia una traccia nel registro dell'apprendimento (Passo 5) e il video successivo dello stesso canale parte dal playbook aggiornato; nessuna PR di apprendimento si apre senza l'OK dell'operatore (o `learning_auto_pr: true`) e nessuna si unisce senza revisione umana.

## 13. Fuori scope

Pubblicazione automatica · Test A/B di Studio via API (non esiste) · SaaS a pagamento per analytics o clip · voce AI di host o ospiti e cloni vocali · montaggio multicam per i canali che non conservano gli ISO.

## 14. Distribuzione come plugin

Il plugin vive in una repo privata su GitHub, che è anche un marketplace Claude Code. Chi ha accesso alla repo lo installa con due comandi. Fatti verificati sulla documentazione di Claude Code (code.claude.com); versione minima 2.1.295 (per `onFailure` negli hook).

**Marketplace e nomi.**
- La radice della repo è un marketplace: `.claude-plugin/marketplace.json` con `name: "youtube-producer"` e un solo plugin, `youtube`, con `source: "./plugins/youtube"`.
- `plugins/youtube/.claude-plugin/plugin.json` ha `name`, `description`, `author` e **niente `version`**: la versione è lo SHA del commit, quindi ogni push su `main` è un aggiornamento.
- Installazione: `claude plugin marketplace add MikeIdeas2025/youtube-producer`, poi `claude plugin install youtube@youtube-producer`, poi `/youtube:setup`. Repo privata: servono `gh auth login` e `gh auth setup-git`.
- Nomi: `commands/<file>.md` → `/youtube:<file>`; il dispatcher `commands/producer.md` è `/youtube:producer`. L'agente si lancia con `subagent_type: "youtube:producer"`.
- Cartelle interne e comandi del toolkit mantengono il prefisso storico `yt` (`scripts/yt`, `docs/yt`, `yt-ingest`…, variabili `YT_*`): sono nomi tecnici, non un marchio.

**Cosa i plugin non permettono, e come lo si risolve.**
- Gli agenti dei plugin ignorano `hooks`, `mcpServers` e `permissionMode` nel frontmatter: il guard è in `hooks/hooks.json` (§10) e filtra su `agent_type`.
- `${CLAUDE_PLUGIN_ROOT}` viene sostituito nel testo di agente e comandi quando si caricano e c'è nei processi degli hook, ma **non** nei comandi che Claude lancia con Bash. Quindi: i comandi del toolkit si chiamano per nome, perché `bin/` del plugin entra nel PATH di Bash (symlink relativi `yt-*` → `../scripts/yt/bin/_run`, più `thumbvision`); i percorsi li stampa `yt-config`; nei file letti con Read l'agente sostituisce la variabile con la radice che conosce.
- Non esiste un hook post-installazione: l'installazione la fa `install.sh`, idempotente, lanciato da `/youtube:setup` nella sessione principale; un hook `SessionStart` veloce mostra una riga di avviso (JSON `systemMessage` per l'operatore, `additionalContext` per Claude) solo quando il marker di setup manca o è vecchio (non installa mai nulla da sé).
- I symlink relativi dentro il plugin si conservano, quelli che escono dal plugin vengono scartati; i bit di esecuzione si verificano dopo l'installazione (`/youtube:setup`).
- `${CLAUDE_PLUGIN_DATA}` (`~/.claude/plugins/data/youtube-youtube-producer/`) sopravvive agli aggiornamenti e si cancella alla disinstallazione (salvo `--keep-data`): lì vanno venv, `node_modules`, il binario Swift compilato e il marker di setup. Il toolkit accetta `CLAUDE_PLUGIN_DATA` solo se il nome della cartella comincia con `youtube-` (tranne `youtube-inline`).

**Configurazione per operatore** (`yt-config`).
- JSON: `plugin_root`, `data_dir`, `venv_python`, `studio_dir`, `vault_path` o `null`, `channels_dirs[]`, `brands_dirs[]`, `deliverables_mode` (`workdir` | `vault`), `operator`, `repo_path`, impostazioni `learning_*`.
- File facoltativo `~/.config/youtube-producer/config.yaml` (`operator`, `vault_path`, `channels_dirs` (default `["~/.config/youtube-producer/channels"]`), `brands_dirs` (default `["~/.config/youtube-producer/brands"]`), `studio_dir` (default `~/youtube-studio`), `repo_path` (default `~/youtube-producer`), `learning_*`); override per sessione `YT_DATA`, `YT_STUDIO`, `YT_VAULT`, `YT_CHANNELS_DIRS`, `YT_BRANDS_DIRS` (percorsi separati da «:»), `YT_OPERATOR`, `YT_REPO_PATH`, `YT_CONFIG`.
- `deliverables_mode: workdir` di default: le note vanno in `<workdir>/deliver/notes/` (per il lavoro senza video, `<studio_dir>/work/<slug>/deliver/notes/`). `vault` solo quando l'operatore ha impostato `vault_path` **e** il profilo del canale indica una cartella in `vault.deliverables`: un'opzione generica per chi tiene le note in un vault Obsidian.

**Cosa sta nella repo e cosa no.**
- Dentro: agente, dispatcher, skill, toolkit senza dipendenze installate, knowledge pack, template del profilo, brand `demo`, modelli per l'operatore, note di licenza.
- Fuori, per sempre: profili e glossari dei canali (nei `channels_dirs`), brand dei canali (nei `brands_dirs`), segreti (`<studio_dir>/secrets/`), girato, transcript, `yt.db`, dati di apprendimento, memorie, note.
- Ponti verso skill che esistono solo su alcune macchine (packaging, post): facoltativi, «se disponibile»; l'agente funziona fino in fondo senza.

**Aggiornamenti e contributi.** `claude plugin marketplace update youtube-producer` e poi `claude plugin update youtube@youtube-producer` portano l'ultimo commit di `main`; dopo il riavvio di Claude Code, `/youtube:setup` (idempotente) riallinea dipendenze e marker. Le modifiche passano da branch e pull request (`CONTRIBUTING.md`): la copia installata non si modifica mai a mano.

**Codex.** La stessa repo è anche un marketplace di Codex, con manifest, skill e hook propri accanto a quelli di Claude Code: §16.

## 15. Apprendimento continuo

Il metodo completo è in `knowledge/13-learning-loop.md`; qui l'architettura e i contratti.

**Due livelli.**
- **Tier A — automatico, locale, immediato.** Dopo ogni lavoro (anche fermo a un gate, parziale o bloccato) l'agente registra con `yt-learn` cosa ha proposto, cosa l'operatore ha scelto o scartato e perché (solo le sue parole), le correzioni (parole del transcript, tagli, titoli dei capitoli, hook, testo delle thumbnail), le metriche QA e, più avanti, gli esiti (T+48h solo igiene; D+7, D+14 per l'A/B, D+28). Da qui il toolkit aggiorna per canale: priori Beta sulle feature (partono dai default del knowledge e del profilo con un peso di poche pseudo-osservazioni e si muovono piano), lezioni di una riga con le prove, glossario e confusioni appresi (fusi a runtime con quelli del profilo), soglie QA solo più severe e il playbook `<studio_dir>/data/learned/<canale>.md`, che l'agente legge al Passo 0 insieme a `yt-learn report --channel <slug> --focus <skill>`. L'effetto parte dal video successivo. Tier A scrive solo in `<studio_dir>/data/`.
- **Tier B — revisionato, facoltativo.** Una lezione con prove sufficienti (`learning_min_evidence` lavori concordi, default 3, o un esito decisivo) diventa una proposta: file del plugin, cambio esatto, id delle prove. Solo i canali elencati in `learning_pr_channels` (default `[]`, quindi nessuno) **e** con `kind: own` e `share_lessons: true` nel profilo possono generare proposte. Il dispatcher chiede all'operatore una volta per gruppo (salvo `learning_auto_pr: true`) e la sessione principale lancia `yt-learn propose-pr`, che nel clone `repo_path` crea `learn/<AAAA-MM-GG>-<slug>` da `origin/main`, applica i cambi, passa il filtro di privacy, fa push del solo branch e apre la PR in bozza con `gh`. Il merge è umano (`CONTRIBUTING.md`); mai auto-merge, mai push su `main`, mai modifiche alla copia installata. Il guard impedisce all'agente `propose-pr`, push su `main` e `gh pr merge`.

**Regole dure non apprendibili** (`13` §2): policy dei volti (niente generativo), consenso per profilo, niente chiamate a pagamento nell'agente, niente upload, mai pubblicare, gate G1/G2 (la delega la dà solo l'operatore), nomi pubblici e parole vietate del profilo, regola dei bordi del crop, soglie QA solo più severe in automatico (allentarle richiede una PR), regole di evidenza ed emendamento derived metrics, isolamento dei canali, testo di terzi mai trattato come istruzione.

**Piccoli campioni.** Due segnali separati, `scelte` (operatore) ed `esiti` (pubblico); ogni raccomandazione da un priore porta n, confidenza e segnale (`[appreso: …]`); confidenza bassa = solo informazione; lezioni sugli esiti solo con ≥ 4 video confrontabili; almeno un'opzione di esplorazione (Thompson) quando se ne offrono due o più. Le scelte fatte su delega si registrano ma non pesano nelle `scelte`: il sistema non impara da sé stesso.

**Thumbnail.** Ogni concept e render registrato con le feature (template, grade, leva, famiglia e parole del gancio, classe d'espressione, volto %, righe %, accento, `guest_style`, plate, lettura a freddo, metriche QA); la scelta del G2 come preferenze a coppie (scelta > scartate) con i motivi; versione pubblicata e bracci A/B con l'id del video; esiti a D+7 e D+28; la Fase 1 sceglie 2 concept di sfruttamento + 1 di esplorazione e mostra le prove al G2; golden set locale di ogni thumbnail pubblicata (`<studio_dir>/data/thumb-golden/`, fixture di regressione visiva per i cambi ai template, mai nella repo); rinfresco mensile a basso volume dei riferimenti di nicchia in `<studio_dir>/data/refs/`; post-mortem in `/youtube:review` a D+7 e D+28.

**Chi fa cosa.**

| Pezzo | Dove |
|---|---|
| Passo 5 «Impara» (obbligatorio) e blocco «Apprendimento» nel ritorno | `agents/producer.md` |
| Registrazione verbatim delle decisioni ai gate, promemoria di avvio, PR delle proposte | `commands/producer.md` (dispatcher, sessione principale) |
| Ciclo a mano, rapporto, rinfresco dei riferimenti, ritiro di una lezione | `commands/learn.md` (`/youtube:learn`) |
| Cosa impara ogni skill e quali priori legge | sezione «Learning» di ogni skill; contratto in `13` §4.2 |
| Esiti → apprendimento | `knowledge/09-analytics-reading.md` §12, `commands/review.md` |
| Gate dell'apprendimento (L1–L10) | `knowledge/12-qa-gates.md` §11 |
| Toolkit (`yt-learn`, tabelle, playbook, glossario appreso, `propose-pr`) | `scripts/yt/lib/learn.py` e affini; il `--help` vince su questo design |
| Toolkit delle thumbnail (`yt-thumb-learn`) e sezione «Thumbnail learning» | `scripts/yt/lib/thumb_learn.py`, `commands/thumbnail.md` |
| Promemoria di avvio (≤ 1 s, solo shell e `sqlite3`, una o due righe, muto se non c'è niente) | `scripts/yt/bin/session-hint.sh` |

**Privacy.** I dati di apprendimento restano in `<studio_dir>/data/` su ogni Mac, per canale. Una PR contiene regole e conteggi, mai immagini di persone, file del golden set o dei riferimenti, testo dei transcript, nomi di ospiti o di canali, dati di clienti o di canali personali, percorsi personali o segreti (`13` §9.2). Le lezioni di un cliente non escono dal suo perimetro.

**Tornare indietro** (`13` §10): una lezione si ritira subito (`yt-learn lesson retire`), un evento registrato male si annulla (`yt-learn retract`) e i priori si ricalcolano; una PR di apprendimento unita per errore si annulla con una PR di revert.

## 16. Due host: Claude Code e Codex

Dal 2026-10-22 la stessa repo è anche un marketplace di OpenAI Codex (app ChatGPT per Mac e Codex CLI 0.155 o successiva). Guida per chi lo usa: `CODEX.md` nella radice della repo; regole per chi lo modifica: `CONTRIBUTING.md`, «Versione Codex». I fatti su Codex sono verificati sul sorgente al tag installato (`openai/codex` `rust-v0.155.0-alpha.16`) e sulla documentazione OpenAI (learn.chatgpt.com, developers.openai.com), consultati il 2026-10-22.

**Principio: una fonte, due host.** Agente, dispatcher, skill, toolkit e knowledge pack sono gli stessi. Per Codex si aggiungono solo file che Claude Code non legge, e il comportamento di Claude Code non cambia.

| Cosa | Claude Code | Codex |
|---|---|---|
| Marketplace | `.claude-plugin/marketplace.json` | `.agents/plugins/marketplace.json` (Codex lo preferisce a `.claude-plugin/`) |
| Manifest | `.claude-plugin/plugin.json`, senza versione | `.codex-plugin/plugin.json`: `version` semver (serve alla cartella della cache), `skills: ./codex/skills/`, `hooks: ./codex/hooks.json`, `commands: []` (niente conversione automatica dei comandi). Con questi campi Codex ignora `skills/` e `hooks/hooks.json` |
| Skill | `commands/*.md` → `/youtube:<skill>` | `codex/skills/<skill>/SKILL.md` → `$youtube:<skill>`: involucri generati da `scripts/codex/build_skills.py`; solo `producer` è invocabile in modo implicito |
| Agente | `agents/producer.md` (`youtube:producer`), lettore a freddo `agents/thumb-cold-reader.md` | nessuno: i plugin di Codex non portano agenti. Il Producer è la conversazione stessa; critic e lettore a freddo sono subagent di Codex |
| Traduzione | — | `codex/references/codex-host.md`, scritto a mano: strumenti, gate, guard, sandbox, setup, proposte |
| Hook | `hooks/hooks.json` | `codex/hooks.json`, comandi congelati |
| Comandi `yt-*` | symlink di `bin/` nel PATH di Bash | Codex scarta i symlink all'installazione e non mette `bin/` nel PATH: shim in `<data_dir>/shims/` (`scripts/yt/bin/codex-shims.sh`) più una riga PATH in `~/.zprofile` aggiunta con l'OK dell'operatore; prima del setup, `_run <comando>` |
| Data dir | `~/.claude/plugins/data/youtube-youtube-producer/` | `~/.codex/plugins/data/youtube-youtube-producer/`: stessa regola della cache in `_paths.sh` e `config.py`; Codex la lascia dopo la disinstallazione |
| Permessi | `settings.json` | sandbox di Codex in workspace-write con `~/youtube-studio` come progetto; `writable_roots` per configurazione (profili e brand compresi) e cartelle deliverable del vault (mai il vault intero, mai la data dir del plugin, che contiene i programmi lanciati anche fuori dalla sandbox), incollati dall'operatore; rete spenta. I comandi che usano GPU/Metal, VideoToolbox, Chrome o Apple Vision (trascrizione, render, fotogrammi, ritratti, thumbnail) dentro la sandbox falliscono (verificato con `codex sandbox -P :workspace`, Codex 0.155, macOS 26): girano fuori, con l'approvazione dell'operatore per ogni comando |
| Memoria dell'agente | `memory: user` | `<studio_dir>/data/codex-memory/MEMORY.md`, letta al Passo 0 e aggiornata al Passo 4.3 |

**Perché involucri e non copie.** Quando l'utente invoca una skill, Codex inietta solo i primi 8.000 byte del `SKILL.md` senza segnalare il taglio al modello (`ext/skills/src/render.rs`, `MAX_SKILL_PROMPT_BYTES`), mentre i file delle skill sono di 17–58 KB. Gli strumenti di Claude Code (Agent, SendMessage, Monitor, TodoWrite) non si traducono con sostituzioni di testo. L'involucro (al massimo 7.500 byte, controllato dal generatore) fa leggere a runtime `codex-host.md`, `agents/producer.md`, `commands/producer.md` e la skill, come già fa l'agente in Claude Code. `build_skills.py --check` e `scripts/yt/tests/test_codex_skills.py` tengono gli involucri allineati ai comandi.

**Gate.** Codex non tiene attiva una skill da un turno all'altro. Al G1 e al G2 il Producer scrive il brief e chiude il turno; l'operatore risponde con `$youtube:producer` e le decisioni, che si registrano verbatim con `yt-learn decision` prima di applicarle. Lo stato resta in `project.json` e `qa/gate-G*.md`, quindi la ripresa funziona anche in un'altra conversazione. Delega solo con frase esplicita, G3 sempre manuale. Critic e lettore a freddo partono con `spawn_agent` senza la cronologia della conversazione; senza subagent, il critic gira in linea e il brief lo dichiara, il lettore a freddo risulta «non eseguito» e non si simula.

**Guard.** Tre hook in `codex/hooks.json`: `PreToolUse` con matcher `^(Bash|apply_patch|mcp__.+)$` → `guard.sh --codex pre` (timeout 20 s), `UserPromptSubmit` → `guard.sh --codex prompt`, `SessionStart` → `session-hint.sh --codex`. Rispetto al §10:

- Codex non passa all'hook l'identità di un agente, quindi il guard si accende **per sessione**: un marcatore `<session_id>` in `~/Library/Application Support/youtube-producer/codex-guard/` (solo ora e tipo di innesco), creato al primo segno di lavoro del plugin (`$youtube:` nel prompt, un comando del toolkit, un percorso di plugin, data dir, shim, studio o configurazione, una patch su studio o configurazione, un comando lanciato dallo studio). Da lì vale per tutta la sessione. Il vault da solo non lo accende.
- Valgono le regole del §10, più: **N** (in entrambi gli host) `_run <comando>` e `bash <script>` valgono come il comando che lanciano, e le regole si applicano anche dentro `bash -c` con le opzioni unite (`-lc`, `-ec`), dentro `find -exec` e dopo le parole chiave della shell (`if`, `then`, `do`, `{`); **C1** niente scritture in `~/.codex/`, nella data dir del plugin e in quella della versione Claude Code (venv, node, shim, thumbvision, pycache: girano anche fuori dalla sandbox), nella copia installata del plugin o nello stato del guard; **C2** niente shell o REPL interattivi né comandi che eseguono quello che arriva dal terminale (`cat | bash`, `xargs` senza input, `read` + `eval`, codice `-c`/`-e` che esegue lo stdin), perché `write_stdin` non passa da `PreToolUse`: è un controllo al meglio; **C3** niente agenti annidati (`codex`, `claude`, `gemini`, `cursor-agent`, `aider`, `opencode`); **C4** niente destinazioni relative in scrittura senza un `cd` assoluto nello stesso comando, perché il payload dell'hook non porta il `workdir` del comando; **C5** niente strumenti MCP (`mcp__…`: connettori, browser, computer use, `node_repl`, servizi generativi o a pagamento), come la lista `tools:` dell'agente di Claude Code, che non ne ha. Una chiamata a pagamento approvata si fa in una chat nuova.
- Blocca con exit 2 e motivo su stderr. Gli hook di un plugin girano solo dopo che l'utente li ha approvati; l'approvazione vale per evento, matcher e comando (non per il contenuto dello script), quindi i comandi in `codex/hooks.json` non si cambiano.
- Codex lascia passare il comando quando un hook manca, fallisce o va in timeout. Per compensare, ogni chiamata dell'hook rinfresca il marcatore e `yt-config` lanciato da Codex (`CODEX_SESSION_ID` nell'ambiente) riporta `codex_guard.active` solo se il marcatore ha meno di 600 s (altrimenti `reason: stale`; il margine copre l'attesa di un'approvazione), le skill non lanciano comandi su media, dati, render o vault finché è `false`, e la sandbox tiene la rete spenta e scrivibili solo le cartelle di YouTube per i comandi che girano dentro di lei (non per quelli su video e immagini, che escono dalla sandbox con l'approvazione dell'operatore e restano sotto il guard).
- In Codex 0.155 ogni modifica ai file passa da `PreToolUse`: `apply_patch` esiste solo nella forma freeform e arriva all'hook come `apply_patch` con `{"command": <patch>}`; una patch lanciata dalla shell arriva come `Bash` (sorgente `rust-v0.155.0-alpha.16`: `protocol/src/openai_models.rs` `ApplyPatchToolType`, `core/src/tools/handlers/apply_patch.rs`, `core/src/tools/registry.rs`). La sandbox resta la seconda linea.
- Le skill leggono i file a blocchi di 120 righe (al massimo ~24 KB): Codex taglia a metà l'output di uno strumento oltre circa 10.000 token (`models-manager/models.json`, `truncation_policy`). `test_codex_skills.py` controlla i blocchi.

**Proposte (Tier B, §15).** In Codex la PR `learn/…` la lancia l'operatore nel suo Terminale (`yt-learn propose-pr --dry-run`, poi `yt-learn propose-pr`). Nella conversazione il guard la blocca, e `learning_auto_pr` non vale.

**Claude Code invariato.** `commands/`, `agents/`, `hooks/hooks.json` e i symlink di `bin/` non cambiano. Negli script condivisi il comportamento per Codex sta dietro `--codex`, dietro la forma diretta `_run <comando>`, dietro `CODEX_SESSION_ID` o dietro una copia del toolkit nella cache dei plugin di Codex, con un'eccezione voluta: le regole del guard sui lanciatori (N), sulle shell annidate con opzioni unite (`bash -lc`), su `find -exec` e sulle parole chiave della shell valgono anche per l'agente di Claude Code, che diventa solo più stretto. Nella radice del plugin non esiste una cartella `skills/`: Claude Code la caricherebbe e le skill risulterebbero doppie. Si verifica con `claude plugin validate`, i test del toolkit, `guard.sh --selftest`, `build_skills.py --check`, il test di sincronia (`test_codex_skills.py`) e `test_codex_runtime.py` (copia installata da Codex senza symlink, shim, guard per sessione, hook congelati, hook di Claude Code muti con i payload di Codex).

**Cosa non c'è in Codex.** HyperFrames e `/watch`, che sono plugin di Claude Code: valgono i ripieghi descritti nelle skill. Le attività cloud di Codex e l'estensione per gli editor (che non supporta i plugin) non possono usare il toolkit locale. Come in Claude Code, solo Mac Apple Silicon.
