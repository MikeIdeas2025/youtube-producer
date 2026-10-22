#!/bin/bash
# install.sh — setup idempotente di YouTube Producer (plugin youtube) su un Mac Apple Silicon.
#
# Uso:
#   install.sh                       # PIANO: controlla tutto e dice cosa installerebbe (con le dimensioni); non cambia nulla
#   install.sh --yes                 # esegue il piano
#   install.sh --yes --with-senko    # + diarizzazione Senko (venv ~/.venvs/senko, ~560 MB)
#   install.sh --yes --with-rembg    # + matting di yt-portrait (venv ~/.venvs/rembg + modello BiRefNet, ~1,3 GB)
#   install.sh --yes --with-mediapipe  # + espressioni di yt-portrait scan (extra «mediapipe» nel venv + modello, ~200 MB)
#
# Opzioni:
#   --yes            esegue (senza: solo piano)
#   --data DIR       data dir del plugin (default: YT_DATA, CLAUDE_PLUGIN_DATA o ~/.claude/plugins/data/youtube-youtube-producer)
#   --with-senko     installa Senko se manca          --with-rembg   installa rembg + birefnet-portrait se mancano
#   --with-mediapipe extra «mediapipe» (mediapipe==1.1.0, Apache-2.0) nel venv del plugin + face_landmarker.task
#                    (3,8 MB, SHA256 fissato) in <data>/models/mediapipe; una volta installato resta anche nei rilanci
#   --skip-system    non installa formule Homebrew né modelli: li verifica soltanto (riusa quelli già presenti)
#   --force          ricrea venv, node_modules e thumbvision anche se aggiornati
#   --codex          versione per OpenAI Codex: suggerimenti con $youtube:setup e, dopo il setup, i comandi yt-* in
#                    <data>/shims (codex-shims.sh), più la riga PATH e il blocco per ~/.codex/config.toml da aggiungere
#   -h, --help       questo aiuto
#
# Cosa fa (solo ciò che manca, mai sudo, mai curl|sh):
#   1. verifica macOS su Apple Silicon e Homebrew (se manca: istruzioni ufficiali, poi stop);
#   2. formule Homebrew: ffmpeg-full, whisper-cpp, yt-dlp, auto-editor; uv e node@22 solo se mancano uv o node 20+;
#   3. modelli in ~/.whisper-models (large-v3-turbo, Silero VAD v6.2.0, Parakeet TDT 0.6B v3 q8_0) a revisione fissata,
#      con verifica SHA256;
#   4. cartelle di studio_dir (work, cache, data, secrets 700);
#   5. venv Python 3.12 in <data>/venv con uv sync --frozen (pyproject.toml + uv.lock del plugin);
#   6. Playwright in <data>/node e Remotion in <data>/remotion con npm ci dai package-lock del plugin
#      (PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1: Playwright usa Google Chrome di sistema);
#   7. thumbvision compilato con swiftc in <data>/bin/thumbvision (ripiego: il binario incluso nel plugin);
#   8. facoltativi Senko, rembg e MediaPipe; 9. marcatore <data>/.setup-ok (commit, data, impronta dei lock) e riepilogo;
#   10. solo con --codex: shim dei comandi yt-* in <data>/shims.
# Non tocca ~/.claude (né ~/.codex) fuori dalla data dir. Rilanciarlo è sicuro: salta ciò che è già a posto.
set -uo pipefail

