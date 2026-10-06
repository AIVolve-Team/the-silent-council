"""Il Consiglio: la staffetta degli esperti sul motore, le note per la persona, il verdetto e il dissenso.

Per un contratto:
1. il taglio dà una sezione a ogni esperto;
2. la staffetta del motore fa pensare gli esperti in ordine e scrivere il verdetto al relatore;
3. ogni esperto scrive la sua nota da una copia della propria memoria: la nota non entra nella catena;
4. confidenza dai logprob e dissenso fra nota e verdetto, per categoria.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field

from motore import TELEPATIA, TESTO, Agente, Generazione, Motore, Staffetta

from .categorie import Benchmark
from .citazioni import verifica
from .confidenza import livello, probabilita_si, token_booleani
from .istruzioni import istruzioni_esperto, istruzioni_relatore, lettura, nota, verdetto
from .schemi import schema_nota, schema_verdetto
from .taglio import taglia

# Bastano anche nel caso peggiore, perché gli schemi limitano voci e caratteri.
MAX_TOKEN_NOTA = 300
MAX_TOKEN_VERDETTO = 1100


@dataclass
class Scritto:
    """Una nota o un verdetto: il JSON (None se non è valido), le confidenze e quanto è costato."""

    dati: dict | None
    probabilita_si: dict[str, float]
    # Categoria → la citazione compare parola per parola nel contratto.
    citazioni_trovate: dict[str, bool]
    token_letti: int
    token_generati: int
    testo: str

    @property
    def valido(self) -> bool:
        return self.dati is not None


@dataclass
class Dissenso:
    categoria: str
    ruolo: str
    tipo: str  # grave: l'esperto dice sì e il verdetto no; lieve: il contrario
    confidenza_esperto: str | None
    confidenza_verdetto: str | None


@dataclass
class Revisione:
    benchmark: str
    contratto: str
    modalita: str
    passi_latenti: int
    modello: str
    taglio: dict
    note: dict[str, Scritto] = field(default_factory=dict)
    verdetto: Scritto | None = None
    dissensi: list[Dissenso] = field(default_factory=list)
    fermata: dict | None = None
    impronte: list[str] = field(default_factory=list)
    token_letti: int = 0
    token_generati: int = 0
    posizioni_latenti: int = 0
    secondi: float = 0.0

    def come_dict(self) -> dict:
        return asdict(self)


def _scritto(generazione: Generazione, veri: list[int], falsi: list[int], contratto: str) -> Scritto:
    try:
        dati = json.loads(generazione.testo)
    except json.JSONDecodeError:
        dati = None
    return Scritto(
        dati,
        probabilita_si(generazione, veri, falsi),
        verifica(dati, contratto),
        generazione.token_letti,
        generazione.token_generati,
        generazione.testo,
    )


def _confidenza(scritto: Scritto, chiave: str, posizione: bool) -> str | None:
    p = scritto.probabilita_si.get(chiave)
    return None if p is None else livello(p, posizione)


def dissensi(benchmark: Benchmark, note: dict[str, Scritto], giudizio: Scritto) -> list[Dissenso]:
    """Per ogni categoria, la nota dell'esperto che la guarda contro il verdetto."""
    if not giudizio.valido:
        return []
    trovati = []
    for categoria in benchmark.categorie:
        esperto = note.get(categoria.ruolo)
        if esperto is None or not esperto.valido:
            continue
        dice_esperto = esperto.dati["segnalare"].get(categoria.chiave)
        dice_verdetto = giudizio.dati["segnalare"].get(categoria.chiave)
        if dice_esperto is None or dice_verdetto is None or dice_esperto == dice_verdetto:
            continue
        trovati.append(
            Dissenso(
                categoria.chiave,
                categoria.ruolo,
                "grave" if dice_esperto else "lieve",
                _confidenza(esperto, categoria.chiave, dice_esperto),
                _confidenza(giudizio, categoria.chiave, dice_verdetto),
            )
        )
    return trovati


class Consiglio:
    def __init__(
        self,
        motore: Motore,
        benchmark: Benchmark,
        *,
        modalita: str = TELEPATIA,
        passi_latenti: int = 10,
        traduci: bool = False,
    ) -> None:
        self.motore = motore
        self.benchmark = benchmark
        self.modalita = modalita
        self.passi_latenti = passi_latenti
        self.traduci = traduci
        self.esperti = [Agente(r, istruzioni_esperto(r, benchmark)) for r in benchmark.lettori]
        self.relatore = Agente("relatore", istruzioni_relatore(benchmark))
        self.veri, self.falsi = token_booleani(motore.modello.tokenizer)

    def revisiona(self, contratto: str, testo: str, **opzioni) -> Revisione:
        """`opzioni` va alla staffetta: per esempio `pensieri_da` per la prova di «Eval pre-registrato» o `attacchi` per la demo."""
        inizio = time.perf_counter()
        taglio = taglia(testo, self.benchmark.lettori, self.benchmark.famiglia)
        sessione = f"{self.benchmark.nome}/{contratto}/{self.modalita}/m{self.passi_latenti}"
        testi = {r: lettura(taglio.sezioni[r]) for r in self.benchmark.lettori}
        testi["relatore"] = verdetto(traduci=self.traduci)
        staffetta = Staffetta(
            self.motore, self.esperti, self.relatore, modalita=self.modalita, passi_latenti=self.passi_latenti
        )
        esito = staffetta.esegui(
            sessione,
            testi,
            schema=schema_verdetto(self.benchmark.categorie),
            ordine_campi=True,
            osserva=self.veri + self.falsi,
            max_token=MAX_TOKEN_VERDETTO,
            **opzioni,
        )
        revisione = Revisione(
            self.benchmark.nome,
            contratto,
            self.modalita,
            self.passi_latenti,
            self.motore.modello.nome,
            {
                "modo": taglio.modo,
                "clausole": len(taglio.clausole),
                "caratteri": {r: len(s) for r, s in taglio.sezioni.items()},
            },
            impronte=[m.impronta for m in esito.messaggi],
            posizioni_latenti=esito.posizioni_latenti,
        )
        if esito.fermata is not None:
            revisione.fermata = asdict(esito.fermata)
        else:
            revisione.verdetto = _scritto(esito.finale, self.veri, self.falsi, testo)
        letti, generati = esito.token_letti, esito.token_generati
        for i, esperto in enumerate(self.esperti[: len(esito.messaggi)]):
            # La nota nasce da una copia della memoria dell'esperto e non entra nella catena.
            sezione = taglio.sezioni[esperto.nome] if self.modalita == TESTO else None
            scritta = self.motore.scrivi(
                esperto,
                nota(sezione),
                esito.messaggi[: i + 1],
                modalita=self.modalita,
                schema=schema_nota(self.benchmark.del_ruolo(esperto.nome)),
                ordine_campi=True,
                osserva=self.veri + self.falsi,
                max_token=MAX_TOKEN_NOTA,
            )
            revisione.note[esperto.nome] = _scritto(scritta, self.veri, self.falsi, testo)
            letti, generati = letti + scritta.token_letti, generati + scritta.token_generati
        if revisione.verdetto is not None:
            revisione.dissensi = dissensi(self.benchmark, revisione.note, revisione.verdetto)
        revisione.token_letti, revisione.token_generati = letti, generati
        revisione.secondi = time.perf_counter() - inizio
        return revisione
