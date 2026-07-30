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


def test_country_names_are_translated_in_youth_teams() -> None:
    assert localize_name("Greece U18") == "Греция U18"
    assert localize_name("Spain U18") == "Испания U18"
    assert localize_name("Turkey U18") == "Турция U18"
    assert localize_name("Czech Republic U18") == "Чехия U18"
    assert localize_name("Bosnia & Herzegovina U18") == "Босния и Герцеговина U18"
    assert localize_name("Minnesota Lynx W") == "Миннесота Линкс Ж"


def test_current_basketball_leagues_have_readable_names() -> None:
    assert localize_name("EuroBasket U18") == "Евробаскет U18"
    assert localize_name("EuroBasket U18 B") == "Евробаскет U18, дивизион B"
    assert localize_name("NBA W") == "Женская НБА"
