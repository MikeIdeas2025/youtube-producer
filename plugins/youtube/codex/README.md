# codex/ — la versione Codex del plugin

Claude Code non legge niente di questa cartella. La legge Codex, tramite `.codex-plugin/plugin.json`.

- `skills/<nome>/SKILL.md` e `skills/<nome>/agents/openai.yaml` — **generati** da `scripts/codex/build_skills.py` a partire da `commands/*.md`. Sono involucri sottili: rimandano ai file di Claude Code (agente, dispatcher, skill), che restano l'unica fonte. Non modificarli a mano: cambia `commands/` o il generatore e rigenera con `python3 plugins/youtube/scripts/codex/build_skills.py`.
- `toolkit-commands.txt` — **generato** dallo stesso script: i nomi dei comandi di `bin/`, per gli shim e per il guard di Codex.
- `references/codex-host.md` — **scritto a mano**: come valgono in Codex le istruzioni scritte per Claude Code (strumenti, gate, guard, sandbox, setup).
- `hooks.json` — **scritto a mano**, con i comandi congelati: se cambiano (evento, matcher, comando, timeout o messaggio), Codex chiede a ogni utente di riapprovare gli hook. Il matcher di PreToolUse, `^(Bash|apply_patch|mcp__.+)$`, porta al guard anche gli strumenti MCP.

Controllo: `python3 plugins/youtube/scripts/codex/build_skills.py --check`, `python3 plugins/youtube/scripts/yt/tests/test_codex_skills.py` e `python3 plugins/youtube/scripts/yt/tests/test_codex_runtime.py`.
