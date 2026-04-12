"""Fix unreadable class combinations left by bw_sweep.

Key fixes:
- bg-white text-white -> bg-white text-black (primary button contrast)
- hover:bg-white hover:bg-white -> hover:bg-white/90 (dedup)
- Missing colors: bg-yellow-*, bg-blue-* (in engagementColor) -> grayscale
- Collapse redundant ternaries like 'bg-white text-white : bg-white text-white'
"""
import re
from pathlib import Path

SRC = Path(__file__).parent.parent / "webapp-react" / "src"
SKIP = {"GraphPage.tsx"}


def fix_file(path: Path) -> bool:
    src = path.read_text(encoding="utf-8")
    orig = src

    # 1. bg-white + text-white on same element = make text black
    # Match if both are in same className string (within same quotes)
    def fix_white_on_white(m):
        s = m.group(0)
        # If contains both 'bg-white' (not /opacity) and 'text-white' (not /opacity), swap text to black
        if re.search(r"\bbg-white\b(?!/)", s) and re.search(r"\btext-white\b(?!/)", s):
            s = re.sub(r"\btext-white\b(?!/)", "text-black", s)
        return s

    # Apply within className="..." strings and template literals
    src = re.sub(r'"[^"]*"', fix_white_on_white, src)
    src = re.sub(r"'[^']*'", fix_white_on_white, src)
    src = re.sub(r"`[^`]*`", fix_white_on_white, src, flags=re.DOTALL)

    # 2. Deduplicate hover:bg-white hover:bg-white
    src = re.sub(r"hover:bg-white\s+hover:bg-white\b", "hover:bg-white/90", src)
    src = re.sub(r"(bg-white hover:bg-white)\b", "bg-white hover:bg-white/90", src)

    # 3. Residual colors that weren't in the sweep list
    residual_colors = ["yellow", "blue", "teal", "lime", "fuchsia"]
    for c in residual_colors:
        src = re.sub(rf"\bbg-{c}-\d{{3}}\b", "bg-white/20", src)
        src = re.sub(rf"\btext-{c}-\d{{3}}\b", "text-white", src)
        src = re.sub(rf"\bborder-{c}-\d{{3}}\b", "border-white/30", src)

    # 4. gray-600 literal bg used as accent should become gray-700 neutral
    # (bg-gray-600 for engagement dots etc. is fine to keep as gray)
    # No change here — gray is already monochrome.

    # 5. Fix "bg-white text-white" in CustomizePage mode buttons where all 3 cases collapse
    # We already fixed via step 1, but also simplify the ternary if all branches are identical
    src = re.sub(
        r"mode === 'quick'\s*\?\s*'bg-white hover:bg-white/90'\s*:\s*mode === 'full'\s*\?\s*'bg-white hover:bg-white/90'\s*:\s*'bg-white hover:bg-white/90'",
        "'bg-white hover:bg-white/90'",
        src,
    )

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
