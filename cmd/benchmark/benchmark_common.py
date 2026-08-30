#!/usr/bin/env python3
"""Shared helpers for BC-250 benchmarks.

Stdlib-only by design: these helpers are installed with the RPM and must work on
an otherwise minimal Fedora host. API shapes target Ollama 0.32.15.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import threading
import time
from typing import Any, Iterable
from urllib import error, request

STANDARD_OLLAMA_VERSION = "0.32.15"
DEFAULT_TIMEOUT = 900.0
DEFAULT_TELEMETRY_INTERVAL = 0.5
TEMP_THRESHOLDS = (80.0, 83.0, 85.0)


class BenchmarkError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        base_url = base_url.strip()
        if "://" not in base_url:
            base_url = f"http://{base_url}"
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def json_request(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        method: str | None = None,
    ) -> dict[str, Any]:
        data = None
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = request.Request(
            self._url(path),
            data=data,
            headers=headers,
            method=method or ("POST" if payload is not None else "GET"),
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise BenchmarkError(f"Ollama {path} returned HTTP {exc.code}: {body}") from exc
        except OSError as exc:
            raise BenchmarkError(f"Ollama request failed for {self._url(path)}: {exc}") from exc
        if not body.strip():
            return {}
        try:
            result = json.loads(body)
        except json.JSONDecodeError as exc:
            raise BenchmarkError(f"Ollama {path} returned invalid JSON") from exc
        if isinstance(result, dict) and result.get("error"):
            raise BenchmarkError(str(result["error"]))
        if not isinstance(result, dict):
            raise BenchmarkError(f"Ollama {path} returned unexpected JSON type")
        return result

    def ndjson_request(self, path: str, payload: dict[str, Any]):
        """Yield Ollama newline-delimited JSON records from a streaming request."""
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self._url(path),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                for raw in response:
                    if not raw.strip():
                        continue
                    try:
                        item = json.loads(raw.decode("utf-8"))
                    except json.JSONDecodeError as exc:
                        raise BenchmarkError(f"Ollama {path} returned invalid streaming JSON") from exc
                    if isinstance(item, dict) and item.get("error"):
                        raise BenchmarkError(str(item["error"]))
                    if not isinstance(item, dict):
                        raise BenchmarkError(f"Ollama {path} returned unexpected streaming JSON type")
                    yield item
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise BenchmarkError(f"Ollama {path} returned HTTP {exc.code}: {body}") from exc
        except OSError as exc:
            raise BenchmarkError(f"Ollama streaming request failed for {self._url(path)}: {exc}") from exc

    def version(self) -> str:
        return str(self.json_request("/api/version").get("version", "unknown"))

    def tags(self) -> list[dict[str, Any]]:
        return list(self.json_request("/api/tags").get("models", []))

    def show(self, model: str) -> dict[str, Any]:
        return self.json_request("/api/show", {"model": model})

    def ps(self) -> list[dict[str, Any]]:
        return list(self.json_request("/api/ps").get("models", []))

    def stop(self, model: str) -> bool:
        """Request model unload, falling back to the Ollama 0.32.15 HTTP path."""
        env = os.environ.copy()
        env["OLLAMA_HOST"] = self.base_url
        try:
            result = subprocess.run(
                ["ollama", "stop", model],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                timeout=30,
            )
            if result.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        # Ollama documents an empty /api/generate request with keep_alive=0 as
        # the HTTP unload path. This remains valid in 0.32.15.
        try:
            self.json_request("/api/generate", {"model": model, "keep_alive": 0, "stream": False})
            return True
        except BenchmarkError:
            # Embedding-only or multimodal registrations can reject generation.
            # The caller decides whether a failed unload is fatal for its lane.
            return False

    def model_loaded(self, model: str) -> bool:
        """Return whether /api/ps currently reports this exact model."""
        normalized = model.removesuffix(":latest")
        return any(
            str(row.get("name") or row.get("model") or "").removesuffix(":latest") == normalized
            for row in self.ps()
        )

    def wait_unloaded(self, model: str, timeout: float = 30.0) -> bool:
        """Return True only after /api/ps confirms that the model is absent."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if not self.model_loaded(model):
                    return True
            except BenchmarkError:
                return False
            time.sleep(0.25)
        return False

    def ensure_unloaded(self, model: str, timeout: float = 30.0) -> None:
        """Require a confirmed unload; return immediately when already absent."""
        try:
            if not self.model_loaded(model):
                return
        except BenchmarkError as exc:
            raise BenchmarkError(f"cannot verify model residency before unload: {model}") from exc
        if not self.stop(model):
            raise BenchmarkError(f"could not request unload for {model}")
        if not self.wait_unloaded(model, timeout):
            raise BenchmarkError(f"model remained loaded after {timeout:.0f}s: {model}")

    def digest(self, model: str) -> str:
        normalized = model.removesuffix(":latest")
        for row in self.tags():
            name = str(row.get("name") or row.get("model") or "").removesuffix(":latest")
            if name == normalized:
                return str(row.get("digest") or "")
        return ""

    def runtime_state(self, model: str) -> dict[str, Any]:
        normalized = model.removesuffix(":latest")
        try:
            rows = self.ps()
        except BenchmarkError:
            rows = []
        for row in rows:
            name = str(row.get("name") or row.get("model") or "").removesuffix(":latest")
            if name == normalized:
                return {
                    "resident_size_bytes": row.get("size"),
                    "resident_vram_bytes": row.get("size_vram"),
                    "allocated_context": row.get("context_length"),
                }
        return {
            "resident_size_bytes": None,
            "resident_vram_bytes": None,
            "allocated_context": None,
        }


