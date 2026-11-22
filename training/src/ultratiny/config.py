"""Model / data / training configuration (data-model.md ModelConfig)."""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ModelConfig:
    vocab_size: int = 96
    d_model: int = 128
    n_layers: int = 4
    n_heads: int = 4
    n_kv_heads: int = 1
    d_ff: int = 384
    ctx_len: int = 256
    norm_eps: float = 1e-5

    @property
    def head_dim(self) -> int:
        return self.d_model // self.n_heads

    def validate(self) -> None:
        if self.d_model % self.n_heads != 0:
            raise ValueError("d_model must be divisible by n_heads")
        if self.n_kv_heads != 1:
            raise ValueError("format v1 supports only multi-query attention (n_kv_heads = 1)")
        if not 0 < self.vocab_size <= 96:
            raise ValueError("vocab_size must be in 1..96")
        if self.head_dim % 4 != 0:
            raise ValueError("head_dim must be a multiple of 4 (alignment)")
        if self.ctx_len > 4096:
            raise ValueError("ctx_len too large")


@dataclass(frozen=True)
class DataConfig:
    facts: list[str] = field(default_factory=list)
    templates: list[str] = field(default_factory=list)
    topics: str = "data/topics.toml"
    demo_prompts: str = "data/demo_prompts.tsv"
    noisy_copies: int = 2
    max_answer_len: int = 200
    # Optional LLM augmentation snapshots (train-only; see ultratiny/augment.py).
    augment_phrasings: list[str] = field(default_factory=list)
    augment_templates: list[str] = field(default_factory=list)
    augment_refusals: list[str] = field(default_factory=list)
    refusal_relation: str = "abweisen"
    # Hybrid chemistry teacher (specs/006-hybrid-chemielehrer): function output + fact table.
    hybrid: bool = False
    hybrid_templates: str = "data/templates/hybrid.toml"
    element_facts: str = "data/facts/wikidata_elemente_chemie.tsv"
    compound_facts: list[str] = field(default_factory=list)  # name/formula TSVs (formel_von)
    acidbase_facts: str = ""
    equation_facts: str = ""
    test_facts: str = ""
    alias_facts: str = ""
    explanations: list[str] = field(default_factory=list)  # reviewed short explanations
    free_facts: list[str] = field(default_factory=list)  # persona + refusals (free relations)
    kurzarbeit: str = ""
    kurzarbeit_sha256: str = ""
    forms_per_combo: int = 4
    combo_holdout: float = 0.10
    explain_holdout: float = 0.10
    # Share of training lines per kind (research R7); the rest is greetings/refusals/unknown.
    mix_facts: float = 0.55
    mix_explain: float = 0.30


@dataclass(frozen=True)
class TrainConfig:
    steps: int = 3000
    batch_size: int = 64
    lr: float = 3e-3
    min_lr: float = 3e-4
    warmup_steps: int = 100
    weight_decay: float = 0.01
    grad_clip: float = 1.0
    dropout: float = 0.1
    num_threads: int = 4
    qat_steps: int = 0
    qat_trigger_pp: float = 2.0


@dataclass(frozen=True)
class EvalConfig:
    demo_min: float = 0.80
    heldout_min: float = 0.60
    max_edit_ratio: float = 0.10
    golden_cases: int = 24
    refusal_relation: str = "abweisen"
    refusal_min: float = 0.0
    false_refusal_max: float = 1.0
    # Hybrid thresholds (contracts/eval-sets.md); 0 / 1 disable a check.
    combo_min: float = 0.0
    family_min: float = 0.0
    kurzarbeit_min: float = 0.0
    wrong_fact_max: float = 1.0
    explain_min: float = 0.0


@dataclass(frozen=True)
class Config:
    name: str
    model: ModelConfig
    data: DataConfig
    train: TrainConfig
    eval: EvalConfig
    path: Path

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "model": asdict(self.model),
            "data": asdict(self.data),
            "train": asdict(self.train),
            "eval": asdict(self.eval),
        }


def load_config(path: str | Path) -> Config:
    path = Path(path)
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    model = ModelConfig(**raw.get("model", {}))
    model.validate()
    return Config(
        name=raw.get("name", path.stem),
        model=model,
        data=DataConfig(**raw.get("data", {})),
        train=TrainConfig(**raw.get("train", {})),
        eval=EvalConfig(**raw.get("eval", {})),
        path=path,
    )
