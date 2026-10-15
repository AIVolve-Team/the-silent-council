from revisore.gestore import Revisore
from revisore.instradamento import SOGLIA, Instradamento

from .conftest import CONTRATTO, LINK, SEGRETO, ConsiglioFinto, email


class ConsiglioDi(ConsiglioFinto):
    """Il Consiglio finto con il nome del suo modello nella revisione, come quello vero."""

    def __init__(self, modello: str) -> None:
        super().__init__()
        self.modello = modello

    def __call__(self, *argomenti, **opzioni) -> dict:
        return super().__call__(*argomenti, **opzioni) | {"modello": self.modello}


def parole(testo: str) -> int:
    return len(testo.split())


def test_fino_alla_soglia_il_modello_dei_corti_oltre_quello_dei_lunghi():
    corto, lungo = ConsiglioDi("Qwen/Qwen3-14B"), ConsiglioDi("google/gemma-4-31B-it")
    router = Instradamento(corto, lungo, parole, soglia=3)
    assert router("a", "uno due tre", "telepatia")["modello"] == "Qwen/Qwen3-14B"
    lunga = router("b", "uno due tre quattro", "telepatia", "cuad")
    assert lunga["modello"] == "google/gemma-4-31B-it"
    assert lunga["instradamento"] == {"token_contratto": 4, "soglia": 3}
    assert corto.chiamate == [("a", "uno due tre", "telepatia", "dimostrativo")]
    assert lungo.chiamate == [("b", "uno due tre quattro", "telepatia", "cuad")]


def test_la_soglia_di_default_e_quella_della_prova():
    assert Instradamento(ConsiglioFinto(), ConsiglioFinto(), parole).soglia == SOGLIA == 6_000


def test_la_risposta_per_evolus_dice_quale_modello_ha_esaminato(tmp_path):
    router = Instradamento(ConsiglioDi("Qwen/Qwen3-14B"), ConsiglioDi("google/gemma-4-31B-it"), parole, soglia=1)
    revisore = Revisore(router, tmp_path / "casi", segreto=SEGRETO, link=LINK)
    risposta = revisore.revisiona_contratto(None, CONTRATTO, **email())
    assert risposta["modello"] == "google/gemma-4-31B-it" and risposta["verdetto"]
