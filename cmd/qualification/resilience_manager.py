#!/usr/bin/env python3
"""Bounded resilience campaign manager for lanes 20-26."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

try:
    from resilience_common import (
        MANAGED_SWAP,
        RESILIENCE_PLAN_SCHEMA,
        RESILIENCE_STATE_SCHEMA,
        RESULT_TO_RC,
        QualificationError,
        active_swaps,
        atomic_write_json,
        normal_topology_status,
        query_installed_rpm,
        rc_result,
        refresh_managed_swap,
        restore_normal_topology,
        run_command,
        sha256_path,
        source_identity,
        utc_now,
        validate_package_gate,
    )
except ImportError as exc:
    print(f"ERROR: resilience common module unavailable: {exc}", file=sys.stderr)
    raise SystemExit(2) from None

DEFAULT_ROOT = Path("/var/lib/bc250-llm-server/resilience")
PRE_REBOOT_LANES = tuple(str(number) for number in range(20, 26))
FINAL_LANE = "26"
ALL_LANES = (*PRE_REBOOT_LANES, FINAL_LANE)
TERMINAL_RESULTS = {"DEFECT", "SAFETY"}
RETRYABLE_RESULTS = {"PENDING", "HARNESS", "INCOMPLETE", "INTERRUPTED"}


class CampaignInterrupted(Exception):
    def __init__(self, signum: int) -> None:
        super().__init__(signal.Signals(signum).name)
        self.signum = signum


class CampaignManager:
    def __init__(self, campaign: Path) -> None:
        self.campaign = campaign
        self.state_path = campaign / "state.json"
        self.plan_path = campaign / "plan.json"
        self.gate_dir = campaign / "package-gate"
        self.evidence_dir = campaign / "evidence"
        self.events_path = campaign / "events.jsonl"
        self.state: dict[str, object] = {}
        self.current_child: subprocess.Popen[str] | None = None
        self.current_action: tuple[str, str] | None = None
        self.interrupted_signum: int | None = None
        self._old_handlers: dict[int, object] = {}

    def persist(self) -> None:
        self.state["updated_at"] = utc_now()
        atomic_write_json(self.state_path, self.state)

    def event(self, event: str, **fields: object) -> None:
        payload = {"time": utc_now(), "event": event, **fields}
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(self.events_path, 0o600)

    def install_signal_handlers(self) -> None:
        for signum in (signal.SIGINT, signal.SIGTERM):
            self._old_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, self._handle_signal)

    def restore_signal_handlers(self) -> None:
        for signum, handler in self._old_handlers.items():
            signal.signal(signum, handler)
        self._old_handlers.clear()

    def _handle_signal(self, signum: int, _frame: object) -> None:
        self.interrupted_signum = signum
        child = self.current_child
        if child is not None and child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        raise CampaignInterrupted(signum)

    def load_state(self) -> bool:
        if not self.state_path.is_file():
            print(f"INCOMPLETE: missing campaign state: {self.state_path}", file=sys.stderr)
            return False
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"INCOMPLETE: unreadable campaign state: {exc}", file=sys.stderr)
            return False
        if state.get("schema") != RESILIENCE_STATE_SCHEMA:
            print(f"INCOMPLETE: unrecognized campaign schema: {state.get('schema')!r}", file=sys.stderr)
            return False
        self.state = state
        return True

    def mark_gap(self, detail: str) -> int:
        gaps = self.state.setdefault("evidence_gaps", [])
        if isinstance(gaps, list) and detail not in gaps:
            gaps.append(detail)
        self.state["result"] = "INCOMPLETE"
        self.event("evidence-gap", detail=detail)
        self.persist()
        print(f"INCOMPLETE: {detail}", file=sys.stderr)
        return RESULT_TO_RC["INCOMPLETE"]

    def _source_paths(self) -> list[Path]:
        return [Path(__file__).resolve(), Path(__file__).with_name("resilience_common.py").resolve()]

    def initialize(
        self,
        *,
        plan_source: Path,
        gate_source: Path,
        refresh_swap: bool,
    ) -> None:
        gate_validation = validate_package_gate(gate_source, require_pass=True)
        installed = query_installed_rpm()
        gate = gate_validation.gate
        candidate = gate.get("candidate")
        if not isinstance(candidate, dict) or candidate.get("nevra") != installed["nevra"]:
            raise QualificationError(
                "installed RPM does not match the authoritative package-gate candidate",
                "INCOMPLETE",
            )
        plan = load_plan(plan_source)

        self.campaign.mkdir(parents=True, exist_ok=False)
        os.chmod(self.campaign, 0o700)
        self.evidence_dir.mkdir(mode=0o700)
        shutil.copy2(plan_source, self.plan_path)
        os.chmod(self.plan_path, 0o600)
        shutil.copytree(gate_source, self.gate_dir)
        for path in self.gate_dir.rglob("*"):
            if path.is_file():
                os.chmod(path, 0o600)
            elif path.is_dir():
                os.chmod(path, 0o700)
        copied_gate = validate_package_gate(self.gate_dir, require_pass=True)

        swap_priority = None
        for path, priority in active_swaps():
            if path == MANAGED_SWAP:
                swap_priority = priority
                break

        now = utc_now()
        self.state = {
            "schema": RESILIENCE_STATE_SCHEMA,
            "schema_version": 1,
            "created_at": now,
            "updated_at": now,
            "phase": "pre-reboot",
            "result": "INCOMPLETE",
            "package_identity": installed,
            "package_gate_manifest_sha256": copied_gate.manifest_sha256,
            "source_identity": source_identity(self._source_paths()),
            "plan_sha256": sha256_path(self.plan_path),
            "start_boot_id": read_boot_id(),
            "post_reboot_boot_id": None,
            "refresh_managed_swap": bool(refresh_swap or plan.get("refresh_managed_swap", False)),
            "managed_swap_priority": swap_priority,
            "lanes": {lane: {"result": "PENDING", "attempts": 0} for lane in ALL_LANES},
            "barriers": {f"after-{lane}": {"result": "PENDING", "attempts": 0} for lane in PRE_REBOOT_LANES},
            "evidence_gaps": [],
            "interrupt_restoration": None,
        }
        self.persist()
        self.event(
            "campaign-created",
            installed_nevra=installed["nevra"],
            gate_manifest=copied_gate.manifest_sha256,
        )

    def validate_resume_identity(self) -> int | None:
        # Identity validation happens before any lane retry or mutation.
        for required in (self.plan_path, self.gate_dir / "gate.json", self.gate_dir / "SHA256SUMS"):
            if not required.exists():
                return self.mark_gap(f"missing resume artifact: {required.relative_to(self.campaign)}")
        try:
            gate_validation = validate_package_gate(self.gate_dir, require_pass=True)
        except QualificationError as exc:
            return self.mark_gap(f"package-gate revalidation failed: {exc}")
        expected_gate_sha = self.state.get("package_gate_manifest_sha256")
        if gate_validation.manifest_sha256 != expected_gate_sha:
            return self.mark_gap("package-gate manifest identity changed since campaign start")
        try:
            installed = query_installed_rpm()
        except QualificationError as exc:
            return self.mark_gap(f"installed RPM identity unavailable on resume: {exc}")
        expected_package = self.state.get("package_identity")
        if not isinstance(expected_package, dict) or installed != expected_package:
            return self.mark_gap("installed RPM identity changed since campaign start")
        candidate = gate_validation.gate.get("candidate")
        if not isinstance(candidate, dict) or candidate.get("nevra") != installed["nevra"]:
            return self.mark_gap("installed RPM no longer matches package-gate candidate")

        expected_source = self.state.get("source_identity")
        try:
            observed_source = source_identity(self._source_paths())
        except OSError as exc:
            return self.mark_gap(f"manager source identity unavailable: {exc}")
        if observed_source != expected_source:
            return self.mark_gap("manager/common source identity changed since campaign start")
        try:
            plan_sha = sha256_path(self.plan_path)
        except OSError as exc:
            return self.mark_gap(f"resilience plan unavailable: {exc}")
        if plan_sha != self.state.get("plan_sha256"):
            return self.mark_gap("resilience plan identity changed since campaign start")
        return self.validate_recorded_artifacts()

    def validate_recorded_artifacts(self) -> int | None:
        lanes = self.state.get("lanes")
        barriers = self.state.get("barriers")
        if not isinstance(lanes, dict) or not isinstance(barriers, dict):
            return self.mark_gap("campaign lane/barrier state is malformed")
        for lane in ALL_LANES:
            record = lanes.get(lane)
            if not isinstance(record, dict):
                return self.mark_gap(f"lane {lane} state is missing")
            if record.get("result") != "PENDING":
                artifact = self.evidence_dir / f"lane-{lane}" / "result.json"
                if not artifact.is_file():
                    return self.mark_gap(f"missing resume evidence for lane {lane}")
        for lane in PRE_REBOOT_LANES:
            key = f"after-{lane}"
            record = barriers.get(key)
            if not isinstance(record, dict):
                return self.mark_gap(f"barrier {key} state is missing")
            if record.get("result") != "PENDING":
                artifact = self.evidence_dir / f"barrier-{key}" / "result.json"
                if not artifact.is_file():
                    return self.mark_gap(f"missing resume evidence for barrier {key}")
        return None

    def _plan(self) -> dict[str, object]:
        return load_plan(self.plan_path)

    def _terminal_result(self) -> str | None:
        lanes = self.state["lanes"]
        assert isinstance(lanes, dict)
        for lane in ALL_LANES:
            record = lanes[lane]
            assert isinstance(record, dict)
            result = str(record.get("result"))
            if result in TERMINAL_RESULTS:
                return result
        return None

    def run_lane(self, lane: str) -> int:
        plan = self._plan()
        lanes = plan["lanes"]
        assert isinstance(lanes, dict)
        argv = lanes[lane]
        assert isinstance(argv, list)
        lane_dir = self.evidence_dir / f"lane-{lane}"
        lane_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(lane_dir, 0o700)
        stdout_path = lane_dir / "stdout.txt"
        stderr_path = lane_dir / "stderr.txt"
        record = self.state["lanes"][lane]  # type: ignore[index]
        assert isinstance(record, dict)
        record["attempts"] = int(record.get("attempts", 0)) + 1
        record["started_at"] = utc_now()
        record["result"] = "RUNNING"
        self.state["result"] = "INCOMPLETE"
        self.persist()
        self.event("lane-start", lane=lane, attempt=record["attempts"], argv=argv)
        self.current_action = ("lane", lane)

        env = os.environ.copy()
        env.update(
            {
                "BC250_RESILIENCE_CAMPAIGN_DIR": str(self.campaign),
                "BC250_RESILIENCE_EVIDENCE_DIR": str(lane_dir),
                "BC250_RESILIENCE_LANE": lane,
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        try:
            with stdout_path.open("a", encoding="utf-8") as stdout, stderr_path.open("a", encoding="utf-8") as stderr:
                self.current_child = subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    text=True,
                    env=env,
                    start_new_session=True,
                )
                returncode = self.current_child.wait()
        except OSError as exc:
            returncode = 2
            result = "HARNESS"
            stderr_path.write_text(f"lane execution failed: {exc}\n", encoding="utf-8")
        else:
            if returncode in (-signal.SIGINT, -signal.SIGTERM):
                result = "INTERRUPTED"
                returncode = 130
            else:
                result = rc_result(returncode)
        finally:
            self.current_child = None
            self.current_action = None
        record.update(
            {
                "finished_at": utc_now(),
                "returncode": returncode,
                "result": result,
                "evidence": str(lane_dir.relative_to(self.campaign)),
            }
        )
        atomic_write_json(lane_dir / "result.json", record)
        self.state["result"] = result if result != "PASS" else "INCOMPLETE"
        self.persist()
        self.event("lane-finish", lane=lane, result=result, returncode=returncode)
        return RESULT_TO_RC[result]

    def run_barrier(self, after_lane: str) -> int:
        key = f"after-{after_lane}"
        barrier_dir = self.evidence_dir / f"barrier-{key}"
        barrier_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(barrier_dir, 0o700)
        record = self.state["barriers"][key]  # type: ignore[index]
        assert isinstance(record, dict)
        record["attempts"] = int(record.get("attempts", 0)) + 1
        record["started_at"] = utc_now()
        record["result"] = "RUNNING"
        self.persist()
        self.event("barrier-start", barrier=key, attempt=record["attempts"])
        self.current_action = ("barrier", key)

        details: dict[str, object] = {}
        result = "PASS"
        try:
            topology_ok, topology = normal_topology_status()
            details["normal_topology"] = topology
            # An inactive Agent is the expected normal topology, not a failure.
            if not topology_ok:
                result = "HARNESS"
                details["topology_error"] = "normal main/task/embedding topology not restored"

            swaps_before = active_swaps()
            details["active_swaps_before"] = [
                {"name": str(path), "priority": priority} for path, priority in swaps_before
            ]
            managed_before = [priority for path, priority in swaps_before if path == MANAGED_SWAP]
            if self.state.get("managed_swap_priority") is not None and not managed_before:
                result = "HARNESS"
                details["swap_error"] = "package-managed disk swap is unexpectedly inactive"
            if result == "PASS" and self.state.get("refresh_managed_swap"):
                refresh = refresh_managed_swap()
                details["managed_swap_refresh"] = {
                    "status": refresh.status,
                    "detail": refresh.detail,
                    "priority": refresh.priority,
                    "restored": refresh.restored,
                }
                if refresh.status != "PASS" or not refresh.restored:
                    result = "HARNESS"
            swaps_after = active_swaps()
            details["active_swaps_after"] = [
                {"name": str(path), "priority": priority} for path, priority in swaps_after
            ]
            baseline_priority = self.state.get("managed_swap_priority")
            if baseline_priority is not None:
                priorities = [priority for path, priority in swaps_after if path == MANAGED_SWAP]
                if priorities != [baseline_priority]:
                    result = "HARNESS"
                    details["swap_restore_error"] = (
                        f"managed swap priority/state changed: expected {baseline_priority}, observed {priorities}"
                    )
        except QualificationError as exc:
            result = "HARNESS"
            details["error"] = str(exc)

        record.update(
            {
                "finished_at": utc_now(),
                "result": result,
                "details": details,
                "evidence": str(barrier_dir.relative_to(self.campaign)),
            }
        )
        atomic_write_json(barrier_dir / "result.json", record)
        self.current_action = None
        self.state["result"] = result if result != "PASS" else "INCOMPLETE"
        self.persist()
        self.event("barrier-finish", barrier=key, result=result)
        return RESULT_TO_RC[result]

    def restore_managed_state_after_interrupt(self) -> dict[str, object]:
        # Ignore a second Ctrl-C while mandatory restoration is in progress.
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        result: dict[str, object] = {"started_at": utc_now(), "status": "PASS"}
        try:
            try:
                topology_ok, topology_detail = restore_normal_topology()
                result["normal_topology"] = topology_detail
                if not topology_ok:
                    result["status"] = "HARNESS"
            except QualificationError as exc:
                result["normal_topology"] = {"error": str(exc)}
                result["status"] = "HARNESS"

            baseline_priority = self.state.get("managed_swap_priority")
            if baseline_priority is not None:
                try:
                    swaps = active_swaps()
                    current = [priority for path, priority in swaps if path == MANAGED_SWAP]
                    if not current:
                        restore = run_command(
                            ["swapon", "--priority", str(baseline_priority), str(MANAGED_SWAP)], timeout=120
                        )
                        result["managed_swap_restore_rc"] = restore.returncode
                        if restore.returncode != 0:
                            result["status"] = "HARNESS"
                    elif current != [baseline_priority]:
                        result["managed_swap_priority_mismatch"] = current
                        result["status"] = "HARNESS"
                except QualificationError as exc:
                    result["managed_swap"] = {"error": str(exc)}
                    result["status"] = "HARNESS"
        finally:
            result["finished_at"] = utc_now()
            for sig, handler in previous.items():
                signal.signal(sig, handler)
        return result

    def mark_interrupted(self, exc: CampaignInterrupted) -> int:
        self.current_child = None
        action = self.current_action
        if action is not None:
            kind, identifier = action
            if kind == "lane":
                record = self.state["lanes"][identifier]  # type: ignore[index]
                evidence = self.evidence_dir / f"lane-{identifier}"
            else:
                record = self.state["barriers"][identifier]  # type: ignore[index]
                evidence = self.evidence_dir / f"barrier-{identifier}"
            assert isinstance(record, dict)
            record.update({"result": "INTERRUPTED", "finished_at": utc_now(), "returncode": 130})
            evidence.mkdir(parents=True, exist_ok=True)
            atomic_write_json(evidence / "result.json", record)
            atomic_write_json(
                evidence / "interruption.json",
                {"time": utc_now(), "signal": signal.Signals(exc.signum).name, "sealed": True},
            )
        restoration = self.restore_managed_state_after_interrupt()
        self.state["interrupt_restoration"] = restoration
        self.state["result"] = "INTERRUPTED"
        self.event(
            "campaign-interrupted",
            signal=signal.Signals(exc.signum).name,
            restoration=restoration.get("status"),
        )
        self.persist()
        print(
            f"INTERRUPTED: {signal.Signals(exc.signum).name}; managed restoration={restoration.get('status')}",
            file=sys.stderr,
        )
        return 130

    def run_pre_reboot(self) -> int:
        terminal = self._terminal_result()
        if terminal is not None:
            print(f"{terminal}: product/safety result is terminal; start a new campaign.", file=sys.stderr)
            return RESULT_TO_RC[terminal]
        for lane in PRE_REBOOT_LANES:
            lane_record = self.state["lanes"][lane]  # type: ignore[index]
            assert isinstance(lane_record, dict)
            lane_result = str(lane_record.get("result"))
            if lane_result != "PASS":
                if lane_result not in RETRYABLE_RESULTS and lane_result != "RUNNING":
                    return self.mark_gap(f"unrecognized lane {lane} resume result: {lane_result}")
                rc = self.run_lane(lane)
                if rc != 0:
                    return rc
            barrier_key = f"after-{lane}"
            barrier_record = self.state["barriers"][barrier_key]  # type: ignore[index]
            assert isinstance(barrier_record, dict)
            barrier_result = str(barrier_record.get("result"))
            if barrier_result != "PASS":
                if barrier_result not in RETRYABLE_RESULTS and barrier_result != "RUNNING":
                    return self.mark_gap(f"unrecognized barrier {barrier_key} resume result: {barrier_result}")
                rc = self.run_barrier(lane)
                if rc != 0:
                    return rc
        self.state["phase"] = "awaiting-lane26-post-reboot"
        self.state["result"] = "INCOMPLETE"
        self.persist()
        self.event("pre-reboot-complete", boot_id=self.state.get("start_boot_id"))
        print("Pre-reboot resilience lanes 20-25 and hygiene barriers PASS.")
        print("Reboot the appliance, then run: sudo bc250 resilience resume --campaign-dir " + str(self.campaign))
        return RESULT_TO_RC["INCOMPLETE"]

    def run_post_reboot(self) -> int:
        terminal = self._terminal_result()
        if terminal is not None:
            print(f"{terminal}: Lane 26 result is terminal; a new candidate/campaign is required.", file=sys.stderr)
            return RESULT_TO_RC[terminal]
        current_boot = read_boot_id()
        post_boot = self.state.get("post_reboot_boot_id")
        if post_boot is None:
            if current_boot == self.state.get("start_boot_id"):
                self.state["result"] = "INCOMPLETE"
                self.state["last_resume_check"] = {
                    "time": utc_now(),
                    "status": "INCOMPLETE",
                    "detail": "post-lanes reboot not observed",
                }
                self.persist()
                print("INCOMPLETE: reboot not observed; Lane 26 was not started.", file=sys.stderr)
                return RESULT_TO_RC["INCOMPLETE"]
            self.state["post_reboot_boot_id"] = current_boot
            self.state["phase"] = "lane26-post-reboot"
            self.persist()
            self.event("post-reboot-resume", boot_id=current_boot)
        elif current_boot != post_boot:
            return self.mark_gap("boot identity changed again during Lane 26 resume")

        lane_record = self.state["lanes"][FINAL_LANE]  # type: ignore[index]
        assert isinstance(lane_record, dict)
        result = str(lane_record.get("result"))
        if result in TERMINAL_RESULTS:
            print(f"{result}: Lane 26 is non-retryable; start a new campaign.", file=sys.stderr)
            return RESULT_TO_RC[result]
        if result == "PASS":
            self.state["phase"] = "complete"
            self.state["result"] = "PASS"
            self.persist()
            return 0
        if result not in RETRYABLE_RESULTS and result != "RUNNING":
            return self.mark_gap(f"unrecognized Lane 26 resume result: {result}")
        # Crucially, post-reboot resume can retry Lane 26 only. It never re-enters lanes 20-25.
        rc = self.run_lane(FINAL_LANE)
        if rc == 0:
            self.state["phase"] = "complete"
            self.state["result"] = "PASS"
            self.persist()
            self.event("campaign-complete", result="PASS")
            print("Resilience campaign PASS.")
        return rc

    def run_or_resume(self) -> int:
        phase = str(self.state.get("phase"))
        if phase == "complete":
            result = str(self.state.get("result", "INCOMPLETE"))
            print(f"Campaign already complete: {result}")
            return RESULT_TO_RC.get(result, 4)
        if phase in {"pre-reboot", "initializing"}:
            return self.run_pre_reboot()
        if phase in {"awaiting-lane26-post-reboot", "lane26-post-reboot"}:
            return self.run_post_reboot()
        return self.mark_gap(f"unrecognized campaign phase: {phase}")


def read_boot_id() -> str:
    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise QualificationError(f"cannot read boot identity: {exc}") from exc
    if not value:
        raise QualificationError("boot identity is empty")
    return value


def load_plan(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualificationError(f"cannot read resilience plan: {exc}", "INCOMPLETE") from exc
    if payload.get("schema") != RESILIENCE_PLAN_SCHEMA:
        raise QualificationError(f"unrecognized resilience plan schema: {payload.get('schema')!r}", "INCOMPLETE")
    lanes = payload.get("lanes")
    if not isinstance(lanes, dict) or set(lanes) != set(ALL_LANES):
        raise QualificationError(f"resilience plan must define exactly lanes {', '.join(ALL_LANES)}", "INCOMPLETE")
    for lane in ALL_LANES:
        argv = lanes.get(lane)
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(value, str) and value for value in argv)
        ):
            raise QualificationError(f"lane {lane} command must be a non-empty argv array", "INCOMPLETE")
    refresh = payload.get("refresh_managed_swap", False)
    if not isinstance(refresh, bool):
        raise QualificationError("refresh_managed_swap must be boolean", "INCOMPLETE")
    return payload


def default_campaign_dir() -> Path:
    stamp = utc_now().replace(":", "").replace("-", "")
    return DEFAULT_ROOT / f"campaign-{stamp}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bc250 resilience",
        description="Run the bounded resilience lanes with durable resume and cleanup semantics.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("--plan", type=Path, required=True)
    start.add_argument("--package-gate", type=Path, required=True)
    start.add_argument("--campaign-dir", type=Path)
    start.add_argument(
        "--refresh-managed-swap",
        action="store_true",
        help="transactionally refresh only the package-managed disk swap at inter-lane barriers",
    )
    resume = sub.add_parser("resume")
    resume.add_argument("--campaign-dir", type=Path, required=True)
    status = sub.add_parser("status")
    status.add_argument("--campaign-dir", type=Path, required=True)
    return parser


def print_status(manager: CampaignManager) -> int:
    if not manager.load_state():
        return 4
    print("BC-250 resilience campaign")
    print(f"Campaign : {manager.campaign}")
    print(f"Phase    : {manager.state.get('phase')}")
    print(f"Result   : {manager.state.get('result')}")
    package = manager.state.get("package_identity")
    if isinstance(package, dict):
        print(f"Package  : {package.get('nevra', 'unknown')}")
    lanes = manager.state.get("lanes", {})
    if isinstance(lanes, dict):
        for lane in ALL_LANES:
            record = lanes.get(lane, {})
            result = record.get("result", "missing") if isinstance(record, dict) else "missing"
            print(f"Lane {lane:>2}  : {result}")
    barriers = manager.state.get("barriers", {})
    if isinstance(barriers, dict):
        for lane in PRE_REBOOT_LANES:
            key = f"after-{lane}"
            record = barriers.get(key, {})
            result = record.get("result", "missing") if isinstance(record, dict) else "missing"
            print(f"Barrier {lane}: {result}")
    restoration = manager.state.get("interrupt_restoration")
    if isinstance(restoration, dict):
        print(f"Interrupt restoration: {restoration.get('status')}")
    gaps = manager.state.get("evidence_gaps")
    if isinstance(gaps, list) and gaps:
        print("Evidence gaps:")
        for gap in gaps:
            print(f"  - {gap}")
    return RESULT_TO_RC.get(str(manager.state.get("result")), 4)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "status":
        return print_status(CampaignManager(args.campaign_dir.resolve()))
    if os.geteuid() != 0:
        print("ERROR: resilience start/resume requires root (run with sudo).", file=sys.stderr)
        return 2

    if args.command == "start":
        campaign = (args.campaign_dir or default_campaign_dir()).resolve()
        manager = CampaignManager(campaign)
        try:
            manager.initialize(
                plan_source=args.plan.resolve(),
                gate_source=args.package_gate.resolve(),
                refresh_swap=args.refresh_managed_swap,
            )
        except FileExistsError:
            print(f"INCOMPLETE: campaign directory already exists: {campaign}", file=sys.stderr)
            return 4
        except QualificationError as exc:
            print(f"{exc.result}: {exc}", file=sys.stderr)
            return exc.rc
    else:
        manager = CampaignManager(args.campaign_dir.resolve())
        if not manager.load_state():
            return 4
        identity_rc = manager.validate_resume_identity()
        if identity_rc is not None:
            return identity_rc

    manager.install_signal_handlers()
    try:
        return manager.run_or_resume()
    except CampaignInterrupted as exc:
        return manager.mark_interrupted(exc)
    except QualificationError as exc:
        manager.state["result"] = exc.result
        manager.event("controlled-error", result=exc.result, detail=str(exc))
        manager.persist()
        print(f"{exc.result}: {exc}", file=sys.stderr)
        return exc.rc
    finally:
        manager.restore_signal_handlers()


if __name__ == "__main__":
    raise SystemExit(main())
