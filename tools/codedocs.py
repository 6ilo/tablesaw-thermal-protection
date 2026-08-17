#!/usr/bin/env python3
"""Build and verify the table saw error code registry.

The markdown in docs/codes/ is the single source of truth for three artifacts:

  * this repository's browsable index (docs/codes/README.md)
  * the offline HTML bundle served from the ESP32 over the ALN Table Saw AP
  * firmware/generated/error_codes.h, so the device's code list cannot drift

Usage:
    python3 tools/codedocs.py check    # validate; non-zero exit on any problem
    python3 tools/codedocs.py build    # regenerate every artifact

`check` is the CI gate. It is deliberately strict: an operator reading a stale
threshold off a screen at a machine is the failure this whole pipeline exists to
prevent, so quoting a number that disagrees with ARCHITECTURE.md is a build error,
not a warning.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
    import markdown as md_lib
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
except ImportError as exc:  # pragma: no cover - dependency guidance
    sys.exit(
        f"missing dependency: {exc.name}\n"
        "install with: python3 -m pip install -r tools/requirements.txt"
    )

REPO = Path(__file__).resolve().parent.parent
CODES_DIR = REPO / "docs" / "codes"
TEMPLATES = Path(__file__).resolve().parent / "templates"
ARCHITECTURE = REPO / "ARCHITECTURE.md"
README = REPO / "README.md"
INDEX_MD = CODES_DIR / "README.md"
BUILD = REPO / "build"
SITE_OUT = BUILD / "site"
FW_OUT = BUILD / "firmware"

REPO_BLOB = "https://github.com/6ilo/tablesaw-thermal-protection/blob/main/"
REPO_URL = "https://github.com/6ilo/tablesaw-thermal-protection"

FRONT_MATTER_KEYS = [
    "code", "title", "severity", "event", "state",
    "led", "clears", "loto", "since", "summary", "refs",
]
SEVERITIES = ["trip", "lockout", "warning", "info"]
STATES = ["BOOT", "ARMED", "TRIPPED", "COOLDOWN", "MANUAL_LOCKOUT"]
CLEARS = ["auto", "ack", "power", "none"]

REQUIRED_SECTIONS = [
    "What happened",
    "Do this now",
    "Why it happens",
    "When it clears",
    "If it keeps happening",
]
LOTO_SECTION = "Before you touch anything"

CLEARS_TEXT = {
    "ack": "Physical ack button press",
    "power": "Fix the fault, then power-cycle",
    "none": "Does not clear on its own",
}

# "auto" means different things eitherside of a trip. A trip clears by cooling; an
# advisory clears when whatever raised it stops being true — which for W03 is the
# probe getting *warmer*, the exact opposite of cooling.
CLEARS_AUTO_TEXT = {
    "trip": "On its own, once the motor cools",
    "lockout": "On its own, once the motor cools",
    "warning": "On its own, when the condition passes",
    "info": "On its own, when the condition passes",
}

SEVERITY_GROUPS = [
    ("Trips — the saw stopped", ["trip"]),
    ("Lockouts — the saw stays stopped", ["lockout"]),
    ("Warnings — the saw is still running", ["warning"]),
    ("Notices — feedback, not a fault", ["info"]),
]

CODE_RE = re.compile(r"^[EW]\d{2}$")
CODE_LINK_RE = re.compile(r"\[[^\]]+\]\((?!https?:)([^)]+)\)")
CONST_MENTION_RE = re.compile(r"\b([A-Z][A-Z0-9_]{3,})\b\s*\(([^)]{1,60})\)")
FIRST_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


# --------------------------------------------------------------------------- #
# canonical values, parsed from the design of record
# --------------------------------------------------------------------------- #

@dataclass
class Canon:
    """Constants and LED patterns lifted straight out of ARCHITECTURE.md.

    Nothing here is hardcoded. If the design of record changes a threshold, these
    values change with it and every doc that quotes the old number fails `check`.
    """
    constants: dict[str, float] = field(default_factory=dict)
    led_patterns: set[str] = field(default_factory=set)
    headings: dict[str, set[str]] = field(default_factory=dict)


def _first_number(text: str) -> float | None:
    m = FIRST_NUMBER_RE.search(text.replace(",", ""))
    return float(m.group()) if m else None


def slugify(heading: str) -> str:
    """GitHub's heading-anchor algorithm.

    Lowercase, drop anything that is not a word character, space or hyphen, then
    turn spaces into hyphens. An em dash vanishes and leaves a doubled hyphen,
    which is why the repo's own links look like `#relay-polarity--critical`.
    """
    s = heading.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    return re.sub(r"\s", "-", s)


def load_canon() -> Canon:
    canon = Canon()
    arch = ARCHITECTURE.read_text(encoding="utf-8")

    # Thresholds table: | `TRIP_THRESHOLD` | 110 °C | note |
    for name, value in re.findall(
        r"^\|\s*`([A-Z][A-Z0-9_]*)`\s*\|\s*([^|]+?)\s*\|", arch, re.MULTILINE
    ):
        num = _first_number(value)
        if num is not None:
            canon.constants[name] = num

    # Pseudocode constants: TRIP_C = 110, several to a line. Only untagged fences —
    # the mermaid and ascii-diagram blocks have nothing to contribute.
    for lang, block in re.findall(r"^```(\w*)\n(.*?)^```", arch, re.DOTALL | re.MULTILINE):
        if lang:
            continue
        for name, value in re.findall(
            r"\b([A-Z][A-Z0-9_]{2,})\s*=\s*(-?\d+(?:\.\d+)?)\b", block
        ):
            canon.constants.setdefault(name, float(value))

    # Status LED patterns table, first column.
    led_table = re.search(
        r"### Status LED patterns.*?\n\n(\|.*?)\n\n", arch, re.DOTALL
    )
    if led_table:
        for line in led_table.group(1).splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 3 and not set(cells[0]) <= set("-: "):
                pattern = cells[0].replace("**", "").strip()
                if pattern and pattern != "Pattern":
                    canon.led_patterns.add(pattern)

    # Headings of every local file a doc is allowed to link into.
    for path in (ARCHITECTURE, README):
        text = path.read_text(encoding="utf-8")
        canon.headings[path.name] = {
            slugify(h) for h in re.findall(r"^#{1,6}\s+(.+)$", text, re.MULTILINE)
        }

    return canon


# --------------------------------------------------------------------------- #
# document model
# --------------------------------------------------------------------------- #

@dataclass
class Doc:
    path: Path
    front: dict
    body: str

    @property
    def code(self) -> str:
        return str(self.front.get("code", self.path.stem))

    def __getattr__(self, item):
        try:
            return self.front[item]
        except KeyError:
            raise AttributeError(item) from None

    @property
    def clears_text(self) -> str:
        clears = self.front.get("clears", "")
        if clears == "auto":
            return CLEARS_AUTO_TEXT.get(self.front.get("severity", ""), "On its own")
        return CLEARS_TEXT.get(clears, "—")

    def sections(self) -> list[str]:
        return re.findall(r"^##\s+(.+?)\s*$", self.body, re.MULTILINE)


def parse_doc(path: Path) -> tuple[Doc | None, list[str]]:
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.DOTALL)
    if not m:
        return None, [f"{path.name}: missing YAML front matter delimited by ---"]
    try:
        front = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        return None, [f"{path.name}: front matter is not valid YAML: {exc}"]
    if not isinstance(front, dict):
        return None, [f"{path.name}: front matter must be a mapping"]
    return Doc(path=path, front=front, body=m.group(2)), []


def load_docs() -> tuple[list[Doc], list[str]]:
    docs, errors = [], []
    for path in sorted(CODES_DIR.glob("*.md")):
        if path.name in ("_TEMPLATE.md", "README.md"):
            continue
        doc, errs = parse_doc(path)
        errors.extend(errs)
        if doc:
            docs.append(doc)
    docs.sort(key=lambda d: (d.code[0] != "E", d.code))
    return docs, errors


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #

def validate(docs: list[Doc], canon: Canon) -> list[str]:
    errors: list[str] = []
    seen_codes: dict[str, Path] = {}
    known_files = {p.name for p in CODES_DIR.glob("*.md")}

    if not docs:
        errors.append("docs/codes/ contains no code documents")

    for doc in docs:
        name = doc.path.name
        front = doc.front

        def err(msg: str) -> None:
            errors.append(f"{name}: {msg}")

        # --- front matter schema ---------------------------------------- #
        keys = list(front.keys())
        if keys != FRONT_MATTER_KEYS:
            missing = [k for k in FRONT_MATTER_KEYS if k not in keys]
            extra = [k for k in keys if k not in FRONT_MATTER_KEYS]
            if missing:
                err(f"front matter missing key(s): {', '.join(missing)}")
            if extra:
                err(f"front matter has unknown key(s): {', '.join(extra)}")
            if not missing and not extra:
                err(f"front matter keys out of order: expected {FRONT_MATTER_KEYS}")

        code = str(front.get("code", ""))
        if not CODE_RE.match(code):
            err(f"code {code!r} must look like E01 or W01")
        if code != doc.path.stem:
            err(f"code {code!r} does not match filename {doc.path.stem!r}")
        if code in seen_codes:
            err(f"duplicate code, also defined in {seen_codes[code].name}")
        seen_codes[code] = doc.path

        if front.get("severity") not in SEVERITIES:
            err(f"severity {front.get('severity')!r} not one of {SEVERITIES}")
        if front.get("state") not in STATES:
            err(f"state {front.get('state')!r} not one of {STATES}")
        if front.get("clears") not in CLEARS:
            err(f"clears {front.get('clears')!r} not one of {CLEARS}")
        if not isinstance(front.get("loto"), bool):
            err("loto must be true or false")
        if not isinstance(front.get("since"), str):
            err('since must be a quoted string, e.g. "1.0.0"')
        if not str(front.get("title", "")).strip():
            err("title is empty")
        if not str(front.get("event", "")).strip():
            err("event is empty")

        summary = str(front.get("summary", ""))
        if not summary.strip():
            err("summary is empty")
        if len(summary) > 160:
            err(f"summary is {len(summary)} chars, limit is 160")
        if "\n" in summary.strip():
            err("summary must be a single line")

        led = str(front.get("led", ""))
        if canon.led_patterns and led not in canon.led_patterns:
            err(
                f"led {led!r} is not a pattern in ARCHITECTURE.md "
                f"§ Status LED patterns ({sorted(canon.led_patterns)})"
            )

        # A warning that changes the LED would contradict the LED table, which
        # only defines patterns for states, not for advisories.
        if front.get("severity") in ("warning", "info") and led.startswith(
            ("Fast", "Slow", "Double", "SOS")
        ) and front.get("state") == "ARMED":
            err("an ARMED advisory must leave the LED solid; see § Status LED patterns")

        # --- sections ---------------------------------------------------- #
        sections = doc.sections()
        expected = list(REQUIRED_SECTIONS)
        if front.get("loto") is True:
            expected.insert(1, LOTO_SECTION)
        # "Full detail" is appended by the renderer, never written by hand.
        if sections != expected:
            err(f"sections {sections} do not match required {expected}")

        if front.get("loto") is False and LOTO_SECTION in sections:
            err(f"has a '{LOTO_SECTION}' section but loto is false")

        # --- cross links -------------------------------------------------- #
        for target in CODE_LINK_RE.findall(doc.body):
            target = target.split("#")[0]
            if not target:
                continue
            if target not in known_files and not (CODES_DIR / target).exists():
                err(f"relative link to {target!r} which does not exist")

        # --- refs ---------------------------------------------------------- #
        refs = front.get("refs")
        if not isinstance(refs, list) or not refs:
            err("refs must be a non-empty list")
        else:
            for ref in refs:
                if not isinstance(ref, dict) or set(ref) != {"title", "url"}:
                    err(f"ref {ref!r} must have exactly title and url")
                    continue
                url = str(ref["url"])
                if not url.startswith((REPO_BLOB, REPO_URL)):
                    err(f"ref url {url!r} must point into this repository")
                    continue
                if url.startswith(REPO_BLOB) and "#" in url:
                    target, _, anchor = url[len(REPO_BLOB):].partition("#")
                    if target in canon.headings:
                        if anchor not in canon.headings[target]:
                            err(f"ref anchor #{anchor} does not exist in {target}")
                    elif not (REPO / target).exists():
                        err(f"ref points at {target!r} which does not exist")

        # --- quoted constants must match the design of record -------------- #
        for const, paren in CONST_MENTION_RE.findall(doc.body):
            if const not in canon.constants:
                continue
            quoted = _first_number(paren)
            if quoted is None:
                continue
            expected_val = canon.constants[const]
            if abs(quoted - expected_val) > 1e-9:
                err(
                    f"quotes {const} as {paren.strip()!r} but ARCHITECTURE.md "
                    f"says {expected_val:g}"
                )

    return errors


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #

def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def registry_version() -> str:
    path = REPO / "VERSION"
    return path.read_text(encoding="utf-8").strip() if path.exists() else "0.0.0"


def make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    # ensure_ascii=False so the generated C header carries literal UTF-8 "°C"
    # rather than ° universal character names.
    env.filters["tojson"] = lambda v: json.dumps(v, ensure_ascii=False)
    return env


def qr_svg(url: str, enabled: bool) -> str:
    if not enabled:
        return ""
    try:
        import segno
    except ImportError:
        return ""
    buf = io.BytesIO()
    segno.make(url, error="m").save(
        buf, kind="svg", scale=3, border=2,
        dark="#000000", light="#ffffff",
        xmldecl=False, svgns=True, nl=False,
    )
    return buf.getvalue().decode("utf-8")


def render_body(doc: Doc) -> str:
    html = md_lib.markdown(doc.body, extensions=["tables", "sane_lists"])
    # Cross-links are written as [E04](E04.md) so they work on GitHub. The device
    # bundle is HTML, so they have to be rewritten or every sibling link is dead on
    # the one copy that has no internet to fall back on.
    html = re.sub(r'href="([EW]\d{2})\.md(#[^"]*)?"', r'href="\1.html\2"', html)
    html = html.replace('href="None"', 'href="#"')
    # Wrap the lockout section so it renders as a hazard callout rather than as
    # just another heading the operator can skim past.
    pattern = re.compile(
        rf"(<h2>{re.escape(LOTO_SECTION)}</h2>.*?)(?=<h2>)", re.DOTALL
    )
    html = pattern.sub(r'<div class="loto">\1</div>', html, count=1)
    # Same-page links are written as [If it keeps happening](#if-it-keeps-happening)
    # because GitHub mints heading anchors for free. python-markdown does not, so the
    # device copy — the one with no internet to fall back on — needs them injected, or
    # the "stop and read this" link at the end of every procedure goes nowhere.
    return re.sub(
        r"<h2>(.*?)</h2>",
        lambda m: f'<h2 id="{slugify(m.group(1))}">{m.group(1)}</h2>',
        html,
    )


def verify_bundle(site: Path) -> list[str]:
    """Post-build integrity pass over the artifact that actually reaches the saw.

    `check` validates the markdown; this validates the HTML that gets flashed. They
    are different failure surfaces — a link that is correct on GitHub can still be
    dead on the device, which is the copy with no internet to fall back on.
    """
    problems: list[str] = []
    for html in sorted(site.glob("*.html")):
        text = html.read_text(encoding="utf-8")
        gz = site / (html.name + ".gz")
        if not gz.exists() or gzip.decompress(gz.read_bytes()) != html.read_bytes():
            problems.append(f"{html.name}: gzip copy missing or does not round-trip")
        ids = set(re.findall(r'\bid="([^"]+)"', text))
        for href in re.findall(r'href="([^"]+)"', text):
            if href.startswith(("http://", "https://", "mailto:")):
                continue
            target, _, anchor = href.partition("#")
            if target and not (site / target).exists():
                problems.append(f"{html.name}: dead local link {href!r}")
                continue
            # A same-page anchor that lands nowhere is silent on GitHub, which mints
            # its own, and broken only here — on the copy read at the machine.
            if anchor and not target and anchor not in ids:
                problems.append(f"{html.name}: dead in-page anchor {href!r}")
        if re.search(r"^\s*#{2,}\s", text, re.MULTILINE):
            problems.append(f"{html.name}: unrendered markdown heading")
        if re.search(r"\]\([^)]*\.md\)", text):
            problems.append(f"{html.name}: unrendered markdown link")
    return problems


def group_docs(docs: list[Doc]) -> list[tuple[str, list[Doc]]]:
    groups = []
    for label, sevs in SEVERITY_GROUPS:
        items = [d for d in docs if d.front.get("severity") in sevs]
        if items:
            groups.append((label, items))
    return groups


def write_gz(path: Path, data: bytes) -> int:
    buf = io.BytesIO()
    # mtime=0 keeps the output byte-identical between builds.
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as fh:
        fh.write(data)
    gz = buf.getvalue()
    path.write_bytes(gz)
    return len(gz)


def build(docs: list[Doc], *, with_qr: bool = True) -> list[str]:
    env = make_env()
    style = (TEMPLATES / "style.css").read_text(encoding="utf-8")
    version = registry_version()
    commit = git("rev-parse", "--short", "HEAD")
    commit_date = git("log", "-1", "--format=%cs")
    written: list[str] = []

    SITE_OUT.mkdir(parents=True, exist_ok=True)
    FW_OUT.mkdir(parents=True, exist_ok=True)

    page_tpl = env.get_template("page.html.j2")
    index_tpl = env.get_template("index.html.j2")
    manifest = []

    for doc in docs:
        # Exactly one QR per page, pointing at this code's canonical page. Four QR
        # codes on one screen is noise, and each one costs ~3 KB of flash for a
        # link the operator can also just read. The rest render as plain URLs.
        canonical = f"{REPO_BLOB}docs/codes/{doc.code}.md"
        refs = [{
            "title": f"{doc.code} on GitHub — canonical source",
            "url": canonical,
            "qr": qr_svg(canonical, with_qr),
        }]
        refs += [
            {"title": r["title"], "url": r["url"], "qr": ""}
            for r in doc.front.get("refs", [])
        ]
        view = dict(doc.front, refs=refs)
        html = page_tpl.render(
            doc=view, body=render_body(doc), style=style,
            clears_text=doc.clears_text, registry_version=version,
            commit=commit, commit_date=commit_date,
        )
        out = SITE_OUT / f"{doc.code}.html"
        data = html.encode("utf-8")
        out.write_bytes(data)
        gz_size = write_gz(SITE_OUT / f"{doc.code}.html.gz", data)
        manifest.append({
            "code": doc.code, "path": f"/codes/{doc.code}.html",
            "bytes": len(data), "gzip_bytes": gz_size,
        })
        written.append(str(out.relative_to(REPO)))

    groups = group_docs(docs)
    repo_refs = [
        {"title": "Project repository", "url": REPO_URL, "qr": qr_svg(REPO_URL, with_qr)},
        {"title": "Operator instructions",
         "url": f"{REPO_BLOB}README.md#operator-instructions", "qr": ""},
    ]
    index_html = index_tpl.render(
        groups=[(label, [d.front for d in items]) for label, items in groups],
        warnings=[d.front for d in docs if d.front.get("severity") == "warning"],
        style=style, registry_version=version,
        commit=commit, commit_date=commit_date, repo_refs=repo_refs,
    )
    data = index_html.encode("utf-8")
    (SITE_OUT / "index.html").write_bytes(data)
    gz_size = write_gz(SITE_OUT / "index.html.gz", data)
    manifest.insert(0, {
        "code": "index", "path": "/codes/index.html",
        "bytes": len(data), "gzip_bytes": gz_size,
    })
    written.append(str((SITE_OUT / "index.html").relative_to(REPO)))

    total_gz = sum(m["gzip_bytes"] for m in manifest)
    (SITE_OUT / "manifest.json").write_text(
        json.dumps({
            "registry_version": version,
            "commit": commit,
            "total_gzip_bytes": total_gz,
            "files": manifest,
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    written.append(str((SITE_OUT / "manifest.json").relative_to(REPO)))

    header = env.get_template("error_codes.h.j2").render(
        docs=[d.front for d in docs], registry_version=version,
        commit=commit, commit_date=commit_date,
    )
    (FW_OUT / "error_codes.h").write_text(header, encoding="utf-8")
    written.append(str((FW_OUT / "error_codes.h").relative_to(REPO)))

    INDEX_MD.write_text(render_index_md(env, docs), encoding="utf-8")
    written.append(str(INDEX_MD.relative_to(REPO)))

    return written


def render_index_md(env: Environment, docs: list[Doc]) -> str:
    """Deterministic — no commit or timestamp, because this artifact is committed."""
    groups = [
        (label, [dict(d.front, clears_text=d.clears_text) for d in items])
        for label, items in group_docs(docs)
    ]
    return env.get_template("index.md.j2").render(
        groups=groups, registry_version=registry_version()
    )


# --------------------------------------------------------------------------- #
# entry points
# --------------------------------------------------------------------------- #

def cmd_check(args) -> int:
    canon = load_canon()
    docs, errors = load_docs()
    errors += validate(docs, canon)

    if INDEX_MD.exists():
        expected = render_index_md(make_env(), docs)
        if INDEX_MD.read_text(encoding="utf-8") != expected:
            errors.append(
                "docs/codes/README.md is stale — run `python3 tools/codedocs.py build`"
            )
    else:
        errors.append("docs/codes/README.md is missing — run build")

    if errors:
        print(f"FAIL — {len(errors)} problem(s) in the error code registry:\n")
        for e in errors:
            print(f"  ✗ {e}")
        print("\nThe registry is what an operator reads at the machine. Fix these.")
        return 1

    print(f"OK — {len(docs)} codes: {', '.join(d.code for d in docs)}")
    print(f"     {len(canon.constants)} constants and "
          f"{len(canon.led_patterns)} LED patterns cross-checked against ARCHITECTURE.md")
    return 0


def cmd_build(args) -> int:
    canon = load_canon()
    docs, errors = load_docs()
    errors += validate(docs, canon)
    if errors and not args.force:
        print("refusing to build an invalid registry:\n")
        for e in errors:
            print(f"  ✗ {e}")
        print("\nrun `codedocs.py check` for the same list, or --force to build anyway")
        return 1

    written = build(docs, with_qr=not args.no_qr)
    manifest = json.loads((SITE_OUT / "manifest.json").read_text(encoding="utf-8"))

    problems = verify_bundle(SITE_OUT)
    if problems:
        print(f"built, but the device bundle has {len(problems)} problem(s):\n")
        for p in problems:
            print(f"  ✗ {p}")
        return 1

    print(f"built {len(docs)} codes, registry {manifest['registry_version']}")
    for path in written:
        print(f"  → {path}")
    print(f"\ndevice bundle: {manifest['total_gzip_bytes'] / 1024:.1f} KiB gzipped "
          f"across {len(manifest['files'])} pages")
    if args.no_qr:
        print("note: built without QR codes (--no-qr)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="validate the registry (CI gate)")
    p_check.set_defaults(func=cmd_check)

    p_build = sub.add_parser("build", help="regenerate every artifact")
    p_build.add_argument("--no-qr", action="store_true",
                         help="skip QR generation (segno not installed)")
    p_build.add_argument("--force", action="store_true",
                         help="build even if validation fails")
    p_build.set_defaults(func=cmd_build)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
