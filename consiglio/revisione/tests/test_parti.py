"""Test senza modello: schemi, confidenza, citazioni, dissenso e voto."""

import math

import pytest
from motore import Generazione, Passo

from revisione import BENCHMARK
from revisione.citazioni import trovata, verifica
from revisione.confidenza import livello, probabilita_si
from revisione.consiglio import Scritto, dissensi
from revisione.punteggio import vota
from revisione.schemi import schema_nota, schema_verdetto

CUAD = BENCHMARK["cuad"]
VERO, FALSO = 1, 2


def passo(testo, p_vero=None):
    osservati = {} if p_vero is None else {VERO: math.log(p_vero), FALSO: math.log(1 - p_vero)}
    return Passo(0, testo, 0.0, [], osservati)


def test_schemi_limitati_e_con_tutte_le_categorie():
    nota = schema_nota(CUAD.del_ruolo("finanza"))
    assert nota["properties"]["segnalare"]["required"] == [c.chiave for c in CUAD.del_ruolo("finanza")]
    assert nota["properties"]["citazioni"]["maxItems"] == 3
    verdetto = schema_verdetto(CUAD.categorie)
    assert len(verdetto["properties"]["segnalare"]["required"]) == 19
    assert verdetto["required"][0] == "obiezioni" and verdetto["required"][-2] == "raccomandazione"


def test_categorie_dei_benchmark():
    assert [len(CUAD.del_ruolo(r)) for r in CUAD.lettori] == [7, 4, 8]
    assert BENCHMARK["contractnli"].lettori == ("legale", "rischio") and len(BENCHMARK["contractnli"].categorie) == 17
    assert len(BENCHMARK["claudette"].categorie) == 9
    assert BENCHMARK["dimostrativo"].categorie == CUAD.categorie


def test_confidenza_dai_booleani_dentro_segnalare():
    passi = [passo('{"segnalare": {"Exclusivity": '), passo("true", 0.8), passo(', "Non-Compete": ', 0.3)]
    passi += [passo(" false", 0.1), passo('}, "dettagli": [{"categoria": "Exclusivity", "x": '), passo("true", 0.99)]
    p = probabilita_si(Generazione("", passi, 0), [VERO], [FALSO])
    assert p == pytest.approx({"Exclusivity": 0.8, "Non-Compete": 0.1})
    assert livello(0.95, True) == "alta" and livello(0.2, False) == "media" and livello(0.6, True) == "bassa"


def test_citazioni_cercate_nel_contratto():
    contratto = "Il Cliente si impegna ad acquistare, in ciascun Anno Contrattuale, Componenti per € 180.000,00."
    assert trovata("si impegna ad acquistare, in ciascun Anno", contratto)
    assert trovata("«Il cliente si impegna» … per € 180.000,00", contratto)
    assert not trovata("se un terzo ottiene condizioni migliori", contratto)
    assert not trovata("Cliente", contratto)
    dati = {"dettagli": [{"categoria": "Minimum Commitment", "citazione": "per € 180.000,00 di componenti"}]}
    assert verifica(dati, contratto) == {"Minimum Commitment": False}


def scritto(segnalare, p=None):
    return Scritto({"segnalare": segnalare}, p or {}, {}, 0, 0, "")


def test_dissenso_grave_e_lieve():
    note = {"rischio": scritto({"Exclusivity": True, "Non-Compete": False}, {"Exclusivity": 0.95})}
    verdetto = scritto({"Exclusivity": False, "Non-Compete": True}, {"Exclusivity": 0.4})
    trovati = {d.categoria: d for d in dissensi(CUAD, note, verdetto)}
    assert trovati["Exclusivity"].tipo == "grave" and trovati["Exclusivity"].confidenza_esperto == "alta"
    assert trovati["Exclusivity"].confidenza_verdetto == "bassa"
    assert trovati["Non-Compete"].tipo == "lieve" and trovati["Non-Compete"].confidenza_esperto is None


def test_voto_con_base_sempre_si():
    revisioni = [
        {"contratto": "a", "verdetto": {"dati": {"segnalare": {"x": True, "y": False}}}},
        {"contratto": "b", "verdetto": None},
    ]
    giuste = {("a", "x"): True, ("a", "y"): True, ("b", "x"): False, ("b", "y"): True}
    voto = vota(revisioni, giuste)
    assert (voto.vp, voto.fp, voto.fn, voto.vn, voto.non_valide) == (1, 0, 2, 1, 2)
    assert round(voto.f1, 1) == 50.0 and round(voto.f1_sempre_si, 1) == round(100 * 2 * 3 / 7, 1)
