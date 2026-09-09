"""Reproduction of the `geo_prior` (Mac Aodha, Cole & Perona,
"Presence-Only Geographical Priors for Fine-Grained Image Classification")
FCNet architecture, location/date encoding, and presence-only embedding
loss, adapted from the vendored upstream at
``research/third_party/geo_prior/`` (commit
257dc7e30f3cc6bf02fbec55ee878724d077fe61 - see
``research/third_party/geo_prior/FlyTech_VENDORING.md``).

This is an independent reproduction for FlyTech S3 Milestone 2, not the
paper's released code path used verbatim: the upstream ``geo_prior/`` module
is written as a set of top-level scripts (``import utils as ut`` inside
``losses.py``, no package `__init__.py`), so this file re-expresses the same
architecture, encoding, and loss as an importable module rather than adding
the vendored tree to ``sys.path``.

**Hard reproduction limitation**: upstream's default loss includes a
``'user'`` (recorder-identity) term. No user/recorder-id field exists
anywhere in this project's occurrence schema
(:class:`s3_ecological.interfaces.occurrence.RawOccurrenceRecord`), so only
the non-user ``full_loss`` variant is implemented here - ``FCNet`` therefore
has no ``user_emb`` layer at all (upstream always allocates one, unused,
when the user term is disabled; omitting it here is a deliberate,
documented simplification, not a behavioural difference for the loss that
is actually computed).

Torch-only: this module must never be imported by ``src/s3_ecological``
(``pyproject.toml``'s only hard dependency is ``pydantic``). It is executed
via the isolated venv at ``data/local/m2/s1/venv/Scripts/python.exe``.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Literal

import numpy as np
import torch
from torch import nn


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True, warn_only=True)


class ResLayer(nn.Module):
    """Verbatim structure of upstream ``geo_prior/models.py::ResLayer``."""

    def __init__(self, linear_size: int) -> None:
        super().__init__()
        self.nonlin1 = nn.ReLU(inplace=True)
        self.nonlin2 = nn.ReLU(inplace=True)
        self.dropout1 = nn.Dropout()
        self.w1 = nn.Linear(linear_size, linear_size)
        self.w2 = nn.Linear(linear_size, linear_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = self.w1(x)
        y = self.nonlin1(y)
        y = self.dropout1(y)
        y = self.w2(y)
        y = self.nonlin2(y)
        return x + y


class FCNet(nn.Module):
    """Adapted from upstream ``geo_prior/models.py::FCNet``, with the unused
    ``user_emb`` layer omitted (see module docstring). ``forward`` returns
    the raw per-class sigmoid score, matching upstream exactly."""

    def __init__(self, num_inputs: int, num_classes: int, num_filts: int) -> None:
        super().__init__()
        self.class_emb = nn.Linear(num_filts, num_classes, bias=False)
        self.feats = nn.Sequential(
            nn.Linear(num_inputs, num_filts),
            nn.ReLU(inplace=True),
            ResLayer(num_filts),
            ResLayer(num_filts),
            ResLayer(num_filts),
            ResLayer(num_filts),
        )

    def forward(self, x: torch.Tensor, *, return_feats: bool = False) -> torch.Tensor:
        loc_emb = self.feats(x)
        if return_feats:
            return loc_emb
        return torch.sigmoid(self.class_emb(loc_emb))


@dataclass(frozen=True)
class EncodingParams:
    """The subset of upstream ``params`` this reproduction actually uses.
    Only ``loc_encode='encode_cos_sin'`` is implemented - the only encoding
    used anywhere in the M2-C config grid."""

    loc_encode: Literal["encode_cos_sin"] = "encode_cos_sin"
    use_date_feats: bool = False
    date_encode: Literal["encode_cos_sin"] = "encode_cos_sin"


def num_input_feats(params: EncodingParams) -> int:
    """4 dims for cos/sin-encoded lon/lat, +2 more for cos/sin-encoded date
    when date features are enabled."""
    return 4 + (2 if params.use_date_feats else 0)


def convert_loc_to_tensor(lon_lat: np.ndarray, device: torch.device | None = None) -> torch.Tensor:
    """Input columns are ``[lon, lat]`` in degrees (lon in [-180, 180], lat
    in [-90, 90]); output is normalised to [-1, 1], matching upstream
    ``utils.py::convert_loc_to_tensor``."""
    scaled = lon_lat.astype(np.float32).copy()
    scaled[:, 0] /= 180.0
    scaled[:, 1] /= 90.0
    tensor = torch.from_numpy(scaled)
    if device is not None:
        tensor = tensor.to(device)
    return tensor


def encode_loc_time(
    loc: torch.Tensor, date: torch.Tensor | None, *, params: EncodingParams
) -> torch.Tensor:
    """``loc`` is ``[N, 2]`` of normalised ``[lon, lat]`` in [-1, 1]; ``date``
    (if used) is ``[N]`` normalised to [-1, 1]. Matches upstream
    ``utils.py::encode_loc_time``'s ``encode_cos_sin`` branch exactly."""
    feats = torch.cat((torch.sin(math.pi * loc), torch.cos(math.pi * loc)), 1)
    if params.use_date_feats:
        if date is None:
            raise ValueError("use_date_feats=True requires a date tensor")
        date_feats = torch.cat(
            (torch.sin(math.pi * date.unsqueeze(-1)), torch.cos(math.pi * date.unsqueeze(-1))), 1
        )
        feats = torch.cat((feats, date_feats), 1)
    return feats


