import jsonschema
import pytest
from fatture.genera import genera_insieme

from pipeline.schemi import SCHEMA_IMPEGNO, SCHEMA_LETTURA, lettura_da, schema_abbinamenti, schema_proposta


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


def test_l_abbinatore_risponde_solo_per_le_righe_libere_e_il_decisore_non_abbina():
    schema = schema_abbinamenti([2, 5])
    risposta = {"abbinamenti": [{"riga": 2, "riga_ordine": 1}, {"riga": 5, "riga_ordine": None}]}
    jsonschema.validate(risposta, schema)
    risposta["abbinamenti"] = [{"riga": 3, "riga_ordine": 1}, {"riga": 5, "riga_ordine": None}]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(risposta, schema)
    assert "abbinamenti" not in schema_proposta()["properties"]  # il decisore vede la memoria: non abbina (F7 di «Catalogo degli attacchi»)


def test_il_riferimento_alla_riga_d_ordine_e_solo_un_numero(casi):
    import copy

    impegno = copy.deepcopy(next(c.impegno for c in casi if c.impegno["righe"][0]["num_item"]))
    impegno["righe"][0]["num_item"] = "CAF-1KG"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(impegno, SCHEMA_IMPEGNO)
