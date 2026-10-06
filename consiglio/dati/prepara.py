"""Prepara il set di misura del Consiglio.

Scarica CUAD, ContractNLI e i ToS italiani di CLAUDETTE dalle fonti ufficiali, conta i token Qwen3 di ogni
contratto, estrae il campione con seme fisso tra i contratti sotto il tetto e scrive le risposte giuste:
per ogni coppia (contratto, categoria), se va segnalata sì o no, con i pezzi di testo che lo provano.

Decisioni: "Benchmark e contratti di prova", "Impostazione del Consiglio".
"""

import argparse
import csv
import hashlib
import json
import random
import re
import statistics
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from categorie import CLAUDETTE_CATEGORIE, CONTRACTNLI_IPOTESI, CUAD_CATEGORIE

QUI = Path(__file__).resolve().parent
CACHE = QUI / "cache"

SEME = 60
TETTO = 24_000
N_SVILUPPO = 5
N_TEST = 20

# nome: (file nella cache, url, sha256 del file)
FONTI = {
    "cuad": (
        "cuad.zip",
        "https://github.com/TheAtticusProject/cuad/raw/67faa0e6023b04fcaae6cc09497ab00e5d63a2a2/data.zip",
        "f8161d18bea4e9c05e78fa6dda61c19c846fb8087ea969c172753bc2f45b999a",
    ),
    "contractnli": (
        "contractnli.zip",
        "https://stanfordnlp.github.io/contract-nli/resources/contract-nli.zip",
        "e03fc77bbf8b53e2976a250e81d8a294bc3d5e5fb014521e477dee9340d6287b",
    ),
    # L'archivio di GitHub non ha un hash stabile: si verifica il contenuto dei file italiani (CLAUDETTE_SHA256).
    "claudette": (
        "claudette.tar.gz",
        (
            "https://codeload.github.com/lt-nlp-lab-unibo/Multilingual-Unfair-Clause-Detection/tar.gz/"
            "04d9878bfca0e1e17e7dd1cf7bd17fc4ce5fcd12"
        ),
        None,
    ),
    "tokenizer": (
        "qwen3-tokenizer.json",
        "https://huggingface.co/Qwen/Qwen3-14B/resolve/40c069824f4251a91eefaf281ebe4c544efd3e18/tokenizer.json",
        "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4",
    ),
}
CLAUDETTE_SHA256 = "21e62635064832320843e6a067fb38a55ec47f3f935c406fe2b4c613a774a173"

# Due errori di annotazione nei ToS italiani, corretti come nella versione inglese degli stessi ToS.
# (ToS, testo originale, testo corretto): il testo originale deve comparire una volta sola.
CORREZIONI_CLAUDETTE = [
    ("Weebly", "le vostre informazioni finanziarie.</ter2>", "le vostre informazioni finanziarie.</ch2>"),
    ("Yelp", "legalmente perseguibile.</ter3></ch3>", "legalmente perseguibile.</ter3></ch2>"),
]

TAG_CLAUDETTE = re.compile(r"<(/?)(" + "|".join(CLAUDETTE_CATEGORIE) + r")([123])>")
TAG_IGNORATI = re.compile(r"</?countryM>")


def sha256(dati: bytes) -> str:
    return hashlib.sha256(dati).hexdigest()


def scarica(nome: str) -> Path:
    file, url, atteso = FONTI[nome]
    percorso = CACHE / file
    if not percorso.exists():
        CACHE.mkdir(exist_ok=True)
        print(f"Scarico {nome} da {url}")
        with urllib.request.urlopen(url) as risposta:
            percorso.write_bytes(risposta.read())
    if atteso is not None and sha256(percorso.read_bytes()) != atteso:
        raise SystemExit(
            f"{percorso.name}: l'hash non corrisponde a quello fissato. La fonte è cambiata: "
            "controllare cosa è cambiato prima di aggiornare l'hash in FONTI."
        )
    return percorso


# --- CUAD -----------------------------------------------------------------------------------------------