src="$0"
while [ -L "$src" ]; do
  dir="$(cd -P "$(dirname "$src")" && pwd)"
  src="$(readlink "$src")"
  case "$src" in /*) ;; *) src="$dir/$src" ;; esac
done
YT_HOME="$(cd -P "$(dirname "$src")" && pwd)"
PLUGIN_ROOT="$(cd -P "$YT_HOME/../.." && pwd)"
# shellcheck source=bin/_paths.sh
. "$YT_HOME/bin/_paths.sh"

YES=0; DATA_OPT=""; WITH_SENKO=0; WITH_REMBG=0; WITH_MP=0; SKIP_SYSTEM=0; FORCE=0; CODEX=0
usage() { sed -n '2,35p' "$src" | sed 's/^# \{0,1\}//'; }
while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) YES=1 ;;
    --data) shift; DATA_OPT="${1:-}"; [ -n "$DATA_OPT" ] || { echo "--data richiede una cartella" >&2; exit 2; } ;;
    --data=*) DATA_OPT="${1#--data=}" ;;
    --with-senko) WITH_SENKO=1 ;;
    --with-rembg) WITH_REMBG=1 ;;
    --with-mediapipe) WITH_MP=1 ;;
    --skip-system) SKIP_SYSTEM=1 ;;
    --force) FORCE=1 ;;
    --codex) CODEX=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "opzione sconosciuta: $1 (vedi --help)" >&2; exit 2 ;;
  esac
  shift
done

# ── Costanti (versioni e hash fissati; aggiornarle qui, poi yt-doctor) ──
MODELS_DIR="$HOME/.whisper-models"
W_NAME="ggml-large-v3-turbo.bin"
W_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/5359861c739e955e79d9a303bcbc70fb988958b1/ggml-large-v3-turbo.bin"
W_SHA="1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69"; W_SIZE=1624555275
V_NAME="ggml-silero-v6.2.0.bin"
V_URL="https://huggingface.co/ggml-org/whisper-vad/resolve/9ffd54a1e1ee413ddf265af9913beaf518d1639b/ggml-silero-v6.2.0.bin"
V_SHA="2aa269b785eeb53a82983a20501ddf7c1d9c48e33ab63a41391ac6c9f7fb6987"; V_SIZE=885098
P_NAME="ggml-parakeet-tdt-0.6b-v3-q8_0.bin"
P_URL="https://huggingface.co/ggml-org/parakeet-GGUF/resolve/35156454d1a39de06863303dd209fd2bed6ee079/ggml-parakeet-tdt-0.6b-v3-q8_0.bin"
P_SHA="4d64e9e96c2792186d072fde0034df0ad670cf680a2f53069052ead827fd600e"; P_SIZE=668757119
SENKO_VENV="$HOME/.venvs/senko"
SENKO_SHA="1bcb09041bfa170b4a5a4b0af92f66eff76204d5"
SENKO_REQ="senko @ git+https://github.com/narcotic-sh/senko.git@$SENKO_SHA"
REMBG_VENV="$HOME/.venvs/rembg"
REMBG_REQ="rembg[cpu]==2.0.85"
REMBG_MODEL="$REMBG_VENV/home/models/birefnet-portrait/birefnet-portrait.onnx"
R_URL="https://github.com/danielgatis/rembg/releases/download/v0.0.0/BiRefNet-portrait-epoch_150.onnx"
R_SHA="1ba1c8ff5a7bbfadc8d8d13fb11d7be793f91f23d9d466549e37a854f6668f99"; R_SIZE=972666916
# MediaPipe Face Landmarker (facoltativo, --with-mediapipe): extra «mediapipe» di pyproject.toml nel venv del plugin +
# modello ufficiale a revisione fissata (stessi valori di lib/expressions.py MP_MODEL_*). Codice e model card Apache-2.0.
MP_EXTRA="mediapipe"; MP_DIST="mediapipe-1.1.0.dist-info"
MP_URL="https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
MP_SHA="64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"; MP_SIZE=3758596
FFMPEG_BIN="/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
LOCK_STAMP=".yt-lock-sha256"

# ── Utilità ──────────────────────────────────────────────────────────────────
SETUP_CMD="/youtube:setup"
[ "$CODEX" = 1 ] && SETUP_CMD='$youtube:setup'
say() { printf '%s\n' "$*"; }
hr() { say "────────────────────────────────────────────────────────────────────────"; }
mb() { awk -v b="$1" 'BEGIN { if (b >= 1e9) printf "%.1f GB", b / 1e9; else if (b >= 1e6) printf "%.0f MB", b / 1e6; else printf "%.0f KB", b / 1e3 }'; }
sha256() { local l; l="$(shasum -a 256 "$1" 2>/dev/null)" || return 1; printf '%s\n' "${l%% *}"; }
stamp_ok() { [ -f "$2" ] && [ "$(cat "$2" 2>/dev/null)" = "$(sha256 "$1")" ]; }   # file sorgente, stamp

STATUS_NAMES=(); STATUS_LEVELS=(); STATUS_STATES=(); STATUS_DETAILS=()
MUST_FAIL=0; PLANNED=0; PLANNED_BYTES=0
status() {   # nome livello stato dettaglio   (stato: ok | fatto | da fare | manca | errore | saltato)
  STATUS_NAMES+=("$1"); STATUS_LEVELS+=("$2"); STATUS_STATES+=("$3"); STATUS_DETAILS+=("$4")
  if [ "$2" = must ] && { [ "$3" = manca ] || [ "$3" = errore ]; }; then MUST_FAIL=1; fi
  if [ "$3" = "da fare" ]; then PLANNED=$((PLANNED + 1)); fi
}
plan_bytes() { PLANNED_BYTES=$((PLANNED_BYTES + $1)); }

download_verified() {   # url destinazione sha256 byte etichetta
  local url="$1" dest="$2" want="$3" size="$4" label="$5" part got
  part="$dest.partial"
  mkdir -p "$(dirname "$dest")"
  say "  ↓ $label: $(mb "$size") da $url"
  if ! curl -fL --proto '=https' --tlsv1.2 --retry 3 --retry-delay 3 -C - --progress-bar -o "$part" "$url"; then
    say "  ✗ download non riuscito (rilancia: riprende da dove si è fermato)"
    return 1
  fi
  got="$(sha256 "$part")"
  if [ "$got" != "$want" ]; then
    rm -f "$part"
    say "  ✗ SHA256 diverso dall'atteso ($got ≠ $want): file scartato"
    return 1
  fi
  mv -f "$part" "$dest"
  say "  ✓ $label verificato (SHA256 ok)"
}

# ── 0. Dove ──────────────────────────────────────────────────────────────────
DATA="${DATA_OPT:-$(yt_data_dir)}"
if [ -z "$DATA" ]; then
  say "Checkout di sviluppo con il layout storico (venv in $YT_HOME/.venv): i comandi usano quello."
  say "Per un setup nel layout del plugin passa --data DIR (e usa YT_DATA=DIR), oppure rimuovi $YT_HOME/.venv."
  exit 2
fi
case "$DATA" in "~"|"~/"*) DATA="$HOME${DATA#\~}" ;; esac
case "$DATA" in /*) ;; *) DATA="$(pwd)/$DATA" ;; esac

if [ "$YES" = 1 ]; then MODE="installazione"; else MODE="piano (nessuna modifica: rilancia con --yes per eseguire)"; fi
hr
say "YouTube Producer — setup del plugin youtube · $MODE"
say "Plugin:   $PLUGIN_ROOT"
say "Data dir: $DATA"
hr

# ── 1. Piattaforma ───────────────────────────────────────────────────────────
if [ "$(uname -s)" != Darwin ]; then
  say "ERRORE: serve macOS (questo è $(uname -s))."; exit 1
fi
ARCH="$(uname -m)"
if [ "$ARCH" != arm64 ]; then
  if [ "$(sysctl -n sysctl.proc_translated 2>/dev/null)" = 1 ]; then
    say "ERRORE: il terminale gira sotto Rosetta (x86_64). Apri un terminale nativo arm64 e rilancia."
  else
    say "ERRORE: serve un Mac Apple Silicon (arm64); questo è $ARCH."
  fi
  exit 1
fi
MACOS="$(sw_vers -productVersion 2>/dev/null || echo '?')"
MACOS_MAJOR="${MACOS%%.*}"
status "macOS Apple Silicon" must ok "macOS $MACOS · $ARCH"

# ── 2. Homebrew e formule ────────────────────────────────────────────────────
BREW="$(command -v brew || true)"
[ -n "$BREW" ] || { [ -x /opt/homebrew/bin/brew ] && BREW=/opt/homebrew/bin/brew; }
if [ -z "$BREW" ]; then
  if [ "$SKIP_SYSTEM" = 1 ]; then
    status "Homebrew" should manca "non trovato (--skip-system: verifico solo i binari)"
  else
    hr
    say "Homebrew non è installato. Installalo TU dal Terminale seguendo le istruzioni ufficiali:"
    say "  https://brew.sh   (chiede la password di amministratore; questo script non lo esegue per te)"
    say "Poi chiudi e riapri il Terminale e rilancia $SETUP_CMD."
    exit 1
  fi
else
  status "Homebrew" must ok "$("$BREW" --version 2>/dev/null | head -1) · $BREW"
fi

FORMULAE=()   # da installare
check_bin() {   # nome formula binario stima_byte
  local name="$1" formula="$2" bin="$3" est="$4"
  if [ -x "$bin" ]; then
    status "$name" must ok "$bin"
  elif [ "$SKIP_SYSTEM" = 1 ]; then
    status "$name" must manca "manca $bin (--skip-system: brew install $formula)"
  else
    FORMULAE+=("$formula"); plan_bytes "$est"
    status "$name" must "da fare" "brew install $formula (≈ $(mb "$est") con le dipendenze)"
  fi
}
check_bin "ffmpeg-full" ffmpeg-full "$FFMPEG_BIN" 900000000
check_bin "whisper.cpp (whisper-cli)" whisper-cpp /opt/homebrew/bin/whisper-cli 85000000
if [ -x /opt/homebrew/bin/whisper-cli ] && [ ! -x /opt/homebrew/bin/parakeet-cli ]; then
  if [ "$SKIP_SYSTEM" = 1 ]; then
    status "parakeet-cli" should manca "serve whisper.cpp ≥ 1.9.5 (brew upgrade whisper-cpp)"
  else
    UPGRADE_WHISPER=1
    status "parakeet-cli" should "da fare" "brew upgrade whisper-cpp (serve whisper.cpp ≥ 1.9.5)"
  fi
else
  [ -x /opt/homebrew/bin/parakeet-cli ] && status "parakeet-cli" should ok "/opt/homebrew/bin/parakeet-cli"
fi
check_bin "yt-dlp" yt-dlp /opt/homebrew/bin/yt-dlp 340000000
check_bin "auto-editor" auto-editor /opt/homebrew/bin/auto-editor 280000000

UV="$(command -v uv || true)"
for c in "$HOME/.local/bin/uv" /opt/homebrew/bin/uv; do [ -n "$UV" ] || { [ -x "$c" ] && UV="$c"; }; done
if [ -n "$UV" ]; then
  status "uv" must ok "$("$UV" --version 2>/dev/null) · $UV"
elif [ "$SKIP_SYSTEM" = 1 ]; then
  status "uv" must manca "uv non trovato (brew install uv)"
else
  FORMULAE+=(uv); plan_bytes 45000000
  status "uv" must "da fare" "brew install uv (≈ 45 MB)"
fi

node_major() { "$1" --version 2>/dev/null | sed -n 's/^v\([0-9][0-9]*\).*/\1/p'; }
find_node() {   # PATH, nvm v22, node@22, node di Homebrew: il primo v22, altrimenti il primo ≥ 20 (= ytcore.node_bin)
  local c m pass
  if [ -n "${YT_NODE:-}" ] && [ -x "$YT_NODE" ]; then
    m="$(node_major "$YT_NODE")"
    if [ -n "$m" ] && [ "$m" -ge 20 ]; then printf '%s\n' "$YT_NODE"; return 0; fi
  fi
  for pass in 22 20; do
    for c in "$(command -v node || true)" $(ls -d "$HOME"/.nvm/versions/node/v22.*/bin/node 2>/dev/null | sort -r) \
             /opt/homebrew/opt/node@22/bin/node /opt/homebrew/bin/node; do
      [ -n "$c" ] && [ -x "$c" ] || continue
      m="$(node_major "$c")"
      [ -n "$m" ] || continue
      if { [ "$pass" = 22 ] && [ "$m" -eq 22 ]; } || { [ "$pass" = 20 ] && [ "$m" -ge 20 ]; }; then
        printf '%s\n' "$c"; return 0
      fi
    done
  done
  return 1
}
NODE="$(find_node || true)"
if [ -n "$NODE" ]; then
  status "node 20+" must ok "$("$NODE" --version) · $NODE"
