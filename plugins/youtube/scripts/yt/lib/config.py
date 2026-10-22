"""yt-config — configurazione e layout del plugin YouTube Producer (solo stdlib).

Uso:
  yt-config                         # JSON con percorsi, vault, canali, operatore, stato del setup
  yt-config --channel SLUG          # come sopra, con le consegne (deliverables_mode, deliverables_dir) di quel canale
  yt-config --get studio_dir        # un solo valore, testo semplice (per la shell)
  yt-config --init --operator NOME [--vault PATH] [--studio DIR] [--channels-dir DIR …] [--brands-dir DIR …]
                   [--repo DIR] [--force]
                                    # crea ~/.config/youtube-producer/config.yaml (mai sovrascritto senza --force)

Configurazione (facoltativa): ~/.config/youtube-producer/config.yaml (o il file in YT_CONFIG)
  operator: "Nome"                  # chi lavora (compare nei log e nei riepiloghi)
  vault_path: "~/…/Il mio vault"    # vault Obsidian facoltativo; assente o null = consegne nella cartella di lavoro
  channels_dirs:                    # profili canale (<slug>.md), cercati PRIMA di docs/yt/channels del plugin
    - ~/.config/youtube-producer/channels   # (default se la chiave manca)
  brands_dirs:                      # brand dell'operatore, cercati PRIMA di assets/brands del plugin
    - ~/.config/youtube-producer/brands     # (default se la chiave manca)
  studio_dir: ~/youtube-studio      # cartelle di lavoro, cache, database, segreti
  repo_path: ~/youtube-producer     # clone della repo del plugin: lì `yt-learn propose-pr` apre le PR di miglioramento
  learning_pr_channels: []          # canali le cui lezioni possono diventare PR (default nessuno, vedi shareable)
  learning_min_evidence: 3          # apprendimento (yt-learn), vedi LEARNING_DEFAULTS: «learning_<nome>», «learn.<nome>»
                                    # o un blocco «learning:» con le chiavi rientrate (anche senza PyYAML)
Variabili d'ambiente (vincono sul file): YT_DATA, YT_STUDIO, YT_VAULT (vuota = nessun vault),
YT_CHANNELS_DIRS e YT_BRANDS_DIRS (percorsi separati da «:»), YT_OPERATOR, YT_CONFIG, YT_REPO_PATH.

Canali: nessun profilo è incluso nel plugin (docs/yt/channels contiene solo _template.md). Se nei channels_dirs c'è
un solo profilo, quello è il canale predefinito (`default_channel`); con più profili il canale va indicato.

Consegne (note, report, pacchetti): `workdir` per default, in <studio_dir>/work/<slug>/deliver/notes/ (o nel
deliver/notes/ della cartella dell'episodio). `vault` solo se l'operatore imposta vault_path (cartella esistente)
E il profilo del canale indica la sua cartella nel vault:
  vault:
    deliverables: "YouTube/Il mio canale/"   # relativa al vault; l'agente scrive solo lì (guard.sh)

Brand: <brands_dir>/<slug>/ con tokens.json (obbligatorio) e, facoltativi, logo/, fonts/ (TTF/OTF + licenze),
templates/<slug>-*.html (template thumbnail per yt-thumb-render), ass/<preset>.json (preset ASS di yt-captions e
yt-clips), remotion.json (stile delle composizioni di yt-remotion), layout.json (geometria del master).
Il plugin include solo il brand neutro «demo» (assets/brands/demo); un brand dell'operatore con lo stesso slug vince.

Data dir del plugin (venv Python, node_modules di Playwright e Remotion, thumbvision compilato, marcatore
del setup), in ordine: YT_DATA → CLAUDE_PLUGIN_DATA (solo se è la cartella di questo plugin, «youtube-…», e non
«youtube-inline» di --plugin-dir) →
ricavata dal percorso della cache dei plugin (~/.claude/plugins/cache/<marketplace>/<plugin>/<versione>/ →
~/.claude/plugins/data/<plugin>-<marketplace>/) → checkout di sviluppo con <scripts/yt>/.venv (layout storico:
tutto dentro scripts/yt) → ~/.claude/plugins/data/youtube-youtube-producer.
In Codex vale la stessa regola della cache: ~/.codex/plugins/cache/youtube-producer/youtube/<versione>/ →
~/.codex/plugins/data/youtube-youtube-producer/ (dove stanno anche gli shim dei comandi yt-*, in shims/). Lanciato da
Codex (CODEX_SESSION_ID nell'ambiente), yt-config aggiunge `codex_guard` (l'hook guard.sh --codex ha segnato questo
thread?) e `codex_shims_dir`.

Questo modulo non dipende da PyYAML (ripiego su un parser minimo) perché lo usano anche guard.sh
(python3 di sistema, -I) e `yt-config` prima che il venv esista.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

HOME = Path.home()
YT_HOME = Path(__file__).resolve().parent.parent            # …/scripts/yt
DEFAULT_DATA_ID = "youtube-youtube-producer"          # <plugin>-<marketplace> di youtube@youtube-producer
DATA_ID_PREFIX = "youtube-"
CONFIG_FILE = HOME / ".config" / "youtube-producer" / "config.yaml"
KEYS = ("operator", "vault_path", "channels_dirs", "brands_dirs", "studio_dir", "repo_path")
DEFAULT_CHANNELS_DIRS = ("~/.config/youtube-producer/channels",)
DEFAULT_BRANDS_DIRS = ("~/.config/youtube-producer/brands",)
DEFAULT_STUDIO = "~/youtube-studio"
DEFAULT_REPO_PATH = "~/youtube-producer"
BUILTIN_BRAND = "demo"                 # unico brand incluso nel plugin (assets/brands/demo), neutro
DEFAULT_ASS_PRESET = "default"         # unico preset ASS incluso nel plugin (assets/ass/default.json)
# Apprendimento (lib/learn.py, `yt-learn`, docs/yt/knowledge/13-learning-loop.md). Nel config.yaml valgono tre forme,
# in quest'ordine di precedenza: «learning.<nome>» / «learn.<nome>» (chiave con il punto), il blocco «learning:» (o
# «learn:») con le chiavi rientrate, «learning_<nome>» (piatta). Il parser minimo (guard.sh, python3 di sistema
# senza PyYAML) le legge tutte. Un valore non valido torna al default senza errori: la configurazione
# dell'apprendimento non deve mai bloccare guard.sh.
LEARNING_DEFAULTS: dict[str, Any] = {
    "min_evidence": 3,           # lavori coerenti (video diversi) prima che una lezione sia «pronta per proposta»
    "decisive_weight": 3,        # quanti lavori vale un esito decisivo (A/B con vincitore, pre-test superato)
    "auto_pr": False,            # true: il dispatcher apre la PR di apprendimento senza chiedere (mai merge)
    "prior_strength": 4.0,       # pseudo-osservazioni del prior del knowledge (13 §3.2): un lavoro non ribalta una media
    "default_bonus": 0.1,        # media del prior del valore di default (profilo/knowledge): 0,5 + bonus
    "pref_weight": 0.5,          # peso di una preferenza dell'operatore (scelta al gate, correzione)
    "elo_k": 16.0,               # K dell'Elo per le preferenze a coppie (tetto 16 su scala 400, 13 §3.2)
    "ab_weight": 1.0,            # peso di un A/B nativo (vincitore > perdenti; pari e inconcludente = pari)
    "outcome_weight_d7": 0.25,   # peso di un verdetto D+7 sulle feature comuni alle braccia pubblicate
    "outcome_weight_d28": 0.5,   # peso di un verdetto D+28 (T+48h non aggiorna mai: è un polso, non un verdetto)
    "explore_arms": 1,           # opzioni di esplorazione (Thompson) in ogni proposta di concept (13 §3.4)
    "min_baseline": 3,           # video confrontabili a pari età sotto i quali l'esito è «non leggibile»
    "above_ratio": 1.25,         # rapporto con la mediana a pari età sopra il quale l'esito è «sopra»
    "below_ratio": 0.8,          # … e sotto il quale è «sotto» (in mezzo: nel rumore, conta metà)
    "pr_channels": [],           # canali le cui lezioni possono diventare PR sulla repo: vuoto = nessuno (Tier B
                                 # opt-in; servono anche kind: own e share_lessons: true nel profilo, vedi ytcore)
}
SETUP_MARKER_NAME = ".setup-ok"
LOCK_STAMP = ".yt-lock-sha256"
# File che, se cambiano, richiedono di rilanciare il setup (stessa lista di install.sh e session-hint.sh).
FINGERPRINT_FILES = ("install.sh", "pyproject.toml", "uv.lock", "node/package-lock.json",
                     "remotion/package-lock.json", "swift/thumbvision.swift")


class ConfigError(Exception):
    pass


# ── Percorsi del plugin ─────────────────────────────────────────────────────
def plugin_root() -> Path | None:
    """Radice del plugin (contiene .claude-plugin/plugin.json); None nel layout storico ~/.claude/scripts/yt."""
    root = YT_HOME.parent.parent
    return root if (root / ".claude-plugin" / "plugin.json").is_file() else None


def docs_dir() -> Path:
    root = plugin_root()
    return root / "docs" / "yt" if root else HOME / ".claude" / "docs" / "yt"


def brands_builtin() -> Path:
    """Brand inclusi nel plugin (solo demo): …/scripts/yt/assets/brands."""
    return YT_HOME / "assets" / "brands"


def _sanitize_id(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "-", text)


def _claude_config_dir() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else HOME / ".claude"


def cache_identity() -> dict | None:
    """Se il toolkit gira dalla cache dei plugin: {base, marketplace, plugin, version}."""
    parts = YT_HOME.parts
    for i in range(len(parts) - 5):
        if parts[i] == "plugins" and parts[i + 1] == "cache" and parts[-2:] == ("scripts", "yt") \
                and len(parts) == i + 7:
            return {"base": Path(*parts[: i + 1]), "marketplace": parts[i + 2], "plugin": parts[i + 3],
                    "version": parts[i + 4]}
    return None


def resolve_data_dir() -> tuple[Path | None, str]:
    """(data dir, origine). None = checkout di sviluppo con layout storico (venv in scripts/yt/.venv)."""
    env = os.environ.get("YT_DATA")
    if env:
        return Path(env).expanduser(), "YT_DATA"
    cpd = os.environ.get("CLAUDE_PLUGIN_DATA")
    # solo la data dir di questo plugin; non «youtube-inline» (--plugin-dir), che i comandi del tool Bash non vedono
    name = Path(cpd.rstrip("/")).name if cpd else ""
    if cpd and name.startswith(DATA_ID_PREFIX) and name != DATA_ID_PREFIX + "inline":
        return Path(cpd).expanduser(), "CLAUDE_PLUGIN_DATA"
    ident = cache_identity()
    if ident:
        return ident["base"] / "data" / _sanitize_id(f"{ident['plugin']}@{ident['marketplace']}"), "cache dei plugin"
    if (YT_HOME / ".venv" / "bin" / "python").exists():
        return None, "checkout di sviluppo (scripts/yt/.venv)"
    return _claude_config_dir() / "plugins" / "data" / DEFAULT_DATA_ID, "predefinita"


# ── Codex (versione del plugin per OpenAI Codex: .codex-plugin/, codex/) ──────
# Codex copia il plugin in <CODEX_HOME>/plugins/cache/<marketplace>/<plugin>/<versione>/ (senza symlink) e gli dà la
# data dir <CODEX_HOME>/plugins/data/<plugin>-<marketplace>: è la stessa regola della cache di Claude Code, quindi
# resolve_data_dir() non cambia. I comandi yt-* di Codex sono shim in <data>/shims (scripts/yt/bin/codex-shims.sh).
# Il guard di Codex (guard.sh --codex) segna con un file per sessione i thread in cui è partito il lavoro di YouTube
# Producer: stessa cartella di _paths.sh yt_codex_guard_dir (se cambi qui, cambia anche lì).
CODEX_GUARD_DEFAULT = HOME / "Library" / "Application Support" / "youtube-producer" / "codex-guard"
CODEX_SESSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{7,79}")
# Ogni chiamata dell'hook (PreToolUse, UserPromptSubmit) rinfresca il marcatore; quella di yt-config arriva un attimo
# prima di yt-config (o prima dell'approvazione, se Codex la chiede: da qui il margine di 10 minuti). Un marcatore più
# vecchio vuol dire che l'hook non sta girando più (thread ripreso dopo un aggiornamento con gli hook da riapprovare,
# hook spenti, solo hook gestiti): il thread non risulta controllato.
CODEX_GUARD_FRESH_S = 600
CODEX_HOOKS_FIX = ("approva gli hook del plugin (CLI: /hooks; app: pagina del plugin → Hook → «Autorizza tutti», in "
                   "inglese «Trust all») e apri una conversazione nuova; se l'organizzazione permette solo gli hook "
                   "gestiti dall'amministratore, vedi CODEX.md («Il guard in Codex»)")


def codex_home() -> Path:
    env = os.environ.get("CODEX_HOME")
    return Path(env).expanduser() if env else HOME / ".codex"


def codex_install() -> bool:
    """True se il toolkit gira dalla cache dei plugin di Codex (<CODEX_HOME>/plugins/cache/…)."""
    ident = cache_identity()
    if not ident:
        return False
    parent = ident["base"].parent
    try:
        return parent == codex_home().resolve() or parent.name == ".codex"
    except OSError:
        return parent.name == ".codex"


def codex_guard_dir() -> Path:
    env = os.environ.get("YT_CODEX_GUARD_DIR")
    return Path(env).expanduser() if env else CODEX_GUARD_DEFAULT


def codex_shims_dir() -> Path | None:
    data, _ = resolve_data_dir()
    return data / "shims" if data else None


def codex_guard_status(session: str | None = None) -> dict:
    """Il guard di Codex ha segnato questa sessione, e di recente? (CODEX_SESSION_ID dell'ambiente dei comandi di
    Codex). L'hook PreToolUse gira prima del comando e rinfresca il marcatore: se è approvato e funziona, un comando del
    toolkit (yt-config, yt-doctor…) trova un marcatore di pochi secondi prima. Un marcatore vecchio (oltre
    CODEX_GUARD_FRESH_S secondi) vuol dire che l'hook non gira più: «active» false, «reason» "stale"."""
    sid = session if session is not None else os.environ.get("CODEX_SESSION_ID", "")
    gdir = codex_guard_dir()
    valid = bool(sid) and CODEX_SESSION_RE.fullmatch(sid) is not None
    marker = gdir / sid if valid else None
    try:
        age = time.time() - marker.stat().st_mtime if marker is not None and marker.is_file() else None
    except OSError:
        age = None
    active = age is not None and age <= CODEX_GUARD_FRESH_S
    out: dict[str, Any] = {"active": active, "session": sid or None, "dir": str(gdir)}
    if not active:
        out["reason"] = ("invalid_session" if not valid else "no_marker" if age is None else "stale")
        if not valid:
            out["fix"] = "CODEX_SESSION_ID assente o non valido: lancia il comando da Codex"
        elif age is None:
            out["fix"] = CODEX_HOOKS_FIX
        else:
            out["fix"] = (f"l'hook ha visto questa conversazione l'ultima volta {int(age)} s fa, non adesso: non sta "
                          f"girando più. {CODEX_HOOKS_FIX[0].upper()}{CODEX_HOOKS_FIX[1:]}")
    return out


