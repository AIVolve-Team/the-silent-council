"""L'esito dello Sportello: coerenza, tre testimoni, regole del catalogo e decisore."""

from fatture.regole import Scatto

from controllore.valuta import valuta
from tests.test_coerenza import IMPEGNO, lettura

ATTACCANTE = "IT99C0300203280000400162854"


def proposta(iban="IT60X0542811101000000123456", importo=152.50, esito="pagare"):
    return {"iban": iban, "importo": importo, "esito": esito, "motivazione": "Fattura conforme all'ordine."}


def test_se_tutto_coincide_si_propone_il_pagamento():
    v = valuta(IMPEGNO, lettura(), proposta(), [])
    assert v.esito == "pagare"
    assert v.motivi == []
    assert v.pagamento_proposto == {"iban": "IT60X0542811101000000123456", "importo": 152.50}


def test_impegno_e_lettura_diversi_bloccano_e_il_motivo_dice_cosa_non_torna():
    v = valuta(IMPEGNO, lettura(pagamento__iban=ATTACCANTE), proposta(iban=ATTACCANTE), [])
    assert v.esito == "bloccare"
    assert v.pagamento_proposto is None
    (motivo, *_) = v.motivi
    assert (motivo.livello, motivo.esito, motivo.codice) == ("coerenza", "bloccare", "pagamento.iban")
    assert motivo.motivo == "L'estrattore dichiara IBAN IT60…, nella memoria c'è IT99…"
    assert motivo.motivo_en == "The extractor declares IBAN IT60…, but its memory holds IT99…"
    assert ATTACCANTE not in motivo.motivo  # l'IBAN sospetto non compare mai intero
    assert [d.campo for d in v.discordanze] == ["pagamento.iban"]


def test_un_dato_critico_vuoto_passa_a_una_persona():
    v = valuta(IMPEGNO, lettura(pagamento__scadenza=None), proposta(), [])
    assert v.esito == "persona"
    assert [(m.livello, m.codice) for m in v.motivi] == [("coerenza", "pagamento.scadenza")]


def test_una_proposta_diversa_da_impegno_e_lettura_blocca():
    v = valuta(IMPEGNO, lettura(), proposta(iban=ATTACCANTE), [])
    assert v.esito == "bloccare"
    assert [(m.livello, m.codice) for m in v.motivi] == [("tre testimoni", "pagamento.iban")]


def test_le_regole_del_catalogo_entrano_nell_esito():
    a04 = Scatto("A04", "persona", "Beneficiario diverso", "Different payee")
    v = valuta(IMPEGNO, lettura(), proposta(), [a04])
    assert v.esito == "persona"
    assert [(m.livello, m.codice) for m in v.motivi] == [("regole", "A04")]


def test_il_decisore_puo_solo_chiedere_una_persona():
    assert valuta(IMPEGNO, lettura(), proposta(esito="persona"), []).esito == "persona"
    assert valuta(IMPEGNO, lettura(), proposta(esito="bloccare"), []).esito == "persona"
    a03 = Scatto("A03", "bloccare", "IBAN diverso", "Different IBAN")
    assert valuta(IMPEGNO, lettura(), proposta(esito="pagare"), [a03]).esito == "bloccare"


def test_una_riga_ancora_da_giudicare_passa_a_una_persona():
    a11 = Scatto("A11", "da_giudicare", "Riga 2 da abbinare", "Line 2 to be matched")
    assert valuta(IMPEGNO, lettura(), proposta(), [a11]).esito == "persona"


def test_l_interruttore_del_livello_2_per_la_demo():
    # L'estrattore che mente (F3): dichiara l'IBAN registrato, ma la memoria porta quello dell'attaccante.
    letta, proposta_attaccante = lettura(pagamento__iban=ATTACCANTE), proposta(iban=ATTACCANTE)
    spenta = valuta(IMPEGNO, letta, proposta_attaccante, [], livello2=False)
    assert spenta.esito == "pagare"
    assert (
        spenta.pagamento_proposto["iban"] == ATTACCANTE
    )  # "senza la macchina della verità, i soldi andavano all'attaccante"
    accesa = valuta(IMPEGNO, letta, proposta_attaccante, [])
    assert accesa.esito == "bloccare"
