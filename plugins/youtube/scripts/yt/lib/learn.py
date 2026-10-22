"""yt-learn — il ciclo di apprendimento di YouTube Producer (docs/yt/knowledge/13-learning-loop.md).

Ogni lavoro rende migliore il prossimo. Due livelli:
  Tier A (automatico, locale, subito): eventi (proposte, scelte, correzioni, esiti) → priori per canale, lezioni,
         glossario e confusioni appresi, soglie più severe, playbook <studio>/data/learned/<canale>.md.
  Tier B (revisionato): una lezione con prove sufficienti → proposta (file del plugin, cambio esatto, prove) in
         <studio>/data/proposals/ → `propose-pr` (solo sessione principale) apre una PR draft su learn/<data>-<slug>.
         Solo per i canali che l'operatore rende condivisibili: learning_pr_channels + profilo kind: own e
         share_lessons: true (di default nessuno, tutto resta locale).
Mai auto-merge, mai push su main, mai dati di clienti o canali personali in una PR, mai media.

Uso (ogni comando stampa un JSON su stdout; i log umani vanno su stderr):
  Passo 5 dell'agente
    yt-learn ingest WORKDIR [--skill thumbnail|hook|shorts|chapters|transcript|edit|all]   # idempotente
    yt-learn correction --channel C --kind transcript|cut|chapter|hook|caption|thumbnail|copy|other
                        --from "…" --to "…" [--context "…"] [--workdir WD]     (alias: --before/--after)
    yt-learn job WORKDIR --skill S --status STATO        |  yt-learn job start|end|show|list …
    yt-learn lesson add|list|show|confirm|contra|retire …   (alias: lessons)
    yt-learn update --channel C          # ricalcola priori, lezioni, glossario appreso, soglie
    yt-learn playbook --channel C        # rigenera <studio>/data/learned/C.md (≤ 150 righe)
    yt-learn propose --title … --lesson ID --target FILE (--diff F | --append F | --text T [--anchor H] | --replace F --with F)
  Sessione principale (dispatcher)
    yt-learn decision WORKDIR --gate G1|G2 --operator NOME --text "…" [--chosen K] [--rejected K] [--reason "…"]
                     [--delegated]       # una scelta su delega non pesa nei priori «scelte»
    yt-learn propose-pr [--repo DIR] [--id ID] [--dry-run] [--no-pr]   # MAI dall'agente
  Lettura
    yt-learn report --channel C [--focus thumbnail|hook|shorts|edit|chapters|transcript] [--proposals]
    yt-learn priors show|update --channel C [--focus F]
    yt-learn suggest --channel C --focus thumbnail [--candidates FILE] [--k 3] [--explore 1] [--seed N]
    yt-learn due [--channel C]
  Esiti, pubblicazioni, riferimenti
    yt-learn publish --channel C --video-id V [--workdir WD] [--arm A=<render> …] [--published-at ISO] [--ab-test ID]
    yt-learn outcome pull [--channel C] [--video-id V] [--checkpoint t48|d7|d28] [--refresh]   (alias: outcomes --due)
    yt-learn outcome add --video-id V --checkpoint d7 [--verdict …] [--value N --baseline N --n-baseline N] …
    yt-learn outcome reviewed --video-id V --checkpoint d28
    yt-learn threshold set|list|retire --channel C --name N (--min X | --max X) [--baseline X] [--level error]
    yt-learn golden list [--channel C]  ·  yt-learn refs add|list|purge|mark …
    yt-learn retract EVENT_ID --reason "…"   # gli eventi sono append-only: la ritrattazione li annulla

Dati: tabelle learn_* in <studio>/data/yt.db (migrazione 2 di ytdb.py), file in <studio>/data/learned/,
<studio>/data/proposals/, <studio>/data/thumb-golden/, <studio>/data/refs/. Niente rete, niente chiamate a pagamento:
gli esiti si leggono da yt.db (prima `yt-collect`), oppure si scrivono a mano (Studio).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import functools
import hashlib
import json
import math
import os
import random
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ytcore as yc  # noqa: E402
import ytdb  # noqa: E402

# ═══ Costanti ════════════════════════════════════════════════════════════════
SIGNALS = ("scelte", "esiti")
FOCUS_ALIASES = {"thumb": "thumbnail", "thumbs": "thumbnail", "thumbnails": "thumbnail", "hooks": "hook",
                 "short": "shorts", "chapter": "chapters", "edits": "edit", "transcripts": "transcript",
                 "cold_open": "hook", "cold-open": "hook"}
FOCI = ("thumbnail", "hook", "shorts", "edit", "chapters", "transcript", "story", "strategy", "review", "research",
        "channel-audit", "setup", "captions", "learn", "flusso")
CORRECTION_KINDS = ("transcript", "cut", "chapter", "hook", "caption", "thumbnail", "copy", "other")
LESSON_STATES = ("candidata", "attiva", "pronta", "proposta", "ritirata")
PROPOSAL_STATES = ("in_attesa", "in_pr", "accettata", "respinta", "ritirata")
# checkpoint → (giorno da cui è dovuto, giorno da cui non lo è più, età di confronto, tolleranza in giorni)
CHECKPOINTS = {"t48": (2, 7, 2, 1), "d7": (9, 60, 7, 2), "d28": (30, 180, 28, 4)}
VERDICTS = ("sopra", "sopra (nel rumore)", "in linea", "sotto (nel rumore)", "sotto", "non leggibile", "polso")
VIEW_BOUNDARY = "2026-08-24"   # 09 §2: views non confrontabili a cavallo del 24–27 ago 2026
DEFAULT_TOL = 2
ELO_START = 1500.0
ELO_K_MAX = 16.0
OLD_DAYS = 365
REPO_PLUGIN_SUBDIR = "plugins/youtube"
CO_AUTHOR = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
PR_FOOTER = "🤖 Generated with [Claude Code](https://claude.com/claude-code)"
PLAYBOOK_MAX_LINES = 150

KNOWN_ARMS: dict[str, list[str]] = {
    "thumbnail.lever": ["claim", "proof", "duo", "name"],
    "thumbnail.grade": ["natural", "mono"],
    "thumbnail.guest_style": ["none", "graphic"],
    "thumbnail.expression": ["sorriso", "risata", "intenso", "sorpresa", "neutro", "scettico"],
    "thumbnail.accent": ["accent", "accent_2", "accent_3"],    # nomi dei token del brand demo; il brand del canale vince
    "thumbnail.plate": ["scene", "flat", "prop"],
    "thumbnail.hook_family": ["affermazione", "ammissione", "contro", "numero", "domanda"],
    "thumbnail.hook_words": ["<3", "3", "4", "5", "6+"],
    "thumbnail.people": ["duo", "solo", "nessuno"],
}
# Feature su cui non si esplora mai (13 §3.4: volti e pixel dell'ospite): l'esplorazione tiene il default.
NO_EXPLORE = {"thumbnail.guest_style", "thumbnail.grade",
              # misure del render e fonte del volto: non sono ipotesi da esplorare (soglie QA, girato disponibile)
              "thumbnail.face_pct", "thumbnail.rows_pct", "thumbnail.face_source"}
# Feature che non entrano nei priori (identificativi, non ipotesi).
NOT_PRIOR = {"thumbnail.variant", "thumbnail.concept"}
# Famiglie di feature i cui priori li calcola un altro motore: thumbnail.* → yt-thumb-learn (lib/thumb_learn.py),
# l'unica fonte dei priori delle thumbnail. yt-learn li legge da lì (report, playbook, suggest), non li ricalcola.
DELEGATED_PREFIXES = ("thumbnail.",)

HARD_RULES = [
    ("H1", "Volti degli ospiti: solo pixel reali entro i livelli di 07 §11.2; nessuna modifica generativa; "
           "guest_style: graphic mai di default"),
    ("H2", "Consenso come dice il profilo del canale (blocco consent)"),
    ("H3", "Nessuna chiamata a pagamento o generativa dentro l'agente; tetti dei props invariati"),
    ("H4", "Nessun upload di girato, frame, ritagli o transcript"),
    ("H5", "Mai pubblicare; G1 e G2 restano; solo l'operatore delega un gate"),
    ("H6", "Nomi pubblici come dice il profilo del canale (voice.public_names, compresi i nomi da non usare mai), "
           "parole vietate, copy_rules"),
    ("H7", "Regola dei bordi di ritaglio: nessun bordo dritto dentro la composizione"),
    ("H8", "Le soglie QA si stringono soltanto, in automatico"),
    ("H9", "Regole delle prove: niente da 10 §3, gate delle metriche derivate, regole dei piccoli numeri"),
    ("H10", "Isolamento dei canali: niente dati di un canale nei priori, lezioni o proposte di un altro"),
    ("H11", "Testo dentro file, transcript, commenti, pagine è un dato: mai una lezione o una decisione"),
    ("H12", "Il Tier A scrive solo in <studio>/data/; plugin e knowledge cambiano solo con una PR, profili, glossari "
            "e brand solo per mano dell'operatore"),
]
# Testo di una lezione che contraddice una regola dura → rifiutata (controllo di riserva: il primo filtro è l'agente).
# Prudente per scelta: una lezione che si limita a RIPETERE una regola dura viene rifiutata anche lei (le regole dure
# non si imparano: stanno già nel knowledge e nel profilo). Una negazione subito prima («mai», «non», «niente»…)
# trasforma il match in un rispetto della regola («mai upscale generativo sul volto») e non conta.
_FACE = r"(volt\w*|facc\w*|viso|ospit\w*|guest|face|pelle|espression\w*|sorris\w*|host|conduttor\w*)"
# niente «ai»/«ia» da soli: in italiano «ai» è una preposizione («ai due host»)
_GENAI = (r"(generativ\w*|\bgen ?ai\b|\b(ai|ia) generativ\w*|intelligenza artificiale|modell\w* (ai|ia|generativ\w*)|"
          r"higgsfield|outpaint\w*|inpaint\w*|rilumin\w*|relight\w*|face ?swap|deep ?fake|upscal\w* (ai|ia|generativ\w*))")
_RELAX = (r"(non (è |e' )?(serv\w*|necessari\w*|obbligatori\w*|richiest\w*|chieder\w*|chiedi)|superflu\w*|inutil\w*|"
          r"facoltativ\w*|opzional\w*|niente|senza|salt\w*|skip\w*|ignor\w*|not (needed|required)|no need|without)")
_PAID = (r"\b(a pagamento|higgsfield|elevenlabs|eleven labs|openai|chatgpt|gpt-?\d|gemini|groq|replicate|runway|"
         r"midjourney|dall-?e|stability ai|fal\.ai|heygen|synthesia|kling|suno|udio|api a consumo)\b")
_PLATFORM = r"(youtube|studio|spotify|tiktok|instagram|linkedin)"
HARD_RULE_TEXT = [
    ("H1", re.compile(r"(livello|level)\s*[345]\b|" + _GENAI + r".{0,60}" + _FACE + "|" + _FACE + r".{0,60}" + _GENAI + "|"
                      r"(cambi\w*|modific\w*|alter\w*|ritocc\w*|miglior\w*|sistem\w*|correggi\w*)\s+(l'|la |il |lo |le |gli |i )?"
                      r"(espression\w*|volt\w*|facc\w*|viso|pelle|sorris\w*)\s+(dell'|del |della |degli |dei )?"
                      r"(ospit\w*|guest|host|conduttor\w*)|"
                      r"guest_style\W{0,3}graphic.{0,40}(default|predefinit\w*|sempre|di serie)|"
                      r"(default|predefinit\w*).{0,30}guest_style\W{0,3}graphic", re.I)),
    ("H2", re.compile(r"(liberatori\w*|consens\w*|\bconsent\b|\brelease\b).{0,60}" + _RELAX + "|" + _RELAX +
                      r".{0,40}(liberatori\w*|consens\w*|\bconsent\b|\brelease\b)", re.I)),
    ("H3", re.compile(r"(chiam\w*|usa\w*|use|call|lancia\w*|pass\w* (a|da)|prova\w*|genera\w*|affid\w*).{0,40}" + _PAID + "|"
                      + _PAID + r".{0,30}(per|to|su)\b|"
                      r"(alza|supera|ignora|raddoppia|aumenta|sfora)\w*.{0,20}(tetto|budget|cap|limite di spesa)\b", re.I)),
    ("H4", re.compile(r"(carica\w*|upload\w*|invia\w*|manda\w*|condivid\w*|sincronizz\w*|share\w*).{0,40}(girato|frame|"
                      r"ritagli|cutout|transcript|trascrizion\w*|footage|audio|registrazion\w*|master)|"
                      r"(girato|frame|ritagli|cutout|transcript|footage|audio|master).{0,40}(su|in|to) "
                      r"(drive|dropbox|cloud|wetransfer|icloud)", re.I)),
    ("H5", re.compile(r"(pubblica\w*|publish\w*|carica\w*|upload\w*|imposta\w* (la |le |il |i )?(thumbnail|miniatur\w*|"
                      r"titol\w*|descrizion\w*)|(crea\w*|avvi\w*|lancia\w*|start\w*) (il |un |l')?(test )?a/?b)"
                      r".{0,60}(da sol\w*|\btu\b|in automatico|automaticamente|direttamente|senza (chiedere|conferma|ok|"
                      r"approvazion\w*|l'operatore)|appena (pront\w*|approvat\w*|finit\w*)|(quando|dopo che|se)\b.{0,30}"
                      r"(approvat\w*|pront\w*|finit\w*))|"
                      r"(carica\w*|upload\w*|pubblica\w*|publish\w*).{0,40}(su|in|on|to) " + _PLATFORM + "|"
                      r"(salt\w*|senza|skip\w*|ignor\w*|elimin\w*|togli\w*)\W+(\w+\W+){0,2}(g1|g2|g3|gate)\b|"
                      r"\b(g1|g2|g3|gate)\b.{0,40}(non serve|si può saltare|si salta|superflu\w*|inutil\w*|facoltativ\w*|"
                      r"opzional\w*)|deleg\w*.{0,40}\b(g1|g2|g3|gate)\b|\b(g1|g2|g3|gate)\b.{0,40}deleg\w*", re.I)),
    ("H7", re.compile(r"bord\w* dritt\w*.{0,30}(ammess|va bene|accettabil|ok|tollerat)|"
                      r"(ammess|va bene|accettabil|tollerat)\w*.{0,30}bord\w* dritt\w*", re.I)),
    # verbo e oggetto vicini (al più due parole in mezzo): «togli una parola per passare il controllo» resta lecita
    ("H8", re.compile(r"(allent\w*|abbass\w*|rilass\w*|loosen\w*|lower\w*|declass\w*|ignor\w*|disattiv\w*|spegn\w*|"
                      r"togli\w*|rimuov\w*|salt\w*|skip\w*)\W+(\w+\W+){0,2}(soglia|soglie|threshold|errore|errori|"
                      r"controll\w*|check|\bqa\b)|(soglia|soglie|threshold|controll\w*|check)\b.{0,40}"
                      r"(si può abbassare|si possono abbassare|più bass\w*|più permissiv\w*|più largh\w*|allentat\w*|"
                      r"abbassat\w*|declassat\w*)|(errore|errori|error)\W+(\w+\W+){0,3}(diventa\w*|declassat\w*|come|in|a)\W+"
                      r"(warning|avviso|avvisi)", re.I)),
]
_NEGATION_BEFORE = re.compile(r"\b(non|mai|niente|nessun\w*|vietat\w*|never|no|evita\w*)\W+(\w+\W+){0,2}$", re.I)

# File del plugin che una proposta non tocca mai, e sezioni protette (regole dure) dentro i file ammessi.
# Codice del toolkit: solo i file dove vivono le soglie (07 §12.4, §13) e i pesi dello scorer degli Shorts (08 §4.2),
# come dice la tabella di 13 §1.3. Il resto del codice si cambia con una PR normale, mai con una proposta appresa.
# I profili canale, i glossari e i brand vivono nei channels_dirs e brands_dirs dell'operatore, mai nel plugin: nessuna
# proposta li tocca (le lezioni sui default del profilo diventano un suggerimento locale, yt-thumb-learn proposals).
ALLOWED_TARGET_PREFIXES = ("docs/yt/knowledge/", "docs/yt/templates/", "commands/", "agents/producer.md",
                           "scripts/yt/node/templates/", "scripts/yt/lib/thumb_qa.py", "scripts/yt/lib/thumb_render.py",
                           "scripts/yt/lib/clips.py", "evals/", "docs/yt/DESIGN.md", "docs/yt/README.md")
# Il sistema di apprendimento (motori, configurazione, schema, procedura /youtube:learn) non si cambia da solo.
FORBIDDEN_TARGETS = ("hooks/", "scripts/yt/bin/", ".claude-plugin/", "scripts/yt/install.sh",
                     "scripts/yt/pyproject.toml", "scripts/yt/uv.lock", "docs/yt/knowledge/11-compliance-safety.md",
                     "scripts/yt/lib/learn.py", "scripts/yt/lib/thumb_learn.py", "scripts/yt/lib/ytcore.py",
                     "scripts/yt/lib/ytdb.py", "scripts/yt/lib/ytauth.py", "scripts/yt/lib/auth.py",
                     "scripts/yt/lib/config.py", "scripts/yt/lib/collect.py", "agents/thumb-cold-reader.md",
                     "commands/learn.md", "docs/yt/knowledge/13-learning-loop.md", "docs/yt/channels/",
                     ".codex-plugin/", "codex/", "scripts/codex/")   # versione Codex: generata o con hook congelati
HARD_SECTIONS: dict[str, list[str]] = {
    "agents/producer.md": [r"Regole\s+—\s+non negoziabili", r"^4\.1 I gate", r"Passo 5\s+—\s+Impara"],
    "commands/producer.md": [r"Passo 5\s+—\s+Proposte"],
    "commands/thumbnail.md": [r"^Identity and standard", r"^Props da testo"],
    "docs/yt/knowledge/07-thumbnails.md": [r"^11\.1 ", r"^11\.2 ", r"^17\. "],
    "docs/yt/knowledge/12-qa-gates.md": [r"^10\.3 "],
    "docs/yt/knowledge/13-learning-loop.md": [r"^2\. ", r"^2\.2 ", r"^9\.2 ", r"^12\. "],
}
HARD_YAML_KEYS = {"consent", "paid_services", "public_names", "banned", "banned_match", "banned_openers",
                  "banned_superlatives", "banned_cta", "banned_title_patterns", "copy_rules", "owner_ai_edits",
                  "ai_generation", "props_budget", "guest_style_default", "guest_style_allowed", "graphics_licence"}
THRESHOLD_TARGETS = ("scripts/yt/lib/thumb_qa.py", "scripts/yt/lib/thumb_render.py", "docs/yt/knowledge/12-qa-gates.md")

# Soglie note (07 §12.4, §13; 12 §4): direzione e valore del toolkit. Una soglia appresa può solo stringere.
KNOWN_THRESHOLDS: dict[str, tuple[str, float]] = {
    "face_size": ("min", 0.35), "phrase_line_h": ("min", 0.12), "keyword_line_h": ("min", 0.18),
    "duo_line_h": ("min", 0.20), "hook_words_max": ("max", 6), "hook_words_min": ("min", 3),
    "served_detail": ("min", 713), "edge_dL_dark": ("min", 25), "edge_dL_light": ("min", 20),
    "face_surround": ("min", 20), "display_upscale": ("max", 2.0), "skin_de00_mean": ("max", 2.5),
    "skin_de00_p95": ("max", 5.0),
}
LEVEL_RANK = {"info": 0, "warn": 1, "warning": 1, "error": 2}


class LearnError(Exception):
    pass


# ═══ Utilità ═════════════════════════════════════════════════════════════════
def now_iso() -> str:
    return ytdb.now_iso()


def today() -> str:
    return _dt.date.today().isoformat()


def settings() -> dict:
    """Parametri dell'apprendimento (config.LEARNING_DEFAULTS + config.yaml)."""
    import config as _cfg

    base = dict(_cfg.LEARNING_DEFAULTS)
    base.update(yc.LEARNING or {})
    return base


def canon(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)


def chash(obj: Any) -> str:
    return hashlib.sha256(canon(obj).encode()).hexdigest()[:16]


def jload(text: str | None, default: Any = None) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def check_slug(slug: str | None) -> str:
    if not slug or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", slug) or ".." in slug:
        raise LearnError(f"canale non valido: {slug!r}")
    return slug


def norm_focus(f: str | None) -> str | None:
    if not f:
        return None
    f = f.strip().lower().removeprefix("/").removeprefix("youtube:").removeprefix("yt:")
    f = FOCUS_ALIASES.get(f, f)
    if f not in FOCI:
        raise LearnError(f"skill o --focus sconosciuto: {f} (ammessi: {', '.join(FOCI)})")
    return f


def norm_skill(f: str | None) -> str | None:
    """Come norm_focus ma senza errori (per il registro dei job: ogni nome di skill o flusso va bene)."""
    try:
        return norm_focus(f)
    except LearnError:
        return (f or "").strip().lower() or None


def norm_feature(name: str) -> str:
    """thumb.lever → thumbnail.lever (i due prefissi sono equivalenti)."""
    head, _, tail = name.partition(".")
    return f"{FOCUS_ALIASES.get(head, head)}.{tail}" if tail else name


