import json

import pytest

from g1.agente import problemi

ARGOMENTI = {
    "mittente": "fornitore@example.com",
    "oggetto": "Fattura 12",
    "data": "2026-10-12",
    "pdf_url": "https://example.org/f.pdf",
}
CHIAMATA = {"type": "function", "function": {"name": "esamina_fattura", "arguments": json.dumps(ARGOMENTI)}}


def risposta(**messaggio):
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [], **messaggio}}]}


def test_una_chiamata_vera_a_esamina_fattura_va_bene():
    assert problemi(risposta(tool_calls=[CHIAMATA])) == []


@pytest.mark.parametrize(
    ("difetto", "parola"),
    [
        ({"content": "<tool_call>\n<function=esamina_fattura>\n</function>\n</tool_call>"}, "parser"),
        ({"content": "Certo, ecco l'analisi della fattura."}, "nessuna chiamata"),
        ({"tool_calls": [CHIAMATA], "reasoning_content": "L'utente vuole che esamini…"}, "pensiero"),
        ({"tool_calls": [CHIAMATA], "reasoning": "L'utente vuole che esamini…"}, "pensiero"),
        (
            {"tool_calls": [{"type": "function", "function": {"name": "esamina_fattura", "arguments": "{non è json"}}]},
            "argomenti",
        ),
        (
            {"tool_calls": [{"type": "function", "function": {"name": "paga_subito", "arguments": "{}"}}]},
            "esamina_fattura",
        ),
    ],
)
def test_i_difetti_dell_endpoint_si_riconoscono(difetto, parola):
    trovati = problemi(risposta(**difetto))

    assert any(parola in p for p in trovati), trovati
