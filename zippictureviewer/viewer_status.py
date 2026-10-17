from __future__ import annotations

from .folder_context import FolderContext
from .image_view import ImageView
from .issue_dialog import IssueDialog
from .models import ImageEntry, ScanIssue, ScanResult
from .source_loader import SourceLoader
from .viewer_controller import ViewerController
from .viewer_controls import ViewerControls, ViewerInfoPanel
from .viewer_presenter import ImagePresenter


class ViewerStatus:
    """Reflect controller, presenter and loader state in the floating panels."""

    def __init__(
        self,
        controller: ViewerController,
        presenter: ImagePresenter,
        source_loader: SourceLoader,
        controls: ViewerControls,
        info_panel: ViewerInfoPanel,
        issue_dialog: IssueDialog,
        image_view: ImageView,
    ) -> None:
        self._controller = controller
        self._presenter = presenter
        self._source_loader = source_loader
        self._controls = controls
        self._file_label = info_panel.file_label
        self._issue_dialog = issue_dialog
        self._image_view = image_view
        self._file_label.setToolTip("")

    def set_status(self, message: str) -> None:
        self._controls.status_label.setText(message)

    def show_entry(self, entry: ImageEntry) -> None:
        context = self._controller.current_context
        if context is not None:
            self.select_encoding(context, entry)
        text = f"{entry.archive_path}  |  {entry.member_name}"
        self._file_label.setText(text)
        self._file_label.setToolTip(text)
        self.set_status(self._controller.state.position_label)
        self.update_navigation()

    def show_empty_source(self, context: FolderContext, result: ScanResult) -> None:
        if result.issues:
            message = "이미지 컨테이너를 읽지 못했습니다"
        elif result.discovered_files == 0:
            message = "빈 폴더입니다"
        else:
            message = "지원되는 이미지 형식이 없습니다"
        self._image_view.show_message(message)
        self._file_label.setText(str(context.logical_path))
        self._file_label.setToolTip(str(context.logical_path))
        self.set_status("0 / 0")
        self.update_navigation()

    def update_navigation(self) -> None:
        state = self._controller.state
        controls = self._controls
        has_entries = state.has_entries
        has_source = self._controller.current_context is not None
        controls.previous_folder_button.setEnabled(has_source)
        controls.next_folder_button.setEnabled(has_source)
        controls.refresh_button.setEnabled(has_source)
        controls.previous_archive_button.setEnabled(
            has_entries and state.has_previous_archive()
        )
        controls.next_archive_button.setEnabled(has_entries and state.has_next_archive())
        controls.previous_button.setEnabled(has_entries and state.current_index > 0)
        controls.next_button.setEnabled(has_entries)
        for button in (
            controls.fit_button,
            controls.actual_size_button,
            controls.zoom_out_button,
            controls.zoom_in_button,
        ):
            button.setEnabled(has_entries)

    def update_issues(self) -> None:
        count = len(self._controller.scan_issues) + len(self._presenter.errors)
        self._controls.set_issue_count(count)
        if self._issue_dialog.isVisible():
            self._issue_dialog.set_messages(self.issue_messages())

    def issue_messages(self) -> list[str]:
        messages = [
            f"[{issue.error_kind}] {issue.target_path}\n{issue.message}"
            for issue in self._controller.scan_issues
            if isinstance(issue, ScanIssue)
        ]
        messages.extend(self._presenter.issue_messages())
        return messages

    def select_encoding(
        self,
        context: FolderContext,
        entry: ImageEntry | None = None,
    ) -> None:
        combo = self._controls.encoding_combo
        index = combo.findData(self._source_loader.encoding_for(context, entry))
        blocked = combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(blocked)
