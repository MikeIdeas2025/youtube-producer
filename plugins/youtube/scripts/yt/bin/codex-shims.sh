#!/bin/bash
# codex-shims.sh — i comandi yt-* di YouTube Producer per OpenAI Codex.
#
# Codex installa il plugin senza i symlink (bin/yt-* → _run) e non mette bin/ del plugin nel PATH. Questo script crea
# nella data dir del plugin (<data>/shims, fuori dalla cache: sopravvive agli aggiornamenti) un lanciatore .yt-shim e un
# symlink per ogni comando di codex/toolkit-commands.txt. Lo shim cerca a ogni chiamata la versione del plugin
# installata in Codex, quindi un aggiornamento del plugin non richiede di rifarli.
#
# Uso:
#   codex-shims.sh [--data DIR]          crea o aggiorna <data>/shims (lo lancia install.sh --codex)
#   codex-shims.sh --check               stato in JSON (shim presenti, versione a cui puntano, PATH)
#   codex-shims.sh --print-path-line     la riga da aggiungere al profilo della shell (~/.zprofile)
#   codex-shims.sh --add-path            aggiunge quella riga a ~/.zprofile (o ~/.bash_profile), una volta sola:
#                                        solo con l'OK dell'operatore
#   codex-shims.sh --print-config        il blocco per ~/.codex/config.toml (cartelle scrivibili dalla sandbox), con i
#                                        percorsi di questo Mac: lo incolla l'operatore, a mano. Va rilanciato dopo
#                                        l'onboarding di un canale con vault.deliverables (aggiunge le sue cartelle).
#                                        La data dir del plugin non c'è mai: contiene i programmi (venv, node, shim,
#                                        thumbvision) che girano anche fuori dalla sandbox
# Opzioni: --data DIR (data dir del plugin; default come _paths.sh: YT_DATA, CLAUDE_PLUGIN_DATA, cache dei plugin)
set -u

src="$0"
while [ -L "$src" ]; do
  dir="$(cd -P "$(dirname "$src")" && pwd)"
  src="$(readlink "$src")"
  case "$src" in /*) ;; *) src="$dir/$src" ;; esac
done
here="$(cd -P "$(dirname "$src")" && pwd)"
YT_HOME="$(cd -P "$here/.." && pwd)"
PLUGIN_ROOT="$(cd -P "$YT_HOME/../.." && pwd)"
# shellcheck source=_paths.sh
. "$here/_paths.sh"

MARK="# YouTube Producer (Codex)"
ACTION=create; DATA_OPT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --data) shift; DATA_OPT="${1:-}"; [ -n "$DATA_OPT" ] || { echo "--data richiede una cartella" >&2; exit 2; } ;;
    --data=*) DATA_OPT="${1#--data=}" ;;
    --check) ACTION=check ;;
    --print-path-line) ACTION=pathline ;;
    --add-path) ACTION=addpath ;;
    --print-config) ACTION=config ;;
    -h|--help) sed -n '2,20p' "$src" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "opzione sconosciuta: $1 (vedi --help)" >&2; exit 2 ;;
  esac
  shift
done

DATA="${DATA_OPT:-$(yt_data_dir)}"
if [ -z "$DATA" ]; then
  echo "checkout di sviluppo con il layout storico (venv in $YT_HOME/.venv): passa --data DIR" >&2
  exit 2
fi
case "$DATA" in "~"|"~/"*) DATA="$HOME${DATA#\~}" ;; esac
case "$DATA" in /*) ;; *) DATA="$(pwd)/$DATA" ;; esac
SHIMS="$DATA/shims"

json_str() {  # stringa JSON
  local s="$1"
  s="${s//\\/\\\\}"; s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"; s="${s//$'\t'/\\t}"
  printf '"%s"' "$s"
}

path_line() {
  local p="$SHIMS"
  case "$p" in "$HOME"/*) p="\$HOME/${p#"$HOME"/}" ;; esac
  printf 'export PATH="%s:$PATH"   %s\n' "$p" "$MARK"
}

# Cartella della cache di Codex che contiene le versioni del plugin (…/plugins/cache/<marketplace>/<plugin>); vuota se
# il toolkit non gira da una cache (checkout di sviluppo: lo shim punta a questa copia).
cache_base() {
  case "$YT_HOME" in
    */plugins/cache/*/scripts/yt)
      local rest after mkt plugin ver extra
      rest="${YT_HOME%/scripts/yt}"
      after="${rest#*/plugins/cache/}"
      IFS=/ read -r mkt plugin ver extra <<EOF
$after
EOF
      if [ -n "$mkt" ] && [ -n "$plugin" ] && [ -n "$ver" ] && [ -z "$extra" ]; then
        printf '%s\n' "${rest%/*}"
        return 0
      fi
      ;;
  esac
  printf '\n'
}

