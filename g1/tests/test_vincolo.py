import torch
from torch.backends import cuda

from g1.esegui import vincolo_sdpa


def test_sulla_mi300x_il_bf16_non_ripiega_sul_math():
    with vincolo_sdpa("cuda", torch.bfloat16):
        assert not cuda.math_sdp_enabled()
        assert cuda.flash_sdp_enabled() and cuda.mem_efficient_sdp_enabled()


def test_il_riferimento_fp32_va_solo_sul_math():
    with vincolo_sdpa("cuda", torch.float32):
        assert cuda.math_sdp_enabled()
        assert not cuda.flash_sdp_enabled() and not cuda.mem_efficient_sdp_enabled()


def test_fuori_dalla_mi300x_nessun_vincolo():
    with vincolo_sdpa("mps", torch.float32):
        assert cuda.math_sdp_enabled() and cuda.flash_sdp_enabled()
