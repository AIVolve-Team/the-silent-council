import copy
import json
from pathlib import Path

import pytest

from revisore.gestore import Revisore

ESEMPIO = json.loads((Path(__file__).parents[2] / "revisione" / "pagina" / "esempio-revisione.json").read_text())
SEGRETO = "segreto-di-prova-lungo-almeno-trentadue-caratteri"
LINK = "https://consiglio.example.org/verdetto/{id}?chiave={chiave}"
CONTRATTO = "CONTRATTO DI FORNITURA\n\nArt. 1 – Oggetto\nIl Fornitore fornisce componenti meccanici al Cliente.\n"


def pdf_con_testo(testo: str) -> bytes:
    """Un PDF di una pagina con una riga di testo, scritto a mano: basta a pypdf per estrarla."""
    flusso = f"BT /F1 12 Tf 72 720 Td ({testo}) Tj ET".encode()
    oggetti = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length " + str(len(flusso)).encode() + b" >>\nstream\n" + flusso + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf, posizioni = b"%PDF-1.4\n", []
    for i, oggetto in enumerate(oggetti, 1):
        posizioni.append(len(pdf))
        pdf += f"{i} 0 obj\n".encode() + oggetto + b"\nendobj\n"
    inizio = len(pdf)
    pdf += f"xref\n0 {len(oggetti) + 1}\n0000000000 65535 f \n".encode()
    pdf += b"".join(f"{p:010d} 00000 n \n".encode() for p in posizioni)
    pdf += f"trailer\n<< /Size {len(oggetti) + 1} /Root 1 0 R >>\nstartxref\n{inizio}\n%%EOF\n".encode()
    return pdf


class ConsiglioFinto:
    """Restituisce la revisione d'esempio della pagina e conta le chiamate."""

    def __init__(self) -> None:
        self.chiamate: list[tuple[str, str, str]] = []
        self.fermata = None
        self.guasto: Exception | None = None

    def __call__(self, id_caso: str, testo: str, modalita: str) -> dict:
        if self.guasto:
            raise self.guasto
        self.chiamate.append((id_caso, testo, modalita))
        revisione = copy.deepcopy(ESEMPIO) | {"contratto": id_caso, "modalita": modalita}
        if self.fermata:
            revisione |= {"fermata": self.fermata, "verdetto": None, "dissensi": []}
        return revisione


@pytest.fixture
def consiglio():
    return ConsiglioFinto()


@pytest.fixture
def revisore(consiglio, tmp_path):
    return Revisore(consiglio, tmp_path / "casi", segreto=SEGRETO, link=LINK)


def email(**altro) -> dict:
    return {"mittente": "fornitore@example.org", "oggetto": "Contratto di fornitura", "data": "2026-10-09"} | altro
