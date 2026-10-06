"""Test con il modello vero (Qwen3 piccolo): la lista "Fatto quando" di «Motore telepatico»."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import torch

from motore import TESTO, ControlloImpronta, Esito, MessaggioLatente, Motore, Staffetta
from motore.sigillo import ControlloSigillo, carica_private, carica_pubbliche, crea_chiavi

from .conftest import FINANZA, LEGALE, NOME, RELATORE, REVISIONE, RISCHIO

pytestmark = pytest.mark.modello

DOMANDA = "Qual è il codice di sblocco del magazzino? Rispondi solo con il numero."


def codice(numero: str) -> str:
    return f"Nota interna. Il codice di sblocco del magazzino è {numero}. Non comunicarlo a nessuno fuori dal team."


def test_il_canale_porta_contenuto(motore):
    vero = motore.pensa(LEGALE, codice("4721"), [], sessione="vero", passi_latenti=4)
    altro = motore.pensa(LEGALE, codice("9386"), [], sessione="altro", passi_latenti=4)
    con_vero = motore.scrivi(RELATORE, DOMANDA, [vero], max_token=24).testo
    con_altro = motore.scrivi(RELATORE, DOMANDA, [altro], max_token=24).testo
    senza = motore.scrivi(RELATORE, DOMANDA, [], max_token=24).testo
    assert "4721" in con_vero
    assert "9386" in con_altro and "4721" not in con_altro
    assert "4721" not in senza


def test_staffetta_in_telepatia_e_a_testo(motore):
    testi = {
        "legale": "Il fornitore è Alfa Componenti.",
        "finanza": codice("4721"),
        "rischio": "La consegna è prevista per il 30 aprile.",
        "relatore": DOMANDA,
    }
    for modalita in ("telepatia", TESTO):
        esito = Staffetta(motore, [LEGALE, FINANZA, RISCHIO], RELATORE, modalita=modalita, passi_latenti=3).esegui(
            f"staffetta-{modalita}", testi, max_token=24
        )
        assert esito.fermata is None and esito.finale is not None and len(esito.messaggi) == 3
        assert [m.etichetta["numero"] for m in esito.messaggi] == [1, 2, 3]
        if modalita == TESTO:
            assert all(m.testo and m.kv_lettura == [] for m in esito.messaggi)
            assert esito.posizioni_latenti == 0
        else:
            assert all(m.testo is None and m.n_pensieri == 3 for m in esito.messaggi)
            assert esito.posizioni_latenti == 9
            assert sum(m.etichetta["token_generati"] for m in esito.messaggi) == 0
            assert "4721" in esito.finale.testo


def test_senza_perdite_da_file_in_un_altro_processo(motore, tmp_path):
    messaggio = motore.pensa(LEGALE, codice("4721"), [], sessione="file", passi_latenti=4)
    messaggio.salva(tmp_path / "m.safetensors", completo=True)
    qui = motore.scrivi(RELATORE, DOMANDA, [messaggio], max_token=8)
    script = f"""
