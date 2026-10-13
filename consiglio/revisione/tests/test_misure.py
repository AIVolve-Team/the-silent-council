"""Test senza modello dell'eval: misure, voto fra 4, protezione del test e rapporto."""

import json

import pytest

from revisione import esame, misure
from revisione.configurazioni import raccomandazione_comune, vota_fra
from revisione.consiglio import MAX_TOKEN_ANALISI as MAX
from revisione.consiglio import Scritto
from revisione.dati import risposte_giuste

PROVA = "The Company shall not, during the Term, engage in any business that competes with the Distributor."


def riga(contratto, segnalare, *, dettagli=(), p=None, token=(100, 10), secondi=1.0, dissensi=(), note=None):
    dati = {"segnalare": segnalare, "dettagli": list(dettagli), "raccomandazione": "negoziare", "motivazione": ""}
    return {
        "contratto": contratto,
        "verdetto": {"dati": dati, "probabilita_si": p or {}},
        "note": note or {},
        "dissensi": list(dissensi),
        "token_letti": token[0],
        "token_generati": token[1],
        "secondi": secondi,
    }


def test_sovrapposizione_con_il_pezzo_annotato():
    assert misure.si_sovrappone("«engage in any business that competes» with others", [PROVA])
    assert misure.si_sovrappone("shall not, during the", [PROVA])  # corta ma tutta dentro
    assert not misure.si_sovrappone("the Term", [PROVA])  # meno di 3 parole
    assert not misure.si_sovrappone("the Distributor may terminate this Agreement", [PROVA])


def test_versione_severa_conta_il_si_solo_con_la_citazione_giusta():
    giuste = {("a", "x"): True, ("a", "y"): True, ("a", "z"): False}
    prove = {("a", "x"): [PROVA], ("a", "y"): [PROVA], ("a", "z"): []}
    dettagli = [
        {"categoria": "x", "citazione": "engage in any business that competes"},
        {"categoria": "y", "citazione": "una frase che non c'entra niente"},
    ]
    r = riga("a", {"x": True, "y": True, "z": True}, dettagli=dettagli)
    severo = misure.vota_severo([r], giuste, prove)
    assert (severo.vp, severo.fp, severo.fn) == (1, 1, 1)
    principale = misure.vota([r], giuste)
    assert (principale.vp, principale.fp, principale.fn) == (2, 1, 0)


def test_bootstrap_appaiato():
    giuste = {(c, "x"): True for c in "abcdef"} | {(c, "y"): False for c in "abcdef"}
    giuste_tutte = [riga(c, {"x": True, "y": False}) for c in "abcdef"]
    meta = [riga(c, {"x": c in "abc", "y": False}) for c in "abcdef"]
    uguale = misure.bootstrap_appaiato(giuste_tutte, giuste_tutte, giuste, ripetizioni=200)
    assert (uguale.differenza, uguale.basso, uguale.alto) == (0.0, 0.0, 0.0) and uguale.dimostrata
    meglio = misure.bootstrap_appaiato(giuste_tutte, meta, giuste, ripetizioni=200)
    assert meglio.differenza == pytest.approx(100 - 100 * 2 * 3 / 9)
    assert meglio.basso >= 0 and meglio == misure.bootstrap_appaiato(giuste_tutte, meta, giuste, ripetizioni=200)


def test_misure_senza_soglia():
    giuste = {("a", "x"): True, ("a", "y"): False, ("a", "z"): True}
    dissensi = [{"categoria": "x", "tipo": "grave"}, {"categoria": "y", "tipo": "lieve"}]
    r = riga("a", {"x": True, "y": True, "z": False}, p={"x": 0.95, "y": 0.8, "z": 0.4}, dissensi=dissensi)
    assert misure.chi_ha_ragione([r], giuste) == {"grave": (1, 1), "lieve": (0, 1)}
    assert misure.taratura([r], giuste) == {"alta": (1, 1), "media": (0, 1), "bassa": (0, 1)}
    contratto = "Il Cliente paga € 180.000,00 entro il 31/12/2026."
    dettagli = [{"categoria": "x", "citazione": "paga € 180.000,00", "motivazione": "e altri 5.000 euro il 1/1/2027"}]
    assert misure.importi_e_date(riga("a", {}, dettagli=dettagli), contratto) == (3, 2)


