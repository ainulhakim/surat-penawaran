import base64
import binascii
import uuid
from datetime import datetime
from pathlib import Path

from app.core.config import settings

ALLOWED_IMAGE_PREFIX = "data:image/"


def _decode(image_base64: str) -> bytes | None:
    raw = image_base64.strip()
    if not raw:
        return None
    if raw.startswith(ALLOWED_IMAGE_PREFIX):
        raw = raw.split(",", 1)[-1]
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        return None
    if not data or len(data) > 5 * 1024 * 1024:
        return None
    return data


def save_base64_image(image_base64: str, subdir: str, prefix: str = "img") -> str | None:
    data = _decode(image_base64)
    if data is None:
        return None
    target_dir = Path(settings.UPLOAD_DIR) / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"{prefix}_{stamp}_{uuid.uuid4().hex[:6]}.png"
    path = target_dir / filename
    path.write_bytes(data)
    return str(path)