def layout() -> dict:
    """Dove stanno venv, node_modules, progetto Remotion eseguibile, thumbvision compilato, marcatore."""
    data, source = resolve_data_dir()
    if data is None:
        return {"mode": "dev", "data_dir": YT_HOME, "data_source": source, "venv": YT_HOME / ".venv",
                "node_prefix": YT_HOME / "node", "remotion_dir": YT_HOME / "remotion",
                "thumbvision_build": YT_HOME / "bin" / "thumbvision", "marker": None}
    return {"mode": "data", "data_dir": data, "data_source": source, "venv": data / "venv",
            "node_prefix": data / "node", "remotion_dir": data / "remotion",
            "thumbvision_build": data / "bin" / "thumbvision", "marker": data / SETUP_MARKER_NAME}


def setup_fingerprint() -> str:
    """sha256 dei file che determinano il setup (come `shasum -a 256 … | shasum -a 256` in session-hint.sh)."""
    lines = []
    for rel in FINGERPRINT_FILES:
        p = YT_HOME / rel
        digest = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "-"
        lines.append(f"{digest}  {rel}\n")
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def read_marker(marker: Path | None) -> dict:
    """Contenuto di <data>/.setup-ok (righe chiave=valore)."""
    out: dict[str, str] = {}
    if marker and marker.is_file():
        for line in marker.read_text(errors="replace").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def plugin_version() -> str | None:
    """SHA del commit: dalla cartella della cache (versione = commit) o da .git nel checkout."""
    ident = cache_identity()
    if ident:
        return ident["version"]
    root = plugin_root()
    if root is None:
        return None
    for git in (root.parent.parent / ".git", root / ".git"):
        head = git / "HEAD"
        try:
            ref = head.read_text().strip()
        except OSError:
            continue
        if ref.startswith("ref: "):
            refp = git / ref[5:]
            try:
                return refp.read_text().strip()
            except OSError:
                packed = git / "packed-refs"
                if packed.exists():
                    for line in packed.read_text().splitlines():
                        if line.endswith(" " + ref[5:]):
                            return line.split()[0]
                return None
        return ref or None
    return None


