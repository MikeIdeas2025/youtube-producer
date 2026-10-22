"""ytcore — libreria comune del toolkit di YouTube Producer.

Ogni comando `bin/yt-<cmd>` esegue `lib/<cmd>.py` nel venv del toolkit e importa da qui:
percorsi, binari, cartella di lavoro dell'episodio (`project.json`), tempi, ffprobe,
profili canale. Niente dipendenze oltre la stdlib + PyYAML.

Convenzioni (vedi docs/yt/DESIGN.md del plugin, §Contratti):
- Cartella di lavoro: <studio_dir>/work/<channel>/<YYYY-MM-DD>-<slug>/ (studio_dir di default ~/youtube-studio)
- Tempi sempre in secondi float sul timeline indicato (source o output).
- Ogni comando stampa su stdout UN oggetto JSON di riepilogo (ok, outputs, warnings);
  i log umani vanno su stderr.
- Percorsi del plugin, data dir (venv, node_modules, thumbvision compilato) e configurazione
  dell'operatore (~/.config/youtube-producer/config.yaml): lib/config.py, riepilogo con `yt-config`.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

# ── Percorsi ────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as _config  # noqa: E402  (lib/config.py, solo stdlib)

try:
    _SETTINGS = _config.settings()
except _config.ConfigError as _exc:
    print(json.dumps({"ok": False, "error": f"configurazione non valida: {_exc}"}, ensure_ascii=False, indent=2))
    print(f"configurazione non valida: {_exc} (correggi il file o usa yt-config --init --force)", file=sys.stderr)
    sys.exit(2)

HOME = Path.home()
YT_HOME = _config.YT_HOME                       # …/scripts/yt (da __file__, mai da ambiente)
PLUGIN_ROOT = _config.plugin_root()             # radice del plugin; None nel layout storico ~/.claude/scripts/yt
LAYOUT = _config.layout()
PLUGIN_DATA = LAYOUT["data_dir"]                # data dir del plugin (≠ DATA, che è <studio>/data)
VENV_DIR = LAYOUT["venv"]
SETUP_MARKER = LAYOUT["marker"]                 # None nel checkout di sviluppo con scripts/yt/.venv
OPERATOR = _SETTINGS["operator"]
STUDIO = _SETTINGS["studio_dir"]
WORK = STUDIO / "work"
CACHE = STUDIO / "cache"
DATA = STUDIO / "data"
SECRETS = Path(os.environ["YT_SECRETS"]).expanduser() if os.environ.get("YT_SECRETS") else STUDIO / "secrets"
DB_PATH = DATA / "yt.db"
LEARNED = DATA / "learned"                      # apprendimento per canale (yt-learn): playbook, glossario e confusioni
REPO_PATH = _SETTINGS.get("repo_path")          # clone della repo del plugin per le PR di miglioramento (Tier B)
LEARNING = _SETTINGS.get("learning") or {}      # parametri dell'apprendimento (config.LEARNING_DEFAULTS)
VAULT = _SETTINGS["vault_path"]                 # Path | None
DOCS = _config.docs_dir()
CHANNELS_DIR = DOCS / "channels"                # nel plugin solo _template.md (nessun profilo incluso)
CHANNELS_DIRS = _SETTINGS["channels_dirs"]      # ordine di ricerca: cartelle extra, poi CHANNELS_DIR
ASSETS = YT_HOME / "assets"
FONTS = ASSETS / "fonts"
BRANDS = ASSETS / "brands"                      # brand inclusi nel plugin (solo demo)
BUILTIN_BRAND = _config.BUILTIN_BRAND           # "demo": brand neutro di ripiego
DEFAULT_ASS_PRESET = _config.DEFAULT_ASS_PRESET  # "default": preset ASS incluso nel plugin
BRANDS_DIRS = _SETTINGS["brands_dirs"]          # ordine di ricerca: brands_dirs esterni, poi BRANDS
REMOTION_SRC = YT_HOME / "remotion"             # sorgenti dei template Remotion (nel plugin)
REMOTION_DIR = LAYOUT["remotion_dir"]           # progetto eseguibile (copia sincronizzata + node_modules)
NODE_DIR = YT_HOME / "node"                     # render_html.mjs e template HTML (nel plugin)
NODE_PREFIX = LAYOUT["node_prefix"]             # package.json + node_modules di Playwright
NODE_MODULES = NODE_PREFIX / "node_modules"
SWIFT_SRC = YT_HOME / "swift" / "thumbvision.swift"
SWIFT_BIN_PREBUILT = YT_HOME / "bin" / "thumbvision"    # binario arm64 incluso nel repo (ripiego)
SWIFT_BIN_BUILD = LAYOUT["thumbvision_build"]           # compilato da install.sh per questo Mac
SWIFT_BIN = SWIFT_BIN_BUILD if os.access(SWIFT_BIN_BUILD, os.X_OK) else SWIFT_BIN_PREBUILT
# In Codex (comando lanciato da Codex o toolkit nella cache dei plugin di Codex) le skill si chiamano con $youtube:…
CODEX_HOST = bool(os.environ.get("CODEX_SESSION_ID")) or _config.codex_install()
SETUP_HINT = f"esegui {'$' if CODEX_HOST else '/'}youtube:setup (oppure yt-install --yes)"

# ── Binari ──────────────────────────────────────────────────────────────────
# ffmpeg-full (keg-only) ha libass/freetype/zscale: lo usiamo SEMPRE per percorso assoluto.
FFMPEG = os.environ.get("YT_FFMPEG", "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
FFPROBE = os.environ.get("YT_FFPROBE", "/opt/homebrew/opt/ffmpeg-full/bin/ffprobe")
WHISPER_CLI = os.environ.get("YT_WHISPER_CLI", "/opt/homebrew/bin/whisper-cli")
PARAKEET_CLI = os.environ.get("YT_PARAKEET_CLI", "/opt/homebrew/bin/parakeet-cli")
WHISPER_MODEL = Path(os.environ.get("YT_WHISPER_MODEL", HOME / ".whisper-models" / "ggml-large-v3-turbo.bin"))
VAD_MODEL = Path(os.environ.get("YT_VAD_MODEL", HOME / ".whisper-models" / "ggml-silero-v6.2.0.bin"))
SENKO_PY = Path(os.environ.get("YT_SENKO_PY", HOME / ".venvs" / "senko" / "bin" / "python"))
YTDLP = os.environ.get("YT_YTDLP", "/opt/homebrew/bin/yt-dlp")
AUTO_EDITOR = os.environ.get("YT_AUTO_EDITOR", "/opt/homebrew/bin/auto-editor")
_CHROME_REL = "Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME = os.environ.get("YT_CHROME") or next(
    (str(p) for p in (Path("/Applications") / _CHROME_REL, HOME / "Applications" / _CHROME_REL) if p.exists()),
    str(Path("/Applications") / _CHROME_REL))
NODE_MIN_MAJOR = 20                    # Playwright 1.64 e Remotion 4.0.534; consigliato 22

WORK_SUBDIRS = ("src", "analysis", "edit", "deliver", "thumbs", "shorts", "qa", "logs")


# ── Output e log ────────────────────────────────────────────────────────────
def log(*parts: Any) -> None:
    """Log umano su stderr (stdout è riservato al JSON di riepilogo)."""
    print(*parts, file=sys.stderr, flush=True)


def emit(ok: bool = True, **fields: Any) -> None:
    """Stampa il riepilogo JSON del comando su stdout."""
    print(json.dumps({"ok": ok, **fields}, ensure_ascii=False, indent=2, default=str))


def fail(message: str, code: int = 1, **fields: Any) -> None:
    emit(False, error=message, **fields)
    sys.exit(code)


# ── JSON ────────────────────────────────────────────────────────────────────
def read_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text())


def write_json(path: Path | str, data: Any) -> Path:
    """Scrittura atomica (tmp + rename) per non lasciare JSON a metà."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, path)
    return path


