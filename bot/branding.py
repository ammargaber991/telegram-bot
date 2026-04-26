BRAND_NAME = "Design Lab"
BRAND_TAGLINE = "Build clean systems. Ship fast. Stay secure."


def header(title: str) -> str:
    return f"🎨 *{BRAND_NAME}* — {title}"


def footer() -> str:
    return f"_{BRAND_TAGLINE}_"