# ── Lettura del file di configurazione ──────────────────────────────────────
def _scalar(text: str) -> Any:
    t = text.strip()
    if not t or t in ("~", "null", "Null", "NULL"):
        return None
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
        if t[0] == "'":
            return t[1:-1].replace("''", "'")
        try:
            return json.loads(t)          # "…" con escape in stile JSON (come li scrive yt-config --init)
        except ValueError:
            return t[1:-1]
    if t.lower() in ("true", "yes", "on"):
        return True
    if t.lower() in ("false", "no", "off"):
        return False
    return t


def _strip_comment(line: str) -> str:
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def parse_mini_yaml(text: str) -> dict:
    """Sottoinsieme di YAML sufficiente per config.yaml: chiave: valore (anche «learn.min_evidence»), liste «- x»
    o [a, b], un livello di mappa rientrata sotto una chiave vuota («learning:» + «  min_evidence: 3»), commenti."""
    data: dict[str, Any] = {}
    current: str | None = None
    for n, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw)
        if not line.strip() or line.strip() in ("---", "..."):
            continue
        if line[0] in " \t" or line.lstrip().startswith("- "):
            item = line.strip()
            sub = re.match(r"^([A-Za-z_][\w.-]*)\s*:\s*(.*)$", item)
            if current is not None and sub and not item.startswith("-") and \
                    (data.get(current) is None or isinstance(data.get(current), dict)):
                if not isinstance(data.get(current), dict):
                    data[current] = {}
                val = sub.group(2).strip()
                if val.startswith("[") and val.endswith("]"):
                    inner = val[1:-1].strip()
                    data[current][sub.group(1)] = [_scalar(x) for x in inner.split(",")] if inner else []
                else:
                    data[current][sub.group(1)] = _scalar(val)
                continue
            if current is None or not item.startswith("-"):
                raise ConfigError(f"riga {n} non riconosciuta: {raw.strip()!r}")
            if not isinstance(data.get(current), list):
                data[current] = []
            data[current].append(_scalar(item[1:]))
            continue
        m = re.match(r"^([A-Za-z_][\w.-]*)\s*:\s*(.*)$", line)
        if not m:
            raise ConfigError(f"riga {n} non riconosciuta: {raw.strip()!r}")
        key, val = m.group(1), m.group(2).strip()
        current = key
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            data[key] = [_scalar(x) for x in inner.split(",")] if inner else []
        else:
            data[key] = _scalar(val)
    return data


