from typing import Literal


LanguageCode = Literal["zh", "en"]


def detect_focus_language(focus: str) -> LanguageCode:
    """Detect output language from focus text."""
    if any("\u4e00" <= ch <= "\u9fff" for ch in (focus or "")):
        return "zh"
    return "en"
