"""Test delle skill Codex (scripts/codex/build_skills.py → codex/skills/, codex/toolkit-commands.txt).

Rigenera le skill in una cartella temporanea e le confronta con quelle nella repo (vecchie = errore), controlla che
`--check` trovi file vecchi, mancanti e in più, che i SKILL.md rispettino le regole di Codex (nome, descrizione,
8.000 byte iniettati, link che restano nel plugin), che gate, «mai pubblicare» e guard ci siano, che non resti niente
di solo Claude Code senza spiegazione e che una copia installata da Codex (senza symlink) passi lo stesso controllo.
Se sul Mac ci sono i validatori di Codex (~/.codex/skills/.system/skill-creator e plugin-creator, con PyYAML), li lancia
in sola lettura; altrimenti quei test vengono saltati.

Niente pytest: assert semplici, tutto in cartelle temporanee. Libreria standard; basta il python3 di sistema.
Uso:
  python3 plugins/youtube/scripts/yt/tests/test_codex_skills.py           # tutti
  python3 plugins/youtube/scripts/yt/tests/test_codex_skills.py check     # solo i test col nome che contiene «check»
"""
from __future__ import annotations

import filecmp
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.dont_write_bytecode = True                  # niente __pycache__ accanto al generatore (repo o cache dei plugin)

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent.parent.parent              # …/plugins/youtube
BUILD = PLUGIN / "scripts" / "codex" / "build_skills.py"
TMP = Path(tempfile.mkdtemp(prefix="yt-codex-skills-test-"))
CODEX_SYSTEM = Path.home() / ".codex" / "skills" / ".system"
HOST_GUIDE = PLUGIN / "codex" / "references" / "codex-host.md"

_spec = importlib.util.spec_from_file_location("build_skills", BUILD)
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)


class Skip(Exception):
    pass


def commands() -> list:
    return sorted(p.stem for p in (PLUGIN / "commands").glob("*.md"))


def run_build(*args, root: Path | None = None, cwd: Path | None = None):
    cmd = [sys.executable, "-B", str(BUILD), *args]
    if root is not None:
        cmd += ["--plugin-root", str(root)]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd or TMP), env=env, timeout=120)


def split_frontmatter(text: str):
    assert text.startswith("---\n"), "manca il frontmatter"
    end = text.index("\n---\n", 4)
    fm = {}
    for line in text[4:end].split("\n"):
        key, _, raw = line.partition(":")
        raw = raw.strip()
        fm[key.strip()] = json.loads(raw) if raw.startswith('"') else raw
    return fm, text[end + 5:]


def generated_files(root: Path) -> list:
    out = []
    skills = root / "codex" / "skills"
    if skills.is_dir():
        out += [p.relative_to(root).as_posix() for p in skills.rglob("*") if p.is_file()]
    if (root / "codex" / "toolkit-commands.txt").exists():
        out.append("codex/toolkit-commands.txt")
    return sorted(out)


def copy_plugin(dst: Path, *, keep_symlinks: bool) -> Path:
    """Copia del plugin. keep_symlinks=False imita l'installazione di Codex: cartelle e file, permessi, niente symlink."""
    for dirpath, dirnames, filenames in os.walk(PLUGIN, followlinks=False):
        rel = Path(dirpath).relative_to(PLUGIN)
        if rel.parts[:1] in (("docs",), ("evals",), ("scripts",)):
            dirnames[:] = []                    # non servono al generatore (che gira dalla repo): copia leggera
            continue
        dirnames[:] = [d for d in dirnames if d != "__pycache__" and not (Path(dirpath) / d).is_symlink()]
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for f in filenames:
            src = Path(dirpath) / f
            if src.is_symlink():
                if keep_symlinks:
                    os.symlink(os.readlink(src), dst / rel / f)
                continue
            shutil.copy2(src, dst / rel / f)
    if not (dst / "codex" / "references" / "codex-host.md").exists():
        # la guida scritta a mano può non esserci ancora: qui serve solo che i link si risolvano
        (dst / "codex" / "references").mkdir(parents=True, exist_ok=True)
        (dst / "codex" / "references" / "codex-host.md").write_text("# segnaposto del test\n", encoding="utf-8")
    return dst


