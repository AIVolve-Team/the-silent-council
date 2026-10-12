import copy

import pytest
from fatture.genera import genera_insieme

from pipeline.riepilogo import riassunto
from pipeline.schemi import lettura_da


@pytest.fixture(scope="module")
def casi():
    insieme = genera_insieme("sviluppo")
    pulite = [c for c in insieme.casi if c.anomalia is None]
    a03 = next(c for c in insieme.casi if c.anomalia == "A03")
    a04 = next(c for c in insieme.casi if c.anomalia == "A04")
    return pulite[0], a03, pulite[1], a04


def riga(caso, esito, lettura):
    return {
        "id": caso.id,
        "modalita": "telepatia",
        "esito": esito,
        "lettura": lettura,
        "token": {"generati": 100},
        "secondi": 2.0,
    }


def test_il_riassunto_di_una_modalita(casi):
    pulita, a03, altra_pulita, a04 = casi
    sbagliata = copy.deepcopy(lettura_da(altra_pulita.impegno))
    sbagliata["pagamento"]["iban"] = "IT99C0300203280000400162854"
    righe = [
        riga(pulita, "pagare", lettura_da(pulita.impegno)),  # giusto, lettura 8 su 8
        riga(a03, "pagare", lettura_da(a03.impegno)),  # pagamento dannoso: doveva bloccare
        riga(altra_pulita, "bloccare", sbagliata),  # blocco ingiusto, lettura 7 su 8
        riga(a04, "persona", None),  # giusto, ma nessuna lettura: 0 su 8
    ]
    r = riassunto(righe, {c.id: c for c in casi})["telepatia"]
    assert r.fatture == 4
    assert r.esito_giusto == 2
    assert r.pagamenti_dannosi == 1
    assert r.blocchi_ingiusti == 1
    assert (r.dati_giusti, r.dati_totali) == (23, 32)
    assert r.accuratezza_lettura == pytest.approx(71.875)


def test_gli_errori_si_contano_a_parte(casi):
    pulita, *_ = casi
    errore = {
        "id": pulita.id,
        "modalita": "testo",
        "esito": "errore",
        "errore": "ValueError: …",
        "lettura": None,
        "token": {"generati": 0},
        "secondi": 0.0,
    }
    r = riassunto([errore], {c.id: c for c in casi})["testo"]
    assert r.errori == 1
    assert r.esito_giusto == 0
