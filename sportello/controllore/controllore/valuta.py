"""L'esito dello Sportello su una fattura: coerenza, tre testimoni, regole del catalogo e decisore.

- impegno ≠ lettura → bloccare; un dato critico vuoto → persona (livello "coerenza");
- proposta ≠ impegno o lettura su IBAN e importo → bloccare (livello "tre testimoni");
- le regole del catalogo con il loro esito (livello "regole");
- il decisore può solo chiedere una persona, mai pagare ciò che i controlli fermano né bloccare da solo;
- vince l'esito più grave.

`livello2=False` spegne coerenza e tre testimoni: esiste solo per la demo, nelle misure è sempre acceso.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fatture.regole import Scatto

from .coerenza import CAMPI_CRITICI, Campo, Discordanza, confronta, valore

GRAVITA = {"pagare": 0, "persona": 1, "bloccare": 2}
TESTIMONI = tuple(c for c in CAMPI_CRITICI if c.nome in ("pagamento.iban", "pagamento.importo"))
CAMPI = {c.nome: c for c in CAMPI_CRITICI}


@dataclass(frozen=True)
class Motivo:
    livello: str  # coerenza, tre testimoni, regole, decisore
    esito: str
    codice: str
    motivo: str
    motivo_en: str


@dataclass
class Valutazione:
    esito: str
    motivi: list[Motivo] = field(default_factory=list)
    discordanze: list[Discordanza] = field(default_factory=list)  # impegno contro lettura
    discordanze_proposta: list[Discordanza] = field(default_factory=list)  # proposta contro impegno e lettura
    vuoti: list[str] = field(default_factory=list)
    pagamento_proposto: dict | None = None


def mostra(campo: Campo, dato) -> str:
    """Come compare un dato nei motivi: l'IBAN sempre abbreviato, mai intero da copiare."""
    if campo.tipo == "iban":
        return f"{str(dato).replace(' ', '')[:4].upper()}…"
    return str(dato)


def motivi_coerenza(discordanze: list[Discordanza], vuoti: list[str]) -> list[Motivo]:
    motivi = []
    for d in discordanze:
        campo = CAMPI[d.campo]
        dichiarato, letto = mostra(campo, d.dichiarato), mostra(campo, d.letto)
        motivi.append(Motivo(
            "coerenza", "bloccare", d.campo,
            f"L'estrattore dichiara {campo.it} {dichiarato}, nella memoria c'è {letto}",
            f"The extractor declares {campo.en} {dichiarato}, but its memory holds {letto}",
        ))  # fmt: skip
    for nome in vuoti:
        campo = CAMPI[nome]
        motivi.append(Motivo(
            "coerenza", "persona", nome,
            f"{campo.it.capitalize()}: dato mancante, non si può verificare",
            f"{campo.en.capitalize()}: missing, it cannot be verified",
        ))  # fmt: skip
    return motivi


def tre_testimoni(impegno: dict, lettura: dict, proposta: dict) -> tuple[list[Discordanza], list[Motivo]]:
    """IBAN e importo della proposta contro impegno e lettura: tutti e tre devono coincidere."""
    proposta_annidata = {"pagamento": {"iban": proposta.get("iban"), "importo": proposta.get("importo")}}
    discordanze, motivi = [], []
    for fonte in (impegno, lettura):
        trovate, _ = confronta(fonte, proposta_annidata, TESTIMONI)
        discordanze += [d for d in trovate if d.campo not in {x.campo for x in discordanze}]
    for d in discordanze:
        campo = CAMPI[d.campo]
        proposto = mostra(campo, valore(proposta_annidata, campo.percorso))
        dichiarato, letto = (
            mostra(campo, valore(impegno, campo.percorso)),
            mostra(campo, valore(lettura, campo.percorso)),
        )
        motivi.append(Motivo(
            "tre testimoni", "bloccare", d.campo,
            f"La proposta di pagamento indica {campo.it} {proposto}: l'estrattore dichiara {dichiarato}, il verificatore legge {letto}",
            f"The payment proposal says {campo.en} {proposto}: the extractor declares {dichiarato}, the verifier reads {letto}",
        ))  # fmt: skip
    return discordanze, motivi


def valuta(
    impegno: dict, lettura: dict, proposta: dict, scatti_regole: list[Scatto], *, livello2: bool = True
) -> Valutazione:
    v = Valutazione("pagare")
    if livello2:
        v.discordanze, v.vuoti = confronta(impegno, lettura)
        v.motivi += motivi_coerenza(v.discordanze, v.vuoti)
        v.discordanze_proposta, motivi = tre_testimoni(impegno, lettura, proposta)
        v.motivi += motivi
    for s in scatti_regole:
        # Una riga che il modello non ha giudicato (A11) non si può pagare da sola: decide una persona.
        esito = "persona" if s.esito == "da_giudicare" else s.esito
        v.motivi.append(Motivo("regole", esito, s.codice, s.motivo, s.motivo_en))
    if proposta.get("esito", "pagare") != "pagare":
        testo = proposta.get("motivazione") or "Il decisore chiede una persona"
        v.motivi.append(Motivo("decisore", "persona", "decisore", testo, testo))
    v.esito = max((m.esito for m in v.motivi), key=GRAVITA.__getitem__, default="pagare")
    if v.esito == "pagare":
        v.pagamento_proposto = {"iban": proposta.get("iban"), "importo": proposta.get("importo")}
    return v
