from g1.gsm8k import corretta, estrai_risposta, risposta_giusta


def test_la_risposta_giusta_e_il_numero_dopo_i_quattro_cancelletti():
    assert risposta_giusta("She sells 16 - 3 - 4 = <<16-3-4=9>>9 eggs.\n#### 18") == "18"
    assert risposta_giusta("Total is 1,000.\n#### 1,000") == "1000"


def test_dal_testo_del_modello_vale_l_ultimo_numero_nel_riquadro():
    assert estrai_risposta("So she makes \\boxed{18} dollars.") == "18"
    assert estrai_risposta("First \\boxed{18}, but correcting: \\boxed{20}") == "20"
    assert estrai_risposta("The cost is \\boxed{\\$1,250.00}.") == "1250"


def test_senza_riquadro_vale_l_ultimo_numero_del_testo():
    assert estrai_risposta("She has 3 apples and buys 5 more, so 8 apples.") == "8"
    assert estrai_risposta("Il risultato è -4.5") == "-4.5"


def test_senza_numeri_non_c_e_risposta():
    assert estrai_risposta("I cannot solve this.") is None
    assert estrai_risposta("") is None


def test_due_risposte_sono_uguali_se_lo_sono_come_numeri():
    assert corretta("18", "18.0")
    assert corretta("0.5", ".5")
    assert corretta("-3", "-3")
    assert not corretta("17", "18")
    assert not corretta(None, "18")