def rand_samples(
    batch_size: int, *, device: torch.device, params: EncodingParams
) -> torch.Tensor:
    """Random spherical background locations (+ uniform random date when
    date features are used), encoded the same way as real samples. Matches
    upstream ``losses.py::rand_samples(..., rand_type='spherical')``."""
    raw = torch.rand(batch_size, 3, device=device) * 2 - 1
    theta = ((raw[:, 1].unsqueeze(1) + 1) / 2.0) * (2 * math.pi)
    radius = torch.sqrt(1.0 - raw[:, 0].unsqueeze(1) ** 2)
    lon = radius * torch.cos(theta)
    lat = radius * torch.sin(theta)
    date = raw[:, 2] if params.use_date_feats else None
    return encode_loc_time(torch.cat((lon, lat), 1), date, params=params)


def _log_loss(pred: torch.Tensor) -> torch.Tensor:
    return -torch.log(pred + 1e-5)


def embedding_loss(
    model: FCNet,
    *,
    loc_feat: torch.Tensor,
    loc_class: torch.Tensor,
    num_classes: int,
    device: torch.device,
    params: EncodingParams,
) -> torch.Tensor:
    """Non-user ``full_loss`` variant of upstream
    ``losses.py::embedding_loss`` - the hard reproduction limitation
    documented in the module docstring. Presence-only: real observations are
    positive-for-their-class evidence, random spherical background samples
    are treated as negative evidence for every class."""
    batch_size = loc_feat.shape[0]
    loc_feat_rand = rand_samples(batch_size, device=device, params=params)

    loc_cat = torch.cat((loc_feat, loc_feat_rand), 0)
    loc_emb_cat = model(loc_cat, return_feats=True)
    loc_emb = loc_emb_cat[:batch_size, :]
    loc_emb_rand = loc_emb_cat[batch_size:, :]

    loc_pred = torch.sigmoid(model.class_emb(loc_emb))
    loc_pred_rand = torch.sigmoid(model.class_emb(loc_emb_rand))

    pos_weight = num_classes
    loss_pos = _log_loss(1.0 - loc_pred)
    row_index = torch.arange(batch_size, device=device)
    loss_pos[row_index, loc_class] = pos_weight * _log_loss(loc_pred[row_index, loc_class])
    loss_bg = _log_loss(1.0 - loc_pred_rand)

    return loss_pos.mean() + loss_bg.mean()


class BalancedSampler:
    """Deterministic, seeded re-implementation of upstream
    ``utils.py::BalancedSampler`` for single-label classification: each
    epoch samples up to ``num_per_class`` indices per class (with
    replacement if a class has fewer than ``num_per_class`` members),
    shuffled. Driven by an explicit ``random.Random`` instance rather than
    global numpy state, so a training run's sequence of epochs is
    reproducible independent of anything else that touches the RNG."""

    def __init__(self, class_indices: list[int], num_per_class: int, *, rng: random.Random) -> None:
        self._by_class: dict[int, list[int]] = {}
        for position, class_index in enumerate(class_indices):
            self._by_class.setdefault(class_index, []).append(position)
        self._num_per_class = num_per_class
        self._rng = rng

    def sample_epoch(self) -> list[int]:
        indices: list[int] = []
        for members in self._by_class.values():
            if len(members) >= self._num_per_class:
                indices.extend(self._rng.sample(members, self._num_per_class))
            else:
                indices.extend(self._rng.choices(members, k=self._num_per_class))
        self._rng.shuffle(indices)
        return indices
