"""Scan a QR code with the webcam: the optional 'webcam' extra (PyAV and zxing-cpp).

PyAV reads the camera and zxing-cpp decodes the QR code. The camera picture is
previewed in the terminal itself. Terminals that speak the kitty graphics
protocol (kitty, Ghostty, WezTerm) show it as a real image; elsewhere it's drawn
with half-block characters: each cell's foreground colour is one pixel and its
background colour the pixel below it.
Frames only live in memory while scanning; nothing is written to disk.
"""
import base64
import os
import re
import select
import shutil
import sys
import time
import zlib

from totp_cli import messages as msg

MAX_PREVIEW_WIDTH = 100  # cells, for half blocks; wider only costs redraw time, it doesn't help aiming
MAX_IMAGE_WIDTH = 640  # pixels sent per frame with the kitty protocol; the terminal scales it up
STATUS_ROWS = 2  # the line above the preview and a blank one under it
NO_FRAME_TIMEOUT = 5  # seconds without a frame before giving up on the camera
QUERY_TIMEOUT = 0.5  # seconds to wait for the terminal to say which graphics it supports
DEFAULT_CELL = (8, 16)  # cell size in pixels when the terminal doesn't report it
HALF_BLOCK = "▀"
RESET = "\x1b[0m"
IMAGE_ID = 7031  # our image in the terminal; any number, as long as it's always the same
KITTY_CHUNK = 4096  # the kitty protocol takes base64 data in chunks of at most this many bytes
KITTY_QUERY = "\x1b_Gi=31,s=1,v=1,a=q,t=d,f=24;AAAA\x1b\\"  # "could you show this 1-pixel image?"
DEVICE_ATTRIBUTES = "\x1b[c"  # every terminal answers this, so it marks the end of the answers
# a terminal's answers and keys like the arrows start with Esc too; these aren't the Esc key
ESCAPE_SEQUENCE = re.compile(rb"\x1b(\[[0-?]*[ -/]*[@-~]|_[^\x1b]*\x1b\\|O.)")


class Unavailable(Exception):
    """The webcam can't be used: the extra isn't installed, no camera, no terminal."""

    def __init__(self, message, *hints):
        super().__init__(message)
        self.message = message
        self.hints = hints


def first_match(frames, decode, accept):
    """Decode frames until one holds text that accept() takes; that text, or None if frames run out."""
    for frame in frames:
        text = decode(frame)
        if text and accept(text):
            return text
    return None


def scan(accept):
    """Preview the camera in the terminal until a QR code that accept() takes is in view.

    Returns its text, or None when the user cancels (Esc or q).
    Raises Unavailable when the webcam can't be used.
    """
    try:
        import av
        import zxingcpp
    except ImportError:
        raise Unavailable(msg.NO_WEBCAM_EXTRA, msg.NO_WEBCAM_EXTRA_HINT) from None
    if sys.platform != "darwin" and not sys.platform.startswith("linux"):
        raise Unavailable(msg.WEBCAM_UNSUPPORTED)
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise Unavailable(msg.WEBCAM_NO_TERMINAL)

    camera = _open_camera(av)
    try:
        with Preview() as preview:
            frames = preview.show(_camera_frames(camera))
            return first_match(frames, lambda frame: decode(zxingcpp, frame), accept)
    finally:
        camera.close()


def decode(zxingcpp, frame):
    """The text of the QR code in a camera frame, or "".

    zxing-cpp reads mirrored codes too, so the frame is passed as the camera sees it.
    """
    gray = frame.reformat(format="gray")
    image = memoryview(plane_bytes(gray, 1)).cast("B", (gray.height, gray.width))
    for barcode in zxingcpp.read_barcodes(image, formats=zxingcpp.BarcodeFormat.QRCode):
        if barcode.text:
            return barcode.text
    return ""


def plane_bytes(frame, bytes_per_pixel):
    """A frame's pixels, row after row, without the padding FFmpeg adds at the end of each row."""
    plane = frame.planes[0]
    row = frame.width * bytes_per_pixel
    data = bytes(plane)
    if plane.line_size == row:
        return data
    return b"".join(data[y * plane.line_size:y * plane.line_size + row] for y in range(frame.height))


# --- the camera ----------------------------------------------------------------------

def _camera_source():
    """(device, FFmpeg input format, option sets to try in turn, hint if none opens)."""
    if sys.platform == "darwin":
        # avfoundation refuses its default 29.97 fps on most cameras
        return ("0", "avfoundation",
                [{"framerate": "30", "video_size": "1280x720"}, {"framerate": "30"}, {"framerate": "15"}],
                msg.WEBCAM_UNAVAILABLE_HINT_MACOS)
    return "/dev/video0", "v4l2", [{"video_size": "1280x720"}, {}], msg.WEBCAM_UNAVAILABLE_HINT_LINUX


def _open_camera(av):
    device, input_format, attempts, hint = _camera_source()
    for options in attempts:
        try:
            return av.open(device, format=input_format, options=options)
        except (OSError, av.FFmpegError):
            continue
    raise Unavailable(msg.WEBCAM_UNAVAILABLE, hint)


