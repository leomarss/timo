"""How otpcli shows things. The texts themselves live in messages.py.

stdout gets what the user asked for: codes, lists, stats, and "✓" lines
confirming what was done. stderr gets everything else: errors ("✗"),
warnings ("!") and notes (dimmed), so piping stdout stays clean.

On a terminal, results are drawn as boxes and tables and codes are split
in two ("482 913"). When a stream isn't a terminal, the same information
comes out as plain lines, so scripts and pipes get bare values. Colour is
used only on a terminal, and never when NO_COLOR is set.
"""
import os
import re
import sys

from totp_cli import messages as msg

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"

_ANSI = re.compile(r"\033\[[0-9;]*m")
BAR_WIDTH = 18


# --- terminal detection --------------------------------------------------------------

def is_terminal(stream=None):
    stream = stream or sys.stdout
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


def color_enabled(stream=None):
    return not os.environ.get("NO_COLOR") and is_terminal(stream)


def paint(text, *styles, stream=None):
    if not styles or not color_enabled(stream):
        return text
    return "".join(styles) + text + RESET


def visible_len(text):
    return len(_ANSI.sub("", text))


# --- small formatting helpers --------------------------------------------------------

def time_color(seconds):
    if seconds > 20:
        return GREEN
    if seconds > 10:
        return YELLOW
    return RED


def plural(count, word, words=None):
    return f"{count} {word if count == 1 else (words or word + 's')}"


def group_code(code):
    """482913 -> 482 913, 48291305 -> 4829 1305 (for reading only, never for copying)."""
    half = len(code) // 2
    return f"{code[:half]} {code[half:]}"


def age(seconds):
    """A rough, human age: "just now", "5 minutes", "2 hours", "3 weeks"."""
    if seconds < 60:
        return msg.AGE_JUST_NOW
    for size, unit in reversed(msg.AGE_UNITS):
        if seconds >= size:
            return plural(int(seconds // size), unit)
    return msg.AGE_JUST_NOW


def bar(seconds, total=30, stream=None):
    filled = round(BAR_WIDTH * seconds / total)
    return (paint("█" * filled, time_color(seconds), stream=stream)
            + paint("░" * (BAR_WIDTH - filled), DIM, stream=stream))


# --- boxes and tables ----------------------------------------------------------------

def box(lines, title="", footer=(), stream=None):
    """Draw lines (which may already contain colour) in a rounded box."""
    stream = stream or sys.stdout
    width = max([visible_len(line) for line in list(lines) + list(footer)] + [visible_len(title) + 1]) + 4

    def edge(text):
        return paint(text, DIM, stream=stream)

    def row(line):
        return edge("│") + "  " + line + " " * (width - 4 - visible_len(line)) + "  " + edge("│")

    if title:
        top = edge("╭─ ") + title + edge(" " + "─" * (width - visible_len(title) - 3) + "╮")
    else:
        top = edge("╭" + "─" * width + "╮")
    out = [top] + [row(line) for line in lines]
    if footer:
        out.append(edge("├" + "─" * width + "┤"))
        out += [row(line) for line in footer]
    out.append(edge("╰" + "─" * width + "╯"))
    print("\n".join(out), file=stream)


def table(headers, rows, right=(), total=None, note=""):
    """Print an aligned table to stdout. `right` holds the indexes of right-aligned columns."""
    cells = [list(map(str, r)) for r in [headers] + list(rows) + ([total] if total else [])]
    widths = [max(len(r[i]) for r in cells) for i in range(len(headers))]

    def line(row):
        parts = [c.rjust(w) if i in right else c.ljust(w) for i, (c, w) in enumerate(zip(row, widths))]
        return (" " + "  ".join(parts)).rstrip()

    rule = paint(" " + "  ".join("─" * w for w in widths), DIM)
    lines = [paint(line(headers), BOLD), rule] + [line(list(map(str, r))) for r in rows]
    if total:
        lines += [rule, line(list(map(str, total))) + (paint("   " + note, DIM) if note else "")]
    print("\n".join(lines), file=sys.stdout)


# --- messages ------------------------------------------------------------------------

def _emit(stream, symbol, styles, message, detail=None, hints=()):
    if hints and is_terminal(stream):
        title = f"{paint(symbol, *styles, stream=stream)} {paint(message, BOLD, stream=stream)}"
        box(list(hints), title=title, stream=stream)
        stream.flush()
        return
    first = f"{paint(symbol, *styles, stream=stream)} {message}"
    if detail:
        first += "  " + paint(detail, DIM, stream=stream)
    lines = [first] + [paint("  " + h, DIM, stream=stream) for h in hints]
    print("\n".join(lines), file=stream)
    stream.flush()


def ok(message, detail=None):
    """Something the user asked for was done."""
    _emit(sys.stdout, "✓", (GREEN, BOLD), message, detail)


def ok_rows(rows):
    """Several ✓ lines whose details line up."""
    width = max(len(message) for message, _ in rows)
    for message, detail in rows:
        ok(message.ljust(width), detail)


def warn(message, *hints):
    _emit(sys.stderr, "!", (YELLOW, BOLD), message, hints=hints)


def error(message, *hints):
    """An error; with hint lines it's drawn as a box on a terminal."""
    _emit(sys.stderr, "✗", (RED, BOLD), message, hints=hints)


def note(message):
    """Background information, not the result of the command."""
    print(paint(message, DIM, stream=sys.stderr), file=sys.stderr)


def out(text=""):
    """A plain result line."""
    print(text, file=sys.stdout)