# ── Processi ────────────────────────────────────────────────────────────────
def run(cmd: Iterable[Any], *, check: bool = True, capture: bool = False,
        cwd: Path | str | None = None, env: dict | None = None, logfile: Path | None = None) -> subprocess.CompletedProcess:
    """Esegue un comando (lista, mai shell=True). Con `logfile` accoda stderr al log."""
    args = [str(c) for c in cmd]
    log("$", " ".join(_q(a) for a in args))
    full_env = {**os.environ, **(env or {})}
    if capture or logfile:
        proc = subprocess.run(args, cwd=cwd, env=full_env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if logfile:
            logfile.parent.mkdir(parents=True, exist_ok=True)
            with open(logfile, "a") as fh:
                fh.write(f"\n$ {' '.join(args)}\n{proc.stderr}")
    else:
        proc = subprocess.run(args, cwd=cwd, env=full_env, text=True)
    if check and proc.returncode != 0:
        tail = (proc.stderr or "")[-2000:] if capture or logfile else ""
        raise RuntimeError(f"Comando fallito ({proc.returncode}): {args[0]} …\n{tail}")
    return proc


def _q(a: str) -> str:
    return a if re.fullmatch(r"[\w@%+=:,./-]+", a) else "'" + a.replace("'", "'\\''") + "'"


def which(binary: str) -> str | None:
    return binary if Path(binary).is_file() and os.access(binary, os.X_OK) else shutil.which(binary)


# ── Node e progetti npm installati da install.sh ────────────────────────────
_NODE_MEMO: dict[str, str | None] = {}


def _node_major(path: str) -> int:
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=15).stdout.strip()
        return int(out.lstrip("v").split(".")[0])
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0


def node_bin() -> str | None:
    """node ≥ 20, preferito 22 (stesso ordine di find_node in install.sh).

    YT_NODE vince se è ≥ 20; poi il primo v22 tra PATH, nvm v22, node@22 di Homebrew (keg-only), node di
    Homebrew; altrimenti il primo ≥ 20 nello stesso ordine. Così node@22 installato accanto a un node più
    nuovo nel PATH viene usato davvero (è quello che chiede yt-doctor).
    """
    if "node" in _NODE_MEMO:
        return _NODE_MEMO["node"]
    env_node = os.environ.get("YT_NODE")
    if env_node and os.access(env_node, os.X_OK) and _node_major(env_node) >= NODE_MIN_MAJOR:
        _NODE_MEMO["node"] = env_node
        return env_node
    cands: list[str] = []
    if shutil.which("node"):
        cands.append(shutil.which("node") or "")
    cands += [str(p) for p in sorted((HOME / ".nvm" / "versions" / "node").glob("v22.*/bin/node"), reverse=True)]
    cands += ["/opt/homebrew/opt/node@22/bin/node", "/opt/homebrew/bin/node"]
    majors = {c: _node_major(c) for c in dict.fromkeys(cands) if c and os.access(c, os.X_OK)}
    found = (next((c for c, m in majors.items() if m == 22), None)
             or next((c for c, m in majors.items() if m >= NODE_MIN_MAJOR), None))
    _NODE_MEMO["node"] = found
    return found


def node_env(extra: dict | None = None) -> dict:
    """Ambiente per i processi node: la cartella del node scelto in testa al PATH (shebang `env node`)."""
    env = dict(extra or {})
    node = node_bin()
    if node:
        env["PATH"] = str(Path(node).parent) + os.pathsep + os.environ.get("PATH", "")
    return env


