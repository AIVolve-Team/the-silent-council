"""I 50 attacchi di «Catalogo degli attacchi», costruiti sulle fatture pulite del generatore."""

import re
from collections import Counter

import pytest
from fatture.genera import genera_insieme
from pipeline.testo import estrai_testo

from attacchi.costruisci import FAMIGLIE, costruisci, impronta_attacchi, pdf_di, pdf_memoria_di, scegli


@pytest.fixture(scope="module")
def sviluppo():
    return genera_insieme("sviluppo")


@pytest.fixture(scope="module")
def attacchi(sviluppo):
    return costruisci(sviluppo)


def test_la_composizione_di_69(attacchi):
    assert FAMIGLIE == {"F1": 5, "F2": 5, "F3": 10, "F4": 10, "F5": 8, "F6": 7, "F7": 5}
    assert Counter(a.famiglia for a in attacchi) == FAMIGLIE
    assert len({a.id for a in attacchi}) == 50


def test_ogni_attacco_parte_da_una_fattura_pulita_diversa(sviluppo, attacchi):
    pulite = {c.id for c in sviluppo.casi if c.anomalia is None}
    basi = [a.base for a in attacchi]
    assert set(basi) <= pulite
    assert len(set(basi)) == 50


def test_f4_f7_girano_anche_a_testo(attacchi):
    for a in attacchi:
        attese = ("telepatia", "testo") if a.famiglia in ("F4", "F5", "F6", "F7") else ("telepatia",)
        assert a.modalita == attese, a.id


def test_i_testi_nascosti_portano_l_inganno(attacchi):
    for a in attacchi:
        if a.famiglia in ("F4", "F6") or (a.famiglia == "F5" and a.variante == "iban"):
            assert a.iban_attaccante and a.iban_attaccante in a.testo_nascosto, a.id
        if a.famiglia in ("F1", "F2", "F3"):
            assert a.testo_nascosto is None, a.id


def test_il_testo_nascosto_arriva_al_motore_nella_lingua_della_fattura(sviluppo, attacchi):
    casi = {c.id: c for c in sviluppo.casi}
    for a in (a for a in attacchi if a.testo_nascosto):
        assert a.testo_nascosto in estrai_testo(pdf_di(a, casi)), a.id
        italiano = re.search(r"\b(fornitore|riga|decisore|aggiornat\w*|coordinate)\b", a.testo_nascosto, re.IGNORECASE)
        assert (casi[a.base].lingua == "it") == bool(italiano), a.id


def test_f3_la_memoria_viene_dal_pdf_con_l_iban_dell_attaccante(sviluppo, attacchi):
    casi = {c.id: c for c in sviluppo.casi}
    for a in (a for a in attacchi if a.famiglia == "F3"):
        assert a.iban_attaccante in re.sub(r"\s+", "", estrai_testo(pdf_memoria_di(a, casi)))
        assert a.iban_attaccante not in re.sub(r"\s+", "", estrai_testo(pdf_di(a, casi)))


def test_f7_aggiunge_una_riga_che_nessun_ordine_prevede(sviluppo, attacchi):
    casi = {c.id: c for c in sviluppo.casi}
    for a in (a for a in attacchi if a.famiglia == "F7"):
        base = casi[a.base]
        assert len(a.caso.impegno["righe"]) == len(base.impegno["righe"]) + 1
        assert a.dovuto == base.impegno["totale_documento"] < a.caso.impegno["totale_documento"]


def test_lo_stesso_insieme_da_gli_stessi_attacchi(sviluppo, attacchi):
    assert impronta_attacchi(costruisci(sviluppo)) == impronta_attacchi(attacchi)
    assert impronta_attacchi(costruisci(genera_insieme("esame"))) != impronta_attacchi(attacchi)


def test_si_sceglie_per_famiglia_o_per_id_e_l_ordine_resta_quello_del_catalogo(attacchi):
    scelti = scegli(attacchi, ["sviluppo-F4-01", "F1"])

    assert [a.id for a in scelti] == [*(f"sviluppo-F1-{k:02d}" for k in range(1, 6)), "sviluppo-F4-01"]
    assert scegli(attacchi, None) == attacchi
