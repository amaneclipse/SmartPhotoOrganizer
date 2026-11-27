"""PySide6 desktop interface for the MVP."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import sqlite3
from pathlib import Path
from app.classifiers.rule_based import classify
from app.config.categories import REVIEW_ROOT
from app.core.scanner import scan_images
from app.database.repository import Repository
from app.models import ClassificationResult, SortPlanItem
from app.sorting.engine import execute_plan
from app.ai.base import AIProviderError, ProviderConfig
from app.ai.manager import AIManager, AnalysisMode
from app.ai.prompt import CLASSIFICATION_PROMPT
from app.config.settings import AISettings, load_settings, save_settings
from app.security.keyring_store import KeyringStore, SecureStorageError
try:
    from PySide6.QtCore import QThread, Signal
    from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QProgressBar, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget
except ImportError:
    QApplication = None

if QApplication is not None:
    class ScanWorker(QThread):
        found, finished, error = Signal(object), Signal(), Signal(str)
        def __init__(self, roots, database_path, ai_manager, api_keys: list[str] | None = None, parallel_requests: int = 20): super().__init__(); self.roots, self.database_path, self.ai_manager, self.api_keys, self.parallel_requests = roots, Path(database_path), ai_manager, api_keys or [], max(1, min(200, parallel_requests)); self.repository = None; self.skip_processed = getattr(ai_manager.limits, "skip_processed", True)
        def run(self):
            self.repository = None
            try:
                self.repository = Repository(self.database_path)
                keys_list = [key.strip() for key in self.api_keys if key.strip()]
                if not keys_list and self.ai_manager.mode != AnalysisMode.LOCAL:
                    keys_list = [self.ai_manager.provider.config.api_key]
                batch = []
                submitted_images = 0
                result_id = 0
                for record in scan_images(self.roots, should_stop=self.isInterruptionRequested):
                    if self.isInterruptionRequested(): break
                    try:
                        if self.skip_processed and self.repository.is_analyzed(record.path): continue
                        record_id = result_id; result_id += 1
                        if self.skip_processed:
                            cached_result = self.repository.get_analysis(record.path)
                            if cached_result is not None:
                                self.found.emit((record_id, record, cached_result)); continue
                        if self.ai_manager.mode != AnalysisMode.LOCAL and self.ai_manager.images_analyzed + submitted_images >= self.ai_manager.limits.max_images: break
                        if self.ai_manager.mode != AnalysisMode.LOCAL and self.ai_manager.limits.max_budget_usd is not None and self.ai_manager.spent_usd >= self.ai_manager.limits.max_budget_usd: break
                        key = keys_list[record_id % len(keys_list)] if keys_list else ""
                        batch.append((record_id, record, key)); submitted_images += 1
                        if len(batch) == 100:
                            self._process_batch(batch, keys_list); batch = []
                    except (OSError, ValueError) as exc:
                        self.error.emit(f"Файл {record.path.name}: {exc}"); continue
                if batch:
                    self._process_batch(batch, keys_list)
                self.finished.emit()
            except Exception as exc: self.error.emit(str(exc))
            finally:
                if self.repository is not None:
                    self.repository.close()
        def _process_batch(self, batch, keys_list):
            max_workers = min(self.parallel_requests, len(batch))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                pending = {executor.submit(self._process_record, record, key): (record_id, record) for record_id, record, key in batch}
                for future in as_completed(pending):
                    record_id, record = pending[future]
                    try:
                        result, manager = future.result()
                        if manager is not None:
                            self.ai_manager.requests += manager.requests
                            self.ai_manager.images_analyzed += manager.images_analyzed
                            self.ai_manager.spent_usd += manager.spent_usd
                        self.repository.save_analysis(record, result); self.found.emit((record_id, record, result))
                    except AIProviderError as exc:
                        if "429" in str(exc): self.error.emit(f"Файл {record.path.name}: Превышен лимит запросов к API (429). Попробуйте позже или уменьшите количество параллельных запросов в настройках.")
                        else: self.error.emit(f"Файл {record.path.name}: {exc}")
                        continue
                    except (OSError, ValueError) as exc:
                        self.error.emit(f"Файл {record.path.name}: {exc}"); continue
        def _process_record(self, record, api_key):
            result = classify(record); manager = None
            if self.ai_manager.mode == AnalysisMode.CLOUD or (self.ai_manager.mode == AnalysisMode.HYBRID and result.confidence < 0.60):
                config = self.ai_manager.provider.config
                manager = AIManager(self.ai_manager.mode, ProviderConfig(config.provider_id, config.model, config.base_url, api_key, config.timeout_seconds), self.ai_manager.limits)
                remote = manager.analyze(record.path, CLASSIFICATION_PROMPT); result = ClassificationResult(str(remote.get("category", "Разное")), str(remote.get("subcategory", "Неопределённая категория")), str(remote.get("source", "Неизвестный источник")), float(remote.get("confidence", 0.0)), list(remote.get("tags", [])), bool(remote.get("is_screenshot", False)), str(remote.get("screenshot_kind", "")), str(remote.get("text", "")), result.orientation, "Результат выбранного AI-провайдера")
            return result, manager

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__(); self.setWindowTitle("Smart Photo Organizer"); self.resize(1100, 700); self.repository = Repository(Path("organizer.sqlite3")); self.records = []; self.worker = None; self.ai_settings_path = Path("ai_settings.json"); self.ai_settings = load_settings(self.ai_settings_path); self.keyring = KeyringStore(); self._build_ui(); self.ai_key.setPlaceholderText("Можно вставить несколько ключей через запятую"); self.ai_provider_type = QComboBox(); self.ai_provider_type.addItem("OpenAI / Compatible (OpenRouter)", "openai"); self.ai_provider_type.addItem("Google Gemini", "gemini"); self._active_provider_type = "gemini" if self.ai_settings.provider_type == "gemini" else "openai"; self.ai_provider_type.setCurrentIndex(1 if self._active_provider_type == "gemini" else 0); self.ai_provider_type.currentTextChanged.connect(self._provider_type_changed); self.ai_parallel_requests = QSpinBox(); self.ai_parallel_requests.setRange(1, 200); self.ai_parallel_requests.setValue(self.ai_settings.parallel_requests); self.reset_cache_button = QPushButton("Сбросить кэш (БД)"); self.reset_cache_button.clicked.connect(self.reset_cache); self.tabs.widget(2).layout().addRow("Тип провайдера:", self.ai_provider_type); self.tabs.widget(2).layout().addRow("Параллельные запросы:", self.ai_parallel_requests); self.tabs.widget(2).layout().addRow(self.reset_cache_button); self._load_provider_settings(self._active_provider_type)
        def _build_ui(self):
            root, layout = QWidget(), QVBoxLayout(); root.setLayout(layout); controls = QHBoxLayout(); self.source, self.destination = QLineEdit(), QLineEdit(); self.source.setPlaceholderText("Исходная папка"); self.destination.setPlaceholderText("Папка назначения")
            for field, text, handler in ((self.source, "Выбрать источник", self.choose_source), (self.destination, "Выбрать назначение", self.choose_destination)):
                button = QPushButton(text); button.clicked.connect(handler); controls.addWidget(field); controls.addWidget(button)
            layout.addLayout(controls); actions = QHBoxLayout()
            for label, handler in (("Сканировать и анализировать", self.scan), ("Предварительный просмотр", self.preview), ("Начать копирование", self.copy_files), ("Остановить", self.stop)):
                button = QPushButton(label); button.clicked.connect(handler); actions.addWidget(button)
            layout.addLayout(actions); self.progress = QProgressBar(); layout.addWidget(self.progress); self.status = QLabel("Готово. Локальный режим не требует API-ключа."); layout.addWidget(self.status); self.tabs = QTabWidget(); self.table = QTableWidget(0, 7); self.table.setHorizontalHeaderLabels(["ID", "Файл", "Категория", "Подкатегория", "Источник", "Уверенность", "Статус"]); self.tabs.addTab(self.table, "Результаты"); self.log = QTextEdit(); self.log.setReadOnly(True); self.tabs.addTab(self.log, "Журнал"); self.tabs.addTab(self._build_ai_tab(), "Настройки → Искусственный интеллект"); layout.addWidget(self.tabs); self.setCentralWidget(root)
        def _build_ai_tab(self):
            tab, form = QWidget(), QFormLayout(); self.ai_mode = QComboBox(); self.ai_mode.addItems(["Локальный режим", "Облачный режим", "Гибридный режим"]); self.ai_mode.setCurrentIndex({"local": 0, "cloud": 1, "hybrid": 2}.get(self.ai_settings.mode, 0)); self.ai_provider = QComboBox(); self.ai_provider.addItems(["openai", "openai-compatible"]); self.ai_provider.setCurrentText(self.ai_settings.provider_id); self.ai_model = QLineEdit(self.ai_settings.model); self.ai_url = QLineEdit(self.ai_settings.base_url); self.ai_key = QLineEdit(); self.ai_key.setEchoMode(QLineEdit.EchoMode.Password); self.ai_show_key = QCheckBox("Показать ключ"); self.ai_show_key.toggled.connect(lambda checked: self.ai_key.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)); self.ai_max_images = QSpinBox(); self.ai_max_images.setRange(1, 1000000); self.ai_max_images.setValue(self.ai_settings.max_images); self.ai_max_requests = QSpinBox(); self.ai_max_requests.setRange(1, 1000000); self.ai_max_requests.setValue(self.ai_settings.max_requests); self.ai_budget = QDoubleSpinBox(); self.ai_budget.setRange(0, 1000000); self.ai_budget.setSpecialValueText("Не ограничивать"); self.ai_budget.setValue(self.ai_settings.max_budget_usd or 0); form.addRow("Режим:", self.ai_mode); form.addRow("Провайдер:", self.ai_provider); form.addRow("Модель:", self.ai_model); form.addRow("Base URL:", self.ai_url); form.addRow("API-ключ:", self.ai_key); form.addRow("", self.ai_show_key); form.addRow("Макс. изображений:", self.ai_max_images); form.addRow("Макс. запросов:", self.ai_max_requests); form.addRow("Бюджет USD:", self.ai_budget); buttons = QHBoxLayout(); check = QPushButton("Проверить подключение"); check.clicked.connect(self.check_ai_connection); save = QPushButton("Сохранить настройки"); save.clicked.connect(self.save_ai_settings); delete = QPushButton("Удалить ключ"); delete.clicked.connect(self.delete_ai_key); buttons.addWidget(check); buttons.addWidget(save); buttons.addWidget(delete); form.addRow(buttons); warning = QLabel("Облачный режим отправляет выбранные изображения провайдеру. Проверьте его условия обработки данных и конфиденциальности."); warning.setWordWrap(True); form.addRow(warning); tab.setLayout(form); return tab
        def choose_source(self):
            if path := QFileDialog.getExistingDirectory(self, "Исходная папка"): self.source.setText(path)
        def choose_destination(self):
            if path := QFileDialog.getExistingDirectory(self, "Папка назначения"): self.destination.setText(path)
        def scan(self):
            source = Path(self.source.text().strip())
            if not source.is_dir(): QMessageBox.warning(self, "Проверка", "Выберите существующую исходную папку."); return
            try:
                mode, config = self._ai_config(); manager = AIManager(mode, config, self.ai_settings.limits())
                if mode != AnalysisMode.LOCAL and QMessageBox.question(self, "Облачный анализ", "Изображения будут отправлены выбранному провайдеру. Возможна дополнительная оплата. Продолжить?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes: return
            except (AIProviderError, SecureStorageError, OSError) as exc: QMessageBox.warning(self, "AI", str(exc)); return
            keys_list = [key.strip() for key in config.api_key.replace(",", "\n").splitlines() if key.strip()]; self.records.clear(); self.table.setRowCount(0); self.progress.setRange(0, 0); self.status.setText("Сканирование и анализ…"); self.worker = ScanWorker([source], self.repository.database_path, manager, keys_list, self.ai_parallel_requests.value()); self.worker.found.connect(self.add_result); self.worker.finished.connect(self.scan_finished); self.worker.error.connect(self.handle_worker_error); self.worker.start()
        def handle_worker_error(self, error):
            if "429" in error or "Доступные модели:" in error: self.log.append(error)
            else: QMessageBox.critical(self, "Ошибка", error)
        def _remember_provider_settings(self, provider_type):
            if provider_type == "gemini": self.ai_settings.gemini_model, self.ai_settings.gemini_base_url = self.ai_model.text().strip(), self.ai_url.text().strip()
            else: self.ai_settings.openai_model, self.ai_settings.openai_base_url = self.ai_model.text().strip(), self.ai_url.text().strip()
        def _load_provider_settings(self, provider_type):
            if provider_type == "gemini": model, base_url, key_id = self.ai_settings.gemini_model or "gemini-2.5-flash", "", "gemini"
            else: model, base_url, key_id = self.ai_settings.openai_model or self.ai_settings.model, self.ai_settings.openai_base_url or self.ai_settings.base_url, self.ai_provider.currentText()
            self.ai_model.setText(model); self.ai_url.setText(base_url); self.ai_url.setPlaceholderText("Для Gemini не используется" if provider_type == "gemini" else "https://api.openai.com/v1"); self.ai_key.setText(self.keyring.get(key_id) or "")
        def _provider_type_changed(self, _value=None):
            provider_type = self.ai_provider_type.currentData(); self._remember_provider_settings(self._active_provider_type); self._load_provider_settings(provider_type); self._active_provider_type = provider_type
        def scan_finished(self):
            stopped = self.worker is not None and self.worker.isInterruptionRequested()
            self.progress.setRange(0, 1); self.progress.setValue(1); self.status.setText("Остановлено пользователем" if stopped else f"Готово: {len(self.records)} изображений")
        def _ai_config(self):
            mode = [AnalysisMode.LOCAL, AnalysisMode.CLOUD, AnalysisMode.HYBRID][self.ai_mode.currentIndex()]; provider_id = "gemini" if self.ai_provider_type.currentData() == "gemini" else self.ai_provider.currentText(); key = self.keyring.get(provider_id) or self.ai_key.text().strip(); config = ProviderConfig(provider_id, self.ai_model.text().strip(), self.ai_url.text().strip(), key); return mode, config
        def check_ai_connection(self):
            try:
                mode, config = self._ai_config(); keys_list = [key.strip() for key in config.api_key.replace(",", "\n").splitlines() if key.strip()]; check_config = ProviderConfig(config.provider_id, config.model, config.base_url, keys_list[0] if keys_list else "", config.timeout_seconds); AIManager(mode, check_config, self.ai_settings.limits()).check_connection(); QMessageBox.information(self, "AI", "Подключение успешно.")
            except (AIProviderError, SecureStorageError, OSError) as exc:
                if "Доступные модели:" in str(exc): self.log.append(str(exc))
                else: QMessageBox.warning(self, "AI", str(exc))
        def save_ai_settings(self):
            provider_type = self.ai_provider_type.currentData(); self._remember_provider_settings(provider_type); self.ai_settings.mode = ["local", "cloud", "hybrid"][self.ai_mode.currentIndex()]; self.ai_settings.provider_id = self.ai_provider.currentText(); self.ai_settings.model = self.ai_model.text().strip(); self.ai_settings.base_url = self.ai_url.text().strip(); self.ai_settings.max_images = self.ai_max_images.value(); self.ai_settings.max_requests = self.ai_max_requests.value(); self.ai_settings.max_budget_usd = self.ai_budget.value() or None; self.ai_settings.parallel_requests = self.ai_parallel_requests.value(); self.ai_settings.provider_type = provider_type
            try:
                provider_id = "gemini" if self.ai_provider_type.currentData() == "gemini" else self.ai_provider.currentText()
                if self.ai_key.text(): self.keyring.save(provider_id, self.ai_key.text()); self.ai_key.clear()
                save_settings(self.ai_settings_path, self.ai_settings); QMessageBox.information(self, "AI", "Настройки сохранены. Секрет хранится только в Windows Credential Manager.")
            except SecureStorageError as exc: QMessageBox.warning(self, "Безопасность", str(exc))
        def delete_ai_key(self):
            try: self.keyring.delete("gemini" if self.ai_provider_type.currentData() == "gemini" else self.ai_provider.currentText()); self.ai_key.clear(); QMessageBox.information(self, "AI", "Ключ удалён из защищённого хранилища.")
            except SecureStorageError as exc: QMessageBox.warning(self, "Безопасность", str(exc))
        def add_result(self, item):
            record_id, record, result = item; self.records.append((record, result)); row = self.table.rowCount(); self.table.insertRow(row); values = [record_id, record.path.name, result.category, result.subcategory, result.source, f"{result.confidence:.0%}", "На проверку" if result.confidence < 0.60 else "Готово"]
            for column, value in enumerate(values): self.table.setItem(row, column, QTableWidgetItem(str(value)))
        def make_plan(self, root): return [SortPlanItem(record.path, root / (REVIEW_ROOT if result.confidence < 0.60 else result.category) / result.subcategory / result.source / record.path.name, result) for record, result in self.records]
        def preview(self):
            if not self.records: self.status.setText("Сначала выполните сканирование."); return
            plan = self.make_plan(Path(self.destination.text().strip() or "Фотоархив")); self.log.append(f"Предварительный просмотр: {len(plan)} операций, оригиналы не изменены."); self.status.setText(f"Предпросмотр готов: {len(plan)} файлов")
        def copy_files(self):
            if not self.records: self.status.setText("Сначала выполните сканирование."); return
            root = Path(self.destination.text().strip() or "Фотоархив")
            if QMessageBox.question(self, "Подтверждение", f"Скопировать {len(self.records)} файлов в {root}? Оригиналы останутся на месте.") != QMessageBox.StandardButton.Yes: return
            plan = self.make_plan(root); self.progress.setRange(0, len(plan)); execute_plan(plan, self.repository, progress=lambda index, item: self.progress.setValue(index)); done = sum(item.status == "done" for item in plan); self.status.setText(f"Завершено: {done}, ошибок: {len(plan) - done}"); self.log.append(f"Копирование завершено: {done} успешно, {len(plan) - done} ошибок.")
        def reset_cache(self):
            if QMessageBox.question(self, "Сброс кэша", "Это удалит историю анализа. Уже скопированные файлы останутся на месте. Продолжить?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes: return
            try:
                self.repository.clear_all(); self.records.clear(); self.table.setRowCount(0); self.status.setText("Кэш очищен")
            except (OSError, sqlite3.Error) as exc: QMessageBox.warning(self, "Сброс кэша", str(exc))
        def stop(self):
            if self.worker and self.worker.isRunning(): self.worker.requestInterruption()
            self.status.setText("Остановка запрошена…")
        def closeEvent(self, event): self.repository.close(); event.accept()

def run_app() -> int:
    if QApplication is None: print("PySide6 не установлен. Установите зависимости из requirements.txt и запустите main.py снова."); return 1
    application = QApplication(sys.argv); window = MainWindow(); window.show(); return application.exec()
