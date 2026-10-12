"""L'eval del Consiglio: fa girare le configurazioni a confronto e ne scrive il rapporto.

Esempi:
    python -m revisione.esame esegui --benchmark cuad --insieme sviluppo --passi 10 --modello Qwen/Qwen3-14B
    python -m revisione.esame esegui --benchmark dimostrativo --passi 10 --configurazioni telepatia m0
    python -m revisione.esame rapporto esame

Il modello si carica una volta per tutte le configurazioni. Ogni configurazione scrive
`<benchmark>-<insieme>-<configurazione>.jsonl`, una revisione per riga; `esame.json` dice con cosa è girato.
Sul set di test l'eval parte solo con la pre-registrazione congelata e committata (`consiglio/PREREGISTRAZIONE.md`),
e una volta sola: un secondo giro è una deviazione e chiede il motivo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import torch
from motore import TELEPATIA, TESTO, Modello, Motore

from . import misure
from .categorie import BENCHMARK
from .configurazioni import AgenteSolo, VotoFraQuattro
from .consiglio import Consiglio
from .dati import dimostrativo, prove, risposte_giuste, risposte_grado_3
from .esegui import MODELLI, _contratti_e_risposte, libera_memoria, sintesi

RADICE = Path(__file__).resolve().parents[3]
PREREGISTRAZIONE = RADICE / "consiglio" / "PREREGISTRAZIONE.md"
# Stato della pre-registrazione finché non è congelata: con questa riga il test non parte.
BOZZA = "Stato: bozza"
# Ordine di esecuzione: la telepatia viene prima perché i suoi pensieri servono alla prova dei pensieri scambiati.
ORDINE = ("telepatia", "testo", "solo", "voto", "m0", "pensieri-scambiati", "contratto-scambiato")


def _git(*argomenti: str) -> str:
    return subprocess.run(["git", "-C", str(RADICE), *argomenti], capture_output=True, text=True, check=True).stdout


def controlla_preregistrazione() -> dict:
    """La pre-registrazione dev'essere congelata e committata, e il codice senza modifiche locali."""
    if not PREREGISTRAZIONE.exists():
        raise SystemExit(f"Manca la pre-registrazione: {PREREGISTRAZIONE}")
    testo = PREREGISTRAZIONE.read_text()
    if BOZZA in testo:
        raise SystemExit("La pre-registrazione è ancora una bozza: va congelata e committata prima del test.")
    relativo = str(PREREGISTRAZIONE.relative_to(RADICE))
    if _git("status", "--porcelain", "--", relativo).strip():
        raise SystemExit("La pre-registrazione ha modifiche non committate: il test usa solo regole committate.")
    if _git("status", "--porcelain", "--untracked-files=no", "--", "consiglio", "motore").strip():
        raise SystemExit("Il codice di consiglio/ o motore/ ha modifiche non committate: il test gira su un commit.")
    commit, data = _git("log", "-1", "--format=%H %cI", "--", relativo).split()
    return {
        "file": relativo,
        "commit": commit,
        "data_commit": data,
        "sha256": hashlib.sha256(testo.encode("utf-8")).hexdigest(),
    }


def _giuste(benchmark: str, insieme: str) -> dict:
    if benchmark == "dimostrativo":
        return {(cid, r["categoria"]): r["da_segnalare"] for cid, _, attesa in dimostrativo() for r in attesa["righe"]}
    return risposte_giuste(benchmark, insieme)