def test_g4_e_frase_sui_pensieri():
    giuste = {("a", "x"): True}
    tele = [riga("a", {"x": True}, token=(50, 40), secondi=10)]
    testo = [riga("a", {"x": True}, token=(100, 100), secondi=20)]
    assert misure.g4(tele, testo, giuste) == {"f1": True, "token": True, "tempo": True}
    assert misure.g4(testo, tele, giuste) == {"f1": True, "token": False, "tempo": False}
    assert misure.pensieri_aiutano(60, 57, 59) is True
    assert misure.pensieri_aiutano(60, 59, 59) is False
    assert misure.pensieri_aiutano(60, None, 59) is None


def scritto(segnalare, p):
    return Scritto({"segnalare": segnalare}, p, {}, 0, 0, "")


def test_voto_fra_quattro_con_il_pari():
    scritti = {
        "a": scritto({"x": True, "y": True, "z": True}, {"x": 0.9, "y": 0.6, "z": 0.75}),
        "b": scritto({"x": True, "y": True, "z": True}, {"x": 0.9, "y": 0.6, "z": 0.75}),
        "c": scritto({"x": False, "y": False, "z": False}, {"x": 0.2, "y": 0.1, "z": 0.25}),
        "d": scritto({"x": True, "y": False, "z": False}, {"x": 0.9, "y": 0.1, "z": 0.25}),
        "rotto": Scritto(None, {}, {}, 0, 0, ""),
    }
    segnalare, p = vota_fra(scritti, ["x", "y", "z"])
    # x: 3 a 1. y: 2 a 2, il no è più sicuro (0,9 contro 0,6). z: 2 a 2 a confidenza pari (0,75): vince il sì.
    assert segnalare == {"x": True, "y": False, "z": True}
    assert p["x"] == pytest.approx(0.725)
    assert raccomandazione_comune(["firmare", "negoziare"]) == "negoziare"
    assert raccomandazione_comune(["firmare", "firmare", "non firmare"]) == "firmare"
    assert raccomandazione_comune([]) is None


def test_il_test_non_parte_con_la_bozza(tmp_path, monkeypatch):
    bozza = tmp_path / "PREREGISTRAZIONE.md"
    bozza.write_text(f"# Pre-registrazione\n\n{esame.BOZZA}\n")
    monkeypatch.setattr(esame, "PREREGISTRAZIONE", bozza)
    with pytest.raises(SystemExit, match="bozza"):
        esame.controlla_preregistrazione()


def test_rapporto_su_cuad_di_sviluppo(tmp_path):
    giuste = risposte_giuste("cuad", "sviluppo")
    contratti = sorted({c for c, _ in giuste})
    perfetti = [riga(c, {k: v for (cc, k), v in giuste.items() if cc == c}, token=(500, 100)) for c in contratti]
    tutto_no = [riga(c, {k: False for (cc, k) in giuste if cc == c}, token=(1000, 300), secondi=2) for c in contratti]
    for nome, righe in {"telepatia": perfetti, "testo": tutto_no, "m0": tutto_no}.items():
        (tmp_path / f"cuad-sviluppo-{nome}.jsonl").write_text("\n".join(json.dumps(r) for r in righe))
    testo = esame.scrivi_rapporto(tmp_path)
    numeri = json.loads((tmp_path / "numeri.json").read_text())["cuad-sviluppo"]
    assert numeri["configurazioni"]["telepatia"]["f1"] == 100.0 and numeri["configurazioni"]["testo"]["f1"] == 0.0
    assert numeri["telepatia_contro_testo"]["dimostrata"] and numeri["sabotaggi"]["m0"] == -100.0
    assert "[x] F1 telepatia" in testo and "Pensieri azzerati" in testo
    assert (tmp_path / "grafico-cuad-sviluppo.svg").read_text().startswith("<svg")


