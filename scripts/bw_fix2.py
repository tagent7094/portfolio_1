"""Second fixup pass for class malformations from the initial sweep."""
import re
from pathlib import Path

SRC = Path(__file__).parent.parent / "webapp-react" / "src"
SKIP = {"GraphPage.tsx"}


def fix_file(path: Path) -> bool:
    src = path.read_text(encoding="utf-8")
    orig = src

    # 1. Malformed double-opacity: bg-white/X/Y -> bg-white/X
    src = re.sub(r"\bbg-white/(\d+)/\d+\b", r"bg-white/\1", src)
    src = re.sub(r"\btext-white/(\d+)/\d+\b", r"text-white/\1", src)
    src = re.sub(r"\bborder-white/(\d+)/\d+\b", r"border-white/\1", src)

    # 2. Residual indigo-100 missed by first sweep
    for c in ("indigo", "amber", "violet", "purple", "cyan", "emerald", "sky", "pink", "rose"):
        src = re.sub(rf"\btext-{c}-100\b", "text-white", src)
        src = re.sub(rf"\bbg-{c}-100\b", "bg-white/10", src)
        src = re.sub(rf"\bborder-{c}-100\b", "border-white/20", src)

    # 3. bg-white/50 as panel/card bg → bg-white/10 (50 is too bright w/ text-white)
    # Only replace when on a background element, not buttons. Safe heuristic:
    # replace bg-white/50 unconditionally (50% white bg is never a good idea in our design)
    src = re.sub(r"\bbg-white/50\b", "bg-white/10", src)

    # 4. bg-white/20/80 residual (in case)
    src = re.sub(r"\bbg-white/20/80\b", "bg-white/20", src)

    # 5. Dedup 'bg-white/5 text-white' : 'bg-white/5 text-white' ternary (both branches same)
    src = re.sub(
        r"result\.quality\.passed\s*\?\s*'bg-white/5 text-white'\s*:\s*'bg-white/5 text-white'",
        "'bg-white/5 text-white'",
        src,
    )

    # 6. Remove residual color + fix any remaining blue/yellow/teal
    for c in ("blue", "yellow", "teal", "lime", "fuchsia"):
        src = re.sub(rf"\bbg-{c}-\d{{3}}\b", "bg-white/20", src)
        src = re.sub(rf"\btext-{c}-\d{{3}}\b", "text-white", src)
        src = re.sub(rf"\bborder-{c}-\d{{3}}\b", "border-white/30", src)

    if src != orig:
        path.write_text(src, encoding="utf-8")
        return True
    return False


def main():
    changed = []
    for tsx in SRC.rglob("*.tsx"):
        if tsx.name in SKIP:
            continue
        if fix_file(tsx):
            changed.append(str(tsx.relative_to(SRC)))
    for ts in SRC.rglob("*.ts"):
        if ts.name in SKIP:
            continue
        if fix_file(ts):
            changed.append(str(ts.relative_to(SRC)))
    print(f"Fixed {len(changed)} files:")
    for c in changed:
        print(f"  {c}")


if __name__ == "__main__":
    main()
