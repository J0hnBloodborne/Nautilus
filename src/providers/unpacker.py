"""
JavaScript p,a,c,k,e,d unpacker ported to Python.

Many streaming embed hosts use Dean Edwards' JS packer:
  eval(function(p,a,c,k,e,d){...})

This module unpacks those to plain JS so we can regex out stream URLs.
"""
from __future__ import annotations
import re
import math

_PACKED_RE = re.compile(
    r"eval\(function\(p,a,c,k,e,[dr]\)\{.*?\}\('(.*?)',(\d+),(\d+),'(.*?)'\.split\('\|'\)",
    re.DOTALL,
)

def _base_encode(val: int, base: int) -> str:
    """Encode `val` in the given base (up to 62)."""
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if val < base:
        return chars[val]
    return _base_encode(val // base, base) + chars[val % base]


def detect(text: str) -> bool:
    """Check if text contains packed JS."""
    return bool(_PACKED_RE.search(text))


def unpack(text: str) -> str:
    """Unpack packed JS. Returns the unpacked source or the original text."""
    match = _PACKED_RE.search(text)
    if not match:
        return text

    payload, radix_s, count_s, symtab_raw = match.groups()
    radix = int(radix_s)
    count = int(count_s)
    symtab = symtab_raw.split("|")

    # Pad symtab to count entries
    while len(symtab) < count:
        symtab.append("")

    def _replacer(m: re.Match) -> str:
        word = m.group(0)
        try:
            idx = int(word, radix) if radix <= 36 else _decode_base62(word)
        except (ValueError, IndexError):
            return word
        return symtab[idx] if idx < len(symtab) and symtab[idx] else word

    # Replace each word token
    # The pattern matches wordlike tokens (digits + letters)
    result = re.sub(r'\b\w+\b', _replacer, payload)
    return result


def _decode_base62(s: str) -> int:
    """Decode a base-62 encoded string to int."""
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    val = 0
    for ch in s:
        val = val * 62 + chars.index(ch)
    return val
