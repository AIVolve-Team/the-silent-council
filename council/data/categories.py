"""Categories of the three measurement-set benchmarks and the council role that reviews each of them.

CUAD comes from the table in "Council setup": legal 7, finance 4, risk 8.
ContractNLI and CLAUDETTE were decided in “Trial contracts and correct answers” (6/10/2026). None of their categories is financial, so on these two
benchmarks finance is not convened and the council has three members: legal, risk and the rapporteur.
"""

LEGAL = "legal"
FINANCE = "finance"
RISK = "risk"

# Who reads a section of the contract, in relay order. The rapporteur always closes the relay:
# it has no categories of its own and judges all of them.
READERS = {
    "cuad": (LEGAL, FINANCE, RISK),
    "contractnli": (LEGAL, RISK),
    "claudette": (LEGAL, RISK),
}

# Exact names of the CUAD v1 questions (suffix of the id "<contract>__<category>").
CUAD_CATEGORIES = {
    "Uncapped Liability": LEGAL,
    "Cap On Liability": LEGAL,
    "Ip Ownership Assignment": LEGAL,
    "Joint Ip Ownership": LEGAL,
    "Irrevocable Or Perpetual License": LEGAL,
    "Covenant Not To Sue": LEGAL,
    "Non-Disparagement": LEGAL,
    "Liquidated Damages": FINANCE,
    "Minimum Commitment": FINANCE,
    "Volume Restriction": FINANCE,
    "Most Favored Nation": FINANCE,
    "Change Of Control": RISK,
    "Anti-Assignment": RISK,
    "Rofr/Rofo/Rofn": RISK,
    "Termination For Convenience": RISK,
    "Non-Compete": RISK,
    "Exclusivity": RISK,
    "No-Solicit Of Customers": RISK,
    "No-Solicit Of Employees": RISK,
}

# Decided in “Trial contracts and correct answers”. Key: hypothesis id in ContractNLI; value: (official short description, role).
CONTRACTNLI_HYPOTHESES = {
    "nda-1": ("Explicit identification", LEGAL),
    "nda-2": ("None-inclusion of non-technical information", LEGAL),
    "nda-3": ("Inclusion of verbally conveyed information", LEGAL),
    "nda-8": ("Notice on compelled disclosure", LEGAL),
    "nda-10": ("Confidentiality of Agreement", LEGAL),
    "nda-11": ("No reverse engineering", LEGAL),
    "nda-15": ("No licensing", LEGAL),
    "nda-17": ("Permissible copy", LEGAL),
    "nda-4": ("Limited use", RISK),
    "nda-5": ("Sharing with employees", RISK),
    "nda-7": ("Sharing with third-parties", RISK),
    "nda-12": ("Permissible development of similar information", RISK),
    "nda-13": ("Permissible acquirement of similar information", RISK),
    "nda-16": ("Return of confidential information", RISK),
    "nda-18": ("No solicitation", RISK),
    "nda-19": ("Survival of obligations", RISK),
    "nda-20": ("Permissible post-agreement possession", RISK),
}

# Decided in “Trial contracts and correct answers”. Key: tag name in the CLAUDETTE XML (without the grade); value: (name, role). The name is the
# Italian one (CLAUDETTE's ToS are the Italian ones) and is also the `category` written in the correct answers.
CLAUDETTE_CATEGORIES = {
    "ltd": ("Limitazione di responsabilità", LEGAL),
    "a": ("Arbitrato", LEGAL),
    "j": ("Foro competente", LEGAL),
    "law": ("Legge applicabile", LEGAL),
    "use": ("Accettazione con il semplice uso", LEGAL),
    "pinc": ("Privacy inclusa nel contratto", LEGAL),
    "ch": ("Modifica unilaterale", RISK),
    "ter": ("Recesso unilaterale", RISK),
    "cr": ("Rimozione dei contenuti", RISK),
}
