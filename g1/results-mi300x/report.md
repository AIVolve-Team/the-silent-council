## G1: the engine on the MI300X

| Run | Accuracy | Tokens generated | Tokens read | Seconds per problem | Truncated messages |
|---|---|---|---|---|---|
| text | 97.0% | 124,790 | 245,092 | 34.3 | 2 |
| telepathy (10 steps) | 96.0% | 23,697 | 47,192 | 7.6 | 0 |
| no thoughts (m=0) | 98.0% | 16,135 | 47,192 | 4.7 | 0 |

- **Tokens generated in telepathy:** −81% compared with text (threshold: at least −50%) ✓
- **Accuracy:** telepathy minus text = −1.0 points → zone **demonstrated**
- **Memory:** engine and Qwen3.6 on the same MI300X without errors ✓
- **Weights of the two models:** 99.9 GB: the line *"it wouldn't fit on an H100"* can be said (it takes more than 80 GB)

**G1 passes**

