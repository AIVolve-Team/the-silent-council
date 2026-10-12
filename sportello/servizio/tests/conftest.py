import re

import pytest
from fatture.genera import genera_insieme
from fatture.pdf import rendi_pdf

from servizio.gestore import Sportello

IBAN_INTERO = re.compile(r"[A-Z]{2}\d{2}(?:\s?[A-Z0-9]){12,30}")


@pytest.fixture(scope="session")
def insieme():
    return genera_insieme("sviluppo")


@pytest.fixture(scope="session")
def pulita(insieme):
    return next(c for c in insieme.casi if c.anomalia is None and c.al_limite is None and c.lingua == "it")


@pytest.fixture(scope="session")
def frode(insieme):
    return next(c for c in insieme.casi if c.anomalia == "A03")


def risultato(caso, esito="pagare", motivi=()):
    """Come l'uscita di `pipeline.sportello.esamina`, senza il modello."""
    impegno = caso.impegno
    pagamento = {"iban": impegno["pagamento"]["iban"], "importo": impegno["totale_documento"]}
    return {
        "esito": esito,
        "motivi": list(motivi),
        "proposta": {**pagamento, "abbinamenti": []},
        "pagamento_proposto": pagamento if esito == "pagare" else None,
        "discordanze": [
            {
                "campo": "pagamento.iban",
                "dichiarato": impegno["pagamento"]["iban"],
                "letto": "IT99X0000000000000000002854",
            }
        ]
        if esito == "bloccare"
        else [],
        "discordanze_proposta": [],
        "vuoti": [],
        "abbinamenti": {},
        "sigillo": "integro",
        "impegno": impegno,
        "lettura": impegno,
        "token": {"generati": 100, "letti": 900, "analisi": 0},
        "secondi": 1.5,
    }


class FintaPipeline:
    """Sta al posto della staffetta vera: dà il risultato preparato e conta le chiamate."""

    def __init__(self, risultati: dict[bytes, dict], predefinito: dict):
        self.risultati = risultati
        self.predefinito = predefinito  # per i PDF fatti al momento: attacchi e testo del giudice
        self.chiamate = []
        self.pdf = []
        self.opzioni = []
        self.guasto = None

    def __call__(self, pdf, email, modalita, id_caso, **opzioni):
        self.chiamate.append((email, modalita, id_caso))
        self.pdf.append(pdf)
        self.opzioni.append(opzioni)
        if self.guasto:
            raise self.guasto
        return {"id_caso": id_caso, **self.risultati.get(pdf, self.predefinito), "email": email}


@pytest.fixture
def pdf_pulita(pulita):
    return rendi_pdf(pulita)


@pytest.fixture
def pdf_frode(frode):
    return rendi_pdf(frode)


@pytest.fixture
def pipeline(pulita, frode, pdf_pulita, pdf_frode):
    motivo = {
        "livello": "regole", "esito": "bloccare", "codice": "A03",
        "motivo": f"IBAN {frode.impegno['pagamento']['iban']} diverso da quello in anagrafica",
        "motivo_en": f"IBAN {frode.impegno['pagamento']['iban']} differs from the one on file",
    }  # fmt: skip
    return FintaPipeline(
        {pdf_pulita: risultato(pulita), pdf_frode: risultato(frode, "bloccare", [motivo])}, risultato(pulita)
    )


@pytest.fixture
def sportello(tmp_path, insieme, pipeline):
    return Sportello(pipeline, insieme.archivi, tmp_path / "casi", link="https://sportello.example/caso.html?id={id}")