elif [ "$SKIP_SYSTEM" = 1 ]; then
  status "node 20+" must manca "node non trovato (brew install node@22)"
else
  FORMULAE+=(node@22); plan_bytes 110000000
  status "node 20+" must "da fare" "brew install node@22 (≈ 110 MB, keg-only: usato per percorso assoluto)"
fi

if [ -d "/Applications/Google Chrome.app" ] || [ -d "$HOME/Applications/Google Chrome.app" ]; then
  status "Google Chrome" should ok "per Playwright (HTML→PNG delle thumbnail)"
else
  status "Google Chrome" should manca "installalo da https://www.google.com/chrome (serve a yt-thumb-render)"
fi

SWIFTC=""
if xcode-select -p >/dev/null 2>&1 && [ -d "$(xcode-select -p 2>/dev/null)" ]; then
  SWIFTC="$(xcrun --find swiftc 2>/dev/null || true)"
fi

# ── 3. Modelli ───────────────────────────────────────────────────────────────
MODEL_TODO=()
check_model() {   # etichetta livello nome url sha byte [glob]
  local label="$1" level="$2" name="$3" url="$4" want="$5" size="$6" glob="${7:-}" have=""
  if [ -n "$glob" ]; then
    have="$(ls "$MODELS_DIR"/$glob 2>/dev/null | sort | head -1)"
  elif [ -f "$MODELS_DIR/$name" ]; then
    have="$MODELS_DIR/$name"
  fi
  if [ -n "$have" ]; then
    local sz; sz="$(stat -L -f %z "$have" 2>/dev/null || echo 0)"
    if [ "$sz" -lt $((size * 9 / 10)) ]; then
      status "$label" "$level" errore "$have è troppo piccolo ($(mb "$sz")): download incompleto? Spostalo e rilancia"
    else
      status "$label" "$level" ok "$(basename "$have") · $(mb "$sz")"
    fi
  elif [ "$SKIP_SYSTEM" = 1 ]; then
    status "$label" "$level" manca "manca $MODELS_DIR/$name (--skip-system)"
  else
    MODEL_TODO+=("$name|$url|$want|$size|$label"); plan_bytes "$size"
    status "$label" "$level" "da fare" "scarico $name ($(mb "$size"), SHA256 verificato)"
  fi
}
check_model "modello whisper large-v3-turbo" must "$W_NAME" "$W_URL" "$W_SHA" "$W_SIZE"
check_model "modello VAD Silero v6.2.0" must "$V_NAME" "$V_URL" "$V_SHA" "$V_SIZE"
check_model "modello Parakeet TDT 0.6B v3" should "$P_NAME" "$P_URL" "$P_SHA" "$P_SIZE" "ggml-parakeet-tdt-0.6b-v3*.bin"

