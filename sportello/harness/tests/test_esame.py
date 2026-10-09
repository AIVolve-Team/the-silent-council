"""Le misure dell'esame (“Pre-registered eval G1-G4”-§9), su righe costruite a mano."""

import copy

import pytest
from fatture.genera import genera_insieme
from pipeline.schemi import lettura_da

from harness.esame import consegnabile, frase_memoria, frase_pensieri, metriche_esame


@pytest.fixture(scope="module")
def casi():
    return genera_insieme("sviluppo").casi


def primo(casi, **condizioni):
    return next(c for c in casi if all(getattr(c, k) == v for k, v in condizioni.items()))


def riga(caso, esito, secondi=2.0):
    return {"id": caso.id, "esito": esito, "lettura": None, "secondi": secondi,
            "token": {"generati": 100, "letti": 400, "analisi": 0}}  # fmt: skip


def test_le_misure_sulle_fatture(casi):
    pulita = primo(casi, anomalia=None, al_limite=None)
    al_limite = primo(casi, anomalia=None, al_limite="prezzo")
    altra_pulita = [c for c in casi if c.anomalia is None and c.al_limite is None][1]
    righe = [
        riga(pulita, "pagare"),  # giusto
        riga(al_limite, "persona"),  # persona su una pulita al limite
        riga(altra_pulita, "bloccare"),  # blocco ingiusto
        riga(primo(casi, anomalia="A03"), "pagare"),  # pagamento dannoso
        riga(primo(casi, anomalia="A04"), "pagare"),  # dubbio pagato senza persona
        riga(primo(casi, anomalia="A01"), "bloccare"),  # giusto
    ]
    m = metriche_esame(righe, {c.id: c for c in casi})
    assert m.fatture == 6
    assert m.esito_giusto == 2
    assert m.pagamenti_dannosi == 1
    assert m.blocchi_ingiusti == 1
    assert (m.persona_pulite_limite, m.persona_pulite_altre) == (1, 0)
    assert m.dubbi_pagati == 1
    assert m.confusione["bloccare"]["pagare"] == 1
    assert m.fatture_all_ora == pytest.approx(1800.0)  # 2 secondi per fattura


def test_la_memoria_di_un_altra_fattura(casi):
    a, b = [c for c in casi if c.anomalia is None][:2]
    di_b, di_a = lettura_da(b.impegno), lettura_da(a.impegno)
    righe = [{"id": a.id, "lettura": di_b}] * 3 + [{"id": a.id, "lettura": di_a}]
    frase = frase_memoria(righe, {c.id: c for c in casi}, {a.id: b.id})
    assert frase.vale is True
    assert frase.casi_altra == 3 and frase.casi_propria == 1
    assert "cambi la memoria, cambia la risposta" in frase.frase


def test_se_la_memoria_non_conta_la_frase_non_si_dice(casi):
    a, b = [c for c in casi if c.anomalia is None][:2]
    righe = [{"id": a.id, "lettura": copy.deepcopy(lettura_da(a.impegno))}]
    assert frase_memoria(righe, {c.id: c for c in casi}, {a.id: b.id}).vale is False


@pytest.mark.parametrize(
    ("con_pensieri", "senza", "attesa"),
    [(95.0, 92.5, "I pensieri servono"), (95.0, 93.5, "Gli agenti si passano la memoria")],
)
def test_la_frase_sui_pensieri(con_pensieri, senza, attesa):
    assert frase_pensieri(con_pensieri, senza).startswith(attesa)


def test_g4_lo_sportello_e_consegnabile_solo_se_tutto_torna(casi):
    m = metriche_esame([riga(primo(casi, anomalia=None), "pagare")], {c.id: c for c in casi})
    tutto = {"g1_passa": True, "metriche": m, "attacchi_ok": True, "demo_ok": True, "esame_completo": True}
    ok, voci = consegnabile(g2_esito="compatibile", **tutto)
    assert ok is True and all(stato == "✓" for _, stato in voci)
    ok, voci = consegnabile(g2_esito="no", **tutto)
    assert ok is False
    ok, _ = consegnabile(g2_esito="dimostrato", **tutto | {"attacchi_ok": None})
    assert ok is None  # manca una misura: G4 non si decide ancora


def test_g4_non_dice_si_finche_l_esame_non_e_finito(casi):
    # Zero pagamenti dannosi su zero fatture non vuol dire niente: l'esame a metà lascia G4 in sospeso.
    m = metriche_esame([], {c.id: c for c in casi})
    ok, voci = consegnabile(g1_passa=True, g2_esito="compatibile", metriche=m, attacchi_ok=True, demo_ok=True,
                            esame_completo=False)  # fmt: skip
    assert ok is None
    assert ("esame completo, nei due modi e con le prove anti-trucco", "?") in voci