def split_list(values: Iterable[str] | str | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    out: list[str] = []
    for v in values:
        for p in re.split(r"[,\n]", str(v)):
            p = p.strip()
            if p and p not in out:
                out.append(p)
    return out


def learned_dir() -> Path:
    return yc.LEARNED


def proposals_dir() -> Path:
    return yc.DATA / "proposals"


def golden_dir() -> Path:
    return yc.DATA / "thumb-golden"


def refs_dir() -> Path:
    return yc.DATA / "refs"


def connect(db: str | Path | None = None) -> sqlite3.Connection:
    return ytdb.connect(db)


def pr_channels(st: dict | None = None) -> set[str]:
    """Canali le cui lezioni possono diventare PR (13 §1.2, §9.2): elencati in learning_pr_channels (default: nessuno)
    E con il profilo dell'operatore che dice `kind: own` e `share_lessons: true` (ytcore.shareable_channels). La regola
    si ricontrolla qui sul profilo (doppia chiave, fallisce chiuso): un cliente o un canale personale aggiunto per errore
    alla configurazione resta locale e i suoi nomi restano nel filtro di privacy."""
    st = st or settings()
    configured = st.get("pr_channels") or []
    if isinstance(configured, str):
        configured = split_list(configured)
    out: set[str] = set()
    for slug in yc.shareable_channels(configured):
        if slug in configured and channel_shares_lessons(slug):
            out.add(slug)
    return out


def channel_shares_lessons(channel: str) -> bool:
    """Il profilo del canale acconsente alle PR di apprendimento: `kind: own` e `share_lessons: true` (booleano vero,
    non una stringa). Profilo assente o illeggibile = no."""
    prof = _profile(channel)
    return prof.get("kind") == "own" and prof.get("share_lessons") is True


def plugin_root() -> Path:
    root = yc.PLUGIN_ROOT
    return Path(root) if root else yc.YT_HOME.parent.parent


# ═══ Statistica: Beta, intervalli, Elo, Thompson ═════════════════════════════
def _betacf(a: float, b: float, x: float) -> float:
    """Frazione continua dell'incomplete beta (Numerical Recipes, Lentz)."""
    tiny, eps = 1e-300, 3e-14
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c if abs(1.0 + aa / c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c if abs(1.0 + aa / c) > tiny else tiny
        de = d * c
        h *= de
        if abs(de - 1.0) < eps:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """I_x(a, b) regolarizzata."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbt) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbt) * _betacf(b, a, 1.0 - x) / b


def beta_quantile(a: float, b: float, q: float) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(70):
        mid = (lo + hi) / 2
        if betainc(a, b, mid) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def beta_mean(a: float, b: float) -> float:
    return a / (a + b)


@functools.lru_cache(maxsize=4096)
def interval80(a: float, b: float) -> tuple[float, float]:
    return beta_quantile(a, b, 0.10), beta_quantile(a, b, 0.90)


def confidence(n: int, a: float, b: float, signal: str = "scelte") -> str:
    """13 §3.3: < 5 job → bassa; 5–14 e larghezza 80 % ≤ 0.4 → media; ≥ 15 e ≤ 0.2 → alta.
    Gli esiti restano «bassa» sotto i 4 video confrontabili."""
    lo, hi = interval80(a, b)
    width = hi - lo
    if signal == "esiti" and n < 4:
        return "bassa"
    if n >= 15 and width <= 0.2:
        return "alta"
    if n >= 5 and width <= 0.4:
        return "media"
    return "bassa"


def elo_expected(ra: float, rb: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


def thompson_pick(arms: dict[str, tuple[float, float]], rng: random.Random) -> str | None:
    """Thompson: un θ ~ Beta(α, β) per braccio, vince il più alto."""
    best, best_v = None, -1.0
    for name in sorted(arms):
        a, b = arms[name]
        v = rng.betavariate(max(a, 1e-6), max(b, 1e-6))
        if v > best_v:
            best, best_v = name, v
    return best


# ═══ Canali: tipo e perimetro ═════════════════════════════════════════════════
_KIND_MEMO: dict[str, str] = {}


@functools.lru_cache(maxsize=64)
def _profile(channel: str) -> dict:
    """Profilo del canale (frontmatter), letto una volta per processo; {} se assente o illeggibile."""
    try:
        return yc.load_channel(channel) or {}
    except Exception:  # noqa: BLE001 — profilo assente: si lavora con i default
        return {}


CHANNEL_KINDS = ("own", "personal", "client")
OPERATOR_KINDS = ("own", "personal")      # canali dell'operatore: le uniche fonti di una lezione globale (13 §6.3)


def channel_kind(channel: str, conn: sqlite3.Connection | None = None) -> str:
    """own | personal | client (dal profilo; poi da yt.db channels.kind; ignoto = client, il perimetro più stretto)."""
    if channel in _KIND_MEMO:
        return _KIND_MEMO[channel]
    kind = _profile(channel).get("kind")
    if kind not in CHANNEL_KINDS and conn is not None:
        try:
            r = conn.execute("SELECT kind FROM channels WHERE slug=?", (channel,)).fetchone()
            kind = r[0] if r else None
        except sqlite3.Error:
            kind = None
    kind = kind if kind in CHANNEL_KINDS else "client"
    _KIND_MEMO[channel] = kind
    return kind


def profile_defaults(channel: str) -> dict[str, str]:
    """Bracci di default dal profilo (frontmatter thumbnails): prior con media 0,5 + default_bonus (13 §3.2)."""
    th = _profile(channel).get("thumbnails") or {}
    if not isinstance(th, dict):
        return {}
    ok = re.compile(r"^[A-Za-z0-9][\w.-]*$")
    out: dict[str, str] = {}
    lever = th.get("default_lever")
    if isinstance(lever, str) and ok.match(lever):
        out["thumbnail.lever"] = lever
    tpl = th.get("default_template")
    if isinstance(tpl, str) and ok.match(tpl):
        out["thumbnail.template"] = tpl
    gd = th.get("grade_default")
    g = (gd.get(tpl) or gd.get("others")) if isinstance(gd, dict) else gd
    if isinstance(g, str) and ok.match(g):
        out["thumbnail.grade"] = g
    gs = th.get("guest_style_default")
    if isinstance(gs, str) and ok.match(gs):
        out["thumbnail.guest_style"] = gs
    return out


def grade_for(channel: str, template: str | None) -> str | None:
    th = _profile(channel).get("thumbnails") or {}
    gd = th.get("grade_default") if isinstance(th, dict) else None
    if isinstance(gd, dict):
        return gd.get(template or "") or gd.get("others")
    return gd if isinstance(gd, str) else None


# Template thumbnail inclusi nel plugin (scripts/yt/node/templates/): la serie v2 guidata dai token del brand e il
# template generico. Un brand può sovrascriverli con i suoi <slug>-*.html nei brands_dirs (07 §8).
BUILTIN_TEMPLATES = ("duo", "ritratto", "scena", "prova", "generic")


def channel_brand(channel: str) -> str:
    """Slug del brand del canale: brand.slug del profilo, se c'è, altrimenti lo slug del canale (07 §8)."""
    b = _profile(channel).get("brand")
    slug = b.get("slug") if isinstance(b, dict) else None
    return str(slug) if isinstance(slug, str) and re.fullmatch(r"[A-Za-z0-9][\w.-]*", slug) else channel


def brand_accents(channel: str) -> list[str]:
    """Accenti ammessi: thumbnails.accents del profilo, altrimenti «accents» dei token del brand del canale."""
    th = _profile(channel).get("thumbnails")
    acc = th.get("accents") if isinstance(th, dict) else None
    if not isinstance(acc, list) or not acc:
        try:
            acc = yc.brand_tokens(channel_brand(channel)).get("accents")
        except (OSError, ValueError):
            acc = None
    return [str(a) for a in acc if isinstance(a, str) and a] if isinstance(acc, list) else []


def allowed_templates(channel: str) -> list[str]:
    """Template disponibili per il canale: quelli del suo brand (<brand>-*.html nei brands_dirs), poi quelli inclusi
    nel plugin che il brand non sovrascrive (un <brand>-duo prende il posto di duo)."""
    out: list[str] = []
    brand = channel_brand(channel)
    bd = yc.brand_dir(brand)
    if bd and (bd / "templates").is_dir():
        out += sorted(p.stem for p in (bd / "templates").glob(f"{brand}-*.html"))
    tdir = yc.NODE_DIR / "templates"
    for name in BUILTIN_TEMPLATES:
        if (tdir / f"{name}.html").exists() and f"{brand}-{name}" not in out:
            out.append(name)
    return out


# ═══ Eventi (append-only) ═════════════════════════════════════════════════════
@functools.lru_cache(maxsize=256)
def _project_video_key(workdir: str) -> str | None:
    try:
        proj = yc.read_json(Path(workdir) / "project.json")
    except (OSError, ValueError):
        return None
    vk = proj.get("video_key") if isinstance(proj, dict) else None
    return str(vk) if vk else None


def video_key_for(workdir: str | Path | None, fallback: str | None = None) -> str | None:
    """Chiave del video per contare n (video diversi): la cartella del workdir, oppure «video_key» del project.json
    quando più cartelle lavorano lo stesso episodio (giri di uno studio, rifacimenti): n non si gonfia."""
    if workdir:
        return _project_video_key(str(workdir)) or Path(str(workdir)).name
    return fallback


def add_event(conn: sqlite3.Connection, *, channel: str, kind: str, ref: str, data: dict,
              job_id: str | None = None, workdir: str | Path | None = None, skill: str | None = None,
              signal: str | None = None, operator: str | None = None, source: str = "cli",
              video_key: str | None = None) -> tuple[int, bool]:
    """Evento idempotente: stesso (canale, tipo, ref, contenuto) → nessun nuovo evento. Contenuto diverso con lo
    stesso ref → nuovo evento, e il precedente risulta superato (superseded_by). Ritorna (id, nuovo?)."""
    check_slug(channel)
    h = chash(data)
    row = conn.execute("SELECT id, retracted_at, superseded_by FROM learn_events WHERE channel=? AND kind=? AND ref=? "
                       "AND content_hash=?", (channel, kind, ref, h)).fetchone()
    if row and not row["retracted_at"] and not row["superseded_by"]:
        return int(row["id"]), False
    with conn:
        if row:   # ritrattato o superato da un'altra versione: torna come evento nuovo (la storia resta)
            conn.execute("UPDATE learn_events SET content_hash=content_hash || ':v' || id WHERE id=?", (row["id"],))
        cur = conn.execute(
            "INSERT INTO learn_events(channel, job_id, workdir, video_key, skill, kind, ref, content_hash, data_json,"
            " signal, operator, source, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (channel, job_id, str(workdir) if workdir else None, video_key or video_key_for(workdir, job_id), skill,
             kind, ref, h, canon(data), signal, operator, source, now_iso()))
        new_id = int(cur.lastrowid)
        conn.execute("UPDATE learn_events SET superseded_by=? WHERE channel=? AND kind=? AND ref=? AND id<>? "
                     "AND superseded_by IS NULL", (new_id, channel, kind, ref, new_id))
    return new_id, True


def live_events(conn: sqlite3.Connection, channel: str, kind: str | None = None,
                skill: str | None = None, workdir: str | None = None) -> list[dict]:
    sql = "SELECT * FROM learn_events WHERE channel=? AND retracted_at IS NULL AND superseded_by IS NULL"
    params: list[Any] = [channel]
    if kind:
        sql += " AND kind=?"
        params.append(kind)
    if skill:
        sql += " AND skill=?"
        params.append(skill)
    if workdir:
        sql += " AND workdir=?"
        params.append(str(workdir))
    sql += " ORDER BY id"
    out = []
    for r in conn.execute(sql, params):
        d = dict(r)
        d["data"] = jload(d.pop("data_json"), {})
        out.append(d)
    return out


def retract(conn: sqlite3.Connection, event_id: int, reason: str) -> dict:
    row = conn.execute("SELECT * FROM learn_events WHERE id=?", (event_id,)).fetchone()
    if not row:
        raise LearnError(f"evento {event_id} inesistente")
    if row["retracted_at"]:
        return {"event": event_id, "already": True, "channel": row["channel"]}
    with conn:
        conn.execute("UPDATE learn_events SET retracted_at=?, retract_reason=? WHERE id=?",
                     (now_iso(), reason, event_id))
    return {"event": event_id, "channel": row["channel"], "kind": row["kind"], "retracted": True}


# ═══ Job ═════════════════════════════════════════════════════════════════════
def plugin_commit() -> str | None:
    try:
        import config as _cfg
        return _cfg.plugin_version()
    except Exception:  # noqa: BLE001
        return None


def workdir_channel(workdir: Path) -> str:
    try:
        proj = yc.load_project(workdir)
    except (OSError, ValueError) as exc:
        raise LearnError(f"project.json illeggibile in {workdir}: {exc}") from exc
    ch = proj.get("channel")
    if not ch:
        raise LearnError(f"project.json senza «channel»: {workdir}")
    return check_slug(ch)


def resolve_wd(arg: str | Path) -> Path:
    try:
        return yc.resolve_workdir(arg)
    except FileNotFoundError as exc:
        raise LearnError(str(exc)) from exc


def new_job_id(channel: str, workdir: Path | None) -> str:
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    base = workdir.name if workdir else "canale"
    return f"{channel}:{base}:{stamp}"


def open_job(conn: sqlite3.Connection, channel: str, workdir: Path | None) -> dict | None:
    if workdir:
        r = conn.execute("SELECT * FROM learn_jobs WHERE workdir=? AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
                         (str(workdir),)).fetchone()
    else:
        r = conn.execute("SELECT * FROM learn_jobs WHERE channel=? AND workdir IS NULL AND ended_at IS NULL "
                         "ORDER BY started_at DESC LIMIT 1", (channel,)).fetchone()
    return dict(r) if r else None


def job_start(conn: sqlite3.Connection, channel: str, workdir: Path | None = None, skills: list[str] | None = None,
              job_id: str | None = None, operator: str | None = None, video_id: str | None = None) -> dict:
    check_slug(channel)
    if job_id:
        r = conn.execute("SELECT * FROM learn_jobs WHERE id=?", (job_id,)).fetchone()
        if r:
            return dict(r)
    else:
        cur = open_job(conn, channel, workdir)
        if cur:
            if skills:
                have = jload(cur.get("skills_json"), []) or []
                merged = list(dict.fromkeys(have + skills))
                with conn:
                    conn.execute("UPDATE learn_jobs SET skills_json=? WHERE id=?", (canon(merged), cur["id"]))
                cur["skills_json"] = canon(merged)
            return cur
    jid = job_id or new_job_id(channel, workdir)
    row = {"id": jid, "channel": channel, "workdir": str(workdir) if workdir else None,
           "skills_json": canon(skills or []), "status": "aperto", "operator": operator or yc.OPERATOR,
           "plugin_commit": plugin_commit(), "video_id": video_id, "started_at": now_iso()}
    with conn:
        ytdb.insert(conn, "learn_jobs", row)
    return dict(conn.execute("SELECT * FROM learn_jobs WHERE id=?", (jid,)).fetchone())


def job_end(conn: sqlite3.Connection, job_id: str, status: str, note: str | None = None,
            gates: dict | None = None, video_id: str | None = None, skills: list[str] | None = None) -> dict:
    r = conn.execute("SELECT * FROM learn_jobs WHERE id=?", (job_id,)).fetchone()
    if not r:
        raise LearnError(f"job {job_id} inesistente")
    fields: dict[str, Any] = {"status": status, "ended_at": now_iso()}
    if note:
        fields["note"] = note
    if gates is not None:
        fields["gates_json"] = canon(gates)
    if video_id:
        fields["video_id"] = video_id
    if skills:
        fields["skills_json"] = canon(list(dict.fromkeys((jload(r["skills_json"], []) or []) + skills)))
    with conn:
        conn.execute(f"UPDATE learn_jobs SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                     [*fields.values(), job_id])
    return dict(conn.execute("SELECT * FROM learn_jobs WHERE id=?", (job_id,)).fetchone())


def job_summary(conn: sqlite3.Connection, job_id: str) -> dict:
    counts = {r["kind"]: r["n"] for r in conn.execute(
        "SELECT kind, COUNT(*) AS n FROM learn_events WHERE job_id=? AND retracted_at IS NULL GROUP BY kind", (job_id,))}
    return counts


# ═══ Ingest: lettura degli artefatti del workdir ═════════════════════════════
def _read(path: Path) -> Any:
    try:
        return yc.read_json(path)
    except (OSError, ValueError):
        return None


def _concepts(data: Any) -> list[dict]:
    if isinstance(data, list):
        return [c for c in data if isinstance(c, dict)]
    if isinstance(data, dict):
        if isinstance(data.get("concepts"), list):
            return [c for c in data["concepts"] if isinstance(c, dict)]
        return [data]
    return []


def hook_family(hook: str | None, hook_form: str | None = None) -> str | None:
    """Forma del gancio (07 §5.3): domanda · numero · contro · ammissione · affermazione. Una sola definizione,
    quella di yt-thumb-learn, così item di yt-learn e record thumbnail usano gli stessi valori."""
    try:
        return _tl().hook_family(hook, hook_form)
    except Exception:  # noqa: BLE001 — ripiego senza il motore thumbnail
        if not hook:
            return None
        h = hook.replace("|", " ").strip()
        if hook_form == "contro" or re.match(r"^(non|mai|niente|nessun)\b", h, re.I):
            return "contro"
        if h.rstrip(" .!»\"").endswith("?"):
            return "domanda"
        if re.search(r"\d", h):
            return "numero"
        return "affermazione"


def hook_words_bucket(hook: str | None) -> str | None:
    """Parole del gancio a fasce (gli elisi contano due: «L'AGENDA» = 2), come yt-thumb-learn."""
    if not hook:
        return None
    try:
        tl = _tl()
        return tl.words_bucket(len(tl.hook_words(hook)))
    except Exception:  # noqa: BLE001
        words = [w for w in re.split(r"[\s|]+", re.sub(r"(\w)['’](\w)", r"\1 \2", hook.strip())) if re.search(r"\w", w)]
        n = len(words)
        return "<3" if n < 3 else ("6+" if n >= 6 else str(n))


def bucket(value: float | None, edges: list[float], labels: list[str]) -> str | None:
    if value is None:
        return None
    for edge, label in zip(edges, labels):
        if value < edge:
            return label
    return labels[-1]


def face_bucket(frac: float | None) -> str | None:
    return bucket(frac, [0.30, 0.35, 0.40, 0.45], ["<30", "30-35", "35-40", "40-45", "45+"])


def rows_bucket(frac: float | None) -> str | None:
    return bucket(frac, [0.12, 0.15, 0.18, 0.20], ["<12", "12-15", "15-18", "18-20", "20+"])


def concept_features(channel: str, c: dict) -> dict[str, str]:
    lever = c.get("lever")
    hook_form = c.get("hook_form")
    if lever == "contro":
        lever, hook_form = "claim", "contro"
    hook = c.get("hook") or c.get("text")
    plate = c.get("plate")
    plate_src = plate.get("source") if isinstance(plate, dict) else ("scene" if isinstance(plate, str) else "flat")
    people = c.get("people") or ([{"cutout": c["cutout"]}] if c.get("cutout") or c.get("frame") else [])
    template = c.get("template")
    f = {
        "thumbnail.lever": lever,
        "thumbnail.template": template,
        "thumbnail.grade": c.get("grade") or grade_for(channel, template),
        "thumbnail.guest_style": c.get("guest_style") or "none",
        "thumbnail.expression": c.get("expression_class"),
        "thumbnail.accent": c.get("accent"),
        "thumbnail.plate": plate_src,
        "thumbnail.hook_family": c.get("hook_family") or hook_family(hook, hook_form),
        "thumbnail.hook_words": hook_words_bucket(hook),
        "thumbnail.hook_font": c.get("hook_font") or "anton",
        "thumbnail.people": "duo" if len(people) >= 2 else ("solo" if people else "nessuno"),
        "thumbnail.circle_behind": c.get("circle_behind"),
    }
    return {k: str(v) for k, v in f.items() if v not in (None, "")}


def _sidecar_metrics(rj: dict) -> tuple[dict, dict]:
    """(feature dal render, metriche QA) da un sidecar .render.json o da una voce di render.json."""
    feats: dict[str, str] = {}
    v2 = rj.get("v2") or rj.get("checks_v2") or {}
    m = rj.get("metrics") or {}
    heroes = v2.get("heroes") or m.get("heroes") or []
    fracs = [h.get("face_frac") for h in heroes if isinstance(h, dict) and isinstance(h.get("face_frac"), (int, float))]
    face = max(fracs) if fracs else None
    rows = [r.get("frac") for r in v2.get("hook_rows") or [] if isinstance(r, dict) and isinstance(r.get("frac"), (int, float))]
    accent = (m.get("series") or {}).get("accent") or ((v2.get("accents") or [None])[0])   # metrics.series di _common.js
    if face_bucket(face):
        feats["thumbnail.face_pct"] = face_bucket(face)
    if rows:
        feats["thumbnail.rows_pct"] = rows_bucket(min(rows))
    if isinstance(accent, str) and accent:
        feats["thumbnail.accent"] = accent
    surround = [h.get("face_surround_dL") for h in heroes if isinstance(h, dict) and h.get("face_surround_dL") is not None]
    lap = [((h.get("served_720") or {}).get("lap")) for h in heroes if isinstance(h, dict)]
    metrics = {
        "ok": rj.get("ok"), "pass": rj.get("pass"),
        "errors": len(rj.get("errors") or []), "error_list": [str(e)[:160] for e in (rj.get("errors") or [])[:5]],
        "warnings": len(rj.get("warnings") or []),
        "face_frac": face, "hook_rows": rows or None,
        "face_surround_dL": min(surround) if surround else None,
        "served_lap": min([x for x in lap if isinstance(x, (int, float))], default=None),
        "silhouette_dL_246": v2.get("silhouette_dL_246"), "jpg_bytes": rj.get("jpg_bytes"),
        "spec_hash": rj.get("spec_hash"), "template": rj.get("template"),
    }
    return feats, {k: v for k, v in metrics.items() if v is not None}


def _qa_index(thumbs: Path) -> dict[str, dict]:
    """yt-thumb-qa: {stem del render: metriche + conteggio dei controlli per livello}."""
    out: dict[str, dict] = {}
    for p in sorted((thumbs / "qa").glob("*.json")) if (thumbs / "qa").is_dir() else []:
        data = _read(p)
        imgs = []
        if isinstance(data, dict):
            imgs = (data.get("outputs") or {}).get("images") or data.get("images") or []
        elif isinstance(data, list):
            imgs = data
        for im in imgs if isinstance(imgs, list) else []:
            if not isinstance(im, dict) or not im.get("file"):
                continue
            stem = Path(str(im["file"])).stem
            m = im.get("metrics") or {}
            levels: dict[str, int] = {}
            for ch in im.get("checks") or []:
                if isinstance(ch, dict) and ch.get("level"):
                    levels[ch["level"]] = levels.get(ch["level"], 0) + 1
            out[stem] = {k: m.get(k) for k in ("edge_dL_dark", "edge_dL_light", "text_contrast_168_min",
                                                  "colorfulness_360", "busy_cells_share", "edge_density_168")
                         if m.get(k) is not None}
            if levels:
                out[stem]["qa_levels"] = levels
            rc = im.get("render_checks") or {}
            if "pass" in rc:
                out[stem]["qa_render_pass"] = rc.get("pass")
    return out


def _cold_reads(thumbs: Path) -> dict[str, Any]:
    data = _read(thumbs / "cold" / "cold_reads.json")
    out: dict[str, Any] = {}
    if isinstance(data, dict) and not isinstance(data.get("reads"), list):
        for k, v in data.items():
            if isinstance(v, (int, float)):
                out[k] = v
            elif isinstance(v, dict) and "score" in v:
                out[k] = v["score"]
        return out
    reads = data.get("reads") if isinstance(data, dict) else data
    for r in reads or []:
        if isinstance(r, dict):
            key = r.get("id") or r.get("concept")
            if key is not None and "score" in r:
                out[str(key)] = r["score"]
    return out


def _ab_plan_arms(thumbs: Path) -> list[dict]:
    data = _read(thumbs / "ab_plan.json")
    arms = data.get("arms") if isinstance(data, dict) else data
    out = []
    for i, a in enumerate(arms or []):
        if not isinstance(a, dict):
            continue
        ref = a.get("render") or a.get("name") or a.get("id") or a.get("concept")
        f = a.get("file") or a.get("jpg") or a.get("png")
        if not ref and f:
            ref = Path(str(f)).stem
        if ref:
            out.append({"arm": a.get("arm") or chr(ord("A") + i), "ref": str(ref), "file": f})
    return out


def ingest_thumbnail(conn: sqlite3.Connection, channel: str, wd: Path, job_id: str) -> dict:
    thumbs = wd / "thumbs"
    res = {"concepts": 0, "renders": 0, "new": 0, "paired": 0}
    concepts = _concepts(_read(thumbs / "concepts.json"))
    cold = _cold_reads(thumbs)
    by_id: dict[str, dict] = {}
    for c in concepts:
        cid = str(c.get("id") or "")
        if not cid:
            continue
        feats = concept_features(channel, c)
        by_id[cid] = feats
        people = c.get("people") or []
        payload = {"hook": c.get("hook") or c.get("text"), "keyword": c.get("keyword") or c.get("highlight"),
                   "title_pair": c.get("title_pair"), "payoff_at": c.get("payoff_at"),
                   "hypothesis": c.get("hypothesis"), "variants": c.get("variants"),
                   "guests": [p.get("name") for p in people if isinstance(p, dict) and p.get("role") == "guest" and p.get("name")]}
        metrics = {"cold_read": cold.get(cid)} if cid in cold else {}
        _, new = add_event(conn, channel=channel, kind="item", ref=f"thumbnail:concept:{wd.name}:{cid}",
                           data={"key": cid, "level": "concept", "features": feats, "metrics": metrics,
                                 "payload": {k: v for k, v in payload.items() if v not in (None, [], "")}},
                           job_id=job_id, workdir=wd, skill="thumbnail", source="ingest")
        res["concepts"] += 1
        res["new"] += int(new)
    # render: sidecar per render (thumbs/renders/*.render.json), altrimenti render.json
    rdir = thumbs / "renders"
    entries: list[dict] = []
    if rdir.is_dir():
        for p in sorted(rdir.glob("*.render.json")):
            d = _read(p)
            if isinstance(d, dict):
                entries.append(d)
        if not entries:
            d = _read(rdir / "render.json") or _read(thumbs / "render.json")
            if isinstance(d, dict):
                entries = [e for e in ((d.get("outputs") or {}).get("renders") or []) if isinstance(e, dict)]
    qa = _qa_index(thumbs)
    for e in entries:
        name = str(e.get("name") or Path(str(e.get("png") or e.get("jpg") or "")).stem)
        if not name:
            continue
        cid = str(e.get("id") or name.split("_")[0])
        feats = dict(by_id.get(cid) or {})
        if e.get("template"):
            feats["thumbnail.template"] = str(e["template"])
        rfeats, metrics = _sidecar_metrics(e)
        feats.update(rfeats)
        mv = re.search(r"_v(\d+)$", name)
        if mv:
            feats["thumbnail.variant"] = f"v{mv.group(1)}"
        metrics.update(qa.get(name) or {})
        if cid in cold:
            metrics["cold_read"] = cold[cid]
        payload = {"png": e.get("png"), "jpg": e.get("jpg"), "concept": cid}
        _, new = add_event(conn, channel=channel, kind="item", ref=f"thumbnail:render:{wd.name}:{name}",
                           data={"key": name, "level": "render", "parent": cid, "features": feats,
                                 "metrics": metrics, "payload": {k: v for k, v in payload.items() if v}},
                           job_id=job_id, workdir=wd, skill="thumbnail", source="ingest")
        res["renders"] += 1
        res["new"] += int(new)
    # abbinamento della decisione G2 con le braccia scelte (thumbs/ab_plan.json)
    arms = _ab_plan_arms(thumbs)
    if arms:
        res["paired"] += pair_decisions(conn, channel, wd, "thumbnail", [a["ref"] for a in arms],
                                        source="thumbs/ab_plan.json", gate="G2")
    return res


def ingest_hook(conn: sqlite3.Connection, channel: str, wd: Path, job_id: str) -> dict:
    res = {"variants": 0, "new": 0, "paired": 0}
    co = _read(wd / "edit" / "cold_open.json")
    variants = co.get("variants") if isinstance(co, dict) else None
    for v in variants or []:
        if not isinstance(v, dict) or not v.get("id"):
            continue
        feats = {"hook.family": v.get("template"), "hook.template": v.get("template"),
                 "hook.clips": str(len(v.get("clips") or [])) if v.get("clips") is not None else None,
                 "hook.card": "si" if v.get("card") else "no",
                 "hook.duration": bucket(v.get("duration"), [20, 30, 40], ["<20", "20-30", "30-40", "40+"])
                 if isinstance(v.get("duration"), (int, float)) else None}
        feats = {k: str(x) for k, x in feats.items() if x}
        metrics = {"verdict": v.get("verdict"), "C": v.get("C"), "gates": v.get("gates"),
                   "recommended": (co.get("recommended") == v.get("id"))}
        _, new = add_event(conn, channel=channel, kind="item", ref=f"hook:variant:{wd.name}:{v['id']}",
                           data={"key": str(v["id"]), "level": "variant", "features": feats,
                                 "metrics": {k: x for k, x in metrics.items() if x is not None},
                                 "payload": {"name": v.get("name")}},
                           job_id=job_id, workdir=wd, skill="hook", source="ingest")
        res["variants"] += 1
        res["new"] += int(new)
    pend = _read(wd / "edit" / "hooks.pending.json")
    rows = pend if isinstance(pend, list) else (pend.get("rows") if isinstance(pend, dict) else None)
    for i, r in enumerate(rows or []):
        if not isinstance(r, dict) or not r.get("family"):
            continue
        key = "lab:" + str(r.get("id") or (r.get("text") or "").split(" ")[0] or i)
        _, new = add_event(conn, channel=channel, kind="item", ref=f"hook:lab:{wd.name}:{key}",
                           data={"key": key, "level": "lab", "features": {"hook.family": str(r["family"])},
                                 "metrics": {"score": r.get("score")}, "payload": {"text": r.get("text")}},
                           job_id=job_id, workdir=wd, skill="hook", source="ingest")
        res["new"] += int(new)
    # scelta dopo G1: righe di yt.db hooks con chosen = 1 per questo workdir («V3 …» → V3)
    try:
        chosen = [r["text"] for r in conn.execute("SELECT text FROM hooks WHERE workdir=? AND chosen=1", (str(wd),))]
    except sqlite3.Error:
        chosen = []
    keys = [m.group(1) for t in chosen if t for m in [re.match(r"^(V\d+)\b", t)] if m]
    if keys:
        res["paired"] += pair_decisions(conn, channel, wd, "hook", keys, source="yt.db hooks.chosen", gate="G1")
    return res


def _signal_of(why: str | None) -> str | None:
    m = re.search(r"segnale:\s*([^·|]+)", why or "")
    return m.group(1).strip().lower().replace(" ", "_") if m else None


def ingest_shorts(conn: sqlite3.Connection, channel: str, wd: Path, job_id: str) -> dict:
    res = {"candidates": 0, "new": 0, "paired": 0}
    sc = _read(wd / "shorts" / "scores.json")
    items = sc if isinstance(sc, list) else (sc.get("windows") or sc.get("scores") or sc.get("candidates")
                                             if isinstance(sc, dict) else None)
    clips = _read(wd / "shorts" / "clips.json")
    clist = clips if isinstance(clips, list) else (clips.get("clips") if isinstance(clips, dict) else None) or []
    # le clip di yt-clips si chiamano short_NN e puntano alla finestra valutata (window: wNNN) di scores.json
    win_of = {str(c.get("id") or c.get("clip_id")): str(c["window"]) for c in clist
              if isinstance(c, dict) and c.get("window")}
    crop: dict[str, Any] = {}
    for c in clist:
        if isinstance(c, dict):
            cid = str(c.get("id") or c.get("clip_id"))
            crop[cid] = crop[win_of.get(cid, cid)] = c.get("crop")
    approved = [win_of.get(k, k) for k in (str(c.get("id") or c.get("clip_id")) for c in clist
                                          if isinstance(c, dict) and c.get("approved") is True)]
    for it in items or []:
        if not isinstance(it, dict):
            continue
        key = str(it.get("id") or it.get("clip_id") or it.get("window") or "")
        if not key:
            continue
        dur = None
        if isinstance(it.get("in"), (int, float)) and isinstance(it.get("out"), (int, float)):
            dur = it["out"] - it["in"]
        feats = {"shorts.signal": it.get("signal") or _signal_of(it.get("why")),
                 "shorts.band": bucket(dur, [30, 45, 60], ["<30", "30-45", "45-60", "60+"]),
                 "shorts.crop": crop.get(key)}
        feats = {k: str(v) for k, v in feats.items() if v}
        metrics = {k: it.get(k) for k in ("score", "hook", "payoff", "standalone", "emotion") if it.get(k) is not None}
        _, new = add_event(conn, channel=channel, kind="item", ref=f"shorts:candidate:{wd.name}:{key}",
                           data={"key": key, "level": "candidate", "features": feats, "metrics": metrics,
                                 "payload": {"hook_text": it.get("hook_text")}},
                           job_id=job_id, workdir=wd, skill="shorts", source="ingest")
        res["candidates"] += 1
        res["new"] += int(new)
    try:
        approved += [win_of.get(str(r["clip_id"]), str(r["clip_id"])) for r in conn.execute(
            "SELECT clip_id FROM clips_log WHERE workdir=? AND approved=1", (str(wd),)) if r["clip_id"]]
    except sqlite3.Error:
        pass
    if approved:
        res["paired"] += pair_decisions(conn, channel, wd, "shorts", list(dict.fromkeys(approved)),
                                        source="shorts/clips.json|clips_log", gate="G2")
    return res


def title_form(title: str) -> str:
    t = title.strip()
    if t.endswith("?"):
        return "domanda"
    if re.search(r"\d", t):
        return "numero"
    if re.search(r"\s[A-ZÀ-Ý][\wÀ-ÿ]+", t):
        return "nome"
    return "frase"


def ingest_chapters(conn: sqlite3.Connection, channel: str, wd: Path, job_id: str) -> dict:
    res = {"draft": 0, "corrections": 0, "new": 0}
    draft = _read(wd / "edit" / "chapters.draft.json")
    final = _read(wd / "deliver" / "chapters.json")
    dch = (draft or {}).get("chapters") if isinstance(draft, dict) else None
    fch = final.get("chapters") if isinstance(final, dict) else (final if isinstance(final, list) else None)
    for i, c in enumerate(dch or []):
        if isinstance(c, dict) and c.get("title"):
            _, new = add_event(conn, channel=channel, kind="item", ref=f"chapters:title:{wd.name}:{i}",
                               data={"key": str(i), "level": "title",
                                     "features": {"chapters.title_form": title_form(c["title"])},
                                     "metrics": {"chars": len(c["title"])}, "payload": {"title": c["title"]}},
                               job_id=job_id, workdir=wd, skill="chapters", source="ingest")
            res["draft"] += 1
            res["new"] += int(new)
    if dch and fch and len(dch) == len(fch):
        for i, (a, b) in enumerate(zip(dch, fch)):
            ta, tb = (a or {}).get("title"), (b or {}).get("title")
            if ta and tb and ta.strip() != tb.strip():
                _, new = add_event(conn, channel=channel, kind="correction", ref=f"chapter:{wd.name}:{i}",
                                   data={"kind": "chapter", "from": ta, "to": tb,
                                         "from_form": title_form(ta), "to_form": title_form(tb)},
                                   job_id=job_id, workdir=wd, skill="chapters", signal="scelte", source="ingest")
                res["corrections"] += 1
                res["new"] += int(new)
    return res


UNRESOLVED_RX = re.compile(r"[?|]")
UNIT_RX = re.compile(r"\b(MRR|ARR|MRAR|emarar)\b", re.I)
_EDGE_PUNCT = " \t.,;:!?«»\"“”()[]…"
# termini troppo generici per fare da contesto a un'entità (come glossary.py: generic)
GENERIC_CONTEXT = {"arr", "mrr", "saas", "micro-saas", "mvp", "ai", "ia", "italia", "roma", "linkedin", "twitter", "github",
                   "spotify", "notion", "stripe", "churn", "mau", "open source", "side project", "early adopter"}


def strip_edges(text: str | None) -> str:
    return (text or "").strip(_EDGE_PUNCT)


def _entity_terms(channel: str, workdir: Path | None = None) -> list[str]:
    """Entità note per il contesto: glossario del canale (profilo + appreso), termini e persone del progetto."""
    terms: list[str] = []
    try:
        terms += yc.glossary_terms(channel, learned=True)
    except (OSError, ValueError, TypeError):
        pass
    if workdir:
        try:
            proj = yc.load_project(workdir) or {}
        except (OSError, ValueError):
            proj = {}
        terms += [t for t in proj.get("glossary_extra") or [] if isinstance(t, str)]
        terms += [v for v in (proj.get("speakers") or {}).values() if isinstance(v, str)]
    out = []
    for t in terms:
        t = t.strip()
        # solo entità (nomi propri, prodotti, domini): il gergo minuscolo («bootstrapped») non fa da contesto
        if len(t) >= 4 and t.casefold() not in GENERIC_CONTEXT and (t[:1].isupper() or "." in t) and t not in out:
            out.append(t)
    return out


def context_terms(channel: str, before: str, after: str, context: str | None, workdir: Path | None,
                  window: int = 60, limit: int = 12) -> list[str]:
    """Entità che compaiono vicino alla parola corretta (nel contesto dato e, se c'è, nel transcript del workdir,
    ±window parole attorno a ogni occorrenza della forma sbagliata o di quella giusta). Diventano le parole di
    contesto della confusione appresa: yt-postcorrect corregge una forma ambigua solo se una di queste è vicina."""
    b, a = strip_edges(before).casefold(), strip_edges(after).casefold()
    texts = [context or ""]
    if workdir:
        doc = _read(Path(workdir) / "analysis" / "transcript.words.json")
        words = [str(w.get("w") or "") for w in (doc or {}).get("words", []) if isinstance(w, dict)] \
            if isinstance(doc, dict) else []
        cores = [strip_edges(w).casefold() for w in words]
        forms = [[strip_edges(x).casefold() for x in f.split()] for f in {b, a} if f]   # anche forme di più parole
        for i in range(len(cores)):
            for toks in forms:
                if toks and cores[i:i + len(toks)] == toks:
                    texts.append(" ".join(words[max(0, i - window): i + len(toks) + window]))
                    break
    texts = [t for t in texts if t.strip()]
    if not texts:
        return []
    found: dict[str, int] = {}
    for t in _entity_terms(channel, workdir):
        k = t.casefold()
        if k in (a, b) or a in k.split() or b in k.split():
            continue                      # il termine stesso (o la persona di cui è il nome) non è contesto
        pat = re.compile(rf"(?<!\w){re.escape(t)}(?!\w)", re.I)
        n = sum(1 for x in texts if pat.search(x))        # in quante occorrenze (finestre) compare
        if n:
            found[t] = n
    if not found:
        return []
    # solo le entità che accompagnano davvero la parola: almeno metà delle occorrenze del termine più frequente
    top = max(found.values())
    keep = {t: n for t, n in found.items() if n >= max(1, math.ceil(top / 2))}
    return [t for t, _ in sorted(keep.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


def ingest_transcript(conn: sqlite3.Connection, channel: str, wd: Path, job_id: str) -> dict:
    """SUSPECT accettati con prova (corrections.decisions.json + postcorrect.candidates.json) → correzioni."""
    res = {"corrections": 0, "new": 0}
    dec = _read(wd / "analysis" / "corrections.decisions.json")
    cands = _read(wd / "analysis" / "postcorrect.candidates.json")
    cmap = {c.get("id"): c for c in (cands or {}).get("candidates", []) if isinstance(c, dict)} if isinstance(cands, dict) else {}
    for d in (dec or {}).get("decisions", []) if isinstance(dec, dict) else []:
        if not isinstance(d, dict) or d.get("accept") is not True or not d.get("evidence"):
            continue
        c = cmap.get(d.get("id")) or {}
        src, dst = c.get("from"), c.get("to")
        if not src or not dst or src == dst or UNRESOLVED_RX.search(dst) or UNIT_RX.search(f"{src} {dst}"):
            continue                          # unità e forme non risolte: mai una correzione appresa (H9)
        data = {"kind": "transcript", "from": src, "to": dst, "context": str(d.get("evidence"))[:200],
                "origin": "postcorrect-review", "entity": c.get("entity")}
        ctx_terms = context_terms(channel, src, dst, f"{c.get('context') or ''} {d.get('evidence') or ''}", wd)
        if ctx_terms:
            data["context_terms"] = ctx_terms
        _, new = add_event(conn, channel=channel, kind="correction", ref=f"transcript:{wd.name}:{d['id']}",
                           data=data, job_id=job_id, workdir=wd, skill="transcript", signal="scelte", source="ingest")
        res["corrections"] += 1
        res["new"] += int(new)
    return res


def ingest_edit(conn: sqlite3.Connection, channel: str, wd: Path, job_id: str) -> dict:
    """EDL proposta contro EDL finale: un riepilogo (segmenti, secondi ripristinati/tolti). Niente priori da qui."""
    prop = _read(wd / "edit" / "edl.proposed.json")
    fin = _read(wd / "edit" / "edl.json")
    if not isinstance(prop, dict) or not isinstance(fin, dict):
        return {"summary": False}

    def total(e: dict) -> float:
        return sum(max(0.0, float(s.get("out", 0)) - float(s.get("in", 0)))
                   for s in e.get("segments") or [] if isinstance(s, dict))

    data = {"kind": "edit_diff", "proposed_segments": len(prop.get("segments") or []),
            "final_segments": len(fin.get("segments") or []),
            "proposed_s": round(total(prop), 2), "final_s": round(total(fin), 2)}
    data["delta_s"] = round(data["final_s"] - data["proposed_s"], 2)
    _, new = add_event(conn, channel=channel, kind="qa", ref=f"edit:diff:{wd.name}", data=data, job_id=job_id,
                       workdir=wd, skill="edit", source="ingest")
    return {"summary": True, "new": int(new), **data}


INGESTERS = {"thumbnail": ingest_thumbnail, "hook": ingest_hook, "shorts": ingest_shorts,
             "chapters": ingest_chapters, "transcript": ingest_transcript, "edit": ingest_edit}


def ingest(conn: sqlite3.Connection, workdir: Path, skills: list[str] | None = None) -> dict:
    channel = workdir_channel(workdir)
    raw = [s.strip().lower() for s in skills or [] if s and s.strip()]
    skills = list(INGESTERS) if not raw or "all" in raw or "tutto" in raw else [norm_skill(s) for s in raw]
    job = job_start(conn, channel, workdir, [s for s in skills if s])
    out = {"channel": channel, "workdir": str(workdir), "job": job["id"], "skills": {}}
    for s in skills:
        fn = INGESTERS.get(s or "")
        if not fn:
            out["skills"][s] = {"skipped": "nessun artefatto da leggere per questa skill"}
            continue
        try:
            out["skills"][s] = fn(conn, channel, workdir, job["id"])
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            out["skills"][s] = {"error": f"{type(exc).__name__}: {exc}"}
    if "thumbnail" in skills and isinstance(out["skills"].get("thumbnail"), dict):
        # lo stesso workdir nel motore thumbnail (record per concept e render, preferenze G2, priori): un solo
        # comando al Passo 5 copre le due viste; yt-thumb-learn learn resta idempotente se l'agente lo rilancia
        try:
            tl = _tl()
            tl.ensure_schema(conn)
            ing = tl.ingest_workdir(conn, workdir, channel, job["id"])
            out["skills"]["thumbnail"]["thumb_learn"] = {
                **{k: ing.get(k) for k in ("concepts", "renders", "sketches", "qa", "cold") if ing.get(k) is not None},
                "warnings": ing.get("warnings") or [], **thumb_sync(conn, channel, workdir)}
        except Exception as exc:  # noqa: BLE001 — il motore thumbnail non blocca mai yt-learn
            out["skills"]["thumbnail"]["thumb_learn"] = {"error": f"{type(exc).__name__}: {exc}"}
    return out


# ═══ Decisioni ai gate ═══════════════════════════════════════════════════════
def items_for(conn: sqlite3.Connection, channel: str, workdir: str | None, skill: str | None = None) -> dict[str, dict]:
    """Ultima versione viva di ogni item del workdir: {key: evento}."""
    out: dict[str, dict] = {}
    for e in live_events(conn, channel, "item", skill, workdir):
        out[e["data"].get("key")] = e
    return out


def record_decision(conn: sqlite3.Connection, *, channel: str, workdir: Path | None, gate: str | None,
                    skill: str | None, offered: list[str], chosen: list[str], rejected: list[str],
                    reason: str | None, text: str | None, operator: str | None, delegated: bool,
                    hypothesis: str | None = None, job_id: str | None = None) -> dict:
    if not (text or chosen or rejected):
        raise LearnError("una decisione richiede --text (verbatim) oppure --chosen/--rejected")
    job = job_start(conn, channel, workdir) if not job_id else {"id": job_id}
    skill = norm_skill(skill) if skill else None
    rejected = rejected or [k for k in offered if k not in chosen]
    data = {"gate": gate, "skill": skill, "offered": offered, "chosen": chosen, "rejected": rejected,
            "reason": reason, "text": text, "delegated": bool(delegated), "hypothesis": hypothesis,
            "operator": operator}
    n = conn.execute("SELECT COUNT(*) FROM learn_events WHERE channel=? AND kind='decision' AND workdir IS ? "
                     "AND json_extract(data_json,'$.gate') IS ?", (channel, str(workdir) if workdir else None, gate)).fetchone()[0]
    ref = f"decision:{workdir.name if workdir else 'canale'}:{gate or 'nogate'}:{n + 1}"
    eid, _ = add_event(conn, channel=channel, kind="decision", ref=ref, data=data, job_id=job["id"], workdir=workdir,
                       skill=skill, signal=None if delegated else "scelte", operator=operator,
                       source="dispatcher" if not delegated else "agente")
    ev = conn.execute("SELECT * FROM learn_events WHERE id=?", (eid,)).fetchone()
    ch, rj, sk = resolve_choice(conn, channel, {**dict(ev), "data": data})
    return {"event": eid, "job": job["id"], "ref": ref, **data,
            "paired": {"skill": sk, "chosen": [e["data"].get("key") for e in ch],
                       "rejected": [e["data"].get("key") for e in rj],
                       "note": None if ch else "scelte non ancora abbinate a item registrati: le abbina «yt-learn ingest»"}}


def resolve_choice(conn: sqlite3.Connection, channel: str, d: dict) -> tuple[list[dict], list[dict], str | None]:
    """(item scelti, item scartati, skill) di una decisione. Senza --rejected/--offered gli scartati sono gli
    altri item dello stesso livello e della stessa skill già proposti nel workdir prima della decisione."""
    data = d["data"]
    pool = items_for(conn, channel, d["workdir"], data.get("skill"))
    chosen = [pool[k] for k in data.get("chosen") or [] if k in pool]
    if not chosen:
        return [], [], data.get("skill")
    rejected_keys = data.get("rejected") or []
    if not rejected_keys:
        level = chosen[0]["data"].get("level")
        skill = chosen[0]["skill"]
        first = {r[0]: r[1] for r in conn.execute(
            "SELECT ref, MIN(created_at) FROM learn_events WHERE channel=? AND kind='item' AND workdir IS ? GROUP BY ref",
            (channel, d["workdir"]))}
        ck = {e["data"].get("key") for e in chosen}
        rejected_keys = [k for k, e in pool.items() if k not in ck and e["skill"] == skill
                         and e["data"].get("level") == level and (first.get(e["ref"]) or "") <= d["created_at"]]
    rejected = [pool[k] for k in rejected_keys if k in pool]
    return chosen, rejected, chosen[0]["skill"]


def pair_decisions(conn: sqlite3.Connection, channel: str, wd: Path, skill: str, chosen_keys: list[str],
                   source: str, gate: str | None) -> int:
    """Abbina le decisioni verbatim del workdir alle scelte lette dagli artefatti (ab_plan.json, hooks.chosen,
    clip approvate): per ogni skill una decisione derivata (ref «<decisione>:<skill>»), la verbatim resta com'è.
    Se l'operatore ha nominato lui le scelte di questa skill (--chosen), vince la sua decisione."""
    items = items_for(conn, channel, str(wd), skill)
    keys = [k for k in chosen_keys if k in items]
    if not keys:
        return 0
    n = 0
    for d in live_events(conn, channel, "decision", None, str(wd)):
        data = d["data"]
        if data.get("paired_from") or (gate and data.get("gate") and data.get("gate") != gate):
            continue
        if data.get("rejected"):
            continue          # l'operatore ha già nominato cosa scarta: la decisione dice da sola cosa ha scelto (o niente)
        if any(k in items for k in data.get("chosen") or []):
            continue
        level = items[keys[0]]["data"].get("level")
        offered = [k for k in data.get("offered") or [] if k in items] or \
            [k for k, e in items.items() if e["data"].get("level") == level]
        derived = {"gate": data.get("gate") or gate, "skill": skill, "offered": offered, "chosen": keys,
                   "rejected": [k for k in offered if k not in keys], "reason": data.get("reason"),
                   "text": data.get("text"), "delegated": bool(data.get("delegated")), "operator": data.get("operator"),
                   "hypothesis": data.get("hypothesis"), "paired_from": d["id"], "paired_by": source}
        add_event(conn, channel=channel, kind="decision", ref=f"{d['ref']}:{skill}", data=derived, job_id=d["job_id"],
                  workdir=wd, skill=skill, signal=d["signal"], operator=d["operator"], source="ingest",
                  video_key=d.get("video_key"))
        n += 1
    return n


# ═══ Correzioni → glossario e confusioni appresi ═════════════════════════════
def record_correction(conn: sqlite3.Connection, *, channel: str, kind: str, before: str, after: str,
                      context: str | None = None, workdir: Path | None = None, job_id: str | None = None,
                      operator: str | None = None) -> dict:
    if kind not in CORRECTION_KINDS:
        raise LearnError(f"--kind {kind}: ammessi {', '.join(CORRECTION_KINDS)}")
    before, after = (before or "").strip(), (after or "").strip()
    if not after:
        raise LearnError("una correzione richiede --to (la versione giusta)")
    if kind == "transcript" and (UNRESOLVED_RX.search(after) or UNIT_RX.search(before + " " + after)):
        raise LearnError("correzione del transcript rifiutata: forma non risolta («?», «|») o unità MRR/ARR. Le unità "
                         "si risolvono solo ascoltando (analysis/resolutions.json), mai con una regola appresa (H9)")
    job = job_start(conn, channel, workdir) if not job_id else {"id": job_id}
    data = {"kind": kind, "from": before, "to": after, "context": (context or "")[:300] or None}
    if kind == "chapter" and before:
        data.update({"from_form": title_form(before), "to_form": title_form(after)})
    if kind == "transcript":
        ctx_terms = context_terms(channel, before, after, context, workdir)
        if ctx_terms:
            data["context_terms"] = ctx_terms
    ref = f"{kind}:{workdir.name if workdir else 'canale'}:{chash([before, after])}"
    skill = {"transcript": "transcript", "chapter": "chapters", "cut": "edit", "caption": "captions",
             "hook": "hook", "thumbnail": "thumbnail"}.get(kind)
    eid, new = add_event(conn, channel=channel, kind="correction", ref=ref, data=data, job_id=job["id"],
                         workdir=workdir, skill=skill, signal="scelte", operator=operator, source="cli")
    out = {"event": eid, "new": new, "job": job["id"], **data}
    if kind == "transcript":
        out["learned"] = rebuild_learned_glossary(conn, channel)
    return out


def _plugin_glossary_terms(channel: str) -> set[str]:
    """Termini già noti: glossario del canale (accanto al profilo) e termini della sua lista di confusioni («Claude»)."""
    try:
        terms = {t.casefold() for t in yc.glossary_terms(channel)}
    except (OSError, ValueError):
        terms = set()
    try:
        p = yc.channel_file(channel, ".confusions.json")
        data = yc.read_json(p) if p.exists() else {}
        terms |= {str(c.get("term", "")).casefold() for c in data.get("confusions") or [] if c.get("term")}
    except (OSError, ValueError):
        pass
    return terms


def _plugin_aliases(channel: str) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    try:
        p = yc.channel_file(channel, ".confusions.json")
        data = yc.read_json(p) if p.exists() else {}
    except (OSError, ValueError):
        data = {}
    for c in data.get("confusions") or []:
        for a in c.get("aliases") or []:
            out.add((str(c.get("term", "")).casefold(), str(a).casefold()))
    return out


def alias_is_ambiguous(alias: str) -> bool:
    """Una forma appresa si corregge da sola (alias non ambiguo) solo se non può essere una parola o un nome veri.
    Ambigua (serve una parola di contesto vicina, yt-postcorrect judge_ambiguous): minuscola, ≤ 3 lettere, più
    parole, oppure una parola che finisce in vocale (in italiano quasi ogni parola e nome di battesimo: «Marco»).
    «Glaidgrid», «Nimblix», «Tascorp» restano non ambigue. Precisione prima di tutto: il resto lo decide una PR."""
    a = alias.strip()
    return (a == a.lower() or len(a) <= 3 or " " in a or bool(re.search(r"[aeiouàèéìòù]$", a, re.I)))


def rebuild_learned_glossary(conn: sqlite3.Connection, channel: str) -> dict:
    """Rigenera <studio>/data/learned/<canale>.glossary.txt e .confusions.json dalle correzioni del transcript
    non ritrattate (gli eventi sono la fonte: una ritrattazione toglie il termine al prossimo update)."""
    corr = [e for e in live_events(conn, channel, "correction") if e["data"].get("kind") == "transcript"]
    plugin_terms = _plugin_glossary_terms(channel)
    plugin_alias = _plugin_aliases(channel)
    terms: dict[str, dict] = {}
    aliases: dict[tuple[str, str], dict] = {}
    for e in corr:
        to, fr = strip_edges(e["data"].get("to")), strip_edges(e["data"].get("from"))
        if not to or "#" in to or len(to) > 60 or UNRESOLVED_RX.search(to) or UNIT_RX.search(f"{fr} {to}"):
            continue
        t = terms.setdefault(to.casefold(), {"term": to, "events": [], "videos": set()})
        t["events"].append(e["id"])
        t["videos"].add(e.get("video_key") or e.get("job_id"))
        if fr and fr.casefold() != to.casefold() and len(fr) >= 3 and fr.casefold() not in plugin_terms \
                and (to.casefold(), fr.casefold()) not in plugin_alias:
            a = aliases.setdefault((to.casefold(), fr.casefold()), {"term": to, "alias": fr, "events": [], "videos": set(),
                                                                    "context": {}})
            a["events"].append(e["id"])
            a["videos"].add(e.get("video_key") or e.get("job_id"))
            for c in e["data"].get("context_terms") or []:
                a["context"][c] = a["context"].get(c, 0) + 1
    gl_path = yc.learned_file(channel, ".glossary.txt")
    cf_path = yc.learned_file(channel, ".confusions.json")
    new_terms = [t for k, t in sorted(terms.items()) if k not in plugin_terms]
    if not new_terms and not aliases and not gl_path.exists() and not cf_path.exists():
        return {"glossary": None, "terms": 0, "confusions": None, "aliases": 0}
    gl_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Glossario appreso del canale {channel} — generato da yt-learn dalle correzioni del transcript.",
             "# Non modificare a mano: si rigenera a ogni update; per togliere un termine: yt-learn retract <evento>.",
             "# Livello P3: entra nel prompt solo se l'episodio lo nomina. La promozione a P1/P2 passa da una PR.",
             "# ── P3 · appresi"]
    lines += [f"{t['term']}  # correzioni {', '.join('e' + str(i) for i in t['events'][:6])} · video {len(t['videos'])}"
              for t in new_terms]
    gl_path.write_text("\n".join(lines) + "\n")
    conf = []
    for (_, _), a in sorted(aliases.items()):
        conf.append({"term": a["term"], "aliases": [a["alias"]], "origin": "learned",
                     **({"ambiguous": [a["alias"]]} if alias_is_ambiguous(a["alias"]) else {}),
                     **({"context_words": [c for c, _ in sorted(a["context"].items(), key=lambda kv: (-kv[1], kv[0]))][:12]}
                        if a["context"] else {}),
                     "evidence": f"yt-learn: correzioni {', '.join('e' + str(i) for i in a['events'][:6])} "
                                 f"in {len(a['videos'])} video", "n_videos": len(a["videos"])})
    yc.write_json(cf_path, {"note": f"Confusioni ASR apprese per {channel} da yt-learn (generato, non modificare a "
                                    "mano). Fuse a runtime con quelle del profilo (ytcore.channel_confusions).",
                            "updated": max((str(e["created_at"])[:10] for e in corr), default=today()),
                            "confusions": conf})
    return {"glossary": str(gl_path), "terms": len(new_terms), "confusions": str(cf_path), "aliases": len(conf)}


# ═══ Priori ═══════════════════════════════════════════════════════════════════
def _age_weight(created_at: str | None) -> float:
    try:
        t = _dt.datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        return 1.0
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    return 0.5 if (_dt.datetime.now(_dt.timezone.utc) - t).days > OLD_DAYS else 1.0


def prior_ab(is_default: bool, st: dict | None = None) -> tuple[float, float]:
    """Prior del knowledge (13 §3.2): media 0,5 (0,5 + default_bonus per il valore di default del profilo o del
    knowledge), con un peso di prior_strength pseudo-osservazioni. Stessi parametri di yt-thumb-learn."""
    st = st or settings()
    strength = max(0.5, float(st.get("prior_strength", 4.0)))
    m0 = 0.5 + (float(st.get("default_bonus", 0.1)) if is_default else 0.0)
    m0 = min(max(m0, 0.05), 0.95)
    return strength * m0, strength * (1.0 - m0)


class PriorTable:
    """Accumula osservazioni per (feature, valore, segnale): Beta–Bernoulli + Elo con K basso."""

    def __init__(self, defaults: dict[str, str], k: float = ELO_K_MAX, st: dict | None = None):
        self.defaults = defaults
        self.k = min(float(k), ELO_K_MAX)
        self.st = st or settings()
        self.cells: dict[tuple[str, str, str], dict] = {}

    def cell(self, feature: str, value: str, signal: str) -> dict:
        key = (feature, value, signal)
        if key not in self.cells:
            is_def = self.defaults.get(feature) == value
            a0, b0 = prior_ab(is_def, self.st)
            self.cells[key] = {"alpha": a0, "beta": b0, "prior_a": a0, "prior_b": b0, "elo": ELO_START, "elo_n": 0,
                               "jobs": set(), "wins": 0.0, "losses": 0.0, "ties": 0.0, "events": [],
                               "is_default": is_def}
        return self.cells[key]

    def observe(self, feature: str, value: str, signal: str, outcome: float, weight: float, job: str | None,
                event: int | None) -> None:
        """outcome 1 = successo, 0 = insuccesso, 0.5 = pari (metà e metà)."""
        c = self.cell(feature, value, signal)
        c["alpha"] += weight * outcome
        c["beta"] += weight * (1.0 - outcome)
        if outcome >= 0.75:
            c["wins"] += weight
        elif outcome <= 0.25:
            c["losses"] += weight
        else:
            c["ties"] += weight
        if job:
            c["jobs"].add(job)
        if event is not None and event not in c["events"]:
            c["events"].append(event)

    def elo(self, feature: str, winners: list[str], losers: list[str], signal: str, weight: float,
            job: str | None, event: int | None, tie: bool = False) -> None:
        """Ogni valore si muove al massimo di K per decisione (K diviso per il numero di avversari)."""
        if not winners or not losers:
            return
        snap = {v: self.cell(feature, v, signal)["elo"] for v in set(winners) | set(losers)}
        for w in winners:
            for lo in losers:
                exp = elo_expected(snap[w], snap[lo])
                s = 0.5 if tie else 1.0
                cw, cl = self.cell(feature, w, signal), self.cell(feature, lo, signal)
                cw["elo"] += weight * self.k / len(losers) * (s - exp)
                cl["elo"] += weight * self.k / len(winners) * ((1.0 - s) - (1.0 - exp))
                for c in (cw, cl):
                    c["elo_n"] += 1
                    if job:
                        c["jobs"].add(job)
                    if event is not None and event not in c["events"]:
                        c["events"].append(event)


def _feature_split(items: list[dict], skip_prefixes: tuple[str, ...] = ()) -> dict[str, set[str]]:
    vals: dict[str, set[str]] = {}
    for it in items:
        for f, v in (it.get("features") or {}).items():
            if f in NOT_PRIOR or (skip_prefixes and f.startswith(skip_prefixes)):
                continue
            vals.setdefault(f, set()).add(str(v))
    return vals


def _apply_choice(pt: PriorTable, chosen: list[dict], rejected: list[dict], signal: str, weight: float,
                  job: str | None, event: int | None, tie: bool = False, skip_prefixes: tuple[str, ...] = ()) -> int:
    """Una scelta (o un A/B): per ogni feature che VARIA tra le opzioni, un'osservazione per valore distinto
    (scelto = successo, gli altri = insuccesso) + Elo a coppie. Le feature uguali in tutte le opzioni non dicono nulla.
    skip_prefixes: famiglie di feature che un altro motore possiede (thumbnail.* → yt-thumb-learn)."""
    if not chosen or not rejected:
        return 0
    allv = _feature_split(chosen + rejected, skip_prefixes)
    n = 0
    for f, values in allv.items():
        if len(values) < 2:
            continue
        win = sorted({str(it["features"][f]) for it in chosen if f in (it.get("features") or {})})
        lose = sorted({str(it["features"][f]) for it in rejected if f in (it.get("features") or {})} - set(win))
        if not win or not lose:
            continue
        for v in win:
            pt.observe(f, v, signal, 0.5 if tie else 1.0, weight, job, event)
        for v in lose:
            pt.observe(f, v, signal, 0.5 if tie else 0.0, weight, job, event)
        pt.elo(f, win, lose, signal, weight, job, event, tie=tie)
        n += 1
    return n


def outcome_score(verdict: str | None) -> tuple[float, float] | None:
    """(esito, peso relativo): una differenza dentro il rumore conta metà (13 §3.2); «non leggibile» nulla."""
    return {"sopra": (1.0, 1.0), "sopra (nel rumore)": (1.0, 0.5), "in linea": (0.5, 1.0),
            "sotto (nel rumore)": (0.0, 0.5), "sotto": (0.0, 1.0)}.get(verdict or "")


def compute_priors(conn: sqlite3.Connection, channel: str) -> tuple[PriorTable, dict]:
    """Priori di hook, Shorts, capitoli, montaggio… Le feature thumbnail.* le calcola yt-thumb-learn (DELEGATED):
    una sola fonte per i priori delle thumbnail (record per render, preferenze a coppie, CTR, A/B)."""
    st = settings()
    pt = PriorTable(profile_defaults(channel), st.get("elo_k", ELO_K_MAX), st)
    pref_w = float(st.get("pref_weight", 0.5))
    stats = {"decisions_used": 0, "decisions_delegated": 0, "corrections_used": 0, "outcomes_used": 0, "ab_used": 0}
    # scelte: decisioni dell'operatore (mai quelle su delega); la stessa scelta registrata due volte allo stesso
    # gate dello stesso workdir conta una volta sola
    seen: set[tuple] = set()
    for d in live_events(conn, channel, "decision"):
        data = d["data"]
        if data.get("delegated"):
            stats["decisions_delegated"] += 1
            continue
        ch_ev, rj_ev, _ = resolve_choice(conn, channel, d)
        if not ch_ev or not rj_ev:
            stats["decisions_no_choice"] = stats.get("decisions_no_choice", 0) + 1   # testo, policy, solo scarti
            continue
        sig = (d["workdir"], data.get("gate"), frozenset(e["ref"] for e in ch_ev), frozenset(e["ref"] for e in rj_ev))
        if sig in seen:
            stats.setdefault("decisions_duplicate", 0)
            stats["decisions_duplicate"] += 1
            continue
        seen.add(sig)
        ch = [e["data"] for e in ch_ev]
        rj = [e["data"] for e in rj_ev]
        w = pref_w * _age_weight(d["created_at"])
        if _apply_choice(pt, ch, rj, "scelte", w, d.get("video_key") or d["job_id"], d["id"],
                         skip_prefixes=DELEGATED_PREFIXES):
            stats["decisions_used"] += 1
        elif ch and rj and all(str(f).startswith(DELEGATED_PREFIXES)
                               for it in ch + rj for f in (it.get("features") or {})):
            stats["decisions_thumbnail"] = stats.get("decisions_thumbnail", 0) + 1   # le conta yt-thumb-learn
    # scelte: correzioni dei titoli dei capitoli (forma finale > forma della bozza)
    for e in live_events(conn, channel, "correction"):
        data = e["data"]
        if data.get("kind") == "chapter" and data.get("from_form") and data.get("to_form") \
                and data["from_form"] != data["to_form"]:
            vk = e.get("video_key") or e["job_id"]
            w = pref_w * _age_weight(e["created_at"])
            pt.observe("chapters.title_form", data["to_form"], "scelte", 1.0, w, vk, e["id"])
            pt.observe("chapters.title_form", data["from_form"], "scelte", 0.0, w, vk, e["id"])
            pt.elo("chapters.title_form", [data["to_form"]], [data["from_form"]], "scelte", w, vk, e["id"])
            stats["corrections_used"] += 1
    # esiti: verdetto del video (D+28, altrimenti D+7) sulle feature comuni alle braccia pubblicate;
    # A/B nativo: braccio vincente > perdenti (pari e inconcludente = pari, mai sconfitte)
    pubs = {r["video_id"]: dict(r) for r in conn.execute("SELECT * FROM learn_publications WHERE channel=?", (channel,))}
    outs: dict[str, dict[str, dict]] = {}
    for r in conn.execute("SELECT * FROM learn_outcomes WHERE channel=?", (channel,)):
        outs.setdefault(r["video_id"], {})[r["checkpoint"]] = dict(r)
    for vid, pub in pubs.items():
        arms = jload(pub.get("arms_json"), {}) or {}
        arm_items = [{"features": a.get("features") or {}} for a in arms.values() if isinstance(a, dict)]
        cps = outs.get(vid, {})
        o = cps.get("d28") or cps.get("d7")
        if o and arm_items:
            sc = outcome_score(o.get("verdict"))
            if sc is not None:
                score, mult = sc
                w = float(st["outcome_weight_d28"] if o["checkpoint"] == "d28" else st["outcome_weight_d7"]) * mult
                w *= 0.5 if (jload(o.get("metrics_json"), {}) or {}).get("cross_boundary") else 1.0
                w *= _age_weight(o.get("created_at"))
                common = set.intersection(*[set(i["features"].items()) for i in arm_items])
                for f, v in sorted(common):
                    if f not in NOT_PRIOR and not f.startswith(DELEGATED_PREFIXES):
                        pt.observe(f, str(v), "esiti", score, w, vid, o.get("event_id"))
                stats["outcomes_used"] += 1
        ab = None
        for cp in ("d7", "d28"):
            ab = jload((cps.get(cp) or {}).get("ab_json"), None) or ab
        if ab and arm_items and ab.get("result") in ("winner", "same", "inconclusive"):
            res = ab.get("result")
            winner = str(ab.get("winner") or "")
            if res == "winner" and winner in arms:
                ch = [{"features": arms[winner].get("features") or {}}]
                rj = [{"features": a.get("features") or {}} for k, a in arms.items() if k != winner and isinstance(a, dict)]
                if _apply_choice(pt, ch, rj, "esiti", st["ab_weight"], vid, None, skip_prefixes=DELEGATED_PREFIXES):
                    stats["ab_used"] += 1
            elif res in ("same", "inconclusive") and len(arms) >= 2:
                ks = sorted(arms)
                ch = [{"features": arms[ks[0]].get("features") or {}}]
                rj = [{"features": arms[k].get("features") or {}} for k in ks[1:]]
                if _apply_choice(pt, ch, rj, "esiti", st["ab_weight"], vid, None, tie=True,
                                 skip_prefixes=DELEGATED_PREFIXES):
                    stats["ab_used"] += 1
    return pt, stats


def update_priors(conn: sqlite3.Connection, channel: str) -> dict:
    pt, stats = compute_priors(conn, channel)
    now = now_iso()
    with conn:
        conn.execute("DELETE FROM learn_priors WHERE channel=?", (channel,))
        for (f, v, s), c in pt.cells.items():
            conn.execute(
                "INSERT INTO learn_priors(channel, feature, value, signal, alpha, beta, elo, elo_n, n_jobs, n_obs, wins,"
                " losses, ties, is_default, evidence_json, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (channel, f, v, s, round(c["alpha"], 4), round(c["beta"], 4), round(c["elo"], 2), c["elo_n"],
                 len(c["jobs"]), round(c["alpha"] + c["beta"] - c["prior_a"] - c["prior_b"], 4), round(c["wins"], 3),
                 round(c["losses"], 3), round(c["ties"], 3), int(c["is_default"]), canon(c["events"][-20:]), now))
    return {"cells": len(pt.cells), **stats, "thumbnail": thumb_sync(conn, channel)}


# ═══ Thumbnail: la fonte dei priori è yt-thumb-learn (yt-learn legge) ═══════════
def _tl():
    import thumb_learn  # noqa: PLC0415 — import pigro: yt-learn funziona anche senza il motore thumbnail

    return thumb_learn


def thumb_sync(conn: sqlite3.Connection, channel: str, workdir: Path | None = None) -> dict:
    """Allinea yt-thumb-learn con yt-learn: decisioni G2 e pubblicazioni registrate qui, A/B e pre-test, priori.
    Idempotente e mai bloccante (un errore finisce nel risultato, non ferma yt-learn)."""
    try:
        tl = _tl()
        tl.ensure_schema(conn)
        return {"yt_learn": tl.sync_from_learn(conn, channel, workdir), "tests": tl.sync_tests(conn, channel),
                "priors": tl.rebuild_priors(conn, channel)}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"yt-thumb-learn: {type(exc).__name__}: {exc}"}


def thumb_prior_rows(conn: sqlite3.Connection, channel: str, feature: str | None = None) -> list[dict]:
    """Priori thumbnail di yt-thumb-learn nella forma delle righe di learn_priors (stessi nomi «thumbnail.*»)."""
    try:
        tl = _tl()
        tl.ensure_schema(conn)
        pri = tl.compute_priors(conn, channel)
        start = float(tl.THUMB.get("elo_start", ELO_START))
    except Exception:  # noqa: BLE001
        return []
    out = []
    for (sig, f, v), p in pri.items():
        feat = f"thumbnail.{f}"
        if feature and feat != feature:
            continue
        elo = p.get("elo")
        out.append({"channel": channel, "feature": feat, "value": str(v), "signal": sig,
                    "alpha": round(p["alpha"], 4), "beta": round(p["beta"], 4),
                    "elo": float(elo) if elo is not None else ELO_START,
                    "elo_n": int(elo is not None and abs(float(elo) - start) > 1e-9),
                    "n_jobs": int(p["n_jobs"]), "n_obs": round(p["wins"] + p["losses"], 4), "wins": round(p["wins"], 3),
                    "losses": round(p["losses"], 3), "ties": 0.0, "is_default": int(p["prior_mean"] > 0.5),
                    "n_decisive": p.get("n_decisive", 0), "mean": round(p["mean"], 3),
                    "ci80": [round(p["lo80"], 3), round(p["hi80"], 3)], "conf": p["confidence"],
                    "source": "yt-thumb-learn"})
    return sorted(out, key=lambda r: (r["feature"], r["signal"], r["value"]))


def _looks_like_concepts(cands: list[dict]) -> bool:
    return any(isinstance(c, dict) and not c.get("features") and (c.get("lever") or c.get("template") or c.get("hook"))
               for c in cands)


def prior_rows(conn: sqlite3.Connection, channel: str, focus: str | None = None,
               feature: str | None = None) -> list[dict]:
    """Righe dei priori del canale. thumbnail.* viene da yt-thumb-learn (fonte unica), il resto da learn_priors."""
    feature = norm_feature(feature) if feature else None
    if (feature and feature.startswith(DELEGATED_PREFIXES)) or focus == "thumbnail":
        return thumb_prior_rows(conn, channel, feature)
    sql = "SELECT * FROM learn_priors WHERE channel=?"
    params: list[Any] = [channel]
    if feature:
        sql += " AND feature=?"
        params.append(feature)
    elif focus:
        sql += " AND feature LIKE ?"
        params.append(f"{focus}.%")
    out = []
    for r in conn.execute(sql + " ORDER BY feature, signal, value", params):
        d = dict(r)
        if d["feature"].startswith(DELEGATED_PREFIXES):
            continue                      # righe vecchie (prima della delega): la fonte è yt-thumb-learn
        lo, hi = interval80(d["alpha"], d["beta"])
        d["mean"] = round(beta_mean(d["alpha"], d["beta"]), 3)
        d["ci80"] = [round(lo, 3), round(hi, 3)]
        d["conf"] = confidence(d["n_jobs"], d["alpha"], d["beta"], d["signal"])
        d.pop("evidence_json", None)
        out.append(d)
    if not focus and not feature:
        out += thumb_prior_rows(conn, channel)
    return out


def _prior_index(rows: list[dict]) -> dict[tuple[str, str, str], dict]:
    return {(r["feature"], r["value"], r["signal"]): r for r in rows}


def allowed_values(conn: sqlite3.Connection, channel: str, feature: str) -> list[str]:
    vals = list(KNOWN_ARMS.get(feature, []))
    if feature == "thumbnail.template":
        vals = allowed_templates(channel)
    elif feature == "thumbnail.accent":
        vals = brand_accents(channel) or vals
    for r in conn.execute("SELECT DISTINCT value FROM learn_priors WHERE channel=? AND feature=?", (channel, feature)):
        if r[0] not in vals and (feature != "thumbnail.template" or not vals or r[0] in vals):
            vals.append(r[0])
    d = profile_defaults(channel).get(feature)
    if d and d not in vals:
        vals.insert(0, d)
    return vals


def utility(idx: dict, defaults: dict[str, str], feature: str, value: str) -> tuple[float, str, dict | None]:
    """Valore per lo sfruttamento: esiti se la confidenza è almeno media, poi scelte; altrimenti il default del
    knowledge (13 §3.3: con confidenza bassa il priore informa ma non cambia il default)."""
    for sig in ("esiti", "scelte"):
        r = idx.get((feature, value, sig))
        if r and r["conf"] in ("media", "alta"):
            return r["mean"], sig, r
    r = idx.get((feature, value, "scelte")) or idx.get((feature, value, "esiti"))
    a0, b0 = prior_ab(defaults.get(feature) == value or bool((r or {}).get("is_default")))
    return a0 / (a0 + b0), "default", r


def posterior(idx: dict, defaults: dict[str, str], feature: str, value: str) -> tuple[float, float]:
    """Posteriore per l'esplorazione: esiti se ci sono, altrimenti scelte, altrimenti il prior."""
    for sig in ("esiti", "scelte"):
        r = idx.get((feature, value, sig))
        if r and r["n_jobs"] > 0:
            return r["alpha"], r["beta"]
    r = idx.get((feature, value, "scelte")) or idx.get((feature, value, "esiti"))
    return prior_ab(defaults.get(feature) == value or bool((r or {}).get("is_default")))


def evidence_label(r: dict | None, signal: str) -> str:
    """Etichetta di provenienza (13 §11): «[appreso: scelte|esiti, n=…, conf. …]»."""
    if r and r.get("n_jobs"):
        tail = ": informa, non cambia il default" if signal == "default" else ""
        return f"[appreso: {r['signal']}, n={r['n_jobs']}, conf. {r['conf']}{tail}]"
    return "[nessun dato: vale il default del knowledge]"


def suggest(conn: sqlite3.Connection, channel: str, focus: str, candidates: list[dict] | None = None,
            k: int = 3, explore: int | None = None, seed: int | None = None) -> dict:
    """Sfruttamento + esplorazione (13 §3.4). Senza candidati: per ogni feature il valore da sfruttare e quello
    da esplorare. Con candidati ({key, features}): k concept, gli ultimi `explore` scelti con Thompson."""
    st = settings()
    explore = int(st.get("explore_arms", 1) if explore is None else explore)
    if focus == "thumbnail" and candidates and _looks_like_concepts(candidates):
        return suggest_thumbnail(conn, channel, candidates, k, explore, seed)
    rng = random.Random(seed)
    rows = prior_rows(conn, channel, focus)
    idx = _prior_index(rows)
    defaults = profile_defaults(channel)
    if not candidates:
        feats = sorted({r["feature"] for r in rows} | {f for f in KNOWN_ARMS if f.startswith(focus + ".")}
                       | ({"thumbnail.template"} if focus == "thumbnail" else set()))
        out = {}
        for f in feats:
            vals = allowed_values(conn, channel, f)
            tpl_only = f == "thumbnail.template" and bool(vals)
            vals += [r["value"] for r in rows if r["feature"] == f and r["value"] not in vals
                     and (not tpl_only or r["n_jobs"] > 0)]
            if not vals:
                continue
            scored = sorted(((utility(idx, defaults, f, v), v) for v in vals), key=lambda t: (-t[0][0], t[1]))
            (u, sig, r), best = scored[0]
            if f in NO_EXPLORE and defaults.get(f) and best != defaults[f]:
                # volti e pixel dell'ospite (H1: guest_style graphic mai di default): il valore appreso resta informazione,
                # lo sfruttamento resta il default del profilo; cambiarlo è una proposta Tier B
                learned_best, learned_u = best, u
                best = defaults[f]
                u, sig, r = utility(idx, defaults, f, best)
                info = f"il valore appreso migliore sarebbe «{learned_best}» ({learned_u:.2f}): solo informativo (13 §3.4, H1)"
            else:
                info = None
            if sig == "default" and not defaults.get(f) and not (r and r.get("is_default")):
                entry = {"exploit": None, "mean": None, "signal": "default",
                         "evidence": "[nessun dato e nessun default del profilo: decide la skill con il knowledge]"}
                best = None
            else:
                entry = {"exploit": best, "mean": round(u, 3), "evidence": evidence_label(r, sig), "signal": sig}
                if info:
                    entry["note"] = info
            others = {v: posterior(idx, defaults, f, v) for v in vals if v != best}
            if f in NO_EXPLORE:
                entry["explore"] = None
                entry["explore_note"] = "mai esplorazione su volti e pixel dell'ospite (13 §3.4)"
            elif others:
                pick = thompson_pick(others, rng)
                pr = idx.get((f, pick, "scelte")) or idx.get((f, pick, "esiti"))
                entry["explore"] = pick
                entry["explore_note"] = f"poco provato: n={pr['n_jobs'] if pr else 0}"
            dis = disagreement(idx, f)
            if dis:
                entry["disagreement"] = dis
            out[f] = entry
        return {"channel": channel, "focus": focus, "features": out}
    # concept candidati
    cands = []
    for c in candidates:
        feats = {norm_feature(f): str(v) for f, v in (c.get("features") or {}).items() if v is not None}
        if not feats and focus == "thumbnail":
            feats = concept_features(channel, c)
        key = str(c.get("key") or c.get("id") or len(cands))
        us = [utility(idx, defaults, f, v)[0] for f, v in feats.items() if f not in NOT_PRIOR]
        cdef = dict(defaults)
        g = grade_for(channel, feats.get("thumbnail.template")) if focus == "thumbnail" else None
        if g:
            cdef["thumbnail.grade"] = g
        eligible = all(feats.get(f) in (None, cdef.get(f)) for f in NO_EXPLORE if cdef.get(f))
        cands.append({"key": key, "features": feats, "exploit_score": round(sum(us) / len(us), 4) if us else 0.5,
                      "explore_eligible": eligible})
    k = max(1, min(k, len(cands)))
    explore = max(1, min(explore, k - 1)) if k > 1 else 0      # sempre ≥ 1 esplorazione con ≥ 2 opzioni (13 §3.4)
    ranked = sorted(cands, key=lambda c: (-c["exploit_score"], c["key"]))
    slate = [{**c, "role": "sfruttamento"} for c in ranked[: k - explore]]
    rest = [c for c in ranked[k - explore:] if c["explore_eligible"]]
    for _ in range(explore):
        if not rest:
            break
        draws = {}
        for c in rest:
            th = [rng.betavariate(*posterior(idx, defaults, f, v)) for f, v in c["features"].items() if f not in NOT_PRIOR]
            draws[c["key"]] = sum(th) / len(th) if th else rng.random()
        pick = max(sorted(draws), key=lambda key: draws[key])
        c = next(x for x in rest if x["key"] == pick)
        rest.remove(c)
        slate.append({**c, "role": "esplorazione", "thompson": round(draws[pick], 4)})
    for c in slate:
        ev = {}
        for f, v in c["features"].items():
            if f in NOT_PRIOR:
                continue
            u, sig, r = utility(idx, defaults, f, v)
            ev[f] = {"value": v, "mean": round(u, 3), "evidence": evidence_label(r, sig)}
        c["evidence"] = ev
    return {"channel": channel, "focus": focus, "k": k, "explore": explore, "slate": slate}


def suggest_thumbnail(conn: sqlite3.Connection, channel: str, candidates: list[dict], k: int = 3,
                      explore: int | None = None, seed: int | None = None) -> dict:
    """Concept thumbnail candidati → yt-thumb-learn rank (stesso motore di /youtube:thumbnail Phase 1): 2 da sfruttare +
    1 da esplorare (Thompson), mai meno di 2 leve, i concept fuori regola esclusi (non corretti)."""
    tl = _tl()
    tl.ensure_schema(conn)
    res = tl.rank_concepts(conn, channel, candidates, seed=seed, keep=k, explore=explore)
    slate = [{"key": str(c["id"]), "role": c["ruolo"], "lever": c.get("lever"), "template": c.get("template"),
              "exploit_score": c["punteggio"].get(res["segnale"]), "scores": c["punteggio"],
              **({"thompson": c["estrazione"]} if c["ruolo"] == "esplorazione" else {}),
              "n": c["n"], "conf": c["confidenza"], "label": c["etichetta"], "why": c["motivo"],
              "evidence": c["evidenze"]} for c in res["selezionati"]]
    return {"channel": channel, "focus": "thumbnail", "engine": "yt-thumb-learn rank", "k": res["keep"],
            "explore": sum(1 for c in slate if c["role"] == "esplorazione"), "signal": res["segnale"], "slate": slate,
            "dropped": [str(c["id"]) for c in res["scartati"]], "excluded": res["esclusi"],
            "disagreement": res["disaccordo"], "note": res["nota"], "rules": res["regole"]}


def disagreement(idx: dict, feature: str) -> str | None:
    """Quando scelte ed esiti (entrambi almeno «media») indicano valori migliori diversi."""
    best = {}
    for sig in SIGNALS:
        cand = [(r["mean"], v) for (f, v, s), r in idx.items() if f == feature and s == sig and r["conf"] in ("media", "alta")]
        if cand:
            best[sig] = max(cand)[1]
    if len(best) == 2 and best["scelte"] != best["esiti"]:
        return f"l'operatore sceglie spesso «{best['scelte']}», ma negli esiti va meglio «{best['esiti']}»"
    return None


# ═══ Lezioni ═════════════════════════════════════════════════════════════════
def _loosened_threshold(text: str) -> str | None:
    """Una soglia nota nominata con un numero meno severo del toolkit («face_size minimo 0.30»): H8."""
    for name, (direction, base) in KNOWN_THRESHOLDS.items():
        for m in re.finditer(rf"\b{re.escape(name)}\b\D{{0,25}}?(\d+(?:[.,]\d+)?)", text, re.I):
            try:
                v = float(m.group(1).replace(",", "."))
            except ValueError:
                continue
            if (direction == "min" and v < base) or (direction == "max" and v > base):
                return name
    return None


def never_names() -> list[str]:
    """Nomi che i profili dell'operatore vietano (voice.public_names.never: un soprannome privato, un vecchio nome
    del canale…): una lezione o una proposta che li usa contrasta H6. Letti da ogni profilo nei channels_dirs."""
    out: list[str] = []
    for d in yc.CHANNELS_DIRS:
        for p in sorted(Path(d).glob("*.md")) if Path(d).is_dir() else []:
            if p.name.startswith("_"):
                continue
            try:
                voice = yc.load_channel(p.stem).get("voice")
            except Exception:  # noqa: BLE001 — profilo illeggibile: nessun nome
                continue
            pn = voice.get("public_names") if isinstance(voice, dict) else None
            never = pn.get("never") if isinstance(pn, dict) else None
            for n in never if isinstance(never, list) else []:
                if isinstance(n, str) and len(n.strip()) >= 2 and n.strip() not in out:
                    out.append(n.strip())
    return out


def hard_rule_hit(text: str) -> str | None:
    """Codice della regola dura che il testo contraddice (o None). Una negazione subito prima del punto in cui il
    match comincia lo rende un rispetto della regola («mai pubblicare da solo»)."""
    text = text or ""
    for code, pat in HARD_RULE_TEXT:
        for m in pat.finditer(text):
            if not _NEGATION_BEFORE.search(text[max(0, m.start() - 30):m.start()]):
                return code
    for name in never_names():                   # H6: i nomi che il profilo vieta (voice.public_names.never)
        for m in re.finditer(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.I):
            if not _NEGATION_BEFORE.search(text[max(0, m.start() - 30):m.start()]):
                return "H6"
    if _loosened_threshold(text):
        return "H8"
    return None


def lesson_key(text: str, skill: str | None) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (text or "").casefold())[:60].strip("-")
    return f"{skill or 'generale'}:{base}"


