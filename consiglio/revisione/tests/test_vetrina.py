"""La parte del Consiglio nel sito per i giudici, senza modello."""

import json
from pathlib import Path

import pytest

from revisione import BENCHMARK
from revisione.dati import risposte_esperti
from revisione.vetrina import Privato, scrivi_vetrina

ESEMPIO = Path(__file__).parents[1] / "pagina" / "esempio-revisione.json"


def giro(tmp_path, **cambi):
    revisione = json.loads(ESEMPIO.read_text()) | cambi
    f = tmp_path / f"giro-{revisione['benchmark']}.jsonl"
    f.write_text(json.dumps(revisione) + "\n")
    return f


def test_il_set_dimostrativo_non_esce_prima_della_consegna(tmp_path):
    with pytest.raises(Privato, match="private until delivery"):
        scrivi_vetrina([giro(tmp_path)], tmp_path / "vetrina", registrato=None)
    assert not (tmp_path / "vetrina").exists()


def test_indice_e_pagine(tmp_path):
    uscita = tmp_path / "vetrina"
    n = scrivi_vetrina(
        [giro(tmp_path, benchmark="cuad", contratto="ESEMPIO-SUPPLY AGREEMENT")], uscita, registrato="oggi"
    )
    assert n == 1
    indice = (uscita / "index.html").read_text()
    dati = json.loads(indice.split('<script id="dati" type="application/json">')[1].split("</script>")[0])
    voce = dati["verdetti"][0]
    assert dati["registrato"] == "oggi" and voce["raccomandazione"] == "negoziare" and voce["categorie"] == 19
    assert voce["sigillo_integro"] and (uscita / voce["pagina"]).exists()
    assert "citazione" not in json.dumps(voce)  # nell'indice solo conteggi, niente frasi del contratto


def test_i_nomi_delle_categorie_sono_quelli_dei_dati():
    # Se un nome non coincide, la riga del verdetto resterebbe senza la risposta degli esperti.
    for benchmark in ("cuad", "contractnli", "claudette"):
        chiavi = {c.chiave for c in BENCHMARK[benchmark].categorie}
        usate = {cat for categorie in risposte_esperti(benchmark).values() for cat in categorie}
        assert usate == chiavi, benchmark


def test_un_contratto_cuad_ha_il_confronto_con_gli_esperti(tmp_path):
    contratto = "TRANSPHORM,INC_02_14_2020-EX-10.12(1)-JOINT VENTURE AGREEMENT"
    uscita = tmp_path / "vetrina"
    scrivi_vetrina([giro(tmp_path, benchmark="cuad", contratto=contratto)], uscita, registrato=None)
    indice = (uscita / "index.html").read_text()
    dati = json.loads(indice.split('<script id="dati" type="application/json">')[1].split("</script>")[0])
    voce = dati["verdetti"][0]
    giuste = risposte_esperti("cuad")[contratto]
    segnalare = json.loads(ESEMPIO.read_text())["verdetto"]["dati"]["segnalare"]
    attese = sum(segnalare[c] == g["da_segnalare"] for c, g in giuste.items() if segnalare.get(c) is not None)
    assert voce["fonte"] == "CUAD" and voce["confrontate"] == 19 and voce["d_accordo"] == attese
    pagina = (uscita / voce["pagina"]).read_text()
    assert "github.com/TheAtticusProject/cuad" in pagina
