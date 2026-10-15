"""I comandi del motore: `pensa`, `scrivi` e `consegna`, più il ricalcolo dei pensieri per le prove di «Eval pre-registrato»."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import torch
from transformers import DynamicCache

from .controllo import Controllo, ControlloCatena, ControlloImpronta, Esito
from .messaggio import (
    TELEPATIA,
    TESTO,
    VERSIONE,
    MessaggioLatente,
    cache_da,
    cache_da_pezzi,
    hash_inizio,
    sha256,
    taglia,
)
from .modello import Generazione, Modello
from .sigillo import firma

# Con questi nomi i template di LatentMAS sovrascrivono il prompt: qui non si usano.
NOMI_VIETATI = {"planner", "critic", "refiner", "judger"}


@dataclass(frozen=True)
class Agente:
    nome: str
    istruzioni: str

    def __post_init__(self) -> None:
        if self.nome.lower() in NOMI_VIETATI:
            raise ValueError(f"Nome di ruolo vietato: {self.nome}")


@dataclass
class Consegna:
    esito: Esito
    copia: MessaggioLatente | None


def token_ammessi(ammessi) -> list[int]:
    """lm-format-enforcer 0.11 restituisce una `TokenList`: una lista di id, oppure una maschera di bit int32."""
    if not getattr(ammessi, "use_bitmask", False):
        return list(getattr(ammessi, "allowed_tokens", ammessi))
    return maschera_ammessi(ammessi).nonzero().flatten().tolist()


def maschera_ammessi(ammessi) -> torch.Tensor:
    """La stessa `TokenList` come maschera booleana, senza passare da una lista Python: dentro una stringa JSON
    sono ammessi quasi tutti i token, e una lista da 150.000 id a ogni passo rallenta la generazione."""
    if not getattr(ammessi, "use_bitmask", False):
        maschera = torch.zeros(max(ammessi.allowed_tokens, default=-1) + 1, dtype=torch.bool)
        maschera[list(ammessi.allowed_tokens)] = True
        return maschera
    bit = (ammessi.allowed_tokens.unsqueeze(1) >> torch.arange(32, dtype=torch.int32)) & 1
    return bit.flatten().bool()


def con_colleghi(testo: str, ricevuti: list[MessaggioLatente]) -> str:
    """In modalità testo chi riceve legge ciò che i precedenti hanno scritto, mai ciò che hanno letto."""
    scritti = [m for m in ricevuti if m.testo]
    if not scritti:
        return testo
    righe = "\n\n".join(f"[{m.mittente}]\n{m.testo}" for m in scritti)
    return f"Messaggi dei colleghi:\n\n{righe}\n\n---\n\n{testo}"


class Motore:
    def __init__(
        self,
        modello: Modello,
        *,
        controlli: list[Controllo] | None = None,
        firme: dict | None = None,
        registro: Path | None = None,
        max_token_testo: int = 512,
    ) -> None:
        self.modello = modello
        self.controlli: list[Controllo] = [
            ControlloImpronta(),
            ControlloCatena(modello.nome, modello.revisione),
            *(controlli or []),
        ]
        self.firme = firme or {}
        self.registro = registro
        self.max_token_testo = max_token_testo
        self._dati_tokenizer = None

    # --- pensa ----------------------------------------------------------------------------------------

    def pensa(
        self,
        agente: Agente,
        testo: str,
        ricevuti: list[MessaggioLatente],
        *,
        sessione: str,
        passi_latenti: int = 10,
        modalita: str = TELEPATIA,
        destinatario: str | None = None,
    ) -> MessaggioLatente:
        """L'agente legge il suo testo sopra i messaggi ricevuti e restituisce il suo messaggio latente.

        In modalità testo scrive invece la sua analisi, al massimo `max_token_testo` token.
        """
        if modalita == TESTO:
            prompt = self.modello.prompt(agente.istruzioni, con_colleghi(testo, ricevuti), pensiero=False)
            scritto = self.modello.genera(DynamicCache(), self.modello.codifica(prompt), self.max_token_testo)
            etichetta = self._etichetta(agente, sessione, ricevuti, destinatario, modalita, prompt)
            etichetta |= {"inizio": None, "n_lettura": 0, "passi_latenti": 0}
            etichetta |= {"token_letti": scritto.token_letti, "token_generati": scritto.token_generati}
            return self._chiudi(MessaggioLatente(etichetta, testo=scritto.testo))

        cache = cache_da(ricevuti)
        inizio = cache.get_seq_length()
        prompt = self.modello.prompt(agente.istruzioni, testo, pensiero=True)
        ids = self.modello.codifica(prompt)
        stati = self.modello.passi_latenti(cache, self.modello.leggi(ids, cache), passi_latenti)
        n = ids.shape[1]
        etichetta = self._etichetta(agente, sessione, ricevuti, destinatario, modalita, prompt)
        etichetta |= {"inizio": inizio, "n_lettura": n, "passi_latenti": passi_latenti}
        etichetta |= {"token_letti": n, "token_generati": 0}
        messaggio = MessaggioLatente(
            etichetta,
            taglia(cache, inizio, inizio + n),
            taglia(cache, inizio + n, inizio + n + passi_latenti),
            stati,
        )
        return self._chiudi(messaggio)

    def _etichetta(self, agente, sessione, ricevuti, destinatario, modalita, prompt) -> dict:
        return {
            "mittente": agente.nome,
            "destinatario": destinatario,
            "sessione": sessione,
            "numero": len(ricevuti) + 1,
            "hash_precedente": ricevuti[-1].impronta if ricevuti else hash_inizio(sessione),
            "modello": self.modello.nome,
            "revisione": self.modello.revisione,
            "versione_motore": VERSIONE,
            "dtype": str(self.modello.dtype).removeprefix("torch."),
            "n_layer": self.modello.n_layer,
            "modalita": modalita,
            "hash_testo_letto": sha256(prompt.encode("utf-8")),
            "impegno": None,
        }

    def _chiudi(self, messaggio: MessaggioLatente) -> MessaggioLatente:
        messaggio.chiudi()
        if messaggio.mittente in self.firme:
            firma(messaggio, self.firme[messaggio.mittente])
        return messaggio

    def con_impegno(self, messaggio: MessaggioLatente, impegno: dict) -> MessaggioLatente:
        """Mette l'impegno nell'etichetta, poi richiude e rifirma: così l'impegno è sigillato."""
        nuovo = messaggio.copia()
        nuovo.etichetta["impegno"] = impegno
        return self._chiudi(nuovo)

    # --- scrivi ---------------------------------------------------------------------------------------

    def scrivi(
        self,
        agente: Agente,
        testo: str,
        ricevuti: list[MessaggioLatente],
        *,
        modalita: str = TELEPATIA,
        schema: dict | None = None,
        ordine_campi: bool = False,
        max_spazi: int | None = None,
        max_token: int | None = None,
        osserva: list[int] | None = None,
    ) -> Generazione:
        """L'agente scrive partendo dai messaggi ricevuti: nota, verdetto o decisione. Lavora su una copia della
        memoria.

        Con uno schema JSON la decodifica è vincolata. `ordine_campi` impone l'ordine di `required` (per esempio
        prima le obiezioni, poi il verdetto); `max_spazi` limita gli spazi di fila: con 1 restano gli spazi fra le
        parole e spariscono i rientri, che consumano token.
        `osserva` registra a ogni passo i logprob di quei token, per la confidenza.
        """
        if modalita == TESTO:
            cache, testo = DynamicCache(), con_colleghi(testo, ricevuti)
        else:
            cache = cache_da(ricevuti)
        ids = self.modello.codifica(self.modello.prompt(agente.istruzioni, testo, pensiero=False))
        consentiti = None if schema is None else self._vincolo(schema, ordine_campi, max_spazi)
        return self.modello.genera(
            cache, ids, max_token or self.max_token_testo, consentiti=consentiti, osserva=osserva
        )

    def _vincolo(self, schema: dict, ordine_campi: bool, max_spazi: int | None):
        import sys

        try:
            from transformers.tokenization_utils import PreTrainedTokenizerBase  # noqa: F401
        except ImportError:
            # lm-format-enforcer 0.11.3 importa PreTrainedTokenizerBase da un modulo che transformers 5 ha tolto
            import transformers.tokenization_utils_base as base

            sys.modules["transformers.tokenization_utils"] = base
        from lmformatenforcer import CharacterLevelParserConfig, JsonSchemaParser, TokenEnforcer
        from lmformatenforcer.integrations.transformers import build_token_enforcer_tokenizer_data

        if self._dati_tokenizer is None:
            self._dati_tokenizer = build_token_enforcer_tokenizer_data(self.modello.tokenizer)
        parser = JsonSchemaParser(schema)
        vincolo = TokenEnforcer(self._dati_tokenizer, parser)
        # lm-format-enforcer 0.11.3: TokenEnforcer sostituisce la configurazione del parser con una che ha solo
        # l'alfabeto del tokenizer, e così ordine dei campi e limite degli spazi tornano ai valori predefiniti.
        # La configurazione giusta si rimette dopo, con lo stesso alfabeto.
        configurazione = CharacterLevelParserConfig(
            alphabet=self._dati_tokenizer.tokenizer_alphabet, force_json_field_order=ordine_campi
        )
        if max_spazi is not None:
            configurazione.max_consecutive_whitespaces = max_spazi
        parser.config = configurazione
        return lambda sequenza: maschera_ammessi(vincolo.get_allowed_tokens(sequenza))

    # --- consegna -------------------------------------------------------------------------------------

    def consegna(self, messaggio: MessaggioLatente, catena: list[MessaggioLatente]) -> Consegna:
        """Porta il messaggio al destinatario passando sempre dai controlli. Il destinatario riceve una copia,
        e solo se tutti dicono "passa"."""
        for controllo in self.controlli:
            esito = controllo(messaggio, catena)
            if not esito.passa:
                self._registra_incidente(messaggio, esito)
                return Consegna(esito, None)
        return Consegna(Esito(True, "consegna"), messaggio.copia())

    def verifica_catena(self, catena: list[MessaggioLatente]) -> Esito:
        """Tutti i controlli su tutta la catena, prima che esca il risultato finale."""
        for i, messaggio in enumerate(catena):
            for controllo in self.controlli:
                esito = controllo(messaggio, catena[:i])
                if not esito.passa:
                    self._registra_incidente(messaggio, esito)
                    return esito
        return Esito(True, "catena intera")

    def _registra_incidente(self, messaggio: MessaggioLatente, esito: Esito) -> None:
        """Registro dell'incidente e messaggio intero salvato come prova."""
        if self.registro is None:
            return
        self.registro.mkdir(parents=True, exist_ok=True)
        ora = datetime.now(UTC)
        sessione = re.sub(r"[^\w.-]", "_", str(messaggio.etichetta.get("sessione")))
        nome = f"incidente-{sessione}-{messaggio.etichetta.get('numero')}-{ora:%Y%m%dT%H%M%S%f}"
        voce = {"ora": ora.isoformat(), "controllo": esito.controllo, "motivo": esito.motivo}
        voce["etichetta"] = messaggio.etichetta
        (self.registro / f"{nome}.json").write_text(json.dumps(voce, indent=2, ensure_ascii=False))
        messaggio.salva(self.registro / f"{nome}.safetensors", completo=True)

    # --- prove di “Pre-registered eval” ---------------------------------------------------------------------------------

    @torch.no_grad()
    def ricalcola_pensieri(
        self,
        messaggio: MessaggioLatente,
        catena: list[MessaggioLatente],
        *,
        stati_da: torch.Tensor | None = None,
        origine: str | None = None,
    ) -> MessaggioLatente:
        """Rifà la KV dei passi latenti dagli stati nascosti, nella posizione del messaggio.

        Con gli stati del messaggio stesso deve ridare la sua KV. Con quelli di un altro messaggio è la prova
        "pensieri di un altro contratto": la lettura resta, i pensieri cambiano.
        """
        stati = messaggio.stati if stati_da is None else stati_da
        passi = messaggio.n_pensieri
        if stati.shape[0] != passi + 1:
            raise ValueError(f"servono {passi + 1} stati, ce ne sono {stati.shape[0]}")
        cache = cache_da_pezzi([p for m in catena for p in (m.kv_lettura, m.kv_pensieri)] + [messaggio.kv_lettura])
        inizio = cache.get_seq_length()
        for t in range(passi):
            self.modello.passo_latente(stati[t : t + 1].to(self.modello.dispositivo), cache)
        nuovo = messaggio.copia()
        nuovo.kv_pensieri = taglia(cache, inizio, inizio + passi)
        nuovo.stati = stati.clone()
        if stati_da is not None:
            nuovo.etichetta["pensieri_da"] = origine or "altro messaggio"
        return self._chiudi(nuovo)
