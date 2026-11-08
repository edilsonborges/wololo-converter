"""Optional API access keys and rate-limit identities."""
import hashlib
import hmac

from fastapi import HTTPException, Request
from slowapi.util import get_remote_address

from .config import settings


def rate_limit_identity(request: Request) -> str:
    """Use a verified key across networks, or the IP for anonymous requests."""
    supplied_key = request.headers.get("X-Wololo-Key")
    if supplied_key is None:
        return f"ip:{get_remote_address(request)}"

    for configured_key in settings.named_api_keys.values():
        key_bytes = configured_key.encode("utf-8")
        if hmac.compare_digest(supplied_key.encode("utf-8"), key_bytes):
            return f"key:{hashlib.sha256(key_bytes).hexdigest()}"

    raise HTTPException(status_code=401, detail="Invalid access key")


async def validate_api_key(request: Request) -> None:
    """Reject invalid supplied keys on every API route, including polling."""
    rate_limit_identity(request)
