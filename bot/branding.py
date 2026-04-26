from __future__ import annotations

BRAND_NAME = "Design Lab Elite"
BRAND_TAGLINE = "Premium Management • إدارة احترافية"


HELP_CATEGORIES = {
    "admin": "📌 الإدارة",
    "members": "📌 الأعضاء",
    "guard": "📌 الحماية",
    "stats": "📌 الإحصائيات",
    "dev": "📌 المطور",
    "tools": "📌 الأدوات",
}


def header(title: str) -> str:
    return f"✨ {BRAND_NAME} — {title}"


def footer() -> str:
    return f"{BRAND_TAGLINE}"


def premium_panel(title: str, lines: list[str]) -> str:
    return "\n".join(["━━━━━━━━━━━━━━━━━━", title, *lines, "━━━━━━━━━━━━━━━━━━"])