# ── 4–7. Data dir: venv, node, remotion, thumbvision ─────────────────────────
VENV_TODO=0; NODE_TODO=0; REMO_TODO=0; SWIFT_TODO=0
MP_MODEL="$DATA/models/mediapipe/face_landmarker.task"
EXTRAS_FILE="$DATA/venv/.yt-extras"   # extra già installati: un uv sync senza --extra li toglierebbe
mp_pkg_ok() { ls -d "$DATA"/venv/lib/python3.*/site-packages/"$MP_DIST" >/dev/null 2>&1; }
mp_model_ok() { [ -f "$MP_MODEL" ] && [ "$(sha256 "$MP_MODEL")" = "$MP_SHA" ]; }
mp_ok() { mp_pkg_ok && mp_model_ok; }
WANT_MP=0
if [ "$WITH_MP" = 1 ] || grep -qsx "$MP_EXTRA" "$EXTRAS_FILE"; then WANT_MP=1; fi
SYNC_EXTRAS=()
[ "$WANT_MP" = 1 ] && SYNC_EXTRAS+=(--extra "$MP_EXTRA")
if [ "$FORCE" = 1 ] || [ ! -x "$DATA/venv/bin/python" ] || ! stamp_ok "$YT_HOME/uv.lock" "$DATA/venv/$LOCK_STAMP" \
   || { [ "$WANT_MP" = 1 ] && ! mp_pkg_ok; }; then
  VENV_TODO=1; plan_bytes 490000000
  status "venv Python 3.12" must "da fare" "uv sync --frozen in $DATA/venv (≈ 490 MB; uv scarica Python 3.12 se manca, ≈ 20 MB)"
else
  status "venv Python 3.12" must ok "$DATA/venv (uv.lock invariato)"
fi
if [ "$FORCE" = 1 ] || [ ! -d "$DATA/node/node_modules" ] || ! stamp_ok "$YT_HOME/node/package-lock.json" "$DATA/node/$LOCK_STAMP"; then
  NODE_TODO=1; plan_bytes 20000000
  status "Playwright 1.64.0" should "da fare" "npm ci in $DATA/node (≈ 20 MB, nessun browser: usa Chrome di sistema)"
else
  status "Playwright 1.64.0" should ok "$DATA/node (package-lock invariato)"
fi
if [ "$FORCE" = 1 ] || [ ! -d "$DATA/remotion/node_modules" ] || ! stamp_ok "$YT_HOME/remotion/package-lock.json" "$DATA/remotion/$LOCK_STAMP"; then
  REMO_TODO=1; plan_bytes 530000000
  status "Remotion 4.0.534" should "da fare" "npm ci in $DATA/remotion (≈ 530 MB; chrome-headless-shell ≈ 570 MB al primo render)"
else
  status "Remotion 4.0.534" should ok "$DATA/remotion (package-lock invariato)"
fi
TV_SRC="$YT_HOME/swift/thumbvision.swift"
TV_OUT="$DATA/bin/thumbvision"
if [ -n "$SWIFTC" ]; then
  if [ "$FORCE" = 1 ] || [ ! -x "$TV_OUT" ] || ! stamp_ok "$TV_SRC" "$DATA/bin/.thumbvision-src-sha256"; then
    SWIFT_TODO=1
    status "thumbvision" should "da fare" "swiftc -O → $TV_OUT (≈ 1 min)"
  else
    status "thumbvision" should ok "$TV_OUT (sorgente invariato)"
  fi
elif [ "${MACOS_MAJOR:-0}" -ge 26 ] 2>/dev/null; then
  status "thumbvision" should ok "binario incluso nel plugin (swiftc assente; per compilarlo: xcode-select --install)"
else
  status "thumbvision" should manca "serve swiftc (xcode-select --install, poi rilancia): il binario incluso richiede macOS 26"
fi

