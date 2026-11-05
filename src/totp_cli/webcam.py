"""Scan a QR code with the webcam: the optional 'webcam' extra (PyAV and zxing-cpp).

PyAV reads the camera and zxing-cpp decodes the QR code. The camera picture is
previewed in the terminal itself, drawn with half-block characters: each cell's
foreground colour is one pixel and its background colour the pixel below it.
Frames only live in memory while scanning; nothing is written to disk.
"""
import os
import select
import shutil
import sys
import time

from totp_cli import messages as msg

CANCEL_KEYS = (b"\x1b", b"q", b"Q")  # Esc, q
MAX_PREVIEW_WIDTH = 100  # cells; wider only costs redraw time, it doesn't help aiming
STATUS_ROWS = 2  # the line above the preview and a blank one under it
NO_FRAME_TIMEOUT = 5  # seconds without a frame before giving up on the camera
HALF_BLOCK = "▀"
RESET = "\x1b[0m"


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


class Preview:
    """The terminal while scanning: alternate screen, no cursor, keys read one at a time.

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
        self._write("\x1b[?1049h\x1b[?25l\x1b[2J")  # alternate screen, hide cursor, clear
        return self

    def __exit__(self, *exc):
        import termios

        self._write(RESET + "\x1b[?25h\x1b[?1049l")  # show cursor, back to the normal screen
        termios.tcsetattr(self._fd, termios.TCSAFLUSH, self._saved)  # drops keys typed while scanning
        return False

    def show(self, frames):
        """Draw each frame as it passes through, until the user cancels."""
        for frame in frames:
            if self._cancelled():
                return
            self._draw(frame)
            yield frame

    def _cancelled(self):
        while select.select([self._fd], [], [], 0)[0]:
            key = os.read(self._fd, 1)
            if not key:
                return False
            if key in CANCEL_KEYS:
                return True
        return False

    def _draw(self, frame):
        cols, rows = shutil.get_terminal_size()
        if cols <= 0 or rows <= 0:  # some terminals report 0 x 0, which Python 3.9 passes on
            cols, rows = 80, 24
        # one column spare: a line that fills the width leaves the cursor on its last cell,
        # and clearing to the end of the line from there would erase that cell
        width, height = preview_size(cols - 1, rows - STATUS_ROWS, frame.width, frame.height)
        small = frame.reformat(width=width, height=height, format="rgb24")
        margin = " " * ((cols - width) // 2)
        lines = [msg.WEBCAM_PREVIEW_STATUS[:cols], ""]
        lines += [margin + line for line in render(plane_bytes(small, 3), width, height, self._truecolor)]
        # redraw in place: clear each line's leftovers and anything below, so there's no flicker
        self._write("\x1b[H" + "\x1b[K\r\n".join(lines) + "\x1b[K\x1b[J")

    @staticmethod
    def _write(text):
        sys.stdout.write(text)
        sys.stdout.flush()
