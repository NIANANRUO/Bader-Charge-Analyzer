# -*- coding: utf-8 -*-
from __future__ import annotations

import math
from collections.abc import Iterable


# ---- Color profiles ----
# Each profile defines how the neutral center and saturated endpoints look.
# "neutral" is the RGB at charge=0, "pos" is the positive endpoint (electron loss),
# "neg" is the negative endpoint (electron gain).
# "interpolation" controls how intermediate values are computed.

_PROFILES = {
    # Standard blue-gray-red: neutral=light gray, fades linearly to blue/red.
    # This is the original behavior.
    "标准": {
        "neutral": (0.85, 0.85, 0.85),
        "pos": (1.0, 0.15, 0.15),
        "neg": (0.15, 0.15, 1.0),
    },
    # Coolwarm-inspired: neutral=warm white, endpoints are more muted but
    # perceptually smoother.  The neutral is slightly warm-tinted so
    # small charges are visible.
    "柔和": {
        "neutral": (0.87, 0.86, 0.84),
        "pos": (0.70, 0.20, 0.18),
        "neg": (0.18, 0.26, 0.72),
    },
    # Vivid: neutral is mid-gray (darker), so even small charges stand out.
    # Endpoints are fully saturated.
    "鲜明": {
        "neutral": (0.72, 0.72, 0.72),
        "pos": (1.0, 0.05, 0.05),
        "neg": (0.05, 0.10, 1.0),
    },
}

PROFILE_NAMES = list(_PROFILES.keys())


class ChargeColorMapper:
    """Map Bader charge values to sign-aware RGB colors.

    Parameters
    ----------
    charges : iterable of float
        All charge values in the dataset (used to compute clim).
    gamma : float
        Power-law exponent for intensity mapping.  ``gamma < 1``
        expands the color difference for small charges (default 1.0 =
        linear).  A value of 0.5 applies a square-root curve.
    range_mode : str
        How to determine the color limits:
        ``"极值"`` — symmetric max |charge|  (default)
        ``"95%位"`` — 95th percentile of |charge|
        ``"80%位"`` — 80th percentile of |charge|
    profile : str
        Color profile name: ``"标准"``, ``"柔和"``, ``"鲜明"``.
    """

    def __init__(
        self,
        charges: Iterable[float],
        gamma: float = 1.0,
        range_mode: str = "极值",
        profile: str = "标准",
    ) -> None:
        raw = self._finite_values(charges)
        abs_charges = sorted(abs(v) for v in raw)

        # Compute clim based on range mode
        max_abs = self._compute_max_abs(abs_charges, range_mode)
        self.clim = (-max_abs, max_abs)

        # Store mapping parameters
        self.gamma = max(gamma, 0.05)
        prof = _PROFILES.get(profile, _PROFILES["标准"])
        self._neutral = prof["neutral"]
        self._pos = prof["pos"]
        self._neg = prof["neg"]

    # ---- Public API ----

    def rgb_for_charge(self, charge: float) -> tuple[float, float, float]:
        value = self._finite_or_zero(charge)
        max_abs = self.clim[1]
        if max_abs == 0.0:
            return self._neutral

        # Normalized intensity in [0, 1]
        t = min(abs(value) / max_abs, 1.0)

        # Apply gamma (power-law) normalization
        if self.gamma != 1.0:
            t = t ** self.gamma

        # Interpolate from neutral to endpoint
        if value > 0:
            endpoint = self._pos
        elif value < 0:
            endpoint = self._neg
        else:
            return self._neutral

        r = self._neutral[0] + (endpoint[0] - self._neutral[0]) * t
        g = self._neutral[1] + (endpoint[1] - self._neutral[1]) * t
        b = self._neutral[2] + (endpoint[2] - self._neutral[2]) * t
        return (r, g, b)

    def label_for_charge(self, charge: float) -> str:
        value = self._finite_or_zero(charge)
        if value > 0:
            return "electron gain"
        if value < 0:
            return "electron loss"
        return "neutral"

    # ---- Internal helpers ----

    @staticmethod
    def _compute_max_abs(sorted_abs: list[float], mode: str) -> float:
        if not sorted_abs:
            return 1.0
        if mode == "95%位":
            idx = max(int(len(sorted_abs) * 0.95) - 1, 0)
            val = sorted_abs[min(idx, len(sorted_abs) - 1)]
        elif mode == "80%位":
            idx = max(int(len(sorted_abs) * 0.80) - 1, 0)
            val = sorted_abs[min(idx, len(sorted_abs) - 1)]
        else:  # "极值"
            val = sorted_abs[-1]
        return val if val > 0.0 else 1.0

    @classmethod
    def _finite_values(cls, charges: Iterable[float]) -> list[float]:
        return [
            value
            for charge in charges
            if (value := cls._finite_or_none(charge)) is not None
        ]

    @staticmethod
    def _finite_or_zero(charge: float) -> float:
        value = ChargeColorMapper._finite_or_none(charge)
        if value is None:
            return 0.0
        return value

    @staticmethod
    def _finite_or_none(charge: float) -> float | None:
        try:
            value = float(charge)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value):
            return None
        return value
