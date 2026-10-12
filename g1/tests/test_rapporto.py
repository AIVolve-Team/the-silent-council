import json

from g1.riepilogo import rapporto


def scrivi(cartella, nome, righe):
    (cartella / f"{nome}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in righe))


def riga(i, corretto, token):
    return {
        "id": f"p{i}",
        "corretto": corretto,
        "token_generati": token,
        "token_letti": 50,
        "secondi": 2.0,
        "troncati": 0,
        "posizioni_latenti": 0,
    }


def test_il_rapporto_per_il_ticket(tmp_path):
    scrivi(tmp_path, "testo", [riga(0, True, 400), riga(1, True, 600)])
    scrivi(tmp_path, "telepatia", [riga(0, True, 100), riga(1, True, 100)])
    scrivi(tmp_path, "senza_pensieri", [riga(0, True, 90), riga(1, False, 90)])
    (tmp_path / "memoria.json").write_text(json.dumps({"ok": True, "pesi_due_modelli_gb": 101.6}))

    testo = rapporto(tmp_path)

    assert "**G1 passa**" in testo
    assert "−80%" in testo  # 200 token in telepatia contro 1.000 a testo
    assert "dimostrato" in testo
    assert "101,6 GB" in testo
    assert "si può dire" in testo  # più di 80 GB: la frase sulla H100 del copione


def test_senza_memoria_il_rapporto_lo_dice(tmp_path):
    for nome in ("testo", "telepatia", "senza_pensieri"):
        scrivi(tmp_path, nome, [riga(0, True, 100)])
    assert "manca la misura della memoria" in rapporto(tmp_path)


def test_un_giro_interrotto_si_riporta_sui_problemi_finiti_nei_tre_modi(tmp_path):
    scrivi(tmp_path, "testo", [riga(0, True, 400), riga(1, True, 600)])
    scrivi(tmp_path, "telepatia", [riga(0, True, 100), riga(1, True, 100)])
    scrivi(tmp_path, "senza_pensieri", [riga(0, True, 90)])
    (tmp_path / "ambiente.json").write_text(json.dumps({"problemi": 100}))

    testo = rapporto(tmp_path)

    assert "Parziale: 1 problema su 100" in testo
    assert "−75%" in testo  # solo p0: 100 token in telepatia contro 400 a testo