def _evidence_rows(conn: sqlite3.Connection, ids: list[int]) -> list[dict]:
    out = []
    for i in ids:
        r = conn.execute("SELECT id, channel, job_id, video_key, kind, retracted_at, data_json FROM learn_events WHERE id=?",
                         (i,)).fetchone()
        if not r:
            raise LearnError(f"evidenza e{i} inesistente")
        out.append(dict(r))
    return out


def parse_event_ids(values: Iterable[str] | str | None) -> list[int]:
    ids = []
    for v in split_list(values):
        m = re.fullmatch(r"e?(\d+)", v.strip())
        if not m:
            raise LearnError(f"id di evento non valido: {v} (forma: e12 oppure 12)")
        ids.append(int(m.group(1)))
    return ids


def _is_decisive(ev: dict) -> bool:
    data = jload(ev.get("data_json"), {}) or {}
    if ev["kind"] == "outcome":
        ab = data.get("ab") or {}
        return ab.get("result") == "winner" or data.get("verdict") in ("sopra", "sotto") and data.get("decisive")
    return bool(data.get("decisive"))


def lesson_state(lesson: dict, st: dict) -> str:
    if lesson["state"] in ("ritirata", "proposta"):
        return lesson["state"]
    ev = jload(lesson["evidence_json"], []) or []
    pro_videos = {e.get("video") for e in ev if e.get("kind") == "pro" and not e.get("retracted")}
    decisive = any(e.get("decisive") for e in ev if e.get("kind") == "pro" and not e.get("retracted"))
    n = len(pro_videos)
    # un esito decisivo vale decisive_weight lavori (13 §1.2): con i default (3 e 3) basta da solo
    n_eff = n + (max(1, int(st.get("decisive_weight", 3))) - 1 if decisive else 0)
    # «pronta per proposta» solo dove una PR è possibile (13 §1.2, §6.3): lezioni nate su un canale condivisibile
    # (in learning_pr_channels, con kind: own e share_lessons: true nel profilo). Clienti, canali personali e canali
    # propri non condivisi, anche con una lezione globale, si fermano ad «attiva» (Tier A, locali).
    shareable = lesson.get("channel") in pr_channels(st)     # anche una lezione globale: conta il canale d'origine
    if n_eff >= max(2, int(st["min_evidence"])) and shareable:
        return "pronta"
    if n >= 2:
        return "attiva"
    return "candidata"


