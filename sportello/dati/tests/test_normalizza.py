from decimal import Decimal

from fatture.normalizza import iban, id_fiscale, importo, numero_documento, stesso_importo


def test_il_numero_del_documento_si_confronta_come_in_a01():
    assert numero_documento("FT/0012/2026") == numero_documento("ft 12 2026") == "ft 12 2026"
    assert numero_documento("FT-12/2026") == "ft 12 2026"
    assert numero_documento("INV-2026-007") == "inv 2026 7"
    assert numero_documento("FT/0012/2026") != numero_documento("FT/0021/2026")


def test_iban_senza_spazi_e_in_maiuscolo():
    assert iban(" it60 x054 2811 1010 0000 0123 456 ") == "IT60X0542811101000000123456"


def test_identificativo_fiscale_con_il_prefisso_del_paese():
    assert id_fiscale("it 01234567890") == "IT01234567890"
    assert id_fiscale("DE 123.456.789") == "DE123456789"


def test_gli_importi_hanno_due_decimali_arrotondati_per_eccesso_a_meta():
    assert importo("1250.005") == Decimal("1250.01")
    assert importo(12.5) == Decimal("12.50")
    assert importo("1.004") == Decimal("1.00")


def test_due_importi_sono_uguali_entro_un_centesimo():
    assert stesso_importo("100.00", "100.01")
    assert not stesso_importo("100.00", "100.02")