def config_path() -> Path:
    env = os.environ.get("YT_CONFIG")
    return Path(env).expanduser() if env else CONFIG_FILE


def load_config(path: Path | None = None) -> dict:
    """Dizionario del config.yaml ({} se assente). ConfigError se illeggibile."""
    p = path or config_path()
    if not p.is_file():
        return {}
    try:
        text = p.read_text()
    except OSError as exc:
        raise ConfigError(f"{p}: illeggibile ({exc})") from exc
    try:
        import yaml  # type: ignore
    except ImportError:
        data = parse_mini_yaml(text)
    else:
        try:
            data = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"{p}: YAML non valido ({exc})") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{p}: atteso un dizionario chiave: valore")
    return data


def _path(value: Any) -> Path | None:
    if value in (None, "", False):
        return None
    return Path(os.path.expandvars(str(value))).expanduser()


def learning_settings(cfg: dict | None = None) -> dict:
    """Parametri dell'apprendimento: LEARNING_DEFAULTS sovrascritti dal config.yaml («learning.<nome>»,
    «learn.<nome>», blocco «learning:»/«learn:», «learning_<nome>»). Mai un'eccezione: un valore illeggibile
    resta al default (guard.sh legge la stessa configurazione)."""
    cfg = cfg or {}
    out: dict[str, Any] = {}
    blocks = [b for b in (cfg.get("learning"), cfg.get("learn")) if isinstance(b, dict)]
    for key, default in LEARNING_DEFAULTS.items():
        raw = None
        for cand in (cfg.get(f"learning.{key}"), cfg.get(f"learn.{key}"), *(b.get(key) for b in blocks),
                     cfg.get(f"learning_{key}")):
            if cand is not None and cand != "":
                raw = cand
                break
        if raw is None:
            out[key] = list(default) if isinstance(default, list) else default
            continue
        try:
            if isinstance(default, list):
                vals = raw if isinstance(raw, list) else str(raw).replace(",", " ").split()
                out[key] = [str(v).strip() for v in vals if str(v).strip()]
            elif isinstance(default, bool):
                out[key] = raw if isinstance(raw, bool) else str(raw).lower() in ("1", "true", "yes", "on")
            elif isinstance(default, int):
                out[key] = max(0, int(float(raw)))
            else:
                out[key] = float(raw)
        except (TypeError, ValueError):
            out[key] = list(default) if isinstance(default, list) else default
        if key in LEARNING_BOUNDS and isinstance(out[key], (int, float)) and not isinstance(out[key], bool):
            lo, hi = LEARNING_BOUNDS[key]
            out[key] = type(default)(min(max(out[key], lo), hi))
    return out


