"""Le misure dell'eval del Consiglio, dalle revisioni scritte da `revisione.esame`.

Tutto parte dalle righe `.jsonl` (una revisione per contratto, nella forma di `Revisione.come_dict()`) e dalle
risposte giuste: qui non gira nessun modello. Le regole, comprese le definizioni operative, sono nella
pre-registrazione (`consiglio/PREREGISTRAZIONE.md`).
"""

from __future__ import annotations

import random
import re
from collections import Counter
from dataclasses import dataclass

from .citazioni import normalizza
from .confidenza import livello
from .punteggio import Voto, accordo, vota

# Le configurazioni, nell'ordine dei rapporti: le quattro a confronto e le tre prove di sabotaggio.
CONFIGURAZIONI = ("solo", "voto", "testo", "telepatia", "m0", "pensieri-scambiati", "contratto-scambiato")
SABOTAGGI = ("m0", "pensieri-scambiati", "contratto-scambiato")
NOMI = {
    "solo": "Agente solo",
    "voto": "4 agenti indipendenti e voto",
    "testo": "Consiglio a testo",
    "telepatia": "Consiglio in telepatia",
    "m0": "Pensieri azzerati (m=0)",
    "pensieri-scambiati": "Pensieri di un altro contratto",
    "contratto-scambiato": "Contratto scambiato",
}
# Soglie di “Pre-registered eval”.
MARGINE_F1 = 3.0
CALO_PENSIERI = 2.0
RIDUZIONE_TOKEN = 0.5
RIPETIZIONI_BOOTSTRAP = 10_000
SEME_BOOTSTRAP = 62
PAROLE_SOVRAPPOSIZIONE = 5


# --- versione severa -----------------------------------------------------------------------------------------------


def _parole(testo: str) -> list[str]:
    return re.findall(r"\w+", normalizza(testo))


def si_sovrappone(citazione: str, prove: list[str]) -> bool:
    """La citazione si sovrappone a un pezzo annotato: hanno in comune almeno 5 parole di fila, oppure la citazione
    intera se è più corta. Le citazioni di meno di 3 parole non contano, come in `citazioni.trovata`. Parole e
    punteggiatura si confrontano dopo la stessa normalizzazione delle citazioni."""
    parole = _parole(citazione)
    if len(parole) < 3:
        return False
    n = min(PAROLE_SOVRAPPOSIZIONE, len(parole))
    cercate = {tuple(parole[i : i + n]) for i in range(len(parole) - n + 1)}
    for prova in prove:
        annotate = _parole(prova)
        if any(tuple(annotate[i : i + n]) in cercate for i in range(len(annotate) - n + 1)):
            return True
    return False


def _citazioni(revisione: dict) -> dict[str, list[str]]:
    dati = (revisione.get("verdetto") or {}).get("dati") or {}
    citazioni: dict[str, list[str]] = {}
    for d in dati.get("dettagli", []):
        citazioni.setdefault(d["categoria"], []).append(d.get("citazione") or "")
    return citazioni


def vota_severo(revisioni: list[dict], giuste: dict, prove: dict) -> Voto:
    """Come `vota`, ma un "sì" giusto conta solo se una sua citazione si sovrappone a un pezzo annotato: altrimenti
    vale come clausola mancata."""
    severe = []
    for r in revisioni:
        dati = (r.get("verdetto") or {}).get("dati")
        if dati is None:
            severe.append(r)
            continue
        citazioni = _citazioni(r)
        segnalare = {}
        for categoria, si in dati["segnalare"].items():
            chiave = (r["contratto"], categoria)
            # I "no" e i falsi allarmi restano come sono; un "sì" giusto resta solo con la citazione giusta.
            giusto = si and giuste.get(chiave)
            segnalare[categoria] = (
                any(si_sovrappone(c, prove.get(chiave, [])) for c in citazioni.get(categoria, [])) if giusto else si
            )
        severe.append({**r, "verdetto": {**r["verdetto"], "dati": {**dati, "segnalare": segnalare}}})
    return vota(severe, giuste)


# --- bootstrap appaiato --------------------------------------------------------------------------------------------


