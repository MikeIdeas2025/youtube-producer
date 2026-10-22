#!/bin/bash
# session-hint.sh — hook SessionStart del plugin youtube (hooks/hooks.json; in Codex codex/hooks.json con --codex).
# Solo shell + sqlite3, < 1 s, non installa nulla.
# 1. Setup: stampa UNA riga (in italiano) che suggerisce /youtube:setup quando il setup del toolkit manca o è vecchio:
#      - manca <data>/.setup-ok, oppure
#      - install.sh è più recente del marcatore E l'impronta di install.sh + lock (uv.lock, package-lock,
#        sorgente Swift) è cambiata (un aggiornamento del plugin che non tocca le dipendenze non disturba).
# 2. Apprendimento (13-learning-loop.md §7.3): al massimo due righe quando qualcosa è dovuto — esiti da leggere e
#    post-mortem (viste learn_due_v di yt-learn e thumb_learn_due di yt-thumb-learn in <studio_dir>/data/yt.db, una
#    volta per video e checkpoint), proposte di miglioramento in attesa, rinfresco mensile dei riferimenti. Muto se
#    non c'è niente, se il database o le viste mancano o se sqlite3 non risponde.
# Uscita: un solo oggetto JSON (solo se c'è qualcosa da dire) con `systemMessage` (lo vede l'operatore: lo stdout semplice
# di SessionStart arriva solo a Claude) e `hookSpecificOutput.additionalContext` (le stesse righe per Claude). Esce sempre
# con 0.
src="$0"
while [ -L "$src" ]; do
  dir="$(cd -P "$(dirname "$src")" && pwd)"
  src="$(readlink "$src")"
  case "$src" in /*) ;; *) src="$dir/$src" ;; esac
done
YT_HOME="$(cd -P "$(dirname "$src")/.." && pwd)" || exit 0
. "$YT_HOME/bin/_paths.sh" 2>/dev/null || exit 0

# --codex (codex/hooks.json): stesse righe con la sintassi delle skill di Codex ($youtube:…) e, se il toolkit è
# installato ma mancano i comandi yt-* per Codex (<data>/shims, codex-shims.sh), una riga che lo dice.
P="/youtube:"; CODEX=""
if [ "${1:-}" = "--codex" ]; then P='$youtube:'; CODEX=1; fi

OUT=""
say() {  # aggiunge una riga al messaggio (stampato una volta sola in fondo, come JSON)
  OUT="${OUT:+$OUT
}$1"
}

json_str() {  # stringa JSON: barre, virgolette e caratteri di controllo comuni
  local s="$1"
  s="${s//\\/\\\\}"; s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"; s="${s//$'\r'/\\r}"; s="${s//$'\t'/\\t}"
  printf '"%s"' "$s"
}

plural() {  # n singolare plurale
  if [ "$1" = "1" ]; then printf '1 %s' "$2"; else printf '%s %s' "$1" "$3"; fi
}

learning_hint() {
  local db row pulls reviews props chans refs line1 line2 sq
  sq="$(command -v sqlite3 2>/dev/null)"
  [ -n "$sq" ] || return 0
  db="$(yt_studio_dir)/data/yt.db"
  [ -f "$db" ] || return 0
  # quali viste ci sono: learn_due_v (yt-learn, migrazione 2 di ytdb.py) e thumb_learn_due (yt-thumb-learn)
  local have q pull_src="" rev_src="" refs_src="" props_q="0"
  have="$("$sq" -readonly -batch -noheader -cmd '.timeout 300' "$db" \
          "SELECT group_concat(name, ' ') FROM sqlite_master WHERE name IN ('learn_due_v','thumb_learn_due','learn_proposals');" \
          2>/dev/null)" \
    || have="$("$sq" -batch -noheader -cmd '.timeout 300' "$db" \
          "SELECT group_concat(name, ' ') FROM sqlite_master WHERE name IN ('learn_due_v','thumb_learn_due','learn_proposals');" \
          2>/dev/null)" || return 0
  case " $have " in *" learn_due_v "*)
    pull_src="SELECT channel, video_id, checkpoint FROM learn_due_v WHERE task='pull'"
    rev_src="SELECT channel, video_id, checkpoint FROM learn_due_v WHERE task='review'"
    refs_src="SELECT channel FROM learn_events WHERE kind='refs_refresh' AND retracted_at IS NULL GROUP BY channel HAVING julianday(MAX(created_at)) < julianday('now', '-30 days')" ;;
  esac
  case " $have " in *" thumb_learn_due "*)
    pull_src="${pull_src:+$pull_src UNION }SELECT channel, video_id, checkpoint FROM thumb_learn_due WHERE task='outcome'"
    rev_src="${rev_src:+$rev_src UNION }SELECT channel, video_id, checkpoint FROM thumb_learn_due WHERE task='postmortem'"
    refs_src="${refs_src:+$refs_src UNION }SELECT channel FROM thumb_learn_due WHERE task='refs'" ;;
  esac
  case " $have " in *" learn_proposals "*) props_q="(SELECT COUNT(*) FROM learn_proposals WHERE state='in_attesa')" ;; esac
  [ -n "$pull_src" ] || [ "$props_q" != "0" ] || return 0
  if [ -n "$CODEX" ]; then PR_WHO="la PR la lanci tu dal Terminale, con yt-learn propose-pr"
  else PR_WHO="la PR la apre la sessione principale, con l'OK dell'operatore"; fi
  [ -n "$pull_src" ] || { pull_src="SELECT NULL, NULL, NULL WHERE 0"; rev_src="$pull_src"; refs_src="SELECT NULL WHERE 0"; }
  q="SELECT (SELECT COUNT(*) FROM (SELECT DISTINCT video_id, checkpoint FROM ($pull_src))),
            (SELECT COUNT(*) FROM (SELECT DISTINCT video_id, checkpoint FROM ($rev_src))),
            $props_q,
            (SELECT COALESCE(group_concat(ch, ', '), '') FROM (SELECT DISTINCT channel AS ch FROM ($pull_src UNION $rev_src)
                                                               WHERE channel IS NOT NULL ORDER BY ch)),
            (SELECT COUNT(DISTINCT channel) FROM ($refs_src));"
  # solo SELECT. -readonly fallisce su un database in WAL senza i file -shm/-wal (nessuna connessione aperta):
  # allora si riapre in modo normale, sempre e solo in lettura; busy timeout 300 ms, mai un'attesa lunga.
  row="$("$sq" -readonly -batch -noheader -separator '|' -cmd '.timeout 300' "$db" "$q" 2>/dev/null)" \
    || row="$("$sq" -batch -noheader -separator '|' -cmd '.timeout 300' "$db" "$q" 2>/dev/null)" || return 0
  IFS='|' read -r pulls reviews props chans refs <<EOF
$row
EOF
  case "$pulls$reviews$props$refs" in *[!0-9]*|"") return 0 ;; esac
  line1=""; line2=""
  if [ "$pulls" -gt 0 ] || [ "$reviews" -gt 0 ]; then
    line1="YouTube Producer · apprendimento:"
    [ "$pulls" -gt 0 ] && line1="$line1 $(plural "$pulls" "esito da leggere" "esiti da leggere")"
    [ "$pulls" -gt 0 ] && [ "$reviews" -gt 0 ] && line1="$line1 e"
    [ "$reviews" -gt 0 ] && line1="$line1 $(plural "$reviews" "post-mortem da fare" "post-mortem da fare")"
    [ -n "$chans" ] && line1="$line1 ($chans)"
    line1="$line1 → ${P}review."
  fi
  if [ "$props" -gt 0 ] || [ "$refs" -gt 0 ]; then
    line2="YouTube Producer · apprendimento:"
    [ "$props" -gt 0 ] && line2="$line2 $(plural "$props" "proposta di miglioramento in attesa" "proposte di miglioramento in attesa") ($PR_WHO)"
    [ "$props" -gt 0 ] && [ "$refs" -gt 0 ] && line2="$line2;"
    [ "$refs" -gt 0 ] && line2="$line2 riferimenti di nicchia da rinfrescare"
    line2="$line2 → ${P}learn."
  fi
  # al massimo due righe in tutto: se c'è già la riga del setup, l'apprendimento ne usa una sola
  if [ -n "${SETUP_LINE:-}" ] && [ -n "$line1" ] && [ -n "$line2" ]; then
    say "$line1 Inoltre: ${line2#YouTube Producer · apprendimento: }"
  else
    [ -n "$line1" ] && say "$line1"
    [ -n "$line2" ] && say "$line2"
  fi
  return 0
}

data="$(yt_data_dir 2>/dev/null)"
if [ -n "$data" ]; then                      # vuoto = checkout di sviluppo con layout storico: niente da suggerire
  marker="$data/.setup-ok"
  if [ ! -f "$marker" ]; then
    say "YouTube Producer (plugin youtube): il toolkit locale non è ancora installato su questo Mac. Esegui ${P}setup prima di usare ${P}producer o i comandi yt-*."
    SKIP_LEARNING=1
  elif [ "$YT_HOME/install.sh" -nt "$marker" ]; then
    want="$(yt_fingerprint 2>/dev/null)"
    have="$(sed -n 's/^fingerprint=//p' "$marker" 2>/dev/null)"
    if [ -n "$want" ] && [ "$want" != "$have" ]; then
      say "YouTube Producer (plugin youtube): il plugin è stato aggiornato e le dipendenze del toolkit sono cambiate. Esegui ${P}setup per riallinearle."
      SETUP_LINE=1
    fi
  fi
  if [ -n "$CODEX" ] && [ -f "$marker" ] && [ -z "${SETUP_LINE:-}" ] && [ ! -f "$data/shims/.yt-shim" ]; then
    say "YouTube Producer (plugin youtube): il toolkit è installato ma in Codex mancano ancora i comandi yt-*. Esegui ${P}setup per collegarli."
    SETUP_LINE=1
  fi
fi
[ -n "${SKIP_LEARNING:-}" ] || learning_hint
if [ -n "$OUT" ]; then
  msg="$(json_str "$OUT")"
  printf '{"systemMessage": %s, "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": %s}}\n' "$msg" "$msg"
fi
exit 0
