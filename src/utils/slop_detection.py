"""AI-slop pattern detection — extracted from opening_line_massacre for use by the batch amplifier."""

AI_SLOP_PATTERNS = [
    "in today's fast-paced",
    "in the world of",
    "let me tell you",
    "here's the thing",
    "here's what nobody tells you",
    "hot take:",
    "unpopular opinion:",
    "let that sink in",
    "read that again",
    "i'll say it louder",
    "can we talk about",
    "it's time we talked about",
    "the truth about",
    "the secret to",
    "what if i told you",
    "imagine this",
    "picture this",
    "buckle up",
    "spoiler alert",
    "plot twist",
    "game changer",
    "here's why",
    "stop what you're doing",
    "this changed everything",
    "i used to think",
    "let's be honest",
    "real talk",
    "hard truth",
    "controversial opinion",
    "most people don't realize",
    "nobody is talking about",
    "the biggest mistake",
    "i'm going to be brutally honest",
    "a thread \U0001f9f5",
]


def is_slop(text: str) -> bool:
    """Check if an opening line matches known AI-slop patterns."""
    lower = text.lower().strip()
    for pattern in AI_SLOP_PATTERNS:
        if lower.startswith(pattern) or pattern in lower[:80]:
            return True
    emoji_count = sum(1 for c in text if ord(c) > 0x1F600)
    if emoji_count > 2:
        return True
    return False
