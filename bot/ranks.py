from __future__ import annotations

from enum import IntEnum


class Rank(IntEnum):
    MEMBER = 10
    TRUSTED = 20
    VIP = 30
    MODERATOR = 40
    ADMIN = 50
    SUPERADMIN = 60
    OWNER = 70

    @classmethod
    def parse(cls, raw: str) -> "Rank":
        key = raw.strip().upper().replace(" ", "").replace("_", "")
        aliases = {
            "USER": "MEMBER",
            "COOWNER": "SUPERADMIN",
            "MANAGER": "SUPERADMIN",
            "HELPER": "TRUSTED",
        }
        normalized = aliases.get(key, key)
        for rank in cls:
            if rank.name.replace("_", "") == normalized:
                return rank
        valid = ", ".join(rank.name.lower() for rank in cls)
        raise ValueError(f"Invalid rank '{raw}'. Valid ranks: {valid}")

    def label(self) -> str:
        return self.name.lower()
