"""Small demo authentication layer. Replace demo accounts with campus SSO in production."""
from __future__ import annotations
import hashlib, hmac, os
from dataclasses import dataclass

_DEMO = {"asha": ("STU1001", "student"), "kabir": ("STU1002", "student"),
         "mira": ("STU1003", "student"), "approver": (None, "approver")}
_PASSWORDS = {"asha": "Asha-Demo-2026!", "kabir": "Kabir-Demo-2026!",
              "mira": "Mira-Demo-2026!", "approver": "Approve-Demo-2026!"}
_SALT = b"student-support-assignment-demo"
_HASHES = {u: hashlib.pbkdf2_hmac("sha256", p.encode(), _SALT, 200_000) for u,p in _PASSWORDS.items()}

@dataclass(frozen=True)
class Principal:
    username: str
    role: str
    student_id: str | None

def authenticate(username: str, password: str) -> Principal | None:
    username = username.strip().lower()
    record = _DEMO.get(username)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), _SALT, 200_000)
    if not record or not hmac.compare_digest(candidate, _HASHES[username]):
        return None
    return Principal(username, record[1], record[0])
