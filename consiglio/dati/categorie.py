"""Categorie dei tre benchmark del set di misura e ruolo del Consiglio che le guarda.

CUAD viene dalla tabella di "Impostazione del Consiglio": legale 7, finanza 4, rischio 8.
ContractNLI e CLAUDETTE sono una PROPOSTA, da far rivedere a @portapulito prima di far girare quei
due benchmark. In entrambi nessuna categoria è finanziaria, quindi la finanza resta senza categorie:
vedi la nota nel README.
"""

LEGALE = "legale"
FINANZA = "finanza"
RISCHIO = "rischio"

# Nomi esatti delle domande di CUAD v1 (suffisso dell'id "<contratto>__<categoria>").
CUAD_CATEGORIE = {
    "Uncapped Liability": LEGALE,
    "Cap On Liability": LEGALE,
    "Ip Ownership Assignment": LEGALE,
    "Joint Ip Ownership": LEGALE,
    "Irrevocable Or Perpetual License": LEGALE,
    "Covenant Not To Sue": LEGALE,
    "Non-Disparagement": LEGALE,
    "Liquidated Damages": FINANZA,
    "Minimum Commitment": FINANZA,
    "Volume Restriction": FINANZA,
    "Most Favored Nation": FINANZA,
    "Change Of Control": RISCHIO,
    "Anti-Assignment": RISCHIO,
    "Rofr/Rofo/Rofn": RISCHIO,
    "Termination For Convenience": RISCHIO,
    "Non-Compete": RISCHIO,
    "Exclusivity": RISCHIO,
    "No-Solicit Of Customers": RISCHIO,
    "No-Solicit Of Employees": RISCHIO,
}

# PROPOSTA. Chiave: id dell'ipotesi in ContractNLI; valore: (descrizione breve ufficiale, ruolo).
CONTRACTNLI_IPOTESI = {
    "nda-1": ("Explicit identification", LEGALE),
    "nda-2": ("None-inclusion of non-technical information", LEGALE),
    "nda-3": ("Inclusion of verbally conveyed information", LEGALE),
    "nda-8": ("Notice on compelled disclosure", LEGALE),
    "nda-10": ("Confidentiality of Agreement", LEGALE),
    "nda-11": ("No reverse engineering", LEGALE),
    "nda-15": ("No licensing", LEGALE),
    "nda-17": ("Permissible copy", LEGALE),
    "nda-4": ("Limited use", RISCHIO),
    "nda-5": ("Sharing with employees", RISCHIO),
    "nda-7": ("Sharing with third-parties", RISCHIO),
    "nda-12": ("Permissible development of similar information", RISCHIO),
    "nda-13": ("Permissible acquirement of similar information", RISCHIO),
    "nda-16": ("Return of confidential information", RISCHIO),
    "nda-18": ("No solicitation", RISCHIO),
    "nda-19": ("Survival of obligations", RISCHIO),
    "nda-20": ("Permissible post-agreement possession", RISCHIO),
}

# PROPOSTA. Chiave: nome del tag nell'XML di CLAUDETTE (senza il grado); valore: (nome, ruolo).
CLAUDETTE_CATEGORIE = {
    "ltd": ("Limitazione di responsabilità", LEGALE),
    "a": ("Arbitrato", LEGALE),
    "j": ("Foro competente", LEGALE),
    "law": ("Legge applicabile", LEGALE),
    "use": ("Accettazione con il semplice uso", LEGALE),
    "pinc": ("Privacy inclusa nel contratto", LEGALE),
    "ch": ("Modifica unilaterale", RISCHIO),
    "ter": ("Recesso unilaterale", RISCHIO),
    "cr": ("Rimozione dei contenuti", RISCHIO),
}
