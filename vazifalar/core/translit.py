"""
core/translit.py — Uzbek Latin → Cyrillic, for people who read Cyrillic. Used by the Telegram bot;
static/translit.js is the same rules for the web pages (keep the two in step; tests/test_translit.py).
# CORE: reusable — Uzbek orthography rules, no company data.
"""
APOS = "'ʻ‘’`ʼ"
VOWELS = set("aeiouAEIOU")

PAIRS = {"sh": "ш", "ch": "ч", "yo": "ё", "yu": "ю", "ya": "я", "ye": "е"}
SINGLE = {
    "a": "а", "b": "б", "d": "д", "f": "ф", "g": "г", "h": "ҳ", "i": "и", "j": "ж", "k": "к", "l": "л",
    "m": "м", "n": "н", "o": "о", "p": "п", "q": "қ", "r": "р", "s": "с", "t": "т", "u": "у", "v": "в",
    "x": "х", "y": "й", "z": "з", "c": "с", "w": "в",
}


def _case(src: str, out: str) -> str:
    if src.isupper() and (len(src) > 1 or len(out) == 1):
        return out.upper()
    if src[0].isupper():
        return out[0].upper() + out[1:]
    return out


# Whole words whose Cyrillic spelling is not letter-by-letter (Russian-origin month names).
WORDS = {
    "yanvar": "январь", "fevral": "февраль", "aprel": "апрель", "iyun": "июнь", "iyul": "июль",
    "avgust": "август", "sentabr": "сентябрь", "oktabr": "октябрь", "noyabr": "ноябрь", "dekabr": "декабрь",
    "sen": "сен", "okt": "окт", "noy": "ноя", "dek": "дек", "yan": "янв", "fev": "фев",
}


def to_cyrillic(text: str) -> str:  # CORE: reusable
    import re

    def word(m):
        w = m.group(0)
        c = WORDS.get(w.lower())
        if c is None:
            return _letters(w)
        return c.capitalize() if w[0].isupper() else c
    return re.sub(r"[A-Za-z][A-Za-z'ʻ‘’`ʼ]*", word, text)


def _letters(text: str) -> str:
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        lo = ch.lower()
        nxt = text[i + 1] if i + 1 < n else ""
        prev = text[i - 1] if i > 0 else ""
        word_start = prev == "" or (not prev.isalpha() and prev not in APOS)
        if lo in ("o", "g") and nxt and nxt in APOS:                       # o' → ў, g' → ғ
            out.append(_case(ch, "ў" if lo == "o" else "ғ"))
            i += 2
            continue
        pair = (ch + nxt)
        after = text[i + 2] if i + 2 < n else ""
        if pair.lower() == "yo" and after and after in APOS:   # yo' → йў ("Yo'nalish"), not ёъ
            out.append(_case(ch, "й"))
            i += 1
            continue
        if pair.lower() in PAIRS:
            src = pair if nxt.isupper() else ch
            out.append(_case(src, PAIRS[pair.lower()]))
            i += 2
            continue
        if lo == "e":                                         # e → э at a word start or after a vowel
            out.append(_case(ch, "э" if word_start or prev in VOWELS else "е"))
            i += 1
            continue
        if ch in APOS and prev.isalpha():                     # tutuq belgisi
            out.append("ъ")
            i += 1
            continue
        if lo in SINGLE:
            out.append(_case(ch, SINGLE[lo]))
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)
