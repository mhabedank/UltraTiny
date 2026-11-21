import struct
import zlib
from dataclasses import replace

import numpy as np
import pytest
import torch

from ultratiny.alphabet import Alphabet
from ultratiny.config import ModelConfig
from ultratiny.export import HEADER_SIZE, read_model, write_model
from ultratiny.model import TinyLM
from ultratiny.reference import Reference, arena_size, seq_sum, ut_exp

AB = Alphabet()
CFG = ModelConfig(vocab_size=AB.vocab_size, d_model=32, n_layers=2, n_heads=4, d_ff=64, ctx_len=48)


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    torch.manual_seed(0)
    model = TinyLM(CFG)
    state = {k: v.detach().numpy() for k, v in model.state_dict().items()}
    path = tmp_path_factory.mktemp("m") / "tiny.utny"
    write_model(path, CFG, state, AB, {"name": "test"})
    return model, path


def test_header_fields_and_crc(tiny):
    _, path = tiny
    data = path.read_bytes()
    assert data[:4] == b"UTNY"
    assert struct.unpack_from("<H", data, 4)[0] == 1
    assert struct.unpack_from("<I", data, 60)[0] == zlib.crc32(data[:60])
    assert struct.unpack_from("<I", data, 40)[0] == len(data) - HEADER_SIZE
    assert struct.unpack_from("<I", data, 44)[0] == zlib.crc32(data[HEADER_SIZE:])
    m = read_model(path)
    assert m.cfg == replace(CFG, norm_eps=float(np.float32(CFG.norm_eps)))
    assert m.meta["name"] == "test"
    assert m.alphabet.symbols == AB.symbols


def test_corrupt_payload_rejected(tiny):
    _, path = tiny
    data = bytearray(path.read_bytes())
    data[-3] ^= 1
    with pytest.raises(ValueError, match="CRC"):
        read_model(bytes(data))


def test_reference_matches_torch_fake_quant(tiny):
    model, path = tiny
    ref = Reference(path)
    ids = AB.prompt_ids("Was ist die Hauptstadt von Frankreich?")
    model.qat = True
    with torch.no_grad():
        want = model(torch.tensor([ids]))[0].numpy()
    for i, t in enumerate(ids):
        got = ref.feed(t)
        assert np.argmax(got) == np.argmax(want[i]) or np.max(np.abs(got - want[i])) < 1e-3
        assert np.max(np.abs(got - want[i])) < 2e-2


def test_reference_deterministic_and_rewind(tiny):
    _, path = tiny
    ref = Reference(path)
    a = ref.generate("Hallo", max_len=10)
    b = ref.generate("Hallo", max_len=10)
    assert a["tokens"] == b["tokens"]
    ref.reset()
    ref.feed(1)
    la = ref.feed(10).copy()
    ref.feed(11)
    ref.rewind(1)
    ref.rewind(1)
    assert np.array_equal(ref.feed(10), la)


def test_exp_and_seq_sum():
    x = np.linspace(-79, 0, 1000, dtype=np.float32)
    assert np.allclose(ut_exp(x), np.exp(x.astype(np.float64)), rtol=2e-6, atol=1e-37)
    assert ut_exp(np.array([-100.0], dtype=np.float32))[0] == 0
    v = np.array([1e8, 1.0, -1e8, 1.0], dtype=np.float32)
    assert seq_sum(v) == np.float32(1.0)  # ((1e8 + 1) - 1e8) + 1 in float32


def test_arena_size_v1_within_budget():
    v1 = ModelConfig(vocab_size=AB.vocab_size)
    assert arena_size(v1) <= 128 * 1024 * 0.9
