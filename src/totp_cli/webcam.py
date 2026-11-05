"""Scan a QR code with the webcam: the optional 'webcam' extra (OpenCV).

Frames only live in memory while scanning; nothing is written to disk.
"""
import os

from totp_cli import messages as msg

WINDOW = "otpcli - show the QR code to the camera, Esc to cancel"
ESC = 27


class Unavailable(Exception):
    """The webcam can't be used: the extra isn't installed, no camera, no window."""

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
    """Show the camera in a window until a QR code that accept() takes is in view.

    Returns its text, or None when the user cancels (Esc, q, or closing the window).
    Raises Unavailable when the webcam can't be used.
    """
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")  # no camera chatter in the terminal
    try:
        import cv2
    except ImportError:
        raise Unavailable(msg.NO_WEBCAM_EXTRA, msg.NO_WEBCAM_EXTRA_HINT) from None

    camera = cv2.VideoCapture(0)
    try:
        if not camera.isOpened():
            raise Unavailable(msg.WEBCAM_UNAVAILABLE, msg.WEBCAM_UNAVAILABLE_HINT)
        detector = cv2.QRCodeDetector()
        try:
            return first_match(_frames(cv2, camera), lambda frame: decode(cv2, detector, frame), accept)
        except cv2.error as e:  # e.g. no display to open the window on
            raise Unavailable(msg.WEBCAM_FAILED.format(error=str(e).strip().splitlines()[-1])) from None
    finally:
        camera.release()
        cv2.destroyAllWindows()
        cv2.waitKey(1)  # lets the window actually close


def decode(cv2, detector, frame):
    """The text of the QR code in frame, or "".

    When a code is found but can't be read, the mirrored frame gets a second try:
    some webcams mirror their picture, and the other way round often reads
    a code the first one missed.
    """
    text, points, _ = detector.detectAndDecode(frame)
    if not text and points is not None:
        text, _, _ = detector.detectAndDecode(cv2.flip(frame, 1))
    return text


def _frames(cv2, camera):
    """Camera frames, each shown mirrored in the window, until the user cancels."""
    while True:
        ok, frame = camera.read()
        if not ok:
            raise Unavailable(msg.WEBCAM_UNAVAILABLE, msg.WEBCAM_UNAVAILABLE_HINT)
        cv2.imshow(WINDOW, cv2.flip(frame, 1))  # mirrored, so moving the code left moves it left
        key = cv2.waitKey(1) & 0xFF
        if key in (ESC, ord("q")) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
            return
        yield frame
