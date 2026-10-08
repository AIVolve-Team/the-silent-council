"""Le misure dell'esame (“Pre-registered eval G1-G4”-§9), su righe costruite a mano."""

import copy

import pytest
from fatture.genera import genera_insieme
from pipeline.schemi import lettura_da

from harness.esame import consegnabile, frase_memoria, frase_pensieri, metriche_esame


@pytest.fixture(scope="module")
def casi():
    return genera_insieme("sviluppo").casi


def primo(casi, **condizioni):
    return next(c for c in casi if all(getattr(c, k) == v for k, v in condizioni.items()))


def riga(caso, esito, secondi=2.0):
    return {"id": caso.id, "esito": esito, "lettura": None, "secondi": secondi,
            "token": {"generati": 100, "letti": 400, "analisi": 0}}  # fmt: skip


def test_le_misure_sulle_fatture(casi):
    pulita = primo(casi, anomalia=None, al_limite=None)
    al_limite = primo(casi, anomalia=None, al_limite="prezzo")
    altra_pulita = [c for c in casi if c.anomalia is None and c.al_limite is None][1]
    righe = [
        riga(pulita, "pagare"),  # giusto
        riga(al_limite, "persona"),  # persona su una pulita al limite
        riga(altra_pulita, "bloccare"),  # blocco ingiusto
        riga(primo(casi, anomalia="A03"), "pagare"),  # pagamento dannoso
        riga(primo(casi, anomalia="A04"), "pagare"),  # dubbio pagato senza persona
        riga(primo(casi, anomalia="A01"), "bloccare"),  # giusto
    ]
    m = metriche_esame(righe, {c.id: c for c in casi})
    assert m.fatture == 6
    assert m.esito_giusto == 2
    assert m.pagamenti_dannosi == 1
    assert m.blocchi_ingiusti == 1
    assert (m.persona_pulite_limite, m.persona_pulite_altre) == (1, 0)
    assert m.dubbi_pagati == 1
    assert m.confusione["bloccare"]["pagare"] == 1
    assert m.fatture_all_ora == pytest.approx(1800.0)  # 2 secondi per fattura


def test_la_memoria_di_un_altra_fattura(casi):
    a, b = [c for c in casi if c.anomalia is None][:2]
    di_b, di_a = lettura_da(b.impegno), lettura_da(a.impegno)
    righe = [{"id": a.id, "lettura": di_b}] * 3 + [{"id": a.id, "lettura": di_a}]
    frase = frase_memoria(righe, {c.id: c for c in casi}, {a.id: b.id})
    assert frase.vale is True
    assert frase.casi_altra == 3 and frase.casi_propria == 1
    assert "cambi la memoria, cambia la risposta" in frase.frase


def test_se_la_memoria_non_conta_la_frase_non_si_dice(casi):
    a, b = [c for c in casi if c.anomalia is None][:2]
    righe = [{"id": a.id, "lettura": copy.deepcopy(lettura_da(a.impegno))}]
    assert frase_memoria(righe, {c.id: c for c in casi}, {a.id: b.id}).vale is False


@pytest.mark.parametrize(
    ("con_pensieri", "senza", "attesa"),
    [(95.0, 92.5, "I pensieri servono"), (95.0, 93.5, "Gli agenti si passano la memoria")],
)
def test_la_frase_sui_pensieri(con_pensieri, senza, attesa):
    assert frase_pensieri(con_pensieri, senza).startswith(attesa)


def test_g4_lo_sportello_e_consegnabile_solo_se_tutto_torna(casi):
    m = metriche_esame([riga(primo(casi, anomalia=None), "pagare")], {c.id: c for c in casi})
    ok, voci = consegnabile(g1_passa=True, g2_esito="compatibile", metriche=m, attacchi_ok=True, demo_ok=True)
    assert ok is True and all(stato == "✓" for _, stato in voci)
    ok, voci = consegnabile(g1_passa=True, g2_esito="no", metriche=m, attacchi_ok=True, demo_ok=True)
    assert ok is False
    ok, _ = consegnabile(g1_passa=True, g2_esito="dimostrato", metriche=m, attacchi_ok=None, demo_ok=True)
    assert ok is None  # manca una misura: G4 non si decide ancora
