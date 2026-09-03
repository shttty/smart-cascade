#!/usr/bin/env python3
"""Convert a to-tickets local ticket directory into a Smart Cascade queue.

`to-tickets` publishes one Markdown file per ticket under
`.scratch/<feature-slug>/issues/<NN>-<slug>.md`. Its fields map onto the queue
without any judgement call:

    <NN>-<slug>.md   ->  id           (numeric prefix stripped)
    **What to build** ->  scope
    **Blocked by**    ->  depends_on
    acceptance boxes  ->  checks

`checks` are acceptance targets, so a ticket's acceptance criteria transfer
verbatim; they do not need to be rewritten as shell commands.

The conversion is mechanical, so it is a script rather than a prose procedure.
Anything this script cannot resolve is reported as an error instead of being
guessed at: a queue that silently drops a dependency is worse than no queue.

Usage:
    python3 to-queue.py .scratch/<feature-slug>/issues
    python3 to-queue.py .scratch/<feature-slug>/issues -o .smart-cascade/queue.toml
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FILENAME_RE = re.compile(r"^(?P<num>\d+)[-_](?P<slug>.+)$")
ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
NONE_RE = re.compile(r"^\s*(none|n/?a|-|—)\b", re.IGNORECASE)

# `**What to build:** text` and `## What to build` are both in circulation;
# to-tickets uses the inline form locally and the heading form on a tracker.
INLINE_FIELD_RE = re.compile(
    r"^\s*\*\*(?P<name>[^*]+?):?\*\*:?\s*(?P<value>.*)$", re.IGNORECASE
)
HEADING_RE = re.compile(r"^\s*#{1,6}\s+(?P<name>.+?)\s*$")
CHECKBOX_RE = re.compile(r"^\s*[-*]\s*\[[ xX]?\]\s*(?P<text>.+?)\s*$")
BULLET_RE = re.compile(r"^\s*[-*]\s+(?P<text>.+?)\s*$")

BUILD_KEYS = {"what to build", "what it delivers", "what to build:"}
BLOCKED_KEYS = {"blocked by", "blockers", "depends on"}
ACCEPT_KEYS = {"acceptance criteria", "acceptance", "criteria"}
STATUS_KEYS = {"status", "parent"}


def slugify(raw: str) -> str:
    """Reduce a ticket title or filename stem to a queue-legal slice id."""
    text = raw.strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"[^a-z0-9-]", "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    text = re.sub(r"^\d+-", "", text)
    return text


def toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", " ").replace("\t", " ")
    return '"' + re.sub(r"\s{2,}", " ", escaped).strip() + '"'


class Ticket:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.number: str | None = None
        self.slug = ""
        self.title = ""
        self.scope = ""
        self.blocked_raw: list[str] = []
        self.blocked_seen = False
        self.checks: list[str] = []
        self.errors: list[str] = []


def split_blockers(raw: str) -> list[str]:
    """Split one 'Blocked by' value into individual ticket references."""
    if not raw.strip() or NONE_RE.match(raw):
        return []
    # Strip a trailing parenthetical such as "None (can start immediately)".
    cleaned = re.sub(r"\((?:[^()]*)\)", " ", raw)
    parts = re.split(r"[,;]|\band\b|\+", cleaned)
    return [part.strip(" .`*") for part in parts if part.strip(" .`*")]


def parse_ticket(path: Path) -> Ticket:
    ticket = Ticket(path)
    stem = path.stem
    match = FILENAME_RE.match(stem)
    if match:
        ticket.number = match.group("num").lstrip("0") or "0"
        ticket.slug = slugify(match.group("slug"))
    else:
        ticket.slug = slugify(stem)

    lines = path.read_text(encoding="utf-8").splitlines()
    section = ""
    body: dict[str, list[str]] = {}

    for line in lines:
        heading = HEADING_RE.match(line)
        if heading:
            name = heading.group("name").strip().lower()
            # `# <NN>: <Title>` carries the human title.
            title_match = re.match(r"^\d+\s*[:.\-]\s*(?P<t>.+)$", heading.group("name").strip())
            if title_match and not ticket.title:
                ticket.title = title_match.group("t").strip()
                section = ""
                continue
            section = name
            body.setdefault(section, [])
            continue

        inline = INLINE_FIELD_RE.match(line)
        if inline:
            name = inline.group("name").strip().lower()
            value = inline.group("value").strip()
            if name in BUILD_KEYS:
                if value:
                    ticket.scope = value
                section = "what to build"
                body.setdefault(section, [])
                continue
            if name in BLOCKED_KEYS:
                # An inline value settles this field even when it says "None";
                # otherwise a later section sweep would scavenge unrelated lines.
                ticket.blocked_seen = True
                if value:
                    ticket.blocked_raw.extend(split_blockers(value))
                    section = ""
                else:
                    section = "blocked by"
                    body.setdefault(section, [])
                continue
            if name in STATUS_KEYS:
                section = ""
                continue
            if name in ACCEPT_KEYS:
                section = "acceptance criteria"
                body.setdefault(section, [])
                continue

        if section:
            body[section].append(line)

    # Checkbox items are the acceptance criteria wherever they appear.
    for line in lines:
        checkbox = CHECKBOX_RE.match(line)
        if checkbox:
            ticket.checks.append(checkbox.group("text").strip())

    for name, content in body.items():
        text = "\n".join(content).strip()
        if name in BUILD_KEYS and not ticket.scope:
            paragraph = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if paragraph:
                ticket.scope = paragraph[0]
        elif name in BLOCKED_KEYS and not ticket.blocked_raw and not ticket.blocked_seen:
            for line in content:
                bullet = BULLET_RE.match(line)
                candidate = bullet.group("text") if bullet else line.strip()
                # Never scavenge acceptance checkboxes as dependency edges.
                if candidate and not CHECKBOX_RE.match(line):
                    ticket.blocked_raw.extend(split_blockers(candidate))
        elif name in ACCEPT_KEYS and not ticket.checks:
            for line in content:
                bullet = BULLET_RE.match(line)
                if bullet:
                    ticket.checks.append(bullet.group("text").strip())

    if not ticket.title:
        ticket.title = ticket.slug.replace("-", " ")
    if not ticket.scope:
        ticket.errors.append("no 'What to build' section found")
    if not ticket.checks:
        ticket.errors.append("no acceptance criteria found")
    if not ID_RE.match(ticket.slug):
        ticket.errors.append(f"filename does not yield a legal slice id: {ticket.slug!r}")
    return ticket


def resolve_blockers(tickets: list[Ticket]) -> None:
    """Map each raw 'Blocked by' reference onto a real slice id."""
    by_number = {t.number: t for t in tickets if t.number}
    by_slug = {t.slug: t for t in tickets}
    by_title = {slugify(t.title): t for t in tickets if t.title}

    for ticket in tickets:
        resolved: list[str] = []
        for raw in ticket.blocked_raw:
            ref = raw.strip()
            number = re.match(r"^#?(\d+)\b", ref)
            target: Ticket | None = None
            if number:
                target = by_number.get(number.group(1).lstrip("0") or "0")
            if target is None:
                key = slugify(ref)
                target = by_slug.get(key) or by_title.get(key)
            if target is None and number:
                # A bare number that matches nothing is a dangling edge.
                target = None
            if target is None:
                ticket.errors.append(f"unresolved blocker reference: {raw!r}")
                continue
            if target is ticket:
                ticket.errors.append(f"ticket blocks itself: {raw!r}")
                continue
            if target.slug not in resolved:
                resolved.append(target.slug)
        ticket.blocked_raw = resolved


def detect_cycles(tickets: list[Ticket]) -> list[str]:
    graph = {t.slug: list(t.blocked_raw) for t in tickets}
    state: dict[str, int] = {}
    cycles: list[str] = []

    def visit(node: str, trail: list[str]) -> None:
        if state.get(node) == 2:
            return
        if state.get(node) == 1:
            start = trail.index(node)
            cycles.append(" -> ".join(trail[start:] + [node]))
            return
        state[node] = 1
        for nxt in graph.get(node, []):
            visit(nxt, trail + [node])
        state[node] = 2

    for slug in graph:
        visit(slug, [])
    return cycles


def render(tickets: list[Ticket], source: Path) -> str:
    lines = [
        "# Generated from to-tickets output by bootstrap/to-queue.py",
        f"# Source: {source}",
        "#",
        "# `checks` are acceptance targets carried over verbatim from each",
        "# ticket's acceptance criteria. They state what must be true when the",
        "# slice is done; the implementer chooses the verification commands and",
        "# reports what was actually run in settlement.",
        "#",
        "# Review scope wording and dependency edges before approving this queue.",
        "",
    ]
    for ticket in tickets:
        lines.append("[[slices]]")
        lines.append(f"id = {toml_string(ticket.slug)}")
        if ticket.blocked_raw:
            deps = ", ".join(toml_string(dep) for dep in ticket.blocked_raw)
            lines.append(f"depends_on = [{deps}]")
        else:
            lines.append("depends_on = []")
        lines.append(f"scope = {toml_string(ticket.scope)}")
        if len(ticket.checks) == 1:
            lines.append(f"checks = [{toml_string(ticket.checks[0])}]")
        else:
            lines.append("checks = [")
            for check in ticket.checks:
                lines.append(f"    {toml_string(check)},")
            lines.append("]")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert a to-tickets issues directory into a Smart Cascade queue."
    )
    parser.add_argument("issues_dir", type=Path, help="directory holding <NN>-<slug>.md tickets")
    parser.add_argument("-o", "--output", type=Path, help="write the queue here instead of stdout")
    args = parser.parse_args()

    if not args.issues_dir.is_dir():
        print(f"error: not a directory: {args.issues_dir}", file=sys.stderr)
        return 2

    paths = sorted(p for p in args.issues_dir.glob("*.md") if p.is_file())
    if not paths:
        print(f"error: no .md tickets in {args.issues_dir}", file=sys.stderr)
        return 2

    tickets = [parse_ticket(path) for path in paths]
    resolve_blockers(tickets)

    seen: dict[str, Path] = {}
    for ticket in tickets:
        if ticket.slug in seen:
            ticket.errors.append(f"duplicate slice id, also produced by {seen[ticket.slug].name}")
        else:
            seen[ticket.slug] = ticket.path

    for cycle in detect_cycles(tickets):
        print(f"error: dependency cycle: {cycle}", file=sys.stderr)

    failed = [t for t in tickets if t.errors]
    if failed or detect_cycles(tickets):
        for ticket in failed:
            for message in ticket.errors:
                print(f"error: {ticket.path.name}: {message}", file=sys.stderr)
        print(
            "\nNothing was written. Fix the tickets, or write the queue by hand;\n"
            "this converter never guesses at a missing scope or dependency.",
            file=sys.stderr,
        )
        return 1

    output = render(tickets, args.issues_dir)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
        print(f"wrote {args.output} ({len(tickets)} slices)", file=sys.stderr)
        print("Validate it next:", file=sys.stderr)
        print(
            f"  python3 {Path(__file__).parent / 'validate-queue.py'} {args.output}",
            file=sys.stderr,
        )
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