def _conteggi(revisioni: list[dict], giuste: dict) -> dict[str, tuple[int, int, int]]:
    """Contratto → (vp, fp, fn) del voto principale."""
    fuori = {}
    for r in revisioni:
        v = vota([r], {k: g for k, g in giuste.items() if k[0] == r["contratto"]})
        fuori[r["contratto"]] = (v.vp, v.fp, v.fn)
    return fuori


def _f1(vp: int, fp: int, fn: int) -> float:
    return 100 * 2 * vp / (2 * vp + fp + fn) if vp else 0.0


@dataclass
class Differenza:
    differenza: float
    basso: float
    alto: float
    contratti: int

    @property
    def dimostrata(self) -> bool:
        """Si dice "non perde, dimostrato" se anche il limite inferiore sta entro i −3 punti."""
        return self.basso >= -MARGINE_F1


def bootstrap_appaiato(
    a: list[dict], b: list[dict], giuste: dict, *, ripetizioni: int = RIPETIZIONI_BOOTSTRAP, seme: int = SEME_BOOTSTRAP
) -> Differenza:
    """F1(a) − F1(b) con l'intervallo al 95%: si ricampionano i contratti con reinserimento, gli stessi per a e b.
    Percentili 2,5 e 97,5, seme fisso."""
    ca, cb = _conteggi(a, giuste), _conteggi(b, giuste)
    contratti = sorted(set(ca) & set(cb))
    if not contratti:
        raise ValueError("nessun contratto in comune fra le due configurazioni")

    def differenza(scelti: list[str]) -> float:
        sa = [sum(ca[c][i] for c in scelti) for i in range(3)]
        sb = [sum(cb[c][i] for c in scelti) for i in range(3)]
        return _f1(*sa) - _f1(*sb)

    caso = random.Random(seme)
    campioni = sorted(differenza(caso.choices(contratti, k=len(contratti))) for _ in range(ripetizioni))
    return Differenza(
        differenza(contratti),
        campioni[int(0.025 * (ripetizioni - 1))],
        campioni[int(0.975 * (ripetizioni - 1))],
        len(contratti),
    )


# --- costi ---------------------------------------------------------------------------------------------------------


def costi(revisioni: list[dict]) -> dict[str, float]:
    """Medie per contratto: token letti, generati (note comprese) e totali, e secondi."""
    n = len(revisioni) or 1
    letti = sum(r["token_letti"] for r in revisioni) / n
    generati = sum(r["token_generati"] for r in revisioni) / n
    return {
        "token_letti": letti,
        "token_generati": generati,
        "token_totali": letti + generati,
        "secondi": sum(r["secondi"] for r in revisioni) / n,
    }


# --- misure senza soglia -------------------------------------------------------------------------------------------


def chi_ha_ragione(revisioni: list[dict], giuste: dict) -> dict[str, tuple[int, int]]:
    """Nei dissensi gravi (esperto sì, verdetto no) quante volte aveva ragione l'esperto; nei lievi (esperto no,
    verdetto sì) quante volte aveva ragione il relatore. (a ragione, dissensi con risposta giusta nota)."""
    conta = {"grave": [0, 0], "lieve": [0, 0]}
    for r in revisioni:
        for d in r.get("dissensi", []):
            giusta = giuste.get((r["contratto"], d["categoria"]))
            if giusta is None:
                continue
            conta[d["tipo"]][1] += 1
            # Grave: ha ragione l'esperto se la clausola va segnalata. Lieve: ha ragione il relatore se va segnalata.
            conta[d["tipo"]][0] += giusta
    return {tipo: (a, n) for tipo, (a, n) in conta.items()}


def taratura(revisioni: list[dict], giuste: dict) -> dict[str, tuple[int, int]]:
    """Per livello di confidenza del verdetto (alta, media, bassa), (giuste, decisioni)."""
    conta = {"alta": [0, 0], "media": [0, 0], "bassa": [0, 0]}
    for r in revisioni:
        verdetto = r.get("verdetto") or {}
        dati = verdetto.get("dati")
        if not dati:
            continue
        for categoria, si in dati["segnalare"].items():
            p = verdetto.get("probabilita_si", {}).get(categoria)
            giusta = giuste.get((r["contratto"], categoria))
            if p is None or giusta is None:
                continue
            voce = conta[livello(p, si)]
            voce[0] += si == giusta
            voce[1] += 1
    return {k: (g, n) for k, (g, n) in conta.items()}