def _sha256_of(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def npm_project_status(src: Path, dst: Path) -> tuple[bool, str]:
    """Il progetto npm `src` (nel plugin) è installato in `dst` con lo stesso package-lock.json?"""
    if not (dst / "node_modules").is_dir():
        return False, f"mancano i node_modules in {dst}: {SETUP_HINT}"
    try:
        same = src.resolve() == dst.resolve()
    except OSError:
        same = False
    if same:      # checkout di sviluppo con layout storico: node_modules accanto ai sorgenti
        return True, ""
    want = _sha256_of(src / "package-lock.json")
    try:
        have = (dst / _config.LOCK_STAMP).read_text().strip()
    except OSError:
        have = None
    if want and want != have:
        return False, f"le dipendenze di {src.name} sono cambiate (package-lock.json) dopo l'ultimo setup: {SETUP_HINT}"
    return True, ""


_SYNC_SKIP = {"node_modules", ".remotion", "out", "build", _config.LOCK_STAMP, ".DS_Store"}


def sync_tree(src: Path, dst: Path, skip: Iterable[str] = _SYNC_SKIP) -> int:
    """Copia in `dst` i file di `src` cambiati (dimensione/mtime) e toglie quelli spariti; salta `skip`
    (a ogni livello). Ritorna il numero di file copiati o rimossi."""
    import filecmp

    skip = set(skip)
    changed = 0
    src, dst = Path(src), Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in skip]
        rel = Path(root).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for f in files:
            if f in skip:
                continue
            s, d = Path(root) / f, dst / rel / f
            if d.is_symlink() or not d.exists() or not filecmp.cmp(s, d, shallow=True):
                tmp = d.with_name(f".{f}.yt-sync-{os.getpid()}")
                shutil.copy2(s, tmp)
                os.replace(tmp, d)        # atomico: due render in parallelo non leggono mai un file a metà
                changed += 1
    for root, dirs, files in os.walk(dst, topdown=True):
        dirs[:] = [d for d in dirs if d not in skip]
        rel = Path(root).relative_to(dst)
        for f in files:
            if f not in skip and ".yt-sync-" not in f and not (src / rel / f).exists():
                (Path(root) / f).unlink(missing_ok=True)
                changed += 1
        for d in list(dirs):
            if not (src / rel / d).exists():
                shutil.rmtree(Path(root) / d, ignore_errors=True)
                dirs.remove(d)
                changed += 1
    return changed


def prepare_remotion() -> Path:
    """Progetto Remotion pronto da eseguire: sincronizza i sorgenti del plugin nella copia della data dir
    (dove install.sh ha fatto npm ci). RuntimeError con l'indicazione del setup se manca qualcosa."""
    ok, why = npm_project_status(REMOTION_SRC, REMOTION_DIR)
    if not ok:
        raise RuntimeError(f"Remotion non installato: {why}")
    if REMOTION_SRC.resolve() != REMOTION_DIR.resolve():
        n = sync_tree(REMOTION_SRC, REMOTION_DIR)
        # src/lib/brand.ts importa ../../../assets/brands/demo/tokens.json (default dello Studio): stessa struttura
        # accanto alla copia. I brand esterni non servono qui: yt-remotion passa token e stile nelle props e
        # collega i loro font nella public dir temporanea di ogni render.
        n += sync_tree(BRANDS, REMOTION_DIR.parent / "assets" / "brands")
        if n:
            log(f"· sorgenti Remotion sincronizzati nella data dir ({n} file)")
    return REMOTION_DIR


# ── Tempi ───────────────────────────────────────────────────────────────────
def fmt_ts(sec: float, style: str = "hms") -> str:
    """hms → 00:12:03.40 · srt → 00:12:03,400 · vtt → 00:12:03.400 · yt → 12:03 / 1:02:03."""
    sec = max(0.0, float(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if style == "yt":
        s_int = int(s)
        return f"{int(h)}:{int(m):02d}:{s_int:02d}" if h >= 1 else f"{int(m)}:{s_int:02d}"
    if style == "srt":
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s % 1) * 1000)) % 1000:03d}"
    if style == "vtt":
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}.{int(round((s % 1) * 1000)) % 1000:03d}"
    return f"{int(h):02d}:{int(m):02d}:{s:05.2f}"


def parse_ts(text: str | float | int) -> float:
    """Accetta 75.2, '1:15.2', '00:01:15,200', '1:02:03'."""
    if isinstance(text, (int, float)):
        return float(text)
    t = str(text).strip().replace(",", ".")
    parts = t.split(":")
    total = 0.0
    for p in parts:
        total = total * 60 + float(p)
    return total


# ── Media ───────────────────────────────────────────────────────────────────
def ffprobe(path: Path | str) -> dict:
    proc = run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path], capture=True)
    return json.loads(proc.stdout)


def media_duration(path: Path | str) -> float:
    return float(ffprobe(path)["format"]["duration"])


def sha256_file(path: Path | str, chunk: int = 1 << 22, limit_bytes: int | None = None) -> str:
    """Hash del file (con `limit_bytes` hash veloce di testa+coda+dimensione per file enormi)."""
    path = Path(path)
    h = hashlib.sha256()
    size = path.stat().st_size
    with open(path, "rb") as fh:
        if limit_bytes and size > 2 * limit_bytes:
            h.update(fh.read(limit_bytes))
            fh.seek(size - limit_bytes)
            h.update(fh.read(limit_bytes))
            h.update(str(size).encode())
        else:
            for block in iter(lambda: fh.read(chunk), b""):
                h.update(block)
    return h.hexdigest()


