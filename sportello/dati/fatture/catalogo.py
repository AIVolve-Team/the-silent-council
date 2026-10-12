"""I prodotti delle fatture di prova, in italiano e in inglese.

Ogni prodotto ha la descrizione dell'ordine e alcune varianti libere, come le scriverebbe un fornitore: le righe
con una variante e senza riferimento all'ordine le abbina il modello (A11).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prodotto:
    codice: str
    it: str
    varianti_it: tuple[str, ...]
    en: str
    varianti_en: tuple[str, ...]
    prezzo: tuple[float, float]
    aliquota: float
    canone: bool = False  # si fattura a rate mensili


PRODOTTI = (
    Prodotto(
        "CAR-A4",
        "Carta per fotocopie A4 80 g, risma da 500 fogli",
        ("Risme carta A4 80gr", "Carta A4 per stampanti (500 fogli)"),
        "A4 copy paper 80 gsm, ream of 500 sheets",
        ("A4 paper reams 80gsm", "Printer paper A4 (500 sheets)"),
        (3.5, 6.0),
        22,
    ),
    Prodotto(
        "TON-305",
        "Toner nero per stampante laser, modello 305",
        ("Cartuccia toner 305 nera", "Toner originale 305 black"),
        "Black laser toner, model 305",
        ("305 black toner cartridge", "Original toner 305, black"),
        (45.0, 70.0),
        22,
    ),
    Prodotto(
        "MON-24",
        "Monitor 24 pollici Full HD",
        ('Schermo LED 24" FHD', "Display 24 pollici 1920x1080"),
        "24-inch Full HD monitor",
        ('24" FHD LED display', "Monitor 24in 1920x1080"),
        (110.0, 160.0),
        22,
    ),
    Prodotto(
        "SED-ERG",
        "Sedia ergonomica da ufficio",
        ("Poltrona operativa ergonomica", "Seduta da ufficio con supporto lombare"),
        "Ergonomic office chair",
        ("Ergonomic task chair", "Office chair with lumbar support"),
        (140.0, 260.0),
        22,
    ),
    Prodotto(
        "CAV-HDMI",
        "Cavo HDMI 2 metri",
        ("Cavo HDMI 2m", "Cavetto HDMI da 2 metri"),
        "HDMI cable, 2 metres",
        ("2m HDMI lead", "HDMI cord 2 m"),
        (6.0, 12.0),
        22,
    ),
    Prodotto(
        "TAS-USB",
        "Tastiera USB layout italiano",
        ("Tastiera cablata USB (ITA)", "Tastiera USB italiana"),
        "USB keyboard, Italian layout",
        ("Wired USB keyboard (IT layout)", "Italian layout USB keyboard"),
        (14.0, 25.0),
        22,
    ),
    Prodotto(
        "MOU-WL",
        "Mouse wireless",
        ("Mouse senza fili", "Mouse ottico wireless"),
        "Wireless mouse",
        ("Cordless mouse", "Wireless optical mouse"),
        (9.0, 18.0),
        22,
    ),
    Prodotto(
        "CAF-1KG",
        "Caffè in grani 1 kg",
        ("Caffè in chicchi, confezione da 1 kg", "Grani di caffè 1kg"),
        "Coffee beans, 1 kg",
        ("Whole bean coffee 1kg", "Coffee beans 1 kg bag"),
        (14.0, 22.0),
        10,
    ),
    Prodotto(
        "ACQ-6X",
        "Acqua minerale naturale, confezione da 6 bottiglie",
        ("Acqua naturale 6x1,5 l", "Confezione acqua minerale (6 bottiglie)"),
        "Still mineral water, pack of 6 bottles",
        ("Still water 6x1.5L", "Mineral water 6-pack"),
        (2.5, 4.5),
        22,
    ),
    Prodotto(
        "DET-5L",
        "Detergente per pavimenti 5 litri",
        ("Detersivo pavimenti tanica 5 l", "Lavapavimenti 5L"),
        "Floor cleaner, 5 litres",
        ("Floor detergent 5L can", "5 l floor cleaning liquid"),
        (8.0, 15.0),
        22,
    ),
    Prodotto(
        "GUA-NIT",
        "Guanti in nitrile, scatola da 100",
        ("Guanti nitrile monouso (100 pz)", "Scatola guanti nitrile 100"),
        "Nitrile gloves, box of 100",
        ("Disposable nitrile gloves (100)", "Box of 100 nitrile gloves"),
        (6.0, 11.0),
        22,
    ),
    Prodotto(
        "LIB-MAN",
        "Manuale tecnico di manutenzione",
        ("Libro manuale manutenzione", "Manuale di manutenzione"),
        "Technical maintenance manual",
        ("Maintenance manual book", "Technical manual (volume)"),
        (25.0, 60.0),
        4,
    ),
    Prodotto(
        "ETI-100",
        "Etichette adesive, 100 fogli",
        ("Etichette autoadesive (100 fogli)", "Fogli etichette x100"),
        "Adhesive labels, 100 sheets",
        ("Self-adhesive labels (100 sheets)", "Label sheets x100"),
        (12.0, 20.0),
        22,
    ),
    Prodotto(
        "PAL-EU",
        "Pallet in legno EUR",
        ("Bancale EPAL in legno", "Pallet EPAL 120x80"),
        "EUR wooden pallet",
        ("EPAL wooden pallet", "Euro pallet 120x80"),
        (9.0, 16.0),
        22,
    ),
    Prodotto(
        "NAS-48",
        "Nastro adesivo da imballo 48 mm",
        ("Scotch imballo 48mm", "Nastro per pacchi 48 mm"),
        "Packing tape, 48 mm",
        ("48mm packaging tape", "Parcel tape 48 mm"),
        (1.5, 3.5),
        22,
    ),
    Prodotto(
        "SCA-60",
        "Scatola di cartone 60x40x40",
        ("Scatoloni 60x40x40", "Cartone da imballo 60x40x40 cm"),
        "Cardboard box 60x40x40",
        ("60x40x40 shipping box", "Corrugated box 60x40x40 cm"),
        (1.2, 2.8),
        22,
    ),
    Prodotto(
        "MAN-ORE",
        "Ore di manutenzione impianto",
        ("Intervento tecnico (ore)", "Manutenzione impianto, ore"),
        "Plant maintenance hours",
        ("Technical service (hours)", "Maintenance labour hours"),
        (35.0, 60.0),
        22,
    ),
    Prodotto(
        "LIC-SW",
        "Licenza software annuale per utente",
        ("Abbonamento software annuo (utente)", "Licenza annua per postazione"),
        "Annual software licence per user",
        ("Yearly software subscription (per user)", "Annual seat licence"),
        (80.0, 240.0),
        22,
    ),
    Prodotto(
        "NOL-STA",
        "Canone mensile noleggio stampante",
        ("Noleggio stampante, rata mensile", "Canone noleggio multifunzione"),
        "Monthly printer rental fee",
        ("Printer rental, monthly instalment", "Monthly MFP lease fee"),
        (60.0, 140.0),
        22,
        canone=True,
    ),
    Prodotto(
        "CLO-MES",
        "Canone mensile servizio cloud",
        ("Servizio cloud, canone del mese", "Abbonamento cloud mensile"),
        "Monthly cloud service fee",
        ("Cloud service, monthly fee", "Monthly cloud subscription"),
        (90.0, 400.0),
        22,
        canone=True,
    ),
    Prodotto(
        "VIG-MES",
        "Canone mensile vigilanza",
        ("Servizio di vigilanza, rata mensile", "Vigilanza notturna (mese)"),
        "Monthly security service fee",
        ("Security service, monthly instalment", "Night watch service (month)"),
        (150.0, 380.0),
        22,
        canone=True,
    ),
)

# Voci che nessun ordine prevede: le righe di A11.
EXTRA = (
    ("Spese di trasporto urgente", "Express shipping costs"),
    ("Contributo ambientale", "Environmental fee"),
    ("Servizio di installazione", "Installation service"),
    ("Diritti di gestione pratica", "Handling fee"),
    ("Consulenza tecnica aggiuntiva", "Additional technical consulting"),
)

PRODOTTI_A_PEZZI = tuple(p for p in PRODOTTI if not p.canone)
CANONI = tuple(p for p in PRODOTTI if p.canone)