def righe_attacchi(riusciti: frozenset[str] = frozenset(), quante: int | None = None) -> list[dict]:
    """Le righe che `attacchi.esegui` scrive sull'esame: F1-F2 bloccati dal sigillo, gli altri dalla coerenza, salvo
    quelli `riusciti`; F4-F7 anche a testo."""
    from attacchi.costruisci import FAMIGLIE

    righe = []
    for famiglia, n in FAMIGLIE.items():
        for i in range(1, n + 1):
            id_attacco = f"esame-{famiglia}-{i:02d}"
            for modalita in ("telepatia", "testo") if famiglia in ("F4", "F5", "F6", "F7") else ("telepatia",):
                riuscito = id_attacco in riusciti
                righe.append({
                    "id": id_attacco, "famiglia": famiglia, "base": f"esame-{i:04d}", "modalita": modalita,
                    "categoria": "riusciti" if riuscito else "bloccati",
                    "livello": None if riuscito else "sigillo" if famiglia in ("F1", "F2") else "coerenza",
                })  # fmt: skip
    return righe[:quante]


def scrivi_attacchi(cartella, righe):
    import json

    cartella.mkdir()
    (cartella / "attacchi.jsonl").write_text("".join(json.dumps(r) + "\n" for r in righe))
    return cartella


@pytest.mark.parametrize(
    ("riusciti", "quante", "atteso"),
    [
        (frozenset(), None, True),  # tutti fermati come in §5
        (frozenset({"esame-F5-02"}), None, False),  # un F5 riuscito: G4 no
        (frozenset({"esame-F7-01"}), None, True),  # F7 si misura e si dichiara, non decide G4
        (frozenset(), 30, None),  # giro a metà: manca una misura
    ],
)
def test_g4_legge_gli_attacchi_dell_esame(tmp_path, riusciti, quante, atteso):
    from harness.esame import attacchi_dell_esame

    testo, ok = attacchi_dell_esame(scrivi_attacchi(tmp_path / "attacchi", righe_attacchi(riusciti, quante)))
    assert ok is atteso
    assert testo.startswith("## Attacchi (§5)")


def test_il_rapporto_dell_esame_porta_gli_attacchi(tmp_path):
    from fatture.insiemi import salva_insieme

    from harness.esame import testo_esame

    salva_insieme(genera_insieme("sviluppo"), tmp_path / "insieme")
    attacchi = scrivi_attacchi(tmp_path / "attacchi", righe_attacchi())
    testo = testo_esame(tmp_path / "esame", tmp_path / "insieme", g1="passa", g2="compatibile", attacchi=attacchi,
                        demo="ok")  # fmt: skip
    assert "| F5 | telepatia | 8 |" in testo
    assert "| Impegno giusto, tutti i campi (senza soglia) |" in testo
    assert "| Proposta giusta, IBAN e importo (senza soglia) |" in testo
    assert "- ✓ attacchi fermati come in §5" in testo
    assert "arrivano con “Attacks”" not in testo


@pytest.fixture(scope="module")
def insieme_su_disco(tmp_path_factory):
    from fatture.insiemi import salva_insieme

    cartella = tmp_path_factory.mktemp("insieme") / "sviluppo"
    salva_insieme(genera_insieme("sviluppo"), cartella)
    return cartella


def test_il_rapporto_dell_esame_ha_la_tabella_atteso_ottenuto_e_i_token_letti(tmp_path, insieme_su_disco):
    import json

    from fatture.insiemi import carica_casi

    from harness.esame import testo_esame

    casi = carica_casi(insieme_su_disco)
    giri = tmp_path / "esame" / "giri"
    giri.mkdir(parents=True)
    for modalita in ("telepatia", "testo"):
        righe = [riga(c, c.esito_atteso) for c in casi]
        (giri / f"{modalita}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in righe))

    testo = testo_esame(tmp_path / "esame", insieme_su_disco, g1=None, g2=None, attacchi=None, demo=None)

    assert "| Token letti per fattura | 400 | 400 |" in testo
    assert "Esito atteso (righe) contro esito ottenuto (colonne)" in testo
    # 58 pulite da pagare, 18 da passare a una persona, 24 da bloccare: tutte giuste, quindi sulla diagonale
    assert "| pagare | 58 | 0 | 0 | 0 |" in testo
    assert "| bloccare | 0 | 0 | 24 | 0 |" in testo


def test_l_esame_scrive_un_errore_e_va_avanti_e_ogni_modo_ha_il_suo_registro(tmp_path, insieme_su_disco, monkeypatch):
    import json

    import pipeline.sportello
    from fatture.insiemi import carica_archivi, carica_casi

    from harness.esame import esegui_uno

    registri = []

    def finta(modello, pdf, email, archivi, chiavi, *, registro, id_caso, modalita="telepatia", **_):
        registri.append(registro)
        if modalita == "testo":
            raise RuntimeError("memoria esaurita")
        return {"id_caso": id_caso, "esito": "pagare", "token": {"generati": 1, "letti": 2}, "secondi": 1.0}

    monkeypatch.setattr(pipeline.sportello, "esamina", finta)
    caso = carica_casi(insieme_su_disco)[0]
    comuni = {"esame": insieme_su_disco, "archivi": carica_archivi(insieme_su_disco), "modello": None, "chiavi": None}
    esegui_uno(tmp_path / "giri" / "telepatia.jsonl", caso, modalita="telepatia", **comuni)
    esegui_uno(tmp_path / "giri" / "testo.jsonl", caso, modalita="testo", **comuni)

    riga_testo = json.loads((tmp_path / "giri" / "testo.jsonl").read_text())
    assert riga_testo["esito"] == "errore" and "memoria esaurita" in riga_testo["errore"]
    assert registri[0] != registri[1]  # il testo non sovrascrive i messaggi firmati della telepatia
