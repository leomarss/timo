import base64

import pytest

from utils.utils import generate_otp, make_totp

# RFC 6238 Appendix B test vectors (T = 59s), seeds per algorithm
SEEDS = {
    "SHA1": b"12345678901234567890",
    "SHA256": b"12345678901234567890123456789012",
    "SHA512": b"1234567890123456789012345678901234567890123456789012345678901234",
}
EXPECTED_8_DIGITS_AT_59 = {"SHA1": "94287082", "SHA256": "46119246", "SHA512": "90693936"}


def b32(raw):
    return base64.b32encode(raw).decode().replace("=", "")


@pytest.mark.parametrize("algorithm", ["SHA1", "SHA256", "SHA512"])
def test_rfc6238_vectors(algorithm):
    account = {"secret": b32(SEEDS[algorithm]), "algorithm": algorithm, "digits": 8}
    assert make_totp(account).at(59) == EXPECTED_8_DIGITS_AT_59[algorithm]


def test_defaults_to_sha1_six_digits_for_old_files():
    account = {"secret": b32(SEEDS["SHA1"])}
    assert make_totp(account).at(59) == "287082"


def test_algorithm_is_case_insensitive():
    account = {"secret": b32(SEEDS["SHA256"]), "algorithm": "sha256", "digits": 8}
    assert make_totp(account).at(59) == "46119246"


def test_rejects_unknown_algorithm():
    with pytest.raises(ValueError):
        make_totp({"secret": b32(SEEDS["SHA1"]), "algorithm": "SHA3"})


def test_rejects_unsupported_digits():
    with pytest.raises(ValueError):
        make_totp({"secret": b32(SEEDS["SHA1"]), "digits": 7})


def test_generate_otp_uses_account_settings():
    code, remaining = generate_otp({"secret": b32(SEEDS["SHA512"]), "algorithm": "SHA512", "digits": 8})
    assert len(code) == 8
    assert 1 <= remaining <= 30
