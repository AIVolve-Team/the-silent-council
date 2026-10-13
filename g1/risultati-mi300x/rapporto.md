## G1: il motore sulla MI300X

| Giro | Precisione | Token generati | Token letti | Secondi per problema | Messaggi troncati |
|---|---|---|---|---|---|
| testo | 97,0% | 124.790 | 245.092 | 34,3 | 2 |
| telepatia (10 passi) | 96,0% | 23.697 | 47.192 | 7,6 | 0 |
| senza pensieri (m=0) | 98,0% | 16.135 | 47.192 | 4,7 | 0 |

- **Token generati in telepatia:** −81% rispetto al testo (soglia: almeno −50%) ✓
- **Precisione:** telepatia meno testo = −1,0 punti → zona **dimostrato**
- **Memoria:** motore e Qwen3.6 sulla stessa MI300X senza errori ✓
- **Pesi dei due modelli:** 99,9 GB: la frase *"su una H100 non ci starebbe"* si può dire (serve più di 80 GB,)

**G1 passa**

