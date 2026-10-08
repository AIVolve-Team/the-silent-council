import jsonschema
import pytest
from fatture.genera import genera_insieme

from pipeline.schemi import SCHEMA_IMPEGNO, SCHEMA_LETTURA, lettura_da, schema_proposta


@pytest.fixture(scope="module")
def casi():
    return genera_insieme("sviluppo").casi


def test_l_impegno_di_un_estrattore_perfetto_rispetta_lo_schema(casi):
    for caso in casi:
        jsonschema.validate(caso.impegno, SCHEMA_IMPEGNO)


def test_la_lettura_ha_solo_gli_otto_dati_critici(casi):
    lettura = lettura_da(casi[0].impegno)
    jsonschema.validate(lettura, SCHEMA_LETTURA)
    assert lettura["pagamento"].keys() == {"iban", "importo", "scadenza"}
    assert "righe" not in lettura


@pytest.mark.parametrize("sbagliato", [{"pagamento__iban": "it60 x054"}, {"documento__data": "15/09/2026"}])
def test_lo_schema_impone_i_formati_di_46(casi, sbagliato):
    import copy

    impegno = copy.deepcopy(casi[0].impegno)
    ((percorso, valore),) = sbagliato.items()
    sezione, campo = percorso.split("__")
    impegno[sezione][campo] = valore
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(impegno, SCHEMA_IMPEGNO)


def test_la_proposta_chiede_l_abbinamento_delle_sole_righe_libere():
    schema = schema_proposta([2, 5])
    proposta = {
        "iban": "IT60X0542811101000000123456", "importo": 152.5, "esito": "pagare",
        "motivazione": "Conforme all'ordine.",
        "abbinamenti": [{"riga": 2, "riga_ordine": 1}, {"riga": 5, "riga_ordine": None}],
    }  # fmt: skip
    jsonschema.validate(proposta, schema)
    proposta["abbinamenti"] = [{"riga": 3, "riga_ordine": 1}, {"riga": 5, "riga_ordine": None}]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(proposta, schema)
    assert "abbinamenti" not in schema_proposta([])["properties"]


def test_il_riferimento_alla_riga_d_ordine_e_solo_un_numero(casi):
    import copy

    impegno = copy.deepcopy(next(c.impegno for c in casi if c.impegno["righe"][0]["num_item"]))
    impegno["righe"][0]["num_item"] = "CAF-1KG"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(impegno, SCHEMA_IMPEGNO)