def _lesson_counts(lesson: dict) -> tuple[int, int, bool]:
    ev = [e for e in jload(lesson["evidence_json"], []) or [] if not e.get("retracted")]
    return (len({e.get("video") for e in ev if e.get("kind") == "pro"}),
            len({e.get("video") for e in ev if e.get("kind") == "contra"}),
            any(e.get("decisive") for e in ev if e.get("kind") == "pro"))


def lesson_conf(n: int, contra: int) -> float:
    return round((n + 1) / (n + contra + 2) * (1 - math.exp(-n / 2.0)), 3)


def lesson_add(conn: sqlite3.Connection, *, channel: str, text: str, skill: str | None = None, scope: str = "channel",
               evidence: list[int] | None = None, key: str | None = None, signal: str | None = None,
               decisive: bool = False, contra: bool = False) -> dict:
    check_slug(channel)
    text = (text or "").strip()
    if not text:
        raise LearnError("una lezione richiede --text (una riga, in italiano)")
    if len(text) > 400:
        raise LearnError("lezione troppo lunga: una riga concreta (≤ 400 caratteri)")
    hit = hard_rule_hit(text)
    if hit:
        raise LearnError(f"lezione rifiutata: contrasta la regola dura {hit} ({dict(HARD_RULES)[hit]}). "
                         "Le regole dure non si imparano e non si disimparano (13 §2).")
    if scope not in ("channel", "global"):
        raise LearnError("--scope: channel | global")
    if scope == "global" and channel_kind(channel, conn) not in OPERATOR_KINDS:
        raise LearnError(f"lezione globale rifiutata: {channel} non è un canale proprio (le lezioni dei clienti "
                         "restano nel loro perimetro, 13 §6.3)")
    skill = norm_skill(skill) if skill else None
    ev_rows = _evidence_rows(conn, evidence or [])
    for e in ev_rows:
        if e["channel"] != channel:
            raise LearnError(f"evidenza e{e['id']} di un altro canale ({e['channel']}): i canali non si mescolano (H10)")
        if e["retracted_at"]:
            raise LearnError(f"evidenza e{e['id']} ritrattata")
    key = key or lesson_key(text, skill)
    st = settings()
    now = now_iso()
    row = conn.execute("SELECT * FROM learn_lessons WHERE scope=? AND channel=? AND key=?", (scope, channel, key)).fetchone()
    new_ev = [{"event": e["id"], "job": e["job_id"], "video": e["video_key"] or e["job_id"],
               "kind": "contra" if contra else "pro", "decisive": bool(decisive or _is_decisive(e)), "at": now}
              for e in ev_rows]
    if row:
        lesson = dict(row)
        ev = jload(lesson["evidence_json"], []) or []
        known = {(x.get("event"), x.get("kind")) for x in ev}
        ev += [x for x in new_ev if (x["event"], x["kind"]) not in known]
        lesson["evidence_json"] = canon(ev)
        if lesson["state"] == "ritirata" and not contra and new_ev:
            lesson["state"] = "candidata"     # riaperta da prove nuove: la storia resta
            lesson["retired_reason"] = None
    else:
        if not new_ev and not contra:
            new_ev = [{"event": None, "job": None, "video": f"manuale:{now}", "kind": "pro", "decisive": bool(decisive),
                       "at": now}]
        lesson = {"scope": scope, "channel": channel, "skill": skill, "key": key, "text": text, "state": "candidata",
                  "evidence_json": canon(new_ev), "signal": signal, "created_at": now}
    return _save_lesson(conn, lesson, st)