# Limiti delle chiavi numeriche (13 §3, «small-sample guard»): la configurazione può regolare il ciclo, non spegnerne
# le protezioni. Un valore fuori limite torna nel limite, senza errori: niente proposte da una sola prova
# (min_evidence ≥ 2), niente prior che un solo video ribalta (prior_strength ≥ 2, pesi ≤ 1, Elo K ≤ 16), sempre
# almeno un'opzione di esplorazione (explore_arms ≥ 1), mai un verdetto su meno di 3 video (min_baseline ≥ 3).
LEARNING_BOUNDS: dict[str, tuple[float, float]] = {
    "min_evidence": (2, 20), "decisive_weight": (1, 10), "prior_strength": (2.0, 50.0), "default_bonus": (0.0, 0.2),
    "pref_weight": (0.05, 1.0), "elo_k": (1.0, 16.0), "ab_weight": (0.0, 2.0), "outcome_weight_d7": (0.0, 1.0),
    "outcome_weight_d28": (0.0, 1.0), "explore_arms": (1, 3), "min_baseline": (3, 50), "above_ratio": (1.05, 5.0),
    "below_ratio": (0.2, 0.95),
}


def settings(cfg: dict | None = None) -> dict:
    """Valori effettivi (ambiente > config.yaml > predefiniti)."""
    cfg = load_config() if cfg is None else cfg
    studio = _path(os.environ.get("YT_STUDIO")) or _path(cfg.get("studio_dir")) or _path(DEFAULT_STUDIO)
    if "YT_VAULT" in os.environ:
        vault = _path(os.environ["YT_VAULT"])
    else:
        vault = _path(cfg.get("vault_path"))
    env_dirs = os.environ.get("YT_CHANNELS_DIRS")
    if env_dirs is not None:
        extra = [d for d in env_dirs.split(os.pathsep) if d.strip()]
    else:
        raw = cfg.get("channels_dirs")
        extra = list(DEFAULT_CHANNELS_DIRS) if raw is None else ([raw] if isinstance(raw, str) else list(raw))
    dirs: list[Path] = []
    for d in extra:
        p = _path(d)
        if p and p not in dirs:
            dirs.append(p)
    builtin = docs_dir() / "channels"
    if builtin not in dirs:
        dirs.append(builtin)
    env_brands = os.environ.get("YT_BRANDS_DIRS")
    if env_brands is not None:
        braw = [d for d in env_brands.split(os.pathsep) if d.strip()]
    else:
        raw_b = cfg.get("brands_dirs")
        braw = list(DEFAULT_BRANDS_DIRS) if raw_b is None else ([raw_b] if isinstance(raw_b, str) else list(raw_b))
    bdirs: list[Path] = []
    for d in braw:
        p = _path(d)
        if p and p not in bdirs:
            bdirs.append(p)
    bbuiltin = brands_builtin()
    if bbuiltin not in bdirs:
        bdirs.append(bbuiltin)
    operator = os.environ.get("YT_OPERATOR") or cfg.get("operator") or None
    repo = _path(os.environ.get("YT_REPO_PATH")) or _path(cfg.get("repo_path")) or _path(DEFAULT_REPO_PATH)
    return {"operator": str(operator) if operator else None, "studio_dir": studio, "vault_path": vault,
            "channels_dirs": dirs, "channels_dirs_extra": dirs[:-1], "channels_builtin": builtin,
            "brands_dirs": bdirs, "brands_dirs_extra": bdirs[:-1], "brands_builtin": bbuiltin,
            "repo_path": repo, "learning": learning_settings(cfg)}