def fresh_copy(name: str, *, keep_symlinks: bool = True) -> Path:
    dst = TMP / name / "youtube"
    copy_plugin(dst, keep_symlinks=keep_symlinks)
    r = run_build(root=dst)
    assert r.returncode == 0, r.stdout + r.stderr
    return dst


# ---------------------------------------------------------------------------- allineamento

def test_generated_up_to_date():
    """Rigenera in una cartella temporanea e confronta byte per byte con codex/ della repo (nei due sensi)."""
    out = TMP / "regen"
    files, _warn, _links = B.generate(PLUGIN)
    B.write_tree(out, files, prune=True)
    expected, current = generated_files(out), generated_files(PLUGIN)
    assert expected, "il generatore non ha prodotto niente"
    if "codex/toolkit-commands.txt" not in files:      # copia installata da Codex: bin/ senza symlink
        current = [r for r in current if r != "codex/toolkit-commands.txt"]
    missing = sorted(set(expected) - set(current))
    extra = sorted(set(current) - set(expected))
    stale = [rel for rel in expected if rel in current and not filecmp.cmp(out / rel, PLUGIN / rel, shallow=False)]
    assert not (missing or extra or stale), (
        f"skill Codex non allineate (lancia python3 plugins/youtube/scripts/codex/build_skills.py): "
        f"mancano {missing}, in più {extra}, vecchie {stale}")
    for rel in expected:
        data = (PLUGIN / rel).read_bytes()
        assert data.endswith(b"\n") and b"\r" not in data, f"{rel}: serve LF e newline finale"


def test_cli_out_matches_module():
    """--out scrive lo stesso albero della funzione (determinismo, niente date)."""
    out = TMP / "cli-out"
    r = run_build("--out", str(out))
    links_only = all("link non risolto" in line for line in r.stderr.splitlines() if line.startswith("errore:"))
    assert r.returncode == 0 or links_only, r.stdout + r.stderr
    files, _w, _l = B.generate(PLUGIN)
    for rel, text in files.items():
        assert (out / rel).read_text(encoding="utf-8") == text, rel
    files2, _w, _l = B.generate(PLUGIN)
    assert files == files2, "output non deterministico"


