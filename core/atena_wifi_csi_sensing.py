#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ATENA Wi-Fi CSI Sensing Lab.

Privacy-first integration inspired by public Wi-Fi CSI human-sensing research.
It does not perform covert surveillance, router compromise, or hidden through-wall
tracking. The module accepts explicit, consent-tagged CSI-like frames and returns
coarse motion/presence signals suitable for authorized safety and accessibility
experiments.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Iterable, Sequence


ALLOWED_USE_CASES = {
    "fall_detection",
    "assisted_living",
    "occupancy_safety",
    "research_demo",
    "accessibility",
}

PROHIBITED_USE_CASES = {
    "covert_surveillance",
    "stalking",
    "law_enforcement_tracking_without_warrant",
    "employee_monitoring_without_notice",
    "credential_or_router_compromise",
}


@dataclass(frozen=True)
class CSIFrame:
    """One consent-tagged Channel State Information-like observation."""

    timestamp_ms: int
    amplitudes: list[float]
    phases: list[float]
    device_id: str = "atena-sim-node"
    location_label: str = "lab"
    consent_token: str = "demo-consent"


@dataclass(frozen=True)
class SensingPolicy:
    """Policy gate that must pass before any Wi-Fi sensing inference."""

    use_case: str = "research_demo"
    consent_token: str = "demo-consent"
    authorized_locations: set[str] = field(default_factory=lambda: {"lab"})
    allow_pose_estimation: bool = False
    allow_biometrics: bool = False

    def validate(self, frame: CSIFrame) -> list[str]:
        violations: list[str] = []
        if self.use_case in PROHIBITED_USE_CASES:
            violations.append(f"prohibited_use_case:{self.use_case}")
        if self.use_case not in ALLOWED_USE_CASES:
            violations.append(f"unknown_use_case:{self.use_case}")
        if frame.consent_token != self.consent_token:
            violations.append("missing_or_invalid_consent")
        if frame.location_label not in self.authorized_locations:
            violations.append(f"unauthorized_location:{frame.location_label}")
        return violations


