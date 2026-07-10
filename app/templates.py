from datetime import datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def datetimeformat(value: datetime | None, fmt: str = "%Y-%m-%d %H:%M UTC") -> str:
    if value is None:
        return ""
    return value.strftime(fmt)


templates.env.filters["datetimeformat"] = datetimeformat