# ── Profili canale ──────────────────────────────────────────────────────────
def channel_file(slug: str, suffix: str = ".md") -> Path:
    """File di canale `<slug><suffix>` (.md, .glossary.txt, .confusions.json): il primo che esiste nelle
    CHANNELS_DIRS (cartelle extra della configurazione, poi docs/yt/channels del plugin). Se non esiste,
    il percorso accanto al profilo del canale (o nella prima cartella extra, o in quella del plugin)."""
    for d in CHANNELS_DIRS:
        p = d / f"{slug}{suffix}"
        if p.exists():
            return p
    if suffix != ".md":
        prof = channel_file(slug, ".md")
        if prof.exists():
            return prof.parent / f"{slug}{suffix}"
    return CHANNELS_DIRS[0] / f"{slug}{suffix}"


def load_channel(slug: str) -> dict:
    """Legge <slug>.md (frontmatter YAML) dalle CHANNELS_DIRS → dict con 'body' (e 'profile_path')."""
    import yaml

    path = channel_file(slug, ".md")
    if not path.exists() or str(slug).startswith("_"):
        where = ", ".join(str(d) for d in CHANNELS_DIRS)
        raise FileNotFoundError(f"Profilo canale mancante: {slug}.md (cercato in {where}; copia "
                                f"{CHANNELS_DIR / '_template.md'} in {CHANNELS_DIRS[0]}/{slug}.md e compilalo)")
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    meta = yaml.safe_load(m.group(1)) if m else {}
    meta = meta or {}
    meta["body"] = m.group(2) if m else text
    meta.setdefault("slug", slug)
    meta.setdefault("profile_path", str(path))
    return meta


def list_channels() -> dict[str, Path]:
    """{slug: profilo} dei profili nei channels_dirs (nessuno è incluso nel plugin)."""
    return _config.list_channels(_SETTINGS)


def default_channel() -> str | None:
    """Lo slug dell'unico profilo nei channels_dirs, altrimenti None: con zero o più profili il canale si chiede,
    non si indovina."""
    return _config.default_channel(_SETTINGS)


def channel_brand(slug: str | None) -> str:
    """Brand di un canale: `brand.slug` del profilo, altrimenti lo slug del canale se esiste un brand con quel
    nome, altrimenti il brand neutro del plugin (demo)."""
    if slug:
        try:
            prof = load_channel(slug)
        except Exception:  # noqa: BLE001 — profilo assente o illeggibile
            prof = {}
        braw = prof.get("brand") if isinstance(prof.get("brand"), dict) else {}
        cand = braw.get("slug") or (prof.get("brand") if isinstance(prof.get("brand"), str) else None)
        if cand and brand_dir(str(cand)):
            return str(cand)
        if brand_dir(slug):
            return str(slug)
    return BUILTIN_BRAND


# ── Brand (esterni in brands_dirs, poi assets/brands del plugin) ───────────
def brand_dir(slug: str | None) -> Path | None:
    """Cartella del brand: la prima <brands_dir>/<slug>/ con tokens.json (esterne prima, poi il plugin)."""
    return _config.brand_dir(slug, _SETTINGS) if slug else None


def brand_file(slug: str, rel: str) -> Path:
    """File del brand (es. layout.json, remotion.json) nella sua cartella. Se il brand non esiste ancora, il
    percorso dove lo scriverebbe un comando di misura: la prima cartella di brands_dirs dell'operatore (mai il
    plugin: i brand dei canali non ci entrano; nel plugin c'è solo il brand neutro demo)."""
    bd = brand_dir(slug)
    if bd:
        return bd / rel
    if slug != BUILTIN_BRAND:
        ext = [d for d in BRANDS_DIRS if d != BRANDS]
        if ext:
            return ext[0] / slug / rel
    return BRANDS / slug / rel


def layout_file(channel: str | None = None, brand: str | None = None) -> Path:
    """layout.json del master composito, un solo risolutore per yt-clips, yt-portrait e yt-thumb-render: il brand
    esplicito (se non è demo), poi il brand del canale (brand.slug del profilo), poi <brands_dir>/<canale>/layout.json
    (dove `yt-clips layout --measure --write` lo scrive anche per un canale senza token), altrimenti il layout generico
    del brand neutro demo (una camera a tutto quadro, senza inset né PiP)."""
    cands: list[str] = []
    for c in (brand, channel_brand(channel) if channel else None, channel):
        if c and c != BUILTIN_BRAND and c not in cands:
            cands.append(str(c))
    for c in cands:
        p = brand_file(c, "layout.json")
        if p.exists():
            return p
    return brand_file(BUILTIN_BRAND, "layout.json")


def brand_is_external(slug: str | None) -> bool:
    bd = brand_dir(slug)
    try:
        return bool(bd) and bd.resolve().parent != BRANDS.resolve()
    except OSError:
        return bool(bd)


def brand_tokens(slug: str) -> dict:
    bd = brand_dir(slug)
    path = bd / "tokens.json" if bd else BRANDS / str(slug) / "tokens.json"
    return read_json(path) if path.exists() else {}


def brand_font_dirs(slug: str | None) -> list[Path]:
    """Cartelle font del brand (<brand>/fonts) prima di quelle del plugin (assets/fonts)."""
    bd = brand_dir(slug)
    dirs = [bd / "fonts"] if bd and (bd / "fonts").is_dir() else []
    return dirs + [FONTS]


def find_font(name: str, slug: str | None = None, extra: Iterable[Path] = ()) -> Path | None:
    """Primo file font `name` tra le cartelle extra, quelle del brand e assets/fonts del plugin."""
    for d in [*extra, *brand_font_dirs(slug)]:
        p = Path(d) / name
        if p.is_file():
            return p
    return None


