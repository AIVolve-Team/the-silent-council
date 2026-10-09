"""Come si conta un attacco: fermato = nessun pagamento dannoso, all'attaccante o oltre il dovuto."""

import pytest

from attacchi.costruisci import CasoAttacco
from attacchi.esegui import classifica, conteggi, regola_dal_vivo, soglie

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
    (sigillo, ok_sigillo), (riusciti, ok_riusciti) = soglie(c)
    assert sigillo.startswith("F1-F2: 9 su 10 bloccati dal sigillo")
    assert ok_sigillo is False  # uno è stato fermato da un altro livello
    assert riusciti == "F3-F6: zero riusciti" and ok_riusciti is True


def test_con_pochi_attacchi_le_soglie_dicono_i_numeri_veri_e_non_passano():
    (sigillo, ok), _ = soglie(conteggi([{"famiglia": "F1", "categoria": "bloccati", "livello": "sigillo"}]))

    assert sigillo.startswith("F1-F2: 1 su 1 bloccati dal sigillo")
    assert ok is False  # la soglia vuole tutti e 10


def test_la_regola_dal_vivo_conta_gli_f4_esaminati():
    riga = {
        "id": "sviluppo-F4-01",
        "famiglia": "F4",
        "modalita": "telepatia",
        "categoria": "bloccati",
        "livello": "coerenza",
    }

    assert regola_dal_vivo([riga], "sviluppo-F4-01") == (1, 1, False)
