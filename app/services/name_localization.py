"""Russian display names for provider-owned sports entities."""

from __future__ import annotations

import re
import unicodedata

_KNOWN_NAMES = {
    # Competitions
    "premier league": "Премьер-лига",
    "primera division": "Ла Лига",
    "la liga": "Ла Лига",
    "bundesliga": "Бундеслига",
    "serie a": "Серия А",
    "ligue 1": "Лига 1",
    "khl": "КХЛ",
    "nhl": "НХЛ",
    "world championship": "Чемпионат мира",
    "club friendly": "Клубный товарищеский матч",
    "club friendlies": "Клубные товарищеские матчи",
    "friendly games": "Товарищеские матчи",
    "friendly international": "Международный товарищеский матч",
    # Current hockey schedule
    "lida": "Лида",
    "baranavichy": "Барановичи",
    "brest": "Брест",
    "vladivostok": "Владивосток",
    "dinamo-shinnik": "Динамо-Шинник",
    "tayfun": "Тайфун",
    "jihlava u20": "Йиглава U20",
    "kolin u20": "Колин U20",
    "usa u20": "США U20",
    "finland u20": "Финляндия U20",
    "canada u20": "Канада U20",
    "sweden u20": "Швеция U20",
    # Football teams commonly returned by the enabled competitions
    "arsenal fc": "Арсенал",
    "arsenal": "Арсенал",
    "liverpool fc": "Ливерпуль",
    "liverpool": "Ливерпуль",
    "manchester city fc": "Манчестер Сити",
    "manchester united fc": "Манчестер Юнайтед",
    "chelsea fc": "Челси",
    "tottenham hotspur fc": "Тоттенхэм",
    "newcastle united fc": "Ньюкасл Юнайтед",
    "fc barcelona": "Барселона",
    "real madrid cf": "Реал Мадрид",
    "club atlético de madrid": "Атлетико Мадрид",
    "deportivo alavés": "Депортиво Алавес",
    "getafe cf": "Хетафе",
    "sevilla fc": "Севилья",
    "rayo vallecano de madrid": "Райо Вальекано",
    "fc bayern münchen": "Бавария",
    "borussia dortmund": "Боруссия Дортмунд",
    "bayer 04 leverkusen": "Байер 04",
    "fc internazionale milano": "Интер",
    "ac milan": "Милан",
    "juventus fc": "Ювентус",
    "paris saint-germain fc": "Пари Сен-Жермен",
    "olympique de marseille": "Олимпик Марсель",
}

_SEQUENCES = (
    ("shch", "щ"),
    ("sch", "щ"),
    ("zh", "ж"),
    ("kh", "х"),
    ("ts", "ц"),
    ("ch", "ч"),
    ("sh", "ш"),
    ("yu", "ю"),
    ("ya", "я"),
    ("yo", "ё"),
    ("ye", "е"),
    ("ph", "ф"),
    ("th", "т"),
    ("ck", "к"),
    ("qu", "кв"),
)

_LETTERS = {
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф",
    "g": "г", "h": "х", "i": "и", "j": "дж", "k": "к", "l": "л",
    "m": "м", "n": "н", "o": "о", "p": "п", "q": "к", "r": "р",
    "s": "с", "t": "т", "u": "у", "v": "в", "w": "в", "x": "кс",
    "y": "й", "z": "з",
}


def _strip_diacritics(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def _transliterate_word(word: str) -> str:
    if not re.search(r"[A-Za-z]", word):
        return word
    if word.upper() in {"FC", "CF"}:
        return "ФК"

    normalized = _strip_diacritics(word)
    result: list[str] = []
    index = 0
    while index < len(normalized):
        matched = False
        for latin, cyrillic in _SEQUENCES:
            chunk = normalized[index:index + len(latin)]
            if chunk.lower() == latin:
                result.append(cyrillic.upper() if chunk[0].isupper() else cyrillic)
                index += len(latin)
                matched = True
                break
        if matched:
            continue

        char = normalized[index]
        replacement = _LETTERS.get(char.lower(), char)
        result.append(replacement.upper() if char.isupper() else replacement)
        index += 1
    return "".join(result)


def localize_name(value: str) -> str:
    """Return a Russian display label while retaining unknown punctuation."""
    cleaned = " ".join(value.split())
    known = _KNOWN_NAMES.get(cleaned.casefold())
    if known:
        return known
    return re.sub(r"[A-Za-zÀ-ž0-9]+", lambda match: _transliterate_word(match.group()), cleaned)
