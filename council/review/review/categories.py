"""The categories the council judges, per benchmark, with an English description for the prompts and the Italian name
for the Italian pages.

Roles and readers come from `council/data/categories.py`. The keys are the `category` field of
`correct-answers.jsonl`, so the verdict is compared directly with the correct answer.
The CUAD descriptions follow the official category definitions, the ContractNLI ones quote the hypothesis.
"""

from __future__ import annotations

from dataclasses import dataclass

from .data import data_categories

_DATA = data_categories()
LEGAL, FINANCE, RISK = _DATA.LEGAL, _DATA.FINANCE, _DATA.RISK


@dataclass(frozen=True)
class Category:
    key: str
    # The name shown by the Italian pages; the English pages show the key.
    name_it: str
    role: str
    description: str


@dataclass(frozen=True)
class Benchmark:
    name: str
    family: str
    readers: tuple[str, ...]
    categories: tuple[Category, ...]
    # What "to flag" means on this benchmark.
    rule: str
    language: str

    def of_role(self, role: str) -> tuple[Category, ...]:
        return tuple(c for c in self.categories if c.role == role)


_CUAD = {
    "Uncapped Liability": (
        "Responsabilità illimitata",
        (
            "a party's liability for a breach has no cap, even for just one type of breach "
            "(for example intellectual property or confidentiality)"
        ),
    ),
    "Cap On Liability": (
        "Tetto alla responsabilità",
        (
            "there is a limit on liability for breach: a maximum amount, a time limit to bring a claim or "
            "the exclusion of certain damages"
        ),
    ),
    "Ip Ownership Assignment": (
        "Cessione della proprietà intellettuale",
        "intellectual property created by one party becomes the other's, by contract or when an event occurs",
    ),
    "Joint Ip Ownership": (
        "Proprietà intellettuale condivisa",
        "intellectual property is jointly owned or shared between the parties",
    ),
    "Irrevocable Or Perpetual License": (
        "Licenza irrevocabile o perpetua",
        "the contract grants an irrevocable or perpetual license",
    ),
    "Covenant Not To Sue": (
        "Rinuncia a fare causa",
        (
            "a party may not challenge the other's intellectual property or sue it over matters unrelated "
            "to the contract"
        ),
    ),
    "Non-Disparagement": ("Divieto di denigrazione", "a party may not speak ill of the other"),
    "Liquidated Damages": (
        "Penale predeterminata",
        "a party must pay an amount fixed in advance for a breach, or a fee to get out of the contract",
    ),
    "Minimum Commitment": (
        "Minimo d'acquisto",
        "a party must buy a minimum quantity or amount from the other within a certain period",
    ),
    "Volume Restriction": (
        "Limite di volume",
        "if the use of a product or service exceeds a threshold, the price goes up or consent is required",
    ),
    "Most Favored Nation": (
        "Cliente più favorito",
        "if a third party gets better terms for the same goods or service, the buyer is entitled to the same",
    ),
    "Change Of Control": (
        "Cambio di controllo",
        (
            "if a party changes ownership (merger, sale of shares or of the business) the other may terminate, "
            "or its consent or a notice is required"
        ),
    ),
    "Anti-Assignment": (
        "Divieto di cessione",
        "assigning the contract to a third party requires the other party's consent or a notice to it",
    ),
    "Rofr/Rofo/Rofn": (
        "Diritto di prelazione",
        "a party has a right of first offer, first refusal or first negotiation on goods, services or shares",
    ),
    "Termination For Convenience": (
        "Recesso senza motivo",
        "a party may terminate without cause, with just a notice",
    ),
    "Non-Compete": (
        "Non concorrenza",
        "a party may not compete with the other or operate in a territory, sector or technology",
    ),
    "Exclusivity": (
        "Esclusiva",
        (
            "there is an exclusive commitment: buying everything from one party, or not selling to or working with "
            "others, during or after the contract"
        ),
    ),
    "No-Solicit Of Customers": (
        "Divieto di sottrarre clienti",
        "a party may not solicit or deal with the other's customers or partners",
    ),
    "No-Solicit Of Employees": (
        "Divieto di assumere dipendenti",
        "a party may not solicit or hire the other's employees or contractors",
    ),
}

