"""Ogni regola del catalogo con un caso che la fa scattare e uno al limite che non la fa scattare."""

import copy

import pytest

from fatture.archivi import Archivi, Fornitore, Ordine, RigaOrdine, VoceStorico
from fatture.regole import applica_regole, esito_finale

ALFA = "IT01234567890"
IBAN_ALFA = "IT60X0542811101000000123456"


def archivi(rate: int = 1, attivo: bool = True) -> Archivi:
    return Archivi(
        anagrafica={ALFA: Fornitore(ALFA, "Alfa Forniture S.r.l.", IBAN_ALFA, attivo=attivo)},
        ordini={
            "PO-2026-0042": Ordine(
                "PO-2026-0042", ALFA, "2026-08-30", [RigaOrdine(1, "ART-7", "Toner nero", 10, 12.50, 22, 10)], rate
            ),
            "PO-2026-0050": Ordine(
                "PO-2026-0050", "IT11111111111", "2026-08-30", [RigaOrdine(1, "X", "Carta", 1, 5.0, 22, 1)]
            ),
        },
    )


def fattura() -> dict:
    """Una fattura pulita di Alfa sull'ordine PO-2026-0042."""
    return {
        "fornitore": {"id_fiscale": ALFA, "denominazione": "Alfa Forniture S.r.l."},
        "cliente_piva": "IT09876543210",
        "documento": {"tipo": "TD01", "numero": "FT/0012/2026", "data": "2026-09-15", "divisa": "EUR"},
        "ordine": {"numero": "PO-2026-0042"},
        "righe": [
            {
                "n": 1,
                "num_item": "1",
                "codice": "ART-7",
                "descrizione": "Toner nero",
                "quantita": 10,
                "prezzo_unitario": 12.50,
                "prezzo_totale": 125.00,
                "aliquota": 22,
            }
        ],
        "riepilogo": [{"aliquota": 22, "imponibile": 125.00, "imposta": 27.50}],
        "totale_documento": 152.50,
        "pagamento": {
            "modalita": "MP05",
            "iban": IBAN_ALFA,
            "beneficiario": None,
            "scadenza": "2026-10-15",
            "importo": 152.50,
        },
    }


def con(**modifiche) -> dict:
    """La fattura pulita con alcuni campi cambiati, indicati con il percorso: `pagamento__iban="…"`."""
    f = copy.deepcopy(fattura())
    for percorso, valore in modifiche.items():
        *strada, ultimo = percorso.split("__")
        nodo = f
        for pezzo in strada:
            nodo = nodo[int(pezzo)] if pezzo.isdigit() else nodo[pezzo]
        nodo[ultimo] = valore
    return f


def codici(f: dict, a: Archivi | None = None, abbinamenti=None) -> dict[str, str]:
    return {s.codice: s.esito for s in applica_regole(f, a or archivi(), abbinamenti)}


def test_la_fattura_pulita_si_paga():
    scatti = applica_regole(fattura(), archivi())
    assert scatti == []
    assert esito_finale(scatti) == "pagare"


def test_a01_duplicato_esatto_anche_scritto_diverso():
    a = archivi()
    a.storico.append(VoceStorico(ALFA, "FT-12/2026", "2026-08-01", 152.50, "PO-2026-0042"))
    assert codici(fattura(), a) == {"A01": "bloccare"}


def test_a01_stesso_numero_ma_altro_anno_non_e_un_duplicato():
    a = archivi()
    a.storico.append(VoceStorico(ALFA, "FT/0012/2025", "2025-09-15", 152.50, "PO-2026-0042"))
    assert codici(fattura(), a) == {}


def test_a02_duplicato_mascherato():
    a = archivi()
    a.storico.append(VoceStorico(ALFA, "FT/0013/2026", "2026-09-01", 152.50, "PO-2026-0042"))
    assert codici(fattura(), a) == {"A02": "persona"}


def test_a02_un_canone_entro_le_rate_non_e_un_duplicato():
    a = archivi(rate=12)
    a.storico.append(VoceStorico(ALFA, "FT/0013/2026", "2026-09-01", 152.50, "PO-2026-0042"))
    assert codici(fattura(), a) == {}


