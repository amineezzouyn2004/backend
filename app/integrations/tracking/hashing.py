import hashlib
import re


SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def _reject_hash(value: str) -> None:
    if SHA256_RE.fullmatch(value):
        raise ValueError("already_hashed")


def _sha256_once(value: str) -> str:
    if SHA256_RE.fullmatch(value):
        raise ValueError("already_hashed")
    return hashlib.sha256(value.encode()).hexdigest()


def normalize_meta_phone(phone_e164: str) -> str:
    return "".join(char for char in phone_e164 if char.isdigit())


def hash_meta_phone(phone_e164: str) -> str:
    _reject_hash(phone_e164)
    return _sha256_once(normalize_meta_phone(phone_e164))


def normalize_tiktok_phone(phone_e164: str) -> str:
    # Kept separate intentionally; current account payload must be reverified before enable.
    return phone_e164.strip()


def hash_tiktok_phone(phone_e164: str) -> str:
    _reject_hash(phone_e164)
    return _sha256_once(normalize_tiktok_phone(phone_e164))


def normalize_snap_phone(phone_e164: str) -> str:
    return "".join(char for char in phone_e164 if char.isdigit())


def hash_snap_phone(phone_e164: str) -> str:
    _reject_hash(phone_e164)
    return _sha256_once(normalize_snap_phone(phone_e164))