# ── 8. Facoltativi ───────────────────────────────────────────────────────────
senko_ok() {
  [ -x "$SENKO_VENV/bin/python" ] || return 1
  grep -qs "$SENKO_SHA" "$SENKO_VENV"/lib/python3.*/site-packages/senko-*.dist-info/direct_url.json
}
rembg_ok() {
  [ -x "$REMBG_VENV/bin/python" ] && ls "$REMBG_VENV"/lib/python3.*/site-packages/rembg-2.0.85.dist-info >/dev/null 2>&1 \
    && [ "$(stat -f %z "$REMBG_MODEL" 2>/dev/null || echo 0)" -eq "$R_SIZE" ]
}
SENKO_TODO=0; REMBG_TODO=0; MP_TODO=0
if senko_ok; then
  status "Senko (diarizzazione)" optional ok "$SENKO_VENV · commit ${SENKO_SHA:0:7}"
elif [ "$WITH_SENKO" = 1 ]; then
  SENKO_TODO=1; plan_bytes 560000000
  status "Senko (diarizzazione)" optional "da fare" "venv $SENKO_VENV al commit ${SENKO_SHA:0:7} (≈ 560 MB)"
else
  status "Senko (diarizzazione)" optional saltato "non installato: yt-speakers non disponibile (--with-senko, ≈ 560 MB)"
fi
if rembg_ok; then
  status "rembg + birefnet-portrait" optional ok "$REMBG_VENV"
elif [ "$WITH_REMBG" = 1 ]; then
  REMBG_TODO=1; plan_bytes $((370000000 + R_SIZE))
  status "rembg + birefnet-portrait" optional "da fare" "venv $REMBG_VENV + modello $(mb "$R_SIZE") (≈ 1,3 GB in tutto)"
else
  status "rembg + birefnet-portrait" optional saltato "non installato: yt-portrait cut ripiega su Apple Vision (--with-rembg, ≈ 1,3 GB)"
fi
if mp_ok; then
  status "MediaPipe (espressioni)" optional ok "mediapipe 1.1.0 nel venv · $MP_MODEL"
elif [ "$WANT_MP" = 1 ]; then
  MP_TODO=1
  mp_pkg_ok || plan_bytes 200000000
  mp_model_ok || plan_bytes "$MP_SIZE"
  status "MediaPipe (espressioni)" optional "da fare" "extra «${MP_EXTRA}» nel venv (≈ 200 MB con opencv-contrib) + face_landmarker.task $(mb "$MP_SIZE") (SHA256 verificato)"
else
  status "MediaPipe (espressioni)" optional saltato "non installato: yt-portrait scan usa solo la geometria di Apple Vision (--with-mediapipe, ≈ 200 MB)"
fi

if [ "$CODEX" = 1 ]; then
  if /bin/bash "$YT_HOME/bin/codex-shims.sh" --data "$DATA" --check >/dev/null 2>&1; then
    status "comandi yt-* per Codex" should ok "$DATA/shims"
  else
    status "comandi yt-* per Codex" should "da fare" "shim in $DATA/shims (codex-shims.sh), dopo il setup"
  fi
fi

print_status() {
  local i n="${#STATUS_NAMES[@]}"
  for ((i = 0; i < n; i++)); do
    printf '  %-8s %-9s %-32s %s\n' "${STATUS_LEVELS[$i]}" "${STATUS_STATES[$i]}" "${STATUS_NAMES[$i]}" "${STATUS_DETAILS[$i]}"
  done
}

# ── Piano ────────────────────────────────────────────────────────────────────
if [ "$YES" != 1 ]; then
  print_status
  hr
  if [ "$PLANNED" -eq 0 ]; then
    say "Niente da installare."
  else
    say "Da fare: $PLANNED voci · download e spazio stimati ≈ $(mb "$PLANNED_BYTES")."
    say "Per procedere: $YT_HOME/install.sh --yes$( [ -n "$DATA_OPT" ] && printf ' --data %q' "$DATA_OPT")$( [ "$WITH_SENKO" = 1 ] && printf ' --with-senko')$( [ "$WITH_REMBG" = 1 ] && printf ' --with-rembg')$( [ "$WITH_MP" = 1 ] && printf ' --with-mediapipe')$( [ "$SKIP_SYSTEM" = 1 ] && printf ' --skip-system')$( [ "$CODEX" = 1 ] && printf ' --codex')"
  fi
  if [ "$MUST_FAIL" = 1 ]; then
    say "Attenzione: ci sono requisiti 'must' mancanti che questo script non installa (vedi sopra)."
  fi
  exit 0
fi

# ── Esecuzione ───────────────────────────────────────────────────────────────
STATUS_NAMES=(); STATUS_LEVELS=(); STATUS_STATES=(); STATUS_DETAILS=(); MUST_FAIL=0; PLANNED=0
say "Totale stimato da scaricare/installare: ≈ $(mb "$PLANNED_BYTES")."
status "macOS Apple Silicon" must ok "macOS $MACOS · $ARCH"

# bit di esecuzione dei lanciatori del plugin (i comandi yt-* sono link a bin/_run): si possono perdere copiando la
# cartella a mano o con un archivio. Solo chmod +x dove manca, nessun altro cambiamento ai file del plugin.
NOEXEC=()
for f in "$YT_HOME/bin/_run" "$YT_HOME/bin/guard.sh" "$YT_HOME/bin/session-hint.sh" "$YT_HOME/bin/thumbvision" "$YT_HOME/install.sh" \
         "$YT_HOME/bin/codex-shims.sh"; do
  [ -f "$f" ] && [ ! -x "$f" ] && NOEXEC+=("$f")
done
if [ "${#NOEXEC[@]}" -gt 0 ]; then
  if chmod +x "${NOEXEC[@]}" 2>/dev/null; then
    status "lanciatori yt-*" must fatto "bit di esecuzione ripristinato su ${#NOEXEC[@]} file"
  else
    status "lanciatori yt-*" must errore "chmod +x non riuscito: reinstalla il plugin (README, Problemi frequenti)"
  fi