_IMPORTO = re.compile(r"(?:€\s?\d[\d.]*(?:,\d+)?|\d[\d.]*(?:,\d+)?\s?(?:€|euro\b))", re.IGNORECASE)
_MESI = "gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre"
_DATA = re.compile(rf"\b\d{{1,2}}[/.-]\d{{1,2}}[/.-]\d{{2,4}}\b|\b\d{{1,2}}°? (?:{_MESI}) \d{{4}}\b", re.IGNORECASE)


def _cifre(importo: str) -> str:
    return re.sub(r"[^\d,]", "", importo).rstrip(",")


def importi_e_date(revisione: dict, contratto: str) -> tuple[int, int]:
    """Importi e date scritti nel verdetto (citazioni, motivazioni) e quanti non compaiono nel contratto: un importo
    sbagliato si segnala sempre. Solo conteggi: i valori restano nei `.jsonl`."""
    dati = (revisione.get("verdetto") or {}).get("dati") or {}
    pezzi = [dati.get("motivazione") or ""]
    pezzi += [f"{d.get('citazione', '')} {d.get('motivazione', '')}" for d in dati.get("dettagli", [])]
    testo = " ".join(pezzi)
    nel_contratto = {_cifre(i) for i in _IMPORTO.findall(contratto)}
    contratto_normale = normalizza(contratto)
    trovati = [("importo", _cifre(i)) for i in _IMPORTO.findall(testo)]
    trovati += [("data", normalizza(d)) for d in _DATA.findall(testo)]
    fuori = sum(
        (valore not in nel_contratto) if tipo == "importo" else (valore not in contratto_normale)
        for tipo, valore in trovati
    )
    return len(trovati), fuori


# --- decisioni -----------------------------------------------------------------------------------------------------


def g4(telepatia: list[dict], testo: list[dict], giuste: dict) -> dict[str, bool]:
    """Le tre condizioni di G4 su CUAD."""
    f1_tele, f1_testo = vota(telepatia, giuste).f1, vota(testo, giuste).f1
    ct, cx = costi(telepatia), costi(testo)
    return {
        "f1": f1_tele >= f1_testo - MARGINE_F1,
        "token": ct["token_generati"] <= (1 - RIDUZIONE_TOKEN) * cx["token_generati"],
        "tempo": ct["secondi"] <= cx["secondi"],
    }


def pensieri_aiutano(f1_telepatia: float, f1_m0: float | None, f1_scambiati: float | None) -> bool | None:
    """Si dice "i pensieri migliorano il risultato" solo se i pensieri azzerati fanno calare l'F1 di almeno 2 punti
    e quelli di un altro contratto lo fanno calare. None se manca una delle due prove."""
    if f1_m0 is None or f1_scambiati is None:
        return None
    return f1_telepatia - f1_m0 >= CALO_PENSIERI and f1_scambiati < f1_telepatia


FRASE_SEMPRE = "Gli agenti si passano i pensieri."
FRASE_PENSIERI = "I pensieri migliorano il risultato."
FRASE_RISERVA = (
    "Gli agenti si passano la memoria di ciò che hanno letto invece di riscriverlo: stessa qualità, meno token."
)


# --- grafico -------------------------------------------------------------------------------------------------------


