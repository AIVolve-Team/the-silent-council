"""Il modello per lunghezza del contratto: i contratti corti a un modello, quelli lunghi a un altro.

Una regola sola, senza LLM: si contano i token del contratto con il tokenizer del modello dei corti e si confronta con
la soglia. Su 80 contratti CUAD train, in telepatia, sotto i 6.000 token Qwen3-14B e Gemma 4 31B si equivalgono e Qwen
è due volte più veloce; sopra, Gemma trova più clausole (+12,5 punti di F1). Il router fa 77,4 di F1 contro 68,6 di
Qwen da solo e 75,6 di Gemma da solo (spike di «Spike del router», branch `spike/gemma4`).
"""

from __future__ import annotations

from collections.abc import Callable

# La mediana di lunghezza degli 80 contratti della prova, in token di Qwen3-14B: circa 9 pagine.
SOGLIA = 6_000

Revisiona = Callable[..., dict]


class Instradamento:
    """Fa le veci del Consiglio per il `Revisore`: sceglie il modello e passa la chiamata a quello.

    `corto` esamina i contratti fino a `soglia` token compresi, `lungo` quelli più lunghi. La revisione porta già il
    nome del modello (`modello`); qui si aggiungono i token contati e la soglia, così il caso dice perché è andato lì.
    """

    def __init__(self, corto: Revisiona, lungo: Revisiona, conta: Callable[[str], int], soglia: int = SOGLIA) -> None:
        self.corto = corto
        self.lungo = lungo
        self.conta = conta
        self.soglia = soglia

    def __call__(self, id_caso: str, testo: str, modalita: str, benchmark: str = "dimostrativo") -> dict:
        token = self.conta(testo)
        revisiona = self.lungo if token > self.soglia else self.corto
        revisione = revisiona(id_caso, testo, modalita, benchmark)
        return revisione | {"instradamento": {"token_contratto": token, "soglia": self.soglia}}
