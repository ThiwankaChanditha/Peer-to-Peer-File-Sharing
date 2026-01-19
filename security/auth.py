import uuid

APPROVED_TOKENS = set()

def generate_token():
    token = str(uuid.uuid4())
    APPROVED_TOKENS.add(token)
    return token

def validate_token(token: str) -> bool:
    return token in APPROVED_TOKENS
