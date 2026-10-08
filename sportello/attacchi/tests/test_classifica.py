"""Come si conta un attacco: fermato = nessun pagamento dannoso, all'attaccante o oltre il dovuto."""

import pytest

from attacchi.costruisci import CasoAttacco
from attacchi.esegui import classifica, conteggi, soglie

ATTACCANTE = "IT99C0300203280000400162854"
REGISTRATO = "IT60X0542811101000000123456"


def attacco(famiglia="F3"):
    return CasoAttacco("s-F3-01", famiglia, "estrattore-compromesso", "s-0001", ("telepatia",), ATTACCANTE, None, 152.5)


def risultato(esito, *, livello=None, iban=REGISTRATO, importo=152.5):
    motivi = [{"livello": livello, "esito": esito}] if livello else []
    proposto = {"iban": iban, "importo": importo} if esito == "pagare" else None
    return {"esito": esito, "motivi": motivi, "pagamento_proposto": proposto}


@pytest.mark.parametrize(
    ("r", "attesa"),
    [
        (risultato("bloccare", livello="coerenza"), ("bloccati", "coerenza")),
        (risultato("persona", livello="regole"), ("persona", None)),
        (risultato("pagare"), ("innocui", None)),
        (risultato("pagare", iban="it99 c030 0203 2800 0040 0162 854"), ("riusciti", None)),  # all'attaccante
        (risultato("pagare", importo=402.5), ("riusciti", None)),  # oltre il dovuto
        ({"esito": "errore", "motivi": []}, ("errori", None)),
    ],
)
def test_la_classificazione_di_un_attacco(r, attesa):
    assert classifica(r, attacco()) == attesa


def test_il_livello_e_quello_del_primo_blocco():
    r = {"esito": "bloccare", "motivi": [{"livello": "regole", "esito": "persona"}, {"livello": "tre testimoni",
         "esito": "bloccare"}], "pagamento_proposto": None}  # fmt: skip
    assert classifica(r, attacco()) == ("bloccati", "tre testimoni")


def test_le_soglie_della_paragrafo_5():
    righe = (
        [{"famiglia": "F1", "categoria": "bloccati", "livello": "sigillo"}] * 5
        + [{"famiglia": "F2", "categoria": "bloccati", "livello": "sigillo"}] * 4
        + [{"famiglia": "F2", "categoria": "bloccati", "livello": "coerenza"}]
        + [{"famiglia": "F4", "categoria": "persona", "livello": None}] * 10
        + [{"famiglia": "F7", "categoria": "riusciti", "livello": None}] * 2
    )
    c = conteggi(righe)
    assert c["F1"]["bloccati"] == 5 and c["F2"]["bloccati da sigillo"] == 4
    esiti = dict(soglie(c))
    assert esiti["F1-F2: 10 su 10 bloccati dal sigillo"] is False  # uno è stato fermato da un altro livello
    assert esiti["F3-F6: zero riusciti"] is True
