# NOTICE

The code in this folder belongs to the team. The derived data in `measurement-set/` comes from three third-party datasets, all licensed under the Creative Commons Attribution 4.0 International licence (CC BY 4.0, https://creativecommons.org/licenses/by/4.0/), and stays under that licence.

## CUAD v1

- **Source:** The Atticus Project, https://github.com/TheAtticusProject/cuad, commit `67faa0e6023b04fcaae6cc09497ab00e5d63a2a2`.
- **Citation:** Dan Hendrycks, Collin Burns, Anya Chen, Spencer Ball, "CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review", NeurIPS 2021 Datasets and Benchmarks.
- **Licence:** CC BY 4.0.
- **Changes:** we use 19 of the 41 categories; from each (contract, category) pair we derive a yes/no answer ("yes" if there is at least one annotated piece); we keep a sample of 25 contracts.

## ContractNLI

- **Source:** Stanford NLP, https://stanfordnlp.github.io/contract-nli/, file `contract-nli.zip`.
- **Citation:** Yuta Koreeda, Christopher D. Manning, "ContractNLI: A Dataset for Document-level Natural Language Inference for Contracts", Findings of EMNLP 2021.
- **Licence:** CC BY 4.0, with Hitachi America, Ltd.'s "Terms and Conditions of Use" included in the archive, which refer to the same licence.
- **Changes:** from each (NDA, hypothesis) pair we derive a yes/no answer ("yes" if the label is Contradiction), keeping the original label; we keep a sample of 25 NDAs.

## Multilingual CLAUDETTE (Italian ToS)

- **Source:** https://github.com/lt-nlp-lab-unibo/Multilingual-Unfair-Clause-Detection, commit `04d9878bfca0e1e17e7dd1cf7bd17fc4ce5fcd12`, folder `corpus/original_xml/it`.
- **Citation:** Andrea Galassi, Francesca Lagioia, Agnieszka Jabłonowska, Marco Lippi, "Unfair clause detection in terms of service across multiple languages", Artificial Intelligence and Law, 2024, https://doi.org/10.1007/s10506-024-09398-7.
- **Licence:** CC BY 4.0.
- **Changes:** from each (ToS, category) pair we derive a yes/no answer ("yes" if at least one clause has grade 2 or 3); we fixed two badly closed tags, in `Weebly.xml` (`</ter2>` → `</ch2>`) and in `Yelp.xml` (`</ch3>` → `</ch2>`), as in the English version of the same ToS.

## Tokenizer

To count tokens we use the Qwen3-14B tokenizer (https://huggingface.co/Qwen/Qwen3-14B, revision `40c069824f4251a91eefaf281ebe4c544efd3e18`, Apache 2.0 licence). The script downloads it and does not redistribute it.