def risposte_cuad(qas: list[dict]) -> dict[str, list[str]]:
    """Per ognuna delle 19 categorie, i pezzi di testo annotati (lista vuota se la categoria non c'è)."""
    risposte = {categoria: [] for categoria in CUAD_CATEGORIE}
    for qa in qas:
        categoria = qa["id"].rsplit("__", 1)[1]
        if categoria in risposte:
            assert not risposte[categoria], f"categoria ripetuta: {qa['id']}"
            for risposta in qa["answers"]:
                if risposta["text"] not in risposte[categoria]:
                    risposte[categoria].append(risposta["text"])
    return risposte


def leggi_cuad(archivio: Path) -> dict[str, list[dict]]:
    """Testi e risposte da CUADv1.json, una domanda per categoria. I file dello split ufficiale servono solo a
    sapere in quale insieme sta ogni contratto: in train_separate_questions.json gli id hanno un suffisso
    "_<n>" per ogni risposta e non vanno letti come categorie."""
    with zipfile.ZipFile(archivio) as z:
        tutti = {d["title"]: d for d in json.loads(z.read("CUADv1.json"))["data"]}
        split = {
            "train": [d["title"] for d in json.loads(z.read("train_separate_questions.json"))["data"]],
            "test": [d["title"] for d in json.loads(z.read("test.json"))["data"]],
        }
    assert sorted(split["train"] + split["test"]) == sorted(tutti), "lo split di CUAD non copre i 510 contratti"
    contratti = {}
    for insieme, titoli in split.items():
        contratti[insieme] = []
        for titolo in titoli:
            (paragrafo,) = tutti[titolo]["paragraphs"]
            contratti[insieme].append(
                {"id": titolo, "testo": paragrafo["context"], "risposte": risposte_cuad(paragrafo["qas"])}
            )
    return contratti


# --- ContractNLI ----------------------------------------------------------------------------------------


def risposte_contractnli(documento: dict) -> dict[str, tuple[str, list[str]]]:
    """Per ogni ipotesi, l'etichetta originale e i pezzi di testo dell'evidenza."""
    (annotazioni,) = documento["annotation_sets"]
    risposte = {}
    for ipotesi, annotazione in annotazioni["annotations"].items():
        pezzi = [
            documento["text"][inizio:fine] for inizio, fine in (documento["spans"][i] for i in annotazione["spans"])
        ]
        risposte[ipotesi] = (annotazione["choice"], pezzi)
    return risposte


def leggi_contractnli(archivio: Path) -> dict[str, list[dict]]:
    contratti = {}
    with zipfile.ZipFile(archivio) as z:
        for insieme in ("train", "test"):
            dati = json.loads(z.read(f"contract-nli/{insieme}.json"))
            assert {k: v["short_description"] for k, v in dati["labels"].items()} == {
                k: v[0] for k, v in CONTRACTNLI_IPOTESI.items()
            }, "le ipotesi di ContractNLI non corrispondono a categorie.py"
            contratti[insieme] = [
                {"id": d["file_name"], "testo": d["text"], "risposte": risposte_contractnli(d)}
                for d in dati["documents"]
            ]
    return contratti


# --- CLAUDETTE ------------------------------------------------------------------------------------------


def estrai_clausole(xml: str) -> list[tuple[str, int, str]]:
    """Le clausole marcate in un ToS di CLAUDETTE, come (categoria, grado, testo senza tag).

    I tag di categoria possono annidarsi (una frase con due categorie). Il testo che contiene "<a>" senza grado
    è HTML citato nel ToS, non un tag, e resta nel testo.
    """
    xml = TAG_IGNORATI.sub("", xml)
    piano, aperti, clausole, ultimo = [], [], [], 0
    lunghezza = 0
    for tag in TAG_CLAUDETTE.finditer(xml):
        pezzo = xml[ultimo : tag.start()]
        piano.append(pezzo)
        lunghezza += len(pezzo)
        ultimo = tag.end()
        chiusura, categoria, grado = tag.group(1) == "/", tag.group(2), int(tag.group(3))
        if not chiusura:
            aperti.append((categoria, grado, lunghezza))
            continue
        for i in range(len(aperti) - 1, -1, -1):
            if aperti[i][:2] == (categoria, grado):
                _, _, inizio = aperti.pop(i)
                clausole.append((categoria, grado, inizio, lunghezza))
                break
        else:
            raise ValueError(f"tag di chiusura senza apertura: {tag.group(0)}")
    if aperti:
        raise ValueError(f"tag non chiusi: {aperti}")
    piano.append(xml[ultimo:])
    testo = "".join(piano)
    return [(categoria, grado, testo[inizio:fine].strip()) for categoria, grado, inizio, fine in clausole]