def test_a03_iban_diverso_da_quello_registrato():
    assert codici(con(pagamento__iban="IT99C0300203280000400162854")) == {"A03": "bloccare"}


def test_a03_lo_stesso_iban_scritto_diverso_va_bene():
    assert codici(con(pagamento__iban="it60 x054 2811 1010 0000 0123 456")) == {}


def test_a04_beneficiario_diverso_dal_fornitore():
    assert codici(con(pagamento__beneficiario="Mario Rossi")) == {"A04": "persona"}


def test_a04_il_fornitore_scritto_in_maiuscolo_va_bene():
    assert codici(con(pagamento__beneficiario="ALFA FORNITURE S.R.L.")) == {}


def test_a05_fornitore_non_in_anagrafica():
    assert codici(con(fornitore__id_fiscale="IT22222222222")) == {"A05": "bloccare"}


def test_a06_fornitore_disattivato():
    assert codici(fattura(), archivi(attivo=False)) == {"A06": "bloccare"}


def test_a07_nessun_riferimento_all_ordine():
    assert codici(con(ordine__numero=None)) == {"A07": "persona"}


def test_a08_ordine_inesistente_o_di_un_altro_fornitore():
    assert codici(con(ordine__numero="PO-2026-9999")) == {"A08": "bloccare"}
    assert codici(con(ordine__numero="PO-2026-0050")) == {"A08": "bloccare"}


@pytest.mark.parametrize(
    ("prezzo", "attesi"),
    [(12.75, {}), (13.00, {"A09a": "persona"}), (13.75, {"A09a": "persona"}), (14.00, {"A09b": "bloccare"})],
)
def test_a09_prezzo_di_riga_sopra_l_ordine(prezzo, attesi):
    # 12,75 è il +2% esatto: si paga. 13,75 è il +10% esatto: persona. 14,00 è il +12%: blocco.
    assert codici(con(righe__0__prezzo_unitario=prezzo)) == attesi


def test_a10_quantita_oltre_il_residuo():
    assert codici(con(righe__0__quantita=11)) == {"A10": "bloccare"}


def test_a10_tutto_il_residuo_va_bene():
    assert codici(con(righe__0__quantita=10)) == {}


def test_a11_una_riga_senza_ordine_la_giudica_il_modello():
    f = fattura()
    f["righe"].append(
        {
            "n": 2,
            "num_item": None,
            "codice": None,
            "descrizione": "Consulenza",
            "quantita": 1,
            "prezzo_unitario": 50.0,
            "prezzo_totale": 50.0,
            "aliquota": 22,
        }
    )
    assert codici(f) == {"A11": "da_giudicare"}
    assert esito_finale(applica_regole(f, archivi())) == "da_giudicare"
    assert codici(f, abbinamenti={2: None}) == {"A11": "persona"}


def test_a11_una_riga_abbinata_dal_modello_si_controlla_come_le_altre():
    f = con(righe__0__num_item=None, righe__0__descrizione="Cartuccia toner nera")
    assert codici(f, abbinamenti={1: 1}) == {}
    assert codici(con(righe__0__num_item=None, righe__0__quantita=11), abbinamenti={1: 1}) == {"A10": "bloccare"}


def test_a12_aliquota_diversa_da_quella_dell_ordine():
    assert codici(con(righe__0__aliquota=10)) == {"A12": "persona"}


def test_a13_totale_diverso_da_imponibile_piu_iva():
    assert codici(con(totale_documento=162.50)) == {"A13": "bloccare"}


def test_a13_un_centesimo_di_differenza_va_bene():
    assert codici(con(totale_documento=152.51)) == {}


def test_l_esito_finale_e_il_piu_grave():
    f = con(pagamento__beneficiario="Mario Rossi", totale_documento=162.50)
    scatti = applica_regole(f, archivi())
    assert {s.codice for s in scatti} == {"A04", "A13"}
    assert esito_finale(scatti) == "bloccare"


def test_ogni_scatto_ha_il_motivo_in_italiano_e_in_inglese():
    (scatto,) = applica_regole(con(pagamento__iban="IT99C0300203280000400162854"), archivi())
    assert "IT99C0300203280000400162854" in scatto.motivo and IBAN_ALFA in scatto.motivo
    assert "IT99C0300203280000400162854" in scatto.motivo_en