else
  status "lanciatori yt-*" must ok "eseguibili"
fi

if [ "${#FORMULAE[@]}" -gt 0 ] || [ "${UPGRADE_WHISPER:-0}" = 1 ]; then
  hr
  if [ "${#FORMULAE[@]}" -gt 0 ]; then
    say "Homebrew: brew install ${FORMULAE[*]}"
    if HOMEBREW_NO_ENV_HINTS=1 "$BREW" install "${FORMULAE[@]}"; then
      status "formule Homebrew" must fatto "${FORMULAE[*]}"
    else
      status "formule Homebrew" must errore "brew install ${FORMULAE[*]} non riuscito (vedi sopra)"
    fi
  fi
  if [ "${UPGRADE_WHISPER:-0}" = 1 ]; then
    say "Homebrew: brew upgrade whisper-cpp (per parakeet-cli)"
    HOMEBREW_NO_ENV_HINTS=1 "$BREW" upgrade whisper-cpp || status "parakeet-cli" should errore "brew upgrade whisper-cpp non riuscito"
  fi
fi
for b in "ffmpeg-full|$FFMPEG_BIN" "whisper-cli|/opt/homebrew/bin/whisper-cli" "yt-dlp|/opt/homebrew/bin/yt-dlp" "auto-editor|/opt/homebrew/bin/auto-editor"; do
  n="${b%%|*}"; p="${b#*|}"
  if [ -x "$p" ]; then status "$n" must ok "$p"; else status "$n" must manca "manca $p"; fi
done
if [ -x /opt/homebrew/bin/parakeet-cli ]; then status "parakeet-cli" should ok "/opt/homebrew/bin/parakeet-cli"
else status "parakeet-cli" should manca "manca /opt/homebrew/bin/parakeet-cli (whisper.cpp ≥ 1.9.5)"; fi
if [ -z "$UV" ]; then
  UV="$(command -v uv || true)"; [ -n "$UV" ] || { [ -x /opt/homebrew/bin/uv ] && UV=/opt/homebrew/bin/uv; }
fi
[ -n "$UV" ] && status "uv" must ok "$UV" || status "uv" must manca "uv non trovato"
[ -n "$NODE" ] || NODE="$(find_node || true)"
[ -n "$NODE" ] && status "node 20+" must ok "$("$NODE" --version) · $NODE" || status "node 20+" must manca "node 20+ non trovato"

if [ "${#MODEL_TODO[@]}" -gt 0 ]; then
  hr
  say "Modelli in $MODELS_DIR:"
  for m in "${MODEL_TODO[@]}"; do
    IFS='|' read -r name url want size label <<EOF
$m
EOF
    download_verified "$url" "$MODELS_DIR/$name" "$want" "$size" "$label" || true   # l'esito lo dice il controllo sotto
  done
fi
for m in "modello whisper large-v3-turbo|must|$W_NAME" "modello VAD Silero v6.2.0|must|$V_NAME" "modello Parakeet TDT 0.6B v3|should|ggml-parakeet-tdt-0.6b-v3*.bin"; do
  IFS='|' read -r label lvl pat <<EOF
$m
EOF
  f="$(ls "$MODELS_DIR"/$pat 2>/dev/null | sort | head -1)"
  if [ -n "$f" ]; then status "$label" "$lvl" ok "$(basename "$f")"; else status "$label" "$lvl" manca "manca $MODELS_DIR/$pat"; fi
done

# studio_dir (work, cache, data, secrets)
STUDIO="$(/usr/bin/python3 -I "$YT_HOME/lib/config.py" --get studio_dir 2>/dev/null || true)"
[ -n "$STUDIO" ] || STUDIO="${YT_STUDIO:-$HOME/youtube-studio}"
if mkdir -p "$STUDIO/work" "$STUDIO/cache" "$STUDIO/data" && { [ -d "$STUDIO/secrets" ] || mkdir -m 700 "$STUDIO/secrets"; }; then
  status "studio_dir" must ok "$STUDIO (work, cache, data, secrets)"
else
  status "studio_dir" must errore "impossibile creare $STUDIO/{work,cache,data,secrets}"
fi

mkdir -p "$DATA" || { say "ERRORE: impossibile creare $DATA"; exit 1; }

# venv
if [ "$VENV_TODO" = 1 ] && [ -n "$UV" ]; then
  hr
  say "Python: uv sync --frozen → $DATA/venv"
  [ "$FORCE" = 1 ] && rm -rf "$DATA/venv"
  [ "${#SYNC_EXTRAS[@]}" -gt 0 ] && say "  con gli extra: ${SYNC_EXTRAS[*]}"
  if UV_PROJECT_ENVIRONMENT="$DATA/venv" "$UV" sync --frozen --no-install-project --python 3.12 --project "$YT_HOME" ${SYNC_EXTRAS[@]+"${SYNC_EXTRAS[@]}"}; then
    sha256 "$YT_HOME/uv.lock" > "$DATA/venv/$LOCK_STAMP"
    if [ "$WANT_MP" = 1 ]; then printf '%s\n' "$MP_EXTRA" > "$EXTRAS_FILE"; else rm -f "$EXTRAS_FILE"; fi
  else
    VENV_ERR=1
  fi
fi
if [ "${VENV_ERR:-0}" = 1 ]; then
  status "venv Python 3.12" must errore "uv sync non riuscito (vedi sopra)"
elif [ -x "$DATA/venv/bin/python" ]; then
  if "$DATA/venv/bin/python" -c "import numpy, scipy, librosa, soundfile, matplotlib, PIL, requests, yaml, googleapiclient, google_auth_oauthlib" 2>/dev/null; then
    status "venv Python 3.12" must ok "$("$DATA/venv/bin/python" --version 2>&1) · $DATA/venv"
  else
    status "venv Python 3.12" must errore "import dei moduli fallito in $DATA/venv: rilancia con --force"
  fi
