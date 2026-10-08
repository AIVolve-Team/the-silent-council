"""Il gestore dei due tool dello Sportello: lo stesso per MCP e per HTTP.

    esamina_fattura(pdf, mittente, oggetto, data, modalità) → esito, motivi, proposta, discordanze, sigillo, link
    registra_decisione(id del caso, decisione, chi, nota) → la decisione nel registro del caso

Valgono per tutti e due i trasporti:
- l'IBAN esce sempre abbreviato: intero c'è solo nel PDF, nel registro del caso;
- l'interruttore del livello 2 non è un parametro;
- un esame alla volta, perché la GPU è una;
- la stessa email due volte è lo stesso caso, e l'esame non si rifà: è il nuovo tentativo di Evolus;
- "pagare" è una proposta in attesa di approvazione, mai un pagamento.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from fatture.archivi import Archivi
from motore.messaggio import TELEPATIA, TESTO
from pagina.pagina import CAMPI_ELENCO
from pagina.vista import maschera, vista_caso

MODALITA = (TELEPATIA, TESTO)
MAX_PDF = 10 * 1024 * 1024  # una fattura è di decine di kB
MAX_TESTO = 1000
DECISIONI = ("approvato", "rifiutato", "segnalato")  # le scelte della pagina del caso
ID_CASO = re.compile(r"sportello-[0-9a-f]{12}")


class Rifiuto(ValueError):
    """La richiesta non va: 400 in HTTP, errore del tool in MCP. Il modello non è stato toccato."""


def testo_breve(nome: str, valore, *, vuoto: bool = False) -> str:
    if not isinstance(valore, str) or len(valore) > MAX_TESTO or (not vuoto and not valore.strip()):
        raise Rifiuto(f"{nome}: serve un testo di al massimo {MAX_TESTO} caratteri")
    return valore.strip()


def mascherato(dato):
    """Lo stesso dato con ogni IBAN abbreviato, a qualunque profondità."""
    if isinstance(dato, str):
        return maschera(dato)
    if isinstance(dato, dict):
        return {k: mascherato(v) for k, v in dato.items()}
    if isinstance(dato, list):
        return [mascherato(v) for v in dato]
    return dato


class Sportello:
    def __init__(
        self,
        esamina: Callable[[bytes, dict, str, str], dict],
        archivi: Archivi,
        casi: Path,
        *,
        link: str,
    ) -> None:
        """`esamina(pdf, email, modalità, id del caso)` è la staffetta, che scrive il registro in `casi/<id>/`."""
        self.esamina = esamina
        self.archivi = archivi
        self.casi = casi
        self.link = link
        self.lucchetto = threading.Lock()  # un esame alla volta
        self.lucchetto_decisioni = threading.Lock()  # le decisioni non aspettano un esame in corso

    def esamina_fattura(self, pdf: bytes, mittente: str, oggetto: str, data: str, modalita: str = TELEPATIA) -> dict:
        if not isinstance(pdf, bytes) or not pdf.startswith(b"%PDF-") or len(pdf) > MAX_PDF:
            raise Rifiuto(f"pdf: serve un PDF di al massimo {MAX_PDF // 2**20} MB")
        if modalita not in MODALITA:
            raise Rifiuto(f"modalita: {' o '.join(MODALITA)}")
        mittente, oggetto, data = (
            testo_breve("mittente", mittente),
            testo_breve("oggetto", oggetto, vuoto=True),
            testo_breve("data", data),
        )
        email = {"mittente": mittente, "oggetto": oggetto, "data": data}
        id_caso = (
            "sportello-"
            + hashlib.sha256(
                json.dumps([hashlib.sha256(pdf).hexdigest(), mittente, oggetto, data, modalita]).encode()
            ).hexdigest()[:12]
        )
        with self.lucchetto:
            cartella = self.casi / id_caso
            if (cartella / "risposta.json").exists():
                return json.loads((cartella / "risposta.json").read_text())
            risultato = self.esamina(pdf, email, modalita, id_caso)
            cartella.mkdir(parents=True, exist_ok=True)
            (cartella / "fattura.pdf").write_bytes(pdf)
            vista = vista_caso(risultato, self.archivi, pdf=pdf)
            risposta = self.risposta(risultato, vista, modalita)
            (cartella / "vista.json").write_text(
                json.dumps({k: v for k, v in vista.items() if k != "pdf"}, ensure_ascii=False)
            )
            (cartella / "risposta.json").write_text(json.dumps(risposta, ensure_ascii=False, indent=1))
        return risposta

    def risposta(self, risultato: dict, vista: dict, modalita: str) -> dict:
        """Quello che serve all'agente principale per scegliere il percorso e scrivere l'avviso."""
        esito = risultato["esito"]
        proposta = None
        if esito == "pagare" and vista["proposta"]:
            proposta = {
                "importo": vista["proposta"]["importo"],
                "scadenza": vista["fattura"]["scadenza"],
                "iban": vista["proposta"]["iban_registrato"],
                "stato": "in attesa di approvazione",
            }
        return mascherato({
            "id_caso": risultato["id_caso"],
            "esito": esito,
            "frode_sospetta": vista["frode_sospetta"],
            "non_rispondere_al_mittente": vista["frode_sospetta"],
            "motivo": vista["motivo"],
            "motivi": risultato.get("motivi") or [],
            "fattura": vista["fattura"],
            "proposta": proposta,
            "discordanze": risultato.get("discordanze") or [],
            "sigillo": risultato.get("sigillo"),
            "contatti_anagrafica": vista["contatti"],
            "link": self.link.format(id=risultato["id_caso"]),
            "modalita": modalita,
            "token": risultato.get("token"),
            "secondi": risultato.get("secondi"),
        })  # fmt: skip

    def cartella_di(self, id_caso) -> Path:
        """La cartella di un caso che esiste. L'id si controlla prima di farne un percorso."""
        if not isinstance(id_caso, str) or not ID_CASO.fullmatch(id_caso):
            raise Rifiuto("id_caso: non è l'id di un caso dello Sportello")
        cartella = self.casi / id_caso
        if not (cartella / "risposta.json").exists():
            raise Rifiuto(f"id_caso: il caso {id_caso} non esiste")
        return cartella

    def registra_decisione(self, id_caso: str, decisione: str, chi: str, nota: str = "") -> dict:
        """La decisione della persona, con le regole della pagina del caso: un caso bloccato si approva solo con
        la nota della verifica fatta con i contatti in anagrafica; per rifiutare serve il motivo. Nella demo nessuna
        banca vera: "approvato" resta scritto qui."""
        cartella = self.cartella_di(id_caso)
        if decisione not in DECISIONI:
            raise Rifiuto(f"decisione: {', '.join(DECISIONI)}")
        chi, nota = testo_breve("chi", chi), testo_breve("nota", nota or "", vuoto=True)
        esito = json.loads((cartella / "risposta.json").read_text())["esito"]
        if decisione == "approvato" and esito == "bloccare" and not nota:
            raise Rifiuto("nota: per approvare un caso bloccato serve la verifica fatta con i contatti in anagrafica")
        if decisione == "rifiutato" and not nota:
            raise Rifiuto("nota: per rifiutare serve il motivo")
        riga = {"decisione": decisione, "chi": chi, "nota": mascherato(nota), "quando": datetime.now(UTC).isoformat()}
        with self.lucchetto_decisioni, (cartella / "decisioni.jsonl").open("a") as f:
            f.write(json.dumps(riga, ensure_ascii=False) + "\n")
        return {"id_caso": id_caso, "registrata": True, **riga}

    def caso(self, id_caso: str) -> dict:
        """La vista del caso per la pagina e le decisioni prese, la più recente in fondo."""
        cartella = self.cartella_di(id_caso)
        decisioni = cartella / "decisioni.jsonl"
        return {
            "vista": json.loads((cartella / "vista.json").read_text()),
            "decisioni": [json.loads(r) for r in decisioni.read_text().splitlines()] if decisioni.exists() else [],
        }

    def elenco(self) -> list[dict]:
        """I casi per l'indice della casa dei giudici, dal più vecchio, con l'ultima decisione presa."""
        casi = []
        for risposta in sorted(self.casi.glob("sportello-*/risposta.json"), key=lambda f: f.stat().st_mtime):
            caso = self.caso(risposta.parent.name)
            ultima = caso["decisioni"][-1]["decisione"] if caso["decisioni"] else None
            casi.append({k: caso["vista"].get(k) for k in CAMPI_ELENCO} | {"decisione": ultima})
        return casi
