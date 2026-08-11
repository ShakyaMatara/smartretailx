from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Argon2id is the current OWASP-recommended password hashing algorithm.
# It is deliberately slow and memory-hard, which makes large-scale
# offline brute-force attacks expensive even if the database leaks.
# A salt is generated per password automatically and stored inside
# the hash string, so identical passwords produce different hashes.
_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, stored_hash: str) -> bool:
    try:
        _hasher.verify(stored_hash, plain_password)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False