def _camera_frames(camera):
    """Frames from the camera as they come, for as long as it gives them."""
    last_frame = time.monotonic()
    while True:
        try:
            for packet in camera.demux(video=0):
                for frame in packet.decode():
                    last_frame = time.monotonic()
                    yield frame
            raise Unavailable(msg.WEBCAM_UNAVAILABLE)  # the camera went away
        except BlockingIOError:  # no frame ready yet
            if time.monotonic() - last_frame > NO_FRAME_TIMEOUT:
                raise Unavailable(msg.WEBCAM_UNAVAILABLE, _camera_source()[3]) from None
            time.sleep(0.005)


# --- the preview ---------------------------------------------------------------------

def preview_size(cols, rows, width, height):
    """Pixel size of the preview of a width x height picture in a cols x rows area of cells.

    Each cell shows two pixels stacked, and is about twice as tall as it is wide,
    so the pixels come out square. The height is even, a whole number of cells.
    """
    cols = max(1, min(cols, MAX_PREVIEW_WIDTH))
    pixel_rows = max(2, rows * 2)
    preview_width = max(1, min(cols, pixel_rows * width // height))
    preview_height = max(2, min(pixel_rows, preview_width * height // width))
    return preview_width, preview_height - preview_height % 2


def render(rgb, width, height, truecolor=True):
    """Lines of half-block cells showing rgb (width x height pixels, 3 bytes each), mirrored.

    Mirrored so that moving the QR code left moves it left on screen. Without
    24-bit colour support it's drawn in the 24 shades of grey every 256-colour
    terminal has, which is plenty to aim a black and white code.
    """
    stride = width * 3
    cell = _truecolor_cell if truecolor else _gray_cell
    lines = []
    for y in range(0, height - 1, 2):
        top = y * stride
        bottom = top + stride
        cells = [cell(rgb, top + x, bottom + x) for x in range(stride - 3, -1, -3)]
        lines.append("".join(cells) + RESET)
    return lines


def _truecolor_cell(rgb, top, bottom):
    return (f"\x1b[38;2;{rgb[top]};{rgb[top + 1]};{rgb[top + 2]};"
            f"48;2;{rgb[bottom]};{rgb[bottom + 1]};{rgb[bottom + 2]}m{HALF_BLOCK}")


def _gray(rgb, i):
    luma = (rgb[i] * 299 + rgb[i + 1] * 587 + rgb[i + 2] * 114) // 1000
    return 232 + luma * 23 // 255  # 232-255: the greyscale ramp, black to white


def _gray_cell(rgb, top, bottom):
    return f"\x1b[38;5;{_gray(rgb, top)};48;5;{_gray(rgb, bottom)}m{HALF_BLOCK}"


def image_layout(cols, rows, cell_width, cell_height, width, height):
    """How to show a width x height picture as an image in a cols x rows area of cells.

    Returns (pixels wide, pixels high) to send, scaled down to at most MAX_IMAGE_WIDTH
    wide, and the (cols, rows) of cells the terminal stretches it over.
    """
    scale = min(cols * cell_width / width, rows * cell_height / height)
    cells_wide = max(1, int(width * scale / cell_width))
    cells_high = max(1, int(height * scale / cell_height))
    send_width = max(1, min(MAX_IMAGE_WIDTH, round(width * scale)))
    send_height = max(1, round(send_width * height / width))
    return send_width, send_height, cells_wide, cells_high


def mirror_bgr(bgr, width, height):
    """Mirror a BGR picture left to right, as RGB.

    Reversing a row's bytes reverses the pixel order and turns each pixel's
    B, G, R into R, G, B, so one slice per row does both.
    """
    stride = width * 3
    return b"".join(bgr[y * stride:(y + 1) * stride][::-1] for y in range(height))


def kitty_image(rgb, width, height, cols, rows):
    """The kitty graphics escapes that show rgb (width x height pixels) over cols x rows cells.

    The image always has the same id and placement id, so each frame replaces the
    last one in place. The cursor stays put (C=1) and the terminal sends no
    replies (q=2), which would otherwise turn up as keypresses.
    """
    data = base64.standard_b64encode(zlib.compress(rgb, 1)).decode("ascii")
    chunks = [data[i:i + KITTY_CHUNK] for i in range(0, len(data), KITTY_CHUNK)] or [""]
    first = f"a=T,f=24,o=z,s={width},v={height},c={cols},r={rows},i={IMAGE_ID},p=1,C=1,q=2"
    escapes = []
    for n, chunk in enumerate(chunks):
        more = int(n < len(chunks) - 1)
        keys = f"{first},m={more}" if n == 0 else f"m={more},q=2"
        escapes.append(f"\x1b_G{keys};{chunk}\x1b\\")
    return "".join(escapes)


def kitty_supported(answers):
    """Whether the terminal's answers to KITTY_QUERY and DEVICE_ATTRIBUTES include a yes to the query."""
    return b"\x1b_Gi=31;OK" in answers


def cancel_pressed(keys):
    """Whether keys (bytes read from the terminal) hold Esc or q.

    Escape sequences, such as arrow keys or late answers from the terminal, are
    left out: they start with the same byte as the Esc key.
    """
    keys = ESCAPE_SEQUENCE.sub(b"", keys)
    return any(key in keys for key in (b"\x1b", b"q", b"Q"))


def _cell_size(fd):
    """A terminal cell's size in pixels, as the terminal reports it, or DEFAULT_CELL."""
    try:
        import fcntl
        import struct
        import termios

        rows, cols, x_pixels, y_pixels = struct.unpack("HHHH", fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8))
    except (ImportError, OSError):
        return DEFAULT_CELL
    if not (rows and cols and x_pixels and y_pixels):
        return DEFAULT_CELL
    return x_pixels / cols, y_pixels / rows


class Preview:
    """The terminal while scanning: alternate screen, no cursor, keys read as they come.

    Everything is put back on exit, including after Ctrl-C, which still interrupts.
    """

    def __enter__(self):
        import termios

        self._fd = sys.stdin.fileno()
        self._saved = termios.tcgetattr(self._fd)
        raw = termios.tcgetattr(self._fd)
        raw[3] &= ~(termios.ECHO | termios.ICANON)
        raw[6][termios.VMIN] = 0
        raw[6][termios.VTIME] = 0
        termios.tcsetattr(self._fd, termios.TCSANOW, raw)
        self._truecolor = os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")
        self._images = self._ask_for_images()
        self._layout = None
        self._write("\x1b[?1049h\x1b[?25l\x1b[2J")  # alternate screen, hide cursor, clear
        return self

    def __exit__(self, *exc):
        import termios

        if self._images:
            self._write(f"\x1b_Ga=d,d=I,i={IMAGE_ID},q=2\x1b\\")  # forget our image
        self._write(RESET + "\x1b[?25h\x1b[?1049l")  # show cursor, back to the normal screen
        termios.tcsetattr(self._fd, termios.TCSAFLUSH, self._saved)  # drops keys typed while scanning
        return False

    def _ask_for_images(self):
        """Whether the terminal can show images with the kitty graphics protocol.

        Asks it, then reads its answers up to the reply to DEVICE_ATTRIBUTES, which
        every terminal sends; a terminal that ignores the question just doesn't
        say OK. Gives up after QUERY_TIMEOUT, e.g. when nothing answers at all.
        """
        self._write(KITTY_QUERY + DEVICE_ATTRIBUTES)
        answers = b""
        deadline = time.monotonic() + QUERY_TIMEOUT
        while not re.search(rb"\x1b\[\?[0-9;]*c", answers):
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([self._fd], [], [], left)[0]:
                break
            answers += os.read(self._fd, 1024)
        return kitty_supported(answers)

    def show(self, frames):
        """Draw each frame as it passes through, until the user cancels."""
        for frame in frames:
            if self._cancelled():
                return
            self._draw(frame)
            yield frame

    def _cancelled(self):
        keys = b""
        while select.select([self._fd], [], [], 0)[0]:
            read = os.read(self._fd, 1024)
            if not read:
                break
            keys += read
        return cancel_pressed(keys)

    def _draw(self, frame):
        cols, rows = shutil.get_terminal_size()
        if cols <= 0 or rows <= 0:  # some terminals report 0 x 0, which Python 3.9 passes on
            cols, rows = 80, 24
        status = msg.WEBCAM_PREVIEW_STATUS[:cols]
        if self._images:
            self._draw_image(frame, cols, rows, status)
        else:
            self._draw_blocks(frame, cols, rows, status)

    def _draw_image(self, frame, cols, rows, status):
        width, height, cells_wide, cells_high = image_layout(
            cols, rows - STATUS_ROWS, *_cell_size(sys.stdout.fileno()), frame.width, frame.height)
        clear = "\x1b[2J" if (cols, rows, cells_wide, cells_high) != self._layout else ""
        self._layout = (cols, rows, cells_wide, cells_high)
        small = frame.reformat(width=width, height=height, format="bgr24")
        rgb = mirror_bgr(plane_bytes(small, 3), width, height)  # mirrored like a mirror
        column = (cols - cells_wide) // 2 + 1
        self._write(f"{clear}\x1b[H{status}\x1b[K\x1b[{STATUS_ROWS + 1};{column}H"
                    + kitty_image(rgb, width, height, cells_wide, cells_high))

    def _draw_blocks(self, frame, cols, rows, status):
        # one column spare: a line that fills the width leaves the cursor on its last cell,
        # and clearing to the end of the line from there would erase that cell
        width, height = preview_size(cols - 1, rows - STATUS_ROWS, frame.width, frame.height)
        small = frame.reformat(width=width, height=height, format="rgb24")
        margin = " " * ((cols - width) // 2)
        lines = [status, ""]
        lines += [margin + line for line in render(plane_bytes(small, 3), width, height, self._truecolor)]
        # redraw in place: clear each line's leftovers and anything below, so there's no flicker
        self._write("\x1b[H" + "\x1b[K\r\n".join(lines) + "\x1b[K\x1b[J")

    @staticmethod
    def _write(text):
        sys.stdout.write(text)
        sys.stdout.flush()