names() {  # nomi dei comandi: codex/toolkit-commands.txt (generato da scripts/codex/build_skills.py)
  local list="$PLUGIN_ROOT/codex/toolkit-commands.txt" n
  if [ -f "$list" ]; then
    while IFS= read -r n || [ -n "$n" ]; do
      case "$n" in yt-*|thumbvision) printf '%s\n' "$n" ;; esac
    done < "$list"
  elif [ -d "$PLUGIN_ROOT/bin" ] && ls "$PLUGIN_ROOT"/bin/yt-* >/dev/null 2>&1; then
    for n in "$PLUGIN_ROOT"/bin/yt-* "$PLUGIN_ROOT"/bin/thumbvision; do [ -e "$n" ] || [ -L "$n" ] && basename "$n"; done
  fi
}

target_now() {  # scripts/yt a cui punterebbe uno shim adesso
  local base
  base="$(cache_base)"
  if [ -n "$base" ]; then
    ls -td "$base"/*/scripts/yt 2>/dev/null | head -n 1
  else
    printf '%s\n' "$YT_HOME"
  fi
}

case "$ACTION" in
  pathline)
    path_line
    exit 0
    ;;
  addpath)
    case "$(basename "${SHELL:-/bin/zsh}")" in
      zsh) prof="$HOME/.zprofile" ;;
      bash) prof="$HOME/.bash_profile" ;;
      *) echo "Shell $(basename "${SHELL:-?}") non gestita: aggiungi tu questa riga al suo profilo:"; path_line; exit 1 ;;
    esac
    if [ -f "$prof" ] && grep -qF "$MARK" "$prof"; then
      echo "La riga di YouTube Producer è già in $prof: niente da fare."
      exit 0
    fi
    { [ ! -s "$prof" ] || [ -z "$(tail -c 1 "$prof")" ] || printf '\n'; path_line; } >> "$prof" || {
      echo "Non riesco a scrivere $prof: aggiungi tu questa riga:"; path_line; exit 1; }
    echo "Aggiunta a $prof:"
    path_line
    echo "Vale per le conversazioni nuove di Codex (l'app va riavviata) e per i Terminali nuovi."
    exit 0
    ;;
  config)
    PYTHONPYCACHEPREFIX="" YT_SHIMS_DATA="$DATA" /usr/bin/python3 -I -B - "$YT_HOME/lib" <<'PY'
import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import config
s = config.settings()
cfgdir = config.config_path().parent
home = Path(os.path.expanduser("~")).resolve()


def too_broad(p):
    """La home, una sua cartella madre o una cartella di primo livello (/, /Users, /Volumes/X): mai scrivibile per intero
    (succede con YT_CONFIG=~/config.yaml o studio_dir: ~)."""
    try:
        r = Path(p).expanduser().resolve()
    except (OSError, RuntimeError):
        r = Path(os.path.normpath(os.path.expanduser(str(p))))
    return r == home or r in home.parents or len(r.parts) <= 3 and r.parts[1:2] in (("Volumes",), ("Users",)) \
        or len(r.parts) <= 2


roots, skipped = [], []
data = Path(os.environ["YT_SHIMS_DATA"])
for d in [s["studio_dir"], cfgdir, *s["channels_dirs_extra"], *s["brands_dirs_extra"]]:
    d = Path(d)
    if too_broad(d):
        skipped += [d] if d not in skipped else []
    elif d == data or data in d.parents or d in data.parents:
        continue        # la data dir (o una cartella che la contiene) mai: vedi sotto
    elif d not in roots and not any(r in d.parents for r in roots):
        roots.append(d)
try:
    vault = [v for v in config.vault_deliverable_dirs(s) if not too_broad(v)] if s["vault_path"] else []
except Exception:
    vault = []
q = lambda p: json.dumps(str(p), ensure_ascii=False)
print("# YouTube Producer — cartelle che i comandi del toolkit possono scrivere quando Codex lavora in sandbox")
print("# (modalità workspace-write: nell'app «Chiedi approvazione», in inglese «Ask for approval»). Incollalo tu in fondo")
print("# a ~/.codex/config.toml, poi riavvia l'app o riapri la CLI; se lì c'è già [sandbox_workspace_write], aggiungi")
print("# questi percorsi alla sua lista writable_roots; se c'è default_permissions, non incollarlo e chiedi prima.")
print("[sandbox_workspace_write]")
print("writable_roots = [")
for r in roots:
    print(f"  {q(r)},")
for r in skipped:
    print(f"  # escluso {q(r)}: è la home o una cartella troppo ampia: tieni configurazione e studio in una sottocartella")
if vault:
    print("  # vault Obsidian: solo le cartelle deliverable dei profili canale, mai il vault intero")
    for v in vault:
        print(f"  {q(v)},")
else:
    print("  # vault Obsidian (se lo usi): solo la cartella deliverable di ogni profilo, mai il vault intero; il setup")
    print("  # rilancia questo comando dopo l'onboarding di un canale con vault.deliverables e ti mostra le righe nuove")
print(f"  # esclusa la data dir del plugin {q(data)}: venv, node, shim e thumbvision girano anche fuori dalla sandbox")
print("]")
print("network_access = false   # resta spento: Codex chiede il permesso ai comandi che vanno in rete")
PY
    exit $?
    ;;
  check)
    want=0; have=0; missing=""
    for n in $(names); do
      want=$((want + 1))
      if [ -L "$SHIMS/$n" ] && [ "$(readlink "$SHIMS/$n")" = ".yt-shim" ]; then have=$((have + 1))
      else missing="${missing:+$missing, }$(json_str "$n")"; fi
    done
    tgt="$(target_now)"
    resolved="$(command -v yt-config 2>/dev/null || true)"
    onpath=false
    case "$resolved" in "$SHIMS"/*) onpath=true ;; esac
    ok=false
    if [ "$want" -gt 0 ] && [ "$have" = "$want" ] && [ -x "$SHIMS/.yt-shim" ] && [ -n "$tgt" ] && [ -f "$tgt/bin/_run" ]; then ok=true; fi
    printf '{\n  "ok": %s,\n  "shims_dir": %s,\n  "shims": %s,\n  "expected": %s,\n  "missing": [%s],\n  "target": %s,\n  "on_path": %s,\n  "yt_config": %s,\n  "path_line": %s\n}\n' \
      "$ok" "$(json_str "$SHIMS")" "$have" "$want" "$missing" "$(json_str "$tgt")" "$onpath" "$(json_str "$resolved")" \
      "$(json_str "$(path_line)")"
    [ "$ok" = true ]
    exit $?
    ;;
esac

# ── crea o aggiorna gli shim ──
list="$(names)"
if [ -z "$list" ]; then
  echo "codex-shims.sh: manca $PLUGIN_ROOT/codex/toolkit-commands.txt (si genera con scripts/codex/build_skills.py)" >&2
  exit 1
fi
base="$(cache_base)"
fixed=""
[ -n "$base" ] || fixed="$YT_HOME"
mkdir -p "$SHIMS" || { echo "codex-shims.sh: impossibile creare $SHIMS" >&2; exit 1; }
tmp="$SHIMS/.yt-shim.$$"
{
  printf '%s\n' '#!/bin/bash' \
    '# YouTube Producer (Codex): shim generato da codex-shims.sh (non modificarlo: lo rigenera $youtube:setup).' \
    '# Lancia il comando del toolkit con il suo stesso nome dalla versione del plugin installata in Codex.' \
    'set -u' \
    'cmd="$(basename "$0")"' \
    'here_l="$(dirname "$0")"' \
    'here="$(cd -P "$here_l" 2>/dev/null && pwd)"' \
    '# Dentro Claude Code (CLAUDECODE=1) lascia il passo ai comandi del plugin di Claude, se nel PATH ce ne sono.' \
    'if [ -n "${CLAUDECODE:-}" ]; then' \
    '  p="$(printf '"'"'%s'"'"' "$PATH" | tr '"'"':'"'"' '"'"'\n'"'"' | grep -vxF -e "$here" -e "$here_l" | paste -sd: -)"' \
    '  if next="$(PATH="$p" command -v "$cmd")"; then PATH="$p" exec "$next" "$@"; fi' \
    'fi'
  printf 'base=%q\n' "$base"
  printf 'fixed=%q\n' "$fixed"
  printf '%s\n' \
    'if [ -n "$base" ]; then yt="$(ls -td "$base"/*/scripts/yt 2>/dev/null | head -n 1)"; else yt="$fixed"; fi' \
    'if [ -z "$yt" ] || [ ! -f "$yt/bin/_run" ]; then' \
    '  m="YouTube Producer non risulta installato in Codex (${base:-$fixed}): reinstalla il plugin, poi \$youtube:setup"' \
    '  printf '"'"'{\n  "ok": false,\n  "error": "%s"\n}\n'"'"' "$m"' \
    '  echo "$m" >&2' \
    '  exit 3' \
    'fi' \
    'case "$cmd" in' \
    '  yt-install) exec /bin/bash "$yt/install.sh" --codex "$@" ;;' \
    '  *) exec /bin/bash "$yt/bin/_run" "$cmd" "$@" ;;' \
    'esac'
} > "$tmp" && chmod 755 "$tmp" && mv -f "$tmp" "$SHIMS/.yt-shim" || {
  rm -f "$tmp"; echo "codex-shims.sh: impossibile scrivere $SHIMS/.yt-shim" >&2; exit 1; }
n_ok=0
for n in $list; do
  case "$n" in yt-[a-z0-9]*|thumbvision) ;; *) continue ;; esac
  ln -sfn .yt-shim "$SHIMS/$n" && n_ok=$((n_ok + 1))
done
# shim di comandi che non esistono più
for f in "$SHIMS"/*; do
  [ -L "$f" ] && [ "$(readlink "$f")" = ".yt-shim" ] || continue
  case "
$list
" in *"
$(basename "$f")
"*) ;; *) rm -f "$f" ;; esac
done
echo "Comandi yt-* per Codex: $n_ok shim in $SHIMS → ${base:+versione più recente in }${base:-$fixed}"
case "$(command -v yt-config 2>/dev/null)" in
  "$SHIMS"/*) echo "Sono già nel PATH." ;;
  *) echo "Per usarli per nome serve questa riga nel profilo della shell:"
     path_line
     printf 'La aggiunge, con il tuo OK: bash %q --add-path\n' "$here/codex-shims.sh" ;;
esac
exit 0
