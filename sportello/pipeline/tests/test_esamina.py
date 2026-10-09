"""La staffetta dello Sportello su una fattura vera del generatore, con Qwen3-0.6B.

Con un modello così piccolo la qualità non conta: qui si controlla che i pezzi stiano al posto giusto. Il sigillo e la
coerenza fermano la staffetta prima del decisore; il registro del caso si verifica da sé; la modalità a testo scrive di
più. La qualità la misura G2 sulla MI300X con Qwen3-14B.
"""

import json
import os

import pytest
from fatture.genera import genera_insieme
from fatture.pdf import rendi_pdf
from fatture.regole import riferimento
from motore import Modello
from motore.messaggio import TELEPATIA, TESTO
from motore.verifica import verifica_archivio

from pipeline.schemi import lettura_da
from pipeline.sportello import Attacco, chiavi_di_prova, esamina

NOME = os.environ.get("PIPELINE_MODELLO", "Qwen/Qwen3-0.6B")
REVISIONE = os.environ.get("PIPELINE_REVISIONE", "c1899de289a04d12100db370d81485cdf75e47ca")
ATTACCANTE = "IT99C0300203280000400162854"
# Un verificatore perfetto: legge dalla memoria esattamente ciò che l'estrattore ha dichiarato.
PERFETTO = Attacco(lettura=lambda letta, impegno: lettura_da(impegno))
# Un verificatore che nella memoria trova l'IBAN dell'attaccante.
IBAN_FALSO = Attacco(
    lettura=lambda letta, impegno: (
        lettura_da(impegno) | {"pagamento": {**lettura_da(impegno)["pagamento"], "iban": ATTACCANTE}}
    )
)

pytestmark = pytest.mark.modello


@pytest.fixture(scope="module")
def modello():
    return Modello(NOME, REVISIONE)


@pytest.fixture(scope="module")
def insieme():
    return genera_insieme("sviluppo")


@pytest.fixture(scope="module")
def caso(insieme):
    """La fattura pulita più corta, per tenere i test veloci."""
    pulite = [c for c in insieme.casi if c.anomalia is None and c.al_limite is None and not c.abbinamenti]
    return min(pulite, key=lambda c: len(c.impegno["righe"]))


@pytest.fixture(scope="module")
def chiavi(tmp_path_factory):
    return chiavi_di_prova(tmp_path_factory.mktemp("chiavi"))


def esegui(modello, insieme, caso, chiavi, tmp_path, **opzioni):
    return esamina(
        modello, rendi_pdf(caso), caso.email, insieme.archivi, chiavi, max_token_testo=48, registro=tmp_path,
        id_caso=caso.id, **opzioni,
    )  # fmt: skip


def test_telepatia_e_testo_arrivano_a_un_esito(modello, insieme, caso, chiavi, tmp_path):
    telepatia = esegui(modello, insieme, caso, chiavi, tmp_path / "t", modalita=TELEPATIA, passi_latenti=4)
    testo = esegui(modello, insieme, caso, chiavi, tmp_path / "x", modalita=TESTO)
    for r in (telepatia, testo):
        assert r["esito"] in ("pagare", "persona", "bloccare")
        assert r["id_caso"] == caso.id
        assert r["sigillo"] == "integro"
        assert set(r["impegno"]) >= {"fornitore", "documento", "pagamento", "righe"}
        assert set(r["lettura"]) == {"fornitore", "documento", "totale_documento", "pagamento", "ordine"}
    # Il risparmio della telepatia: a testo estrattore e verificatore scrivono le loro analisi, in telepatia no.
    assert telepatia["token"]["analisi"] == 0 < testo["token"]["analisi"]


def test_il_registro_del_caso_si_verifica_da_se(modello, insieme, caso, chiavi, tmp_path):
    r = esegui(modello, insieme, caso, chiavi, tmp_path, modalita=TELEPATIA, passi_latenti=2, attacco=PERFETTO)
    cartella = tmp_path / caso.id
    messaggi = sorted(cartella.glob("*.safetensors"))
    assert len(messaggi) == 2  # estrattore e verificatore: il decisore scrive, non passa memoria
    assert all(esito.passa for _, esito in verifica_archivio(messaggi, cartella / "chiavi-pubbliche"))
    assert json.loads((cartella / "caso.json").read_text())["esito"] == r["esito"]


def test_la_coerenza_ferma_la_staffetta_prima_del_decisore(modello, insieme, caso, chiavi, tmp_path):
    r = esegui(modello, insieme, caso, chiavi, tmp_path, modalita=TELEPATIA, passi_latenti=2, attacco=IBAN_FALSO)
    assert r["esito"] == "bloccare"
    assert r["proposta"] is None  # il decisore non ha mai ricevuto la memoria
    assert r["motivi"][0]["livello"] == "coerenza"
    assert "IT99…2854" in r["motivi"][0]["motivo"]
    # Un motivo per dato, in italiano e in inglese, come quelli della valutazione.
    assert r["motivi"][0]["codice"] == "pagamento.iban"
    assert r["motivi"][0]["motivo_en"].startswith("The extractor declares IBAN")


def test_spento_il_livello_2_si_arriva_al_decisore(modello, insieme, caso, chiavi, tmp_path):
    r = esegui(
        modello, insieme, caso, chiavi, tmp_path, modalita=TELEPATIA, passi_latenti=2, attacco=IBAN_FALSO,
        livello2=False,
    )  # fmt: skip
    assert r["proposta"] is not None
    assert all(m["livello"] not in ("coerenza", "tre testimoni") for m in r["motivi"])


def test_un_messaggio_manomesso_in_transito_rompe_il_sigillo(modello, insieme, caso, chiavi, tmp_path):
    def manometti(ruolo, messaggio):
        if ruolo == "verificatore":
            messaggio.etichetta["impegno"]["pagamento"]["iban"] = ATTACCANTE  # dopo la firma

    attacco = Attacco(manometti=manometti, lettura=PERFETTO.lettura)
    r = esegui(modello, insieme, caso, chiavi, tmp_path, modalita=TELEPATIA, passi_latenti=2, attacco=attacco)
    assert r["esito"] == "bloccare"
    assert r["sigillo"].startswith("rotto")
    assert r["motivi"][0]["livello"] == "sigillo"
    assert list((tmp_path / "incidenti").glob("incidente-*.json"))


def test_le_righe_senza_riferimento_le_abbina_l_abbinatore_cieco(modello, insieme, chiavi, tmp_path):
    con_righe_libere = [c for c in insieme.casi if c.anomalia is None and c.al_limite is None and c.abbinamenti]
    caso = min(con_righe_libere, key=lambda c: len(c.impegno["righe"]))
    perfetto = Attacco(lettura=lambda letta, impegno: lettura_da(impegno))  # perché la staffetta arrivi al decisore
    r = esegui(modello, insieme, caso, chiavi, tmp_path, modalita=TELEPATIA, passi_latenti=2, attacco=perfetto)
    if r["sigillo"] == "integro" and r["proposta"] is not None:
        # Una risposta per ogni riga che nell'impegno dichiarato non ha riferimento, giusta o no: quali sono dipende da
        # come il modello piccolo ha letto la fattura.
        libere = {riga["n"] for riga in r["impegno"]["righe"] if riferimento(riga) is None}
        assert set(r["abbinamenti"]) == libere
