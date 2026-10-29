"""Tolerant JSON parsing for long model output.

Gemini's JSON mode occasionally emits a structurally broken document when the output is long (a missing comma between members,
or a cut-off ending). Throwing the whole case away for that wastes a full model call, so repair the two usual breakages and only
then give up.
"""
import json
from typing import Any


def _close_open(s: str) -> str:
    """Close an unterminated string and any open brackets, dropping a dangling comma or colon."""
    stack, in_str, esc = [], False, False
    for ch in s:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()
    if in_str:
        s += '"'
    s = s.rstrip()
    while s and s[-1] in ",:":
        s = s[:-1].rstrip()
    return s + "".join(reversed(stack))


def loads_lenient(text: str) -> Any:
    """json.loads, repairing a missing comma (up to a dozen times) and a truncated ending. Raises ValueError if it cannot."""
    if text is None:
        raise ValueError("empty model response")
    try:
        return json.loads(text)
    except json.JSONDecodeError as first:
        error = first
    start, end = text.find("{"), text.rfind("}") + 1
    s = text[start:] if start != -1 else text  # keep a truncated tail: there may be no closing brace
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    for _ in range(12):
        try:
            return json.loads(s)
        except json.JSONDecodeError as e:
            if e.msg.startswith("Expecting ',' delimiter"):
                k = e.pos
                while k > 0 and s[k - 1] in " \t\r\n":
                    k -= 1
                s = s[:k] + "," + s[k:]
                continue
            break
    try:
        return json.loads(_close_open(s))
    except json.JSONDecodeError:
        raise error
