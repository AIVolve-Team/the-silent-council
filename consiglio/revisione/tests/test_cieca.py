"""Il controllo a mano alla cieca, senza modello."""

import csv
import json

from revisione.cieca import conta, prepara


def revisione(contratto, raccomandazione):
    return {
        "benchmark": "dimostrativo",
        "contratto": contratto,
        "verdetto": {
            "dati": {
                "segnalare": {"Exclusivity": True, "Non-Compete": False},
                "dettagli": [{"categoria": "Exclusivity", "citazione": "solo dal Fornitore", "motivazione": "vincola"}],
                "raccomandazione": raccomandazione,
                "motivazione": "per l'esclusiva",
                "obiezioni": [],
            }
        },
        "dissensi": [{"categoria": "Non-Compete", "ruolo": "rischio", "tipo": "grave"}],
        "token_generati": 1234,
        "posizioni_latenti": 30,
    }


def test_fogli_senza_modalita_e_conti_con_la_chiave(tmp_path):
    for configurazione, raccomandazione in (("testo", "negoziare"), ("telepatia", "firmare")):
        righe = [revisione(c, raccomandazione) for c in ("uno", "due")]
        (tmp_path / f"dimostrativo-sviluppo-{configurazione}.jsonl").write_text("\n".join(map(json.dumps, righe)))
    assert prepara(tmp_path, tmp_path / "cieca") == 4
    fogli = sorted((tmp_path / "cieca" / "per-chi-controlla").glob("verdetto-*.md"))
    testi = [f.read_text() for f in fogli]
    assert len(fogli) == 4 and all("Esclusiva" in t and "Non concorrenza" in t for t in testi)
    assert not any(parola in t.lower() for t in testi for parola in ("telepatia", "1234", "latent", "token"))
    chiave = json.loads((tmp_path / "cieca" / "chiave.json").read_text())["verdetti"]
    scheda = tmp_path / "cieca" / "per-chi-controlla" / "scheda.csv"
    righe = list(csv.DictReader(scheda.open()))
    for r in righe:  # chi controlla dà ragione solo alle raccomandazioni "negoziare"
        r |= {
            "raccomandazione_giusta": "sì"
            if "negoziare" in (tmp_path / "cieca" / "per-chi-controlla" / f"{r['verdetto']}.md").read_text()
            else "no"
        }
    with scheda.open("w", newline="") as f:
        scrittore = csv.DictWriter(f, fieldnames=righe[0].keys())
        scrittore.writeheader()
        scrittore.writerows(righe)
    tabella = conta(scheda, tmp_path / "cieca" / "chiave.json")
    assert "| Consiglio a testo | 2/2 | 0/0 | 0/0 |" in tabella and "| Consiglio in telepatia | 0/2 |" in tabella
    assert {v["configurazione"] for v in chiave.values()} == {"testo", "telepatia"}
