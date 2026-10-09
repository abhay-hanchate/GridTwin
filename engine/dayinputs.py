"""Bridge from the Round 1 DayInputs (one real day) to the batch scenario format."""
from __future__ import annotations

import numpy as np

from engine.powerflow import DayInputs
from engine.types import DayScenarioBatch, Network

LOAD_POWER_FACTOR = 0.95


def scenarios_from_legacy(inputs: DayInputs, network: Network, seed: int = 42) -> DayScenarioBatch:
    """One scenario: the same meter-to-home assignment as the legacy engine (seeded rng.choice)."""
    meters = np.random.default_rng(seed).choice(np.asarray(inputs.load_kw.columns), network.n_homes)
    return DayScenarioBatch(
        t=inputs.load_kw.index,
        load_kw=inputs.load_kw[meters].to_numpy(dtype=float)[None, :, :],
        pv_per_kwp=inputs.pv_kw_per_kwp.to_numpy(dtype=float)[None, :],
        upstream_pu=inputs.upstream_vm_pu.to_numpy(dtype=float)[None, :],
        load_pf=LOAD_POWER_FACTOR,
        labels=(inputs.date,),
    )
