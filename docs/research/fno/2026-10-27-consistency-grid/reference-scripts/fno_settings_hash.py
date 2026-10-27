"""Per-key sha256 of every effective FNO_* setting (names + hashes only, never values)."""
import hashlib, json
from config import settings
data = settings.model_dump()
print(json.dumps({k: hashlib.sha256(repr(v).encode()).hexdigest()[:16] for k, v in sorted(data.items())
                  if k.startswith("FNO_")}))
