"""Il gestore dei due tool del Consiglio per Evolus: lo stesso per MCP e per HTTP.

    revisiona_contratto(contratto, mittente, oggetto, data, modalità) → raccomandazione, dissensi, sigillo, link, avviso
    registra_scelte(id del caso, scelte, chi) → chi ha ragione su ogni dissenso, nel registro del caso

Valgono per tutti e due i trasporti, come per lo Sportello:
- un esame alla volta, perché la GPU è una;
- la stessa email due volte è lo stesso caso, e il Consiglio non rigira: è il nuovo tentativo di Evolus;
- senza sigillo integro non c'è verdetto, e l'avviso chiede una persona;
- il testo del contratto non si salva: nel caso restano revisione, vista, pagina e scelte.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from revisione import BENCHMARK
from revisione.vista import pagina, vista

MODALITA = ("telepatia", "testo")
MAX_PDF = 10 * 2**20
MAX_CONTRATTO = 200_000  # caratteri: il più lungo del campione CUAD ne ha circa 100.000
MAX_TESTO = 1000
ID_CASO = re.compile(r"consiglio-[0-9a-f]{12}")
SCELTE = ("esperto", "verdetto")  # i due bottoni della pagina del verdetto


class Rifiuto(ValueError):
    """La richiesta non va: 400 in HTTP, errore del tool in MCP. Il modello non è stato toccato."""


def testo_breve(nome: str, valore, *, vuoto: bool = False) -> str:
    if not isinstance(valore, str) or len(valore) > MAX_TESTO or (not vuoto and not valore.strip()):
        raise Rifiuto(f"{nome}: serve un testo di al massimo {MAX_TESTO} caratteri")
    return valore.strip()


def testo_del_pdf(pdf: bytes) -> str:
    """Il testo di un contratto in PDF. Un PDF fatto solo di immagini non ha testo: serve l'OCR, che qui non c'è."""
    if not isinstance(pdf, bytes) or not pdf.startswith(b"%PDF-") or len(pdf) > MAX_PDF:
        raise Rifiuto(f"contratto: serve un PDF di al massimo {MAX_PDF // 2**20} MB")
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        pagine = PdfReader(io.BytesIO(pdf)).pages
        testo = "\n".join(p.extract_text() or "" for p in pagine)
    except (PdfReadError, ValueError) as errore:
        raise Rifiuto("contratto: il PDF non si legge") from errore
    if not testo.strip():
        raise Rifiuto("contratto: il PDF non ha testo (è una scansione?)")
    return testo


def chiave_del_caso(segreto: str, id_caso: str) -> str:
    """La chiave del link personale di un caso: chi ha il link apre la pagina e invia le scelte di quel caso, senza
    conoscere il segreto del server."""
    return hmac.new(segreto.encode(), id_caso.encode(), hashlib.sha256).hexdigest()[:32]


def avviso(v: dict, link: str) -> dict:
    """L'email per la persona, in italiano come la pagina: la scrive il servizio e Evolus la manda così com'è."""
    titolo = v["titolo"]
    if not v["sigillo"]["integro"] or v["raccomandazione"] is None:
        return {
            "oggetto": f"[Consiglio] {titolo}: serve una persona",
            "testo": "\n".join(
                [
                    f"Il Consiglio non ha dato un verdetto su «{titolo}».",
                    "La comunicazione fra gli esperti non ha superato il controllo, oppure il verdetto non è valido.",
                    "Il contratto va rivisto da una persona.",
                    f"Dettagli: {link}",
                ]
            ),
        }
    segnalate = [r["nome"] for r in v["righe"] if r["segnalare"]]
    evidenti = [r for r in v["righe"] if r["dissenso"] and r["dissenso"]["in_evidenza"]]
    righe = [
        f"Il Consiglio ha rivisto «{titolo}». Raccomandazione: {v['raccomandazione']['valore']}.",
        f"Perché: {v['raccomandazione']['motivazione']}",
        "Clausole segnalate: " + (", ".join(segnalate) if segnalate else "nessuna") + ".",
    ]
    if evidenti:
        nomi = ", ".join(f"{r['nome']} ({r['dissenso']['nome_ruolo']})" for r in evidenti)
        righe.append(f"Attenzione: un esperto sicuro non è d'accordo con il verdetto su {nomi}.")
    righe.append(f"Apri il verdetto e scegli chi ha ragione sui dissensi: {link}")
    return {"oggetto": f"[Consiglio] {titolo}: {v['raccomandazione']['valore']}", "testo": "\n".join(righe)}


class Revisore:
    def __init__(
        self,
        revisiona: Callable[[str, str, str], dict],
        casi: Path,
        *,
        segreto: str,
        link: str,
        benchmark: str = "dimostrativo",
    ) -> None:
        """`revisiona(id del caso, testo, modalità)` è il Consiglio e restituisce `Revisione.come_dict()`.

        `link` è l'indirizzo della pagina, con `{id}` e `{chiave}`: per esempio
        `https://consiglio.example.org/verdetto/{id}?chiave={chiave}`.
        """
        if "{id}" not in link or "{chiave}" not in link:
            raise ValueError("il link deve contenere {id} e {chiave}")
        self.revisiona = revisiona
        self.casi = casi
        self.segreto = segreto
        self.link = link
        self.benchmark = BENCHMARK[benchmark]
        self.lucchetto = threading.Lock()  # un esame alla volta
        self.lucchetto_scelte = threading.Lock()  # le scelte non aspettano un esame in corso

    def link_di(self, id_caso: str) -> str:
        return self.link.format(id=id_caso, chiave=chiave_del_caso(self.segreto, id_caso))

    def chiave_giusta(self, id_caso: str, chiave: str) -> bool:
        return isinstance(chiave, str) and hmac.compare_digest(chiave, chiave_del_caso(self.segreto, id_caso))

    def revisiona_contratto(
        self,
        contratto: bytes | None,
        testo: str | None,
        mittente: str,
        oggetto: str,
        data: str,
        modalita: str = "telepatia",
    ) -> dict:
        if (contratto is None) == (testo is None):
            raise Rifiuto("serve il contratto: in PDF oppure come testo, uno solo")
        if modalita not in MODALITA:
            raise Rifiuto(f"modalita: {' o '.join(MODALITA)}")
        testo = testo_del_pdf(contratto) if contratto is not None else testo
        if not isinstance(testo, str) or not testo.strip() or len(testo) > MAX_CONTRATTO:
            raise Rifiuto(f"contratto: serve un testo di al massimo {MAX_CONTRATTO} caratteri")
        mittente = testo_breve("mittente", mittente)
        oggetto = testo_breve("oggetto", oggetto, vuoto=True)
        data = testo_breve("data", data)
        impronta = hashlib.sha256(testo.encode("utf-8")).hexdigest()
        id_caso = (
            "consiglio-"
            + hashlib.sha256(json.dumps([impronta, mittente, oggetto, data, modalita]).encode()).hexdigest()[:12]
        )
        with self.lucchetto:
            cartella = self.casi / id_caso
            if (cartella / "risposta.json").exists():
                return json.loads((cartella / "risposta.json").read_text())
            revisione = self.revisiona(id_caso, testo, modalita)
            titolo = oggetto or next((r.strip() for r in testo.splitlines() if r.strip()), id_caso)[:120]
            v = vista(revisione, self.benchmark, titolo)
            # La pagina, servita da questo server, manda le scelte qui con la chiave del suo link.
            v["invio_scelte"] = f"/verdetto/{id_caso}/scelte?chiave={chiave_del_caso(self.segreto, id_caso)}"
            risposta = self.risposta(id_caso, v, modalita, revisione)
            cartella.mkdir(parents=True, exist_ok=True)
            (cartella / "revisione.json").write_text(json.dumps(revisione, ensure_ascii=False))
            (cartella / "vista.json").write_text(json.dumps(v, ensure_ascii=False))
            (cartella / "pagina.html").write_text(pagina(v))
            (cartella / "email.json").write_text(
                json.dumps({"mittente": mittente, "oggetto": oggetto, "data": data, "impronta_contratto": impronta})
            )
            (cartella / "risposta.json").write_text(json.dumps(risposta, ensure_ascii=False, indent=1))
        return risposta

    def risposta(self, id_caso: str, v: dict, modalita: str, revisione: dict) -> dict:
        """Quello che serve all'agente principale di Evolus per l'avviso e il percorso."""
        link = self.link_di(id_caso)
        dissensi = [r for r in v["righe"] if r["dissenso"]]
        return {
            "id_caso": id_caso,
            "verdetto": v["raccomandazione"] is not None and v["sigillo"]["integro"],
            "raccomandazione": v["raccomandazione"],
            "sigillo_integro": v["sigillo"]["integro"],
            "segnalate": [
                {"categoria": r["nome"], "citazione": r["citazione"], "citazione_trovata": r["citazione_trovata"]}
                for r in v["righe"]
                if r["segnalare"]
            ],
            "dissensi_gravi": [
                {
                    "categoria": r["nome"],
                    "esperto": r["dissenso"]["nome_ruolo"],
                    "confidenza_esperto": r["dissenso"]["confidenza_esperto"],
                    "in_evidenza": r["dissenso"]["in_evidenza"],
                }
                for r in dissensi
                if r["dissenso"]["tipo"] == "grave"
            ],
            "altri_dissensi": sum(r["dissenso"]["tipo"] != "grave" for r in dissensi),
            "link": link,
            "avviso": avviso(v, link),
            "modalita": modalita,
            "token_generati": revisione.get("token_generati"),
            "secondi": round(revisione.get("secondi") or 0, 1),
        }

    def cartella_di(self, id_caso) -> Path:
        """La cartella di un caso che esiste. L'id si controlla prima di farne un percorso."""
        if not isinstance(id_caso, str) or not ID_CASO.fullmatch(id_caso):
            raise Rifiuto("id_caso: non è l'id di un caso del Consiglio")
        cartella = self.casi / id_caso
        if not (cartella / "risposta.json").exists():
            raise Rifiuto(f"id_caso: il caso {id_caso} non esiste")
        return cartella

    def registra_scelte(self, id_caso: str, scelte: dict, chi: str) -> dict:
        """Le scelte della persona sui dissensi: per ogni categoria in dissenso, "esperto" o "verdetto"."""
        cartella = self.cartella_di(id_caso)
        chi = testo_breve("chi", chi)
        in_dissenso = {r["chiave"] for r in json.loads((cartella / "vista.json").read_text())["righe"] if r["dissenso"]}
        if not isinstance(scelte, dict) or not scelte:
            raise Rifiuto("scelte: serve un oggetto categoria → esperto o verdetto")
        if fuori := sorted(set(scelte) - in_dissenso):
            raise Rifiuto(f"scelte: queste categorie non sono in dissenso: {', '.join(fuori)}")
        if any(v not in SCELTE for v in scelte.values()):
            raise Rifiuto(f"scelte: ogni valore è {' o '.join(SCELTE)}")
        riga = {"scelte": scelte, "chi": chi, "quando": datetime.now(UTC).isoformat()}
        with self.lucchetto_scelte, (cartella / "scelte.jsonl").open("a") as f:
            f.write(json.dumps(riga, ensure_ascii=False) + "\n")
        return {"id_caso": id_caso, "registrate": len(scelte), **riga}

    def caso(self, id_caso: str) -> dict:
        """La vista del caso e le scelte registrate, la più recente in fondo."""
        cartella = self.cartella_di(id_caso)
        scelte = cartella / "scelte.jsonl"
        return {
            "vista": json.loads((cartella / "vista.json").read_text()),
            "scelte": [json.loads(r) for r in scelte.read_text().splitlines()] if scelte.exists() else [],
        }

    def pagina_di(self, id_caso: str) -> str:
        return (self.cartella_di(id_caso) / "pagina.html").read_text()

    def elenco(self) -> list[dict]:
        """I casi, dal più vecchio, con raccomandazione, dissensi gravi e quante volte la persona ha scelto."""
        casi = []
        for risposta in sorted(self.casi.glob("consiglio-*/risposta.json"), key=lambda f: f.stat().st_mtime):
            r = json.loads(risposta.read_text())
            scelte = risposta.parent / "scelte.jsonl"
            casi.append(
                {
                    "id_caso": r["id_caso"],
                    "titolo": json.loads((risposta.parent / "vista.json").read_text())["titolo"],
                    "raccomandazione": (r["raccomandazione"] or {}).get("valore"),
                    "dissensi_gravi": len(r["dissensi_gravi"]),
                    "scelte": len(scelte.read_text().splitlines()) if scelte.exists() else 0,
                }
            )
        return casi
