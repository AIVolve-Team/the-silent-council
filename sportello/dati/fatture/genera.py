"""Il generatore delle fatture di prova: sviluppo (seme 101) ed esame (seme 102).

La composizione è quella di "Catalogo delle anomalie" e di "Eval pre-registrato": ogni fattura ha al
più un'anomalia, e la sua verità (l'impegno giusto, l'anomalia, l'esito atteso) nasce insieme alla fattura.
"""

from __future__ import annotations

import copy
import random
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal

from faker import Faker

from .archivi import Archivi, Fornitore, Ordine, RigaOrdine, VoceStorico
from .catalogo import CANONI, EXTRA, PRODOTTI_A_PEZZI, Prodotto
from .normalizza import CENTESIMO, id_fiscale, importo

ANOMALIE = ("A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08", "A09a", "A09b", "A10", "A11", "A12", "A13")
ESITI = {
    "A01": "bloccare", "A02": "persona", "A03": "bloccare", "A04": "persona", "A05": "bloccare",
    "A06": "bloccare", "A07": "persona", "A08": "bloccare", "A09a": "persona", "A09b": "bloccare",
    "A10": "bloccare", "A11": "persona", "A12": "persona", "A13": "bloccare",
}  # fmt: skip
AL_LIMITE = ("prezzo", "canone", "numero")


@dataclass(frozen=True)
class Composizione:
    seme: int
    per_variante: int
    pulite: int
    al_limite: int


COMPOSIZIONI = {
    "sviluppo": Composizione(seme=101, per_variante=3, pulite=58, al_limite=15),
    "esame": Composizione(seme=102, per_variante=6, pulite=116, al_limite=30),
}
QUOTA_ITALIANO = 0.7
INIZIO = date(2026, 9, 1)  # le fatture arrivano fra il 1/9 e il 5/10/2026

# Fornitori esteri: scrivono in inglese e fatturano senza IVA (inversione contabile, art. 196 della direttiva IVA).
ESTERI = {"IE": ("en_IE", 23), "DE": ("de_DE", 19), "NL": ("nl_NL", 21), "FR": ("fr_FR", 20), "ES": ("es_ES", 21)}
STILI_NUMERO = {
    "it": ("FT/{n:04d}/2026", "{n}/2026", "2026/FE/{n:03d}", "FT {n}-2026"),
    "en": ("INV-2026-{n:04d}", "2026-{n:04d}", "INV/{n}/2026"),
}
CAMBIO_ALIQUOTA = {22: 10, 10: 22, 4: 10}


@dataclass
class Caso:
    id: str
    lingua: str
    anomalia: str | None
    al_limite: str | None
    esito_atteso: str
    impegno: dict  # la verità: ciò che un estrattore perfetto dichiarerebbe
    abbinamenti: dict[int, int | None]  # righe senza num_item → riga dell'ordine, None se non c'è (A11)
    intestazione: dict  # fornitore e cliente come stampati nel PDF
    email: dict


@dataclass
class Insieme:
    nome: str
    seme: int
    casi: list[Caso]
    archivi: Archivi
    cliente: dict = field(default_factory=dict)


@dataclass
class Emittente:
    """Un fornitore con quello che serve a stampare le sue fatture."""

    anagrafica: Fornitore
    lingua: str
    indirizzo: str
    stile: str
    contatore: int
    iva_estera: int | None = None

    def numero(self) -> str:
        self.contatore += 1
        return self.stile.format(n=self.contatore)


def numero_alternativo(numero: str) -> str:
    """Lo stesso numero scritto in un altro modo: `FT/0012/2026` → `FT-00012-2026` (uguali per A01)."""
    pezzi = re.findall(r"[A-Za-z]+|\d+", numero)
    return "-".join(p.upper() if p.isalpha() else p.zfill(5) if len(p) < 5 else p for p in pezzi)


def euro(valore) -> float:
    return float(importo(valore))


