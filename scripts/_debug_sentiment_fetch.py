"""Debug: why didn't the sentiment block populate the cache in manual_scan?"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto_predictor.config import load_secrets

project_root = Path(__file__).resolve().parent.parent

secrets_path = project_root / "data" / "secrets.env"
print(f"secrets path: {secrets_path}")
print(f"exists: {secrets_path.exists()}")

secrets = load_secrets(secrets_path)
print(f"loaded keys: {sorted(secrets.keys())}")
print(f"NEWSAPI_API_KEY len: {len(secrets.get('NEWSAPI_API_KEY', ''))}")
print(f"NEWSAPI_API_KEY[:10]: {secrets.get('NEWSAPI_API_KEY', '')[:10]}...")
