"""Replace all colored tailwind classes with black/white equivalents.

Skips GraphPage (user explicitly asked not to touch it).
"""
import re
from pathlib import Path

SRC = Path(__file__).parent.parent / "webapp-react" / "src"
SKIP = {"GraphPage.tsx"}

# Map of color families to B&W replacements.
# Order matters: more specific patterns first.
COLORS = ["indigo", "amber", "violet", "purple", "cyan", "emerald", "sky", "pink", "rose", "orange"]
SEMANTIC_WARN = ["red", "rose"]
SEMANTIC_OK = ["green", "emerald"]

# Primary accent (indigo/amber/violet/etc) → white/gray
REPLACEMENTS = []
for color in COLORS:
    # Backgrounds
    REPLACEMENTS += [
        (rf"\bbg-{color}-600\b(?!/)", "bg-white"),
        (rf"\bbg-{color}-500\b(?!/)", "bg-white"),
        (rf"\bbg-{color}-700\b(?!/)", "bg-white/10"),
        (rf"\bbg-{color}-800\b(?!/)", "bg-white/5"),
        (rf"\bbg-{color}-900\b(?!/)", "bg-white/5"),
        (rf"\bbg-{color}-950\b(?!/)", "bg-black"),
        # With alpha: bg-indigo-500/20 -> bg-white/20
        (rf"\bbg-{color}-\d{{3}}/(\d{{1,3}})\b", r"bg-white/\1"),
        # Gradient
        (rf"\bfrom-{color}-\d{{3}}/\d{{1,3}}\b", "from-white/10"),
        (rf"\bto-{color}-\d{{3}}/\d{{1,3}}\b", "to-white/10"),
        (rf"\bfrom-{color}-\d{{3}}\b", "from-white"),
        (rf"\bto-{color}-\d{{3}}\b", "to-white"),
        (rf"\bvia-{color}-\d{{3}}/\d{{1,3}}\b", "via-white/10"),
        (rf"\bvia-{color}-\d{{3}}\b", "via-white"),
        # Text
        (rf"\btext-{color}-200\b", "text-white"),
        (rf"\btext-{color}-300\b", "text-white"),
        (rf"\btext-{color}-400\b", "text-white"),
        (rf"\btext-{color}-500\b", "text-white/80"),
        (rf"\btext-{color}-600\b", "text-white/60"),
        # Border
        (rf"\bborder-{color}-\d{{3}}/(\d{{1,3}})\b", r"border-white/\1"),
        (rf"\bborder-{color}-\d{{3}}\b", "border-white/30"),
        # Ring
        (rf"\bring-{color}-\d{{3}}/(\d{{1,3}})\b", r"ring-white/\1"),
        (rf"\bring-{color}-\d{{3}}\b", "ring-white/30"),
        # Shadow
        (rf"\bshadow-{color}-\d{{3}}/(\d{{1,3}})\b", r"shadow-white/\1"),
        (rf"\bshadow-{color}-\d{{3}}\b", "shadow-white/20"),
        # Accent (sliders, checkboxes)
        (rf"\baccent-{color}-\d{{3}}\b", "accent-white"),
    ]

# Red → keep neutral "error" look (gray border, white text)
for color in SEMANTIC_WARN:
    REPLACEMENTS += [
        (rf"\bbg-{color}-600\b", "bg-white/10"),
        (rf"\bbg-{color}-500\b", "bg-white/10"),
        (rf"\bbg-{color}-900\b(?!/)", "bg-white/5"),
        (rf"\bbg-{color}-950\b(?!/)", "bg-black"),
        (rf"\bbg-{color}-\d{{3}}/(\d{{1,3}})\b", r"bg-white/\1"),
        (rf"\btext-{color}-300\b", "text-white"),
        (rf"\btext-{color}-400\b", "text-white/90"),
        (rf"\bborder-{color}-\d{{3}}/(\d{{1,3}})\b", r"border-white/\1"),
        (rf"\bborder-{color}-\d{{3}}\b", "border-white/30"),
    ]

# Green → keep as light/success hint (slightly brighter white)
for color in SEMANTIC_OK:
    REPLACEMENTS += [
        (rf"\bbg-{color}-600\b", "bg-white/20"),
        (rf"\bbg-{color}-500\b", "bg-white/20"),
        (rf"\bbg-{color}-900\b(?!/)", "bg-white/5"),
        (rf"\bbg-{color}-950\b(?!/)", "bg-black"),
        (rf"\bbg-{color}-\d{{3}}/(\d{{1,3}})\b", r"bg-white/\1"),
        (rf"\btext-{color}-300\b", "text-white"),
        (rf"\btext-{color}-400\b", "text-white"),
        (rf"\bborder-{color}-\d{{3}}/(\d{{1,3}})\b", r"border-white/\1"),
        (rf"\bborder-{color}-\d{{3}}\b", "border-white/30"),
    ]


def process(path: Path) -> bool:
    src = path.read_text(encoding="utf-8")
    orig = src
    for pat, repl in REPLACEMENTS:
        src = re.sub(pat, repl, src)
    if src != orig:
        path.write_text(src, encoding="utf-8")
        return True
    return False


def main():
    changed = []
    for tsx in SRC.rglob("*.tsx"):
        if tsx.name in SKIP:
            continue
        if process(tsx):
            changed.append(str(tsx.relative_to(SRC)))
    for ts in SRC.rglob("*.ts"):
        if ts.name in SKIP:
            continue
        if process(ts):
            changed.append(str(ts.relative_to(SRC)))
    print(f"Modified {len(changed)} files:")
    for c in changed:
        print(f"  {c}")


if __name__ == "__main__":
    main()
