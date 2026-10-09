"""Le configurazioni di confronto dell'eval: l'agente solo e il voto fra 4 agenti indipendenti.

Chi lavora da solo legge tutto il contratto e scrive un verdetto con lo schema del Consiglio, senza obiezioni perché
non ha colleghi. Il risultato ha la forma di `Revisione.come_dict()`, così voto, token e tempi si misurano allo stesso
modo per tutte le configurazioni.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import asdict

from motore import TESTO, Agente, Motore

from .categorie import Benchmark
from .citazioni import verifica
from .confidenza import token_booleani
from .consiglio import Revisione, Scritto, _scritto
from .istruzioni import INDIPENDENTI, contratto_intero, istruzioni_indipendente, istruzioni_solo
from .schemi import RACCOMANDAZIONI, schema_verdetto, token_massimi

SOLO, VOTO = "solo", "voto"


class _DaSolo:
    """Un agente che legge tutto il contratto e scrive il verdetto senza colleghi."""

    configurazione = ""

    def __init__(self, motore: Motore, benchmark: Benchmark, *, traduci: bool = False) -> None:
        self.motore = motore
        self.benchmark = benchmark
        self.traduci = traduci
        self.schema = schema_verdetto(benchmark.categorie, obiezioni=False)
        self.veri, self.falsi = token_booleani(motore.modello.tokenizer)

    def _scrivi(self, agente: Agente, testo: str) -> Scritto:
        generazione = self.motore.scrivi(
            agente,
            contratto_intero(testo, traduci=self.traduci),
            [],
            modalita=TESTO,
            schema=self.schema,
            ordine_campi=True,
            max_spazi=1,
            osserva=self.veri + self.falsi,
            max_token=token_massimi(self.schema),
        )
        return _scritto(generazione, self.veri, self.falsi, testo)

    def _revisione(self, contratto: str, testo: str) -> Revisione:
        return Revisione(
            self.benchmark.nome,
            contratto,
            self.configurazione,
            0,
            self.motore.modello.nome,
            {"modo": "intero", "clausole": 0, "caratteri": {"tutto": len(testo)}},
            riallineamento=self.motore.modello.riallinea,
        )


class AgenteSolo(_DaSolo):
    """Configurazione 1: un agente solo legge tutto il contratto."""

    configurazione = SOLO

    def revisiona(self, contratto: str, testo: str) -> dict:
        inizio = time.perf_counter()
        revisione = self._revisione(contratto, testo)
        revisione.verdetto = self._scrivi(Agente(SOLO, istruzioni_solo(self.benchmark)), testo)
        revisione.token_letti = revisione.verdetto.token_letti
        revisione.token_generati = revisione.verdetto.token_generati
        revisione.secondi = time.perf_counter() - inizio
        return revisione.come_dict()


def vota_fra(scritti: dict[str, Scritto], categorie: list[str]) -> tuple[dict[str, bool], dict[str, float]]:
    """Per ogni categoria vince la maggioranza dei verdetti validi.

    Sul pari vince il gruppo con la confidenza media più alta, cioè la probabilità media della posizione scelta;
    a confidenza pari vince "sì". Restituisce le posizioni e, per la taratura, la p(sì) media dei verdetti validi.
    """
    validi = [s for s in scritti.values() if s.valido]
    segnalare, probabilita = {}, {}
    for categoria in categorie:
        voti = [(s.dati["segnalare"][categoria], s.probabilita_si.get(categoria, 0.5)) for s in validi]
        si = [p for posizione, p in voti if posizione]
        no = [1 - p for posizione, p in voti if not posizione]
        if len(si) != len(no):
            segnalare[categoria] = len(si) > len(no)
        else:
            segnalare[categoria] = sum(si) / max(len(si), 1) >= sum(no) / max(len(no), 1)
        if voti:
            probabilita[categoria] = sum(p for _, p in voti) / len(voti)
    return segnalare, probabilita


def raccomandazione_comune(raccomandazioni: list[str]) -> str | None:
    """La più frequente; sul pari la più prudente (non firmare, poi negoziare, poi firmare)."""
    if not raccomandazioni:
        return None
    conta = Counter(raccomandazioni)
    return max(conta, key=lambda r: (conta[r], RACCOMANDAZIONI.index(r)))


class VotoFraQuattro(_DaSolo):
    """Configurazione 2: 4 agenti indipendenti, con i punti di vista del Consiglio, leggono tutto il contratto e
    votano categoria per categoria. Token e tempi sono la somma dei 4."""

    configurazione = VOTO

    def __init__(self, motore: Motore, benchmark: Benchmark, *, traduci: bool = False) -> None:
        super().__init__(motore, benchmark, traduci=traduci)
        self.agenti = [Agente(r, istruzioni_indipendente(r, benchmark)) for r in INDIPENDENTI]

    def revisiona(self, contratto: str, testo: str) -> dict:
        inizio = time.perf_counter()
        revisione = self._revisione(contratto, testo)
        scritti = {agente.nome: self._scrivi(agente, testo) for agente in self.agenti}
        validi = [s for s in scritti.values() if s.valido]
        letti = sum(s.token_letti for s in scritti.values())
        generati = sum(s.token_generati for s in scritti.values())
        dati = None
        probabilita: dict[str, float] = {}
        if validi:
            segnalare, probabilita = vota_fra(scritti, [c.chiave for c in self.benchmark.categorie])
            # Per ogni categoria a sì, il primo dettaglio di un agente che ha votato sì: serve alla versione severa
            # del voto e alla pagina.
            dettagli, viste = [], set()
            for s in validi:
                for d in s.dati["dettagli"]:
                    categoria = d["categoria"]
                    if segnalare.get(categoria) and s.dati["segnalare"].get(categoria) and categoria not in viste:
                        viste.add(categoria)
                        dettagli.append(d)
            dati = {
                "segnalare": segnalare,
                "dettagli": dettagli,
                "raccomandazione": raccomandazione_comune([s.dati["raccomandazione"] for s in validi]),
                "motivazione": "",
            }
        revisione.verdetto = Scritto(dati, probabilita, verifica(dati, testo), letti, generati, "")
        revisione.token_letti, revisione.token_generati = letti, generati
        revisione.secondi = time.perf_counter() - inizio
        riga = revisione.come_dict()
        riga["voti"] = {nome: asdict(scritto) for nome, scritto in scritti.items()}
        return riga