def brand_remotion_style(slug: str) -> dict:
    """<brand>/remotion.json: override di stile per le composizioni generiche di Remotion ({} se assente)."""
    bd = brand_dir(slug)
    p = bd / "remotion.json" if bd else None
    return read_json(p) if p and p.is_file() else {}


def own_brand(slug: str | None) -> bool:
    """Brand «proprio» (licenza Remotion, design §11): il brand neutro demo del plugin (lo usa l'operatore per le
    prove), un brand che lo dichiara nei token ("own": true), oppure il brand di un canale con profilo
    kind: own o kind: personal. I brand dei clienti no: per loro HyperFrames o soli file finiti."""
    if not slug:
        return False
    if slug == BUILTIN_BRAND:
        return True
    if brand_tokens(slug).get("own") is True:
        return True
    try:
        return load_channel(slug).get("kind") in ("own", "personal")
    except Exception:  # noqa: BLE001 — profilo assente o illeggibile: non è un brand proprio
        return False


def remotion_allowed(brand: str | None, channel: str | None = None) -> bool:
    """Remotion ammesso (licenza, design §11): mai per un canale con profilo kind: client, qualunque sia il brand (un
    cliente senza cartella brand ricade sul brand neutro demo, che da solo passerebbe); altrimenti own_brand(brand)."""
    if channel:
        try:
            if load_channel(channel).get("kind") == "client":
                return False
        except Exception:  # noqa: BLE001 — profilo assente o illeggibile: decide il brand
            pass
    return own_brand(brand)


def channel_of_path(path: str | Path | None, levels: int = 3) -> str | None:
    """Canale del workdir che contiene `path`: campo «channel» del primo project.json trovato salendo di `levels` livelli."""
    if not path:
        return None
    for d in list(Path(path).expanduser().resolve().parents)[:levels]:
        pj = d / "project.json"
        if pj.is_file():
            try:
                ch = read_json(pj).get("channel")
            except Exception:  # noqa: BLE001
                ch = None
            return str(ch) if ch else None
    return None