_CONTRACTNLI = {
    "nda-1": "All Confidential Information shall be expressly identified by the Disclosing Party.",
    "nda-2": "Confidential Information shall only include technical information.",
    "nda-3": "Confidential Information may include verbally conveyed information.",
    "nda-4": "Receiving Party shall not use any Confidential Information for any purpose other than the purposes "
    "stated in Agreement.",
    "nda-5": "Receiving Party may share some Confidential Information with some of Receiving Party's employees.",
    "nda-7": "Receiving Party may share some Confidential Information with some third-parties (including "
    "consultants, agents and professional advisors).",
    "nda-8": "Receiving Party shall notify Disclosing Party in case Receiving Party is required by law, regulation "
    "or judicial process to disclose any Confidential Information.",
    "nda-10": "Receiving Party shall not disclose the fact that Agreement was agreed or negotiated.",
    "nda-11": "Receiving Party shall not reverse engineer any objects which embody Disclosing Party's Confidential "
    "Information.",
    "nda-12": "Receiving Party may independently develop information similar to Confidential Information.",
    "nda-13": "Receiving Party may acquire information similar to Confidential Information from a third party.",
    "nda-15": "Agreement shall not grant Receiving Party any right to Confidential Information.",
    "nda-16": "Receiving Party shall destroy or return some Confidential Information upon the termination of "
    "Agreement.",
    "nda-17": "Receiving Party may create a copy of some Confidential Information in some circumstances.",
    "nda-18": "Receiving Party shall not solicit some of Disclosing Party's representatives.",
    "nda-19": "Some obligations of Agreement may survive termination of Agreement.",
    "nda-20": "Receiving Party may retain some Confidential Information even after the return or destruction of "
    "Confidential Information.",
}

_CLAUDETTE = {
    "ltd": "the provider excludes or limits its own liability for damage, losses or malfunctions",
    "a": "disputes go to arbitration instead of a court",
    "j": "disputes are heard by a court chosen by the provider, far from the consumer",
    "law": "a law other than that of the consumer's country applies",
    "use": "the consumer accepts the terms just by using the service",
    "pinc": "accepting the terms also means accepting the processing of personal data",
    "ch": "the provider may change the terms or the service whenever it wants",
    "ter": "the provider may suspend or close the service or the account whenever it wants",
    "cr": "the provider may remove the user's content",
}

_COMMERCIAL = tuple(
    Category(key, name_it, role, description)
    for key, role in _DATA.CUAD_CATEGORIES.items()
    for name_it, description in [_CUAD[key]]
)

BENCHMARK = {
    "cuad": Benchmark(
        "cuad",
        "commercial",
        tuple(_DATA.READERS["cuad"]),
        _COMMERCIAL,
        "true if the contract has a clause of this type, whichever party it concerns; false if it does not",
        "en",
    ),
    "contractnli": Benchmark(
        "contractnli",
        "nda",
        tuple(_DATA.READERS["contractnli"]),
        tuple(
            Category(description, description, role, f'hypothesis: "{_CONTRACTNLI[hypothesis]}"')
            for hypothesis, (description, role) in _DATA.CONTRACTNLI_HYPOTHESES.items()
        ),
        "true if the agreement says the opposite of the hypothesis; false if it confirms it or does not mention it",
        "en",
    ),
    "claudette": Benchmark(
        "claudette",
        "tos",
        tuple(_DATA.READERS["claudette"]),
        tuple(Category(name, name, role, _CLAUDETTE[tag]) for tag, (name, role) in _DATA.CLAUDETTE_CATEGORIES.items()),
        "true if there is a clause of this type that is potentially or clearly unfair to the consumer; false otherwise",
        "it",
    ),
}
# The demo set uses the 19 CUAD categories and the four roles.
BENCHMARK["demo"] = Benchmark(
    "demo", "commercial", BENCHMARK["cuad"].readers, _COMMERCIAL, BENCHMARK["cuad"].rule, "it"
)

ROLE_NAMES = {LEGAL: "legal", FINANCE: "finance", RISK: "risk"}