def esegui(argomenti: argparse.Namespace) -> None:
    uscita: Path = argomenti.uscita
    uscita.mkdir(parents=True, exist_ok=True)
    scelte = [c for c in ORDINE if c in argomenti.configurazioni]
    if argomenti.passi == 0 and {"m0", "pensieri-scambiati"} & set(scelte):
        # Con 0 passi non ci sono pensieri: "pensieri azzerati" sarebbe lo stesso giro della telepatia e i pensieri di
        # un altro contratto non esistono. Le due prove non si fanno (PREREGISTRAZIONE.md, prove di sabotaggio).
        print("0 passi latenti: niente prove sui pensieri (pensieri azzerati, pensieri scambiati).", flush=True)
        scelte = [c for c in scelte if c not in ("m0", "pensieri-scambiati")]
    if "pensieri-scambiati" in scelte and "telepatia" not in scelte:
        raise SystemExit("I pensieri scambiati usano i pensieri del giro in telepatia: aggiungi la telepatia.")
    preregistrazione, deviazione = None, None
    if argomenti.insieme == "test":
        preregistrazione = controlla_preregistrazione()
        precedenti = sorted(uscita.glob(f"{argomenti.benchmark}-test-*.jsonl"))
        if precedenti and not argomenti.deviazione:
            raise SystemExit(
                "Il test gira una volta sola. Per un altro giro serve --deviazione con il motivo, da scrivere "
                "anche fra le deviazioni della pre-registrazione."
            )
        deviazione = argomenti.deviazione
    dtype = getattr(torch, argomenti.dtype) if argomenti.dtype else None
    modello = Modello(
        argomenti.modello,
        argomenti.revisione or MODELLI[argomenti.modello],
        dtype=dtype,
        riallinea=not argomenti.senza_riallineamento,
    )
    motore = Motore(modello, registro=uscita / "registro")
    voci, giuste = _contratti_e_risposte(argomenti.benchmark, argomenti.insieme)
    if argomenti.max_token:
        lunghezza = {cid: len(modello.tokenizer.encode(testo, add_special_tokens=False)) for cid, testo in voci}
        voci = [(cid, testo) for cid, testo in voci if lunghezza[cid] <= argomenti.max_token]
    voci = voci[: argomenti.limite] if argomenti.limite else voci
    if len(voci) < 2 and {"pensieri-scambiati", "contratto-scambiato"} & set(scelte):
        raise SystemExit("Gli scambi servono almeno 2 contratti.")
    meta = {
        "benchmark": argomenti.benchmark,
        "insieme": argomenti.insieme,
        "modello": argomenti.modello,
        "revisione": modello.revisione,
        "dtype": str(modello.dtype).removeprefix("torch."),
        "dispositivo": modello.dispositivo,
        "riallineamento": modello.riallinea,
        "passi": argomenti.passi,
        "configurazioni": scelte,
        "contratti": [cid for cid, _ in voci],
        "codice": _git("rev-parse", "HEAD").strip(),
        "modifiche_locali": bool(_git("status", "--porcelain", "--untracked-files=no").strip()),
        "preregistrazione": preregistrazione,
        "deviazione": deviazione,
        "inizio": datetime.now(UTC).isoformat(),
    }
    (uscita / f"esame-{argomenti.benchmark}-{argomenti.insieme}.json").write_text(json.dumps(meta, indent=2))
    benchmark = BENCHMARK[argomenti.benchmark]
    pensieri: dict[str, dict] = {}
    for configurazione in scelte:
        if configurazione in ("solo", "voto"):
            classe = AgenteSolo if configurazione == "solo" else VotoFraQuattro
            esecutore = classe(motore, benchmark, traduci=argomenti.traduci)
        else:
            modalita = TESTO if configurazione == "testo" else TELEPATIA
            passi = 0 if configurazione == "m0" else argomenti.passi
            esecutore = Consiglio(motore, benchmark, modalita=modalita, passi_latenti=passi, traduci=argomenti.traduci)
        nome = f"{argomenti.benchmark}-{argomenti.insieme}-{configurazione}"
        print(f"-- {nome} ({time.strftime('%H:%M')})", flush=True)
        revisioni = []
        with (uscita / f"{nome}.jsonl").open("w") as f:
            for i, (contratto, testo) in enumerate(voci):
                altro, testo_altro = voci[(i + 1) % len(voci)]
                extra: dict = {"configurazione": configurazione}
                if configurazione in ("solo", "voto"):
                    revisione = esecutore.revisiona(contratto, testo)
                elif configurazione == "pensieri-scambiati":
                    revisione = esecutore.revisiona(contratto, testo, pensieri_da=pensieri[altro]).come_dict()
                    extra["pensieri_da"] = altro
                elif configurazione == "contratto-scambiato":
                    revisione = esecutore.revisiona(contratto, testo_altro).come_dict()
                    extra["testo_da"] = altro
                else:
                    revisione = esecutore.revisiona(contratto, testo).come_dict()
                    if configurazione == "telepatia":
                        pensieri[contratto] = esecutore.pensieri
                revisione |= extra
                revisioni.append(revisione)
                f.write(json.dumps(revisione, ensure_ascii=False) + "\n")
                f.flush()
                print(f"  {contratto[:60]}: {revisione['secondi']:.0f} s", flush=True)
                libera_memoria()
        print(f"{nome}: {sintesi(revisioni, giuste)}", flush=True)
    meta["fine"] = datetime.now(UTC).isoformat()
    (uscita / f"esame-{argomenti.benchmark}-{argomenti.insieme}.json").write_text(json.dumps(meta, indent=2))