else
  status "venv Python 3.12" must manca "manca $DATA/venv"
fi

npm_ci() {   # cartella
  local dir="$1" npm
  npm="$(dirname "$NODE")/npm"
  [ -x "$npm" ] || npm="$(command -v npm || true)"
  [ -n "$npm" ] || { say "  ✗ npm non trovato accanto a $NODE"; return 1; }
  (cd "$dir" && PATH="$(dirname "$NODE"):$PATH" PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    npm_config_fund=false npm_config_audit=false npm_config_update_notifier=false \
    "$npm" ci --no-audit --no-fund)
}

sync_remotion_sources() {   # sorgenti Remotion + assets/brands (brand.ts importa ../../../assets/brands/…/tokens.json)
  mkdir -p "$DATA/remotion" "$DATA/assets/brands"
  rsync -a --delete --exclude node_modules --exclude .remotion --exclude out --exclude build \
    --exclude "$LOCK_STAMP" --exclude .DS_Store "$YT_HOME/remotion/" "$DATA/remotion/" &&
  rsync -a --delete --exclude .DS_Store "$YT_HOME/assets/brands/" "$DATA/assets/brands/"
}

# Playwright
if [ -n "$NODE" ]; then
  if [ "$NODE_TODO" = 1 ]; then
    hr
    say "Playwright: npm ci → $DATA/node"
    mkdir -p "$DATA/node"
    cp -f "$YT_HOME/node/package.json" "$YT_HOME/node/package-lock.json" "$DATA/node/"
    if npm_ci "$DATA/node"; then
      sha256 "$YT_HOME/node/package-lock.json" > "$DATA/node/$LOCK_STAMP"
    fi
  fi
  if [ -f "$DATA/node/node_modules/playwright/package.json" ] && stamp_ok "$YT_HOME/node/package-lock.json" "$DATA/node/$LOCK_STAMP"; then
    status "Playwright 1.64.0" should ok "$DATA/node"
  else
    status "Playwright 1.64.0" should errore "npm ci in $DATA/node non riuscito"
  fi
  # Remotion
  if [ "$REMO_TODO" = 1 ]; then
    hr
    say "Remotion: copia del progetto + npm ci → $DATA/remotion"
    mkdir -p "$DATA/remotion"
    sync_remotion_sources
    if npm_ci "$DATA/remotion"; then
      sha256 "$YT_HOME/remotion/package-lock.json" > "$DATA/remotion/$LOCK_STAMP"
    fi
  else
    sync_remotion_sources 2>/dev/null || true
  fi
  if [ -f "$DATA/remotion/node_modules/remotion/package.json" ] && stamp_ok "$YT_HOME/remotion/package-lock.json" "$DATA/remotion/$LOCK_STAMP"; then
    status "Remotion 4.0.534" should ok "$DATA/remotion"
  else
    status "Remotion 4.0.534" should errore "npm ci in $DATA/remotion non riuscito"
  fi
else
  status "Playwright 1.64.0" should manca "serve node 20+"
  status "Remotion 4.0.534" should manca "serve node 20+"
fi

# thumbvision
if [ "$SWIFT_TODO" = 1 ]; then
  hr
  say "thumbvision: swiftc -O → $TV_OUT"
  mkdir -p "$DATA/bin"
  if xcrun swiftc -O "$TV_SRC" -o "$TV_OUT.tmp" && "$TV_OUT.tmp" version >/dev/null 2>&1; then
    mv -f "$TV_OUT.tmp" "$TV_OUT"
    sha256 "$TV_SRC" > "$DATA/bin/.thumbvision-src-sha256"
  else
    rm -f "$TV_OUT.tmp"
    say "  ✗ compilazione non riuscita: resta il binario incluso nel plugin"
  fi
fi
if [ -x "$TV_OUT" ] && "$TV_OUT" version >/dev/null 2>&1; then
  status "thumbvision" should ok "compilato per questo Mac · $TV_OUT"
elif "$YT_HOME/bin/thumbvision" version >/dev/null 2>&1; then
  status "thumbvision" should ok "binario incluso nel plugin ($YT_HOME/bin/thumbvision)"
else
  status "thumbvision" should errore "nessun thumbvision eseguibile: xcode-select --install, poi rilancia"
fi

# Senko
if [ "$SENKO_TODO" = 1 ] && [ -n "$UV" ]; then
  hr
  say "Senko: venv $SENKO_VENV al commit $SENKO_SHA (≈ 560 MB)"
  [ -x "$SENKO_VENV/bin/python" ] || "$UV" venv -p 3.12 "$SENKO_VENV"
  "$UV" pip install --python "$SENKO_VENV/bin/python" -c "$YT_HOME/setup/senko-constraints.txt" "$SENKO_REQ" \
    || say "  ✗ installazione di Senko non riuscita (serve git: xcode-select --install)"
fi
if senko_ok; then status "Senko (diarizzazione)" optional ok "$SENKO_VENV"
elif [ "$WITH_SENKO" = 1 ]; then status "Senko (diarizzazione)" optional errore "installazione non riuscita"
else status "Senko (diarizzazione)" optional saltato "non installato (--with-senko)"; fi

