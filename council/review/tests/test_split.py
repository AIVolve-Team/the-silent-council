from review.split import FINANCE, LEGAL, RISK, find_headings, split_contract

READERS = (LEGAL, FINANCE, RISK)


def headings(text):
    return [h.text for h in find_headings(text)]


def test_inline_english_headings():
    text = "AGREEMENT\n1. Services. FASC agrees to provide.\n2. Fees. For its Services, Adviser pays.\n"
    text += "4. Limitation of Liability and Indemnification.\n(a) FASC shall not.\n5. Duration and Termination.\n"
    assert {
        "Services",
        "Fees",
        "Limitation of Liability and Indemnification",
        "Duration and Termination",
    } <= set(headings(text))


def test_a_numbered_sentence_is_not_a_heading():
    text = "1. Definitions.\n1.1 The Supplier shall deliver the goods on time.\n2. Term. This Agreement lasts."
    assert "The Supplier shall deliver the goods on time" not in headings(text)


def test_italian_headings_with_dash_and_subclauses():
    text = "Art. 3 – Esclusiva di acquisto\n\n3.1 Per tutta la durata il Cliente compra solo dal Fornitore.\n"
    text += "Art. 10 – Cessione del contratto e cambio di controllo\n\n10.1 Il Cliente non può cedere."
    assert headings(text)[:2] == [
        "Esclusiva di acquisto",
        "Cessione del contratto e cambio di controllo",
    ]


def test_tables_of_contents_and_roman_numerals():
    text = "TABLE OF CONTENTS\nArticle VII Term and Termination 15\n1. Interpretation 3 2. Commencement 4\n"
    text += "INTELLECTUAL PROPERTY AGREEMENT\nArticle VII Term and Termination\nThe term is five years."
    found = find_headings(text)
    assert [h.text for h in found if h.numbered] == ["Term and Termination"]
    assert all("NTELLECTUAL" != h.text[:11] for h in found)


def test_uppercase_heading_followed_by_subclause():
    text = "IT IS AGREED as follows: 1. INTERPRETATION 1.1 In this Agreement words mean.\n"
    text += "2. COMMENCEMENT OF APPOINTMENT 2.1 The Appointment will begin on 27 January."
    assert {"INTERPRETATION", "COMMENCEMENT OF APPOINTMENT"} <= set(headings(text))


def test_repeated_lines_and_lines_with_a_colon_are_not_headings():
    text = (
        "Source: EDGAR, S-1/A\nSome text here that is long enough.\nTable of Contents\nMore text.\nTable of Contents\n"
    )
    assert headings(text) == []


def test_routing_by_role_and_preamble_to_legal():
    text = "CONTRATTO\nTra le parti.\nArt. 1 – Oggetto\nfornitura.\nArt. 2 – Esclusiva di acquisto\nsolo da noi.\n"
    text += "Art. 3 – Prezzi e pagamenti\n60 giorni.\nArt. 4 – Durata e recesso\ntre anni.\n"
    split = split_contract(text, READERS, "commercial")
    assert split.mode == "headings"
    assert "CONTRATTO" in split.sections[LEGAL] and "Oggetto" in split.sections[LEGAL]
    assert "Prezzi e pagamenti" in split.sections[FINANCE]
    assert "Esclusiva" in split.sections[RISK] and "Durata e recesso" in split.sections[RISK]
    # Each clause is in a single section.
    joined = "".join(split.sections.values()).replace("[…]", "")
    assert joined.count("Prezzi e pagamenti") == 1 and len(joined.replace("\n", "")) <= len(text.replace("\n", ""))


def test_without_headings_contiguous_parts_of_similar_length():
    sentence = "Lo Studio svolgerà l'incarico con diligenza. "
    text = (
        "Spettabile\nFerramenta Galli\nVia Roma 18, Cremona\n\n"
        + sentence * 60
        + "\n\nCordiali saluti,\nDott.ssa Moretti"
    )
    split = split_contract(text, READERS, "commercial")
    assert split.mode == "contiguous"
    lengths = [len(split.sections[r]) for r in READERS]
    assert max(lengths) < 2 * min(lengths)
    assert "".join(split.sections[r] for r in READERS).replace(" ", "").replace("\n", "") == text.replace(
        " ", ""
    ).replace("\n", "")


def test_without_finance_on_nda():
    text = "1. Confidential Information. Means all.\n2. Term. Two years.\n3. Return of Materials. Destroy.\n"
    text += "4. Payment. None.\n"
    split = split_contract(text, (LEGAL, RISK), "nda")
    assert set(split.sections) == {LEGAL, RISK} and "Return of Materials" in split.sections[RISK]