def test_check_cli_with_host_guide():
    """`--check` sulla repo: exit 0. Serve anche la guida scritta a mano codex/references/codex-host.md."""
    r = run_build("--check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"ok: {len(commands())} skill Codex" in r.stdout, r.stdout


def test_check_detects_stale_missing_extra():
    root = fresh_copy("stale")
    assert run_build("--check", root=root).returncode == 0

    edit = root / "commands" / "edit.md"
    edit.write_text(edit.read_text(encoding="utf-8").replace("description: Edit —", "description: Edit (nuovo) —", 1), encoding="utf-8")
    r = run_build("--check", root=root)
    assert r.returncode == 1 and "vecchio: codex/skills/edit/SKILL.md" in r.stdout, r.stdout + r.stderr

    (root / "codex" / "skills" / "hook" / "agents" / "openai.yaml").unlink()
    r = run_build("--check", root=root)
    assert "manca: codex/skills/hook/agents/openai.yaml" in r.stdout, r.stdout

    old = root / "codex" / "skills" / "vecchia"
    shutil.copytree(root / "codex" / "skills" / "story", old)
    r = run_build("--check", root=root)
    assert r.returncode == 1 and "in più: codex/skills/vecchia/SKILL.md" in r.stdout, r.stdout

    r = run_build(root=root)                    # scrive: rigenera, rimette il file mancante, toglie la skill generata in più
    assert r.returncode == 0 and "tolta codex/skills/vecchia" in r.stdout, r.stdout + r.stderr
    assert not old.exists() and "Edit (nuovo)" in (root / "codex/skills/edit/SKILL.md").read_text(encoding="utf-8")
    assert run_build("--check", root=root).returncode == 0

    hand = root / "codex" / "skills" / "a-mano"
    hand.mkdir()
    (hand / "SKILL.md").write_text("---\nname: a-mano\ndescription: scritta a mano\n---\n", encoding="utf-8")
    r = run_build(root=root)
    assert r.returncode == 1 and "non è generata" in r.stderr, r.stdout + r.stderr
    assert hand.exists(), "una skill scritta a mano non si cancella mai"
    shutil.rmtree(hand)

    tk = root / "codex" / "toolkit-commands.txt"
    if not any(p.is_symlink() for p in (root / "bin").iterdir()):
        return                                  # copia installata da Codex: toolkit-commands.txt non si rigenera
    tk.write_text(tk.read_text(encoding="utf-8").replace("yt-config\n", ""), encoding="utf-8")
    r = run_build("--check", root=root)
    assert r.returncode == 1 and "vecchio: codex/toolkit-commands.txt" in r.stdout, r.stdout


def test_build_errors_on_bad_sources():
    root = fresh_copy("errors")
    (root / "skills").mkdir()
    r = run_build("--check", root=root)
    assert r.returncode == 1 and "skills/" in r.stderr and "skill doppie" in r.stderr, r.stderr
    (root / "skills").rmdir()

    new = root / "commands" / "nuova.md"
    new.write_text('---\ndescription: "Nuova — prova"\nargument-hint: "[richiesta]"\n---\n\n$ARGUMENTS\n', encoding="utf-8")
    r = run_build("--check", root=root)
    assert r.returncode == 1 and "nuova" in r.stderr and "Passo 1" in r.stderr and "TITLES" in r.stderr, r.stderr
    new.unlink()

    story = root / "commands" / "story.md"
    text = story.read_text(encoding="utf-8")
    story.write_text(text.replace("description: Story —", "description: Story <bozza> —", 1), encoding="utf-8")
    r = run_build("--check", root=root)
    assert r.returncode == 1 and "< o >" in r.stderr, r.stderr
    story.write_text(text.replace("description: Story —", "description: " + "x" * 1100 + " —", 1), encoding="utf-8")
    r = run_build("--check", root=root)
    assert r.returncode == 1 and "max 1024" in r.stderr, r.stderr
    story.write_text(text, encoding="utf-8")

    learn = root / "commands" / "learn.md"
    ltext = learn.read_text(encoding="utf-8")
    learn.write_text(ltext.replace("la PR la apre /youtube:producer con il tuo OK", "la PR la apre il Producer"), encoding="utf-8")
    r = run_build("--check", root=root)
    assert r.returncode == 1 and "DESCRIPTION_OVERRIDES" in r.stderr, r.stderr
    learn.write_text(ltext, encoding="utf-8")

    agent = root / "agents" / "producer.md"
    atext = agent.read_text(encoding="utf-8")
    agent.write_text("\n".join(l for l in atext.split("\n") if "`chapters.md`" not in l), encoding="utf-8")
    r = run_build("--check", root=root)
    assert r.returncode == 1 and "solo in commands/: chapters" in r.stderr, r.stderr
    agent.write_text(atext, encoding="utf-8")

    (root / "codex" / "references" / "codex-host.md").unlink()
    r = run_build("--check", root=root)
    assert r.returncode == 1 and "link non risolto ../../references/codex-host.md" in r.stderr, r.stderr
    assert run_build("--check", root=fresh_copy("errors-ok")).returncode == 0


def test_writes_only_codex_folder():
    root = TMP / "only-codex" / "youtube"
    copy_plugin(root, keep_symlinks=True)
    shutil.rmtree(root / "codex" / "skills", ignore_errors=True)
    before = {p.relative_to(root).as_posix(): p.lstat().st_mtime_ns for p in root.rglob("*") if "codex" not in p.relative_to(root).parts[:1]}
    r = run_build(root=root)
    assert r.returncode == 0, r.stdout + r.stderr
    after = {p.relative_to(root).as_posix(): p.lstat().st_mtime_ns for p in root.rglob("*") if "codex" not in p.relative_to(root).parts[:1]}
    assert before == after, "il generatore ha scritto fuori da codex/"
    assert not (root / "skills").exists() and not (PLUGIN / "skills").exists(), "skills/ nella radice del plugin: Claude Code la caricherebbe"


def test_codex_cache_copy_without_symlinks():
    """Una copia come la installa Codex (niente symlink) passa `--check`; toolkit-commands.txt resta com'è."""
    root = TMP / "cache" / "youtube-producer" / "youtube" / "1.0.0"
    copy_plugin(root, keep_symlinks=False)
    links = [p for p in root.rglob("*") if p.is_symlink()]
    assert not links, links
    if not (PLUGIN / "codex" / "skills").is_dir():
        raise Skip("codex/skills non ancora generata nella repo")
    r = run_build("--check", root=root)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "toolkit-commands.txt non rigenerato" in r.stderr, r.stderr


# ---------------------------------------------------------------------------- contenuto delle skill

def test_skill_frontmatter_and_limits():
    names = commands()
    assert sorted(d.name for d in (PLUGIN / "codex" / "skills").iterdir() if d.is_dir()) == names
    for name in names:
        text = (PLUGIN / "codex" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        size = len(text.encode("utf-8"))
        assert size <= 7000, f"{name}: {size} byte (Codex inietta solo 8.000 byte del SKILL.md)"
        fm, body = split_frontmatter(text)
        assert set(fm) == {"name", "description"}, (name, fm.keys())
        assert fm["name"] == name and re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) and len(name) <= 64
        desc = fm["description"]
        assert desc and len(desc) <= 1024 and "<" not in desc and ">" not in desc, (name, desc)
        src = B.parse_frontmatter((PLUGIN / "commands" / f"{name}.md").read_text(encoding="utf-8"), name)["description"]
        if name == "learn":
            src = src.replace("la PR la apre /youtube:producer con il tuo OK", "la PR la lanci tu dal Terminale")
        expect = src.replace("/youtube:", "$youtube:")
        if name == "producer":
            expect = expect.rstrip(".") + ". Usalo anche per rispondere ai gate G1 e G2 e riprendere il lavoro."
        assert desc == expect, f"{name}: la descrizione italiana deve restare quella del comando\n{desc}\n{expect}"
        hint = B.parse_frontmatter((PLUGIN / "commands" / f"{name}.md").read_text(encoding="utf-8"), name).get("argument-hint", "")
        assert f"Parametri previsti: `{hint.replace('/youtube:', '$youtube:')}`" in body, name


def test_openai_yaml():
    for name in commands():
        lines = (PLUGIN / "codex" / "skills" / name / "agents" / "openai.yaml").read_text(encoding="utf-8").split("\n")
        data, section = {}, None
        for line in filter(None, lines):
            if not line.startswith(" "):
                section = line.rstrip(":")
                data[section] = {}
                continue
            key, _, raw = line.strip().partition(": ")
            data[section][key] = json.loads(raw) if raw.startswith('"') else {"true": True, "false": False}[raw]
        assert set(data) == {"interface", "policy"}, data
        assert set(data["interface"]) == {"display_name", "short_description", "default_prompt"}, data
        assert set(data["policy"]) == {"allow_implicit_invocation"}, data
        assert data["interface"]["display_name"].startswith("YouTube Producer")
        assert 25 <= len(data["interface"]["short_description"]) <= 64, data["interface"]["short_description"]
        assert f"$youtube:{name}" in data["interface"]["default_prompt"], data["interface"]["default_prompt"]
        assert data["policy"]["allow_implicit_invocation"] is (name == "producer"), (name, data["policy"])


def test_wrappers_keep_gates_and_rules():
    for name in commands():
        text = (PLUGIN / "codex" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        must = ["](../../references/codex-host.md)", "](../../../agents/producer.md)", "yt-config", "codex_guard.active",
                "$ARGUMENTS", f"$youtube:{name}", "G1", "G2", "**G3.**", "Non pubblichi", "guard.sh", "non cercare giri",
                "A pagamento", "Niente PR né push", "`~/.codex/` non si tocca", "Generato da scripts/codex/build_skills.py"]
        must.append("](../../../commands/)" if name == "producer" else f"](../../../commands/{name}.md)")
        if name != "setup":
            must += ["](../../../commands/producer.md)", "rispondi con `$youtube:producer`", "spawn_agent", "fork_turns: \"none\"",
                     "fork_context: false"]
        if name in ("thumbnail", "producer"):
            must += ["](../../../agents/thumb-cold-reader.md)", "mai simularlo", "view_image"]
        if name == "producer":
            must += ["## Ripresa dopo un gate", "yt-learn decision", "verbatim", "--delegated"]
        if name == "setup":
            must += ["«Setup in Codex»", "senza `--yes`", "Terminale", "rispondi con `$youtube:setup`"]
        missing = [m for m in must if m not in text]
        assert not missing, f"{name}: manca {missing}"


def test_no_claude_only_leftovers():
    tools = ["SendMessage", "TodoWrite", "Monitor", "WebFetch", "WebSearch", "AskUserQuestion", "run_in_background",
             "subagent_type", "Glob", "Grep", "tool Agent"]
    for name in commands():
        text = (PLUGIN / "codex" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert "${CLAUDE_PLUGIN_ROOT}" not in text and "CLAUDE_PLUGIN_ROOT}" not in text, name
        for line in text.split("\n"):
            if "/youtube:" in line:
                assert "$youtube:" in line or "versione Codex di" in line, f"{name}: /youtube: senza la forma Codex: {line}"
            for tool in tools:
                if re.search(rf"\b{re.escape(tool)}\b", line):
                    assert "Codex" in line and "non serv" in line, f"{name}: strumento di Claude senza spiegazione: {line}"
        assert "claude plugin" not in text and "settings.json" not in text, name


def test_links_stay_inside_plugin():
    files, _w, _l = B.generate(PLUGIN)
    real = PLUGIN.resolve()
    n = 0
    for rel, text in files.items():
        if not rel.endswith("/SKILL.md"):
            continue
        for target in B.LINK_RE.findall(text):
            dest = (PLUGIN / Path(rel).parent / target).resolve()
            dest.relative_to(real)              # ValueError se esce dal plugin
            n += 1
            if "codex-host.md" not in target:
                assert dest.exists(), f"{rel}: {target}"
    assert n >= 4 * len(commands()) - 1, n


def test_links_resolve_with_host_guide():
    files, _w, link_errors = B.generate(PLUGIN)
    assert not link_errors, "\n".join(link_errors)


def test_host_guide_sections_used_by_wrappers():
    """La guida scritta a mano ha le sezioni e le traduzioni a cui rimandano gli involucri."""
    if not HOST_GUIDE.exists():
        raise AssertionError("manca codex/references/codex-host.md (guida scritta a mano, design §3.5)")
    text = HOST_GUIDE.read_text(encoding="utf-8")
    headings = [l for l in text.split("\n") if l.startswith("#")]
    for section in ("Setup in Codex", "Proposte", "Guard", "Gate", "Lettore a freddo", "Render lunghi", "Sandbox"):
        assert any(section.lower() in h.lower() for h in headings), f"codex-host.md: manca la sezione «{section}»"
    agent = (PLUGIN / "agents" / "producer.md").read_text(encoding="utf-8")
    tools = re.search(r"^tools:\s*(.+)$", agent, re.M).group(1)
    for tool in [t.strip() for t in tools.split(",")]:
        assert re.search(rf"\b{re.escape(tool)}\b", text), f"codex-host.md: manca la traduzione dello strumento {tool}"
    for name in commands():
        assert f"$youtube:{name}" in text, f"codex-host.md: manca $youtube:{name}"
    for must in ("spawn_agent", "fork_turns", "fork_context", "wait_agent", "view_image", "apply_patch", "update_plan",
                 "codex_guard", "yt-learn decision", "propose-pr", "codex-memory/MEMORY.md", "CLAUDE_PLUGIN_ROOT"):
        assert must in text, f"codex-host.md: manca {must}"
    assert len(text.encode("utf-8")) <= 28000, "codex-host.md troppo lungo: lo legge ogni skill, all'inizio"


# Codex taglia a metà l'output di un comando oltre ~10.000 token (models.json di codex-rs 0.155: truncation_policy
# tokens 10000 per ogni modello). Le skill leggono i file a blocchi di 120 righe: ogni blocco resta sotto i 24 KB
# (~7.000 token), con margine.
CHUNK_LINES = 120
CHUNK_MAX_BYTES = 24000


def test_read_chunks_fit_codex_tool_output():
    wrappers = [p.read_text(encoding="utf-8") for p in (PLUGIN / "codex" / "skills").glob("*/SKILL.md")]
    assert all(f"sed -n '1,{CHUNK_LINES}p'" in w for w in wrappers), "le skill devono leggere a blocchi di 120 righe"
    host = HOST_GUIDE.read_text(encoding="utf-8")
    assert f"sed -n '1,{CHUNK_LINES}p'" in host, "codex-host.md: la lettura a blocchi deve dire 120 righe"
    files = [*(PLUGIN / "commands").glob("*.md"), *(PLUGIN / "agents").glob("*.md"),
             *(PLUGIN / "docs" / "yt" / "knowledge").glob("*.md"), *(PLUGIN / "docs" / "yt" / "templates").glob("*.md"),
             HOST_GUIDE]
    big = []
    for f in files:
        lines = f.read_text(encoding="utf-8").split("\n")
        for i in range(0, len(lines), CHUNK_LINES):
            size = len("\n".join(lines[i:i + CHUNK_LINES]).encode("utf-8"))
            if size > CHUNK_MAX_BYTES:
                big.append(f"{f.relative_to(PLUGIN)} righe {i + 1}-{i + CHUNK_LINES}: {size} byte")
    assert not big, "blocchi troppo grandi per l'output di un comando in Codex: " + "; ".join(big)


def test_passo1_matches_commands():
    assert B.passo1_skills(PLUGIN) == set(commands()) - {"producer"}


def test_toolkit_commands():
    path = PLUGIN / "codex" / "toolkit-commands.txt"
    names = path.read_text(encoding="utf-8").split("\n")
    assert names[-1] == "" and names[:-1] == sorted(names[:-1]), "una riga per nome, in ordine, newline finale"
    names = names[:-1]
    links = sorted(p.name for p in (PLUGIN / "bin").iterdir() if p.is_symlink())
    if not links:
        raise Skip("bin/ senza symlink (copia installata da Codex)")
    assert names == links, (names, links)
    assert len(names) == 31 and "thumbvision" in names and "yt-install" in names, names
    assert all(n == "thumbvision" or n.startswith("yt-") for n in names) and "yt-dlp" not in names


# ---------------------------------------------------------------------------- validatori di Codex (solo lettura)

def _python_with_yaml() -> str | None:
    for py in (sys.executable, "/usr/bin/python3"):
        if py and Path(py).exists() and subprocess.run([py, "-c", "import yaml"], capture_output=True).returncode == 0:
            return py
    return None


def test_codex_skill_validators():
    quick = CODEX_SYSTEM / "skill-creator" / "scripts" / "quick_validate.py"
    plugin_v = CODEX_SYSTEM / "plugin-creator" / "scripts" / "validate_plugin.py"
    py = _python_with_yaml()
    if not quick.exists() or not plugin_v.exists() or not py:
        raise Skip("validatori di Codex o PyYAML non disponibili su questo Mac")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for name in commands():
        r = subprocess.run([py, "-B", str(quick), str(PLUGIN / "codex" / "skills" / name)], capture_output=True, text=True, env=env)
        assert r.returncode == 0, f"{name}: {r.stdout}{r.stderr}"
    # plugin-creator controlla le skill solo in <plugin>/skills/: copia minima con un manifest di prova
    stage = TMP / "stage" / "youtube"
    shutil.copytree(PLUGIN / "codex" / "skills", stage / "skills")
    (stage / ".codex-plugin").mkdir(parents=True)
    (stage / ".codex-plugin" / "plugin.json").write_text(json.dumps({
        "name": "youtube", "version": "1.0.0", "description": "Prova delle skill generate.",
        "author": {"name": "test"}, "skills": "./skills/"}), encoding="utf-8")
    r = subprocess.run([py, "-B", str(plugin_v), str(stage)], capture_output=True, text=True, env=env)
    skill_errors = [l for l in r.stdout.split("\n") if l.startswith("- ") and "skill" in l]
    assert not skill_errors, r.stdout


TESTS = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]


def main() -> int:
    flt = sys.argv[1] if len(sys.argv) > 1 else ""
    failed = 0
    for t in TESTS:
        if flt and flt not in t.__name__:
            continue
        t0 = time.time()
        try:
            t()
            print(f"ok    {t.__name__} ({time.time() - t0:.2f} s)")
        except Skip as s:
            print(f"salto {t.__name__}: {s}")
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}")
            traceback.print_exc()
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"{'tutti ok' if not failed else f'{failed} falliti'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
