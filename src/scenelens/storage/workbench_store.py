from __future__ import annotations

import json
from collections.abc import Mapping

from scenelens.core.domain import (
    AIConceptPreview,
    AIConceptPreviewStatus,
    AIRun,
    AIRunStatus,
    Annotation,
    ArtifactStatus,
    DerivedArtifact,
    Evidence,
    EvidenceSource,
    EvidenceType,
    QualityGate,
    QualityGateState,
    ReviewProfile,
    SourceDocument,
    Task,
    TaskPriority,
    TaskStatus,
)
from scenelens.storage.atomic import canonical_json
from scenelens.storage.project_store import ProjectStore, utc_now


class WorkbenchStore:
    """Persistence for entities shared across trusted workbench modules."""

    def __init__(self, project: ProjectStore) -> None:
        self.project = project

    def save_evidence(self, evidence: Evidence) -> Evidence:
        with self.project.workspace_write_connection() as connection:
            connection.execute(
                """
                INSERT INTO workbench_evidence(
                    id, module_id, shot_id, version_id, evidence_type,
                    source, subject_type, subject_id, payload_json, status,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.id,
                    evidence.module_id,
                    evidence.shot_id,
                    evidence.version_id,
                    evidence.evidence_type.value,
                    evidence.source.value,
                    evidence.subject_type,
                    evidence.subject_id,
                    canonical_json(dict(evidence.payload)),
                    evidence.status.value,
                    evidence.created_at,
                ),
            )
        return evidence

    def list_evidence(
        self,
        module_id: str,
        *,
        subject_type: str | None = None,
        subject_id: str | None = None,
        include_stale: bool = True,
    ) -> tuple[Evidence, ...]:
        clauses = ["module_id = ?"]
        values: list[object] = [module_id]
        if subject_type is not None:
            clauses.append("subject_type = ?")
            values.append(subject_type)
        if subject_id is not None:
            clauses.append("subject_id = ?")
            values.append(subject_id)
        if not include_stale:
            clauses.append("status = 'current'")
        query = (
            "SELECT * FROM workbench_evidence WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at, id"
        )
        with self.project.workspace_read_connection() as connection:
            rows = connection.execute(query, values).fetchall()
        return tuple(self._evidence_from_row(row) for row in rows)

    def save_annotation(self, annotation: Annotation) -> Annotation:
        with self.project.workspace_write_connection() as connection:
            connection.execute(
                """
                INSERT INTO workbench_annotations(
                    id, module_id, shot_id, version_id, evidence_id,
                    annotation_type, geometry_json, label, style_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    annotation.id,
                    annotation.module_id,
                    annotation.shot_id,
                    annotation.version_id,
                    annotation.evidence_id,
                    annotation.annotation_type,
                    canonical_json(dict(annotation.geometry)),
                    annotation.label,
                    canonical_json(dict(annotation.style)),
                    annotation.created_at,
                    annotation.updated_at,
                ),
            )
        return annotation

    def list_annotations(
        self,
        module_id: str,
        *,
        shot_id: str | None = None,
        version_id: str | None = None,
    ) -> tuple[Annotation, ...]:
        clauses = ["module_id = ?"]
        values: list[object] = [module_id]
        if shot_id is not None:
            clauses.append("shot_id = ?")
            values.append(shot_id)
        if version_id is not None:
            clauses.append("version_id = ?")
            values.append(version_id)
        query = (
            "SELECT * FROM workbench_annotations WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at, id"
        )
        with self.project.workspace_read_connection() as connection:
            rows = connection.execute(query, values).fetchall()
        return tuple(self._annotation_from_row(row) for row in rows)

    def save_task(self, task: Task) -> Task:
        with self.project.workspace_write_connection() as connection:
            connection.execute(
                """
                INSERT INTO workbench_tasks(
                    id, module_id, shot_id, version_id, source_evidence_id,
                    source_annotation_id, title, description, priority,
                    status, verification_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.module_id,
                    task.shot_id,
                    task.version_id,
                    task.source_evidence_id,
                    task.source_annotation_id,
                    task.title,
                    task.description,
                    task.priority.value,
                    task.status.value,
                    canonical_json(dict(task.verification)),
                    task.created_at,
                    task.updated_at,
                ),
            )
        return task

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
    ) -> Task:
        now = utc_now()
        with self.project.workspace_write_connection() as connection:
            connection.execute(
                """
                UPDATE workbench_tasks
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (status.value, now, task_id),
            )
            row = connection.execute(
                "SELECT * FROM workbench_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown task: {task_id}")
        return self._task_from_row(row)

    def list_tasks(
        self,
        module_id: str,
        *,
        shot_id: str | None = None,
        version_id: str | None = None,
    ) -> tuple[Task, ...]:
        clauses = ["module_id = ?"]
        values: list[object] = [module_id]
        if shot_id is not None:
            clauses.append("shot_id = ?")
            values.append(shot_id)
        if version_id is not None:
            clauses.append("version_id = ?")
            values.append(version_id)
        query = (
            "SELECT * FROM workbench_tasks WHERE "
            + " AND ".join(clauses)
            + """
              ORDER BY CASE priority
                  WHEN 'critical' THEN 0
                  WHEN 'high' THEN 1
                  WHEN 'medium' THEN 2
                  ELSE 3
              END, created_at, id
            """
        )
        with self.project.workspace_read_connection() as connection:
            rows = connection.execute(query, values).fetchall()
        return tuple(self._task_from_row(row) for row in rows)

    def save_artifact(self, artifact: DerivedArtifact) -> DerivedArtifact:
        with self.project.workspace_write_connection() as connection:
            connection.execute(
                """
                INSERT INTO workbench_derived_artifacts(
                    id, module_id, shot_id, version_id, artifact_type,
                    relative_path, input_hashes_json, parameters_json,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.id,
                    artifact.module_id,
                    artifact.shot_id,
                    artifact.version_id,
                    artifact.artifact_type,
                    artifact.relative_path,
                    canonical_json(dict(artifact.input_hashes)),
                    canonical_json(dict(artifact.parameters)),
                    artifact.status.value,
                    artifact.created_at,
                ),
            )
        return artifact

    def save_ai_concept_preview(
        self,
        preview: AIConceptPreview,
    ) -> AIConceptPreview:
        if not preview.relative_path.replace("\\", "/").startswith(
            "artifacts/ai_previews/"
        ):
            raise ValueError(
                "AIConceptPreview must stay under artifacts/ai_previews."
            )
        self.save_artifact(
            DerivedArtifact(
                id=preview.id,
                module_id=preview.module_id,
                shot_id=preview.shot_id,
                version_id=preview.source_version_id,
                artifact_type="ai_concept_preview",
                relative_path=preview.relative_path,
                input_hashes=dict(preview.input_hashes),
                parameters={
                    "provider_id": preview.provider_id,
                    "model_id": preview.model_id,
                    "instruction": dict(preview.instruction),
                    "protection_constraints": dict(
                        preview.protection_constraints
                    ),
                    "validation_metrics": dict(
                        preview.validation_metrics
                    ),
                    "preview_status": preview.preview_status.value,
                },
                created_at=preview.created_at,
            )
        )
        return preview

    def list_ai_concept_previews(
        self,
        module_id: str,
        *,
        shot_id: str | None = None,
        source_version_id: str | None = None,
    ) -> tuple[AIConceptPreview, ...]:
        clauses = [
            "module_id = ?",
            "artifact_type = 'ai_concept_preview'",
            "status != 'deleted'",
        ]
        values: list[object] = [module_id]
        if shot_id is not None:
            clauses.append("shot_id = ?")
            values.append(shot_id)
        if source_version_id is not None:
            clauses.append("version_id = ?")
            values.append(source_version_id)
        query = (
            "SELECT * FROM workbench_derived_artifacts WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at, id"
        )
        with self.project.workspace_read_connection() as connection:
            rows = connection.execute(query, values).fetchall()
        previews = []
        for row in rows:
            parameters = json.loads(row["parameters_json"])
            previews.append(
                AIConceptPreview(
                    id=str(row["id"]),
                    module_id=str(row["module_id"]),
                    shot_id=str(row["shot_id"]),
                    source_version_id=str(row["version_id"]),
                    provider_id=str(parameters["provider_id"]),
                    model_id=str(parameters["model_id"]),
                    relative_path=str(row["relative_path"]),
                    input_hashes=json.loads(row["input_hashes_json"]),
                    instruction=dict(parameters["instruction"]),
                    protection_constraints=dict(
                        parameters["protection_constraints"]
                    ),
                    validation_metrics=dict(
                        parameters["validation_metrics"]
                    ),
                    preview_status=AIConceptPreviewStatus(
                        str(parameters["preview_status"])
                    ),
                    created_at=str(row["created_at"]),
                )
            )
        return tuple(previews)

    def save_ai_run(self, run: AIRun) -> AIRun:
        self._assert_no_secret_fields(run.input_manifest)
        with self.project.workspace_write_connection() as connection:
            connection.execute(
                """
                INSERT INTO workbench_ai_runs(
                    id, module_id, reviewer_id, provider_id, model_id,
                    capability, request_hash, input_manifest_json,
                    output_json, status, error_code, error_message,
                    created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    output_json = excluded.output_json,
                    status = excluded.status,
                    error_code = excluded.error_code,
                    error_message = excluded.error_message,
                    completed_at = excluded.completed_at
                """,
                (
                    run.id,
                    run.module_id,
                    run.reviewer_id,
                    run.provider_id,
                    run.model_id,
                    run.capability,
                    run.request_hash,
                    canonical_json(dict(run.input_manifest)),
                    (
                        None
                        if run.output is None
                        else canonical_json(dict(run.output))
                    ),
                    run.status.value,
                    run.error_code,
                    run.error_message,
                    run.created_at,
                    run.completed_at,
                ),
            )
        return run

    def get_ai_run(self, run_id: str) -> AIRun | None:
        with self.project.workspace_read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM workbench_ai_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        return None if row is None else self._ai_run_from_row(row)

    def save_source_document(
        self,
        document: SourceDocument,
    ) -> SourceDocument:
        with self.project.workspace_write_connection() as connection:
            connection.execute(
                """
                INSERT INTO workbench_source_documents(
                    id, module_id, document_type, title, source_uri,
                    content_hash, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.id,
                    document.module_id,
                    document.document_type,
                    document.title,
                    document.source_uri,
                    document.content_hash,
                    canonical_json(dict(document.metadata)),
                    document.created_at,
                ),
            )
        return document

    def save_review_profile(
        self,
        profile: ReviewProfile,
        gates: tuple[QualityGate, ...],
    ) -> tuple[ReviewProfile, tuple[QualityGate, ...]]:
        with self.project.workspace_write_connection() as connection:
            connection.execute(
                """
                INSERT INTO workbench_review_profiles(
                    id, module_id, name, reviewer_ids_json, settings_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    reviewer_ids_json = excluded.reviewer_ids_json,
                    settings_json = excluded.settings_json,
                    updated_at = excluded.updated_at
                """,
                (
                    profile.id,
                    profile.module_id,
                    profile.name,
                    canonical_json(list(profile.reviewer_ids)),
                    canonical_json(dict(profile.settings)),
                    profile.created_at,
                    profile.updated_at,
                ),
            )
            connection.execute(
                "DELETE FROM workbench_quality_gates WHERE profile_id = ?",
                (profile.id,),
            )
            for gate in gates:
                if gate.profile_id != profile.id:
                    raise ValueError("Quality gate belongs to another profile.")
                connection.execute(
                    """
                    INSERT INTO workbench_quality_gates(
                        id, profile_id, dimension_id, display_name,
                        metric_key, operator, threshold_json, weight,
                        state, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        gate.id,
                        gate.profile_id,
                        gate.dimension_id,
                        gate.display_name,
                        gate.metric_key,
                        gate.operator,
                        canonical_json(dict(gate.threshold)),
                        gate.weight,
                        gate.state.value,
                        gate.updated_at,
                    ),
                )
        return profile, gates

    def get_review_profile(
        self,
        profile_id: str,
    ) -> tuple[ReviewProfile, tuple[QualityGate, ...]] | None:
        with self.project.workspace_read_connection() as connection:
            profile_row = connection.execute(
                "SELECT * FROM workbench_review_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
            gate_rows = connection.execute(
                """
                SELECT * FROM workbench_quality_gates
                WHERE profile_id = ? ORDER BY dimension_id
                """,
                (profile_id,),
            ).fetchall()
        if profile_row is None:
            return None
        profile = ReviewProfile(
            id=str(profile_row["id"]),
            module_id=str(profile_row["module_id"]),
            name=str(profile_row["name"]),
            reviewer_ids=tuple(json.loads(profile_row["reviewer_ids_json"])),
            settings=json.loads(profile_row["settings_json"]),
            created_at=str(profile_row["created_at"]),
            updated_at=str(profile_row["updated_at"]),
        )
        gates = tuple(
            QualityGate(
                id=str(row["id"]),
                profile_id=str(row["profile_id"]),
                dimension_id=str(row["dimension_id"]),
                display_name=str(row["display_name"]),
                metric_key=str(row["metric_key"]),
                operator=str(row["operator"]),
                threshold=json.loads(row["threshold_json"]),
                weight=float(row["weight"]),
                state=QualityGateState(str(row["state"])),
                updated_at=str(row["updated_at"]),
            )
            for row in gate_rows
        )
        return profile, gates

    @staticmethod
    def _evidence_from_row(row) -> Evidence:
        return Evidence(
            id=str(row["id"]),
            module_id=str(row["module_id"]),
            shot_id=row["shot_id"],
            version_id=row["version_id"],
            evidence_type=EvidenceType(str(row["evidence_type"])),
            source=EvidenceSource(str(row["source"])),
            subject_type=str(row["subject_type"]),
            subject_id=str(row["subject_id"]),
            payload=json.loads(row["payload_json"]),
            status=ArtifactStatus(str(row["status"])),
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _annotation_from_row(row) -> Annotation:
        return Annotation(
            id=str(row["id"]),
            module_id=str(row["module_id"]),
            shot_id=row["shot_id"],
            version_id=row["version_id"],
            evidence_id=row["evidence_id"],
            annotation_type=str(row["annotation_type"]),
            geometry=json.loads(row["geometry_json"]),
            label=str(row["label"]),
            style=json.loads(row["style_json"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _task_from_row(row) -> Task:
        return Task(
            id=str(row["id"]),
            module_id=str(row["module_id"]),
            shot_id=row["shot_id"],
            version_id=row["version_id"],
            source_evidence_id=row["source_evidence_id"],
            source_annotation_id=row["source_annotation_id"],
            title=str(row["title"]),
            description=str(row["description"]),
            priority=TaskPriority(str(row["priority"])),
            status=TaskStatus(str(row["status"])),
            verification=json.loads(row["verification_json"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _ai_run_from_row(row) -> AIRun:
        return AIRun(
            id=str(row["id"]),
            module_id=str(row["module_id"]),
            reviewer_id=str(row["reviewer_id"]),
            provider_id=str(row["provider_id"]),
            model_id=str(row["model_id"]),
            capability=str(row["capability"]),
            request_hash=str(row["request_hash"]),
            input_manifest=json.loads(row["input_manifest_json"]),
            output=(
                None
                if row["output_json"] is None
                else json.loads(row["output_json"])
            ),
            status=AIRunStatus(str(row["status"])),
            error_code=row["error_code"],
            error_message=row["error_message"],
            created_at=str(row["created_at"]),
            completed_at=row["completed_at"],
        )

    @classmethod
    def _assert_no_secret_fields(cls, value: object) -> None:
        blocked = {
            "api_key",
            "apikey",
            "authorization",
            "x-api-key",
            "access_token",
            "refresh_token",
        }
        if isinstance(value, Mapping):
            for key, nested in value.items():
                normalized = str(key).strip().lower().replace(" ", "_")
                if normalized in blocked:
                    raise ValueError(
                        "AI run input manifest must not contain credentials."
                    )
                cls._assert_no_secret_fields(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                cls._assert_no_secret_fields(nested)
