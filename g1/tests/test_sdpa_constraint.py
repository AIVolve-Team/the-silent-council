import torch
from torch.backends import cuda

from g1.run import sdpa_constraint


def test_on_the_mi300x_bf16_does_not_fall_back_to_math():
    with sdpa_constraint("cuda", torch.bfloat16):
        assert not cuda.math_sdp_enabled()
        assert cuda.flash_sdp_enabled() and cuda.mem_efficient_sdp_enabled()


def test_the_fp32_reference_goes_only_on_math():
    with sdpa_constraint("cuda", torch.float32):
        assert cuda.math_sdp_enabled()
        assert not cuda.flash_sdp_enabled() and not cuda.mem_efficient_sdp_enabled()


def test_off_the_mi300x_no_constraint():
    with sdpa_constraint("mps", torch.float32):
        assert cuda.math_sdp_enabled() and cuda.flash_sdp_enabled()
