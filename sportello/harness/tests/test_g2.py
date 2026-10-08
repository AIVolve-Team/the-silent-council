"""G2 e la scelta dei passi latenti, come pre-registrati in «Eval pre-registrato G1-G4»."""

import pytest

from harness.g2 import Intervallo, bootstrap, esito_g2, scegli_passi


def test_la_differenza_e_in_punti_sui_dati_critici():
    # 4 fatture, 8 dati ciascuna: telepatia 32 su 32, testo 24 su 32 → +25 punti.
    intervallo = bootstrap([8, 8, 8, 8], [8, 8, 8, 0])
    assert intervallo.differenza == 25.0
    # Con 4 fatture il ricampionamento può prendere la fattura sbagliata da 0 a 4 volte: 0 ≤ … ≤ 100.
    assert 0.0 <= intervallo.basso <= 25.0 <= intervallo.alto <= 100.0


def test_con_gli_stessi_risultati_l_intervallo_e_zero():
    assert bootstrap([7, 8, 6], [7, 8, 6]) == Intervallo(0.0, 0.0, 0.0)


def test_lo_stesso_seme_da_lo_stesso_intervallo():
    a, b = [8, 7, 8, 5, 8, 6], [8, 8, 8, 8, 7, 8]
    assert bootstrap(a, b) == bootstrap(a, b)


def test_le_coppie_devono_essere_appaiate():
    with pytest.raises(ValueError, match="appaiat"):
        bootstrap([8, 8], [8])


@pytest.mark.parametrize(
    ("intervallo", "atteso"),
    [
        (Intervallo(-2.0, -3.0, 1.0), "dimostrato"),  # anche il limite basso entro i −3 punti
        (Intervallo(-2.0, -4.5, 0.5), "compatibile"),  # la differenza sì, il limite basso no
        (Intervallo(-3.0, -5.0, 0.0), "compatibile"),  # −3 esatto: telepatia ≥ testo − 3
        (Intervallo(-3.5, -6.0, -1.0), "no"),
    ],
)
def test_i_tre_esiti_di_g2(intervallo, atteso):
    assert esito_g2(intervallo) == atteso


@pytest.mark.parametrize(
    ("accuratezze", "atteso"),
    [
        ({0: 95.0, 10: 90.0, 20: 90.8, 40: 92.1}, 40),  # 40 è il migliore, gli altri sono a più di 1 punto
        ({0: 95.0, 10: 91.5, 20: 92.0, 40: 92.3}, 10),  # 10 è a 0,8 punti dal migliore: vince chi ha meno passi
        ({10: 80.0, 20: 85.0, 40: 84.5}, 20),
    ],
)
def test_la_scelta_dei_passi_latenti(accuratezze, atteso):
    # m=0 si misura ma non è un candidato.
    assert scegli_passi(accuratezze) == atteso


def test_il_rapporto_dai_file_dei_giri(tmp_path):
    import copy
    import json

    from fatture.genera import genera_insieme
    from pipeline.schemi import lettura_da

    from harness.g2 import risultato_g2

    casi = genera_insieme("sviluppo").casi[:4]

    def lettura(caso, sbagliati: int):
        letta = copy.deepcopy(lettura_da(caso.impegno))
        if sbagliati:
            letta["pagamento"]["iban"] = "IT99C0300203280000400162854"
        return letta

    def scrivi(cartella, modalita, sbagliate):
        (tmp_path / cartella).mkdir()
        righe = [
            {"id": c.id, "modalita": modalita, "esito": "pagare", "lettura": lettura(c, i in sbagliate)}
            for i, c in enumerate(casi)
        ]
        (tmp_path / cartella / f"{modalita}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in righe))

    scrivi("testo", "testo", set())  # 32 su 32
    scrivi("m0", "telepatia", {0, 1})  # 30 su 32
    scrivi("m10", "telepatia", {0})  # 31 su 32: 3,1 punti sotto m20
    scrivi("m20", "telepatia", set())  # 32 su 32
    scrivi("m40", "telepatia", {0, 1, 2})  # 29 su 32

    r = risultato_g2(tmp_path, {c.id: c for c in casi})
    assert r.accuratezze == {"testo": 100.0, 0: 93.75, 10: 96.875, 20: 100.0, 40: 90.625}
    assert r.passi == 20  # 10 è a 3,1 punti da 20: troppo lontano
    assert r.intervallo.differenza == 0.0
    assert r.esito == "dimostrato"


def test_il_testo_del_rapporto():
    from harness.g2 import RisultatoG2, testo_g2

    r = RisultatoG2(
        {"testo": 98.0, 0: 93.5, 10: 96.0, 20: 96.5, 40: 95.0}, 10, Intervallo(-2.0, -3.4, -0.6), "compatibile"
    )
    testo = testo_g2(r)
    assert "| testo | 98,0% |" in testo
    assert "**10 passi latenti**" in testo
    assert "−2,0 punti" in testo and "da −3,4 a −0,6" in testo
    assert "**G2 passa: compatibile**" in testo
