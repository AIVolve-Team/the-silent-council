"""Il controllo di coerenza dentro `consegna` del motore."""

from motore.controllo import Esito
from motore.messaggio import MessaggioLatente

from controllore.motore import ControlloCoerenza
from tests.test_coerenza import IMPEGNO, lettura


def messaggio(mittente: str, dichiarazione: dict) -> MessaggioLatente:
    return MessaggioLatente({"mittente": mittente, "impegno": dichiarazione})


def test_alla_consegna_del_verificatore_impegno_e_lettura_devono_coincidere():
    controllo = ControlloCoerenza()
    catena = [messaggio("estrattore", IMPEGNO)]
    assert controllo(messaggio("verificatore", lettura()), catena) == Esito(True, "coerenza")
    fermata = controllo(messaggio("verificatore", lettura(pagamento__iban="IT99C0300203280000400162854")), catena)
    assert not fermata.passa
    assert fermata.controllo == "coerenza"
    assert fermata.motivo == "L'estrattore dichiara IBAN IT60…3456, nella memoria c'è IT99…2854"


def test_gli_altri_messaggi_passano():
    controllo = ControlloCoerenza()
    assert controllo(messaggio("estrattore", IMPEGNO), []).passa
    decisore = messaggio("decisore", {"iban": "IT99C0300203280000400162854"})
    assert controllo(decisore, [messaggio("estrattore", IMPEGNO), messaggio("verificatore", lettura())]).passa


def test_un_campo_vuoto_non_ferma_la_staffetta():
    # Decide una persona alla fine: la staffetta va avanti.
    controllo = ControlloCoerenza()
    assert controllo(
        messaggio("verificatore", lettura(pagamento__scadenza=None)), [messaggio("estrattore", IMPEGNO)]
    ).passa


def test_spento_per_la_demo_non_ferma_niente():
    controllo = ControlloCoerenza(attivo=False)
    catena = [messaggio("estrattore", IMPEGNO)]
    assert controllo(messaggio("verificatore", lettura(pagamento__iban="IT99C0300203280000400162854")), catena).passa


def test_senza_il_messaggio_dell_estrattore_si_ferma():
    fermata = ControlloCoerenza()(messaggio("verificatore", lettura()), [])
    assert not fermata.passa
    assert "estrattore" in fermata.motivo