def test_rapporto_con_0_passi_niente_prove_sui_pensieri(tmp_path):
    # Con 0 passi latenti non ci sono pensieri: la frase per la giuria parla di memoria (PREREGISTRAZIONE.md).
    giuste = risposte_giuste("cuad", "sviluppo")
    contratti = sorted({c for c, _ in giuste})
    perfetti = [riga(c, {k: v for (cc, k), v in giuste.items() if cc == c}) for c in contratti]
    tutto_no = [riga(c, {k: False for (cc, k) in giuste if cc == c}) for c in contratti]
    for nome, righe in {"telepatia": perfetti, "testo": tutto_no, "contratto-scambiato": tutto_no}.items():
        (tmp_path / f"cuad-sviluppo-{nome}.jsonl").write_text("\n".join(json.dumps(r) for r in righe))
    (tmp_path / "esame-cuad-sviluppo.json").write_text(json.dumps({"passi": 0, "riallineamento": False}))
    testo = esame.scrivi_rapporto(tmp_path)
    assert "Gli agenti si passano la memoria di ciò che hanno letto." in testo
    assert "si passano i pensieri" not in testo and "Pensieri azzerati" not in testo
    assert "riallineamento spento" in testo


def test_scelta_dei_passi_e_soglie_proposte():
    from revisione.taratura import proponi_soglie, scegli_passi

    assert scegli_passi({0: 60.0, 10: 61.5, 20: 62.6, 40: 63.0}) == 20  # i pensieri aiutano: 20 e 40 entro 1 punto
    assert scegli_passi({10: 61.5, 20: 62.0, 40: 62.4}) == 10  # sotto 1 punto vince il valore con meno passi
    assert scegli_passi({0: 68.8, 10: 56.2, 20: 60.0, 40: 69.5}) == 0  # i pensieri non aiutano: si corregge
    voci = [(0.99, True)] * 9 + [(0.95, False)] + [(0.75, True)] * 7 + [(0.72, False)] * 3 + [(0.55, False)] * 5
    assert proponi_soglie(voci) == (0.8, 0.6)  # sopra 0,8: 9 giuste su 10; fra 0,6 e 0,8: 7 su 10
    assert proponi_soglie([(0.99, False)]) is None


def test_rapporto_telepatia_contro_solo_e_analisi_troncate(tmp_path):
    # Il confronto che isola il canale è con l'agente solo, e il rapporto conta le analisi a testo che toccano il tetto.
    giuste = risposte_giuste("cuad", "sviluppo")
    contratti = sorted({c for c, _ in giuste})
    perfetti = [riga(c, {k: v for (cc, k), v in giuste.items() if cc == c}) for c in contratti]
    tutto_no = [riga(c, {k: False for (cc, k) in giuste if cc == c}) for c in contratti]
    a_testo = [r | {"analisi": {"legale": MAX, "finanza": 300, "rischio": MAX - 1}} for r in tutto_no]
    for nome, righe in {"telepatia": perfetti, "testo": a_testo, "solo": perfetti}.items():
        (tmp_path / f"cuad-sviluppo-{nome}.jsonl").write_text("\n".join(json.dumps(r) for r in righe))
    testo = esame.scrivi_rapporto(tmp_path)
    numeri = json.loads((tmp_path / "numeri.json").read_text())["cuad-sviluppo"]
    assert numeri["telepatia_contro_solo"]["differenza"] == 0.0
    assert numeri["configurazioni"]["testo"]["analisi_troncate"] == len(contratti)
    assert numeri["configurazioni"]["testo"]["analisi"] == 3 * len(contratti)
    assert "F1 della telepatia meno F1 dell'agente solo" in testo
    assert f"tetto di {MAX} token:** {len(contratti)} su {3 * len(contratti)}" in testo


def test_il_giudizio_dimostrato_solo_su_cuad(tmp_path):
    # PREREGISTRAZIONE.md: ContractNLI e CLAUDETTE si riportano senza soglia.
    giuste = risposte_giuste("contractnli", "sviluppo")
    contratti = sorted({c for c, _ in giuste})
    perfetti = [riga(c, {k: v for (cc, k), v in giuste.items() if cc == c}) for c in contratti]
    for nome in ("telepatia", "testo"):
        (tmp_path / f"contractnli-sviluppo-{nome}.jsonl").write_text("\n".join(json.dumps(r) for r in perfetti))
    testo = esame.scrivi_rapporto(tmp_path)
    assert "dimostrato" not in testo and "Senza soglia" in testo
