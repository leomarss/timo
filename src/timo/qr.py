"""QR codes drawn in the terminal with half-block characters (two rows per line)."""
import segno

from timo.ui import RESET

QUIET_ZONE = 4  # light border, in modules, that scanners need around the code
# always black on bright white: scanners expect dark modules on a light background,
# so the terminal's own colours (often light on dark) can't be used, NO_COLOR or not
DARK_ON_LIGHT = "\033[30;107m"
HALF_BLOCKS = {(False, False): " ", (True, False): "▀", (False, True): "▄", (True, True): "█"}


def terminal_lines(text):
    """Lines that draw text as a QR code, each wrapped in DARK_ON_LIGHT ... RESET."""
    rows = [[bool(module) for module in row]
            for row in segno.make_qr(text).matrix_iter(scale=1, border=QUIET_ZONE)]
    if len(rows) % 2:
        rows.append([False] * len(rows[0]))
    return [DARK_ON_LIGHT + "".join(HALF_BLOCKS[pair] for pair in zip(top, bottom)) + RESET
            for top, bottom in zip(rows[::2], rows[1::2])]