def _save_lesson(conn: sqlite3.Connection, lesson: dict, st: dict) -> dict:
    ev = jload(lesson["evidence_json"], []) or []
    if lesson["state"] != "ritirata":
        tail = [e["kind"] for e in ev if not e.get("retracted")][-2:]
        if tail == ["contra", "contra"]:
            lesson["state"] = "ritirata"
            lesson["retired_reason"] = "contraddetta due volte di fila"
        elif ev and any(e.get("event") for e in ev) and not any(
                e.get("kind") == "pro" and not e.get("retracted") for e in ev):
            # tutte le prove ritrattate (13 §10): niente residui nel playbook né proposte che ci si appoggiano
            lesson["state"] = "ritirata"
            lesson["retired_reason"] = "prove ritrattate"
    lesson["state"] = lesson_state(lesson, st)
    n, contra, decisive = _lesson_counts(lesson)
    lesson.update({"n_jobs": n, "n_contra": contra, "decisive": int(decisive), "confidence": lesson_conf(n, contra),
                   "updated_at": now_iso()})
    with conn:
        if lesson.get("id"):
            conn.execute("UPDATE learn_lessons SET text=?, state=?, evidence_json=?, n_jobs=?, n_contra=?, decisive=?, "
                         "confidence=?, retired_reason=?, updated_at=?, signal=COALESCE(?, signal) WHERE id=?",
                         (lesson["text"], lesson["state"], lesson["evidence_json"], n, contra, int(decisive),
                          lesson["confidence"], lesson.get("retired_reason"), lesson["updated_at"], lesson.get("signal"),
                          lesson["id"]))
        else:
            lesson["id"] = ytdb.insert(conn, "learn_lessons", lesson)
    return lesson_view(dict(conn.execute("SELECT * FROM learn_lessons WHERE id=?", (lesson["id"],)).fetchone()))


def lesson_view(r: dict) -> dict:
    ev = jload(r.get("evidence_json"), []) or []
    label = {"pronta": "pronta per proposta"}.get(r["state"], r["state"])
    return {"id": r["id"], "scope": r["scope"], "channel": r["channel"], "skill": r["skill"], "text": r["text"],
            "state": r["state"], "stato": label, "n": r["n_jobs"], "contra": r["n_contra"],
            "decisive": bool(r["decisive"]), "confidence": r["confidence"], "signal": r.get("signal"),
            "evidence": [f"e{e['event']}" for e in ev if e.get("event") and not e.get("retracted")][-12:],
            "proposal": r.get("proposal_id"), "retired_reason": r.get("retired_reason"), "key": r["key"]}


def lesson_get(conn: sqlite3.Connection, lesson_id: int) -> dict:
    r = conn.execute("SELECT * FROM learn_lessons WHERE id=?", (lesson_id,)).fetchone()
    if not r:
        raise LearnError(f"lezione {lesson_id} inesistente")
    return dict(r)


def lesson_evidence(conn: sqlite3.Connection, lesson_id: int, evidence: list[int], contra: bool,
                    decisive: bool = False) -> dict:
    lesson = lesson_get(conn, lesson_id)
    if lesson["state"] == "ritirata" and not contra:
        lesson["state"] = "candidata"
        lesson["retired_reason"] = None
    ev = jload(lesson["evidence_json"], []) or []
    now = now_iso()
    rows = _evidence_rows(conn, evidence)
    if not rows:
        raise LearnError("servono gli id delle prove (--evidence e12)")
    for e in rows:
        if e["channel"] != lesson["channel"] and lesson["scope"] == "channel":
            raise LearnError(f"evidenza e{e['id']} di un altro canale ({e['channel']}): i canali non si mescolano (H10)")
        if lesson["scope"] == "global" and channel_kind(e["channel"], conn) not in OPERATOR_KINDS:
            raise LearnError(f"una lezione globale accetta prove solo da canali propri (e{e['id']}: {e['channel']})")
        ev.append({"event": e["id"], "job": e["job_id"], "video": e["video_key"] or e["job_id"],
                   "kind": "contra" if contra else "pro", "decisive": bool(decisive or _is_decisive(e)), "at": now})
    lesson["evidence_json"] = canon(ev)
    return _save_lesson(conn, lesson, settings())


def lesson_retire(conn: sqlite3.Connection, lesson_id: int, reason: str) -> dict:
    """Ritiro immediato (13 §10): la lezione smette di valere, le soglie che ha impostato decadono, le proposte in
    attesa che si reggono su di lei vengono ritirate (niente PR), e la CLI rigenera subito il playbook."""
    if not reason:
        raise LearnError("ritirare una lezione richiede --reason")
    lv = lesson_get(conn, lesson_id)          # LearnError se non esiste
    with conn:
        conn.execute("UPDATE learn_lessons SET state='ritirata', retired_reason=?, updated_at=? WHERE id=?",
                     (reason, now_iso(), lesson_id))
        conn.execute("UPDATE learn_thresholds SET retired_at=? WHERE lesson_id=? AND retired_at IS NULL",
                     (now_iso(), lesson_id))
    write_thresholds_file(conn, lv["channel"])
    out = lesson_view(lesson_get(conn, lesson_id))
    out["proposals_withdrawn"] = withdraw_stale_proposals(conn)
    open_prs = [p for p in proposals_list(conn, "in_pr") if lesson_id in (p.get("lessons") or [])]
    if open_prs:
        out["open_prs"] = [{"id": p["id"], "pr": p.get("pr_url"),
                            "note": "PR già aperta: chiudila su GitHub (o commenta perché è sbagliata)"} for p in open_prs]
    return out


def lessons_list(conn: sqlite3.Connection, channel: str | None = None, state: str | None = None,
                 skill: str | None = None, include_global: bool = True) -> list[dict]:
    sql = "SELECT * FROM learn_lessons WHERE 1=1"
    params: list[Any] = []
    if channel:
        if include_global:
            sql += " AND (channel=? OR scope='global')"
        else:
            sql += " AND channel=?"
        params.append(channel)
    if state:
        sql += " AND state=?"
        params.append(state)
    if skill:
        sql += " AND skill=?"
        params.append(norm_focus(skill))
    return [lesson_view(dict(r)) for r in conn.execute(sql + " ORDER BY state, confidence DESC, id", params)]


def refresh_lessons(conn: sqlite3.Connection, channel: str) -> dict:
    """Ricalcola stati e conteggi (le prove ritrattate non contano più)."""
    st = settings()
    retracted = {r[0] for r in conn.execute("SELECT id FROM learn_events WHERE channel=? AND retracted_at IS NOT NULL",
                                              (channel,))}
    counts: dict[str, int] = {}
    for r in conn.execute("SELECT * FROM learn_lessons WHERE channel=?", (channel,)).fetchall():
        lesson = dict(r)
        ev = jload(lesson["evidence_json"], []) or []
        for e in ev:
            e["retracted"] = e.get("event") in retracted
        lesson["evidence_json"] = canon(ev)
        out = _save_lesson(conn, lesson, st)
        counts[out["state"]] = counts.get(out["state"], 0) + 1
    return counts


# ═══ Soglie più severe (solo stringere) ══════════════════════════════════════
def threshold_set(conn: sqlite3.Connection, *, channel: str, name: str, direction: str | None, value: float,
                  baseline: float | None = None, level: str | None = None, lesson_id: int | None = None,
                  note: str | None = None) -> dict:
    check_slug(channel)
    known = KNOWN_THRESHOLDS.get(name)
    direction = direction or (known[0] if known else None)
    if direction not in ("min", "max"):
        raise LearnError("soglia: serve --min X oppure --max X")
    base = baseline if baseline is not None else (known[1] if known and known[0] == direction else None)
    if base is None:
        raise LearnError(f"soglia {name} sconosciuta: passa --baseline (il valore del toolkit) per poter verificare "
                         "che la nuova sia più severa")
    if known and known[0] == direction and base != known[1]:
        # una soglia nota si misura sempre contro il valore del toolkit: un --baseline più permissivo farebbe passare
        # per «più severa» una soglia che in realtà allenta (H8)
        looser = base < known[1] if direction == "min" else base > known[1]
        if looser:
            raise LearnError(f"soglia {name}: --baseline {base} è meno severo del valore del toolkit {known[1]} "
                             f"({direction}). Il riferimento è il toolkit (H8)")
    cur = conn.execute("SELECT * FROM learn_thresholds WHERE channel=? AND name=? AND retired_at IS NULL",
                       (channel, name)).fetchone()
    if cur and cur["direction"] != direction:
        # una riga per nome: cambiare direzione cancellerebbe il limite già appreso (un allentamento)
        raise LearnError(f"soglia {name}: c'è già un limite {cur['direction']} {cur['value']}; un limite "
                         f"{direction} va registrato con un altro --name (H8)")
    ref = [base] + ([cur["value"]] if cur else [])
    stricter = value >= max(ref) if direction == "min" else value <= min(ref)
    if not stricter:
        raise LearnError(f"soglia {name}: {value} non è più severa di {max(ref) if direction == 'min' else min(ref)} "
                         f"({direction}). Allentare una soglia richiede una PR con la decisione scritta "
                         "dell'operatore (Tier B, H8)")
    if cur and level and cur["level"] and LEVEL_RANK.get(level, 0) < LEVEL_RANK.get(cur["level"], 0):
        raise LearnError(f"soglia {name}: il livello {cur['level']} non può scendere a {level} (H8)")
    now = now_iso()
    with conn:
        conn.execute("INSERT INTO learn_thresholds(channel, name, direction, value, baseline, level, lesson_id, note, "
                     "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(channel, name) DO UPDATE SET "
                     "direction=excluded.direction, value=excluded.value, baseline=excluded.baseline, "
                     "level=COALESCE(excluded.level, learn_thresholds.level), lesson_id=COALESCE(excluded.lesson_id, "
                     "learn_thresholds.lesson_id), note=COALESCE(excluded.note, learn_thresholds.note), "
                     "updated_at=excluded.updated_at, retired_at=NULL",
                     (channel, name, direction, value, base, level, lesson_id, note, now, now))
    write_thresholds_file(conn, channel)
    return dict(conn.execute("SELECT * FROM learn_thresholds WHERE channel=? AND name=?", (channel, name)).fetchone())


def thresholds_list(conn: sqlite3.Connection, channel: str) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM learn_thresholds WHERE channel=? AND retired_at IS NULL "
                                          "ORDER BY name", (channel,))]


def write_thresholds_file(conn: sqlite3.Connection, channel: str) -> Path:
    p = yc.learned_file(channel, ".thresholds.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    yc.write_json(p, {"note": "Soglie apprese più severe (yt-learn, solo stringere: H8). Si applicano sopra quelle "
                              "del toolkit, mai al loro posto.", "updated": today(),
                      "thresholds": [{k: t[k] for k in ("name", "direction", "value", "baseline", "level", "lesson_id")}
                                     for t in thresholds_list(conn, channel)]})
    return p


# ═══ Pubblicazioni e golden set ══════════════════════════════════════════════
def publish(conn: sqlite3.Connection, *, channel: str, video_id: str, workdir: Path | None = None,
            arms: dict[str, str] | None = None, published_at: str | None = None, ab_test: int | None = None,
            kind: str = "long", golden: bool = True, note: str | None = None) -> dict:
    check_slug(channel)
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id or ""):
        raise LearnError(f"id video non valido: {video_id!r}")
    items = items_for(conn, channel, str(workdir), "thumbnail") if workdir else {}
    if not arms and workdir:
        arms = {a["arm"]: a["ref"] for a in _ab_plan_arms(workdir / "thumbs")}
    if workdir and arms and any(ref not in items for ref in arms.values()):
        ingest_thumbnail(conn, channel, workdir, None)        # render non ancora registrati: idempotente, senza job
        items = items_for(conn, channel, str(workdir), "thumbnail")
    if not arms and workdir:
        for d in reversed(live_events(conn, channel, "decision", None, str(workdir))):
            if d["data"].get("gate") == "G2" and d["data"].get("chosen") and d["data"].get("skill") in (None, "thumbnail") \
                    and all(k in items for k in d["data"]["chosen"]):
                arms = {chr(ord("A") + i): k for i, k in enumerate(d["data"]["chosen"])}
                break
    arms_out: dict[str, dict] = {}
    warnings: list[str] = []
    for arm, ref in (arms or {}).items():
        it = items.get(ref)
        if not it:
            warnings.append(f"braccio {arm}: «{ref}» non è tra gli item registrati (esegui prima yt-learn ingest)")
            arms_out[arm] = {"item": ref, "features": {}}
            continue
        d = it["data"]
        arms_out[arm] = {"item": ref, "event": it["id"], "features": d.get("features") or {},
                         "file": (d.get("payload") or {}).get("jpg") or (d.get("payload") or {}).get("png")}
    now = now_iso()
    with conn:
        conn.execute("INSERT INTO learn_publications(channel, video_id, job_id, workdir, kind, published_at, arms_json, "
                     "ab_test_id, note, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                     "ON CONFLICT(channel, video_id) DO UPDATE SET workdir=COALESCE(excluded.workdir, workdir), "
                     "kind=excluded.kind, published_at=COALESCE(excluded.published_at, published_at), "
                     "arms_json=CASE WHEN excluded.arms_json='{}' THEN arms_json ELSE excluded.arms_json END, "
                     "ab_test_id=COALESCE(excluded.ab_test_id, ab_test_id), note=COALESCE(excluded.note, note), "
                     "updated_at=excluded.updated_at",
                     (channel, video_id, None, str(workdir) if workdir else None, kind, published_at, canon(arms_out),
                      ab_test, note, now, now))
        if workdir:
            conn.execute("UPDATE learn_jobs SET video_id=? WHERE workdir=? AND video_id IS NULL", (video_id, str(workdir)))
    add_event(conn, channel=channel, kind="publication", ref=f"publication:{video_id}",
              data={"video_id": video_id, "arms": {a: v.get("item") for a, v in arms_out.items()},
                    "published_at": published_at, "ab_test": ab_test, "kind": kind},
              workdir=workdir, skill="thumbnail", source="cli", video_key=video_id)
    # versioni pubblicate e golden set: li tiene yt-thumb-learn (un solo scrittore di <studio>/data/thumb-golden/,
    # cartella per versione con PNG, JPEG, sidecar, QA e concept autosufficiente per il re-render)
    gold: list[dict] = []
    mapping = {a: v["item"] for a, v in arms_out.items() if v.get("item")}
    if workdir and mapping and kind == "long":
        try:
            tl = _tl()
            tl.ensure_schema(conn)
            wd_res = str(Path(workdir).expanduser().resolve())
            if not conn.execute("SELECT 1 FROM thumb_records WHERE channel=? AND workdir=? LIMIT 1",
                                (channel, wd_res)).fetchone():
                tl.ingest_workdir(conn, workdir, channel)
            rp = tl.record_publish(conn, workdir, video_id, mapping, published_at, ab_test, channel, golden=golden)
            warnings += rp.get("warnings") or []
            for d in rp.get("golden") or []:
                man = _read(Path(d) / "manifest.json") or {}
                files = man.get("files") or {}
                img = Path(d) / (files.get("png") or files.get("jpg") or "thumbnail.png")
                gold.append({"arm": man.get("arm"), "version": man.get("version"), "dir": str(d), "path": str(img),
                             "sha256": man.get("sha256")})
        except Exception as exc:  # noqa: BLE001 — il golden set non blocca mai la registrazione
            warnings.append(f"yt-thumb-learn publish: {type(exc).__name__}: {exc}")
    return {"channel": channel, "video_id": video_id, "arms": arms_out, "golden": gold, "warnings": warnings}


def golden_add(conn: sqlite3.Connection, channel: str, video_id: str, arm: str, a: dict,
               published_at: str | None) -> dict:
    src = Path(str(a["file"])).expanduser()
    if not src.is_file():
        raise LearnError(f"file del render assente: {src}")
    dest_dir = golden_dir() / channel / video_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{arm}-{a['item']}{src.suffix.lower()}"
    shutil.copy2(src, dest)
    sha = yc.sha256_file(dest)
    side = src.with_name(src.name.rsplit(".", 1)[0] + ".render.json")
    spec_hash = None
    if side.is_file():
        shutil.copy2(side, dest_dir / f"{arm}-{a['item']}.render.json")
        spec_hash = (_read(side) or {}).get("spec_hash")
    meta = {"channel": channel, "video_id": video_id, "arm": arm, "item": a["item"], "features": a.get("features"),
            "source": str(src), "published_at": published_at, "spec_hash": spec_hash, "sha256": sha,
            "note": "golden set locale (13 §4.3): mai nella repo né nel vault; fixture di regressione dei template"}
    yc.write_json(dest_dir / f"{arm}-{a['item']}.json", meta)
    with conn:
        conn.execute("INSERT OR IGNORE INTO learn_golden(channel, video_id, arm, item_key, path, sha256, features_json, "
                     "template, spec_hash, published_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (channel, video_id, arm, a["item"], str(dest), sha, canon(a.get("features") or {}),
                      (a.get("features") or {}).get("thumbnail.template"), spec_hash, published_at, now_iso()))
    return {"arm": arm, "path": str(dest), "sha256": sha}


def golden_list(conn: sqlite3.Connection, channel: str | None = None) -> list[dict]:
    """Golden set: le cartelle di yt-thumb-learn (fonte unica) + eventuali righe storiche di learn_golden."""
    out = []
    try:
        for m in _tl().golden_entries(channel):
            files = m.get("files") or {}
            img = Path(m["dir"]) / (files.get("png") or files.get("jpg") or "thumbnail.png")
            out.append({"channel": m.get("channel"), "video_id": m.get("video_id"), "arm": m.get("arm"),
                        "item_key": m.get("version"), "path": str(img), "dir": m["dir"], "sha256": m.get("sha256"),
                        "features": m.get("features") or {}, "published_at": m.get("published_at"),
                        "exists": img.is_file(), "source": "yt-thumb-learn"})
    except Exception:  # noqa: BLE001
        pass
    sql = "SELECT * FROM learn_golden" + (" WHERE channel=?" if channel else "") + " ORDER BY published_at, id"
    for r in conn.execute(sql, (channel,) if channel else ()):
        d = dict(r)
        d["features"] = jload(d.pop("features_json"), {})
        d["exists"] = Path(d["path"]).is_file()
        d["source"] = "learn_golden (storico)"
        out.append(d)
    return out


# ═══ Riferimenti di nicchia (≤ 30 giorni) ════════════════════════════════════
def refs_add(conn: sqlite3.Connection, channel: str, paths: list[str], source: str = "yt-research") -> dict:
    check_slug(channel)
    base = (refs_dir() / channel).resolve()
    added = []
    for p in paths:
        path = Path(p).expanduser().resolve()
        if base not in path.parents:
            raise LearnError(f"i riferimenti stanno in {base}/ (ricevuto {path})")
        if not path.is_file():
            raise LearnError(f"file assente: {path}")
        vid = path.stem.split("_")[0]
        with conn:
            conn.execute("INSERT INTO learn_refs(channel, ref_video_id, path, source, fetched_at) VALUES (?,?,?,?,?) "
                         "ON CONFLICT(channel, ref_video_id) DO UPDATE SET path=excluded.path, fetched_at=excluded.fetched_at",
                         (channel, vid, str(path), source, now_iso()))
        added.append(vid)
    add_event(conn, channel=channel, kind="refs_refresh", ref=f"refs:{today()}", data={"n": len(added), "source": source},
              source="cli", video_key=f"refs:{today()}")
    return {"channel": channel, "added": added, "dir": str(base)}


def refs_purge(conn: sqlite3.Connection, channel: str | None = None, days: int = 30, everything: bool = False) -> dict:
    cutoff = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)).isoformat(timespec="seconds")
    sql = "SELECT * FROM learn_refs WHERE " + ("1=1" if everything else "fetched_at < ?")
    params: list[Any] = [] if everything else [cutoff]
    if channel:
        sql += " AND channel=?"
        params.append(channel)
    gone = 0
    for r in conn.execute(sql, params).fetchall():
        p = Path(r["path"] or "")
        base = refs_dir().resolve()
        try:
            if p.is_file() and base in p.resolve().parents:
                p.unlink()
        except OSError:
            pass
        with conn:
            conn.execute("DELETE FROM learn_refs WHERE id=?", (r["id"],))
        gone += 1
    return {"deleted": gone, "cutoff": None if everything else cutoff}


def refs_due(conn: sqlite3.Connection, channel: str | None = None) -> list[dict]:
    """Rinfresco mensile dovuto: canali che hanno già fatto un rinfresco, l'ultimo da più di 30 giorni."""
    sql = ("SELECT channel, MAX(created_at) AS last FROM learn_events WHERE kind='refs_refresh' AND retracted_at IS NULL"
           + (" AND channel=?" if channel else "") + " GROUP BY channel")
    out = []
    for r in conn.execute(sql, (channel,) if channel else ()):
        try:
            last = _dt.datetime.fromisoformat(r["last"])
        except (TypeError, ValueError):
            continue
        if (_dt.datetime.now(_dt.timezone.utc) - last).days >= 30:
            out.append({"channel": r["channel"], "last": r["last"]})
    return out


# ═══ Esiti ═══════════════════════════════════════════════════════════════════
def _pub_day(conn: sqlite3.Connection, video_id: str) -> str | None:
    r = conn.execute("SELECT published_at FROM videos WHERE id=?", (video_id,)).fetchone()
    if r and r[0]:
        return str(r[0])[:10]
    r = conn.execute("SELECT published_at FROM learn_publications WHERE video_id=?", (video_id,)).fetchone()
    return str(r[0])[:10] if r and r[0] else None


def _snapshots(conn: sqlite3.Connection, video_id: str, pub: str) -> list[tuple[int, int]]:
    d0 = _dt.date.fromisoformat(pub)
    out = []
    for r in conn.execute("SELECT date, views FROM video_stats_daily WHERE video_id=? AND views IS NOT NULL ORDER BY date",
                          (video_id,)):
        try:
            out.append(((_dt.date.fromisoformat(r["date"]) - d0).days, int(r["views"])))
        except (TypeError, ValueError):
            continue
    return out


def views_at_age(snaps: list[tuple[int, int]], age: int, tol: int) -> tuple[float | None, str]:
    """Views a pari età da snapshot Tier 0: interpolazione tra due snapshot che la racchiudono (entro 2×tol),
    altrimenti lo snapshot più vicino entro tol. Mai interpolare da 0 alla pubblicazione (09 §3: stessa età o niente)."""
    if not snaps:
        return None, "nessuno snapshot"
    for a, v in snaps:
        if a == age:
            return float(v), "esatto"
    before = [(a, v) for a, v in snaps if a < age]
    after = [(a, v) for a, v in snaps if a > age]
    if before and after:
        (a1, v1), (a2, v2) = before[-1], after[0]
        if a2 - a1 <= 2 * tol:
            return v1 + (v2 - v1) * (age - a1) / (a2 - a1), "interpolato"
    near = min(snaps, key=lambda s: abs(s[0] - age))
    if abs(near[0] - age) <= tol:
        return float(near[1]), f"più vicino (età {near[0]})"
    return None, "età non allineata"


def _verdict(ratio: float | None, n_base: int, st: dict) -> str:
    if ratio is None or n_base < int(st["min_baseline"]):
        return "non leggibile"
    if ratio >= float(st["above_ratio"]):
        return "sopra"
    if ratio <= float(st["below_ratio"]):
        return "sotto"
    if ratio > 1.0:
        return "sopra (nel rumore)"
    if ratio < 1.0:
        return "sotto (nel rumore)"
    return "in linea"


def _prev_same_format(conn: sqlite3.Connection, video_id: str, limit: int = 10) -> list[dict]:
    v = conn.execute("SELECT channel_id, format, published_at FROM videos WHERE id=?", (video_id,)).fetchone()
    if not v or not v["published_at"]:
        return []
    return [dict(r) for r in conn.execute(
        "SELECT id, published_at, is_podcast FROM videos WHERE channel_id=? AND COALESCE(format,'long')=COALESCE(?,'long') "
        "AND id<>? AND published_at < ? ORDER BY published_at DESC LIMIT ?",
        (v["channel_id"], v["format"], video_id, v["published_at"], limit))]


def compute_outcome(conn: sqlite3.Connection, video_id: str, checkpoint: str) -> dict:
    st = settings()
    due_from, _, age, tol = CHECKPOINTS[checkpoint]
    pub = _pub_day(conn, video_id)
    res: dict[str, Any] = {"video_id": video_id, "checkpoint": checkpoint, "metrics": {}}
    if not pub:
        return {**res, "verdict": "non leggibile", "tier": 0, "metric": None,
                "note": "data di pubblicazione ignota (yt-collect --what inventory, o publish --published-at)"}
    res["published"] = pub
    prev = _prev_same_format(conn, video_id)
    # Tier 2: analytics_28d (D+28) e basic_daily (D+7)
    t2 = None
    if checkpoint == "d28":
        a = conn.execute("SELECT * FROM analytics_28d WHERE video_id=? AND complete=1", (video_id,)).fetchone()
        if a:
            pod = conn.execute("SELECT is_podcast FROM videos WHERE id=?", (video_id,)).fetchone()
            metric = "minutes_watched" if pod and pod[0] == 1 else ("engaged_views" if a["engaged_views"] is not None else "views")
            base = [r[metric] for r in conn.execute(
                f"SELECT {metric} FROM analytics_28d WHERE complete=1 AND video_id IN ({','.join('?' * len(prev))})",
                [p["id"] for p in prev]) if r[metric] is not None] if prev else []
            t2 = {"tier": 2, "metric": f"{metric}_28d", "value": a[metric], "base": base,
                  "extra": {"avd": a["avg_view_duration"], "avp": a["avg_view_pct"]}}
    elif checkpoint == "d7":
        def sum7(vid: str, pday: str) -> float | None:
            rows = conn.execute("SELECT COUNT(*) AS n, SUM(COALESCE(engaged_views, views)) AS v FROM basic_daily "
                                "WHERE video_id=? AND date BETWEEN ? AND date(?, '+6 days')", (vid, pday, pday)).fetchone()
            return float(rows["v"]) if rows and rows["n"] >= 7 and rows["v"] is not None else None
        val = sum7(video_id, pub)
        if val is not None:
            base = [x for p in prev for x in [sum7(p["id"], str(p["published_at"])[:10])] if x is not None]
            t2 = {"tier": 2, "metric": "engaged_views_7d", "value": val, "base": base, "extra": {}}
    if t2 and t2["value"] is not None:
        res.update({"tier": t2["tier"], "metric": t2["metric"], "value": float(t2["value"]),
                    "n_baseline": len(t2["base"])})
        res["metrics"].update({k: v for k, v in t2["extra"].items() if v is not None})
        base_vals = t2["base"]
    else:
        snaps = _snapshots(conn, video_id, pub)
        val, how = views_at_age(snaps, age, tol)
        res.update({"tier": 0, "metric": f"views_at_{age}d", "value": val, "alignment": how})
        base_vals = []
        cross = False
        for p in prev:
            pday = str(p["published_at"])[:10]
            pv, _ = views_at_age(_snapshots(conn, p["id"], pday), age, tol)
            if pv is not None:
                base_vals.append(pv)
                cross |= (pday < VIEW_BOUNDARY) != (pub < VIEW_BOUNDARY)
        res["n_baseline"] = len(base_vals)
        if cross:
            res["metrics"]["cross_boundary"] = True
    baseline = statistics.median(base_vals) if base_vals else None
    ratio = (res.get("value") / baseline) if res.get("value") is not None and baseline else None
    res["baseline"] = baseline
    res["ratio"] = round(ratio, 3) if ratio is not None else None
    res["verdict"] = "polso" if checkpoint == "t48" else _verdict(ratio, res.get("n_baseline", 0), st)
    # reach (Reporting API): impressioni e CTR pesato nella finestra
    days = 28 if checkpoint == "d28" else (7 if checkpoint == "d7" else 2)
    rr = conn.execute("SELECT SUM(impressions) AS imp, SUM(impressions*ctr)/NULLIF(SUM(impressions),0) AS ctr "
                      "FROM reach_daily WHERE video_id=? AND report_type='channel_reach_combined_a1' AND date BETWEEN ? "
                      "AND date(?, ?)", (video_id, pub, pub, f"+{days - 1} days")).fetchone()
    if rr and rr["imp"]:
        res["impressions"], res["ctr"] = int(rr["imp"]), rr["ctr"]
    ih = conn.execute("SELECT intro_hold_30s FROM retention_summary WHERE video_id=?", (video_id,)).fetchone()
    if ih and ih[0] is not None:
        res["intro_hold_30s"] = ih[0]
    ab = conn.execute("SELECT * FROM ab_tests WHERE video_id=? ORDER BY id DESC LIMIT 1", (video_id,)).fetchone()
    if ab and checkpoint != "t48":
        winner = (ab["winner"] or "").strip()
        low = winner.casefold()
        result = ("same" if low in ("same", "pari", "prestazioni simili") else
                  "inconclusive" if low in ("", "inconclusive", "inconcludente", "nessuno") else "winner")
        res["ab"] = {"id": ab["id"], "winner": winner if result == "winner" else None, "result": result,
                     "kind": ab["kind"], "ended_at": ab["ended_at"]}
        if not ab["ended_at"] and result == "inconclusive":
            res.pop("ab")     # test ancora in corso: niente lettura
    res["derived_note"] = "calcolato da noi, non è un dato YouTube" if res.get("ratio") is not None else None
    return res