def grafico_svg(punti: list[tuple[str, float, float]], titolo: str) -> str:
    """F1 contro token generati per contratto, un punto per configurazione: (nome, token, F1)."""
    larghezza, altezza, margine = 640, 400, 60
    massimo_x = max((x for _, x, _ in punti), default=1) * 1.1 or 1

    def px(x: float) -> float:
        return margine + x / massimo_x * (larghezza - 2 * margine)

    def py(y: float) -> float:
        return altezza - margine - y / 100 * (altezza - 2 * margine)

    righe = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {larghezza} {altezza}" '
            'font-family="sans-serif" font-size="12">'
        ),
        f'<rect width="{larghezza}" height="{altezza}" fill="white"/>',
        f'<text x="{larghezza / 2}" y="24" text-anchor="middle" font-size="15">{titolo}</text>',
        f'<line x1="{margine}" y1="{py(0)}" x2="{larghezza - margine}" y2="{py(0)}" stroke="black"/>',
        f'<line x1="{margine}" y1="{py(0)}" x2="{margine}" y2="{py(100)}" stroke="black"/>',
        f'<text x="{larghezza / 2}" y="{altezza - 18}" text-anchor="middle">token generati per contratto</text>',
        f'<text x="18" y="{altezza / 2}" text-anchor="middle" transform="rotate(-90 18 {altezza / 2})">F1</text>',
    ]
    for y in range(0, 101, 20):
        righe.append(f'<text x="{margine - 8}" y="{py(y) + 4}" text-anchor="end">{y}</text>')
        righe.append(f'<line x1="{margine}" y1="{py(y)}" x2="{larghezza - margine}" y2="{py(y)}" stroke="#ddd"/>')
    for i in range(5):
        x = massimo_x * i / 4
        righe.append(f'<text x="{px(x)}" y="{py(0) + 18}" text-anchor="middle">{x:,.0f}</text>'.replace(",", "."))
    for nome, x, y in punti:
        righe.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="5" fill="#1f5fae"/>')
        righe.append(f'<text x="{px(x) + 8:.1f}" y="{py(y) - 8:.1f}">{nome} ({y:.1f})</text>')
    righe.append("</svg>")
    return "\n".join(righe)


# --- riepilogo per benchmark ---------------------------------------------------------------------------------------


def riga_voto(revisioni: list[dict], giuste: dict, prove: dict) -> dict:
    principale = vota(revisioni, giuste)
    severo = vota_severo(revisioni, giuste, prove)
    validi = sum(bool((r.get("verdetto") or {}).get("dati")) for r in revisioni)
    return {
        "contratti": len(revisioni),
        "verdetti_validi": validi,
        "f1": principale.f1,
        "precisione": principale.precisione,
        "richiamo": principale.richiamo,
        "mcc": principale.mcc,
        "sempre_si": principale.f1_sempre_si,
        "mancate": principale.fn,
        "falsi_allarmi": principale.fp,
        "f1_severa": severo.f1,
        **costi(revisioni),
    }


def riepilogo(
    giri: dict[str, list[dict]],
    giuste: dict,
    prove: dict,
    *,
    testi: dict[str, str] | None = None,
    grado_3: dict | None = None,
) -> dict:
    """Tutti i numeri di un benchmark: `giri` è configurazione → revisioni."""
    numeri: dict = {"configurazioni": {c: riga_voto(r, giuste, prove) for c, r in giri.items()}}
    if "telepatia" in giri and "testo" in giri:
        d = bootstrap_appaiato(giri["telepatia"], giri["testo"], giuste)
        numeri["telepatia_contro_testo"] = {
            "differenza": d.differenza,
            "basso": d.basso,
            "alto": d.alto,
            "contratti": d.contratti,
            "dimostrata": d.dimostrata,
            "g4": g4(giri["telepatia"], giri["testo"], giuste),
        }
    if "telepatia" in giri:
        f1 = {c: numeri["configurazioni"][c]["f1"] for c in giri}
        numeri["sabotaggi"] = {c: f1[c] - f1["telepatia"] for c in SABOTAGGI if c in f1}
        numeri["pensieri_aiutano"] = pensieri_aiutano(f1["telepatia"], f1.get("m0"), f1.get("pensieri-scambiati"))
    numeri["senza_soglia"] = {}
    for c in ("testo", "telepatia"):
        if c in giri:
            uguali, confrontate = accordo(giri[c])
            numeri["senza_soglia"][c] = {
                "dissensi": chi_ha_ragione(giri[c], giuste),
                "taratura": taratura(giri[c], giuste),
                "accordo_note_verdetto": (uguali, confrontate),
                "note_come_verdetto_f1": vota(giri[c], giuste, dalle_note=True).f1,
            }
    if testi:
        numeri["importi_e_date"] = {
            c: tuple(map(sum, zip(*(importi_e_date(r, testi[r["contratto"]]) for r in rev), strict=True)))
            for c, rev in giri.items()
            if rev and c != "contratto-scambiato"
        }
    if grado_3:
        numeri["grado_3"] = {c: vota(r, grado_3).f1 for c, r in giri.items()}
    numeri["raccomandazioni"] = {
        c: dict(Counter(((r.get("verdetto") or {}).get("dati") or {}).get("raccomandazione") for r in rev))
        for c, rev in giri.items()
    }
    return numeri
