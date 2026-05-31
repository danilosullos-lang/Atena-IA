#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ATENA Wi-Fi CSI Sensing Lab.

Privacy-first integration inspired by public Wi-Fi CSI human-sensing research.
Does not perform covert surveillance, router compromise, or hidden through-wall
tracking. Accepts explicit, consent-tagged CSI-like frames and returns coarse
motion/presence signals suitable for authorized safety and accessibility
experiments.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from statistics import StatisticsError, mean, pstdev
from typing import Callable, Final, Iterable, Sequence, TypeAlias

# Canonical alias for JSON-serialisable result dicts produced by this module.
JsonDict: TypeAlias = dict[str, object]

# ---------------------------------------------------------------------------
# Policy constants
# ---------------------------------------------------------------------------

ALLOWED_USE_CASES: Final[frozenset[str]] = frozenset(
    {
        "fall_detection",
        "assisted_living",
        "occupancy_safety",
        "research_demo",
        "accessibility",
    }
)

PROHIBITED_USE_CASES: Final[frozenset[str]] = frozenset(
    {
        "covert_surveillance",
        "stalking",
        "law_enforcement_tracking_without_warrant",
        "employee_monitoring_without_notice",
        "credential_or_router_compromise",
    }
)

# Inference thresholds
_MOTION_THRESHOLD: Final[float] = 0.34
_PRESENCE_THRESHOLD: Final[float] = 0.12
_MOTION_CONFIDENCE_BASE: Final[float] = 0.62
_PRESENCE_CONFIDENCE_BASE: Final[float] = 0.48
_CLEAR_CONFIDENCE_BASE: Final[float] = 0.55
_MAX_MOTION_CONFIDENCE: Final[float] = 0.96
_MAX_PRESENCE_CONFIDENCE: Final[float] = 0.82
_MIN_CLEAR_CONFIDENCE: Final[float] = 0.18

# Feature extraction weights (must sum to 1.0)
_AMPLITUDE_WEIGHT: Final[float] = 0.68
_PHASE_WEIGHT: Final[float] = 0.32

# Safety note shown in every demo report
_SAFETY_NOTE: Final[str] = (
    "Implementação ATENA é consentida e coarse-grained; não captura pessoas "
    "secretamente nem promete visão real através de paredes sem hardware/dataset "
    "autorizado."
)

