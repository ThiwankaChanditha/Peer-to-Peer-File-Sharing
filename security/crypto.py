import os
import base64
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

def generate_key_pair():
    """Generates a new RSA private/public key pair."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()
    return private_key, public_key

def serialize_private_key(private_key):
    """Serialize private key to PEM format."""
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

def serialize_public_key(public_key) -> str:
    """Serialize public key to OpenSSH/PEM format string."""
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return pem.decode('utf-8')

def deserialize_private_key(pem_bytes: bytes):
    """Deserialize private key from PEM bytes."""
    return serialization.load_pem_private_key(
        pem_bytes,
        password=None,
    )

def deserialize_public_key(pem_string: str):
    """Deserialize public key from string representation."""
    return serialization.load_pem_public_key(
        pem_string.encode('utf-8')
    )

def load_or_generate_keys(storage_path: Path):
    """Loads existing keypair from storage, or generates and saves a new one."""
    private_key_path = storage_path / "private_key.pem"
    public_key_path = storage_path / "public_key.pem"
    
    # Needs to ensure directory exists
    storage_path.mkdir(parents=True, exist_ok=True)

    if private_key_path.exists() and public_key_path.exists():
        with open(private_key_path, "rb") as f:
            private_key = deserialize_private_key(f.read())
        with open(public_key_path, "r") as f:
            public_key = deserialize_public_key(f.read())
        return private_key, public_key
    
    # Generate new
    private_key, public_key = generate_key_pair()
    
    with open(private_key_path, "wb") as f:
        f.write(serialize_private_key(private_key))
        
    with open(public_key_path, "w") as f:
        f.write(serialize_public_key(public_key))
        
    return private_key, public_key

def sign_data(private_key, data: bytes) -> str:
    """Signs bytes data and returns a base64 encoded signature string."""
    signature = private_key.sign(
        data,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')

def verify_signature(public_key_str: str, data: bytes, signature_b64: str) -> bool:
    """Verifies a base64 signature against data using the provided public key string.
    Returns True if valid, False otherwise.
    """
    try:
        public_key = deserialize_public_key(public_key_str)
        signature = base64.b64decode(signature_b64)
        
        public_key.verify(
            signature,
            data,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return True
    except (InvalidSignature, ValueError) as e:
        # InvalidSignature from cryptography
        # ValueError from base64 decode if corrupted
        print(f"Signature verification failed: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error during verification: {e}")
        return False
