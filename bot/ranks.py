from __future__ import annotations

from enum import IntEnum


class Rank(IntEnum):
    USER = 10
    MODERATOR = 20
    ADMIN = 30
    DEVELOPER = 40
    OWNER = 50

    @classmethod
    def parse(cls, raw: str) -> "Rank":
        key = raw.strip().upper()
        try:
            return cls[key]
        except KeyError as exc:
            valid = ", ".join(rank.name.lower() for rank in cls)
            raise ValueError(f"Invalid rank '{raw}'. Valid ranks: {valid}") from exc

    def label(self) -> str:
        return self.name.lower()
