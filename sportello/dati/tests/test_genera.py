from collections import Counter

import pytest

from fatture.genera import ANOMALIE, genera_insieme
from fatture.regole import applica_regole, esito_finale


@pytest.fixture(scope="module")
def sviluppo():
    return genera_insieme("sviluppo")


def test_la_composizione_dello_sviluppo(sviluppo):
    # 100 fatture, 42 con un'anomalia (3 per variante) e 58 pulite, di cui 15 al limite.
    assert sviluppo.seme == 101
    assert len(sviluppo.casi) == 100
    assert Counter(c.anomalia for c in sviluppo.casi if c.anomalia) == {a: 3 for a in ANOMALIE}
    pulite = [c for c in sviluppo.casi if c.anomalia is None]
    assert len(pulite) == 58
    assert Counter(c.al_limite for c in pulite if c.al_limite) == {"prezzo": 5, "canone": 5, "numero": 5}
    assert Counter(c.lingua for c in sviluppo.casi) == {"it": 70, "en": 30}
    assert len({c.id for c in sviluppo.casi}) == 100


def test_l_esame_ha_la_composizione_di_47():
    esame = genera_insieme("esame")
    assert esame.seme == 102
    assert len(esame.casi) == 200
    assert Counter(c.anomalia for c in esame.casi if c.anomalia) == {a: 6 for a in ANOMALIE}
    assert sum(c.al_limite is not None for c in esame.casi) == 30
    assert Counter(c.lingua for c in esame.casi) == {"it": 140, "en": 60}


def test_lo_stesso_seme_da_le_stesse_fatture(sviluppo):
    di_nuovo = genera_insieme("sviluppo")
    assert [c.impegno for c in di_nuovo.casi] == [c.impegno for c in sviluppo.casi]
    assert di_nuovo.archivi == sviluppo.archivi


@pytest.mark.parametrize("nome", ["sviluppo", "esame"])
def test_le_regole_sulla_verita_danno_l_esito_atteso_e_solo_l_anomalia_inserita(nome):
    insieme = genera_insieme(nome)
    for caso in insieme.casi:
        scatti = applica_regole(caso.impegno, insieme.archivi, caso.abbinamenti)
        attesi = set() if caso.anomalia is None else {caso.anomalia}
        assert {s.codice for s in scatti} == attesi, caso.id
        assert esito_finale(scatti) == caso.esito_atteso, caso.id


def test_gli_esiti_attesi_sono_quelli_del_catalogo(sviluppo):
    attesi = {
        "A01": "bloccare",
        "A02": "persona",
        "A03": "bloccare",
        "A04": "persona",
        "A05": "bloccare",
        "A06": "bloccare",
        "A07": "persona",
        "A08": "bloccare",
        "A09a": "persona",
        "A09b": "bloccare",
        "A10": "bloccare",
        "A11": "persona",
        "A12": "persona",
        "A13": "bloccare",
    }
    for caso in sviluppo.casi:
        assert caso.esito_atteso == attesi.get(caso.anomalia, "pagare"), caso.id


def test_ci_sono_righe_da_abbinare_anche_nelle_fatture_pulite(sviluppo):
    # Senza, A11 si riconoscerebbe da num_item vuoto e il giudizio del modello non servirebbe.
    pulite_con_righe_libere = [c for c in sviluppo.casi if c.anomalia is None and c.abbinamenti]
    assert len(pulite_con_righe_libere) >= 10
