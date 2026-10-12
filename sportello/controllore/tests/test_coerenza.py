"""Il confronto fra impegno e lettura sugli 8 dati critici."""

import copy

from controllore.coerenza import CAMPI_CRITICI, confronta

IMPEGNO = {
    "fornitore": {"id_fiscale": "IT01234567890", "denominazione": "Alfa Forniture S.r.l."},
    "documento": {"tipo": "TD01", "numero": "FT/0012/2026", "data": "2026-09-15", "divisa": "EUR"},
    "ordine": {"numero": "PO-2026-0042"},
    "totale_documento": 152.50,
    "pagamento": {"iban": "IT60X0542811101000000123456", "importo": 152.50, "scadenza": "2026-10-15"},
}


def lettura(**modifiche):
    """La lettura del verificatore: gli 8 dati critici, con alcuni valori cambiati (`pagamento__iban=…`)."""
    letta = copy.deepcopy(IMPEGNO)
    for percorso, valore in modifiche.items():
        *strada, ultimo = percorso.split("__")
        nodo = letta
        for pezzo in strada:
            nodo = nodo[pezzo]
        nodo[ultimo] = valore
    return letta


def test_gli_otto_dati_critici():
    assert [c.nome for c in CAMPI_CRITICI] == [
        "fornitore.id_fiscale", "documento.numero", "documento.data", "totale_documento",
        "pagamento.iban", "pagamento.importo", "pagamento.scadenza", "ordine.numero",
    ]  # fmt: skip


def test_se_coincidono_non_ci_sono_discordanze():
    assert confronta(IMPEGNO, lettura()) == ([], [])


def test_gli_stessi_dati_scritti_diversi_coincidono():
    letta = lettura(
        pagamento__iban="it60 x054 2811 1010 0000 0123 456",
        documento__numero="ft 12 2026",
        fornitore__id_fiscale="IT 01234567890",
        totale_documento=152.51,
    )
    assert confronta(IMPEGNO, letta) == ([], [])


def test_un_iban_diverso_e_una_discordanza():
    discordanze, vuoti = confronta(IMPEGNO, lettura(pagamento__iban="IT99C0300203280000400162854"))
    assert vuoti == []
    (d,) = discordanze
    assert (d.campo, d.dichiarato, d.letto) == (
        "pagamento.iban",
        "IT60X0542811101000000123456",
        "IT99C0300203280000400162854",
    )


def test_due_centesimi_sono_una_discordanza():
    discordanze, _ = confronta(IMPEGNO, lettura(pagamento__importo=152.52))
    assert [d.campo for d in discordanze] == ["pagamento.importo"]


def test_un_campo_vuoto_non_si_puo_verificare():
    discordanze, vuoti = confronta(IMPEGNO, lettura(pagamento__scadenza=None))
    assert discordanze == []
    assert vuoti == ["pagamento.scadenza"]
    assert confronta(lettura(ordine__numero=None), IMPEGNO) == ([], ["ordine.numero"])