# rembg
if [ "$REMBG_TODO" = 1 ] && [ -n "$UV" ]; then
  hr
  say "rembg: venv $REMBG_VENV ($REMBG_REQ) + modello birefnet-portrait"
  [ -x "$REMBG_VENV/bin/python" ] || "$UV" venv -p 3.12 "$REMBG_VENV"
  "$UV" pip install --python "$REMBG_VENV/bin/python" -c "$YT_HOME/setup/rembg-constraints.txt" "$REMBG_REQ" \
    || say "  ✗ installazione di rembg non riuscita"
  if [ "$(stat -f %z "$REMBG_MODEL" 2>/dev/null || echo 0)" -ne "$R_SIZE" ]; then
    download_verified "$R_URL" "$REMBG_MODEL" "$R_SHA" "$R_SIZE" "birefnet-portrait.onnx" || true
  fi
fi
if rembg_ok; then status "rembg + birefnet-portrait" optional ok "$REMBG_VENV"
elif [ "$WITH_REMBG" = 1 ]; then status "rembg + birefnet-portrait" optional errore "installazione non riuscita"
else status "rembg + birefnet-portrait" optional saltato "non installato: ripiego Apple Vision (--with-rembg)"; fi

# MediaPipe (extra del venv, già sincronizzato sopra) + modello
if [ "$MP_TODO" = 1 ] && ! mp_model_ok; then
  hr
  say "MediaPipe: modello face_landmarker.task → $MP_MODEL"
  download_verified "$MP_URL" "$MP_MODEL" "$MP_SHA" "$MP_SIZE" "face_landmarker.task" || true
fi
if mp_ok; then
  if "$DATA/venv/bin/python" -c "import mediapipe" 2>/dev/null; then
    status "MediaPipe (espressioni)" optional ok "mediapipe 1.1.0 · $MP_MODEL"
  else
    status "MediaPipe (espressioni)" optional errore "import mediapipe fallito nel venv: rilancia con --force --with-mediapipe"
  fi
elif [ "$WANT_MP" = 1 ]; then
  status "MediaPipe (espressioni)" optional errore "$(mp_pkg_ok && echo "modello assente o SHA256 diverso ($MP_MODEL)" || echo "extra mediapipe non installato nel venv")"
else
  status "MediaPipe (espressioni)" optional saltato "non installato: solo geometria Apple Vision (--with-mediapipe)"
fi

# ── 9. Marcatore e riepilogo ─────────────────────────────────────────────────
COMMIT=""
case "$YT_HOME" in */plugins/cache/*/scripts/yt) COMMIT="$(basename "$(dirname "$(dirname "$YT_HOME")")")" ;; esac
[ -n "$COMMIT" ] || COMMIT="$(git -C "$PLUGIN_ROOT" rev-parse --verify -q HEAD 2>/dev/null || true)"
[ -n "$COMMIT" ] || COMMIT="sviluppo"
hr
say "Riepilogo"
print_status
hr
if [ "$MUST_FAIL" = 1 ]; then
  rm -f "$DATA/.setup-ok"
  say "Setup NON completo: mancano requisiti 'must' (sopra). Correggi e rilancia: è idempotente."
  RC=1
else
  {
    printf 'commit=%s\n' "$COMMIT"
    printf 'date=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'fingerprint=%s\n' "$(yt_fingerprint)"
    printf 'plugin_root=%s\n' "$PLUGIN_ROOT"
    printf 'senko=%s\n' "$(senko_ok && echo si || echo no)"
    printf 'rembg=%s\n' "$(rembg_ok && echo si || echo no)"
    printf 'mediapipe=%s\n' "$(mp_ok && echo si || echo no)"
  } > "$DATA/.setup-ok.tmp" && mv -f "$DATA/.setup-ok.tmp" "$DATA/.setup-ok"
  if [ "$CODEX" = 1 ]; then
    case "$YT_HOME" in */plugins/cache/*/scripts/yt) VLABEL="versione" ;; *) VLABEL="commit" ;; esac
    say "Setup completo: marcatore $DATA/.setup-ok ($VLABEL $COMMIT)."
  else
    say "Setup completo: marcatore $DATA/.setup-ok (commit $COMMIT)."
  fi
  RC=0
fi
# ── 10. Solo Codex: comandi yt-* (Codex installa il plugin senza symlink e senza bin/ nel PATH) ──
if [ "$CODEX" = 1 ]; then
  hr
  if ! /bin/bash "$YT_HOME/bin/codex-shims.sh" --data "$DATA"; then
    say "Comandi yt-* per Codex NON creati (sopra il motivo): rilancia $SETUP_CMD."
    RC=1
  fi
  say "Cartelle che i comandi devono poter scrivere nella sandbox di Codex: se non l'hai già fatto, incolla tu"
  say "questo blocco in fondo a ~/.codex/config.toml (open -e ~/.codex/config.toml), poi riavvia l'app o riapri la CLI."
  say "Il plugin non cambia la configurazione di Codex:"
  /bin/bash "$YT_HOME/bin/codex-shims.sh" --data "$DATA" --print-config | sed 's/^/  /'
  hr
fi
say "Spazio occupato:"
TOTAL_K=0
for p in "$DATA/venv" "$DATA/node" "$DATA/remotion" "$DATA/bin" "$DATA/models" "$MODELS_DIR" "$SENKO_VENV" "$REMBG_VENV"; do
  [ -e "$p" ] || continue
  k="$(du -sk "$p/" 2>/dev/null | cut -f1)"; k="${k:-0}"   # «/» finale: segue un symlink (es. ~/.whisper-models)
  TOTAL_K=$((TOTAL_K + k))
  printf '  %10s  %s\n' "$(mb $((k * 1024)))" "$p"
done
printf '  %10s  totale\n' "$(mb $((TOTAL_K * 1024)))"
if [ "$CODEX" = 1 ]; then
  say "Prossimo passo: torna nella conversazione di Codex e scrivi \$youtube:setup. Riprende da qui: riga PATH,"
  say "cartelle scrivibili, extra e domande di configurazione, poi il doctor e il primo canale."
else
  say "Verifica completa dell'ambiente: yt-doctor"
fi
exit "$RC"