def learned_file(slug: str, suffix: str = ".md") -> Path:
    """File appreso del canale in <studio_dir>/data/learned/<slug><suffix> (yt-learn; mai nella repo del plugin):
    .md (playbook), .glossary.txt e .confusions.json (dalle correzioni del transcript). Può non esistere."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", str(slug or "")) or ".." in str(slug):
        raise ValueError(f"slug di canale non valido: {slug!r}")
    return LEARNED / f"{slug}{suffix}"


def shareable_channels(configured: Any) -> list[str]:
    """Canali le cui lezioni possono diventare una PR sulla repo (Tier B, 13-learning-loop §1.2, §9.2). Opt-in:
    uno slug conta solo se è in learning_pr_channels (default vuoto) E il suo profilo nei channels_dirs ha
    `kind: own` E `share_lessons: true`. Un cliente o un canale personale messo per errore nella configurazione
    resta locale (Tier A), così come un canale proprio che non ha scelto di condividere."""
    out: list[str] = []
    for slug in configured or []:
        slug = str(slug).strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", slug) or ".." in slug or slug.startswith("_"):
            continue
        prof = _config.find_profile(slug, _SETTINGS)
        meta = _config.profile_meta(prof) if prof else {}
        if meta.get("kind") == "own" and meta.get("share_lessons") is True and slug not in out:
            out.append(slug)
    return out


def channel_files(slug: str, suffix: str) -> list[Path]:
    """File di canale che esistono, nell'ordine in cui si fondono: quello del profilo/plugin (channel_file),
    poi quello appreso da yt-learn (learned_file). Usato per .glossary.txt e .confusions.json."""
    out: list[Path] = []
    try:
        cands = [channel_file(slug, suffix), learned_file(slug, suffix)] if slug else []
    except ValueError:
        cands = [channel_file(slug, suffix)]
    for p in cands:
        if p.exists() and p not in out:
            out.append(p)
    return out


def channel_confusions(slug: str) -> dict:
    """Confusioni ASR del canale: <slug>.confusions.json (profilo o plugin) + quelle apprese dalle correzioni
    (<studio>/data/learned/<slug>.confusions.json), una lista sola. {"confusions": [...], "sources": [...]}."""
    merged: dict = {"confusions": [], "sources": []}
    for p in channel_files(slug, ".confusions.json"):
        try:
            data = read_json(p)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        for k, v in data.items():
            if k not in ("confusions", "sources"):
                merged.setdefault(k, v)
        merged["confusions"] += [c for c in data.get("confusions") or [] if isinstance(c, dict) and c.get("term")]
        merged["sources"].append(str(p))
    return merged


def glossary_terms(slug: str, extra: Path | str | None = None, *, learned: bool = False) -> list[str]:
    """Termini del glossario canale (+ glossario episodio). Una voce per riga, # commenti.
    learned=True aggiunge i termini appresi da yt-learn (<studio>/data/learned/<slug>.glossary.txt). Il default
    resta False: il costruttore storico del prompt (transcribe.build_prompt_legacy) deve restare identico, se no
    i transcript fatti allora risulterebbero «non aggiornati»; il prompt nuovo li legge da glossary.channel_terms."""
    terms: list[str] = []
    extra_learned = None
    if learned and slug:
        try:
            extra_learned = learned_file(slug, ".glossary.txt")
        except ValueError:
            extra_learned = None
    for p in [channel_file(slug, ".glossary.txt"), extra_learned, Path(extra) if extra else None]:
        if p and Path(p).exists():
            for line in Path(p).read_text().splitlines():
                line = line.split("#", 1)[0].strip()
                if line:
                    terms.append(line)
    return list(dict.fromkeys(terms))


# ── Cartella di lavoro (progetto) ───────────────────────────────────────────
def slugify(text: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:60] or "video"


def today() -> str:
    return _dt.date.today().isoformat()


def workdir_path(channel: str, slug: str, date: str | None = None) -> Path:
    return WORK / channel / f"{date or today()}-{slugify(slug)}"


def resolve_workdir(arg: str | Path) -> Path:
    """Accetta un path o '<channel>/<dir>' relativo a <studio_dir>/work."""
    p = Path(arg).expanduser()
    if not p.is_absolute() and not p.exists():
        p = WORK / p
    if not (p / "project.json").exists():
        raise FileNotFoundError(f"Non è una cartella di lavoro (manca project.json): {p}")
    return p.resolve()


def load_project(workdir: Path | str) -> dict:
    return read_json(Path(workdir) / "project.json")


def save_project(workdir: Path | str, project: dict) -> None:
    project["updated"] = _dt.datetime.now().isoformat(timespec="seconds")
    write_json(Path(workdir) / "project.json", project)


def update_project(workdir: Path | str, **fields: Any) -> dict:
    project = load_project(workdir)
    for key, value in fields.items():
        if isinstance(value, dict) and isinstance(project.get(key), dict):
            project[key].update(value)
        else:
            project[key] = value
    save_project(workdir, project)
    return project


def source_path(workdir: Path | str, key: str | None = None) -> Path:
    """Percorso reale del sorgente principale (o di `key`) dal project.json."""
    project = load_project(workdir)
    sources = project.get("sources", {})
    if not sources:
        raise ValueError("Nessun sorgente in project.json")
    key = key or project.get("main_source") or next(iter(sources))
    return Path(sources[key]["path"]).expanduser()


def analysis_audio(workdir: Path | str, kind: str = "16k") -> Path:
    """analysis/audio16k.wav (mono, ASR) · analysis/audio48k.wav (stereo, mix)."""
    return Path(workdir) / "analysis" / f"audio{kind}.wav"


# ── Decoder AAC: policy centrale ────────────────────────────────────────────
# Perché esiste: `aac_at` (AudioToolbox) decodifica SEMPRE in s16 (anche con -request_sample_fmt
# flt/fltp/s32), quindi i picchi sopra 0 dBFS che un master può contenere vengono tagliati piatti. Il decoder
# nativo di FFmpeg (`aac`) decodifica in float senza clipping.
# Su un master con pacchetti AAC rovinati i suoi errori ("channel element duplicate") cadono di solito dentro
# la zona già corrotta del video: lì scarta i pacchetti e il filtro AUDIO_ASYNC riempie il buco di silenzio,
# quindi il timeline resta quello del contenitore (misurato: 0 ms rispetto a una decodifica fresca dopo
# l'errore; aac_at invece slitta di un frame AAC, −23.2 ms, dopo gli stessi pacchetti).
#
# Regole (aac_decoder_policy, in ordine):
#   1. stream non AAC (codec noto)            → nativo (aac_at decodifica solo AAC);
#   2. env YT_AAC_DECODER=native|aac_at       → forzatura esplicita (auto/vuoto = nessuna);
#   3. file = sorgente di una cartella di lavoro (workdir passata, oppure trovata risalendo
#      dal percorso o tra i project.json di <studio_dir>/work)
#        → project.json audio_decoder_by_source[<key>] / audio_decoder (deciso da yt-ingest),
#          altrimenti la stessa regola sui dati di analysis/inventory.json;
#   4. file dentro una cartella di lavoro ma fuori da src/ (proxy, montato, consegne, Shorts)
#        → nativo: sono codificati dal toolkit (aac/aac_at encoder) e si decodificano puliti;
#   5. qualunque altro AAC (chiamata senza workdir, sorgente mai analizzato)
#        → nativo SOLO se è sicuro: una decodifica nativa di prova (cache in
#          <studio_dir>/cache/aac-decoder/, chiave percorso+dimensione+mtime) non dà errori;
#          altrimenti aac_at. Se la prova fallisce: aac_at.
# Regola di yt-ingest (decide_aac_decoder): nativo se non ci sono errori nativi, oppure se
# TUTTI gli errori nativi cadono entro ±AAC_ERROR_MARGIN_S da uno span corrotto del video;
# altrimenti aac_at (decodifica senza buchi, ma picchi > 0 dBFS limitati).
# Ogni decodifica del sorgente va fatta con AUDIO_ASYNC: con il nativo è ciò che tiene l'audio
# allineato al video dopo un pacchetto scartato.
AAC_DECODERS = ("native", "aac_at")
AAC_DECODER_ENV = "YT_AAC_DECODER"
AAC_ERROR_MARGIN_S = 3.0
AAC_SCAN_VERSION = 1
AUDIO_ASYNC = "aresample=async=1:min_hard_comp=0.02:first_pts=0"
_AAC_MEMO: dict[str, Any] = {}


def aac_decoder_env() -> str | None:
    """Forzatura da ambiente: 'native' | 'aac_at' | None (assente, vuota o 'auto')."""
    raw = (os.environ.get(AAC_DECODER_ENV) or "").strip().lower()
    if raw in ("", "auto"):
        return None
    alias = {"aac": "native", "ffmpeg": "native", "audiotoolbox": "aac_at", "at": "aac_at"}
    value = alias.get(raw, raw)
    if value not in AAC_DECODERS:
        raise ValueError(f"{AAC_DECODER_ENV}={raw!r} non valido: usa native, aac_at o auto")
    return value


def aac_decoder_input_args(decoder: str) -> list[str]:
    """Argomenti ffmpeg (da mettere prima di -i) per un decoder della policy."""
    return ["-c:a", "aac_at"] if decoder == "aac_at" else []


def decide_aac_decoder(native_errors: int | None, native_error_times: list[float] | None = None,
                       corrupt_spans: list[dict] | None = None, *, margin: float = AAC_ERROR_MARGIN_S,
                       native_error_spans: list[dict] | None = None) -> dict:
    """Regola di yt-ingest. `corrupt_spans=None` = integrità video non verificata.

    Ritorna {decoder, reason, native_errors, outside_corrupt (tempi fuori dagli span), margin_s}."""
    n = int(native_errors or 0)
    base = {"native_errors": n, "margin_s": margin, "outside_corrupt": []}
    if n == 0:
        return {**base, "decoder": "native",
                "reason": "decoder AAC nativo senza errori: decodifica float, nessun clipping dei picchi > 0 dBFS"}
    times = [float(t) for t in native_error_times] if native_error_times is not None else None
    if not times and native_error_spans:  # inventari vecchi: solo span (start/end) degli errori
        times = [float(x) for s in native_error_spans for x in (s["start"], s["end"])]
    if not times:
        return {**base, "decoder": "aac_at",
                "reason": f"{n} errori AAC nativi senza timestamp: non verificabile, uso aac_at (picchi > 0 dBFS limitati)"}
    if corrupt_spans is None:
        return {**base, "decoder": "aac_at",
                "reason": f"{n} errori AAC nativi ma integrità video non verificata (nessun corrupt_spans): uso aac_at"}
    spans = [(float(s["start"]), float(s["end"])) for s in corrupt_spans]
    outside = sorted({round(t, 3) for t in times if not any(a - margin <= t <= b + margin for a, b in spans)})
    if outside:
        return {**base, "decoder": "aac_at", "outside_corrupt": outside[:50],
                "reason": f"{len(outside)} istanti di errore AAC nativo fuori dagli span corrotti ±{margin:g} s "
                          f"(primo a {fmt_ts(outside[0])}): uso aac_at (s16, picchi > 0 dBFS limitati)"}
    near = sorted({f"{fmt_ts(a)}–{fmt_ts(b)}" for a, b in spans
                   if any(a - margin <= t <= b + margin for t in times)})
    return {**base, "decoder": "native",
            "reason": f"{n} errori AAC nativi, tutti entro ±{margin:g} s da span corrotti ({', '.join(near)}): "
                      "decoder nativo (float, niente clipping; i pacchetti scartati diventano silenzio con aresample async)"}


def _aac_info(info: Any) -> tuple[Path | None, str | None]:
    """`info` = percorso, oppure dict con path/src_path e codec/acodec/codec_name (stream AUDIO)."""
    if info is None:
        return None, None
    if isinstance(info, (str, Path)):
        return Path(info).expanduser(), None
    path = info.get("path") or info.get("src_path")
    codec = info.get("acodec") or info.get("codec") or info.get("codec_name")
    return (Path(path).expanduser() if path else None), codec


def _audio_codec(path: Path) -> str | None:
    """Codec del primo stream audio (memo per percorso+mtime); None se non leggibile."""
    try:
        st = path.stat()
    except OSError:
        return None
    key = f"codec:{path.resolve()}:{st.st_size}:{st.st_mtime_ns}"
    if key not in _AAC_MEMO:
        try:
            proc = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "a:0", "-show_entries",
                                   "stream=codec_name", "-of", "csv=p=0", str(path)],
                                  capture_output=True, text=True, timeout=60)
            _AAC_MEMO[key] = (proc.stdout.strip().splitlines() or [""])[0] or "none"
        except (OSError, subprocess.SubprocessError):
            _AAC_MEMO[key] = None
    return _AAC_MEMO[key]


def _project_of(path: Path) -> tuple[Path, dict] | None:
    """Cartella di lavoro che contiene `path` (risalendo, senza seguire il symlink)."""
    for parent in path.absolute().parents:
        pj = parent / "project.json"
        if pj.is_file():
            try:
                proj = read_json(pj)
            except (OSError, ValueError):
                return None
            return (parent, proj) if isinstance(proj.get("sources"), dict) else None
    return None


def _source_key(workdir: Path, project: dict, path: Path) -> str | None:
    try:
        real = path.resolve()
    except OSError:
        return None
    for key, s in (project.get("sources") or {}).items():
        for cand in (s.get("path"), s.get("link") and str(workdir / s["link"])):
            if cand:
                try:
                    if Path(cand).expanduser().resolve() == real:
                        return key
                except OSError:
                    continue
    return None


def _registered_source(path: Path) -> tuple[Path, dict, str] | None:
    """Progetto in <studio_dir>/work che usa `path` come sorgente (con una decisione), se c'è."""
    try:
        real, size = path.resolve(), path.stat().st_size
    except OSError:
        return None
    for pj in sorted([*WORK.glob("*/*/project.json"), *WORK.glob("*/*/*/project.json")]):
        try:
            proj = read_json(pj)
        except (OSError, ValueError):
            continue
        for key, s in (proj.get("sources") or {}).items() if isinstance(proj.get("sources"), dict) else []:
            try:
                same = Path(s.get("path", "")).expanduser().resolve() == real
            except OSError:
                continue
            if same and (s.get("size") in (None, size)) and _recorded_decoder(pj.parent, proj, key):
                return pj.parent, proj, key
    return None