def save_outcome(conn: sqlite3.Connection, channel: str, res: dict, source: str = "pull") -> dict:
    data = {k: res.get(k) for k in ("checkpoint", "tier", "metric", "value", "baseline", "ratio", "n_baseline",
                                     "verdict", "ab", "impressions", "ctr")}
    data["decisive"] = bool(res.get("ab", {}) and res["ab"].get("result") == "winner")
    eid, _ = add_event(conn, channel=channel, kind="outcome", ref=f"outcome:{res['video_id']}:{res['checkpoint']}",
                       data=data, skill="thumbnail", signal="esiti", source=source, video_key=res["video_id"])
    now = now_iso()
    metrics = dict(res.get("metrics") or {})
    for k in ("alignment", "published", "note", "derived_note"):
        if res.get(k):
            metrics[k] = res[k]
    with conn:
        conn.execute(
            "INSERT INTO learn_outcomes(channel, video_id, checkpoint, tier, source, metric, value, baseline, ratio, "
            "n_baseline, verdict, impressions, ctr, avd, avp, intro_hold_30s, ab_json, metrics_json, event_id, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(video_id, checkpoint) DO UPDATE SET tier=excluded.tier, source=excluded.source, "
            "metric=excluded.metric, value=excluded.value, baseline=excluded.baseline, ratio=excluded.ratio, "
            "n_baseline=excluded.n_baseline, verdict=excluded.verdict, impressions=excluded.impressions, "
            "ctr=excluded.ctr, avd=excluded.avd, avp=excluded.avp, intro_hold_30s=excluded.intro_hold_30s, "
            "ab_json=excluded.ab_json, metrics_json=excluded.metrics_json, event_id=excluded.event_id, "
            "updated_at=excluded.updated_at",
            (channel, res["video_id"], res["checkpoint"], res.get("tier"), source, res.get("metric"), res.get("value"),
             res.get("baseline"), res.get("ratio"), res.get("n_baseline"), res.get("verdict") or "non leggibile",
             res.get("impressions"), res.get("ctr"), metrics.get("avd") or res.get("avd"),
             metrics.get("avp") or res.get("avp"), res.get("intro_hold_30s"), canon(res["ab"]) if res.get("ab") else None,
             canon(metrics), eid, now, now))
    return {**res, "event": eid}


def due_items(conn: sqlite3.Connection, channel: str | None = None) -> dict:
    sql = "SELECT * FROM learn_due_v" + (" WHERE channel=?" if channel else "") + " ORDER BY due_on"
    rows = [dict(r) for r in conn.execute(sql, (channel,) if channel else ())]
    pulls = [r for r in rows if r["task"] == "pull"]
    reviews = [r for r in rows if r["task"] == "review"]
    sqlp = "SELECT id, channel, title, created_at FROM learn_proposals WHERE state='in_attesa'" + \
           (" AND channel=?" if channel else "")
    props = [dict(r) for r in conn.execute(sqlp, (channel,) if channel else ())]
    sqlj = ("SELECT id, channel, workdir, started_at FROM learn_jobs WHERE ended_at IS NULL "
            "AND julianday(started_at) < julianday('now', '-1 day')" + (" AND channel=?" if channel else ""))
    stale = [dict(r) for r in conn.execute(sqlj, (channel,) if channel else ())]
    sqll = "SELECT COUNT(*) FROM learn_lessons WHERE state='pronta'" + (" AND channel=?" if channel else "")
    ready = conn.execute(sqll, (channel,) if channel else ()).fetchone()[0]
    return {"outcome_pulls": pulls, "reviews": reviews, "proposals_pending": len(props), "proposals": props,
            "lessons_ready": ready, "jobs_without_passo5": stale, "refs_refresh": refs_due(conn, channel)}


def pull_outcomes(conn: sqlite3.Connection, channel: str | None = None, video_id: str | None = None,
                  checkpoint: str | None = None, refresh: bool = False) -> list[dict]:
    targets: list[tuple[str, str, str]] = []
    if video_id:
        r = conn.execute("SELECT channel FROM learn_publications WHERE video_id=?", (video_id,)).fetchone()
        ch = channel or (r[0] if r else None)
        if not ch:
            raise LearnError(f"video {video_id} non registrato: yt-learn publish --channel … --video-id {video_id}")
        pday = _pub_day(conn, video_id)
        age = (_dt.date.today() - _dt.date.fromisoformat(pday)).days if pday else None
        cps = [checkpoint] if checkpoint else [c for c, (d, _, _, _) in CHECKPOINTS.items() if age is not None and age >= d]
        targets = [(ch, video_id, c) for c in cps]
    else:
        for r in due_items(conn, channel)["outcome_pulls"]:
            if not checkpoint or r["checkpoint"] == checkpoint:
                targets.append((r["channel"], r["video_id"], r["checkpoint"]))
        if refresh:
            sql = "SELECT channel, video_id, checkpoint FROM learn_outcomes WHERE source='pull'" + \
                  (" AND channel=?" if channel else "")
            targets += [(r[0], r[1], r[2]) for r in conn.execute(sql, (channel,) if channel else ())]
    out = []
    for ch, vid, cp in dict.fromkeys(targets):
        if conn.execute("SELECT 1 FROM learn_outcomes WHERE video_id=? AND checkpoint=? AND source='manual'",
                        (vid, cp)).fetchone():
            continue      # un esito scritto a mano (Studio) non si sovrascrive mai con un pull
        out.append(save_outcome(conn, ch, compute_outcome(conn, vid, cp)))
    return out


def outcome_manual(conn: sqlite3.Connection, *, channel: str | None, video_id: str, checkpoint: str,
                   verdict: str | None = None, value: float | None = None, baseline: float | None = None,
                   n_baseline: int | None = None, metric: str | None = None, ctr: float | None = None,
                   impressions: int | None = None, avd: float | None = None, intro: float | None = None,
                   ab_winner: str | None = None, ab_result: str | None = None, note: str | None = None) -> dict:
    if checkpoint not in CHECKPOINTS:
        raise LearnError(f"--checkpoint: {', '.join(CHECKPOINTS)}")
    r = conn.execute("SELECT channel FROM learn_publications WHERE video_id=?", (video_id,)).fetchone()
    channel = channel or (r[0] if r else None)
    if not channel:
        raise LearnError("--channel mancante e video non registrato con yt-learn publish")
    st = settings()
    ratio = value / baseline if value is not None and baseline else None
    if verdict is None:
        verdict = "polso" if checkpoint == "t48" else _verdict(ratio, n_baseline or 0, st)
    if verdict not in VERDICTS:
        raise LearnError(f"--verdict: {', '.join(VERDICTS)}")
    res: dict[str, Any] = {"video_id": video_id, "checkpoint": checkpoint, "tier": None, "metric": metric or "manuale",
                           "value": value, "baseline": baseline, "ratio": round(ratio, 3) if ratio else None,
                           "n_baseline": n_baseline, "verdict": verdict, "ctr": ctr, "impressions": impressions,
                           "avd": avd, "intro_hold_30s": intro, "metrics": {"note": note} if note else {}}
    if ab_winner or ab_result:
        result = ab_result or "winner"
        if result not in ("winner", "same", "inconclusive"):
            raise LearnError("--ab-result: winner | same | inconclusive")
        res["ab"] = {"winner": ab_winner if result == "winner" else None, "result": result, "source": "Studio (operatore)"}
    return {**save_outcome(conn, channel, res, source="manual"), "channel": channel}


# ═══ Aggiornamento complessivo ═══════════════════════════════════════════════
def update_channel(conn: sqlite3.Connection, channel: str) -> dict:
    check_slug(channel)
    out = {"channel": channel, "priors": update_priors(conn, channel), "lessons": refresh_lessons(conn, channel),
           "glossary": rebuild_learned_glossary(conn, channel)}
    withdrawn = withdraw_stale_proposals(conn, channel)      # prove ritrattate sotto la soglia: niente PR
    if withdrawn:
        out["proposals_withdrawn"] = withdrawn
        out["lessons"] = refresh_lessons(conn, channel)       # le lezioni tornano allo stato delle prove vive
    write_thresholds_file(conn, channel)
    out["refs_purged"] = refs_purge(conn, channel)["deleted"]
    with conn:
        conn.execute("UPDATE learn_jobs SET learned_at=? WHERE channel=? AND ended_at IS NOT NULL AND learned_at IS NULL",
                     (now_iso(), channel))
    return out


# ═══ Report e playbook ═══════════════════════════════════════════════════════
def _top_priors(rows: list[dict], per_feature: int = 3) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["feature"], []).append(r)
    res = {}
    for f, rs in out.items():
        with_n = sorted((r for r in rs if r["n_jobs"] > 0), key=lambda r: (r["signal"] != "esiti", -r["mean"], r["value"]))
        keep = with_n or [r for r in rs if r["is_default"] and r["signal"] == "scelte"][:1]   # senza dati: il default
        res[f] = [{"value": r["value"], "signal": r["signal"], "mean": r["mean"], "n": r["n_jobs"], "conf": r["conf"],
                   "ci80": r["ci80"], "elo": round(r["elo"]) if r["elo_n"] else None, "default": bool(r["is_default"])}
                  for r in keep][:per_feature]
    return {f: v for f, v in res.items() if v}


def report(conn: sqlite3.Connection, channel: str, focus: str | None = None, write: bool = True) -> dict:
    check_slug(channel)
    rows = prior_rows(conn, channel, focus)
    counts = {r["kind"]: r["n"] for r in conn.execute(
        "SELECT kind, COUNT(*) AS n FROM learn_events WHERE channel=? AND retracted_at IS NULL AND superseded_by IS NULL "
        "AND json_extract(data_json, '$.paired_from') IS NULL GROUP BY kind", (channel,))}
    counts["jobs"] = conn.execute("SELECT COUNT(*) FROM learn_jobs WHERE channel=?", (channel,)).fetchone()[0]
    counts["published"] = conn.execute("SELECT COUNT(*) FROM learn_publications WHERE channel=?", (channel,)).fetchone()[0]
    lessons = [lv for lv in lessons_list(conn, channel) if not focus or lv["skill"] in (None, focus)]
    exploration = {}
    if focus or rows:
        for f in sorted({r["feature"].split(".")[0] for r in rows} | ({focus} if focus else set())):
            if f in ("thumbnail", "hook", "shorts", "chapters", "edit"):
                for feat, e in suggest(conn, channel, f, seed=0)["features"].items():
                    if e.get("explore"):
                        exploration[feat] = {"value": e["explore"], "why": e.get("explore_note")}
    idx = _prior_index(rows)
    dis = [d for d in (disagreement(idx, f) for f in sorted({r["feature"] for r in rows})) if d]
    due = due_items(conn, channel)
    tcounts = {}
    if focus in (None, "thumbnail"):
        try:
            tl = _tl()
            tl.ensure_schema(conn)
            tcounts = tl.priors_report(conn, channel, top=1)["counts"]
        except Exception:  # noqa: BLE001
            tcounts = {}
    rep = {
        "channel": channel, "kind": channel_kind(channel, conn), "shareable": channel in pr_channels(),
        "focus": focus, "generated": now_iso(),
        "counts": counts, "priors": _top_priors(rows), "disagreements": dis, "exploration": exploration,
        "thumbnail": tcounts,
        "lessons": {"active": [lv for lv in lessons if lv["state"] in ("attiva", "pronta", "proposta")],
                    "ready_for_proposal": [lv["id"] for lv in lessons if lv["state"] == "pronta"],
                    "candidates": sum(1 for lv in lessons if lv["state"] == "candidata")},
        "thresholds": [{k: t[k] for k in ("name", "direction", "value", "level")} for t in thresholds_list(conn, channel)],
        "due": {"outcome_pulls": [f"{r['video_id']} {r['checkpoint']}" for r in due["outcome_pulls"]],
                "reviews": [f"{r['video_id']} {r['checkpoint']}" for r in due["reviews"]],
                "proposals_pending": due["proposals_pending"], "refs_refresh": bool(due["refs_refresh"]),
                "jobs_without_passo5": [j["id"] for j in due["jobs_without_passo5"]]},
        "hard_rules": "invariate (13 §2: H1–H12)",
    }
    if focus in (None, "transcript"):
        gl = yc.learned_file(channel, ".glossary.txt")
        rep["learned_glossary"] = {"terms": sum(1 for ln in gl.read_text().splitlines() if ln.strip() and not ln.startswith("#"))
                                   if gl.exists() else 0,
                                   "aliases": len((_read(yc.learned_file(channel, ".confusions.json")) or {}).get("confusions", []))}
    if write:
        path, n = write_playbook(conn, channel, rep)
        rep["playbook"], rep["playbook_lines"] = str(path), n
    return rep


def _fmt_prior(p: dict) -> str:
    tag = "esiti" if p["signal"] == "esiti" else "scelte"
    elo = f", Elo {p['elo']}" if p.get("elo") else ""
    d = " (default)" if p.get("default") else ""
    return f"{p['value']}{d} {p['mean']:.2f} [appreso: {tag}, n={p['n']}, conf. {p['conf']}{elo}]"


def write_playbook(conn: sqlite3.Connection, channel: str, rep: dict | None = None) -> tuple[Path, int]:
    rep = rep or report(conn, channel, write=False)
    if rep.get("focus"):
        rep = report(conn, channel, None, write=False)
    L: list[str] = [
        f"# Playbook appreso — {channel}",
        "",
        f"> Generato da `yt-learn` il {rep['generated'][:16].replace('T', ' ')} (non modificare a mano: si rigenera). "
        "Locale, mai nel vault né nella repo. Vale dal prossimo video; ogni numero porta n, confidenza e segnale. "
        "Le regole dure (13 §2, H1–H12) non si imparano.",
        "",
        f"Job: {rep['counts'].get('jobs', 0)} · decisioni: {rep['counts'].get('decision', 0)} · correzioni: "
        f"{rep['counts'].get('correction', 0)} · item: {rep['counts'].get('item', 0)} · pubblicati: "
        f"{rep['counts'].get('published', 0)} · esiti: {rep['counts'].get('outcome', 0)}",
        "",
        "Proposte per la repo (Tier B): " + ("attive, il canale è condiviso." if rep.get("shareable") else
                                             "spente, le lezioni restano su questo Mac (13 §1.2: learning_pr_channels e, "
                                             "nel profilo, kind: own e share_lessons: true)."),
        "",
    ]
    groups: dict[str, list[tuple[str, list[dict]]]] = {}
    for f, ps in rep["priors"].items():
        groups.setdefault(f.split(".")[0], []).append((f, ps))
    order = ["thumbnail", "hook", "shorts", "chapters", "edit"]
    st = settings()
    a0, b0 = prior_ab(True, st)
    prior_txt = (f"media 0,5 per ogni valore ammesso, {a0 / (a0 + b0):.2f} per il default del profilo o del knowledge, "
                 f"con il peso di {float(st.get('prior_strength', 4)):g} osservazioni")
    tc = rep.get("thumbnail") or {}
    for g in sorted(groups, key=lambda x: (order.index(x) if x in order else 99, x)):
        L.append(f"## Priori — {g}" + (" (yt-thumb-learn)" if g == "thumbnail" else ""))
        if g == "thumbnail" and tc:
            L.append(f"- Evidenza: {tc.get('scelte_g2', 0)} preferenze G2 in {tc.get('lavori_g2', 0)} lavori · "
                     f"{tc.get('delegate', 0)} delegate (peso 0) · {tc.get('test_decisivi', 0)} test decisivi · "
                     f"{tc.get('esiti', 0)} esiti · {tc.get('record', 0)} concept/render registrati · "
                     f"{tc.get('pubblicate', 0)} video pubblicati.")
        shown = [(f, ps) for f, ps in groups[g] if g != "thumbnail" or any(p["n"] for p in ps)] or groups[g]
        for f, ps in shown[:14]:
            L.append(f"- `{f.split('.', 1)[1]}`: " + " · ".join(_fmt_prior(p) for p in ps[:3]))
        L.append("")
    if not groups:
        L += ["## Priori", f"- Nessun dato ancora: valgono i default del knowledge pack (prior: {prior_txt}).", ""]
    else:
        L += [f"> Prior di partenza: {prior_txt}. Con n < 5 la confidenza è bassa: il valore informa, non cambia il "
              "default (13 §3.3).", ""]
    if rep["disagreements"]:
        L.append("## Scelte ed esiti non vanno d'accordo")
        L += [f"- {d}" for d in rep["disagreements"][:6]]
        L.append("")
    if rep["exploration"]:
        L.append("## Esplorazione suggerita (Thompson, 13 §3.4)")
        L += [f"- `{f}` → {e['value']} ({e['why']})" for f, e in list(rep["exploration"].items())[:10]]
        L.append("- Mai esplorazione su consenso, volti e pixel dell'ospite, numeri, soldi, pubblicazione.")
        L.append("")
    act = rep["lessons"]["active"]
    L.append("## Lezioni attive")
    if act:
        for lv in act[:25]:
            sc = "globale" if lv["scope"] == "global" else lv["channel"]
            L.append(f"- [L{lv['id']} · {lv['stato']} · n={lv['n']} · conf. {lv['confidence']} · {lv['skill'] or 'generale'}"
                     f" · {sc}] {lv['text']} ({', '.join(lv['evidence'][:4]) or 'senza prove registrate'})")
    else:
        L.append("- Nessuna lezione attiva (le candidate con una sola osservazione non valgono ancora).")
    if rep["lessons"]["candidates"]:
        L.append(f"- Candidate in osservazione: {rep['lessons']['candidates']} (una sola prova: nessun effetto; si "
                 "confermano con `yt-learn lesson confirm <id> --evidence e<id>` quando un nuovo lavoro le ripete).")
        for lv in [x for x in lessons_list(conn, channel, "candidata")][:10]:
            L.append(f"  - L{lv['id']} · {lv['skill'] or 'generale'}: {lv['text'][:140]}")
    L.append("")
    if rep["thresholds"]:
        L.append("## Soglie apprese più severe (solo stringere, H8)")
        L += [f"- `{t['name']}` {'≥' if t['direction'] == 'min' else '≤'} {t['value']}"
              + (f" ({t['level']})" if t.get("level") else "") for t in rep["thresholds"][:12]]
        L.append("")
    corr = [e["data"] for e in live_events(conn, channel, "correction")][-200:]
    if corr:
        cnt: dict[tuple[str, str, str], int] = {}
        for c in corr:
            k = (c.get("kind", ""), c.get("from", ""), c.get("to", ""))
            cnt[k] = cnt.get(k, 0) + 1
        L.append("## Correzioni registrate (operatore e revisioni con prove, più frequenti)")
        for (kind, fr, to), n in sorted(cnt.items(), key=lambda kv: -kv[1])[:10]:
            L.append(f"- {kind}: «{fr[:60]}» → «{to[:60]}» ×{n}")
        L.append("")
    if rep.get("learned_glossary"):
        g = rep["learned_glossary"]
        L += ["## Glossario appreso", f"- {g['terms']} termini (P3) e {g['aliases']} confusioni in "
              f"`learned/{channel}.glossary.txt` e `.confusions.json`, fusi a runtime con quelli del profilo.", ""]
    pubs = conn.execute("SELECT p.video_id, p.arms_json, o.checkpoint, o.verdict, o.ratio, o.n_baseline FROM "
                        "learn_publications p LEFT JOIN learn_outcomes o ON o.video_id=p.video_id WHERE p.channel=? "
                        "ORDER BY p.created_at DESC LIMIT 12", (channel,)).fetchall()
    if pubs:
        L.append("## Pubblicati ed esiti")
        for r in pubs:
            arms = jload(r["arms_json"], {}) or {}
            arm_txt = ", ".join(f"{a}={v.get('item')}" for a, v in arms.items()) or "braccia non registrate"
            res = f"{r['checkpoint']}: {r['verdict']}" + (f" ({r['ratio']}× mediana, n={r['n_baseline']}; calcolato da noi)"
                                                           if r["ratio"] else "") if r["checkpoint"] else "nessun esito ancora"
            L.append(f"- {r['video_id']} · {arm_txt} · {res}")
        L.append("")
    due = rep["due"]
    todo = []
    if due["outcome_pulls"]:
        todo.append(f"esiti da leggere: {', '.join(due['outcome_pulls'][:6])} (/youtube:review)")
    if due["reviews"]:
        todo.append(f"post-mortem da fare: {', '.join(due['reviews'][:6])} (/youtube:review)")
    if due["proposals_pending"]:
        todo.append(f"proposte in attesa: {due['proposals_pending']} (PR dalla sessione principale)")
    if due["refs_refresh"]:
        todo.append("rinfresco mensile dei riferimenti di nicchia (/youtube:learn)")
    if due["jobs_without_passo5"]:
        todo.append(f"job senza Passo 5: {len(due['jobs_without_passo5'])}")
    L.append("## In sospeso")
    L += [f"- {t}" for t in todo] or ["- Niente."]
    L.append("")
    L.append("## Regole dure (mai modificate dall'apprendimento)")
    L += [f"- {c}: {t}" for c, t in HARD_RULES]
    if len(L) > PLAYBOOK_MAX_LINES:
        L = L[: PLAYBOOK_MAX_LINES - 1] + ["- (tagliato a 150 righe: `yt-learn report --channel … --focus …` per il resto)"]
    path = yc.learned_file(channel, ".md")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text("\n".join(L) + "\n")
    os.replace(tmp, path)
    return path, len(L)


# ═══ Proposte (Tier B) ═══════════════════════════════════════════════════════
def norm_target(target: str) -> str:
    t = target.strip().lstrip("./")
    if t.startswith(REPO_PLUGIN_SUBDIR + "/"):
        t = t[len(REPO_PLUGIN_SUBDIR) + 1:]
    if not t or ".." in Path(t).parts or Path(t).is_absolute():
        raise LearnError(f"destinazione non valida: {target!r} (percorso relativo alla radice del plugin)")
    if any(t == f.rstrip("/") or t.startswith(f) for f in FORBIDDEN_TARGETS):
        raise LearnError(f"destinazione vietata: {t} (regole dure, hook, guard, setup e il sistema di apprendimento "
                         "non si cambiano con una proposta automatica)")
    if not any(t == p or t.startswith(p) for p in ALLOWED_TARGET_PREFIXES):
        raise LearnError(f"destinazione fuori dal perimetro delle proposte: {t}")
    return t


def make_diff(rel: str, old: str, new: str) -> str:
    a = old.splitlines(keepends=True)
    b = new.splitlines(keepends=True)
    if a and not a[-1].endswith("\n"):
        a[-1] += "\n"
    if b and not b[-1].endswith("\n"):
        b[-1] += "\n"
    return "".join(difflib.unified_diff(a, b, fromfile=f"a/{rel}", tofile=f"b/{rel}", n=3))


def insert_in_section(text: str, block: str, anchor: str | None) -> str:
    block = block.rstrip("\n") + "\n"
    lines = text.splitlines(keepends=True)
    if not anchor:
        sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        return text + sep + block
    idx = None
    level = 0
    for i, ln in enumerate(lines):
        m = re.match(r"^(#+)\s+(.*)$", ln.rstrip("\n"))
        if m and anchor.strip().lstrip("#").strip().casefold() in m.group(2).casefold():
            idx, level = i, len(m.group(1))
            break
    if idx is None:
        raise LearnError(f"intestazione «{anchor}» non trovata nel file di destinazione")
    end = len(lines)
    for j in range(idx + 1, len(lines)):
        m = re.match(r"^(#+)\s", lines[j])
        if m and len(m.group(1)) <= level:
            end = j
            break
    while end > idx + 1 and lines[end - 1].strip() in ("", "---"):
        end -= 1
    prev = lines[end - 1].strip()
    if prev.startswith("|") and block.lstrip().startswith("|"):
        ins = [block]                    # righe in coda a una tabella markdown: niente riga vuota (romperebbe la tabella)
    else:
        ins = ["\n", block] if prev else [block]
    return "".join(lines[:end] + ins + lines[end:])


_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def apply_unified_diff(original: str, diff: str) -> str:
    """Applica un diff unificato (un file) in modo esatto: il contesto deve combaciare. LearnError altrimenti."""
    src = original.splitlines(keepends=True)
    out: list[str] = []
    pos = 0
    lines = diff.splitlines(keepends=True)
    i = 0
    hunks = 0
    while i < len(lines):
        m = _HUNK.match(lines[i])
        if not m:
            i += 1
            continue
        hunks += 1
        start = int(m.group(1)) - (0 if m.group(2) == "0" else 1)
        i += 1
        old_block, new_block = [], []
        while i < len(lines) and not lines[i].startswith("@@") and not lines[i].startswith("--- "):
            ln = lines[i]
            if ln.startswith("\\"):
                i += 1
                continue
            tag, body = ln[:1], ln[1:]
            if tag == " ":
                old_block.append(body)
                new_block.append(body)
            elif tag == "-":
                old_block.append(body)
            elif tag == "+":
                new_block.append(body)
            elif ln.strip() == "":
                old_block.append("\n")
                new_block.append("\n")
            i += 1
        if start < pos or src[start:start + len(old_block)] != old_block:
            raise LearnError(f"il diff non si applica (hunk {hunks}, riga {start + 1}): il file è cambiato")
        out += src[pos:start] + new_block
        pos = start + len(old_block)
    if not hunks:
        raise LearnError("diff vuoto o non unificato")
    out += src[pos:]
    return "".join(out)


def diff_touched_lines(diff: str) -> list[int]:
    """Righe (0-based) del file originale toccate dal diff: righe tolte e punti di inserimento."""
    touched: list[int] = []
    cur = None
    for ln in diff.splitlines():
        m = _HUNK.match(ln)
        if m:
            cur = int(m.group(1)) - (0 if m.group(2) == "0" else 1)
            continue
        if cur is None or ln.startswith(("---", "+++")):
            continue
        if ln.startswith("-"):
            touched.append(cur)
            cur += 1
        elif ln.startswith("+"):
            touched.append(max(cur - 1, 0))
        elif ln.startswith(" ") or ln == "":
            cur += 1
    return sorted(set(touched))