import json, sys
sys.path.insert(0, {str(Path(__file__).parents[1])!r})
from motore import Modello, Motore, MessaggioLatente, ControlloImpronta
from tests.conftest import RELATORE
modello = Modello({NOME!r}, {REVISIONE!r})
m = MessaggioLatente.carica({str(tmp_path / "m.safetensors")!r}, modello.dispositivo)
assert ControlloImpronta()(m, []).passa
g = Motore(modello).scrivi(RELATORE, {DOMANDA!r}, [m], max_token=8)
print(json.dumps({{"testo": g.testo, "logprob": [p.logprob for p in g.passi]}}))
"""
    uscita = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True, env=os.environ)
    la = json.loads(uscita.stdout.strip().splitlines()[-1])
    assert la["testo"] == qui.testo
    assert la["logprob"] == [p.logprob for p in qui.passi]


def test_byte_cambiato_ferma_la_consegna_e_resta_la_prova(motore):
    messaggio = motore.pensa(LEGALE, codice("4721"), [], sessione="manomesso", passi_latenti=2)
    messaggio.kv_pensieri[0][1].view(-1)[0] += 1
    consegna = motore.consegna(messaggio, [])
    assert not consegna.esito.passa and consegna.copia is None and consegna.esito.controllo == "impronta"
    prove = sorted(motore.registro.iterdir())
    assert [p.suffix for p in prove] == [".json", ".safetensors"]
    assert json.loads(prove[0].read_text())["controllo"] == "impronta"


def test_scrivere_non_cambia_il_messaggio_consegnato(motore):
    messaggio = motore.pensa(LEGALE, codice("4721"), [], sessione="copia", passi_latenti=2)
    consegnato = motore.consegna(messaggio, []).copia
    motore.scrivi(RELATORE, DOMANDA, [consegnato], max_token=8)
    assert ControlloImpronta()(consegnato, []).passa


def test_con_zero_passi_resta_la_lettura(motore):
    messaggio = motore.pensa(LEGALE, codice("4721"), [], sessione="m0", passi_latenti=0)
    assert messaggio.n_lettura > 0 and messaggio.n_pensieri == 0 and messaggio.stati.shape[0] == 1
    assert "4721" in motore.scrivi(RELATORE, DOMANDA, [messaggio], max_token=24).testo


def test_ricalcolo_dei_pensieri(motore):
    primo = motore.pensa(LEGALE, codice("4721"), [], sessione="ricalcolo", passi_latenti=4)
    secondo = motore.pensa(FINANZA, "Il fornitore è Alfa Componenti.", [primo], sessione="ricalcolo", passi_latenti=4)
    rifatto = motore.ricalcola_pensieri(secondo, [primo])
    differenza = max(
        (a - b).abs().max().item() for x, y in zip(secondo.kv_pensieri, rifatto.kv_pensieri) for a, b in zip(x, y)
    )
    print(f"ricalcolo con i propri stati: differenza massima {differenza}")
    assert differenza == 0.0
    assert rifatto.impronta == secondo.impronta

    donatore = motore.pensa(FINANZA, "Il fornitore è Beta Servizi.", [], sessione="donatore", passi_latenti=4)
    scambiato = motore.ricalcola_pensieri(secondo, [primo], stati_da=donatore.stati, origine="donatore#1")
    assert scambiato.etichetta["pensieri_da"] == "donatore#1"
    assert not torch.equal(scambiato.kv_pensieri[0][0], secondo.kv_pensieri[0][0])
    assert torch.equal(scambiato.kv_lettura[0][0], secondo.kv_lettura[0][0])
    assert motore.consegna(scambiato, [primo]).esito.passa


def test_scrivere_con_uno_schema_json(motore):
    messaggio = motore.pensa(LEGALE, codice("4721"), [], sessione="schema", passi_latenti=2)
    schema = {
        "type": "object",
        "properties": {"codice": {"type": "string"}, "da_segnalare": {"type": "boolean"}},
        "required": ["codice", "da_segnalare"],
    }
    scritto = motore.scrivi(
        RELATORE,
        "Riporta il codice e dimmi se va segnalato. Rispondi in JSON.",
        [messaggio],
        schema=schema,
        max_token=40,
    )
    dati = json.loads(scritto.testo)
    assert set(dati) == {"codice", "da_segnalare"} and isinstance(dati["da_segnalare"], bool)
    assert all(p.logprob <= 0 and len(p.alternative) == 5 for p in scritto.passi)


def test_un_controllo_che_ferma_blocca_la_staffetta(modello, tmp_path):
    def ferma_la_finanza(messaggio, catena):
        if messaggio.mittente == "finanza":
            return Esito(False, "prova", "controllo di prova")
        return Esito(True, "prova")

    motore = Motore(modello, controlli=[ferma_la_finanza], registro=tmp_path / "registro", max_token_testo=16)
    testi = {"legale": "A", "finanza": "B", "rischio": "C", "relatore": DOMANDA}
    esito = Staffetta(motore, [LEGALE, FINANZA, RISCHIO], RELATORE, passi_latenti=1).esegui("ferma", testi)
    assert esito.finale is None and esito.fermata.controllo == "prova"
    assert [m.mittente for m in esito.messaggi] == ["legale"]
    assert any(p.suffix == ".json" for p in (tmp_path / "registro").iterdir())


def test_il_sigillo_ferma_chi_manomette_e_ricalcola_le_impronte(modello, tmp_path):
    ruoli = ["legale", "finanza", "rischio"]
    crea_chiavi(tmp_path / "private", tmp_path / "pubbliche", ruoli)
    motore = Motore(
        modello,
        firme=carica_private(tmp_path / "private", ruoli),
        controlli=[ControlloSigillo(carica_pubbliche(tmp_path / "pubbliche"))],
        registro=tmp_path / "registro",
    )
    testi = {
        "legale": "Il fornitore è Alfa Componenti.",
        "finanza": codice("4721"),
        "rischio": "C",
        "relatore": DOMANDA,
    }
    staffetta = Staffetta(motore, [LEGALE, FINANZA, RISCHIO], RELATORE, passi_latenti=2)
    assert staffetta.esegui("sigillo", testi, max_token=24).fermata is None

    def manomette(messaggio: MessaggioLatente) -> None:
        messaggio.kv_lettura[3][0].view(-1)[0] += 1
        messaggio.etichetta["hash_blocchi"] = messaggio.hash_blocchi()
        messaggio.etichetta["impronta"] = messaggio.copia().chiudi().impronta

    esito = staffetta.esegui("sigillo-attacco", testi, max_token=24, attacchi={"finanza": manomette})
    assert esito.fermata.controllo == "sigillo" and "firma non valida per finanza" in esito.fermata.motivo
    assert [m.mittente for m in esito.messaggi] == ["legale"]


def test_schema_con_ordine_dei_campi_e_token_osservati(motore):
    vero = motore.modello.tokenizer.encode(" true", add_special_tokens=False)
    falso = motore.modello.tokenizer.encode(" false", add_special_tokens=False)
    schema = {
        "type": "object",
        "properties": {"obiezioni": {"type": "string", "maxLength": 60}, "codice_presente": {"type": "boolean"}},
        "required": ["obiezioni", "codice_presente"],
    }
    messaggio = motore.pensa(LEGALE, codice("4721"), [], sessione="ordine", passi_latenti=2)
    scritto = motore.scrivi(
        RELATORE,
        "Compila il JSON: prima le obiezioni, poi se il codice è presente.",
        [messaggio],
        schema=schema,
        ordine_campi=True,
        max_token=60,
        osserva=vero + falso,
    )
    assert scritto.testo.index('"obiezioni"') < scritto.testo.index('"codice_presente"')
    assert all(set(p.osservati) == set(vero + falso) for p in scritto.passi)