def _recorded_decoder(workdir: Path, project: dict, key: str) -> dict | None:
    """Decisione per il sorgente `key`: project.json, altrimenti ricavata da inventory.json."""
    entry = (project.get("audio_decoder_by_source") or {}).get(key)
    if isinstance(entry, dict) and entry.get("decoder") in AAC_DECODERS:
        return {"decoder": entry["decoder"], "reason": entry.get("reason", ""), "basis": "project"}
    main = project.get("main_source") or next(iter(project.get("sources") or {}), None)
    if key == main and project.get("audio_decoder") in AAC_DECODERS:
        return {"decoder": project["audio_decoder"], "reason": project.get("audio_decoder_reason", ""),
                "basis": "project"}
    inv_path = workdir / "analysis" / ("inventory.json" if key == main else f"source-{key}/inventory.json")
    try:
        inv = read_json(inv_path)
    except (OSError, ValueError):
        return None
    ad = inv.get("audio_decode") or {}
    if ad.get("decision") in AAC_DECODERS:
        return {"decoder": ad["decision"], "reason": ad.get("decision_reason", ""), "basis": "inventory"}
    if ad.get("native_aac_errors") is None:
        return None
    integ = inv.get("integrity") or {}
    spans = integ.get("corrupt_spans") if "corrupt_spans" in integ else None
    d = decide_aac_decoder(ad["native_aac_errors"], ad.get("native_aac_error_times"), spans,
                           native_error_spans=ad.get("native_aac_error_spans"))
    return {"decoder": d["decoder"], "reason": d["reason"], "basis": "inventory"}


