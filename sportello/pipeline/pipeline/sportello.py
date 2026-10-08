"""La staffetta dello Sportello su una fattura: estrattore → verificatore → decisore, in telepatia o a testo.

    esamina(modello, pdf, email, archivi, chiavi) → l'uscita di `esamina_fattura`

1. L'estrattore legge il testo del PDF e pensa; da una copia della sua memoria scrive l'**impegno**, che va
   nell'etichetta del suo messaggio e viene firmato.
2. Il verificatore, che non vede la fattura, pensa sulla memoria ricevuta e scrive la **lettura** degli 8 dati
   critici, nell'etichetta del suo messaggio.
3. Alla consegna al decisore la coerenza confronta impegno e lettura: se non coincidono la staffetta si ferma.
4. Il decisore scrive la **proposta** e abbina all'ordine le righe senza riferimento (A11).
5. Catena verificata, regole del catalogo, tre testimoni: l'esito è il più grave (`controllore.valuta`).

Ogni caso lascia un registro con i messaggi firmati e le chiavi pubbliche, che `python -m motore.verifica` controlla
da solo.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from controllore.coerenza import confronta
from controllore.motore import ControlloCoerenza
from controllore.valuta import valuta
from fatture.archivi import Archivi
from fatture.normalizza import id_fiscale
from fatture.regole import applica_regole, riferimento
from motore import ControlloSigillo, MessaggioLatente, Modello, Motore, carica_private, carica_pubbliche, crea_chiavi
from motore.messaggio import TELEPATIA, TESTO
from motore.modello import Generazione

from .agenti import DECISORE, ESTRATTORE, LEGGI, RICORDA, SCRIVI_IMPEGNO, SCRIVI_LETTURA, VERIFICATORE, prompt_decisore
from .schemi import SCHEMA_IMPEGNO, SCHEMA_LETTURA, schema_proposta
from .testo import estrai_testo

RUOLI = ("estrattore", "verificatore", "decisore")
CONTROLLI_DEL_SIGILLO = ("impronta", "catena", "sigillo")
MAX_TOKEN = {"impegno": 2048, "lettura": 320, "proposta": 512}


@dataclass
class Chiavi:
    private: dict
    pubbliche: dict
    cartella_pubbliche: Path


def chiavi_di_prova(cartella: Path) -> Chiavi:
    """Una coppia Ed25519 per ruolo: le private fuori dal repo, le pubbliche da distribuire."""
    private, pubbliche = cartella / "private", cartella / "pubbliche"
    crea_chiavi(private, pubbliche, list(RUOLI))
    return Chiavi(carica_private(private, list(RUOLI)), carica_pubbliche(pubbliche), pubbliche)


@dataclass
class Attacco:
    """Agganci per gli attacchi e per i test: nella modalità normale non esistono."""

    pdf_memoria: bytes | None = None  # F3: l'estrattore pensa su questo PDF, l'impegno viene da quello vero
    manometti: Callable[[str, MessaggioLatente], None] | None = None  # F1-F2: dopo la firma, prima della consegna
    lettura: Callable[[dict, dict], dict] | None = None  # (lettura, impegno) → la lettura da consegnare


class Conteggio:
    def __init__(self) -> None:
        self.generati = 0
        self.letti = 0
        self.analisi = 0  # scritti da `pensa`: le analisi a testo, zero in telepatia

    def messaggio(self, m: MessaggioLatente) -> None:
        self.generati += m.etichetta["token_generati"]
        self.analisi += m.etichetta["token_generati"]
        self.letti += m.etichetta["token_letti"]

    def scritto(self, g: Generazione) -> None:
        self.generati += g.token_generati
        self.letti += g.token_letti


def leggi_json(generazione: Generazione) -> dict | None:
    """Con la decodifica vincolata il JSON è sempre valido, salvo se finisce il limite di token: allora None."""
    try:
        return json.loads(generazione.testo)
    except json.JSONDecodeError:
        return None


def ordine_di(impegno: dict, archivi: Archivi):
    numero = (impegno.get("ordine") or {}).get("numero")
    ordine = archivi.ordini.get(numero) if numero else None
    fornitore = id_fiscale((impegno.get("fornitore") or {}).get("id_fiscale") or "")
    return ordine if ordine is not None and id_fiscale(ordine.fornitore) == fornitore else None


def esamina(
    modello: Modello,
    pdf: bytes,
    email: dict,
    archivi: Archivi,
    chiavi: Chiavi,
    *,
    modalita: str = TELEPATIA,
    passi_latenti: int = 10,
    livello2: bool = True,
    max_token_testo: int = 1024,
    registro: Path | None = None,
    attacco: Attacco | None = None,
    id_caso: str | None = None,
) -> dict:
    inizio = time.perf_counter()
    attacco = attacco or Attacco()
    sessione = id_caso or f"sportello-{hashlib.sha256(pdf).hexdigest()[:12]}"
    motore = Motore(
        modello,
        controlli=[ControlloSigillo(chiavi.pubbliche), ControlloCoerenza(attivo=livello2)],
        firme=chiavi.private,
        registro=None if registro is None else registro / "incidenti",
        max_token_testo=max_token_testo,
    )
    conteggio = Conteggio()
    opzioni = {"sessione": sessione, "passi_latenti": passi_latenti, "modalita": modalita}
    vincolo = {"modalita": modalita, "ordine_campi": True, "max_spazi": 1}
    testo = estrai_testo(pdf)

    # 1. Estrattore: pensa sulla fattura e scrive l'impegno da una copia della sua memoria.
    if attacco.pdf_memoria is not None:
        pulito = motore.pensa(ESTRATTORE, LEGGI.format(fattura=testo), [], destinatario="verificatore", **opzioni)
        conteggio.messaggio(pulito)
        lettura_impegno = [pulito]
        testo_memoria = estrai_testo(attacco.pdf_memoria)
    else:
        lettura_impegno, testo_memoria = None, testo
    m1 = motore.pensa(ESTRATTORE, LEGGI.format(fattura=testo_memoria), [], destinatario="verificatore", **opzioni)
    conteggio.messaggio(m1)
    if modalita == TESTO:
        g = motore.scrivi(ESTRATTORE, f"{SCRIVI_IMPEGNO}\n\nInvoice:\n{testo}", [], schema=SCHEMA_IMPEGNO,
                          max_token=MAX_TOKEN["impegno"], **vincolo)  # fmt: skip
    else:
        g = motore.scrivi(ESTRATTORE, SCRIVI_IMPEGNO, lettura_impegno or [m1], schema=SCHEMA_IMPEGNO,
                          max_token=MAX_TOKEN["impegno"], **vincolo)  # fmt: skip
    conteggio.scritto(g)
    impegno = leggi_json(g)
    if impegno is None:
        return fine(sessione, inizio, conteggio, registro, chiavi, [], esito_troncato("impegno"))
    m1 = motore.con_impegno(m1, impegno)
    if attacco.manometti:
        attacco.manometti("estrattore", m1)
    consegna = motore.consegna(m1, [])
    if not consegna.esito.passa:
        return fine(sessione, inizio, conteggio, registro, chiavi, [], fermata(consegna.esito, impegno, None))
    catena = [consegna.copia]

    # 2. Verificatore: non vede la fattura; dalla memoria ricevuta scrive la lettura dei dati critici.
    m2 = motore.pensa(VERIFICATORE, RICORDA, catena, destinatario="decisore", **opzioni)
    conteggio.messaggio(m2)
    g = motore.scrivi(VERIFICATORE, SCRIVI_LETTURA, [*catena, m2], schema=SCHEMA_LETTURA, max_token=MAX_TOKEN["lettura"],
                      **vincolo)  # fmt: skip
    conteggio.scritto(g)
    lettura = leggi_json(g)
    if lettura is None:
        return fine(sessione, inizio, conteggio, registro, chiavi, catena, esito_troncato("lettura", impegno))
    if attacco.lettura:
        lettura = attacco.lettura(lettura, impegno)
    m2 = motore.con_impegno(m2, lettura)  # nel campo `impegno` dell'etichetta del verificatore c'è la lettura
    if attacco.manometti:
        attacco.manometti("verificatore", m2)
    consegna = motore.consegna(m2, catena)  # qui la coerenza confronta impegno e lettura
    if not consegna.esito.passa:
        return fine(sessione, inizio, conteggio, registro, chiavi, catena, fermata(consegna.esito, impegno, lettura))
    catena.append(consegna.copia)

    # 3. Decisore: propone il pagamento e abbina le righe senza riferimento all'ordine.
    ordine = ordine_di(impegno, archivi)
    libere = [r for r in impegno.get("righe", []) if riferimento(r) is None] if ordine else []
    g = motore.scrivi(DECISORE, prompt_decisore(ordine, libere), catena,
                      schema=schema_proposta([r["n"] for r in libere]), max_token=MAX_TOKEN["proposta"], **vincolo)  # fmt: skip
    conteggio.scritto(g)
    proposta = leggi_json(g)
    if proposta is None:
        return fine(sessione, inizio, conteggio, registro, chiavi, catena, esito_troncato("proposta", impegno, lettura))
    esito_catena = motore.verifica_catena(catena)
    if not esito_catena.passa:
        return fine(sessione, inizio, conteggio, registro, chiavi, catena, fermata(esito_catena, impegno, lettura))

    # 4. Regole del catalogo e tre testimoni.
    abbinamenti = {a["riga"]: a["riga_ordine"] for a in proposta.get("abbinamenti", [])}
    v = valuta(impegno, lettura, proposta, applica_regole(impegno, archivi, abbinamenti), livello2=livello2)
    esito = {
        "esito": v.esito,
        "motivi": [asdict(m) for m in v.motivi],
        "proposta": proposta,
        "pagamento_proposto": v.pagamento_proposto,
        "discordanze": [asdict(d) for d in v.discordanze],
        "discordanze_proposta": [asdict(d) for d in v.discordanze_proposta],
        "vuoti": v.vuoti,
        "abbinamenti": abbinamenti,
        "sigillo": "integro",
        "impegno": impegno,
        "lettura": lettura,
    }
    return fine(sessione, inizio, conteggio, registro, chiavi, catena, esito, email=email)


def fermata(esito_controllo, impegno: dict | None, lettura: dict | None) -> dict:
    """La staffetta si è fermata a una consegna o alla verifica della catena: il pagamento è bloccato."""
    del_sigillo = esito_controllo.controllo in CONTROLLI_DEL_SIGILLO
    livello = "sigillo" if del_sigillo else esito_controllo.controllo
    discordanze, vuoti = confronta(impegno, lettura) if impegno and lettura else ([], [])
    return {
        "esito": "bloccare",
        "motivi": [
            {
                "livello": livello,
                "esito": "bloccare",
                "codice": esito_controllo.controllo,
                "motivo": esito_controllo.motivo,
                "motivo_en": esito_controllo.motivo,
            }
        ],
        "proposta": None,
        "pagamento_proposto": None,
        "discordanze": [asdict(d) for d in discordanze],
        "discordanze_proposta": [],
        "vuoti": vuoti,
        "abbinamenti": {},
        "sigillo": f"rotto: {esito_controllo.motivo}" if del_sigillo else "integro",
        "impegno": impegno,
        "lettura": lettura,
    }


def esito_troncato(cosa: str, impegno: dict | None = None, lettura: dict | None = None) -> dict:
    """Il modello non ha finito il JSON entro il limite: non si paga, decide una persona."""
    motivo = f"{cosa}: risposta incompleta del modello"
    return {
        "esito": "persona",
        "motivi": [
            {
                "livello": "motore",
                "esito": "persona",
                "codice": "troncato",
                "motivo": motivo,
                "motivo_en": f"{cosa}: incomplete model answer",
            }
        ],
        "proposta": None,
        "pagamento_proposto": None,
        "discordanze": [],
        "discordanze_proposta": [],
        "vuoti": [],
        "abbinamenti": {},
        "sigillo": "integro",
        "impegno": impegno,
        "lettura": lettura,
    }


def fine(sessione, inizio, conteggio, registro, chiavi, catena, esito, *, email: dict | None = None) -> dict:
    risultato = {
        "id_caso": sessione,
        **esito,
        "email": email,
        "token": {"generati": conteggio.generati, "letti": conteggio.letti, "analisi": conteggio.analisi},
        "secondi": round(time.perf_counter() - inizio, 3),
    }
    if registro is not None:
        salva_registro(registro / sessione, catena, risultato, chiavi)
    return risultato


def salva_registro(cartella: Path, catena: list[MessaggioLatente], risultato: dict, chiavi: Chiavi) -> None:
    """Il registro del caso: messaggi firmati (etichette e stati), esito e chiavi pubbliche per verificarlo."""
    cartella.mkdir(parents=True, exist_ok=True)
    for messaggio in catena:
        messaggio.salva(cartella / f"{messaggio.etichetta['numero']:02d}-{messaggio.mittente}.safetensors")
    if (cartella / "chiavi-pubbliche").exists():
        shutil.rmtree(cartella / "chiavi-pubbliche")
    shutil.copytree(chiavi.cartella_pubbliche, cartella / "chiavi-pubbliche")
    (cartella / "caso.json").write_text(json.dumps(risultato, indent=1, ensure_ascii=False, default=str) + "\n")
