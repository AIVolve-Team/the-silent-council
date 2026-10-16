# NOTICE

Il codice di questa cartella è del team. I dati derivati in `set-di-misura/` vengono da tre dataset di terzi, tutti con licenza Creative Commons Attribution 4.0 International (CC BY 4.0, https://creativecommons.org/licenses/by/4.0/), e restano sotto quella licenza.

## CUAD v1

- **Fonte:** The Atticus Project, https://github.com/TheAtticusProject/cuad, commit `67faa0e6023b04fcaae6cc09497ab00e5d63a2a2`.
- **Citazione:** Dan Hendrycks, Collin Burns, Anya Chen, Spencer Ball, "CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review", NeurIPS 2021 Datasets and Benchmarks.
- **Licenza:** CC BY 4.0.
- **Modifiche:** usiamo 19 delle 41 categorie; da ogni coppia (contratto, categoria) ricaviamo una risposta sì/no ("sì" se c'è almeno un pezzo annotato); teniamo un campione di 25 contratti.

## ContractNLI

- **Fonte:** Stanford NLP, https://stanfordnlp.github.io/contract-nli/, file `contract-nli.zip`.
- **Citazione:** Yuta Koreeda, Christopher D. Manning, "ContractNLI: A Dataset for Document-level Natural Language Inference for Contracts", Findings of EMNLP 2021.
- **Licenza:** CC BY 4.0, con i "Terms and Conditions of Use" di Hitachi America, Ltd. inclusi nell'archivio, che rimandano alla stessa licenza.
- **Modifiche:** da ogni coppia (NDA, ipotesi) ricaviamo una risposta sì/no ("sì" se l'etichetta è Contradiction), tenendo l'etichetta originale; teniamo un campione di 25 NDA.

## CLAUDETTE multilingue (ToS italiani)

- **Fonte:** https://github.com/lt-nlp-lab-unibo/Multilingual-Unfair-Clause-Detection, commit `04d9878bfca0e1e17e7dd1cf7bd17fc4ce5fcd12`, cartella `corpus/original_xml/it`.
- **Citazione:** Andrea Galassi, Francesca Lagioia, Agnieszka Jabłonowska, Marco Lippi, "Unfair clause detection in terms of service across multiple languages", Artificial Intelligence and Law, 2024, https://doi.org/10.1007/s10506-024-09398-7.
- **Licenza:** CC BY 4.0.
- **Modifiche:** da ogni coppia (ToS, categoria) ricaviamo una risposta sì/no ("sì" se almeno una clausola ha grado 2 o 3); abbiamo corretto due tag chiusi male, in `Weebly.xml` (`</ter2>` → `</ch2>`) e in `Yelp.xml` (`</ch3>` → `</ch2>`), come nella versione inglese degli stessi ToS.

## Tokenizer

Per contare i token usiamo il tokenizer di Qwen3-14B (https://huggingface.co/Qwen/Qwen3-14B, revisione `40c069824f4251a91eefaf281ebe4c544efd3e18`, licenza Apache 2.0). Lo script lo scarica e non lo ridistribuisce.
