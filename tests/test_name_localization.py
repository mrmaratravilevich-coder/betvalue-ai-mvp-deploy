from app.services.name_localization import localize_name


def test_known_football_names_are_localized() -> None:
    assert localize_name("Liverpool FC") == "Ливерпуль"
    assert localize_name("Deportivo Alavés") == "Депортиво Алавес"
    assert localize_name("Premier League") == "Премьер-лига"
    assert localize_name("Club Friendly") == "Клубный товарищеский матч"


def test_current_hockey_names_are_localized() -> None:
    assert localize_name("Baranavichy") == "Барановичи"
    assert localize_name("Dinamo-Shinnik") == "Динамо-Шинник"
    assert localize_name("USA U20") == "США U20"


def test_unknown_latin_name_uses_cyrillic_fallback() -> None:
    localized = localize_name("North Stars")
    assert localized == "Норт Старс"
    assert not any("a" <= char.lower() <= "z" for char in localized)
