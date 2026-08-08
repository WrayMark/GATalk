from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import shutil
from typing import Any, Mapping
import uuid

from scenelens.modules.review_control.models import (
    GATE_STATES,
    TASK_PRIORITIES,
    TASK_STATUSES,
    VERIFICATION_STATES,
    GateEvaluationRecord,
    QualityGateRecord,
    ReviewCenterState,
    ReviewTaskRecord,
    TaskVerificationRecord,
)
from scenelens.modules.review_control.presets import gate_preset
from scenelens.storage.atomic import atomic_write_json, load_json
from scenelens.storage.project_store import utc_now
from scenelens.storage.project_lock import ProjectWriteLock
from scenelens.storage.errors import ProjectLockedError


FORMAT_ID = "gatalk.review_control_center"
FORMAT_VERSION = 2
ENTRY_FILENAME = "review_center.json"


def default_review_center_root() -> Path:
    base = Path(
        os.getenv(
            "LOCALAPPDATA",
            str(Path.home() / "AppData" / "Local"),
        )
    )
    return base / "GATalk" / "review-control"


class ReviewCenterStore:
    def __init__(
        self,
        root: Path,
        state: ReviewCenterState,
        *,
        write_lock: ProjectWriteLock | None = None,
        read_only: bool = False,
    ) -> None:
        self.root = Path(root)
        self.state = state
        self._write_lock = write_lock
        self.read_only = read_only

    @classmethod
    def open_default(cls) -> ReviewCenterStore:
        root = default_review_center_root()
        root.mkdir(parents=True, exist_ok=True)
        (root / "backups").mkdir(exist_ok=True)
        try:
            write_lock = ProjectWriteLock.acquire(
                root,
                "gatalk-review-control",
                utc_now(),
            )
        except ProjectLockedError:
            return cls.open_or_create(root, read_only=True)
        try:
            return cls.open_or_create(root, write_lock=write_lock)
        except Exception:
            write_lock.release()
            raise

    @classmethod
    def open_or_create(
        cls,
        root: str | Path,
        *,
        write_lock: ProjectWriteLock | None = None,
        read_only: bool = False,
    ) -> ReviewCenterStore:
        folder = Path(root)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "backups").mkdir(exist_ok=True)
        entry = folder / ENTRY_FILENAME
        if not entry.exists():
            now = utc_now()
            store = cls(
                folder,
                ReviewCenterState(created_at=now, updated_at=now),
                write_lock=write_lock,
                read_only=read_only,
            )
            if not read_only:
                store.save()
            return store
        data = load_json(entry)
        if data.get("format") != FORMAT_ID:
            raise ValueError("审阅中心数据格式无效。")
        version = int(data.get("format_version", 0))
        if version > FORMAT_VERSION:
            raise ValueError("审阅中心由更高版本 GATalk 创建。")
        store = cls(
            folder,
            ReviewCenterState.from_dict(data.get("state", {})),
            write_lock=write_lock,
            read_only=read_only,
        )
        if version < FORMAT_VERSION and not read_only:
            backup = folder / "backups" / f"pre-migration-v{version}-review-center.json"
            if not backup.exists():
                shutil.copy2(entry, backup)
            store.save()
        return store

    def reload(self) -> None:
        data = load_json(self.root / ENTRY_FILENAME)
        self.state = ReviewCenterState.from_dict(data.get("state", {}))

    def save(self, state: ReviewCenterState | None = None) -> None:
        if self.read_only:
            raise ValueError("审阅中心已被另一个 GATalk 进程打开，当前为只读。")
        if state is not None:
            self.state = state
        self.state = replace(self.state, updated_at=utc_now())
        atomic_write_json(
            self.root / ENTRY_FILENAME,
            {
                "format": FORMAT_ID,
                "format_version": FORMAT_VERSION,
                "state": self.state.to_dict(),
            },
        )

    def backup(self, label: str = "manual") -> Path:
        destination = (
            self.root
            / "backups"
            / f"{utc_now().replace(':', '-')}-{label}-review-center.json"
        )
        shutil.copy2(self.root / ENTRY_FILENAME, destination)
        return destination

    def add_task_from_handoff(
        self, payload: Mapping[str, Any]
    ) -> ReviewTaskRecord:
        source_key = (
            str(payload.get("source_module_id", "")),
            str(payload.get("source_project_id", "")),
            str(payload.get("source_entity_type", "finding")),
            str(payload.get("source_entity_id", "")),
        )
        for task in self.state.tasks:
            current_key = (
                task.source_module_id,
                task.source_project_id,
                task.source_entity_type,
                task.source_entity_id,
            )
            if source_key[-1] and current_key == source_key:
                return task
        now = utc_now()
        priority = str(payload.get("priority", "medium"))
        if priority not in TASK_PRIORITIES:
            priority = "medium"
        task = ReviewTaskRecord(
            task_id=str(payload.get("task_id") or uuid.uuid4()),
            title=str(payload.get("title", "未命名审阅任务")).strip()
            or "未命名审阅任务",
            description=str(payload.get("description", "")).strip(),
            acceptance_criteria=str(
                payload.get("acceptance_criteria", "")
            ).strip(),
            priority=priority,
            status="open",
            source_module_id=source_key[0],
            source_project_id=source_key[1],
            source_project_title=str(payload.get("source_project_title", "")),
            source_project_path=str(payload.get("source_project_path", "")),
            source_entity_type=source_key[2],
            source_entity_id=source_key[3],
            source_version_id=str(payload.get("source_version_id", "")),
            production_stage=str(payload.get("production_stage", "")),
            blocked_by_task_ids=tuple(
                item
                for item in dict.fromkeys(
                    str(value)
                    for value in payload.get("blocked_by_task_ids", ())
                )
                if item in {task.task_id for task in self.state.tasks}
            ),
            due_date=str(payload.get("due_date", "")),
            labels=tuple(
                dict.fromkeys(str(item) for item in payload.get("labels", ()))
            ),
            created_at=now,
            updated_at=now,
        )
        self.save(replace(self.state, tasks=(*self.state.tasks, task)))
        return task

    def update_task(self, task: ReviewTaskRecord) -> ReviewTaskRecord:
        if task.task_id not in {item.task_id for item in self.state.tasks}:
            raise ValueError("审阅任务不存在。")
        if task.status not in TASK_STATUSES:
            raise ValueError("任务状态无效。")
        if task.priority not in TASK_PRIORITIES:
            raise ValueError("任务优先级无效。")
        self._validate_task_dependencies(task)
        updated = replace(task, updated_at=utc_now())
        self.save(
            replace(
                self.state,
                tasks=tuple(
                    updated if item.task_id == task.task_id else item
                    for item in self.state.tasks
                ),
            )
        )
        return updated

    def batch_update_tasks(
        self,
        task_ids: tuple[str, ...] | list[str],
        *,
        status: str,
    ) -> tuple[ReviewTaskRecord, ...]:
        if status not in TASK_STATUSES:
            raise ValueError("任务状态无效。")
        selected = set(str(item) for item in task_ids)
        now = utc_now()
        updated: list[ReviewTaskRecord] = []
        tasks: list[ReviewTaskRecord] = []
        for task in self.state.tasks:
            if task.task_id in selected:
                task = replace(task, status=status, updated_at=now)
                updated.append(task)
            tasks.append(task)
        self.save(replace(self.state, tasks=tuple(tasks)))
        return tuple(updated)

    def unresolved_blockers(self, task_id: str) -> tuple[ReviewTaskRecord, ...]:
        task = next(
            (item for item in self.state.tasks if item.task_id == task_id),
            None,
        )
        if task is None:
            return ()
        blockers = set(task.blocked_by_task_ids)
        return tuple(
            item
            for item in self.state.tasks
            if item.task_id in blockers and item.status != "done"
        )

    def delete_task(self, task_id: str) -> None:
        self.save(
            replace(
                self.state,
                tasks=tuple(
                    replace(
                        item,
                        blocked_by_task_ids=tuple(
                            value
                            for value in item.blocked_by_task_ids
                            if value != task_id
                        ),
                    )
                    for item in self.state.tasks
                    if item.task_id != task_id
                ),
                verifications=tuple(
                    item
                    for item in self.state.verifications
                    if item.task_id != task_id
                ),
            )
        )

    def add_verification(
        self,
        task_id: str,
        *,
        version_label: str,
        version_id: str = "",
        state: str,
        evidence_summary: str,
        notes: str = "",
    ) -> TaskVerificationRecord:
        if task_id not in {item.task_id for item in self.state.tasks}:
            raise ValueError("审阅任务不存在。")
        if state not in VERIFICATION_STATES:
            raise ValueError("复查状态无效。")
        record = TaskVerificationRecord(
            verification_id=str(uuid.uuid4()),
            task_id=task_id,
            version_label=version_label.strip() or "未命名版本",
            version_id=version_id.strip(),
            state=state,
            evidence_summary=evidence_summary.strip(),
            notes=notes.strip(),
            created_at=utc_now(),
        )
        self.save(
            replace(
                self.state,
                verifications=(*self.state.verifications, record),
            )
        )
        return record

    def add_gate(
        self,
        *,
        name: str,
        dimension: str,
        acceptance_criteria: str,
        required: bool,
        source_project_id: str = "",
        source_project_title: str = "",
        source_project_path: str = "",
        production_stage: str = "",
        template_id: str = "",
    ) -> QualityGateRecord:
        now = utc_now()
        gate = QualityGateRecord(
            gate_id=str(uuid.uuid4()),
            name=name.strip() or "未命名门禁",
            dimension=dimension.strip() or "综合",
            acceptance_criteria=acceptance_criteria.strip(),
            required=required,
            source_project_id=source_project_id,
            source_project_title=source_project_title,
            source_project_path=source_project_path,
            production_stage=production_stage,
            template_id=template_id,
            created_at=now,
            updated_at=now,
        )
        self.save(replace(self.state, gates=(*self.state.gates, gate)))
        return gate

    def apply_gate_template(
        self,
        production_stage: str,
        *,
        source_project_id: str = "",
        source_project_title: str = "",
        source_project_path: str = "",
    ) -> tuple[QualityGateRecord, ...]:
        preset = gate_preset(production_stage)
        if preset is None:
            raise ValueError("该制作阶段没有内置门禁模板。")
        existing = {
            (item.template_id, item.source_project_id)
            for item in self.state.gates
            if item.template_id
        }
        added: list[QualityGateRecord] = []
        for item in preset.gates:
            if (item.template_id, source_project_id) in existing:
                continue
            added.append(
                self.add_gate(
                    name=item.name,
                    dimension=item.dimension,
                    acceptance_criteria=item.acceptance_criteria,
                    required=item.required,
                    source_project_id=source_project_id,
                    source_project_title=source_project_title,
                    source_project_path=source_project_path,
                    production_stage=production_stage,
                    template_id=item.template_id,
                )
            )
        return tuple(added)

    def update_gate(self, gate: QualityGateRecord) -> QualityGateRecord:
        if gate.gate_id not in {item.gate_id for item in self.state.gates}:
            raise ValueError("质量门禁不存在。")
        if gate.state not in GATE_STATES:
            raise ValueError("门禁状态无效。")
        updated = replace(gate, updated_at=utc_now())
        self.save(
            replace(
                self.state,
                gates=tuple(
                    updated if item.gate_id == gate.gate_id else item
                    for item in self.state.gates
                ),
            )
        )
        return updated

    def delete_gate(self, gate_id: str) -> None:
        self.save(
            replace(
                self.state,
                gates=tuple(
                    item for item in self.state.gates if item.gate_id != gate_id
                ),
                gate_evaluations=tuple(
                    item
                    for item in self.state.gate_evaluations
                    if item.gate_id != gate_id
                ),
            )
        )

    def evaluate_gate(
        self,
        gate_id: str,
        *,
        version_label: str,
        version_id: str = "",
        state: str,
        evidence_summary: str,
    ) -> GateEvaluationRecord:
        gate = next(
            (item for item in self.state.gates if item.gate_id == gate_id),
            None,
        )
        if gate is None:
            raise ValueError("质量门禁不存在。")
        if state not in GATE_STATES or state == "not_evaluated":
            raise ValueError("门禁复查状态无效。")
        now = utc_now()
        evaluation = GateEvaluationRecord(
            evaluation_id=str(uuid.uuid4()),
            gate_id=gate_id,
            version_label=version_label.strip() or "未命名版本",
            version_id=version_id.strip(),
            state=state,
            evidence_summary=evidence_summary.strip(),
            created_at=now,
        )
        updated_gate = replace(gate, state=state, updated_at=now)
        self.save(
            replace(
                self.state,
                gates=tuple(
                    updated_gate if item.gate_id == gate_id else item
                    for item in self.state.gates
                ),
                gate_evaluations=(*self.state.gate_evaluations, evaluation),
            )
        )
        return evaluation

    def export(self, destination: str | Path) -> Path:
        path = Path(destination)
        atomic_write_json(
            path,
            {
                "format": "gatalk.review_control_export",
                "format_version": 2,
                "state": self.state.to_dict(),
            },
        )
        return path

    def close(self) -> None:
        if self._write_lock is not None:
            self._write_lock.release()
            self._write_lock = None

    def _validate_task_dependencies(self, candidate: ReviewTaskRecord) -> None:
        known = {item.task_id for item in self.state.tasks}
        dependencies = tuple(dict.fromkeys(candidate.blocked_by_task_ids))
        if candidate.task_id in dependencies:
            raise ValueError("任务不能依赖自身。")
        missing = set(dependencies) - known
        if missing:
            raise ValueError("任务依赖中包含已不存在的任务。")
        graph = {
            item.task_id: item.blocked_by_task_ids
            for item in self.state.tasks
        }
        graph[candidate.task_id] = dependencies

        def reaches(start: str, target: str, visited: set[str]) -> bool:
            if start == target:
                return True
            if start in visited:
                return False
            visited.add(start)
            return any(
                reaches(value, target, visited)
                for value in graph.get(start, ())
            )

        if any(
            reaches(dependency, candidate.task_id, set())
            for dependency in dependencies
        ):
            raise ValueError("任务依赖形成循环，请调整前置任务。")
