import copy

from categorie import CUAD_CATEGORIE
from dimostrativo import errori

TESTO = "Il Fornitore può recedere in qualsiasi momento con 30 giorni. Penale di € 2.500,00."


def risposta_valida():
    righe = [
        {"categoria": c, "ruolo": r, "da_segnalare": False, "citazione": None, "motivazione": None}
        for c, r in CUAD_CATEGORIE.items()
    ]
    for riga in righe:
        if riga["categoria"] == "Termination For Convenience":
            riga.update(da_segnalare=True, citazione="può recedere in qualsiasi momento", motivazione="Recesso libero.")
    return {
        "stato": "bozza",
        "raccomandazione": "negoziare",
        "motivazione": "Recesso solo per il Fornitore.",
        "righe": righe,
        "dissenso_atteso": [
            {
                "categoria": "Termination For Convenience",
                "ruolo": "rischio",
                "nota_attesa": "sì",
                "verdetto_atteso": "no",
                "tipo": "grave",
                "ha_ragione": "esperto",
                "perche": "Il relatore potrebbe non vederlo.",
            }
        ],
        "importi_e_date": ["€ 2.500,00", "30 giorni"],
    }


def test_risposta_valida():
    assert errori(risposta_valida(), TESTO) == []


def test_citazione_che_non_compare_nel_contratto():
    risposta = risposta_valida()
    next(r for r in risposta["righe"] if r["da_segnalare"])["citazione"] = "può recedere senza preavviso"
    assert errori(risposta, TESTO) == ["Termination For Convenience: la citazione non compare nel contratto"]


def test_importo_sbagliato():
    risposta = risposta_valida()
    risposta["importi_e_date"] = ["€ 25.000,00"]
    assert errori(risposta, TESTO) == ["importo o data che non compare nel contratto: '€ 25.000,00'"]


def test_dissenso_con_chi_ha_ragione_sbagliato():
    risposta = risposta_valida()
    risposta["dissenso_atteso"][0]["ha_ragione"] = "verdetto"
    assert len(errori(risposta, TESTO)) == 1


def test_mancano_categorie():
    risposta = copy.deepcopy(risposta_valida())
    risposta["righe"].pop()
    assert any("19 categorie" in e for e in errori(risposta, TESTO))