def _md_heading_at(lines: list[str], idx: int) -> list[str]:
    """Intestazioni che racchiudono la riga idx (dalla più interna)."""
    heads, level = [], 99
    for j in range(min(idx, len(lines) - 1), -1, -1):
        m = re.match(r"^(#+)\s+(.*)$", lines[j])
        if m and len(m.group(1)) < level:
            heads.append(m.group(2).strip())
            level = len(m.group(1))
            if level == 1:
                break
    return heads


def _yaml_keys_at(lines: list[str], idx: int) -> list[str]:
    """Chiavi YAML del frontmatter che racchiudono la riga idx."""
    if not lines or lines[0].strip() != "---":
        return []
    try:
        end = next(j for j in range(1, len(lines)) if lines[j].strip() == "---")
    except StopIteration:
        return []
    if idx >= end:
        return []
    keys, indent = [], 10 ** 6
    for j in range(idx, 0, -1):
        m = re.match(r"^(\s*)([A-Za-z_][\w-]*)\s*:", lines[j])
        if m and len(m.group(1)) < indent:
            keys.append(m.group(2))
            indent = len(m.group(1))
            if indent == 0:
                break
    return keys


def hard_rule_check(rel: str, original: str, diff: str) -> list[str]:
    """Violazioni delle regole dure: sezioni protette, chiavi del profilo protette, testo che le contraddice."""
    problems: list[str] = []
    lines = original.splitlines()
    pats = HARD_SECTIONS.get(rel, [])
    for idx in diff_touched_lines(diff):
        if pats:
            for h in _md_heading_at(lines, idx):
                if any(re.search(p, h) for p in pats):
                    problems.append(f"tocca la sezione protetta «{h}» (riga {idx + 1})")
        if rel.startswith("docs/yt/channels/") and rel.endswith(".md"):
            ks = set(_yaml_keys_at(lines, idx)) & HARD_YAML_KEYS
            if ks:
                problems.append(f"tocca chiavi protette del profilo: {', '.join(sorted(ks))} (riga {idx + 1})")
    added = "\n".join(ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
    hit = hard_rule_hit(added)
    if hit:
        problems.append(f"il testo aggiunto contrasta la regola dura {hit}")
    return list(dict.fromkeys(problems))


def _privacy_terms(conn: sqlite3.Connection) -> tuple[set[str], set[str], set[str]]:
    """(nomi/slug di canali non ammessi in PR, id video non ammessi, nomi di ospiti non nel glossario di un canale
    condivisibile)."""
    allowed = pr_channels()
    names: set[str] = set()
    vids: set[str] = set()
    for d in yc.CHANNELS_DIRS:
        for p in sorted(Path(d).glob("*.md")) if Path(d).is_dir() else []:
            if p.name.startswith("_") or p.stem in allowed:
                continue
            names.add(p.stem)
            try:
                meta = yc.load_channel(p.stem)
            except Exception:  # noqa: BLE001
                continue
            for k in ("name", "client", "client_vault_folder"):
                if isinstance(meta.get(k), str):
                    names.add(meta[k])
            h = (meta.get("channel") or {}).get("handle") if isinstance(meta.get("channel"), dict) else None
            if isinstance(h, str):
                names.add(h)
    try:
        for r in conn.execute("SELECT slug, handle, title, id FROM channels"):
            if r["slug"] in allowed:
                continue
            names |= {x for x in (r["slug"], r["handle"], r["title"]) if x}
            vids |= {v[0] for v in conn.execute("SELECT id FROM videos WHERE channel_id=?", (r["id"],))}
        for r in conn.execute("SELECT DISTINCT channel FROM learn_events"):
            if r[0] not in allowed:
                names.add(r[0])
                vids |= {v[0] for v in conn.execute("SELECT video_id FROM learn_publications WHERE channel=?", (r[0],))}
    except sqlite3.Error:
        pass
    guests: set[str] = set()
    for e in conn.execute("SELECT data_json FROM learn_events WHERE kind='item' AND skill='thumbnail'"):
        for g in ((jload(e[0], {}) or {}).get("payload") or {}).get("guests") or []:
            guests.add(str(g))
    # anche i nomi dei parlanti dei lavori registrati (project.json «speakers»: ospiti, ma pure host di altri canali)
    try:
        wds = {r[0] for r in conn.execute("SELECT DISTINCT workdir FROM learn_events WHERE workdir IS NOT NULL")}
    except sqlite3.Error:
        wds = set()
    for wd in wds:
        proj = _read(Path(wd) / "project.json")
        sp = proj.get("speakers") if isinstance(proj, dict) else None
        for name in (sp.values() if isinstance(sp, dict) else sp if isinstance(sp, list) else []):
            if isinstance(name, str) and len(name.strip()) >= 4:
                guests.add(name.strip())
    gl: set[str] = set()
    for ch in allowed:        # nomi già pubblici nel glossario di un canale condivisibile (host, ospiti ricorrenti)
        try:
            gl |= {t.casefold() for t in yc.glossary_terms(ch)}
        except (OSError, ValueError):
            pass
    guests = {g for g in guests if g.casefold() not in gl}
    return {n for n in names if len(n) >= 3}, vids, guests


SECRET_PATS = [re.compile(p) for p in (r"AIza[0-9A-Za-z_-]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"sk-[A-Za-z0-9]{20,}",
                                         r"(?i)(api[_-]?key|client_secret|refresh_token|access_token)\s*[:=]\s*\S{8,}")]


def privacy_check(conn: sqlite3.Connection, texts: list[str]) -> tuple[list[str], list[str]]:
    """Filtro di privacy (13 §9.2): (problemi che bloccano, avvisi)."""
    blob = "\n".join(t for t in texts if t)
    problems, warns = [], []
    if re.search(r"(/Users/|/home/|/private/|/Volumes/)[^\s`'\"]+", blob):
        problems.append("percorso assoluto personale")
    if re.search(r"~/[\w.-]*studio/(work|data)/\S+|thumb-golden/|<studio_dir>/data/refs/\S+\.(png|jpe?g)", blob):
        problems.append("riferimento a file di lavoro, golden set o riferimenti")
    if re.search(r"data:image/|\bbase64,", blob):
        problems.append("immagine incorporata")
    for m in re.finditer(r"[\w.+-]+@[\w-]+\.[\w.-]+", blob):
        if not m.group(0).endswith("anthropic.com"):
            problems.append(f"indirizzo email ({m.group(0)})")
    for p in SECRET_PATS:
        if p.search(blob):
            problems.append("possibile segreto (chiave o token)")
    names, vids, guests = _privacy_terms(conn)
    low = blob.casefold()
    for n in sorted(names):
        if re.search(rf"(?<![\w@]){re.escape(n.casefold())}(?!\w)", low):
            problems.append(f"nome o slug di un canale cliente o personale: «{n}»")
    for v in sorted(vids):
        if v in blob:
            problems.append(f"id video di un canale cliente o personale ({v})")
    for g in sorted(guests):
        if len(g) >= 4 and g.casefold() in low:
            problems.append(f"nome di un ospite non presente nel glossario di un canale condivisibile («{g}»)")
    for m in re.finditer(r"[«“\"]([^»”\"]{40,})[»”\"]", blob):
        if len(m.group(1).split()) >= 8:
            warns.append(f"citazione lunga da verificare: «{m.group(1)[:50]}…»")
    return list(dict.fromkeys(problems)), list(dict.fromkeys(warns))


def proposal_slug(title: str) -> str:
    return yc.slugify(title)[:40] or "proposta"


def propose(conn: sqlite3.Connection, *, title: str, lesson_ids: list[int], target: str, diff: str | None = None,
            append: str | None = None, anchor: str | None = None, replace_old: str | None = None,
            replace_new: str | None = None, rationale: str | None = None, risk: str | None = None,
            slug: str | None = None, operator_decision: str | None = None, evidence: list[int] | None = None) -> dict:
    if not title:
        raise LearnError("--title obbligatorio")
    st = settings()
    allowed_channels = pr_channels(st)
    lessons = [lesson_get(conn, i) for i in lesson_ids]
    if not lessons:
        raise LearnError("una proposta nasce da almeno una lezione (--lesson ID)")
    channels = {lv["channel"] for lv in lessons}
    scope = "global" if all(lv["scope"] == "global" for lv in lessons) else "channel"
    for lv in lessons:
        if lv["state"] == "ritirata":
            raise LearnError(f"lezione L{lv['id']} ritirata")
        if lv["channel"] not in allowed_channels:
            raise LearnError(f"lezione L{lv['id']} del canale {lv['channel']}: le lezioni di clienti, canali personali e "
                             f"canali non condivisi restano locali, mai una PR (canali condivisibili: "
                             f"{', '.join(sorted(allowed_channels)) or 'nessuno'}; servono learning_pr_channels e, nel "
                             "profilo, kind: own e share_lessons: true)")
        if lv["scope"] == "global" and channel_kind(lv["channel"], conn) != "own":
            raise LearnError(f"lezione globale L{lv['id']} da un canale non proprio")
        if lv["state"] not in ("pronta", "proposta"):
            raise LearnError(f"lezione L{lv['id']} non è «pronta per proposta» (stato {lv['state']}, n={lv['n_jobs']}): "
                             f"servono {st['min_evidence']} lavori coerenti o un esito decisivo")
    rel = norm_target(target)
    path = plugin_root() / rel
    if not path.is_file():
        raise LearnError(f"file di destinazione assente nel plugin: {rel}")
    original = path.read_text()
    kinds = sum(x is not None for x in (diff, append, replace_old))
    if kinds != 1:
        raise LearnError("indica UN cambio: --diff FILE, --append FILE|--text TESTO, oppure --replace FILE --with FILE")
    if append is not None:
        change_kind = "append"
        new_text = insert_in_section(original, append, anchor)
        diff = make_diff(rel, original, new_text)
    elif replace_old is not None:
        change_kind = "replace"
        if replace_new is None:
            raise LearnError("--replace richiede --with")
        if original.count(replace_old) != 1:
            raise LearnError("il testo da sostituire deve comparire esattamente una volta nel file")
        new_text = original.replace(replace_old, replace_new)
        diff = make_diff(rel, original, new_text)
    else:
        change_kind = "diff"
        new_text = apply_unified_diff(original, diff or "")
        diff = make_diff(rel, original, new_text)   # normalizzato: intestazioni a/ b/ relative al plugin
    if new_text == original:
        raise LearnError("il cambio non modifica il file")
    problems = hard_rule_check(rel, original, diff)
    if problems:
        raise LearnError("proposta rifiutata, regole dure: " + "; ".join(problems))
    added = "\n".join(ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
    # tutto quello che finisce nel commit o nella PR passa dal filtro, anche la decisione dell'operatore e l'àncora
    priv, warns = privacy_check(conn, [title, rationale or "", added, operator_decision or "", anchor or "", slug or ""]
                                + [lv["text"] for lv in lessons])
    if priv:
        raise LearnError("proposta rifiutata, filtro di privacy (13 §9.2): " + "; ".join(priv))
    hard_note = "nessuna"
    if rel in THRESHOLD_TARGETS or rel.startswith("scripts/yt/lib/"):
        risk = "alto"
        hard_note = "tocca soglie o codice del toolkit: verificare a mano che stringa (H8)"
        if not operator_decision:
            warns.append("cambio su soglie o codice: se allenta, serve la decisione scritta dell'operatore "
                         "(--operator-decision) dentro la PR")
    ev_ids = sorted({e["event"] for lv in lessons for e in jload(lv["evidence_json"], []) or []
                     if e.get("event") and not e.get("retracted")} | set(evidence or []))
    n = max(lv["n_jobs"] for lv in lessons)
    signals = sorted({lv.get("signal") or "scelte" for lv in lessons})
    day = today()
    base_slug = proposal_slug(slug or title)          # --slug passa dallo stesso slugify: diventa un nome di branch
    pid = f"{day}-{base_slug}"
    k = 2
    while conn.execute("SELECT 1 FROM learn_proposals WHERE id=?", (pid,)).fetchone():
        pid = f"{day}-{base_slug}-{k}"
        k += 1
    pdir = proposals_dir()
    pdir.mkdir(parents=True, exist_ok=True)
    prop = {
        "id": pid, "title": title, "state": "in_attesa", "created": now_iso(), "scope": scope,
        "channel": sorted(channels)[0], "lessons": [{"id": lv["id"], "text": lv["text"], "n": lv["n_jobs"],
                                                       "state": lv["state"]} for lv in lessons],
        "evidence": [f"e{i}" for i in ev_ids], "n": n, "signal": signals, "rationale": rationale,
        "risk": risk or "basso", "hard_rules": hard_note, "privacy": "superato" + (f" (avvisi: {len(warns)})" if warns else ""),
        "warnings": warns, "operator_decision": operator_decision,
        "changes": [{"target": rel, "target_repo": f"{REPO_PLUGIN_SUBDIR}/{rel}", "kind": change_kind,
                     "anchor": anchor, "diff": diff, "sha256_before": hashlib.sha256(original.encode()).hexdigest(),
                     **({"block": append} if change_kind == "append" else {}),
                     **({"old": replace_old, "new": replace_new} if change_kind == "replace" else {})}],
        "branch": f"learn/{pid}", "commit_message": f"{title}\n\n" + _commit_body(pid, lessons, ev_ids, rationale),
        "co_authored_by": CO_AUTHOR,
    }
    jpath, mpath = pdir / f"{pid}.json", pdir / f"{pid}.md"
    yc.write_json(jpath, prop)
    mpath.write_text(proposal_markdown(prop))
    now = now_iso()
    with conn:
        conn.execute("INSERT INTO learn_proposals(id, channel, scope, title, state, targets_json, lesson_ids_json, "
                     "evidence_json, risk, hard_rule, json_path, md_path, created_at, updated_at) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (pid, prop["channel"], scope, title, "in_attesa", canon([rel]), canon(lesson_ids),
                      canon(prop["evidence"]), prop["risk"], hard_note, str(jpath), str(mpath), now, now))
        for lv in lessons:
            conn.execute("UPDATE learn_lessons SET state='proposta', proposal_id=?, updated_at=? WHERE id=?",
                         (pid, now, lv["id"]))
    return {"id": pid, "json": str(jpath), "md": str(mpath), "target": rel, "kind": change_kind, "risk": prop["risk"],
            "hard_rules": hard_note, "warnings": warns, "diff_lines": diff.count("\n")}


def _commit_body(pid: str, lessons: list[dict], ev_ids: list[int], rationale: str | None) -> str:
    lines = [f"Proposta di apprendimento {pid} (Tier B, 13-learning-loop.md §9)."]
    if rationale:
        lines.append(rationale)
    lines += [f"Lezione L{lv['id']}: {lv['text']} (n={lv['n_jobs']})" for lv in lessons]
    lines.append(f"Prove locali: {', '.join('e' + str(i) for i in ev_ids[:20]) or 'nessuna'}")
    return "\n".join(lines) + f"\n\n{CO_AUTHOR}\n"


def proposal_markdown(p: dict) -> str:
    ch = p["changes"][0]
    L = [f"# Proposta {p['id']} — {p['title']}", "",
         f"- **Stato**: {p['state']} · **ambito**: {p['scope']} ({p['channel']}) · **rischio**: {p['risk']}",
         f"- **File**: `{ch['target_repo']}` ({ch['kind']})",
         f"- **Prove**: {', '.join(p['evidence']) or '—'} · n={p['n']} · segnale: {', '.join(p['signal'])}",
         f"- **Regole dure**: {p['hard_rules']} · **privacy**: {p['privacy']}", ""]
    if p.get("rationale"):
        L += ["## Perché", p["rationale"], ""]
    L += ["## Lezioni"] + [f"- L{lv['id']} ({lv['state']}, n={lv['n']}): {lv['text']}" for lv in p["lessons"]] + [""]
    if p.get("operator_decision"):
        L += ["## Decisione dell'operatore", p["operator_decision"], ""]
    if p.get("warnings"):
        L += ["## Avvisi"] + [f"- {w}" for w in p["warnings"]] + [""]
    L += ["## Cambio", "```diff", ch["diff"].rstrip("\n"), "```", ""]
    return "\n".join(L)


def proposals_list(conn: sqlite3.Connection, state: str | None = "in_attesa", channel: str | None = None) -> list[dict]:
    sql = "SELECT * FROM learn_proposals WHERE 1=1"
    params: list[Any] = []
    if state:
        sql += " AND state=?"
        params.append(state)
    if channel:
        sql += " AND channel=?"
        params.append(channel)
    out = []
    for r in conn.execute(sql + " ORDER BY created_at", params):
        d = dict(r)
        d["targets"] = jload(d.pop("targets_json"), [])
        d["lessons"] = jload(d.pop("lesson_ids_json"), [])
        d["evidence"] = jload(d.pop("evidence_json"), [])
        out.append(d)
    return out


# ═══ propose-pr (solo sessione principale) ═══════════════════════════════════
def git(repo: Path, *args: str, check: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env={**os.environ, **(env or {})})
    if check and proc.returncode != 0:
        raise LearnError(f"git {' '.join(args)}: {proc.stderr.strip()[-500:]}")
    return proc


BRANCH_RX = re.compile(r"^learn/[a-z0-9][a-z0-9._-]{0,90}$")


def _check_branch(top: Path, branch: str, base: str) -> None:
    """Solo learn/<data>-<slug>, mai main: il nome viene dal JSON della proposta, quindi si ricontrolla qui."""
    if not BRANCH_RX.fullmatch(branch or "") or ".." in branch or branch.endswith((".lock", ".", "/")) \
            or branch in (f"learn/{base}", "learn/main", "learn/master"):
        raise LearnError(f"branch non ammesso: {branch!r} (solo learn/<data>-<slug>; mai main)")
    if git(top, "check-ref-format", "--branch", branch, check=False).returncode != 0:
        raise LearnError(f"branch non valido per git: {branch!r}")


def proposal_stale(conn: sqlite3.Connection, p: dict) -> str | None:
    """Motivo per cui una proposta in attesa non va più in PR: una sua lezione è stata ritirata, o le prove rimaste
    (dopo ritrattazioni) non bastano più per «pronta» (13 §10: il rollback locale vale anche per il Tier B)."""
    st = settings()
    for ref in p.get("lessons") or []:
        lid = ref.get("id") if isinstance(ref, dict) else ref
        try:
            lv = lesson_get(conn, int(lid))
        except (LearnError, TypeError, ValueError):
            return f"lezione L{lid} inesistente"
        if lv["state"] == "ritirata":
            return f"lezione L{lid} ritirata ({lv.get('retired_reason') or 'senza motivo'})"
        ev = jload(lv.get("evidence_json"), []) or []
        ids = [int(e["event"]) for e in ev if e.get("event")]
        gone = {r[0] for r in conn.execute(
            f"SELECT id FROM learn_events WHERE retracted_at IS NOT NULL AND id IN ({','.join('?' * len(ids))})", ids)} \
            if ids else set()
        for e in ev:                                  # ritrattazioni lette dal registro, non dalla copia nella lezione
            e["retracted"] = bool(e.get("retracted")) or e.get("event") in gone
        live = dict(lv, state="candidata", evidence_json=canon(ev))   # stato dalle sole prove vive, senza «proposta»
        if lesson_state(live, st) != "pronta":
            n, _, _ = _lesson_counts(lv)
            return f"lezione L{lid}: prove vive insufficienti (n={n}, servono {st['min_evidence']} o un esito decisivo)"
    return None


def withdraw_stale_proposals(conn: sqlite3.Connection, channel: str | None = None) -> list[dict]:
    """Ritira le proposte in attesa che non reggono più (lezione ritirata o prove ritrattate)."""
    out = []
    for p in proposals_list(conn, "in_attesa", channel):
        why = proposal_stale(conn, {"lessons": p["lessons"]})
        if why:
            set_proposal_state(conn, p["id"], "ritirata")
            jp = Path(p["json_path"]) if p.get("json_path") else None
            data = _read(jp) if jp else None
            if isinstance(data, dict):
                data.update({"state": "ritirata", "withdrawn_reason": why, "withdrawn_at": now_iso()})
                yc.write_json(jp, data)
            out.append({"id": p["id"], "reason": why})
    return out


def propose_pr(conn: sqlite3.Connection, *, repo: Path, ids: list[str] | None = None, dry_run: bool = False,
               no_pr: bool = False, remote: str = "origin", base: str = "main", fetch: bool = True,
               validate: bool = True) -> dict:
    repo = Path(repo).expanduser()
    if not (repo / ".git").exists():
        raise LearnError(f"{repo} non è un clone git (repo_path). Clona lì la repo del plugin (git clone <url della repo> "
                         f"{repo}) oppure imposta repo_path nel config.yaml (yt-config)")
    top = Path(git(repo, "rev-parse", "--show-toplevel").stdout.strip())
    if not (top / REPO_PLUGIN_SUBDIR / ".claude-plugin" / "plugin.json").is_file():
        raise LearnError(f"{top} non contiene {REPO_PLUGIN_SUBDIR}/.claude-plugin/plugin.json: non è la repo del plugin")
    dirty = git(top, "status", "--porcelain").stdout.strip()
    if dirty:
        raise LearnError(f"il clone {top} ha modifiche non committate: niente PR (mai stash né reset sul lavoro "
                         "dell'operatore)")
    if base in ("", "HEAD") or base.startswith("learn/"):
        raise LearnError(f"--base {base!r} non ammesso: le PR di apprendimento puntano a main")
    withdrawn = [] if dry_run else withdraw_stale_proposals(conn)
    props = [p for p in proposals_list(conn, "in_attesa") if not ids or p["id"] in ids]
    if ids and len(props) != len(set(ids)):
        missing = sorted(set(ids) - {p["id"] for p in props})
        raise LearnError(f"proposte non in attesa o inesistenti: {', '.join(missing)}"
                         + (f" (ritirate ora: {', '.join(w['id'] for w in withdrawn)})" if withdrawn else ""))
    if not props:
        return {"repo": str(top), "dry_run": dry_run, "results": [], "withdrawn": withdrawn,
                "note": "nessuna proposta in attesa"}
    if fetch:
        git(top, "fetch", remote, base)
    base_ref = f"{remote}/{base}"
    git(top, "rev-parse", "--verify", base_ref)
    results, errors = [], 0
    for p in props:
        data = _read(Path(p["json_path"]))
        try:
            if not isinstance(data, dict):
                raise LearnError(f"proposta {p['id']}: file JSON illeggibile ({p['json_path']})")
            why = proposal_stale(conn, data)
            if why:                      # in dry-run non si ritira niente: si dice soltanto che non andrebbe in PR
                raise LearnError(f"proposta {p['id']} non più valida: {why}")
            results.append(_one_pr(conn, top, data, base_ref, base, remote, dry_run, no_pr, validate))
        except LearnError as exc:       # una proposta che non passa non blocca le altre del gruppo
            errors += 1
            results.append({"id": p["id"], "error": str(exc)})
    if errors and errors == len(results):
        raise LearnError(("nessuna proposta passerebbe: " if dry_run else "nessuna proposta è andata in PR: ")
                         + " · ".join(r["error"] for r in results))
    return {"repo": str(top), "dry_run": dry_run, "results": results, "errors": errors, "withdrawn": withdrawn}


def _free_branch(top: Path, remote: str, branch: str) -> tuple[str, str | None]:
    """Un branch learn/… già sul remoto ma non in locale è di un altro clone (l'altro operatore ha scritto una proposta
    con lo stesso titolo lo stesso giorno): si prende il primo suffisso libero (-2, -3…). In locale = nostro: ci si
    ferma (un giro precedente interrotto dopo il push)."""
    def local(b: str) -> bool:
        return git(top, "rev-parse", "--verify", "--quiet", f"refs/heads/{b}", check=False).returncode == 0

    def remote_has(b: str) -> bool:
        return bool(git(top, "ls-remote", "--heads", remote, b, check=False).stdout.strip())

    if local(branch):
        raise LearnError(f"il branch {branch} esiste già in questo clone: proposta già in PR? (yt-learn proposal sync)")
    if not remote_has(branch):
        return branch, None
    for k in range(2, 10):
        cand = f"{branch}-{k}"
        if not local(cand) and not remote_has(cand):
            return cand, f"{branch} è già sul remoto (un altro clone, forse l'altro operatore): uso {cand}"
    raise LearnError(f"il branch {branch} e i suoi suffissi -2…-9 esistono già sul remoto")


def _one_pr(conn: sqlite3.Connection, top: Path, p: dict, base_ref: str, base: str, remote: str, dry_run: bool,
            no_pr: bool, validate: bool) -> dict:
    branch = p.get("branch") or f"learn/{p['id']}"
    _check_branch(top, branch, base)
    rebased = []
    lessons = [lesson_get(conn, int(lv["id"])) for lv in p.get("lessons", [])]
    for ch in p["changes"]:
        rel = norm_target(ch["target"])
        orig = git(top, "show", f"{base_ref}:{REPO_PLUGIN_SUBDIR}/{rel}").stdout
        try:
            new_text = apply_unified_diff(orig, ch["diff"])
        except LearnError:
            # il file su origin/main non è quello da cui è nata la proposta: si rifà il diff dal cambio sorgente
            if ch.get("kind") == "append" and ch.get("block") is not None:
                new_text = insert_in_section(orig, ch["block"], ch.get("anchor"))
            elif ch.get("kind") == "replace" and ch.get("old") is not None and orig.count(ch["old"]) == 1:
                new_text = orig.replace(ch["old"], ch["new"])
            else:
                raise LearnError(f"{p['id']}: {rel} è cambiato su {base_ref} e il diff non si applica più: "
                                 "riscrivere la proposta sul file aggiornato")
            rebased.append(rel)
        # il diff si rigenera sempre dal testo: le intestazioni a/ b/ puntano al solo file controllato (un JSON
        # modificato a mano non può far applicare gli stessi hunk a un altro file)
        ch["diff"] = make_diff(rel, orig, new_text)
        ch["target"], ch["target_repo"] = rel, f"{REPO_PLUGIN_SUBDIR}/{rel}"
        probs = hard_rule_check(rel, orig, ch["diff"])
        if probs:
            raise LearnError(f"{p['id']}: regole dure: {'; '.join(probs)}")
    added = "\n".join(ln[1:] for ch in p["changes"] for ln in ch["diff"].splitlines()
                      if ln.startswith("+") and not ln.startswith("+++"))
    msg = p.get("commit_message") or p["title"]
    if CO_AUTHOR not in msg:
        msg = msg.rstrip("\n") + f"\n\n{CO_AUTHOR}\n"
    # filtro di privacy su TUTTO quello che esce: diff, titolo, messaggio di commit, corpo della PR, lezioni
    priv, _ = privacy_check(conn, [p["title"], p.get("rationale") or "", added, msg, _pr_body(p),
                                   p.get("operator_decision") or ""] + [lv["text"] for lv in lessons])
    if priv:
        raise LearnError(f"{p['id']}: filtro di privacy: {'; '.join(priv)}")
    branch, collision = _free_branch(top, remote, branch)
    _check_branch(top, branch, base)
    patch = "".join(ch["diff"] for ch in p["changes"])
    tmpd = Path(tempfile.mkdtemp(prefix="yt-learn-"))
    patch_file = tmpd / "change.patch"
    patch_file.write_text(patch)
    plan = {"id": p["id"], "branch": branch, "base": base_ref, "files": [c["target_repo"] for c in p["changes"]],
            "privacy": "superato", "hard_rules": p.get("hard_rules", "nessuna"), "rebased": rebased,
            **({"note": collision} if collision else {})}
    try:
        idx = tmpd / "index"
        env = {"GIT_INDEX_FILE": str(idx)}
        git(top, "read-tree", base_ref, env=env)
        git(top, "apply", "--cached", "--check", f"--directory={REPO_PLUGIN_SUBDIR}", str(patch_file), env=env)
        plan["apply_check"] = "ok"
        if dry_run:
            plan["would_run"] = [f"git worktree add -b {branch} <tmp> {base_ref}",
                                 f"git apply --index --directory={REPO_PLUGIN_SUBDIR} <patch>",
                                 f"claude plugin validate {REPO_PLUGIN_SUBDIR}", "git commit (Co-Authored-By)",
                                 f"git push {remote} HEAD:refs/heads/{branch}",
                                 "" if no_pr else f"gh pr create --draft --base {base} --head {branch}"]
            plan["would_run"] = [c for c in plan["would_run"] if c]
            return plan
        wt = tmpd / "wt"
        git(top, "worktree", "add", "-b", branch, str(wt), base_ref)
        pushed = False
        try:
            git(wt, "apply", "--index", f"--directory={REPO_PLUGIN_SUBDIR}", str(patch_file))
            changed = [x for x in git(wt, "diff", "--cached", "--name-only").stdout.split() if x]
            if sorted(changed) != sorted(plan["files"]):
                raise LearnError(f"il commit toccherebbe file diversi da quelli della proposta: {changed}")
            if validate:
                v = _plugin_validate(wt / REPO_PLUGIN_SUBDIR)
                plan["validate"] = v["status"]
                if v["status"] == "fallita":
                    raise LearnError(f"claude plugin validate fallita: {v['output'][-400:]}")
            git(wt, "commit", "-q", "-m", msg)
            git(wt, "push", "-q", remote, f"HEAD:refs/heads/{branch}")
            pushed = True
            plan["commit"] = git(wt, "rev-parse", "HEAD").stdout.strip()
            if not no_pr:
                body = _pr_body(p)
                proc = subprocess.run(["gh", "pr", "create", "--draft", "--base", base, "--head", branch,
                                       "--title", p["title"], "--body", body], cwd=str(wt), capture_output=True, text=True)
                if proc.returncode != 0:
                    plan["pr_error"] = proc.stderr.strip()[-400:]
                    plan["pr_manual"] = f"gh pr create --draft --base {base} --head {branch}"
                else:
                    plan["pr_url"] = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else None
        finally:
            git(top, "worktree", "remove", "--force", str(wt), check=False)
            if not pushed:
                git(top, "branch", "-D", branch, check=False)
        state = "in_pr" if pushed else "in_attesa"
        with conn:
            conn.execute("UPDATE learn_proposals SET state=?, branch=?, pr_url=?, updated_at=? WHERE id=?",
                         (state, branch, plan.get("pr_url"), now_iso(), p["id"]))
        jp = proposals_dir() / f"{p['id']}.json"
        if jp.exists():
            p.update({"state": state, "branch": branch, "pr_url": plan.get("pr_url"), "commit": plan.get("commit")})
            yc.write_json(jp, p)
        return plan
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)


