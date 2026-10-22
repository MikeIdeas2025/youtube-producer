# docs/yt — la conoscenza del YouTube Producer

Qui c'è tutto quello che l'agente `youtube:producer` (dispatcher `/youtube:producer`, skill `/youtube:<skill>`) legge per lavorare: il design doc, il knowledge pack, il template del profilo canale, le guide e i modelli da mandare o stampare, le attribuzioni di terzi. In Codex gli stessi file li legge la conversazione aperta con `$youtube:producer` (o `$youtube:<skill>`), tramite le skill di `../../codex/` (DESIGN.md §16). Il codice sta in `../../scripts/yt/` (vedi i link in fondo).

**Ordine di precedenza se due fonti si contraddicono:** `--help` del comando > design doc > knowledge pack > modelli e guide.

## Come si leggono i percorsi

- Nei file di agente e comandi, `${CLAUDE_PLUGIN_ROOT}` è la radice del plugin (`plugins/youtube/` nella repo; la copia installata sta sotto `~/.claude/plugins/`). Claude Code la sostituisce quando carica il file; l'agente la sostituisce da sé nei file che legge con Read; in Bash non esiste.
- Nel knowledge pack i file fratelli si citano per nome (`07-thumbnails.md` §11, oppure `07` §11); i percorsi del toolkit sono relativi alla radice del plugin (`scripts/yt/…`).
- I comandi del toolkit si chiamano per nome (`yt-ingest`, `yt-config`, `thumbvision`…): con il plugin attivo sono nel PATH di Bash.
- `<studio_dir>` è lo `studio_dir` di `yt-config` (default `~/youtube-studio`).
- **In Codex** valgono gli stessi file e gli stessi percorsi, letti secondo `codex/references/codex-host.md`: `${CLAUDE_PLUGIN_ROOT}` è la radice del plugin che stampa `yt-config --get plugin_root` (la copia installata sta sotto `~/.codex/plugins/cache/`), `/youtube:<skill>` diventa `$youtube:<skill>`, e i comandi del toolkit si chiamano per nome grazie agli shim in `<data_dir>/shims/` (`scripts/yt/bin/codex-shims.sh`). Se un file del plugin e `codex-host.md` si contraddicono su come si lavora in Codex, vale `codex-host.md`.

## Knowledge pack — `knowledge/`

Corpo in inglese (metodo), deliverable sempre in italiano. Ogni fatto di piattaforma ha URL e data di verifica. Ogni statistica ha un'etichetta di evidenza: [official], [study], [vendor] o [anecdotal]. Nessun file contiene dati di un canale reale: gli esempi usano canali e persone inventati (per esempio il podcast «Il Caffè dei Maker»).