def brand_dir(slug: str, s: dict | None = None) -> Path | None:
    """Cartella del brand <slug>: la prima <brands_dir>/<slug>/ con tokens.json (cartelle esterne prima,
    poi assets/brands del plugin). None se il brand non esiste da nessuna parte."""
    if not slug or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", str(slug)):
        return None
    s = settings() if s is None else s
    for d in s["brands_dirs"]:
        p = d / str(slug)
        if (p / "tokens.json").is_file():
            return p
    return None


def list_brands(s: dict | None = None) -> dict[str, Path]:
    """{slug: cartella} di tutti i brand visibili (il primo trovato vince, come in brand_dir)."""
    s = settings() if s is None else s
    out: dict[str, Path] = {}
    for d in s["brands_dirs"]:
        try:
            children = sorted(d.iterdir())
        except OSError:
            continue
        for p in children:
            if p.is_dir() and (p / "tokens.json").is_file() and p.name not in out:
                out[p.name] = p
    return out


# ── Profili canale (lettura minima del frontmatter, senza PyYAML: la usa anche guard.sh) ──
PROFILE_SLUG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def _frontmatter_lines(path: Path) -> list[str]:
    """Righe del frontmatter YAML di <slug>.md (tra i due «---»); [] se manca o il file è illeggibile."""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return []
    if not text.startswith("---"):
        return []
    lines = text.splitlines()[1:]
    for i, line in enumerate(lines):
        if line.strip() == "---":
            return lines[:i]
    return []


def profile_meta(path: Path) -> dict:
    """Chiavi di primo livello del profilo (solo scalari) + «vault.deliverables». Mai un'eccezione: è la lettura
    che usano guard.sh (python3 di sistema) e yt-config; i comandi del toolkit leggono il profilo intero con
    ytcore.load_channel (PyYAML)."""
    meta: dict[str, Any] = {}
    block: str | None = None
    for raw in _frontmatter_lines(path):
        line = _strip_comment(raw)
        if not line.strip():
            continue
        if line[0] not in " \t":
            m = re.match(r"^([A-Za-z_][\w.-]*)\s*:\s*(.*)$", line)
            if not m:
                block = None
                continue
            key, val = m.group(1), m.group(2).strip()
            block = key if not val else None
            if val and not val.startswith(("[", "{", "|", ">")):
                meta[key] = _scalar(val)
            continue
        if block == "vault":
            m = re.match(r"^\s+deliverables\s*:\s*(.*)$", line)
            if m and m.group(1).strip():
                meta["vault.deliverables"] = _scalar(m.group(1))
    return meta


def list_channels(s: dict | None = None) -> dict[str, Path]:
    """{slug: profilo} dei profili canale nei channels_dirs (il primo trovato vince; «_template.md» e i file senza
    frontmatter non contano). Il plugin non include profili: un'installazione nuova non ne ha nessuno."""
    s = settings() if s is None else s
    out: dict[str, Path] = {}
    for d in s["channels_dirs"]:
        try:
            files = sorted(d.glob("*.md"))
        except OSError:
            continue
        for p in files:
            slug = p.stem
            if slug.startswith(("_", ".")) or slug in out or not PROFILE_SLUG_RE.fullmatch(slug):
                continue
            if p.is_file() and _frontmatter_lines(p):
                out[slug] = p
    return out


def default_channel(s: dict | None = None) -> str | None:
    """Lo slug dell'unico profilo nei channels_dirs; None se ce ne sono zero o più di uno (allora si chiede)."""
    chans = list_channels(s)
    return next(iter(chans)) if len(chans) == 1 else None


def find_profile(slug: str, s: dict | None = None) -> Path | None:
    """<slug>.md nel primo dei channels_dirs che lo contiene (come ytcore.channel_file)."""
    if not slug or not PROFILE_SLUG_RE.fullmatch(str(slug)) or ".." in str(slug):
        return None
    s = settings() if s is None else s
    for d in s["channels_dirs"]:
        p = d / f"{slug}.md"
        if p.is_file():
            return p
    return None


def _vault_folder(vault: Path, value: Any) -> Path | None:
    """Cartella deliverable dentro il vault (relativa al vault, o assoluta ma interna). None se vuota, se è la radice
    del vault, se esce dal vault o se tocca .obsidian/."""
    if value in (None, "", False) or not isinstance(value, str):
        return None
    raw = os.path.expandvars(value.strip())
    p = Path(raw).expanduser()
    p = Path(os.path.normpath(str(p if p.is_absolute() else vault / p)))
    root = Path(os.path.normpath(str(vault)))
    try:
        rel = p.relative_to(root)
    except ValueError:
        return None
    if not rel.parts or rel.parts[0] in (".", "..") or ".obsidian" in rel.parts:
        return None
    return p


