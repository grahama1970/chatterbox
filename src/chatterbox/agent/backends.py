"""Backend-neutral voice rendering contract and registry (issue #12).

The concrete engine adapters are constructed by the agent server with injected
callables, so this module stays import-light and the server's existing model
globals (which tests monkeypatch) remain authoritative.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

DECLARED_SAMPLE_RATE = 24000
DECLARED_CHANNELS = 1
DECLARED_DTYPE = "pcm_s16le_from_float32"


class UnknownBackendError(ValueError):
    """Requested backend id is not registered."""


class UnsupportedCapabilityError(ValueError):
    """Requested behavior needs a capability the selected backend lacks."""

    def __init__(self, backend_id: str, capability: str):
        super().__init__(f"backend_capability_unsupported:{capability}")
        self.backend_id = backend_id
        self.capability = capability


@dataclass(frozen=True)
class VoiceCapabilities:
    backend_id: str
    revision: str
    voice_cloning: bool
    preset_voices: bool
    structured_affect_axes: bool
    per_segment_delivery: bool
    true_incremental_streaming: bool
    cooperative_inference_cancellation: bool
    stale_output_fencing: bool
    deterministic_seed: bool
    input_sample_formats: tuple[str, ...]
    output_sample_formats: tuple[str, ...]
    estimated_resident_vram_mb: int | None
    max_concurrency: int

    def as_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["input_sample_formats"] = list(self.input_sample_formats)
        data["output_sample_formats"] = list(self.output_sample_formats)
        return data

    def digest(self) -> str:
        canonical = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class BackendHealth:
    state: str = "unloaded"  # unloaded | loading | loaded | failed
    load_seconds: float | None = None
    measured_resident_vram_mb: float | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class CallableVoiceBackend:
    """VoiceBackend implementation delegating to injected engine callables.

    `loader` performs the (idempotent-from-our-side) heavy model load and
    returns nothing; `generator` renders text to a waveform tensor and returns
    (wav, sample_rate, conditioning_receipt).
    """

    caps: VoiceCapabilities
    loader: Callable[[], None]
    generator: Callable[..., tuple[Any, int, dict[str, Any]]]
    is_loaded: Callable[[], bool]
    unloader: Callable[[], None] | None = None
    _health: BackendHealth = field(default_factory=BackendHealth)
    _load_lock: threading.Lock = field(default_factory=threading.Lock)

    def capabilities(self) -> VoiceCapabilities:
        return self.caps

    def health(self) -> BackendHealth:
        if self._health.state in ("unloaded", "loaded"):
            self._health.state = "loaded" if self.is_loaded() else "unloaded"
        return self._health

    def load(self) -> None:
        """Single-flight load: concurrent callers block on one real load."""
        with self._load_lock:
            if self.is_loaded():
                self._health.state = "loaded"
                return
            self._health.state = "loading"
            started = time.perf_counter()
            try:
                measured_before = _cuda_allocated_mb()
                self.loader()
                self._health.load_seconds = round(time.perf_counter() - started, 3)
                measured_after = _cuda_allocated_mb()
                if measured_before is not None and measured_after is not None:
                    self._health.measured_resident_vram_mb = round(measured_after - measured_before, 1)
                self._health.state = "loaded"
                self._health.error = None
            except Exception as exc:
                self._health.state = "failed"
                self._health.error = f"{type(exc).__name__}: {exc}"
                raise

    def warmup(self) -> None:
        self.load()

    def synthesize(self, **kwargs: Any) -> tuple[Any, int, dict[str, Any]]:
        self.load()
        return self.generator(**kwargs)

    def unload(self) -> None:
        with self._load_lock:
            if self.unloader is not None:
                self.unloader()
            self._health = BackendHealth(state="unloaded")


def _cuda_allocated_mb() -> float | None:
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        return torch.cuda.memory_allocated() / (1024 * 1024)
    except Exception:
        return None


class VoiceBackendRegistry:
    def __init__(self) -> None:
        self._backends: dict[str, CallableVoiceBackend] = {}

    def register(self, backend: CallableVoiceBackend) -> None:
        self._backends[backend.caps.backend_id] = backend

    def ids(self) -> list[str]:
        return sorted(self._backends)

    def get(self, backend_id: str) -> CallableVoiceBackend:
        backend = self._backends.get(backend_id)
        if backend is None:
            raise UnknownBackendError(f"unknown_backend:{backend_id}")
        return backend

    def summary(self) -> dict[str, Any]:
        return {
            backend_id: {
                "capabilities": backend.caps.as_dict(),
                "capability_digest": backend.caps.digest(),
                "health": backend.health().as_dict(),
            }
            for backend_id, backend in sorted(self._backends.items())
        }