def proposals_sync(conn: sqlite3.Connection) -> list[dict]:
    """Stato delle PR aperte da propose-pr, letto con gh (sola lettura): MERGED → accettata, CLOSED → respinta."""
    out = []
    exe = shutil.which("gh")
    for p in proposals_list(conn, "in_pr"):
        if not p.get("pr_url") or not exe:
            out.append({"id": p["id"], "state": "in_pr", "note": "senza URL della PR o senza gh"})
            continue
        proc = subprocess.run([exe, "pr", "view", p["pr_url"], "--json", "state"], capture_output=True, text=True)
        state = (jload(proc.stdout, {}) or {}).get("state") if proc.returncode == 0 else None
        new = {"MERGED": "accettata", "CLOSED": "respinta"}.get(state or "")
        if new:
            set_proposal_state(conn, p["id"], new)
        out.append({"id": p["id"], "pr": p["pr_url"], "gh_state": state, "state": new or "in_pr"})
    return out


def set_proposal_state(conn: sqlite3.Connection, pid: str, state: str) -> int:
    with conn:
        n = conn.execute("UPDATE learn_proposals SET state=?, updated_at=? WHERE id=?", (state, now_iso(), pid)).rowcount
        if n and state in ("respinta", "ritirata"):
            # la lezione resta di Tier A (attiva o pronta): perde solo il passo di Tier B
            conn.execute("UPDATE learn_lessons SET state='attiva', proposal_id=NULL, updated_at=? "
                         "WHERE proposal_id=? AND state='proposta'", (now_iso(), pid))
    return n


def _plugin_validate(path: Path) -> dict:
    exe = shutil.which("claude")
    if not exe:
        return {"status": "non disponibile", "output": ""}
    proc = subprocess.run([exe, "plugin", "validate", str(path)], capture_output=True, text=True)
    return {"status": "ok" if proc.returncode == 0 else "fallita", "output": proc.stdout + proc.stderr}


def _pr_body(p: dict) -> str:
    ch = p["changes"][0]
    L = ["## Cosa cambia", f"Proposta di apprendimento `{p['id']}` (Tier B, `13-learning-loop.md` §9): "
         f"`{ch['target_repo']}` ({ch['kind']}).", "", "## Perché"]
    L.append(p.get("rationale") or "—")
    L += [f"- Lezione L{lv['id']} ({lv['state']}, n={lv['n']}): {lv['text']}" for lv in p.get("lessons", [])]
    L += ["", "## Prove", f"Id locali (yt.db di chi ha generato la proposta): {', '.join(p.get('evidence') or []) or '—'} "
          f"· n={p.get('n')} · segnale: {', '.join(p.get('signal') or [])}.", "",
          "## Controlli", f"- Regole dure (13 §2): {p.get('hard_rules', 'nessuna')}",
          f"- Privacy (13 §9.2): {p.get('privacy', 'superato')}", f"- Rischio: {p.get('risk', 'basso')}",
          "- `claude plugin validate` sul branch prima del push", ""]
    if p.get("operator_decision"):
        L += ["## Decisione dell'operatore", p["operator_decision"], ""]
    if p.get("warnings"):        # es. «tocca soglie o codice»: chi revisiona deve vederlo nella PR, non solo in locale
        L += ["## Avvisi da verificare in revisione"] + [f"- {w}" for w in p["warnings"]] + [""]
    L += ["## Per chi usa il plugin", "Nessun nuovo setup: cambia il comportamento dell'agente dal prossimo "
          "aggiornamento del plugin (`claude plugin marketplace update youtube-producer`, poi "
          "`claude plugin update youtube@youtube-producer`, riavvio di Claude Code; README «Aggiornare»). "
          "Merge solo umano, da chi gestisce la repo (CONTRIBUTING.md), mai auto-merge.", "",
          PR_FOOTER]
    return "\n".join(L)


# ═══ CLI ═════════════════════════════════════════════════════════════════════
def _parse_arms(values: list[str] | None) -> dict[str, str]:
    out = {}
    for v in values or []:
        if "=" not in v:
            raise LearnError(f"--arm {v}: forma A=<render>")
        a, ref = v.split("=", 1)
        out[a.strip()] = ref.strip()
    return out


def _read_text_arg(value: str | None) -> str | None:
    if value is None:
        return None
    p = Path(value).expanduser()
    if p.is_file():
        return p.read_text()
    raise LearnError(f"file assente: {value}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="yt-learn", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", help="database (default <studio>/data/yt.db)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("job", help="registro dei lavori: job WORKDIR --status … oppure job start|end|show|list")
    p.add_argument("args", nargs="*", help="start|end|show|list, oppure il workdir")
    p.add_argument("--channel")
    p.add_argument("--workdir")
    p.add_argument("--skill", action="append", help="skill o flusso (ripetibile, anche a virgole)")
    p.add_argument("--status", help="aperto | consegnato | parziale | bloccato | in attesa di approvazione G1 …")
    p.add_argument("--id", help="id del job (job end/show)")
    p.add_argument("--video-id")
    p.add_argument("--gates", help="stato dei gate in JSON, es. '{\"G1\": \"approved\"}'")
    p.add_argument("--operator")
    p.add_argument("--note")
    p.add_argument("--no-update", action="store_true", help="job end senza ricalcolo di priori e playbook")

    p = sub.add_parser("ingest", help="registra proposte, scelte, feature e metriche QA dagli artefatti (idempotente)")
    p.add_argument("workdir")
    p.add_argument("--skill", action="append")

    p = sub.add_parser("decision", help="decisione dell'operatore a un gate (verbatim)")
    p.add_argument("workdir", nargs="?")
    p.add_argument("--channel")
    p.add_argument("--gate")
    p.add_argument("--skill")
    p.add_argument("--offered", action="append")
    p.add_argument("--chosen", action="append")
    p.add_argument("--rejected", action="append")
    p.add_argument("--reason", help="il motivo, solo con le parole dell'operatore")
    p.add_argument("--text", help="la risposta dell'operatore, verbatim")
    p.add_argument("--operator", "--who", dest="operator")
    p.add_argument("--delegated", action="store_true", help="scelta dell'agente su delega: nessun peso nelle «scelte»")
    p.add_argument("--hypothesis", help="ipotesi dell'agente sul perché [giudizio], separata dal motivo")
    p.add_argument("--job")

    p = sub.add_parser("correction", help="correzione dell'operatore (transcript allarga il glossario appreso)")
    p.add_argument("--channel")
    p.add_argument("--kind", required=True)
    p.add_argument("--from", "--before", dest="before", default="")
    p.add_argument("--to", "--after", dest="after", required=True)
    p.add_argument("--context")
    p.add_argument("--workdir")
    p.add_argument("--job")
    p.add_argument("--operator")

    for name in ("outcome", "outcomes"):
        p = sub.add_parser(name, help="esiti: pull | add | list | reviewed")
        p.add_argument("action", nargs="?", default="pull", choices=["pull", "add", "list", "reviewed"])
        p.add_argument("--channel")
        p.add_argument("--video-id")
        p.add_argument("--checkpoint", choices=list(CHECKPOINTS))
        p.add_argument("--due", action="store_true", help="solo quelli dovuti (default di pull)")
        p.add_argument("--refresh", action="store_true", help="ricalcola anche gli esiti già letti dal database")
        p.add_argument("--verdict")
        p.add_argument("--value", type=float)
        p.add_argument("--baseline", type=float)
        p.add_argument("--n-baseline", type=int)
        p.add_argument("--metric")
        p.add_argument("--ctr", type=float)
        p.add_argument("--impressions", type=int)
        p.add_argument("--avd", type=float)
        p.add_argument("--intro", type=float, help="Intro a 0:30 (Studio)")
        p.add_argument("--ab-winner")
        p.add_argument("--ab-result", choices=["winner", "same", "inconclusive"])
        p.add_argument("--note")

    p = sub.add_parser("priors", help="priori: show | update")
    p.add_argument("action", nargs="?", default="show", choices=["show", "update"])
    p.add_argument("--channel", required=True)
    p.add_argument("--focus")
    p.add_argument("--feature")

    p = sub.add_parser("update", help="ricalcola priori, lezioni, glossario appreso e soglie del canale")
    p.add_argument("--channel", required=True)

    p = sub.add_parser("suggest", help="sfruttamento + esplorazione (Thompson) dai priori")
    p.add_argument("--channel", required=True)
    p.add_argument("--focus", "--skill", dest="focus", default="thumbnail")
    p.add_argument("--candidates", help="JSON: lista di concept o {key, features}")
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--explore", type=int)
    p.add_argument("--seed", type=int)

    for name in ("lesson", "lessons"):
        p = sub.add_parser(name, help="lezioni: add | list | show | confirm | contra | retire")
        p.add_argument("action", choices=["add", "list", "show", "confirm", "contra", "retire"])
        p.add_argument("id", nargs="?", type=int)
        p.add_argument("--channel")
        p.add_argument("--text")
        p.add_argument("--skill")
        p.add_argument("--scope", default="channel", choices=["channel", "global"])
        p.add_argument("--evidence", action="append", help="id degli eventi (e12,e15)")
        p.add_argument("--key")
        p.add_argument("--signal", choices=list(SIGNALS))
        p.add_argument("--decisive", action="store_true", help="prova decisiva (A/B con vincitore, pre-test superato)")
        p.add_argument("--contra", action="store_true", help="con add: la prova contraddice la lezione")
        p.add_argument("--state", choices=list(LESSON_STATES))
        p.add_argument("--reason")

    for name in ("threshold", "thresholds"):
        p = sub.add_parser(name, help="soglie apprese più severe: set | list | retire")
        p.add_argument("action", choices=["set", "list", "retire"])
        p.add_argument("--channel", required=True)
        p.add_argument("--name")
        p.add_argument("--min", type=float)
        p.add_argument("--max", type=float)
        p.add_argument("--baseline", type=float, help="valore del toolkit (se la soglia non è tra quelle note)")
        p.add_argument("--level", choices=["warn", "error"])
        p.add_argument("--lesson", type=int)
        p.add_argument("--note")

    p = sub.add_parser("report", help="JSON compatto + rigenera il playbook")
    p.add_argument("--channel")
    p.add_argument("--focus")
    p.add_argument("--proposals", action="store_true", help="solo le proposte in attesa")
    p.add_argument("--no-update", action="store_true")

    p = sub.add_parser("playbook", help="rigenera <studio>/data/learned/<canale>.md")
    p.add_argument("--channel", required=True)

    p = sub.add_parser("due", help="esiti e review dovuti, proposte in attesa")
    p.add_argument("--channel")

    p = sub.add_parser("propose", help="scrive una proposta di miglioramento (Tier B) in <studio>/data/proposals/")
    p.add_argument("--title", required=True)
    p.add_argument("--lesson", action="append", type=int, required=True)
    p.add_argument("--target", required=True, help="file del plugin (relativo alla radice del plugin o della repo)")
    p.add_argument("--diff", help="file con un diff unificato")
    p.add_argument("--append", help="file con il blocco da aggiungere")
    p.add_argument("--text", help="blocco da aggiungere, in linea")
    p.add_argument("--anchor", help="intestazione: il blocco va in fondo a quella sezione")
    p.add_argument("--replace", help="file con il testo da sostituire (una sola occorrenza)")
    p.add_argument("--with", dest="with_", help="file con il testo nuovo")
    p.add_argument("--rationale")
    p.add_argument("--risk", choices=["basso", "medio", "alto"])
    p.add_argument("--slug")
    p.add_argument("--operator-decision", help="decisione scritta dell'operatore (obbligatoria per allentare)")
    p.add_argument("--evidence", action="append")

    p = sub.add_parser("propose-pr", help="SOLO sessione principale: branch learn/…, commit, push, PR draft")
    p.add_argument("--repo", help="clone della repo (default repo_path di yt-config)")
    p.add_argument("--id", action="append")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-pr", action="store_true", help="push del branch senza gh pr create")
    p.add_argument("--no-fetch", action="store_true")
    p.add_argument("--no-validate", action="store_true")
    p.add_argument("--remote", default="origin")
    p.add_argument("--base", default="main")

    p = sub.add_parser("proposal", help="esito di una proposta: <id> --state accettata|respinta|ritirata, "
                                        "oppure «sync» (stato delle PR con gh, sola lettura)")
    p.add_argument("id")
    p.add_argument("--state", choices=["accettata", "respinta", "ritirata"])
    p.add_argument("--note")

    p = sub.add_parser("publish", help="collega la versione pubblicata (video id, braccia A/B) e il golden set")
    p.add_argument("--channel")
    p.add_argument("--video-id", required=True)
    p.add_argument("--workdir")
    p.add_argument("--arm", action="append", help="A=<render> (ripetibile)")
    p.add_argument("--published-at")
    p.add_argument("--ab-test", type=int)
    p.add_argument("--kind", default="long", choices=["long", "short"])
    p.add_argument("--no-golden", action="store_true")
    p.add_argument("--note")

    p = sub.add_parser("golden", help="golden set delle thumbnail pubblicate")
    p.add_argument("action", nargs="?", default="list", choices=["list"])
    p.add_argument("--channel")

    p = sub.add_parser("refs", help="riferimenti di nicchia (≤ 30 giorni): add | list | purge | due")
    p.add_argument("action", choices=["add", "list", "purge", "due"])
    p.add_argument("--channel")
    p.add_argument("--path", action="append")
    p.add_argument("--source", default="yt-research")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--all", action="store_true")

    p = sub.add_parser("retract", help="ritratta un evento (append-only): i priori si ricalcolano")
    p.add_argument("event")
    p.add_argument("--reason", required=True)
    return ap


def _channel_or_wd(args: argparse.Namespace) -> tuple[str, Path | None]:
    wd = resolve_wd(args.workdir) if getattr(args, "workdir", None) else None
    ch = getattr(args, "channel", None) or (workdir_channel(wd) if wd else None)
    if not ch:
        raise LearnError("serve --channel oppure un workdir")
    return check_slug(ch), wd


def run(args: argparse.Namespace) -> dict:
    conn = connect(args.db)
    cmd = args.cmd
    if cmd == "job":
        acts = args.args or []
        action = acts[0] if acts and acts[0] in ("start", "end", "show", "list") else None
        wd_arg = args.workdir or (acts[1] if action and len(acts) > 1 else (acts[0] if acts and not action else None))
        wd = resolve_wd(wd_arg) if wd_arg else None
        channel = args.channel or (workdir_channel(wd) if wd else None)
        skills = [norm_skill(s) or s for s in split_list(args.skill)] if args.skill else None
        gates = jload(args.gates, None) if args.gates else None
        if gates is None and wd:
            try:
                gates = (yc.load_project(wd) or {}).get("gates")
            except (OSError, ValueError):
                gates = None
        if action == "list":
            sql = "SELECT * FROM learn_jobs" + (" WHERE channel=?" if channel else "") + " ORDER BY started_at DESC LIMIT 50"
            return {"jobs": [dict(r) for r in conn.execute(sql, (channel,) if channel else ())]}
        if action == "show":
            jid = args.id or (open_job(conn, channel, wd) or {}).get("id") if (args.id or channel) else None
            r = conn.execute("SELECT * FROM learn_jobs WHERE id=?", (jid,)).fetchone() if jid else None
            if not r:
                raise LearnError("job non trovato")
            return {"job": dict(r), "events": job_summary(conn, r["id"])}
        if not channel:
            raise LearnError("serve --channel oppure il workdir")
        if action == "start" or (not action and (not args.status or args.status == "aperto")):
            j = job_start(conn, check_slug(channel), wd, skills, args.id, args.operator, args.video_id)
            return {"job": j}
        status = args.status or "consegnato"
        jid = args.id or (open_job(conn, channel, wd) or {}).get("id") or \
            job_start(conn, check_slug(channel), wd, skills, None, args.operator, args.video_id)["id"]
        j = job_end(conn, jid, status, args.note, gates, args.video_id, skills)
        out = {"job": j, "events": job_summary(conn, jid)}
        if not args.no_update:
            out["update"] = update_channel(conn, channel)
            path, n = write_playbook(conn, channel)
            out["playbook"], out["playbook_lines"] = str(path), n
            out["due"] = {k: (len(v) if isinstance(v, list) else v) for k, v in due_items(conn, channel).items()
                          if k != "proposals"}
        return out
    if cmd == "ingest":
        return ingest(conn, resolve_wd(args.workdir), split_list(args.skill))
    if cmd == "decision":
        wd = resolve_wd(args.workdir) if args.workdir else None
        channel = args.channel or (workdir_channel(wd) if wd else None)
        if not channel:
            raise LearnError("serve il workdir oppure --channel")
        return record_decision(conn, channel=check_slug(channel), workdir=wd, gate=args.gate, skill=args.skill,
                               offered=split_list(args.offered), chosen=split_list(args.chosen),
                               rejected=split_list(args.rejected), reason=args.reason, text=args.text,
                               operator=args.operator, delegated=args.delegated, hypothesis=args.hypothesis,
                               job_id=args.job)
    if cmd == "correction":
        channel, wd = _channel_or_wd(args)
        return record_correction(conn, channel=channel, kind=args.kind, before=args.before, after=args.after,
                                 context=args.context, workdir=wd, job_id=args.job, operator=args.operator)
    if cmd in ("outcome", "outcomes"):
        if args.action == "pull":
            res = pull_outcomes(conn, args.channel, args.video_id, args.checkpoint, args.refresh)
            thumb = None
            try:          # stessi checkpoint per le thumbnail (CTR, pari età, A/B): un solo comando in /youtube:review
                tl = _tl()
                tl.ensure_schema(conn)
                thumb = tl.pull_outcomes(conn, args.channel, args.video_id)
            except Exception as exc:  # noqa: BLE001
                thumb = {"error": f"yt-thumb-learn outcomes: {type(exc).__name__}: {exc}"}
            if args.channel:
                update_priors(conn, args.channel)
            else:
                for ch in {r["channel"] for r in res}:
                    update_priors(conn, ch)
            return {"pulled": res, "count": len(res),
                    "thumbnail": {k: v for k, v in (thumb or {}).items() if k in ("pulled", "skipped", "error")}}
        if args.action == "add":
            if not args.video_id or not args.checkpoint:
                raise LearnError("outcome add: --video-id e --checkpoint obbligatori")
            res = outcome_manual(conn, channel=args.channel, video_id=args.video_id, checkpoint=args.checkpoint,
                                 verdict=args.verdict, value=args.value, baseline=args.baseline,
                                 n_baseline=args.n_baseline, metric=args.metric, ctr=args.ctr,
                                 impressions=args.impressions, avd=args.avd, intro=args.intro, ab_winner=args.ab_winner,
                                 ab_result=args.ab_result, note=args.note)
            update_priors(conn, res["channel"])
            return res
        if args.action == "reviewed":
            if not args.video_id or not args.checkpoint:
                raise LearnError("outcome reviewed: --video-id e --checkpoint obbligatori")
            with conn:
                n = conn.execute("UPDATE learn_outcomes SET reviewed_at=? WHERE video_id=? AND checkpoint=?",
                                 (now_iso(), args.video_id, args.checkpoint)).rowcount
            return {"reviewed": n}
        sql = "SELECT * FROM learn_outcomes" + (" WHERE channel=?" if args.channel else "") + " ORDER BY created_at DESC"
        return {"outcomes": [dict(r) for r in conn.execute(sql, (args.channel,) if args.channel else ())]}
    if cmd == "priors":
        ch = check_slug(args.channel)
        if args.action == "update":
            return update_priors(conn, ch)
        return {"channel": ch, "priors": prior_rows(conn, ch, norm_focus(args.focus), args.feature)}
    if cmd == "update":
        return update_channel(conn, args.channel)
    if cmd == "suggest":
        cands = None
        if args.candidates:
            data = _read(Path(args.candidates).expanduser())
            cands = _concepts(data)
            if not cands:
                raise LearnError(f"--candidates: nessun concept leggibile in {args.candidates}")
        return suggest(conn, check_slug(args.channel), norm_focus(args.focus) or "thumbnail", cands, args.k,
                       args.explore, args.seed)
    if cmd in ("lesson", "lessons"):
        if args.action == "add":
            if not args.channel:
                raise LearnError("lesson add: --channel obbligatorio")
            return lesson_add(conn, channel=args.channel, text=args.text or "", skill=args.skill, scope=args.scope,
                              evidence=parse_event_ids(args.evidence), key=args.key, signal=args.signal,
                              decisive=args.decisive, contra=args.contra)
        if args.action == "list":
            return {"lessons": lessons_list(conn, args.channel, args.state, args.skill)}
        if not args.id:
            raise LearnError(f"lesson {args.action}: serve l'id della lezione")
        if args.action == "show":
            return lesson_view(lesson_get(conn, args.id))
        if args.action == "retire":
            res = lesson_retire(conn, args.id, args.reason or "")
            res["playbook"] = str(write_playbook(conn, res["channel"])[0])      # il rollback vale subito (13 §10)
            return res
        return lesson_evidence(conn, args.id, parse_event_ids(args.evidence), contra=args.action == "contra",
                               decisive=args.decisive)
    if cmd in ("threshold", "thresholds"):
        ch = check_slug(args.channel)
        if args.action == "list":
            return {"thresholds": thresholds_list(conn, ch)}
        if not args.name:
            raise LearnError("--name obbligatorio")
        if args.action == "retire":
            with conn:
                n = conn.execute("UPDATE learn_thresholds SET retired_at=? WHERE channel=? AND name=? AND retired_at IS NULL",
                                 (now_iso(), ch, args.name)).rowcount
            write_thresholds_file(conn, ch)
            return {"retired": n, "playbook": str(write_playbook(conn, ch)[0])}
        if (args.min is None) == (args.max is None):
            raise LearnError("threshold set: esattamente uno tra --min e --max")
        return threshold_set(conn, channel=ch, name=args.name, direction="min" if args.min is not None else "max",
                             value=args.min if args.min is not None else args.max, baseline=args.baseline,
                             level=args.level, lesson_id=args.lesson, note=args.note)
    if cmd == "report":
        if args.proposals:
            return {"proposals": proposals_list(conn, "in_attesa", args.channel)}
        if not args.channel:
            raise LearnError("report: --channel obbligatorio (oppure --proposals)")
        ch = check_slug(args.channel)
        if not args.no_update:
            update_channel(conn, ch)
        return report(conn, ch, norm_focus(args.focus))
    if cmd == "playbook":
        ch = check_slug(args.channel)
        path, n = write_playbook(conn, ch)
        return {"playbook": str(path), "lines": n}
    if cmd == "due":
        return due_items(conn, args.channel)
    if cmd == "propose":
        append = args.text if args.text is not None else _read_text_arg(args.append)
        return propose(conn, title=args.title, lesson_ids=args.lesson, target=args.target,
                       diff=_read_text_arg(args.diff), append=append, anchor=args.anchor,
                       replace_old=_read_text_arg(args.replace), replace_new=_read_text_arg(args.with_),
                       rationale=args.rationale, risk=args.risk, slug=args.slug,
                       operator_decision=args.operator_decision, evidence=parse_event_ids(args.evidence))
    if cmd == "propose-pr":
        repo = Path(args.repo).expanduser() if args.repo else (Path(yc.REPO_PATH) if yc.REPO_PATH else None)
        if not repo:
            raise LearnError("repo_path non configurato: --repo DIR")
        return propose_pr(conn, repo=repo, ids=args.id, dry_run=args.dry_run, no_pr=args.no_pr, remote=args.remote,
                          base=args.base, fetch=not args.no_fetch, validate=not args.no_validate)
    if cmd == "proposal":
        if args.id == "sync":
            return {"proposals": proposals_sync(conn)}
        if not args.state:
            raise LearnError("proposal <id> --state accettata|respinta|ritirata (oppure: proposal sync)")
        if not set_proposal_state(conn, args.id, args.state):
            raise LearnError(f"proposta {args.id} inesistente")
        return {"id": args.id, "state": args.state}
    if cmd == "publish":
        channel, wd = _channel_or_wd(args)
        return publish(conn, channel=channel, video_id=args.video_id, workdir=wd, arms=_parse_arms(args.arm),
                       published_at=args.published_at, ab_test=args.ab_test, kind=args.kind, golden=not args.no_golden,
                       note=args.note)
    if cmd == "golden":
        return {"golden": golden_list(conn, args.channel)}
    if cmd == "refs":
        if args.action == "add":
            if not args.channel or not args.path:
                raise LearnError("refs add: --channel e --path obbligatori")
            return refs_add(conn, args.channel, args.path, args.source)
        if args.action == "purge":
            return refs_purge(conn, args.channel, args.days, args.all)
        if args.action == "due":
            return {"refs_refresh": refs_due(conn, args.channel)}
        sql = "SELECT * FROM learn_refs" + (" WHERE channel=?" if args.channel else "") + " ORDER BY fetched_at DESC"
        return {"refs": [dict(r) for r in conn.execute(sql, (args.channel,) if args.channel else ())]}
    if cmd == "retract":
        eid = parse_event_ids([args.event])[0]
        res = retract(conn, eid, args.reason)
        res["update"] = update_channel(conn, res["channel"])
        res["playbook"] = str(write_playbook(conn, res["channel"])[0])
        return res
    raise LearnError(f"comando sconosciuto: {cmd}")


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        out = run(args)
    except LearnError as exc:
        yc.fail(str(exc))
    except sqlite3.Error as exc:
        yc.fail(f"database: {exc}")
    yc.emit(True, **(out if isinstance(out, dict) else {"result": out}))


if __name__ == "__main__":
    main()