def risposte_claudette(xml: str) -> dict[str, list[tuple[int, str]]]:
    risposte = {categoria: [] for categoria in CLAUDETTE_CATEGORIE}
    for categoria, grado, testo in estrai_clausole(xml):
        risposte[categoria].append((grado, testo))
    return risposte


def leggi_claudette(archivio: Path) -> dict[str, list[dict]]:
    with tarfile.open(archivio) as tar:
        file = {
            Path(m.name).relative_to(Path(m.name).parts[0]).as_posix(): tar.extractfile(m).read()
            for m in tar.getmembers()
            if m.isfile() and re.search(r"corpus/original_(xml|text)/it/[^/]+\.(xml|txt)$", m.name)
        }
    contenuto = sha256(b"".join(nome.encode() + b"\0" + dati for nome, dati in sorted(file.items())))
    if contenuto != CLAUDETTE_SHA256:
        raise SystemExit(f"CLAUDETTE: il contenuto dei file italiani ha hash {contenuto}, atteso {CLAUDETTE_SHA256}.")
    contratti = []
    for nome in sorted(n for n in file if n.endswith(".xml")):
        tos = Path(nome).stem
        testo = file[f"corpus/original_text/it/{tos}.txt"].decode("utf-8")
        xml = file[nome].decode("utf-8")
        for da_correggere, originale, corretto in CORREZIONI_CLAUDETTE:
            if da_correggere == tos:
                if xml.count(originale) != 1:
                    raise SystemExit(f"CLAUDETTE {tos}: la correzione non trova il testo atteso.")
                xml = xml.replace(originale, corretto)
        contratti.append({"id": tos, "testo": testo, "risposte": risposte_claudette(xml)})
    return {"tutti": contratti}


# --- Campione e risposte giuste -------------------------------------------------------------------------


def campiona(ids: list[str], n: int, chiave: str) -> list[str]:
    """n id estratti con seme fisso. Il seme dipende anche da benchmark e insieme, così le estrazioni sono
    indipendenti e riproducibili (un seme stringa non dipende da PYTHONHASHSEED)."""
    if len(ids) < n:
        raise SystemExit(f"{chiave}: solo {len(ids)} contratti sotto il tetto, ne servono {n}. Vedi --tetto.")
    return random.Random(f"{SEME}-{chiave}").sample(sorted(ids), n)


def righe_cuad(contratto: dict, insieme: str) -> list[dict]:
    return [
        {
            "benchmark": "cuad",
            "insieme": insieme,
            "contratto": contratto["id"],
            "categoria": categoria,
            "ruolo": ruolo,
            "da_segnalare": bool(contratto["risposte"][categoria]),
            "prove": contratto["risposte"][categoria],
        }
        for categoria, ruolo in CUAD_CATEGORIE.items()
    ]


def righe_contractnli(contratto: dict, insieme: str) -> list[dict]:
    righe = []
    for ipotesi, (descrizione, ruolo) in CONTRACTNLI_IPOTESI.items():
        etichetta, pezzi = contratto["risposte"][ipotesi]
        righe.append(
            {
                "benchmark": "contractnli",
                "insieme": insieme,
                "contratto": contratto["id"],
                "categoria": descrizione,
                "ipotesi": ipotesi,
                "ruolo": ruolo,
                "da_segnalare": etichetta == "Contradiction",
                "etichetta_originale": etichetta,
                "prove": pezzi,
            }
        )
    return righe


def righe_claudette(contratto: dict, insieme: str) -> list[dict]:
    righe = []
    for tag, (nome, ruolo) in CLAUDETTE_CATEGORIE.items():
        clausole = contratto["risposte"][tag]
        gradi = [grado for grado, _ in clausole]
        righe.append(
            {
                "benchmark": "claudette",
                "insieme": insieme,
                "contratto": contratto["id"],
                "categoria": nome,
                "tag": tag,
                "ruolo": ruolo,
                "da_segnalare": any(grado >= 2 for grado in gradi),
                "da_segnalare_grado_3": 3 in gradi,
                "grado_massimo": max(gradi, default=None),
                "prove": [testo for grado, testo in clausole if grado >= 2],
            }
        )
    return righe