def vault_status(vault: Path | None) -> tuple[str, str]:
    """('vault'|'workdir', motivo) per il vault in sé: 'vault' se è configurato ed esiste. Quale canale ci scrive
    davvero lo dice deliverables_target (serve anche vault.deliverables nel profilo)."""
    if vault is None:
        return "workdir", "vault non configurato: consegne in deliver/notes/ della cartella di lavoro"
    if not vault.is_dir():
        return "workdir", f"vault non trovato ({vault}): consegne in deliver/notes/ della cartella di lavoro"
    return "vault", f"vault {vault}: vale per i canali il cui profilo indica vault.deliverables"


def deliverables_target(slug: str, s: dict | None = None) -> dict:
    """Dove vanno le note del canale: {'mode': 'vault'|'workdir', 'dir', 'reason'}. 'vault' solo con vault_path
    configurato ed esistente E un profilo con vault.deliverables valido; altrimenti <studio>/work/<slug>/deliver/notes/
    (per il lavoro di un episodio: deliver/notes/ della sua cartella di lavoro)."""
    s = settings() if s is None else s
    workdir = Path(s["studio_dir"]) / "work" / str(slug) / "deliver" / "notes"
    out = {"mode": "workdir", "dir": str(workdir)}
    vault = s.get("vault_path")
    mode, why = vault_status(vault)
    if mode != "vault":
        return {**out, "reason": why}
    prof = find_profile(slug, s)
    if prof is None:
        return {**out, "reason": f"profilo {slug}.md non trovato nei channels_dirs"}
    value = profile_meta(prof).get("vault.deliverables")
    folder = _vault_folder(vault, value)
    if folder is None:
        reason = ("il profilo non indica vault.deliverables" if value in (None, "")
                  else f"vault.deliverables non valido ({value}): deve essere una cartella dentro il vault")
        return {**out, "reason": reason}
    return {"mode": "vault", "dir": str(folder), "reason": f"vault.deliverables del profilo {prof.name}"}


def vault_deliverable_dirs(s: dict | None = None) -> list[Path]:
    """Cartelle del vault in cui l'agente può scrivere (guard.sh, regola 7): le vault.deliverables valide di tutti
    i profili nei channels_dirs. [] senza vault (allora la regola 7 non si applica) o senza profili che le indicano
    (allora nel vault non si scrive)."""
    s = settings() if s is None else s
    vault = s.get("vault_path")
    if vault is None:
        return []
    out: list[Path] = []
    for prof in list_channels(s).values():
        folder = _vault_folder(vault, profile_meta(prof).get("vault.deliverables"))
        if folder is not None and folder not in out:
            out.append(folder)
    return out


# ── Riepilogo per yt-config ─────────────────────────────────────────────────
def describe(channel: str | None = None) -> dict:
    cfg_file = config_path()
    cfg = load_config(cfg_file)
    s = settings(cfg)
    lay = layout()
    chans = list_channels(s)
    default = next(iter(chans)) if len(chans) == 1 else None
    per_channel = {slug: deliverables_target(slug, s) for slug in chans}
    focus = channel or default
    if focus:
        target = per_channel.get(focus) or deliverables_target(focus, s)
        mode, why, ddir = target["mode"], f"canale {focus}: {target['reason']}", target["dir"]
    else:
        vmode, vwhy = vault_status(s["vault_path"])
        mode = "vault" if any(t["mode"] == "vault" for t in per_channel.values()) else "workdir"
        why = (f"{vwhy}; per il dettaglio di un canale: yt-config --channel <slug>" if vmode == "vault" else vwhy)
        ddir = None
    venv_py = lay["venv"] / "bin" / "python"
    tv_build = lay["thumbvision_build"]
    tv_pre = YT_HOME / "bin" / "thumbvision"
    marker = read_marker(lay["marker"])
    fp = setup_fingerprint()
    root = plugin_root()
    codex: dict[str, Any] = {}
    if os.environ.get("CODEX_SESSION_ID"):      # comando lanciato da Codex
        codex["codex_guard"] = codex_guard_status()
    if codex or codex_install():
        shims = codex_shims_dir()
        codex["codex_shims_dir"] = str(shims) if shims else None
    return {
        **codex,
        "plugin_root": str(root) if root else None,
        "data_dir": str(lay["data_dir"]),
        "venv_python": str(venv_py),
        "studio_dir": str(s["studio_dir"]),
        "vault_path": str(s["vault_path"]) if s["vault_path"] else None,
        "channels_dirs": [str(d) for d in s["channels_dirs"]],
        "brands_dirs": [str(d) for d in s["brands_dirs"]],
        "brands": {k: str(v) for k, v in list_brands(s).items()},
        "channels": {k: str(v) for k, v in chans.items()},
        "default_channel": default,
        "channel": focus,
        "deliverables_mode": mode,
        "deliverables_dir": ddir,
        "operator": s["operator"],
        "repo_path": str(s["repo_path"]) if s["repo_path"] else None,
        "learning": s["learning"],
        # dettagli
        "deliverables_reason": why,
        "deliverables": per_channel,
        "builtin_brand": BUILTIN_BRAND,
        "default_ass_preset": DEFAULT_ASS_PRESET,
        "channels_dirs_extra": [str(d) for d in s["channels_dirs_extra"]],
        "brands_dirs_extra": [str(d) for d in s["brands_dirs_extra"]],
        "brands_builtin": str(s["brands_builtin"]),
        "docs_dir": str(docs_dir()),
        "yt_home": str(YT_HOME),
        "bin_dir": str(root / "bin") if root else str(YT_HOME / "bin"),
        "config_file": str(cfg_file),
        "config_exists": cfg_file.is_file(),
        "data_source": lay["data_source"],
        "layout": lay["mode"],
        "venv_ready": venv_py.exists(),
        "node_modules": str(lay["node_prefix"] / "node_modules"),
        "remotion_dir": str(lay["remotion_dir"]),
        "thumbvision": str(tv_build if os.access(tv_build, os.X_OK) else tv_pre),
        "plugin_version": plugin_version(),
        "setup_ok": bool(marker) if lay["marker"] else venv_py.exists(),
        "setup_current": (marker.get("fingerprint") == fp) if marker else False,
        "setup": marker or None,
    }