def aac_native_scan(path: Path | str, *, use_cache: bool = True) -> dict:
    """Decodifica di prova con il decoder AAC nativo (solo conteggio errori), in cache."""
    path = Path(path).expanduser()
    st = path.stat()
    real = path.resolve()
    key = hashlib.sha1(f"{real}|{st.st_size}|{st.st_mtime_ns}|v{AAC_SCAN_VERSION}".encode()).hexdigest()[:20]
    cache = CACHE / "aac-decoder" / f"{key}.json"
    if use_cache and cache.exists():
        try:
            return read_json(cache)
        except (OSError, ValueError):
            pass
    log(f"· prova decoder AAC nativo su {path.name} (una volta, poi in cache)")
    t0 = _dt.datetime.now()
    proc = subprocess.run([FFMPEG, "-nostdin", "-hide_banner", "-nostats", "-loglevel", "level+error", "-c:a", "aac",
                           "-i", str(path), "-vn", "-sn", "-dn", "-map", "0:a:0", "-f", "null", "-"],
                          capture_output=True, text=True, errors="replace")
    errs = [ln for ln in proc.stderr.splitlines() if "[error]" in ln and "aist#" not in ln[:40]]
    res = {"path": str(real), "size": st.st_size, "mtime_ns": st.st_mtime_ns, "native_errors": len(errs),
           "first_errors": errs[:3], "returncode": proc.returncode, "version": AAC_SCAN_VERSION,
           "elapsed_s": round((_dt.datetime.now() - t0).total_seconds(), 2)}
    try:
        write_json(cache, res)
    except OSError:
        pass
    return res


def aac_decoder_policy(workdir: Path | str | None = None, info: Any = None) -> dict:
    """Decoder AAC da usare per decodificare un sorgente (regole in testa a questa sezione).

    workdir: cartella di lavoro (opzionale). info: percorso del media oppure dict dello stream
    audio (path/src_path + codec/acodec/codec_name); senza info = sorgente principale di workdir.
    Ritorna {decoder: 'native'|'aac_at', args: [...], basis, reason, workdir, source}."""
    def out(decoder: str, basis: str, reason: str, wd: Path | None = None, key: str | None = None) -> dict:
        return {"decoder": decoder, "args": aac_decoder_input_args(decoder), "basis": basis, "reason": reason,
                "workdir": str(wd) if wd else None, "source": key}

    path, codec = _aac_info(info)
    wd = Path(workdir).expanduser() if workdir else None
    project = None
    if wd is not None and (wd / "project.json").exists():
        project = load_project(wd)
    if path is None and project is not None:
        try:
            path = source_path(wd)
        except (ValueError, KeyError):
            path = None
    if codec is None and path is not None:
        codec = _audio_codec(path)
    if codec and codec != "aac":
        return out("native", "codec", f"audio {codec}: aac_at serve solo per AAC")
    forced = aac_decoder_env()
    if forced:
        return out(forced, "env", f"{AAC_DECODER_ENV}={forced}")
    if path is None:
        return out("aac_at", "fallback", "nessun file da valutare: aac_at (comportamento storico)")
    key = None
    if project is not None:
        key = _source_key(wd, project, path)
    if key is None:  # cartella di lavoro trovata risalendo dal percorso
        found = _project_of(path)
        if found:
            wd, project = found
            key = _source_key(wd, project, path)
            if key is None:
                try:
                    inside_src = (wd / "src") in path.absolute().parents
                except OSError:
                    inside_src = False
                if not inside_src:
                    return out("native", "output", "file prodotto dal toolkit nella cartella di lavoro", wd)
    if key is None:
        reg = _registered_source(path)
        if reg:
            wd, project, key = reg
    if key is not None and project is not None:
        rec = _recorded_decoder(wd, project, key)
        if rec:
            return out(rec["decoder"], rec["basis"], rec["reason"], wd, key)
    try:
        scan = aac_native_scan(path)
    except OSError as exc:
        return out("aac_at", "fallback", f"prova del decoder nativo impossibile ({exc}): aac_at", wd, key)
    if scan.get("returncode") == 0 and scan.get("native_errors") == 0:
        return out("native", "scan", "prova del decoder nativo senza errori", wd, key)
    return out("aac_at", "scan", f"prova del decoder nativo: {scan.get('native_errors')} errori "
                                 f"(exit {scan.get('returncode')}): aac_at finché yt-ingest non decide", wd, key)


def aac_decoder_args(workdir: Path | str | None = None, info: Any = None) -> list[str]:
    """[] (decoder AAC nativo, float) oppure ['-c:a', 'aac_at']: argomenti da mettere prima di -i.

    Unico punto di decisione del toolkit (vedi aac_decoder_policy e il commento della sezione)."""
    return aac_decoder_policy(workdir, info)["args"]
