"""Safe, collision-resistant file operations with a reversible journal."""
import shutil
from collections.abc import Callable
from pathlib import Path
from app.database.repository import Repository
from app.models import SortPlanItem

def unique_destination(destination: Path) -> Path:
    if not destination.exists(): return destination
    for index in range(1, 100000):
        candidate = destination.with_name(f"{destination.stem} ({index}){destination.suffix}")
        if not candidate.exists(): return candidate
    raise OSError(f"Не удалось подобрать свободное имя: {destination}")

def execute_plan(plan: list[SortPlanItem], repository: Repository, move: bool = False, stop: Callable[[], bool] | None = None, progress: Callable[[int, SortPlanItem], None] | None = None) -> None:
    for index, item in enumerate(plan, start=1):
        if stop and stop(): break
        try:
            item.destination.parent.mkdir(parents=True, exist_ok=True); target = unique_destination(item.destination)
            if move: shutil.move(str(item.source), str(target)); item.action = "move"
            else: shutil.copy2(item.source, target); item.action = "copy"
            item.destination, item.status = target, "done"; repository.log_operation(item.source, target, item.action, item.status); repository.mark_copied(item.source)
        except (OSError, shutil.Error) as exc:
            item.status, item.error = "error", str(exc); repository.log_operation(item.source, item.destination, item.action, item.status, item.error)
        if progress: progress(index, item)