| File | Cosa contiene |
|---|---|
| `01-platform-facts.md` | Specifiche e regole YouTube e Spotify con fonte e data: view, retention, thumbnail, A/B, capitoli, end screen, Shorts, podcast, Collaborations, quote API, Reporting, specifiche di upload, loudness. Da riverificare ogni trimestre |
| `02-strategy-playbook.md` | Come funziona la raccomandazione, packaging, banca di formule per i titoli, metodo outlier, framework dei practitioner, formati e test delle 52 settimane, cadenza, community, KPI tree, benchmark italiani; §12 è il modello di baseline e posizionamento che ogni canale compila nelle sue note |
| `03-story-structures.md` | But/therefore, ABT, story spine, story circle, Ira Glass, Murch, dall'intervista alla storia (selects, beat, paper edit), radio edit, script A/V, claim ledger e rights ledger |
| `04-hooks-first-30s.md` | Cosa misura YouTube nei primi 30 s, budget di parole in italiano, rubrica C1–C9 con gate, 20 template di hook in 7 famiglie, Promise → Proof → Plan, cold open del podcast, checklist a timestamp |
| `05-editing-rules.md` | Regole di produzione (video-use), trascrizione (whisper + tempi Parakeet, glossario, post-correzione), punti di taglio, silenzi adattivi, retake, punch-in, multicam, master compositi (Mode M e Mode I), catena audio e loudness, policy del decoder AAC, encode VideoToolbox, grafica, musica, consegna NLE, autovalutazione |
| `06-captions-italian.md` | Regole Netflix IT applicate, timing, segmentazione italiana, riempitivi contro segnali discorsivi (si segnalano, non si tagliano), ortografia, preset `default` e preset dei brand, zona sicura degli Shorts, checklist del copy italiano |
| `07-thumbnails.md` | Default del telaio v2, contratto di `concepts.json`, fatti di piattaforma, evidenze, principi P1–P13, leve e ganci, archetipi, template incorporati e brand dei canali (`brands_dirs`, §8), selezione dei frame, scontorno e policy sui pixel delle persone, render e pre-check, foglio QA e lettore a freddo, rubrica, A/B e pre-test, scoreboard e apprendimento, AI generativa |
| `08-shorts-clip-engine.md` | Finestre e punteggio, regola dei 2 secondi, clip che stanno in piedi da sole, deduplica, bande di durata, testo del gancio, crop 9:16, sottotitoli, QA, distribuzione, ciclo di apprendimento |
| `09-analytics-reading.md` | Livelli di accesso, dizionario delle metriche, regole per pochi dati, diagnosi del grafico di retention, sorgenti di traffico, formule outlier, log A/B e previsioni, rituali di review, esiti → apprendimento |
| `10-evidence-ledger.md` | Etichette di evidenza, statistiche da NON codificare, ipotesi da testare, registro delle statistiche ammesse, contraddizioni risolte, punti aperti |
| `11-compliance-safety.md` | ToS e policy sviluppatori YouTube, guardrail di yt-dlp, diritti d'immagine (art. 96–97), GDPR, consenso per profilo, lavoro per clienti, trappole di licenza, telemetria, policy sui servizi a pagamento, prompt injection, copertura del guard, regole sui deliverable |
| `12-qa-gates.md` | Gate per ogni deliverable (montaggio, Shorts, thumbnail, hook, capitoli, note), il critic, i limiti dei cicli, i brief di G1/G2, la checklist di G3, il gate dell'apprendimento (§11) |
| `13-learning-loop.md` | Ciclo di apprendimento: Tier A automatico e locale (priori per canale, lezioni, glossario appreso, soglie solo più severe, playbook), Tier B facoltativo e revisionato (proposte → PR su `learn/…`), regole dure non apprendibili, piccoli campioni ed esplorazione, thumbnail, privacy, come si torna indietro |

## Profili canale — `channels/`

Nel plugin c'è un solo file: `_template.md`, il template del profilo (`kind: own | personal | client`). I profili veri e i loro glossari vivono nei `channels_dirs` dell'operatore (default `~/.config/youtube-producer/channels/`), mai nella repo. `ytcore.load_channel(slug)` legge il frontmatter YAML del profilo cercandolo prima nei `channels_dirs` e poi qui; `ytcore.glossary_terms(slug)` legge il glossario `<slug>.glossary.txt` (formato nel template). Nessun canale di default: se nei `channels_dirs` c'è un solo profilo, l'agente usa quello; altrimenti chiede.

## Brand — `brands_dirs` e il brand `demo`

Nel plugin c'è un solo brand, `demo` (`scripts/yt/assets/brands/demo/`: palette neutra con `ink`, `paper` e tre accenti, Anton e Inter, wordmark «Il tuo canale»), più i template incorporati `duo`, `ritratto`, `scena`, `prova`, `generic` e il preset dei sottotitoli `default`. Il brand di un canale (token, logo, font, template `<slug>-*.html`, preset ASS, stili Remotion in `remotion.json`) vive nei `brands_dirs` dell'operatore (default `~/.config/youtube-producer/brands/<slug>/`, override `YT_BRANDS_DIRS`), cercati prima della cartella del plugin. Il contratto completo è in `knowledge/07-thumbnails.md` §8.

## Guide

- `DESIGN.md`: architettura, componenti, flusso dei dati, gate, apprendimento, sicurezza, licenze, distribuzione come plugin.
- `SETUP-GOOGLE.md`: progetto Google Cloud, chiave Data API, OAuth in sola lettura, job Reporting (un progetto per chi possiede i canali, un token per persona).

## Modelli di documento — `templates/`