YAML_TEMPLATE = """# YouTube Producer — configurazione locale (non versionata). Documentazione: yt-config --help
operator: {operator}
vault_path: {vault}
channels_dirs:
{channels}
brands_dirs:
{brands}
studio_dir: {studio}
repo_path: {repo}
"""


def _yq(value: str | None) -> str:
    if value is None:
        return "null"
    return json.dumps(value, ensure_ascii=False)


def init_config(args: argparse.Namespace) -> dict:
    p = config_path()
    if p.exists() and not args.force:
        raise ConfigError(f"{p} esiste già: lo lascio com'è (usa --force per riscriverlo)")
    if not args.operator:
        raise ConfigError("--init richiede --operator (il nome di chi lavora)")
    channels = args.channels_dir or [str(p.parent / "channels")]
    brands = getattr(args, "brands_dir", None) or [str(p.parent / "brands")]
    text = YAML_TEMPLATE.format(
        operator=_yq(args.operator), vault=_yq(args.vault),
        channels="\n".join(f"  - {_yq(c)}" for c in channels),
        brands="\n".join(f"  - {_yq(b)}" for b in brands),
        studio=_yq(args.studio or DEFAULT_STUDIO),
        repo=_yq(getattr(args, "repo", None) or DEFAULT_REPO_PATH))
    parse_mini_yaml(text)  # deve rileggersi anche senza PyYAML
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, p)
    for c in [*channels, *brands]:
        cp = _path(c)
        if cp:
            cp.mkdir(parents=True, exist_ok=True)
    return {"written": str(p)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="yt-config", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--get", metavar="CHIAVE", help="stampa solo questo valore (liste: una voce per riga)")
    ap.add_argument("--channel", metavar="SLUG",
                    help="canale di cui calcolare le consegne (deliverables_mode, deliverables_dir); "
                         "default: l'unico profilo nei channels_dirs, se ce n'è uno solo")
    ap.add_argument("--init", action="store_true", help="crea il config.yaml dell'operatore")
    ap.add_argument("--operator", help="con --init: nome di chi lavora")
    ap.add_argument("--vault", help="con --init: percorso del vault Obsidian (facoltativo)")
    ap.add_argument("--studio", help=f"con --init: cartella di lavoro (default {DEFAULT_STUDIO})")
    ap.add_argument("--channels-dir", action="append",
                    help="con --init: cartella dei profili canale (ripetibile; "
                         "default ~/.config/youtube-producer/channels)")
    ap.add_argument("--brands-dir", action="append",
                    help="con --init: cartella dei brand (ripetibile; default ~/.config/youtube-producer/brands)")
    ap.add_argument("--repo", help=f"con --init: clone della repo del plugin per le PR di miglioramento "
                                   f"(default {DEFAULT_REPO_PATH})")
    ap.add_argument("--force", action="store_true", help="con --init: riscrive un config.yaml esistente")
    args = ap.parse_args(argv)
    try:
        extra = init_config(args) if args.init else {}
        if args.channel and not PROFILE_SLUG_RE.fullmatch(args.channel):
            raise ConfigError(f"--channel {args.channel!r}: slug non valido (lettere, cifre, «_», «.», «-»)")
        info = describe(args.channel)
    except ConfigError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        print(f"yt-config: {exc}", file=sys.stderr)
        return 1
    if args.get:
        if args.get not in info:
            print(f"yt-config: chiave sconosciuta {args.get!r} (disponibili: {', '.join(info)})", file=sys.stderr)
            return 1
        val = info[args.get]
        if isinstance(val, list):
            print("\n".join(val))
        elif isinstance(val, dict):
            print(json.dumps(val, ensure_ascii=False))
        elif val is None:
            print("")
        else:
            print(str(val).lower() if isinstance(val, bool) else val)
        return 0
    print(json.dumps({"ok": True, **extra, **info}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
