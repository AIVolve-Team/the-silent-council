import pytest

from g1.riepilogo import esito_g1, zona


def righe(corretti: list[bool], token: int) -> list[dict]:
    """Una riga per problema, con i token generati divisi in parti uguali."""
    return [
        {"id": f"p{i}", "corretto": c, "token_generati": token // len(corretti), "token_letti": 10, "secondi": 1.0}
        for i, c in enumerate(corretti)
    ]


@pytest.mark.parametrize(
    ("differenza", "attesa"),
    [(1.4, "dimostrato"), (-3.0, "dimostrato"), (-3.5, "si va avanti"), (-10.0, "si va avanti"), (-10.5, "stop")],
)
def test_le_tre_zone_della_precisione(differenza, attesa):
    assert zona(differenza) == attesa


def test_passa_con_memoria_token_e_precisione_a_posto():
    esito = esito_g1(
        testo=righe([True, True, True, False], token=1000),
        telepatia=righe([True, True, False, False], token=300),
        senza_pensieri=righe([True, False, False, False], token=280),
        memoria_ok=True,
    )
    assert esito.accuratezza == {"testo": 75.0, "telepatia": 50.0, "senza_pensieri": 25.0}
    assert esito.differenza == -25.0
    assert esito.zona == "stop"
    assert esito.riduzione_token == pytest.approx(0.7)
    assert esito.passa is False


def test_non_passa_se_i_token_calano_meno_della_meta():
    esito = esito_g1(
        testo=righe([True, True], token=100),
        telepatia=righe([True, True], token=60),
        senza_pensieri=righe([True, True], token=60),
        memoria_ok=True,
    )
    assert esito.zona == "dimostrato"
    assert esito.riduzione_token == pytest.approx(0.4)
    assert esito.passa is False


def test_passa_quando_tutto_torna():
    esito = esito_g1(
        testo=righe([True] * 10, token=2000),
        telepatia=righe([True] * 9 + [False], token=500),
        senza_pensieri=righe([True] * 8 + [False] * 2, token=480),
        memoria_ok=True,
    )
    assert esito.differenza == -10.0
    assert esito.zona == "si va avanti"
    assert esito.passa is True


def test_senza_la_misura_della_memoria_il_verdetto_resta_aperto():
    esito = esito_g1(
        testo=righe([True], token=100), telepatia=righe([True], token=10), senza_pensieri=righe([True], token=10)
    )
    assert esito.passa is None


def test_i_tre_giri_devono_avere_gli_stessi_problemi():
    with pytest.raises(ValueError, match="stessi problemi"):
        esito_g1(testo=righe([True, True], 10), telepatia=righe([True], 10), senza_pensieri=righe([True], 10))