def read_int(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def read_meminfo() -> tuple[float | None, float | None]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, rest = line.split(":", 1)
            match = re.search(r"(\d+)", rest)
            if match:
                values[key] = int(match.group(1))
    except OSError:
        return None, None
    available = values.get("MemAvailable")
    total = values.get("SwapTotal")
    free = values.get("SwapFree")
    available_mib = available / 1024 if available is not None else None
    swap_used_mib = (total - free) / 1024 if total is not None and free is not None else None
    return available_mib, swap_used_mib


def discover_amdgpu_device(drm_root: Path = Path("/sys/class/drm")) -> Path | None:
    """Return the BC-250/AMDGPU DRM device used for benchmark telemetry.

    BC-250 appliances normally expose one AMD DRM card. Prefer the boot VGA
    device if multiple AMD cards exist. BC250_DRM_CARD=cardN can override the
    automatic choice without changing benchmark output schemas.
    """
    forced = os.environ.get("BC250_DRM_CARD", "").strip()
    candidates: list[Path] = []
    if forced:
        card = drm_root / forced
        if (card / "device").exists():
            candidates.append(card / "device")
    else:
        for card in sorted(drm_root.glob("card[0-9]*")):
            device = card / "device"
            if not device.exists():
                continue
            try:
                vendor = (device / "vendor").read_text(encoding="utf-8").strip().casefold()
            except OSError:
                continue
            if vendor == "0x1002":
                candidates.append(device)
    if not candidates:
        return None
    candidates.sort(key=lambda device: (read_int(device / "boot_vga") != 1, device.parent.name))
    return candidates[0]


def amdgpu_edge_temperature(device: Path | None) -> tuple[str, float | None]:
    if device is None:
        return "", None
    hwmons = sorted((device / "hwmon").glob("hwmon*"))
    for hwmon in hwmons:
        try:
            name = (hwmon / "name").read_text(encoding="utf-8").strip().casefold()
        except OSError:
            name = ""
        if name and name != "amdgpu":
            continue
        inputs = sorted(hwmon.glob("temp*_input"))
        if not inputs:
            continue
        chosen: Path | None = None
        label = ""
        for input_path in inputs:
            label_path = input_path.with_name(input_path.name.replace("_input", "_label"))
            try:
                current_label = label_path.read_text(encoding="utf-8").strip()
            except OSError:
                current_label = ""
            if current_label.casefold() == "edge":
                chosen, label = input_path, current_label
                break
        if chosen is None:
            # AMDGPU temp1 is the on-die GPU temperature. On cards that expose
            # labels this is normally "edge"; older ASICs may omit the label.
            temp1 = hwmon / "temp1_input"
            chosen = temp1 if temp1.exists() else inputs[0]
            label_path = chosen.with_name(chosen.name.replace("_input", "_label"))
            try:
                label = label_path.read_text(encoding="utf-8").strip()
            except OSError:
                label = "edge" if chosen.name == "temp1_input" else chosen.stem
        raw = read_int(chosen)
        if raw is None:
            continue
        value = raw / 1000.0 if abs(raw) > 1000 else float(raw)
        return f"{device.parent.name}/amdgpu/{label or chosen.stem}", value
    return "", None


def current_gpu_clock_mhz(device: Path | None) -> float | None:
    if device is None:
        return None
    try:
        text = (device / "pp_dpm_sclk").read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        if "*" not in line:
            continue
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(MHz|Mhz|mhz)", line)
        if match:
            return float(match.group(1))
    return None


def device_sysfs_int(device: Path | None, name: str) -> int | None:
    return read_int(device / name) if device is not None else None


@dataclass
class TelemetrySample:
    timestamp: float
    temp_c: float | None
    temp_label: str
    gpu_busy_pct: float | None
    gpu_clock_mhz: float | None
    vram_used_bytes: int | None
    gtt_used_bytes: int | None
    mem_available_mib: float | None
    swap_used_mib: float | None


class TelemetrySampler:
    def __init__(self, interval: float = DEFAULT_TELEMETRY_INTERVAL) -> None:
        self.interval = max(interval, 0.1)
        self.samples: list[TelemetrySample] = []
        self.gpu_device = discover_amdgpu_device()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample(self) -> TelemetrySample:
        temp_label, temp_c = amdgpu_edge_temperature(self.gpu_device)
        busy_raw = device_sysfs_int(self.gpu_device, "gpu_busy_percent")
        mem_available, swap_used = read_meminfo()
        return TelemetrySample(
            timestamp=time.monotonic(),
            temp_c=temp_c,
            temp_label=temp_label,
            gpu_busy_pct=float(busy_raw) if busy_raw is not None else None,
            gpu_clock_mhz=current_gpu_clock_mhz(self.gpu_device),
            vram_used_bytes=device_sysfs_int(self.gpu_device, "mem_info_vram_used"),
            gtt_used_bytes=device_sysfs_int(self.gpu_device, "mem_info_gtt_used"),
            mem_available_mib=mem_available,
            swap_used_mib=swap_used,
        )

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            self.samples.append(self._sample())

    def start(self) -> "TelemetrySampler":
        self.samples.append(self._sample())
        self._thread = threading.Thread(target=self._loop, name="bc250-telemetry", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval * 3 + 1)
        self.samples.append(self._sample())
        return self.summary()

    def summary(self) -> dict[str, Any]:
        if not self.samples:
            return empty_telemetry()
        temps = [sample.temp_c for sample in self.samples if sample.temp_c is not None]
        busy = [sample.gpu_busy_pct for sample in self.samples if sample.gpu_busy_pct is not None]
        clocks = [sample.gpu_clock_mhz for sample in self.samples if sample.gpu_clock_mhz is not None]
        vrams = [sample.vram_used_bytes for sample in self.samples if sample.vram_used_bytes is not None]
        gtts = [sample.gtt_used_bytes for sample in self.samples if sample.gtt_used_bytes is not None]
        mems = [sample.mem_available_mib for sample in self.samples if sample.mem_available_mib is not None]
        swaps = [sample.swap_used_mib for sample in self.samples if sample.swap_used_mib is not None]

        threshold_seconds = {threshold: 0.0 for threshold in TEMP_THRESHOLDS}
        for previous, current in zip(self.samples, self.samples[1:]):
            delta = max(0.0, current.timestamp - previous.timestamp)
            if previous.temp_c is None:
                continue
            for threshold in TEMP_THRESHOLDS:
                if previous.temp_c >= threshold:
                    threshold_seconds[threshold] += delta

        peak_label = ""
        if temps:
            peak_sample = max(
                (sample for sample in self.samples if sample.temp_c is not None),
                key=lambda sample: float(sample.temp_c),
            )
            peak_label = peak_sample.temp_label

        return {
            "telemetry_samples": len(self.samples),
            "telemetry_duration_s": max(0.0, self.samples[-1].timestamp - self.samples[0].timestamp),
            "temp_max_c": max(temps) if temps else None,
            "temp_p95_c": percentile(temps, 95) if temps else None,
            "seconds_ge_80c": threshold_seconds[80.0],
            "seconds_ge_83c": threshold_seconds[83.0],
            "seconds_ge_85c": threshold_seconds[85.0],
            "temp_peak_label": peak_label,
            "gpu_busy_max_pct": max(busy) if busy else None,
            "gpu_clock_min_mhz": min(clocks) if clocks else None,
            "gpu_clock_max_mhz": max(clocks) if clocks else None,
            "vram_used_max_bytes": max(vrams) if vrams else None,
            "gtt_used_max_bytes": max(gtts) if gtts else None,
            "mem_available_min_mib": min(mems) if mems else None,
            "swap_used_max_mib": max(swaps) if swaps else None,
        }


def empty_telemetry() -> dict[str, Any]:
    return {
        "telemetry_samples": 0,
        "telemetry_duration_s": 0.0,
        "temp_max_c": None,
        "temp_p95_c": None,
        "seconds_ge_80c": 0.0,
        "seconds_ge_83c": 0.0,
        "seconds_ge_85c": 0.0,
        "temp_peak_label": "",
        "gpu_busy_max_pct": None,
        "gpu_clock_min_mhz": None,
        "gpu_clock_max_mhz": None,
        "vram_used_max_bytes": None,
        "gtt_used_max_bytes": None,
        "mem_available_min_mib": None,
        "swap_used_max_mib": None,
    }


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def normalize_words(text: str) -> list[str]:
    return re.findall(r"[\wÀ-ÖØ-öø-ÿ'-]+", text.casefold(), flags=re.UNICODE)


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise BenchmarkError(f"embedding dimension mismatch: {len(left)} != {len(right)}")
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def mean(values: Iterable[float]) -> float:
    data = list(values)
    return statistics.fmean(data) if data else 0.0
