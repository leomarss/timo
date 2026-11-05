import base64
import os
import sys
from urllib.parse import unquote, urlsplit

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

import migration_pb2  # import after sys.path.insert otherwise it will not find the module


def parse_migration_uri(uri):
    """Decode an otpauth-migration:// URI from Google Authenticator.

    Returns (accounts, batch_index, batch_size). Large exports are split
    across several QR codes; batch_index is 0-based.
    """
    parts = urlsplit(uri.strip())
    if parts.scheme != "otpauth-migration":
        raise ValueError("Not an otpauth-migration:// URI.")

    data_b64 = None
    for param in parts.query.split("&"):
        if param.startswith("data="):
            # unquote (not unquote_plus): '+' is a valid base64 character
            data_b64 = unquote(param[len("data="):])
            break
    if not data_b64:
        raise ValueError("Migration URI has no data parameter.")

    data_b64 += "=" * (-len(data_b64) % 4)
    try:
        # Google uses standard base64; accept the URL-safe alphabet too
        data_bytes = base64.b64decode(data_b64.replace("-", "+").replace("_", "/"), validate=True)
        payload = migration_pb2.MigrationPayload()
        payload.ParseFromString(data_bytes)
    except Exception as e:
        raise ValueError(f"Could not decode migration data: {e}") from e

    accounts = []
    for param in payload.otp_parameters:
        accounts.append({
            "issuer": param.issuer or "unknown",
            "name": param.name,
            "secret": base64.b32encode(param.secret).decode("utf-8").replace("=", ""),
        })

    return accounts, payload.batch_index, max(payload.batch_size, 1)
