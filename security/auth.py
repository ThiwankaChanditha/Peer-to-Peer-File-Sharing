import secrets
import time
from typing import Dict

_token_store: Dict[str, tuple] = {}
TOKEN_TTL_SECONDS = 3600 


def issue_token(peer_id: str) -> str:
    """Called by the TRACKER only when a peer joins."""
    token = secrets.token_urlsafe(32)
    _token_store[peer_id] = (token, time.time())
    return token


def validate_token(peer_id: str, token: str) -> bool:
    """Returns True only if the token matches and hasn't expired."""
    entry = _token_store.get(peer_id)
    if not entry:
        return False
    stored_token, issued_at = entry
    if time.time() - issued_at > TOKEN_TTL_SECONDS:
        del _token_store[peer_id]
        return False
    return secrets.compare_digest(stored_token, token)


def revoke_token(peer_id: str):
    _token_store.pop(peer_id, None)