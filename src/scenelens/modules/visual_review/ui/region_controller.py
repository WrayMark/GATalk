from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QDialog, QMessageBox

from scenelens.modules.visual_review.presets import PresetCatalog
from scenelens.modules.visual_review.region_store import RegionStore
from scenelens.modules.visual_review.regions import (
    NormalizedRect,
    RegionPairView,
    RegionRecord,
    validate_region_size,
)
from scenelens.modules.visual_review.ui.region_widgets import (
    RegionListRow,
    RegionMetadataDialog,
    RegionPairPanel,
)
from scenelens.storage.errors import StorageError
from scenelens.storage.project_store import ProjectStore
from scenelens.ui.image_canvas import ImageCanvas, RegionOverlaySpec


REGION_COLOURS = (
    "#4FC3F7",
    "#FFB74D",
    "#81C784",
    "#BA68C8",
    "#E57373",
    "#4DB6AC",
    "#FFD54F",
    "#90A4AE",
)


class RegionController(QObject):
    status_message = Signal(str)
    analysis_requested = Signal(str)

    def __init__(
        self,
        reference_canvas: ImageCanvas,
        current_canvas: ImageCanvas,
        panel: RegionPairPanel,
        presets: PresetCatalog,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.reference_canvas = reference_canvas
        self.current_canvas = current_canvas
        self.panel = panel
        self.presets = presets
        self.project: ProjectStore | None = None
        self.store: RegionStore | None = None
        self.shot_id: str | None = None
        self.version_id: str | None = None
        self.selected_reference_id: str | None = None
        self.selected_current_id: str | None = None
        self.selected_pair_id: str | None = None
        self._pair_views: tuple[RegionPairView, ...] = ()
        self._regions: tuple[RegionRecord, ...] = ()

        self.reference_canvas.region_created.connect(
            lambda geometry: self._region_drawn("reference", geometry)
        )
        self.current_canvas.region_created.connect(
            lambda geometry: self._region_drawn("current", geometry)
        )
        self.reference_canvas.region_creation_rejected.connect(
            self.status_message
        )
        self.current_canvas.region_creation_rejected.connect(
            self.status_message
        )
        self.reference_canvas.region_selected.connect(
            lambda region_id: self.select_region("reference", region_id)
        )
        self.current_canvas.region_selected.connect(
            lambda region_id: self.select_region("current", region_id)
        )
        self.reference_canvas.region_geometry_changed.connect(
            self._geometry_changed
        )
        self.current_canvas.region_geometry_changed.connect(
            self._geometry_changed
        )
        self.panel.mode_toggled.connect(self.set_region_mode)
        self.panel.overlays_toggled.connect(self.set_overlays_visible)
        self.panel.pair_requested.connect(self._pair_dialog)
        self.panel.copy_previous_requested.connect(self.copy_previous_version)
        self.panel.selected.connect(self._list_selected)
        self.panel.edit_requested.connect(self._edit_dialog)
        self.panel.delete_requested.connect(self._delete_dialog)
        self.panel.reanalyze_requested.connect(self.analysis_requested)

    def set_context(
        self,
        project: ProjectStore | None,
        shot_id: str | None,
        version_id: str | None,
    ) -> None:
        changed = (
            project is not self.project
            or shot_id != self.shot_id
            or version_id != self.version_id
        )
        self.project = project
        self.store = None if project is None else RegionStore(project)
        self.shot_id = shot_id
        self.version_id = version_id
        if changed:
            self.selected_reference_id = None
            self.selected_current_id = None
            self.selected_pair_id = None
            self.panel.clear_analysis()
        editable = bool(project is not None and not project.read_only and shot_id)
        self.panel.set_editable(editable)
        if not editable:
            self.set_region_mode(False)
            self.panel.leave_region_mode()
        self.refresh()

    def refresh(self) -> None:
        if self.store is None or self.shot_id is None:
            self._pair_views = ()
            self._regions = ()
            self.panel.set_rows(())
            self.panel.clear_analysis()
            self.reference_canvas.clear_region_overlays()
            self.current_canvas.clear_region_overlays()
            return
        try:
            self._pair_views = self.store.list_pair_views(
                self.shot_id,
                self.version_id,
            )
            self._regions = self.store.list_regions(
                self.shot_id,
                version_id=self.version_id,
            )
        except StorageError as exc:
            self.status_message.emit(f"区域恢复失败：{exc}")
            return
        pair_by_region: dict[str, tuple[int, RegionPairView]] = {}
        for index, view in enumerate(self._pair_views):
            pair_by_region[view.reference_region.id] = (index, view)
            pair_by_region[view.current_region.id] = (index, view)
        reference_specs: list[RegionOverlaySpec] = []
        current_specs: list[RegionOverlaySpec] = []
        for region in self._regions:
            pair_info = pair_by_region.get(region.id)
            pair_index = None if pair_info is None else pair_info[0]
            colour = (
                "#78909C"
                if pair_index is None
                else REGION_COLOURS[pair_index % len(REGION_COLOURS)]
            )
            selected = region.id in {
                self.selected_reference_id,
                self.selected_current_id,
            }
            spec = RegionOverlaySpec(
                region.id,
                region.name,
                (
                    region.normalized_rect.x,
                    region.normalized_rect.y,
                    region.normalized_rect.width,
                    region.normalized_rect.height,
                ),
                colour,
                selected=selected,
                muted=not selected and self.selected_pair_id is not None,
            )
            (
                reference_specs
                if region.image_role == "reference"
                else current_specs
            ).append(spec)
        self.reference_canvas.set_region_overlays(reference_specs)
        self.current_canvas.set_region_overlays(current_specs)
        self.reference_canvas.set_regions_visible(self.panel.show_overlays.isChecked())
        self.current_canvas.set_regions_visible(self.panel.show_overlays.isChecked())
        rows: list[RegionListRow] = []
        paired_ids: set[str] = set()
        for index, view in enumerate(self._pair_views, start=1):
            paired_ids.update(
                (view.reference_region.id, view.current_region.id)
            )
            rows.append(
                RegionListRow(
                    row_id=view.pair.id,
                    row_kind="pair",
                    number=index,
                    colour=REGION_COLOURS[(index - 1) % len(REGION_COLOURS)],
                    name=view.pair.name,
                    semantic_type=view.pair.semantic_type,
                    reference_status="已设置",
                    current_status="已设置",
                    analysis_status=self._analysis_label(
                        view.analysis_status
                    ),
                    reference_region_id=view.reference_region.id,
                    current_region_id=view.current_region.id,
                )
            )
        for region in self._regions:
            if region.id in paired_ids:
                continue
            rows.append(
                RegionListRow(
                    row_id=region.id,
                    row_kind="region",
                    number=None,
                    colour="#78909C",
                    name=region.name,
                    semantic_type=region.semantic_type,
                    reference_status=(
                        "待配对" if region.image_role == "reference" else "—"
                    ),
                    current_status=(
                        "待配对" if region.image_role == "current" else "—"
                    ),
                    analysis_status="待配对",
                    reference_region_id=(
                        region.id if region.image_role == "reference" else None
                    ),
                    current_region_id=(
                        region.id if region.image_role == "current" else None
                    ),
                )
            )
        self.panel.set_rows(tuple(rows), self.selected_pair_id)
        self._update_selection_text()

    def create_region(
        self,
        role: str,
        geometry: tuple[float, float, float, float],
        name: str,
        semantic_type: str,
    ) -> RegionRecord:
        if self.store is None or self.shot_id is None:
            raise RuntimeError("没有可写的项目上下文")
        rect = NormalizedRect(*geometry)
        region = self.store.create_region(
            self.shot_id,
            role,
            None if role == "reference" else self.version_id,
            name,
            semantic_type,
            rect,
        )
        self.select_region(role, region.id)
        self.refresh()
        return region

    def pair_selected_regions(
        self,
        name: str,
        semantic_type: str,
        notes: str = "",
    ):
        if (
            self.store is None
            or self.selected_reference_id is None
            or self.selected_current_id is None
        ):
            raise RuntimeError("请先分别选择参考区域和当前区域")
        pair = self.store.create_pair(
            self.selected_reference_id,
            self.selected_current_id,
            name,
            semantic_type,
            notes,
        )
        self.selected_pair_id = pair.id
        self.refresh()
        self.analysis_requested.emit(pair.id)
        return pair

    def select_region(self, role: str, region_id: str) -> None:
        previous_pair_id = self.selected_pair_id
        if role == "reference":
            self.selected_reference_id = region_id
        else:
            self.selected_current_id = region_id
        containing = next(
            (
                view
                for view in self._pair_views
                if region_id
                in {
                    view.reference_region.id,
                    view.current_region.id,
                }
            ),
            None,
        )
        if containing is not None:
            self.selected_pair_id = containing.pair.id
            self.selected_reference_id = containing.reference_region.id
            self.selected_current_id = containing.current_region.id
        else:
            self.selected_pair_id = None
        self.reference_canvas.select_region(self.selected_reference_id)
        self.current_canvas.select_region(self.selected_current_id)
        self._update_selection_text()
        if (
            containing is not None
            and containing.pair.id != previous_pair_id
        ):
            self.analysis_requested.emit(containing.pair.id)

    def set_region_mode(self, active: bool) -> None:
        self.reference_canvas.set_region_mode(active)
        self.current_canvas.set_region_mode(active)
        self.status_message.emit(
            (
                "区域模式已开启：拖动创建，选中后移动或调整大小，Esc 退出。"
                if active
                else "已返回图片查看模式。"
            )
        )

    def set_overlays_visible(self, visible: bool) -> None:
        self.reference_canvas.set_regions_visible(visible)
        self.current_canvas.set_regions_visible(visible)

    def escape(self) -> bool:
        if not (
            self.reference_canvas.region_mode
            or self.current_canvas.region_mode
        ):
            return False
        self.reference_canvas.cancel_region_creation()
        self.current_canvas.cancel_region_creation()
        self.panel.leave_region_mode()
        return True

    def copy_previous_version(self) -> None:
        if (
            self.project is None
            or self.store is None
            or self.shot_id is None
            or self.version_id is None
        ):
            return
        versions = self.project.list_versions(self.shot_id)
        current = next(
            (item for item in versions if item.id == self.version_id),
            None,
        )
        if current is None:
            return
        source = next(
            (
                item
                for item in reversed(versions)
                if item.ordinal < current.ordinal
                and self.store.list_pair_views(self.shot_id, item.id)
            ),
            None,
        )
        if source is None:
            self.status_message.emit("没有可复制的上一版本区域对。")
            return
        try:
            copied = self.store.copy_previous_version_regions(
                self.shot_id,
                source.id,
                self.version_id,
            )
        except StorageError as exc:
            self.status_message.emit(f"复制区域失败：{exc}")
            return
        self.refresh()
        self.status_message.emit(
            f"已复制 {len(copied)} 组区域；请检查新版本中的位置是否仍然准确。"
        )

    def _region_drawn(
        self,
        role: str,
        geometry: tuple[float, float, float, float],
    ) -> None:
        if self.project is None or self.project.read_only:
            self.status_message.emit("当前没有可写项目，不能创建区域。")
            return
        if role == "current" and self.version_id is None:
            self.status_message.emit("请先导入或选择一个截图 Version。")
            return
        try:
            validate_region_size(NormalizedRect(*geometry))
        except ValueError as exc:
            self.status_message.emit(str(exc))
            return
        next_number = len(self._regions) + 1
        dialog = RegionMetadataDialog(
            "创建参考区域" if role == "reference" else "创建当前区域",
            self.presets,
            name=f"区域 {next_number}",
            parent=self.panel,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, semantic, _notes = dialog.values()
        try:
            self.create_region(role, geometry, name, semantic)
            self.status_message.emit(f"已创建{name}，可选择另一侧区域后建立配对。")
        except (StorageError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self.panel, "无法创建区域", str(exc))
            self.refresh()

    def _geometry_changed(
        self,
        region_id: str,
        geometry: tuple[float, float, float, float],
    ) -> None:
        if self.store is None:
            return
        try:
            self.store.update_region(
                region_id,
                rect=NormalizedRect(*geometry),
            )
            self.refresh()
            self.status_message.emit("区域位置已保存；旧分析已标记为过期。")
            containing = next(
                (
                    view
                    for view in self._pair_views
                    if region_id
                    in {
                        view.reference_region.id,
                        view.current_region.id,
                    }
                ),
                None,
            )
            if containing is not None:
                self.analysis_requested.emit(containing.pair.id)
        except (StorageError, ValueError) as exc:
            QMessageBox.warning(self.panel, "无法调整区域", str(exc))
            self.refresh()

    def _pair_dialog(self) -> None:
        if (
            self.selected_reference_id is None
            or self.selected_current_id is None
        ):
            self.status_message.emit("请先分别选择一个参考区域和当前区域。")
            return
        reference = next(
            (r for r in self._regions if r.id == self.selected_reference_id),
            None,
        )
        dialog = RegionMetadataDialog(
            "建立区域配对",
            self.presets,
            name="区域对" if reference is None else reference.name,
            semantic_type=(
                "自定义" if reference is None else reference.semantic_type
            ),
            notes="",
            parent=self.panel,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, semantic, notes = dialog.values()
        try:
            self.pair_selected_regions(name, semantic, notes)
            self.status_message.emit(f"已建立区域对：{name}")
        except (StorageError, RuntimeError) as exc:
            QMessageBox.warning(self.panel, "无法建立配对", str(exc))

    def _list_selected(self, row_kind: str, row_id: str) -> None:
        if row_kind == "pair":
            view = next(
                (item for item in self._pair_views if item.pair.id == row_id),
                None,
            )
            if view is None:
                return
            self.selected_pair_id = row_id
            self.selected_reference_id = view.reference_region.id
            self.selected_current_id = view.current_region.id
            self.reference_canvas.select_region(self.selected_reference_id)
            self.current_canvas.select_region(self.selected_current_id)
            self._update_selection_text()
            self.analysis_requested.emit(row_id)
            return
        region = next((item for item in self._regions if item.id == row_id), None)
        if region is not None:
            self.select_region(region.image_role, region.id)

    def _edit_dialog(self, row_kind: str, row_id: str) -> None:
        if self.store is None:
            return
        try:
            if row_kind == "pair":
                current = self.store.get_pair(row_id)
                dialog = RegionMetadataDialog(
                    "编辑区域对",
                    self.presets,
                    name=current.name,
                    semantic_type=current.semantic_type,
                    notes=current.notes,
                    parent=self.panel,
                )
            else:
                current = self.store.get_region(row_id)
                dialog = RegionMetadataDialog(
                    "编辑区域",
                    self.presets,
                    name=current.name,
                    semantic_type=current.semantic_type,
                    parent=self.panel,
                )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            name, semantic, notes = dialog.values()
            if row_kind == "pair":
                self.store.update_pair(
                    row_id,
                    name=name,
                    semantic_type=semantic,
                    notes=notes,
                )
            else:
                self.store.update_region(
                    row_id,
                    name=name,
                    semantic_type=semantic,
                )
            self.refresh()
        except StorageError as exc:
            QMessageBox.warning(self.panel, "编辑失败", str(exc))

    def _delete_dialog(self, row_kind: str, row_id: str) -> None:
        if self.store is None:
            return
        answer = QMessageBox.question(
            self.panel,
            "确认删除",
            (
                "删除区域对后，两侧矩形会保留为待配对区域。"
                if row_kind == "pair"
                else "删除该区域会同时删除与它关联的区域对和分析记录。"
            ),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            if row_kind == "pair":
                self.store.delete_pair(row_id)
                self.selected_pair_id = None
                self.panel.clear_analysis()
            else:
                self.store.delete_region(row_id)
                if self.selected_reference_id == row_id:
                    self.selected_reference_id = None
                if self.selected_current_id == row_id:
                    self.selected_current_id = None
            self.refresh()
            self.status_message.emit("区域数据已删除。")
        except StorageError as exc:
            QMessageBox.warning(self.panel, "删除失败", str(exc))

    def _update_selection_text(self) -> None:
        reference_name = next(
            (
                item.name
                for item in self._regions
                if item.id == self.selected_reference_id
            ),
            "未选择",
        )
        current_name = next(
            (
                item.name
                for item in self._regions
                if item.id == self.selected_current_id
            ),
            "未选择",
        )
        self.panel.set_selection_text(
            f"参考：{reference_name}　|　当前：{current_name}"
        )

    def pair_view(self, pair_id: str) -> RegionPairView | None:
        return next(
            (view for view in self._pair_views if view.pair.id == pair_id),
            None,
        )

    def pair_views(self) -> tuple[RegionPairView, ...]:
        return self._pair_views

    def selected_current_rect(
        self,
    ) -> tuple[float, float, float, float] | None:
        """Return the selected current-image region in normalized image space."""
        if self.selected_pair_id is None:
            return None
        view = self.pair_view(self.selected_pair_id)
        if view is None:
            return None
        rect = view.current_region.normalized_rect
        return rect.x, rect.y, rect.width, rect.height

    @staticmethod
    def _analysis_label(status: str) -> str:
        return {
            "pending": "待分析",
            "complete": "已完成",
            "stale": "已过期",
            "failed": "失败",
        }.get(status, status)