@dataclass(frozen=True)
class SensingResult:
    """Coarse, non-identifying Wi-Fi sensing output."""

    status: str
    confidence: float
    motion_energy: float
    amplitude_variance: float
    phase_variance: float
    privacy_mode: str
    warnings: list[str]
    generated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class WifiCSISensingEngine:
    """Deterministic CSI feature extractor and coarse inference engine."""

    def __init__(self, policy: SensingPolicy | None = None) -> None:
        self.policy = policy or SensingPolicy()

    @staticmethod
    def _variance(values: Sequence[float]) -> float:
        if not values:
            return 0.0
        return round(pstdev(values) ** 2, 8)

    @staticmethod
    def unwrap_phase(phases: Sequence[float]) -> list[float]:
        """Unwrap phase values into a continuous series."""
        if not phases:
            return []
        unwrapped = [float(phases[0])]
        offset = 0.0
        previous = float(phases[0])
        for phase in phases[1:]:
            current = float(phase)
            delta = current - previous
            if delta > math.pi:
                offset -= 2 * math.pi
            elif delta < -math.pi:
                offset += 2 * math.pi
            unwrapped.append(current + offset)
            previous = current
        baseline = mean(unwrapped)
        return [round(value - baseline, 8) for value in unwrapped]

    def extract_features(self, frame: CSIFrame) -> dict[str, float]:
        """Extract simple signal features from amplitudes and phases."""
        clean_phase = self.unwrap_phase(frame.phases)
        amplitude_variance = self._variance(frame.amplitudes)
        phase_variance = self._variance(clean_phase)
        mean_amplitude = mean(frame.amplitudes) if frame.amplitudes else 0.0
        motion_energy = round((amplitude_variance * 0.68) + (phase_variance * 0.32), 8)
        normalized_energy = round(motion_energy / max(0.001, mean_amplitude), 8)
        return {
            "amplitude_variance": amplitude_variance,
            "phase_variance": phase_variance,
            "motion_energy": motion_energy,
            "normalized_energy": normalized_energy,
        }

    def analyze_frame(self, frame: CSIFrame) -> SensingResult:
        """Analyze one frame after policy validation.

        Output is intentionally coarse: no identity, no body image, no precise
        through-wall pose, and no biometrics unless a future reviewed policy
        explicitly enables such features.
        """
        warnings = self.policy.validate(frame)
        features = self.extract_features(frame)
        if warnings:
            return SensingResult(
                status="blocked_by_policy",
                confidence=0.0,
                motion_energy=features["motion_energy"],
                amplitude_variance=features["amplitude_variance"],
                phase_variance=features["phase_variance"],
                privacy_mode="blocked",
                warnings=warnings,
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

        energy = features["normalized_energy"]
        if energy >= 0.34:
            status = "motion_detected"
            confidence = min(0.96, 0.62 + energy)
        elif energy >= 0.12:
            status = "possible_presence"
            confidence = min(0.82, 0.48 + energy)
        else:
            status = "no_presence_signal"
            confidence = max(0.18, 0.55 - energy)

        privacy_warnings = [
            "coarse_presence_only",
            "no_identity_inference",
            "no_hidden_surveillance",
            "requires_authorized_csi_source",
        ]
        if not self.policy.allow_pose_estimation:
            privacy_warnings.append("pose_estimation_disabled")
        if not self.policy.allow_biometrics:
            privacy_warnings.append("biometrics_disabled")

        return SensingResult(
            status=status,
            confidence=round(confidence, 3),
            motion_energy=features["motion_energy"],
            amplitude_variance=features["amplitude_variance"],
            phase_variance=features["phase_variance"],
            privacy_mode="consent_required_coarse_sensing",
            warnings=privacy_warnings,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def analyze_stream(self, frames: Iterable[CSIFrame]) -> dict[str, object]:
        """Analyze a stream and summarize policy-safe occupancy status."""
        results = [self.analyze_frame(frame) for frame in frames]
        if not results:
            return {"status": "empty_stream", "frames": 0, "results": []}
        blocked = sum(1 for result in results if result.status == "blocked_by_policy")
        motion = sum(1 for result in results if result.status == "motion_detected")
        possible = sum(1 for result in results if result.status == "possible_presence")
        summary = "blocked" if blocked else "motion" if motion else "possible_presence" if possible else "clear"
        return {
            "status": summary,
            "frames": len(results),
            "motion_frames": motion,
            "possible_presence_frames": possible,
            "blocked_frames": blocked,
            "average_confidence": round(mean(result.confidence for result in results), 3),
            "results": [result.to_dict() for result in results],
        }


def generate_synthetic_csi_stream(frames: int = 6, motion: bool = True) -> list[CSIFrame]:
    """Create deterministic CSI-like frames for demos and tests."""
    out: list[CSIFrame] = []
    for frame_idx in range(max(1, frames)):
        amplitudes: list[float] = []
        phases: list[float] = []
        for subcarrier in range(30):
            base = 1.0 + 0.03 * math.sin(subcarrier / 3)
            disturbance = 0.42 * math.sin((frame_idx + subcarrier) / 2.2) if motion else 0.025
            amplitudes.append(round(base + disturbance, 6))
            phases.append(round(math.sin(subcarrier / 5 + frame_idx / 3) + (0.55 if motion else 0.02), 6))
        out.append(CSIFrame(timestamp_ms=1_800_000_000_000 + frame_idx * 50, amplitudes=amplitudes, phases=phases))
    return out


def build_demo_report(motion: bool = True) -> dict[str, object]:
    engine = WifiCSISensingEngine()
    stream = generate_synthetic_csi_stream(motion=motion)
    payload = engine.analyze_stream(stream)
    payload["capability"] = "wifi_csi_presence_sensing_lab"
    payload["safety_note"] = (
        "Implementação ATENA é consentida e coarse-grained; não captura pessoas secretamente "
        "nem promete visão real através de paredes sem hardware/dataset autorizado."
    )
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ATENA privacy-first Wi-Fi CSI sensing lab")
    parser.add_argument("--no-motion", action="store_true", help="Generate a low-motion synthetic stream")
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    args = parser.parse_args(list(argv) if argv is not None else None)
    payload = build_demo_report(motion=not args.no_motion)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"status={payload['status']} frames={payload['frames']} avg_conf={payload['average_confidence']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