_PRIVACY_WARNINGS: Final[tuple[str, ...]] = (
    "coarse_presence_only",
    "no_identity_inference",
    "no_hidden_surveillance",
    "requires_authorized_csi_source",
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CSIFrame:
    """One consent-tagged Channel State Information-like observation."""

    timestamp_ms: int
    amplitudes: tuple[float, ...]
    phases: tuple[float, ...]
    device_id: str = "atena-sim-node"
    location_label: str = "lab"
    consent_token: str = "demo-consent"

    def __post_init__(self) -> None:
        if not self.amplitudes:
            raise ValueError("CSIFrame.amplitudes must be non-empty.")
        if len(self.amplitudes) != len(self.phases):
            raise ValueError(
                f"amplitudes ({len(self.amplitudes)}) and phases "
                f"({len(self.phases)}) must have the same length."
            )


@dataclass(frozen=True)
class SensingPolicy:
    """Policy gate that must pass before any Wi-Fi sensing inference."""

    use_case: str = "research_demo"
    consent_token: str = "demo-consent"
    authorized_locations: frozenset[str] = field(
        default_factory=lambda: frozenset({"lab"})
    )
    allow_pose_estimation: bool = False
    allow_biometrics: bool = False

    def validate(self, frame: CSIFrame) -> list[str]:
        """Return a list of policy-violation strings (empty means OK)."""
        violations: list[str] = []
        if self.use_case in PROHIBITED_USE_CASES:
            violations.append(f"prohibited_use_case:{self.use_case}")
        elif self.use_case not in ALLOWED_USE_CASES:
            violations.append(f"unknown_use_case:{self.use_case}")
        if frame.consent_token != self.consent_token:
            violations.append("missing_or_invalid_consent")
        if frame.location_label not in self.authorized_locations:
            violations.append(f"unauthorized_location:{frame.location_label}")
        return violations


@dataclass(frozen=True)
class CSIFeatures:
    """Intermediate feature set extracted from a single CSIFrame."""

    amplitude_variance: float
    phase_variance: float
    motion_energy: float
    normalized_energy: float


@dataclass(frozen=True)
class SensingResult:
    """Coarse, non-identifying Wi-Fi sensing output."""

    status: str
    confidence: float
    motion_energy: float
    amplitude_variance: float
    phase_variance: float
    privacy_mode: str
    warnings: tuple[str, ...]
    generated_at: str

    def to_dict(self) -> JsonDict:
        d = asdict(self)
        d["warnings"] = list(d["warnings"])  # JSON-friendly
        return d


@dataclass(frozen=True)
class StreamSummary:
    """Aggregated result over a stream of CSIFrames."""

    status: str
    frames: int
    motion_frames: int
    possible_presence_frames: int
    blocked_frames: int
    average_confidence: float
    capability: str
    safety_note: str
    # Stored as a tuple so StreamSummary is truly immutable end-to-end.
    results: tuple[JsonDict, ...]

    def to_dict(self) -> JsonDict:
        d = asdict(self)
        d["results"] = list(d["results"])  # JSON-friendly
        return d


# ---------------------------------------------------------------------------
# Sensing engine
# ---------------------------------------------------------------------------


class WifiCSISensingEngine:
    """Deterministic CSI feature extractor and coarse inference engine."""

    def __init__(self, policy: SensingPolicy | None = None) -> None:
        self._policy: SensingPolicy = policy or SensingPolicy()

    # -- Signal processing helpers ------------------------------------------

    @staticmethod
    def _variance(values: Sequence[float]) -> float:
        if len(values) < 2:
            return 0.0
        try:
            return round(pstdev(values) ** 2, 8)
        except StatisticsError:
            return 0.0

    @staticmethod
    def unwrap_phase(phases: Sequence[float]) -> list[float]:
        """Return a mean-centred, continuously-unwrapped phase series.

        Uses a single forward pass (O(n)) with no intermediate list allocation
        beyond the output buffer.
        """
        if not phases:
            return []

        two_pi = 2.0 * math.pi
        unwrapped: list[float] = [phases[0]]
        offset = 0.0
        prev = phases[0]

        for current in phases[1:]:
            delta = current - prev
            if delta > math.pi:
                offset -= two_pi
            elif delta < -math.pi:
                offset += two_pi
            unwrapped.append(current + offset)
            prev = current

        baseline = mean(unwrapped)
        return [round(v - baseline, 8) for v in unwrapped]

    # -- Feature extraction -------------------------------------------------

    def extract_features(self, frame: CSIFrame) -> CSIFeatures:
        """Extract signal features from amplitude and phase subcarriers."""
        unwrapped = self.unwrap_phase(frame.phases)
        amplitude_variance = self._variance(frame.amplitudes)
        phase_variance = self._variance(unwrapped)
        mean_amplitude = mean(frame.amplitudes)

        motion_energy = round(
            _AMPLITUDE_WEIGHT * amplitude_variance + _PHASE_WEIGHT * phase_variance,
            8,
        )
        # Avoid division by zero; mean_amplitude is always ≥ 0 for real CSI
        normalized_energy = round(
            motion_energy / max(1e-9, mean_amplitude),
            8,
        )

        return CSIFeatures(
            amplitude_variance=amplitude_variance,
            phase_variance=phase_variance,
            motion_energy=motion_energy,
            normalized_energy=normalized_energy,
        )

    # -- Frame analysis -----------------------------------------------------

    def analyze_frame(self, frame: CSIFrame) -> SensingResult:
        """Validate policy and return a coarse sensing result for one frame."""
        violations = self._policy.validate(frame)
        features = self.extract_features(frame)
        now = datetime.now(timezone.utc).isoformat()

        if violations:
            return SensingResult(
                status="blocked_by_policy",
                confidence=0.0,
                motion_energy=features.motion_energy,
                amplitude_variance=features.amplitude_variance,
                phase_variance=features.phase_variance,
                privacy_mode="blocked",
                warnings=tuple(violations),
                generated_at=now,
            )

        energy = features.normalized_energy
        if energy >= _MOTION_THRESHOLD:
            status = "motion_detected"
            confidence = min(_MAX_MOTION_CONFIDENCE, _MOTION_CONFIDENCE_BASE + energy)
        elif energy >= _PRESENCE_THRESHOLD:
            status = "possible_presence"
            confidence = min(_MAX_PRESENCE_CONFIDENCE, _PRESENCE_CONFIDENCE_BASE + energy)
        else:
            status = "no_presence_signal"
            confidence = max(_MIN_CLEAR_CONFIDENCE, _CLEAR_CONFIDENCE_BASE - energy)

        extra_warnings: list[str] = []
        if not self._policy.allow_pose_estimation:
            extra_warnings.append("pose_estimation_disabled")
        if not self._policy.allow_biometrics:
            extra_warnings.append("biometrics_disabled")

        return SensingResult(
            status=status,
            confidence=round(confidence, 3),
            motion_energy=features.motion_energy,
            amplitude_variance=features.amplitude_variance,
            phase_variance=features.phase_variance,
            privacy_mode="consent_required_coarse_sensing",
            warnings=_PRIVACY_WARNINGS + tuple(extra_warnings),
            generated_at=now,
        )

    # -- Stream analysis ----------------------------------------------------

    def analyze_stream(self, frames: Iterable[CSIFrame]) -> StreamSummary:
        """Analyze a stream and return a policy-safe occupancy summary."""
        results = [self.analyze_frame(f) for f in frames]

        if not results:
            return StreamSummary(
                status="empty_stream",
                frames=0,
                motion_frames=0,
                possible_presence_frames=0,
                blocked_frames=0,
                average_confidence=0.0,
                capability="wifi_csi_presence_sensing_lab",
                safety_note=_SAFETY_NOTE,
                results=(),
            )

        blocked = motion = possible = 0
        total_confidence = 0.0

        for r in results:
            total_confidence += r.confidence
            if r.status == "blocked_by_policy":
                blocked += 1
            elif r.status == "motion_detected":
                motion += 1
            elif r.status == "possible_presence":
                possible += 1

        if blocked:
            summary_status = "blocked"
        elif motion:
            summary_status = "motion"
        elif possible:
            summary_status = "possible_presence"
        else:
            summary_status = "clear"

        return StreamSummary(
            status=summary_status,
            frames=len(results),
            motion_frames=motion,
            possible_presence_frames=possible,
            blocked_frames=blocked,
            average_confidence=round(total_confidence / len(results), 3),
            capability="wifi_csi_presence_sensing_lab",
            safety_note=_SAFETY_NOTE,
            results=tuple(r.to_dict() for r in results),
        )


# Synthetic stream generation parameters
_SYN_DISTURBANCE_SCALE: Final[float] = 0.42
_SYN_PHASE_OFFSET_MOTION: Final[float] = 0.55
_SYN_PHASE_OFFSET_STILL: Final[float] = 0.02
_SYN_FREQ_DIVISOR: Final[float] = 2.2

# ---------------------------------------------------------------------------
# Synthetic data generator
# ---------------------------------------------------------------------------


def generate_synthetic_csi_stream(
    frames: int = 6,
    *,
    motion: bool = True,
    subcarriers: int = 30,
    base_timestamp_ms: int = 1_800_000_000_000,
    frame_interval_ms: int = 50,
    consent_token: str = "demo-consent",
) -> list[CSIFrame]:
    """Create deterministic CSI-like frames for demos and tests.

    Args:
        frames: Number of frames to generate (clamped to ≥ 1).
        motion: When True, inject high-energy disturbance into the signal.
        subcarriers: Number of OFDM subcarriers per frame.
        base_timestamp_ms: Millisecond timestamp for the first frame.
        frame_interval_ms: Millisecond gap between consecutive frames.
        consent_token: Consent token to embed in every frame.

    Returns:
        A list of :class:`CSIFrame` objects.
    """
    n_frames = max(1, frames)
    phase_offset = _SYN_PHASE_OFFSET_MOTION if motion else _SYN_PHASE_OFFSET_STILL
    # Cache math.sin in local scope — reduces global attribute lookups in tight loops.
    _sin = math.sin
    out: list[CSIFrame] = []

    for fi in range(n_frames):
        amplitudes: list[float] = []
        phases: list[float] = []
        for sc in range(subcarriers):
            base = 1.0 + 0.03 * _sin(sc / 3.0)
            disturbance = (
                _SYN_DISTURBANCE_SCALE * _sin((fi + sc) / _SYN_FREQ_DIVISOR)
                if motion
                else 0.025
            )
            amplitudes.append(round(base + disturbance, 6))
            phases.append(round(_sin(sc / 5.0 + fi / 3.0) + phase_offset, 6))

        out.append(
            CSIFrame(
                timestamp_ms=base_timestamp_ms + fi * frame_interval_ms,
                amplitudes=tuple(amplitudes),
                phases=tuple(phases),
                consent_token=consent_token,
            )
        )

    return out


# ---------------------------------------------------------------------------
# Demo report builder
# ---------------------------------------------------------------------------


def build_demo_report(motion: bool = True) -> JsonDict:
    """Run the engine on a synthetic stream and return a JSON-ready dict."""
    engine = WifiCSISensingEngine()
    stream = generate_synthetic_csi_stream(motion=motion)
    return engine.analyze_stream(stream).to_dict()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ATENA privacy-first Wi-Fi CSI sensing lab",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--no-motion",
        action="store_true",
        help="Generate a low-motion synthetic stream",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full JSON payload instead of a one-liner summary",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    payload = build_demo_report(motion=not args.no_motion)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"status={payload['status']}  "
            f"frames={payload['frames']}  "
            f"avg_conf={payload['average_confidence']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
