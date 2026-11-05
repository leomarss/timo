import sys

import pytest

from totp_cli import clipboard, webcam

from test_import import A, B, make_uri

SECRET = "JBSWY3DPEHPK3PXP"
LINK = f"otpauth://totp/GitHub:me?secret={SECRET}&issuer=GitHub"


# --- picking the QR code out of the camera frames ------------------------------------

def decode_as_is(frame):
    return frame  # each fake frame is the text a QR detector would find in it


def test_first_match_skips_frames_without_a_qr_code():
    assert webcam.first_match(["", "", LINK], decode_as_is, lambda t: True) == LINK


def test_first_match_skips_codes_not_accepted():
    frames = ["https://example.com", LINK]
    assert webcam.first_match(frames, decode_as_is, lambda t: t.startswith("otpauth")) == LINK


def test_first_match_is_none_when_cancelled():
    assert webcam.first_match(iter(["", ""]), decode_as_is, lambda t: True) is None


def qr_frame(cv2, text, mirrored):
    img = cv2.QRCodeEncoder.create().encode(text)
    img = cv2.resize(img, None, fx=6, fy=6, interpolation=cv2.INTER_NEAREST)
    img = cv2.copyMakeBorder(img, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
    frame = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return cv2.flip(frame, 1) if mirrored else frame


@pytest.mark.parametrize("mirrored", [False, True])
def test_decode_reads_a_qr_code_either_way_round(mirrored):
    cv2 = pytest.importorskip("cv2")
    frame = qr_frame(cv2, LINK, mirrored)
    assert webcam.decode(cv2, cv2.QRCodeDetector(), frame) == LINK


def test_decode_tries_the_mirrored_frame_when_the_code_cant_be_read():
    class Detector:  # finds a code, but only reads it mirrored
        def detectAndDecode(self, frame):
            return (LINK if frame[0][0] == "mirrored" else ""), "corners", None

    class Cv2:
        @staticmethod
        def flip(frame, axis):
            return [["mirrored"]]

    assert webcam.decode(Cv2, Detector(), [["raw"]]) == LINK


def test_decode_skips_the_second_try_when_there_is_no_code():
    tries = []

    class Detector:
        def detectAndDecode(self, frame):
            tries.append(frame)
            return "", None, None

    assert webcam.decode(None, Detector(), "frame") == ""
    assert tries == ["frame"]


def test_scan_without_opencv_says_how_to_install_it(monkeypatch):
    monkeypatch.setitem(sys.modules, "cv2", None)  # import cv2 fails
    with pytest.raises(webcam.Unavailable) as e:
        webcam.scan(lambda t: True)
    assert "OpenCV" in e.value.message
    assert any("pipx inject totp-cli opencv-python" in hint for hint in e.value.hints)


# --- the commands --------------------------------------------------------------------

@pytest.fixture(autouse=True)
def no_clipboard(monkeypatch):
    monkeypatch.setattr(clipboard, "copy", lambda text: False)


def fake_camera(monkeypatch, *codes):
    """The camera sees these QR codes in turn, each scan going on from where the last stopped."""
    shown = iter(codes)
    monkeypatch.setattr(webcam, "scan", lambda accept: webcam.first_match(shown, decode_as_is, accept))


def test_add_with_webcam_when_the_path_is_left_empty(cli, monkeypatch):
    fake_camera(monkeypatch, "https://example.com/menu", LINK)
    code, out, err = cli.run("--add", answers=("n", ""))
    assert code == 0, err
    assert "✓ Added GitHub (me)" in out
    assert cli.load()[0]["secret"] == SECRET


def test_add_with_webcam_cancelled_adds_nothing(cli, monkeypatch):
    fake_camera(monkeypatch)
    code, _, err = cli.run("--add", answers=("n", ""))
    assert code == 1
    assert "✗ Nothing added" in err
    assert not cli.secrets.exists()


def test_add_with_webcam_unavailable_shows_why(cli, monkeypatch):
    def unavailable(accept):
        raise webcam.Unavailable("Can't use the webcam", "allow the camera")
    monkeypatch.setattr(webcam, "scan", unavailable)
    code, _, err = cli.run("--add", answers=("n", ""))
    assert code == 1
    assert "Can't use the webcam" in err and "allow the camera" in err
    assert not cli.secrets.exists()


def test_initialize_with_webcam_reads_each_part_once(cli, monkeypatch):
    first = make_uri([A], batch_index=0, batch_size=2)
    second = make_uri([B], batch_index=1, batch_size=2)
    # still pointing at the first QR code when asked for the second
    fake_camera(monkeypatch, first, first, first, second)
    code, out, err = cli.run("--initialize", answers=("n", "", "", ""))
    assert code == 0, err
    assert "QR 2 of 2" in out
    assert [a["issuer"] for a in cli.load()] == ["GitHub", "AWS"]
