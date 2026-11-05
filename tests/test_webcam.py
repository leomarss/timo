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


def qr_frame(av, zxingcpp, text, mirrored):
    """A grey camera frame of a QR code, padded the way FFmpeg pads rows."""
    code = memoryview(zxingcpp.write_barcode(zxingcpp.BarcodeFormat.QRCode, text, width=300, height=300))
    height, width = code.shape
    pixels = code.tobytes()
    rows = [pixels[y * width:(y + 1) * width] for y in range(height)]
    if mirrored:
        rows = [row[::-1] for row in rows]
    frame = av.VideoFrame(width, height, "gray")
    padding = b"\0" * (frame.planes[0].line_size - width)
    frame.planes[0].update(b"".join(row + padding for row in rows))
    return frame


@pytest.mark.parametrize("mirrored", [False, True])
def test_decode_reads_a_qr_code_either_way_round(mirrored):
    av = pytest.importorskip("av")
    zxingcpp = pytest.importorskip("zxingcpp")
    assert webcam.decode(zxingcpp, qr_frame(av, zxingcpp, LINK, mirrored)) == LINK


def test_decode_is_empty_without_a_qr_code():
    av = pytest.importorskip("av")
    zxingcpp = pytest.importorskip("zxingcpp")
    frame = av.VideoFrame(64, 64, "gray")
    frame.planes[0].update(b"\x80" * (frame.planes[0].line_size * 64))
    assert webcam.decode(zxingcpp, frame) == ""


def test_scan_without_the_extra_says_how_to_install_it(monkeypatch):
    monkeypatch.setitem(sys.modules, "av", None)  # import av fails
    with pytest.raises(webcam.Unavailable) as e:
        webcam.scan(lambda t: True)
    assert "PyAV" in e.value.message
    assert any("pipx inject totp-cli av zxing-cpp" in hint for hint in e.value.hints)


# --- the terminal preview ------------------------------------------------------------

def test_preview_size_fits_the_height_and_keeps_square_pixels():
    # 16:9 camera in a 200 x 20 area: 40 pixel rows allow 71 pixels wide (40 * 16 / 9),
    # which is 39 rows tall, rounded down to whole cells
    assert webcam.preview_size(200, 20, 1280, 720) == (71, 38)


def test_preview_size_fits_the_width():
    # 60 cells wide leaves 60 x 33 pixels, rounded down to whole cells
    assert webcam.preview_size(60, 50, 1280, 720) == (60, 32)


def test_preview_size_is_capped_so_redraws_stay_fast():
    width, _ = webcam.preview_size(500, 200, 1280, 720)
    assert width == webcam.MAX_PREVIEW_WIDTH


def test_preview_size_survives_a_tiny_terminal():
    width, height = webcam.preview_size(0, 0, 1280, 720)
    assert width >= 1 and height >= 2 and height % 2 == 0


RED, GREEN, BLUE, WHITE = (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)


def picture(*rows):
    return bytes(channel for row in rows for pixel in row for channel in pixel)


def test_render_puts_two_pixels_in_each_cell_mirrored():
    # 2 x 2 pixels: one line of two cells, the right-hand column drawn first
    lines = webcam.render(picture([RED, GREEN], [BLUE, WHITE]), 2, 2)
    assert lines == [
        "\x1b[38;2;0;255;0;48;2;255;255;255m▀"  # top GREEN, bottom WHITE
        "\x1b[38;2;255;0;0;48;2;0;0;255m▀"  # top RED, bottom BLUE
        + webcam.RESET
    ]


def test_render_in_grey_without_24_bit_colour():
    lines = webcam.render(picture([WHITE], [(0, 0, 0)]), 1, 2, truecolor=False)
    assert lines == ["\x1b[38;5;255;48;5;232m▀" + webcam.RESET]  # white over black


def test_render_has_a_line_for_each_pair_of_pixel_rows():
    assert len(webcam.render(picture(*[[RED] * 3] * 6), 3, 6)) == 3


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
