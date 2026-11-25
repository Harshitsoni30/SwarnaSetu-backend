from html import escape
from pathlib import Path


def render_welcome(name: str | None) -> str:
    """Fill the welcome email template. The layout lives in welcome.html."""

    who = escape(name.strip()) if name and name.strip() else "there"
    template = Path(__file__).with_name("welcome.html").read_text(encoding="utf-8")
    return template.replace("{{name}}", who)