def statistiche(token: list[int], tetto: int) -> dict:
    ordinati = sorted(token)
    return {
        "totale": len(token),
        "sotto_tetto": sum(t <= tetto for t in token),
        "mediana": int(statistics.median(ordinati)),
        "p90": ordinati[int(0.9 * (len(ordinati) - 1))],
        "massimo": ordinati[-1],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tetto", type=int, default=TETTO, help="tetto in token Qwen3 (ripiego deciso: 12000)")
    parser.add_argument("--uscita", type=Path, default=QUI / "set-di-misura")
    argomenti = parser.parse_args()

    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(scarica("tokenizer")))
    benchmark = {
        "cuad": (leggi_cuad(scarica("cuad")), righe_cuad),
        "contractnli": (leggi_contractnli(scarica("contractnli")), righe_contractnli),
        "claudette": (leggi_claudette(scarica("claudette")), righe_claudette),
    }

    argomenti.uscita.mkdir(parents=True, exist_ok=True)
    conteggi, campione, righe, token_csv = {"tetto": argomenti.tetto}, {"seme": SEME, "tetto": argomenti.tetto}, [], []
    for nome, (insiemi, righe_di) in benchmark.items():
        conteggi[nome] = {}
        sotto = {}
        for insieme, contratti in insiemi.items():
            codifiche = tokenizer.encode_batch([c["testo"] for c in contratti], add_special_tokens=False)
            token = [len(codifica.ids) for codifica in codifiche]
            conteggi[nome][insieme] = statistiche(token, argomenti.tetto)
            sotto[insieme] = [c["id"] for c, t in zip(contratti, token) if t <= argomenti.tetto]
            token_csv += [(nome, insieme, c["id"], t) for c, t in zip(contratti, token)]
        if nome == "claudette":
            test = campiona(sotto["tutti"], N_TEST, f"{nome}-test")
            sviluppo = sorted(set(sotto["tutti"]) - set(test))
            origine = {"sviluppo": "tutti", "test": "tutti"}
        else:
            sviluppo = campiona(sotto["train"], N_SVILUPPO, f"{nome}-sviluppo")
            test = campiona(sotto["test"], N_TEST, f"{nome}-test")
            origine = {"sviluppo": "train", "test": "test"}
        campione[nome] = {"sviluppo": sviluppo, "test": test}
        per_id = {c["id"]: c for contratti in insiemi.values() for c in contratti}
        for insieme in ("sviluppo", "test"):
            assert all(i in {c["id"] for c in insiemi[origine[insieme]]} for i in campione[nome][insieme])
            nuove = [riga for i in campione[nome][insieme] for riga in righe_di(per_id[i], insieme)]
            if not any(riga["da_segnalare"] for riga in nuove):
                raise SystemExit(
                    f"{nome} {insieme}: nessuna coppia da segnalare, la lettura delle risposte è sbagliata."
                )
            righe += nuove

    (argomenti.uscita / "conteggi.json").write_text(json.dumps(conteggi, indent=2, ensure_ascii=False) + "\n")
    (argomenti.uscita / "campione.json").write_text(json.dumps(campione, indent=2, ensure_ascii=False) + "\n")
    with (argomenti.uscita / "risposte-giuste.jsonl").open("w") as f:
        for riga in righe:
            f.write(json.dumps(riga, ensure_ascii=False) + "\n")
    with (argomenti.uscita / "token-per-contratto.csv").open("w", newline="") as f:
        scrittore = csv.writer(f)
        scrittore.writerow(["benchmark", "insieme_originale", "contratto", "token_qwen3"])
        scrittore.writerows(token_csv)

    for nome in benchmark:
        dettaglio = ", ".join(f"{insieme} {s['sotto_tetto']}/{s['totale']}" for insieme, s in conteggi[nome].items())
        positivi = sum(r["da_segnalare"] for r in righe if r["benchmark"] == nome and r["insieme"] == "test")
        coppie = sum(1 for r in righe if r["benchmark"] == nome and r["insieme"] == "test")
        print(f"{nome}: sotto il tetto {dettaglio}; test {coppie} coppie, {positivi} da segnalare")
    print(f"Scritto in {argomenti.uscita}")


if __name__ == "__main__":
    main()
