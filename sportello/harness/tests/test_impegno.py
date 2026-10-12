"""Senza soglia: l'accuratezza dell'impegno su tutti i campi e quella della proposta, su esempi fatti a mano."""

import copy

import pytest
from fatture.genera import genera_insieme

from harness.impegno import accuratezza_impegno, accuratezza_proposta, giusti_impegno


def completa(c) -> bool:
    """Due righe, ognuna con tutti i dati, e un ordine; il beneficiario, come quasi sempre, non è stampato."""
    i = c.impegno
    righe_piene = all(v is not None for r in i["righe"] for k, v in r.items() if k != "num_item")
    return len(i["righe"]) == 2 and righe_piene and i["ordine"]["numero"] and i["pagamento"]["beneficiario"] is None


@pytest.fixture(scope="module")
def caso():
    return next(c for c in genera_insieme("sviluppo").casi if completa(c))


def test_un_impegno_uguale_alla_verita_ha_tutti_i_dati_giusti(caso):
    giusti, totali = giusti_impegno(caso.impegno, copy.deepcopy(caso.impegno))
    # 14 dati di testa, 6 per riga (num_item no: il PDF non lo stampa), 3 per voce del riepilogo
    assert totali == 14 + 6 * 2 + 3 * len(caso.impegno["riepilogo"])
    assert giusti == totali


def test_ogni_dato_sbagliato_toglie_un_punto_e_una_riga_mancante_tutti_i_suoi(caso):
    letto = copy.deepcopy(caso.impegno)
    letto["pagamento"]["iban"] = "IT99C0300203280000400162854"
    letto["fornitore"]["denominazione"] = "  " + letto["fornitore"]["denominazione"].upper() + " "  # va bene così
    letto["righe"] = letto["righe"][:1]
    letto["righe"][0]["num_item"] = "100"  # non conta: non è stampato
    giusti, totali = giusti_impegno(caso.impegno, letto)
    assert totali - giusti == 1 + 6


def test_senza_impegno_e_giusto_solo_cio_che_nella_verita_manca(caso):
    giusti, totali = giusti_impegno(caso.impegno, None)
    assert (giusti, totali) == (1, 14 + 6 * 2 + 3 * len(caso.impegno["riepilogo"]))  # solo il beneficiario, null


def test_le_due_misure_sulle_righe_di_un_giro(caso):
    giusto = copy.deepcopy(caso.impegno)
    sbagliato = copy.deepcopy(caso.impegno)
    sbagliato["totale_documento"] = 1.0
    pagamento = caso.impegno["pagamento"]
    righe = [
        {"id": caso.id, "impegno": giusto, "proposta": {"iban": pagamento["iban"], "importo": pagamento["importo"]}},
        {"id": caso.id, "impegno": sbagliato, "proposta": {"iban": pagamento["iban"], "importo": 1.0}},
        {"id": caso.id, "impegno": giusto, "proposta": None},  # la staffetta si è fermata prima del decisore
    ]
    casi = {caso.id: caso}
    _, totali = giusti_impegno(caso.impegno, giusto)
    assert accuratezza_impegno(righe, casi) == pytest.approx(100 * (3 * totali - 1) / (3 * totali))
    # la proposta si misura dove c'è: 3 dati giusti su 4, in 2 proposte
    assert accuratezza_proposta(righe, casi) == (pytest.approx(75.0), 2)
