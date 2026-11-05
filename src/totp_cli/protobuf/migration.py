import base64
from urllib.parse import unquote, urlsplit

from totp_cli.protobuf import migration_pb2


ALGORITHMS = {
    migration_pb2.ALGORITHM_SHA1: "SHA1",
    migration_pb2.ALGORITHM_SHA256: "SHA256",
    migration_pb2.ALGORITHM_SHA512: "SHA512",
    migration_pb2.ALGORITHM_MD5: "MD5",
}

DIGITS = {
    migration_pb2.DIGIT_COUNT_SIX: 6,
    migration_pb2.DIGIT_COUNT_EIGHT: 8,
}


def parse_migration_uri(uri):
    """Decode an otpauth-migration:// URI from Google Authenticator.

    Returns (accounts, skipped, batch_index, batch_size). Large exports are
    split across several QR codes; batch_index is 0-based. HOTP accounts are
    not supported and are listed in skipped as "issuer (name)" labels.
    """
    parts = urlsplit(uri.strip())
    if parts.scheme != "otpauth-migration":
        raise ValueError("Not an otpauth-migration:// URI")

    data_b64 = None
    for param in parts.query.split("&"):
        if param.startswith("data="):
            # unquote (not unquote_plus): '+' is a valid base64 character
            data_b64 = unquote(param[len("data="):])
            break
    if not data_b64:
        raise ValueError("Migration URI has no data parameter")

    data_b64 += "=" * (-len(data_b64) % 4)
    try:
        # Google uses standard base64; accept the URL-safe alphabet too
        data_bytes = base64.b64decode(data_b64.replace("-", "+").replace("_", "/"), validate=True)
        payload = migration_pb2.MigrationPayload()
        payload.ParseFromString(data_bytes)
    except Exception as e:
        raise ValueError(f"Could not decode migration data: {e}") from e

    accounts = []
    skipped = []
    for param in payload.otp_parameters:
        issuer = param.issuer or "unknown"
        if param.type == migration_pb2.OTP_TYPE_HOTP:
            skipped.append(f"{issuer} ({param.name})")
            continue
        accounts.append({
            "issuer": issuer,
            "name": param.name,
            "secret": base64.b32encode(param.secret).decode("utf-8").replace("=", ""),
            "algorithm": ALGORITHMS.get(param.algorithm, "SHA1"),
            "digits": DIGITS.get(param.digits, 6),
        })

    return accounts, skipped, payload.batch_index, max(payload.batch_size, 1)
