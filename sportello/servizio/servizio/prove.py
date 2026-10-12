"""Le prove dal vivo della casa per i giudici: esistono solo con il server in modalità demo.

- **fattura**: una delle nostre fatture dell'insieme, scelta per id;
- **attacco 1**: manomissione in transito (F1 di «Catalogo degli attacchi»): dopo la firma qualcuno cambia il messaggio → il sigillo;
- **attacco 2**: il testo nascosto per la sola memoria (F4) → la coerenza. Il ripiego è l'estrattore compromesso (F3),
  se sullo sviluppo la sola coerenza ferma meno di 8 F4 su 10;
- **inganna**: una nostra fattura con il testo nascosto scritto dal giudice.

L'interruttore del livello 2 esiste solo qui. Ogni prova è un caso come gli altri, con il suo registro, e la
stessa prova due volte è lo stesso caso. Una prova alla volta e senza fila: se il motore sta esaminando, `Occupato`.
Le prove chiamano il motore direttamente, mai Evolus.
"""

from __future__ import annotations

import base64

from attacchi.costruisci import costruisci, pdf_di, pdf_memoria_di
from attacchi.esegui import manomissione
from fatture.genera import Caso, Insieme
from fatture.pdf import rendi_pdf
from motore.messaggio import TELEPATIA
from pipeline.sportello import Attacco

from .gestore import MODALITA, Rifiuto, Sportello

MAX_NASCOSTO = 300


class Prove:
    def __init__(self, sportello: Sportello, insieme: Insieme, *, attacco_1: str, attacco_2: str) -> None:
        """`attacco_1` è un F1 dell'insieme (le varianti senza messaggi donatori), `attacco_2` un F4 o un F3."""
        self.sportello = sportello
        self.casi = {c.id: c for c in insieme.casi}
        attacchi = {a.id: a for a in costruisci(insieme)}
        self.attacchi = {1: attacchi[attacco_1], 2: attacchi[attacco_2]}
        if self.attacchi[1].famiglia != "F1" or self.attacchi[2].famiglia not in ("F3", "F4"):
            raise ValueError("l'attacco 1 è un F1, l'attacco 2 un F4 o il suo ripiego F3")

    def caso_di(self, id_fattura) -> Caso:
        if not isinstance(id_fattura, str) or id_fattura not in self.casi:
            raise Rifiuto("id: non è una delle nostre fatture")
        return self.casi[id_fattura]

    def fattura(self, id_fattura: str, modalita: str = TELEPATIA, livello2: bool = True) -> dict:
        caso = self.caso_di(id_fattura)
        return self.prova(rendi_pdf(caso), caso, modalita, livello2, ["fattura", id_fattura])

    def attacco(self, numero: int, modalita: str = TELEPATIA, livello2: bool = True) -> dict:
        a = self.attacchi.get(numero)
        if a is None:
            raise Rifiuto("numero: 1 (manomissione in transito) o 2 (testo nascosto)")
        if modalita not in a.modalita:
            raise Rifiuto(f"modalita: l'attacco {numero} esiste solo in {' e '.join(a.modalita)}")
        aggancio = None
        if a.famiglia == "F1":
            aggancio = Attacco(manometti=manomissione(a, {}))
        elif a.famiglia == "F3":
            aggancio = Attacco(pdf_memoria=pdf_memoria_di(a, self.casi))
        return self.prova(pdf_di(a, self.casi), self.casi[a.base], modalita, livello2, ["attacco", a.id], aggancio)

    def inganna(self, id_fattura: str, testo: str, modalita: str = TELEPATIA, livello2: bool = True) -> dict:
        caso = self.caso_di(id_fattura)
        if not isinstance(testo, str):
            raise Rifiuto("testo: serve il testo da nascondere")
        testo = " ".join("".join(c if c.isprintable() else " " for c in testo).split())
        if not 0 < len(testo) <= MAX_NASCOSTO:
            raise Rifiuto(f"testo: da 1 a {MAX_NASCOSTO} caratteri")
        try:
            testo.encode("cp1252")  # i caratteri dei font del PDF: il resto diventerebbe ■ e non arriverebbe al modello
        except UnicodeEncodeError as errore:
            raise Rifiuto("testo: solo caratteri latini, niente emoji né altri alfabeti") from errore
        pdf = rendi_pdf(caso, testo_nascosto=testo)
        return self.prova(pdf, caso, modalita, livello2, ["inganna", id_fattura, testo])

    def prova(self, pdf: bytes, caso: Caso, modalita, livello2, chiave: list, attacco: Attacco | None = None) -> dict:
        """La risposta del tool e la vista della pagina del caso, PDF compreso: la casa la mostra senza altri giri."""
        if modalita not in MODALITA:
            raise Rifiuto(f"modalita: {' o '.join(MODALITA)}")
        if not isinstance(livello2, bool):
            raise Rifiuto("livello2: vero o falso")
        opzioni = {"livello2": livello2} | ({"attacco": attacco} if attacco else {})
        chiave = [*chiave, modalita, livello2]
        risposta = self.sportello.esame(pdf, caso.email, modalita, chiave, attendi=False, **opzioni)
        vista = self.sportello.caso(risposta["id_caso"])["vista"]
        return {"risposta": risposta, "vista": vista | {"pdf": base64.b64encode(pdf).decode("ascii")}}