Testi in italiano pronti da compilare, mandare o stampare:
- `brief-camera-stretta.md`: brief di una pagina per la troupe sulla camera fissa stretta sull'ospite (inquadratura, ottica, luce, 4K, file ISO);
- `messaggio-ospite.md`: messaggio all'ospite prima della registrazione;
- `pre-test-protocollo.md`: protocollo del pre-test umano delle thumbnail (Prolific o PickFu, a mano dall'operatore);
- `pretest-kit/`: kit del pre-test (pagina del feed simulato, `build_kit.py` che incorpora le immagini, `analizza.py` per i risultati). Nella repo solo testo e codice: immagini di ospiti e di altri canali non si committano mai.

## Valutazioni delle skill — `../../evals/`

`evals/thumbnail.evals.json`: casi e attese per `/youtube:thumbnail` (tre ipotesi diverse, aderenza al girato, niente promesse sul CTR, niente persone o citazioni inventate); pattern adattato da magnus919/agent-skills (MIT, attribuzione nel file e in `vendor/NOTICE.md`).

## Ricerca di base — `research/`

La ricerca da cui nasce il plugin è riassunta nel knowledge pack, che è la versione vincolante. Le sigle «SYNTHESIS §…», «F4 §…», «V2 §…» nei file sono citazioni di provenienza: `research/README.md` spiega perché non ci sono i file.

## Terze parti — `vendor/`

- `NOTICE.md`: attribuzioni e obblighi di licenza. Distingue cosa è installato (HyperFrames, /watch, Senko, auto-editor), cosa è copiato (video-use), cosa è solo un'idea riscritta (repo senza licenza, AGPL, documento MrBeast trapelato), modelli, font e dati.
- `REMOTION_LICENSE_NOTE.md`: regola d'uso di Remotion (solo canali propri o personali, entro 3 persone collaboratori inclusi; clienti con file finiti o HyperFrames).
- `video_use_NOTICE.md`: dettaglio del codice video-use copiato nel toolkit: SHA fissato, hash dei file, modifiche locali, come aggiornarlo.

## Altri file del sistema (percorsi relativi alla radice del plugin)

- Toolkit (comandi `yt-*`, contratti CLI): `scripts/yt/README.md`; il riferimento vincolante resta `<comando> --help`. Installazione: `scripts/yt/install.sh`, lanciato da `/youtube:setup`.
- Agente: `agents/producer.md` · lettore a freddo: `agents/thumb-cold-reader.md` · dispatcher: `commands/producer.md` (`/youtube:producer`) · skill: `commands/*.md` (`/youtube:<skill>`, compreso `/youtube:learn`) · hook: `hooks/hooks.json`.
- Versione Codex: manifest `.codex-plugin/plugin.json` · skill `codex/skills/<skill>/SKILL.md` (`$youtube:<skill>`), generate da `commands/*.md` con `scripts/codex/build_skills.py` · guida di traduzione `codex/references/codex-host.md` · hook `codex/hooks.json` · shim dei comandi `scripts/yt/bin/codex-shims.sh`. Guida per chi lo usa: `CODEX.md` nella radice della repo; regole per chi lo modifica: `CONTRIBUTING.md`, «Versione Codex».
- Configurazione dell'operatore: `yt-config` e `~/.config/youtube-producer/config.yaml` (facoltativo: operatore, vault, `channels_dirs`, `brands_dirs`, `studio_dir`, `repo_path`, chiavi `learning_*`).
- Stato runtime (non versionato, fuori da iCloud e dalla repo): `studio_dir` (cartelle di lavoro, cache, `data/yt.db`, `secrets/`).
- Apprendimento (non versionato, per Mac e per canale): `studio_dir/data/` → tabelle in `yt.db`, `learned/<canale>.md` (playbook generato), `learned/<canale>.glossary.txt` e `.confusions.json` (glossario appreso), `thumb-golden/` (thumbnail pubblicate), `refs/` (riferimenti di nicchia, ≤ 30 giorni). Quello che vale per tutti arriva nella repo solo con una PR `learn/…` revisionata (`knowledge/13-learning-loop.md`).
- Note consegnate: in `<workdir>/deliver/notes/` (o `<studio_dir>/work/<slug>/deliver/notes/` per il lavoro senza video); nel vault dell'operatore solo se `vault_path` è impostato e il profilo indica `vault.deliverables`; sempre file nuovi con `status: draft`.
