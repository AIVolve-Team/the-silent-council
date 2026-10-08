import pytest

from g1.gsm8k import FILE_PROBLEMI, carica_problemi


def test_sono_i_primi_100_problemi_del_test_ufficiale():
    problemi = carica_problemi()
    assert len(problemi) == 100
    primo = problemi[0]
    assert primo.id == "gsm8k-test-0000"
    assert primo.domanda.startswith("Janet’s ducks lay 16 eggs per day.")
    assert primo.risposta == "18"
    assert problemi[-1].id == "gsm8k-test-0099"


def test_se_ne_possono_prendere_meno():
    assert [p.id for p in carica_problemi(2)] == ["gsm8k-test-0000", "gsm8k-test-0001"]


def test_un_file_toccato_non_si_usa(tmp_path):
    toccato = tmp_path / "gsm8k.jsonl"
    toccato.write_text(FILE_PROBLEMI.read_text().replace("16 eggs", "17 eggs", 1))
    with pytest.raises(ValueError, match="impronta"):
        carica_problemi(file=toccato)