class Generatore:
    def __init__(self, nome: str) -> None:
        self.nome = nome
        self.composizione = COMPOSIZIONI[nome]
        self.rng = random.Random(self.composizione.seme)
        self.faker = {}
        for locale in ["it_IT", *(locale for locale, _ in ESTERI.values())]:
            self.faker[locale] = Faker(locale)
            self.faker[locale].seed_instance(self.composizione.seme)
        self.archivi = Archivi()
        self.ordini_emessi = 0
        it = self.faker["it_IT"]
        self.cliente = {
            "denominazione": it.company(),
            "piva": id_fiscale(it.company_vat()),
            "indirizzo": it.address().replace("\n", ", "),
        }

    # --- fornitori -------------------------------------------------------------------------------------

    def emittente(self, lingua: str, *, in_anagrafica: bool = True, attivo: bool = True) -> Emittente:
        if lingua == "it":
            fk, paese, iva = self.faker["it_IT"], "IT", None
            identificativo = id_fiscale(fk.company_vat())
        else:
            paese = self.rng.choice(sorted(ESTERI))
            locale, iva = ESTERI[paese]
            fk = self.faker[locale]
            identificativo = self.id_estero(paese)
        fornitore = Fornitore(
            identificativo, fk.company(), fk.iban(), attivo=attivo, telefono=fk.phone_number(),
            email=fk.company_email(), paese=paese,
        )  # fmt: skip
        if in_anagrafica:
            self.archivi.anagrafica[fornitore.id_fiscale] = fornitore
        stile = self.rng.choice(STILI_NUMERO[lingua])
        indirizzo = fk.address().replace("\n", ", ")
        return Emittente(fornitore, lingua, indirizzo, stile, self.rng.randint(5, 300), iva)

    def id_estero(self, paese: str) -> str:
        cifre = lambda n: "".join(str(self.rng.randint(0, 9)) for _ in range(n))
        lettera = lambda: self.rng.choice("ABCDEFGHJKLMNPQRSTVWXYZ")
        return {
            "IE": f"IE{cifre(7)}{lettera()}", "DE": f"DE{cifre(9)}", "NL": f"NL{cifre(9)}B01",
            "FR": f"FR{cifre(11)}", "ES": f"ES{lettera()}{cifre(7)}{lettera()}",
        }[paese]  # fmt: skip

    # --- ordini e fatture ------------------------------------------------------------------------------

    def ordine(self, emittente: Emittente, giorno: date, prodotti: list[Prodotto], *, rate: int = 1) -> Ordine:
        self.ordini_emessi += 1
        righe = []
        for n, prodotto in enumerate(prodotti, start=1):
            if prodotto.canone:
                quantita = rate
            elif prodotto.codice in ("MAN-ORE", "LIC-SW"):
                quantita = self.rng.randint(1, 10)
            else:
                quantita = self.rng.randint(1, 40)
            prezzo = euro(self.rng.uniform(*prodotto.prezzo))
            aliquota = 0 if emittente.iva_estera is not None else prodotto.aliquota
            descrizione = prodotto.it if emittente.lingua == "it" else prodotto.en
            righe.append(RigaOrdine(n, prodotto.codice, descrizione, quantita, prezzo, aliquota, quantita))
        data_ordine = (giorno - timedelta(days=self.rng.randint(10, 60))).isoformat()
        ordine = Ordine(f"PO-2026-{self.ordini_emessi:04d}", emittente.anagrafica.id_fiscale, data_ordine, righe, rate)
        self.archivi.ordini[ordine.numero] = ordine
        return ordine

    def prodotti(self, *, lunga: bool) -> list[Prodotto]:
        quanti = self.rng.randint(8, 12) if lunga else self.rng.randint(1, 5)
        return self.rng.sample(PRODOTTI_A_PEZZI, quanti)

    def fattura(
        self, emittente: Emittente, ordine: Ordine, giorno: date, quantita: dict[int, float]
    ) -> tuple[dict, dict]:
        """L'impegno di una fattura sull'ordine, una riga per riga d'ordine. Circa una riga su quattro ha una
        descrizione libera e nessun riferimento: la abbina il modello (A11)."""
        righe, abbinamenti = [], {}
        for voce in ordine.righe:
            prodotto = next(p for p in (*PRODOTTI_A_PEZZI, *CANONI) if p.codice == voce.codice)
            libera = self.rng.random() < 0.25
            if libera:
                varianti = prodotto.varianti_it if emittente.lingua == "it" else prodotto.varianti_en
                abbinamenti[voce.n] = voce.n
            riga = {
                "n": voce.n,
                "num_item": None if libera else str(voce.n),
                "codice": None if libera else voce.codice,
                "descrizione": self.rng.choice(varianti) if libera else voce.descrizione,
                "quantita": quantita[voce.n],
                "prezzo_unitario": voce.prezzo_unitario,
                "prezzo_totale": 0.0,
                "aliquota": voce.aliquota,
            }
            righe.append(riga)
        scadenza = giorno + timedelta(days=self.rng.choice([30, 60]))
        impegno = {
            "fornitore": {
                "id_fiscale": emittente.anagrafica.id_fiscale, "denominazione": emittente.anagrafica.denominazione,
            },
            "cliente_piva": self.cliente["piva"],
            "documento": {"tipo": "TD01", "numero": emittente.numero(), "data": giorno.isoformat(), "divisa": "EUR"},
            "ordine": {"numero": ordine.numero},
            "righe": righe,
            "riepilogo": [],
            "totale_documento": 0.0,
            "pagamento": {
                "modalita": "MP05", "iban": emittente.anagrafica.iban, "beneficiario": None,
                "scadenza": scadenza.isoformat(), "importo": 0.0,
            },
        }  # fmt: skip
        ricalcola(impegno)
        return impegno, abbinamenti

    # --- un caso ---------------------------------------------------------------------------------------

    def caso(self, numero: int, lingua: str, tipo: str, variante: str | None, emittenti: dict[str, list]) -> Caso:
        anomalia = variante if tipo == "anomalia" else None
        al_limite = variante if tipo == "limite" else None
        giorno = INIZIO + timedelta(days=self.rng.randint(0, 34))
        if anomalia == "A05":
            emittente = self.emittente(lingua, in_anagrafica=False)
        elif anomalia == "A06":
            emittente = self.emittente(lingua, attivo=False)
        else:
            emittente = self.rng.choice(emittenti[lingua])
        intestazione = {
            "fornitore": {
                "denominazione": emittente.anagrafica.denominazione, "indirizzo": emittente.indirizzo,
                "id_fiscale": emittente.anagrafica.id_fiscale, "telefono": emittente.anagrafica.telefono,
                "email": emittente.anagrafica.email, "paese": emittente.anagrafica.paese,
            },
            "cliente": self.cliente,
        }  # fmt: skip

        if al_limite == "canone":
            impegno, abbinamenti = self.canone(emittente, giorno)
        else:
            impegno, abbinamenti = self.normale(emittente, giorno, anomalia, lunga=self.rng.random() < 0.1)
        if al_limite == "prezzo":
            self.prezzo_al_limite(impegno)
        elif al_limite == "numero":
            self.numero_simile(emittente, impegno, giorno)
        if anomalia:
            self.inserisci(anomalia, emittente, impegno, abbinamenti, giorno, intestazione)

        oggetto = (
            f"Fattura n. {impegno['documento']['numero']}"
            if lingua == "it"
            else f"Invoice {impegno['documento']['numero']}"
        )
        email = {
            "mittente": emittente.anagrafica.email, "oggetto": oggetto,
            "data": (giorno + timedelta(days=1)).isoformat(), "allegato": f"{self.nome}-{numero:04d}.pdf",
        }  # fmt: skip
        esito = ESITI[anomalia] if anomalia else "pagare"
        return Caso(
            f"{self.nome}-{numero:04d}", lingua, anomalia, al_limite, esito, impegno, abbinamenti, intestazione, email
        )

    def normale(self, emittente: Emittente, giorno: date, anomalia: str | None, *, lunga: bool):
        prodotti = self.prodotti(lunga=lunga)
        ordine = self.ordine(emittente, giorno, prodotti)
        quantita = {r.n: r.quantita for r in ordine.righe}
        if anomalia in ("A01", "A02"):
            # La prima fattura ha già consumato metà dell'ordine: il duplicato sta nel residuo, così scatta solo A01/A02.
            for r in ordine.righe:
                r.quantita, r.residuo = 2 * r.quantita, r.quantita
        return self.fattura(emittente, ordine, giorno, quantita)

    def canone(self, emittente: Emittente, giorno: date):
        """Una rata di un canone: lo storico ha le rate precedenti, con lo stesso importo, una ogni mese."""
        prodotto = self.rng.choice(CANONI)
        ordine = self.ordine(emittente, giorno, [prodotto], rate=12)
        passate = self.rng.randint(1, 10)
        ordine.righe[0].residuo = 12 - passate
        impegno, abbinamenti = self.fattura(emittente, ordine, giorno, {1: 1})
        for mese in range(1, passate + 1):
            self.archivi.storico.append(VoceStorico(
                emittente.anagrafica.id_fiscale, emittente.numero(), (giorno - timedelta(days=30 * mese)).isoformat(),
                impegno["totale_documento"], ordine.numero,
            ))  # fmt: skip
        return impegno, abbinamenti

    def prezzo_al_limite(self, impegno: dict) -> None:
        """Un prezzo sopra l'ordine, ma entro il 2%: si paga."""
        riga = self.rng.choice(impegno["righe"])
        originale = importo(riga["prezzo_unitario"])
        massimo = (originale * Decimal("1.02")).quantize(CENTESIMO, rounding=ROUND_DOWN)
        prezzo = importo(originale * Decimal(str(1 + self.rng.uniform(0.004, 0.02))))
        riga["prezzo_unitario"] = float(min(max(prezzo, originale + CENTESIMO), massimo))
        ricalcola(impegno)

    def numero_simile(self, emittente: Emittente, impegno: dict, giorno: date) -> None:
        """Nello storico una fattura dello stesso fornitore con un numero simile, ma di un altro ordine e importo."""
        numero = impegno["documento"]["numero"]
        cifre = re.findall(r"\d+", numero)
        simile = (
            numero.replace(cifre[0], cifre[0][::-1], 1)
            if cifre[0][::-1] != cifre[0]
            else numero.replace(cifre[0], str(int(cifre[0]) + 7), 1)
        )
        altro = euro(importo(impegno["totale_documento"]) + Decimal(self.rng.randint(15, 400)))
        self.archivi.storico.append(VoceStorico(
            emittente.anagrafica.id_fiscale, simile, (giorno - timedelta(days=self.rng.randint(40, 200))).isoformat(),
            altro, f"PO-2025-{self.rng.randint(1, 999):04d}",
        ))  # fmt: skip

    # --- le anomalie del catalogo ----------------------------------------------------------------------

    def inserisci(self, anomalia, emittente, impegno, abbinamenti, giorno, intestazione) -> None:
        fornitore = emittente.anagrafica
        righe = impegno["righe"]
        riga = self.rng.choice(righe)
        if anomalia == "A01":
            precedente = giorno - timedelta(days=self.rng.randint(5, 60))
            self.archivi.storico.append(VoceStorico(
                fornitore.id_fiscale, numero_alternativo(impegno["documento"]["numero"]), precedente.isoformat(),
                impegno["totale_documento"], impegno["ordine"]["numero"],
            ))  # fmt: skip
        elif anomalia == "A02":
            self.archivi.storico.append(VoceStorico(
                fornitore.id_fiscale, emittente.numero(), (giorno - timedelta(days=self.rng.randint(3, 25))).isoformat(),
                impegno["totale_documento"], impegno["ordine"]["numero"],
            ))  # fmt: skip
        elif anomalia == "A03":
            fk = self.faker["it_IT"] if emittente.lingua == "it" else self.faker[ESTERI[fornitore.paese][0]]
            while impegno["pagamento"]["iban"] == fornitore.iban:
                impegno["pagamento"]["iban"] = fk.iban()
            # Chi cambia l'IBAN cambia anche il telefono stampato: la verifica si fa con quello in anagrafica.
            intestazione["fornitore"] = {**intestazione["fornitore"], "telefono": fk.phone_number()}
        elif anomalia == "A05":
            # Il fornitore non esiste per noi, quindi neanche il suo ordine: il numero stampato è inventato.
            del self.archivi.ordini[impegno["ordine"]["numero"]]
        elif anomalia == "A04":
            fk = self.faker["it_IT"] if emittente.lingua == "it" else self.faker[ESTERI[fornitore.paese][0]]
            impegno["pagamento"]["beneficiario"] = fk.name()
        elif anomalia == "A07":
            impegno["ordine"]["numero"] = None
        elif anomalia == "A08":
            if self.rng.random() < 0.5:
                impegno["ordine"]["numero"] = f"PO-2026-{self.rng.randint(5000, 9999):04d}"
            else:
                altro = self.emittente(emittente.lingua)
                impegno["ordine"]["numero"] = self.ordine(altro, giorno, self.prodotti(lunga=False)).numero
        elif anomalia == "A09a":
            riga["prezzo_unitario"] = self.prezzo_sopra(riga["prezzo_unitario"], 0.03, 0.09)
        elif anomalia == "A09b":
            riga["prezzo_unitario"] = self.prezzo_sopra(riga["prezzo_unitario"], 0.12, 0.35)
        elif anomalia == "A10":
            riga["quantita"] = riga["quantita"] + self.rng.randint(1, 5)
        elif anomalia == "A11":
            it, en = self.rng.choice(EXTRA)
            n = len(righe) + 1
            aliquota = 0 if emittente.iva_estera is not None else 22
            righe.append({
                "n": n, "num_item": None, "codice": None, "descrizione": it if emittente.lingua == "it" else en,
                "quantita": 1, "prezzo_unitario": euro(self.rng.uniform(20, 150)), "prezzo_totale": 0.0,
                "aliquota": aliquota,
            })  # fmt: skip
            abbinamenti[n] = None
        elif anomalia == "A12":
            nuova = emittente.iva_estera if emittente.iva_estera is not None else CAMBIO_ALIQUOTA[int(riga["aliquota"])]
            riga["aliquota"] = nuova
        if anomalia != "A13":
            ricalcola(impegno)
        else:
            totale = euro(importo(impegno["totale_documento"]) + Decimal(str(round(self.rng.uniform(1, 50), 2))))
            impegno["totale_documento"] = impegno["pagamento"]["importo"] = totale

    def prezzo_sopra(self, prezzo: float, minimo: float, massimo: float) -> float:
        originale = importo(prezzo)
        while True:
            nuovo = importo(originale * Decimal(str(1 + self.rng.uniform(minimo, massimo))))
            aumento = (nuovo - originale) / originale
            if Decimal(str(minimo)) - Decimal("0.005") < aumento <= Decimal(str(massimo)) + Decimal("0.005"):
                return float(nuovo)

    # --- l'insieme -------------------------------------------------------------------------------------

    def insieme(self) -> Insieme:
        c = self.composizione
        tipi = [("anomalia", a) for a in ANOMALIE for _ in range(c.per_variante)]
        tipi += [("limite", t) for t in AL_LIMITE for _ in range(c.al_limite // len(AL_LIMITE))]
        tipi += [("pulita", None)] * (c.pulite - c.al_limite)
        self.rng.shuffle(tipi)
        n_it = round(len(tipi) * QUOTA_ITALIANO)
        lingue = ["it"] * n_it + ["en"] * (len(tipi) - n_it)
        self.rng.shuffle(lingue)
        emittenti = {
            "it": [self.emittente("it") for _ in range(max(8, n_it // 4))],
            "en": [self.emittente("en") for _ in range(max(4, (len(tipi) - n_it) // 4))],
        }
        casi = [
            self.caso(i, lingua, tipo, variante, emittenti)
            for i, (lingua, (tipo, variante)) in enumerate(zip(lingue, tipi, strict=True), start=1)
        ]
        return Insieme(self.nome, c.seme, casi, self.archivi, self.cliente)


def ricalcola(impegno: dict) -> None:
    """Totali di riga, riepilogo IVA, totale e importo da pagare, come li stamperebbe un gestionale."""
    per_aliquota: dict[float, Decimal] = {}
    for riga in impegno["righe"]:
        totale_riga = importo(Decimal(str(riga["quantita"])) * importo(riga["prezzo_unitario"]))
        riga["prezzo_totale"] = float(totale_riga)
        per_aliquota[riga["aliquota"]] = per_aliquota.get(riga["aliquota"], Decimal(0)) + totale_riga
    impegno["riepilogo"] = [
        {"aliquota": a, "imponibile": float(imponibile), "imposta": float(importo(imponibile * Decimal(str(a)) / 100))}
        for a, imponibile in sorted(per_aliquota.items())
    ]
    totale = sum((importo(r["imponibile"]) + importo(r["imposta"]) for r in impegno["riepilogo"]), Decimal(0))
    impegno["totale_documento"] = impegno["pagamento"]["importo"] = float(totale)


def genera_insieme(nome: str) -> Insieme:
    return Generatore(nome).insieme()


def con_iban(caso: Caso, nuovo_iban: str) -> Caso:
    """La stessa fattura con l'IBAN dell'attaccante: la metà "attaccante" delle coppie di F3."""
    copia = copy.deepcopy(caso)
    copia.impegno["pagamento"]["iban"] = nuovo_iban
    return copia