# --- rapporto ------------------------------------------------------------------------------------------------------


def _n(x: float, cifre: int = 1) -> str:
    return f"{x:.{cifre}f}".replace(".", ",")


def _segno(x: float) -> str:
    return ("+" if x > 0 else "") + _n(x)


def _intero(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def _frazione(coppia: tuple[int, int]) -> str:
    a, n = coppia
    return f"{a}/{n}" + (f" ({_n(100 * a / n, 0)}%)" if n else "")


def _giri(cartella: Path) -> dict[tuple[str, str], dict[str, list[dict]]]:
    giri: dict[tuple[str, str], dict[str, list[dict]]] = {}
    for f in sorted(cartella.glob("*.jsonl")):
        benchmark, insieme, configurazione = f.stem.split("-", 2)
        if configurazione not in misure.CONFIGURAZIONI:
            continue
        righe = [json.loads(r) for r in f.read_text().splitlines() if r.strip()]
        giri.setdefault((benchmark, insieme), {})[configurazione] = righe
    return giri


def scrivi_rapporto(cartella: Path) -> str:
    """Scrive `rapporto.md`, `numeri.json` e un grafico per benchmark nella cartella dei risultati. Solo numeri
    aggregati: il rapporto si può incollare nel ticket."""
    parti = ["# Eval del Consiglio: rapporto", ""]
    tutti = {}
    for (benchmark, insieme), giri in _giri(cartella).items():
        meta_file = cartella / f"esame-{benchmark}-{insieme}.json"
        meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
        giuste = _giuste(benchmark, insieme)
        if not giuste:
            raise SystemExit(
                f"Mancano le risposte giuste di {benchmark}: per il set dimostrativo vedi CONSIGLIO_SET_DIMOSTRATIVO."
            )
        testi = {cid: testo for cid, testo, _ in dimostrativo()} if benchmark == "dimostrativo" else None
        grado_3 = risposte_grado_3(insieme) if benchmark == "claudette" else None
        numeri = misure.riepilogo(giri, giuste, prove(benchmark, insieme), testi=testi, grado_3=grado_3)
        numeri["meta"] = meta
        tutti[f"{benchmark}-{insieme}"] = numeri
        parti += _sezione(benchmark, insieme, numeri, meta)
        punti = [
            (misure.NOMI[c], r["token_generati"], r["f1"])
            for c, r in numeri["configurazioni"].items()
            if c in ("solo", "voto", "testo", "telepatia")
        ]
        if punti:
            titolo = f"{benchmark} ({insieme}): qualità contro costo"
            (cartella / f"grafico-{benchmark}-{insieme}.svg").write_text(misure.grafico_svg(punti, titolo))
            parti += [f"![Qualità contro costo](grafico-{benchmark}-{insieme}.svg)", ""]
    testo = "\n".join(parti)
    (cartella / "rapporto.md").write_text(testo)
    (cartella / "numeri.json").write_text(json.dumps(tutti, indent=2, ensure_ascii=False, default=list))
    return testo


def _sezione(benchmark: str, insieme: str, numeri: dict, meta: dict) -> list[str]:
    configurazioni = numeri["configurazioni"]
    contratti = max(r["contratti"] for r in configurazioni.values())
    righe = [f"## {benchmark}, {insieme} ({contratti} contratti)", ""]
    if meta:
        prereg = meta.get("preregistrazione") or {}
        righe += [
            f"Modello {meta.get('modello')} ({meta.get('dtype')}, {meta.get('dispositivo')}), passi latenti "
            f"{meta.get('passi')}, riallineamento {'acceso' if meta.get('riallineamento') else 'spento'}, codice "
            f"`{str(meta.get('codice'))[:7]}`"
            + (f", pre-registrazione `{prereg['commit'][:7]}` del {prereg['data_commit'][:10]}" if prereg else "")
            + (f". **Deviazione:** {meta['deviazione']}" if meta.get("deviazione") else "")
            + ".",
            "",
        ]
    righe += [
        (
            "| Configurazione | F1 | P | R | MCC | Sempre sì | F1 severa | Mancate | Falsi allarmi "
            "| Verdetti validi | Token generati | Token letti | Secondi |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in misure.CONFIGURAZIONI:
        if c not in configurazioni:
            continue
        r = configurazioni[c]
        righe.append(
            f"| {misure.NOMI[c]} | **{_n(r['f1'])}** | {_n(r['precisione'])} | {_n(r['richiamo'])} | "
            f"{_n(r['mcc'], 2)} | {_n(r['sempre_si'])} | {_n(r['f1_severa'])} | {r['mancate']} | "
            f"{r['falsi_allarmi']} | {r['verdetti_validi']}/{r['contratti']} | {_intero(r['token_generati'])} | "
            f"{_intero(r['token_letti'])} | {_intero(r['secondi'])} |"
        )
    righe.append("")
    confronto = numeri.get("telepatia_contro_testo")
    if confronto:
        tele, testo = configurazioni["telepatia"], configurazioni["testo"]
        risparmio = 1 - tele["token_generati"] / testo["token_generati"] if testo["token_generati"] else 0
        giudizio = "non perde, dimostrato" if confronto["dimostrata"] else "risultati compatibili"
        righe += [
            "### Telepatia contro testo",
            "",
            (
                f"- **F1 della telepatia meno F1 del testo:** {_segno(confronto['differenza'])} punti (intervallo al 95% con bootstrap appaiato sui "
                f"{confronto['contratti']} contratti: da {_n(confronto['basso'])} a {_n(confronto['alto'])}). "
                f"Si dice: *{giudizio}*."
            ),
            (
                f"- **Token generati:** {_n(100 * risparmio, 0)}% in meno. **Tempo:** {_intero(tele['secondi'])} s "
                f"contro {_intero(testo['secondi'])} s per contratto."
            ),
        ]
        if benchmark == "cuad":
            g4 = confronto["g4"]
            righe += [
                "",
                "**G4** (su CUAD):",
                "",
                f"- [{'x' if g4['f1'] else ' '}] F1 telepatia ≥ F1 testo − 3 punti",
                f"- [{'x' if g4['token'] else ' '}] token generati almeno il −50%",
                f"- [{'x' if g4['tempo'] else ' '}] la telepatia non è più lenta del testo",
            ]
        righe.append("")
    if numeri.get("sabotaggi"):
        righe += ["### Prove di sabotaggio", "", "| Prova | Differenza di F1 con la telepatia |", "|---|---|"]
        righe += [f"| {misure.NOMI[c]} | {_segno(d)} |" for c, d in numeri["sabotaggi"].items()]
        if meta.get("passi") == 0:
            # 0 passi: niente pensieri latenti, quindi niente prove sui pensieri e la frase di riserva.
            righe += [
                "",
                "Con 0 passi latenti non ci sono pensieri: le prove sui pensieri non si fanno.",
                f"Frase per la giuria: *{misure.FRASE_MEMORIA}* E poi: *{misure.FRASE_RISERVA}*",
                "",
            ]
        else:
            aiutano = numeri.get("pensieri_aiutano")
            frase = {
                True: misure.FRASE_PENSIERI,
                False: misure.FRASE_RISERVA,
                None: "mancano le prove sui pensieri per decidere",
            }[aiutano]
            righe += ["", f"Frase per la giuria: *{misure.FRASE_SEMPRE}* E poi: *{frase}*", ""]
        if "contratto-scambiato" in numeri["sabotaggi"]:
            righe += ["Il contratto scambiato deve crollare: se non crolla, c'è un errore nel codice.", ""]
    senza = numeri.get("senza_soglia") or {}
    if senza:
        righe += ["### Senza soglia", ""]
        for c, s in senza.items():
            d, t = s["dissensi"], s["taratura"]
            righe.append(
                f"- **{misure.NOMI[c]}:** dissensi gravi {d['grave'][1]}, con ragione l'esperto "
                f"{_frazione(d['grave'])}; dissensi lievi {d['lieve'][1]}, con ragione il relatore "
                f"{_frazione(d['lieve'])}. Accordo fra note e verdetto {_frazione(s['accordo_note_verdetto'])}; "
                f"F1 delle note prese come verdetto {_n(s['note_come_verdetto_f1'])}. Taratura del verdetto, "
                f"giuste per confidenza: alta {_frazione(t['alta'])}, media {_frazione(t['media'])}, bassa "
                f"{_frazione(t['bassa'])}."
            )
        righe.append("")
    if numeri.get("importi_e_date"):
        voci = ", ".join(
            f"{misure.NOMI[c]} {n} ({fuori} non nel contratto)"
            for c in misure.CONFIGURAZIONI
            if c in numeri["importi_e_date"]
            for n, fuori in [numeri["importi_e_date"][c]]
        )
        righe += [f"**Importi e date nel verdetto:** {voci}. Uno non nel contratto si segnala sempre.", ""]
    if numeri.get("grado_3"):
        voci = ", ".join(f"{misure.NOMI[c]} {_n(f)}" for c, f in numeri["grado_3"].items())
        righe += [f"**CLAUDETTE, solo grado 3:** F1 {voci}.", ""]
    return righe


def main() -> None:
    parser = argparse.ArgumentParser(description="L'eval del Consiglio.")
    comandi = parser.add_subparsers(dest="comando", required=True)
    giro = comandi.add_parser("esegui", help="fa girare le configurazioni")
    giro.add_argument("--benchmark", choices=sorted(BENCHMARK), required=True)
    giro.add_argument("--insieme", choices=["sviluppo", "test"], default="sviluppo")
    giro.add_argument("--passi", type=int, required=True, help="i passi latenti scelti sul set di sviluppo")
    giro.add_argument("--configurazioni", nargs="+", choices=ORDINE, default=list(ORDINE))
    giro.add_argument("--modello", default="Qwen/Qwen3-14B")
    giro.add_argument("--revisione", help="revisione del modello su Hugging Face (di default quella fissata)")
    giro.add_argument("--dtype", choices=["float32", "bfloat16", "float16"])
    giro.add_argument("--senza-riallineamento", action="store_true")
    giro.add_argument("--max-token", type=int, help="salta i contratti più lunghi (solo per le prove su un Mac)")
    giro.add_argument("--limite", type=int, help="solo i primi N contratti (solo per le prove)")
    giro.add_argument("--traduci", action="store_true", help="traduzione italiana delle citazioni")
    giro.add_argument("--deviazione", help="motivo di un secondo giro sul test, da scrivere nella pre-registrazione")
    giro.add_argument("--uscita", type=Path, default=Path("esame"))
    rapporto = comandi.add_parser("rapporto", help="scrive rapporto, numeri e grafici da una cartella di risultati")
    rapporto.add_argument("cartella", type=Path)
    argomenti = parser.parse_args()
    if argomenti.comando == "esegui":
        if argomenti.insieme == "test" and (argomenti.max_token or argomenti.limite):
            raise SystemExit("Sul test girano tutti i contratti: --max-token e --limite sono solo per le prove.")
        esegui(argomenti)
    else:
        print(scrivi_rapporto(argomenti.cartella))


if __name__ == "__main__":
    main()
