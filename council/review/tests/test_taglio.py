from revisione.taglio import FINANZA, LEGALE, RISCHIO, taglia, trova_titoli

LETTORI = (LEGALE, FINANZA, RISCHIO)


def titoli(testo):
    return [t.testo for t in trova_titoli(testo)]


def test_titoli_in_linea_all_inglese():
    testo = "AGREEMENT\n1. Services. FASC agrees to provide.\n2. Fees. For its Services, Adviser pays.\n"
    testo += "4. Limitation of Liability and Indemnification.\n(a) FASC shall not.\n5. Duration and Termination.\n"
    assert {
        "Services",
        "Fees",
        "Limitation of Liability and Indemnification",
        "Duration and Termination",
    } <= set(titoli(testo))


def test_una_frase_numerata_non_e_un_titolo():
    testo = "1. Definitions.\n1.1 The Supplier shall deliver the goods on time.\n2. Term. This Agreement lasts."
    assert "The Supplier shall deliver the goods on time" not in titoli(testo)


def test_titoli_italiani_con_trattino_e_sottopunti():
    testo = "Art. 3 – Esclusiva di acquisto\n\n3.1 Per tutta la durata il Cliente compra solo dal Fornitore.\n"
    testo += "Art. 10 – Cessione del contratto e cambio di controllo\n\n10.1 Il Cliente non può cedere."
    assert titoli(testo)[:2] == [
        "Esclusiva di acquisto",
        "Cessione del contratto e cambio di controllo",
    ]


def test_indici_e_numeri_romani():
    testo = "TABLE OF CONTENTS\nArticle VII Term and Termination 15\n1. Interpretation 3 2. Commencement 4\n"
    testo += "INTELLECTUAL PROPERTY AGREEMENT\nArticle VII Term and Termination\nThe term is five years."
    trovati = trova_titoli(testo)
    assert [t.testo for t in trovati if t.numerato] == ["Term and Termination"]
    assert all("NTELLECTUAL" != t.testo[:11] for t in trovati)


def test_titolo_maiuscolo_seguito_da_sottopunto():
    testo = "IT IS AGREED as follows: 1. INTERPRETATION 1.1 In this Agreement words mean.\n"
    testo += "2. COMMENCEMENT OF APPOINTMENT 2.1 The Appointment will begin on 27 January."
    assert {"INTERPRETATION", "COMMENCEMENT OF APPOINTMENT"} <= set(titoli(testo))


def test_righe_ripetute_e_con_i_due_punti_non_sono_titoli():
    testo = (
        "Source: EDGAR, S-1/A\nSome text here that is long enough.\nTable of Contents\nMore text.\nTable of Contents\n"
    )
    assert titoli(testo) == []


def test_instradamento_per_ruolo_e_preambolo_al_legale():
    testo = "CONTRATTO\nTra le parti.\nArt. 1 – Oggetto\nfornitura.\nArt. 2 – Esclusiva di acquisto\nsolo da noi.\n"
    testo += "Art. 3 – Prezzi e pagamenti\n60 giorni.\nArt. 4 – Durata e recesso\ntre anni.\n"
    taglio = taglia(testo, LETTORI, "commerciale")
    assert taglio.modo == "titoli"
    assert "CONTRATTO" in taglio.sezioni[LEGALE] and "Oggetto" in taglio.sezioni[LEGALE]
    assert "Prezzi e pagamenti" in taglio.sezioni[FINANZA]
    assert "Esclusiva" in taglio.sezioni[RISCHIO] and "Durata e recesso" in taglio.sezioni[RISCHIO]
    # Ogni clausola sta in una sola sezione.
    unite = "".join(taglio.sezioni.values()).replace("[…]", "")
    assert unite.count("Prezzi e pagamenti") == 1 and len(unite.replace("\n", "")) <= len(testo.replace("\n", ""))


def test_senza_titoli_parti_contigue_di_lunghezza_simile():
    frase = "Lo Studio svolgerà l'incarico con diligenza. "
    testo = (
        "Spettabile\nFerramenta Galli\nVia Roma 18, Cremona\n\n" + frase * 60 + "\n\nCordiali saluti,\nDott.ssa Moretti"
    )
    taglio = taglia(testo, LETTORI, "commerciale")
    assert taglio.modo == "contiguo"
    lunghezze = [len(taglio.sezioni[r]) for r in LETTORI]
    assert max(lunghezze) < 2 * min(lunghezze)
    assert "".join(taglio.sezioni[r] for r in LETTORI).replace(" ", "").replace("\n", "") == testo.replace(
        " ", ""
    ).replace("\n", "")


def test_senza_finanza_su_nda():
    testo = "1. Confidential Information. Means all.\n2. Term. Two years.\n3. Return of Materials. Destroy.\n"
    testo += "4. Payment. None.\n"
    taglio = taglia(testo, (LEGALE, RISCHIO), "nda")
    assert set(taglio.sezioni) == {LEGALE, RISCHIO} and "Return of Materials" in taglio.sezioni[RISCHIO]
