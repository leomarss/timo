import json
import time
import os

from utils.utils import generate_otp

script_dir = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(script_dir, "../json/secrets.json")

with open(json_path, "r") as f:
    accounts = json.load(f)

def show_otp():
    os.system("clear")
    print("=== otp list ===\n")
    remaining_seconds = 30 - (int(time.time()) % 30)
    for acc in accounts:
        issuer = acc.get("issuer", "unknown")
        name = acc.get("name", "")
        code, remaining_seconds = generate_otp(acc)
        print(f"{code} - {issuer} ({name})")
    print(f"\nnew codes in {remaining_seconds:2d} seconds...")

try:
    while True:
        show_otp()
        time.sleep(1)
except KeyboardInterrupt:
    print("\nexit")
    os.system("clear")
