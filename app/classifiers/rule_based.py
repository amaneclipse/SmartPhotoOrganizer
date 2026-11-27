"""Transparent baseline classifier used when optional ML models are absent."""
from app.config.categories import SOURCES
from app.metadata.extractor import detect_screenshot
from app.models import ClassificationResult, ImageRecord

def classify(record: ImageRecord) -> ClassificationResult:
    screenshot, screenshot_kind, shot_score = detect_screenshot(record.path, record.metadata); name = f"{record.path} {record.metadata}".lower(); orientation = "Портретная" if record.height > record.width else "Альбомная" if record.width > record.height else "Квадратная" if record.width else "Неизвестная"
    if screenshot:
        subcategory, tags = "Разное", []
        if any(x in name for x in ("car", "bmw", "toyota", "auto", "авто", "машин")): subcategory, tags = "Автомобили", ["Скриншот объявления"]
        elif any(x in name for x in ("chat", "telegram", "whatsapp", "переписк")): subcategory, tags = "Переписки", ["Скриншот переписки"]
        return ClassificationResult("Скриншоты", subcategory, "Скриншоты", min(0.99, shot_score), tags, True, screenshot_kind, orientation=orientation, reason="Признаки снимка экрана в метаданных или геометрии")
    rules = [("Документы", "Неопределённые", ("document", "invoice", "receipt", "чек", "договор", "паспорт", "скан"), ["Текстовый документ"]), ("Автомобили", "Другие автомобили", ("car", "auto", "bmw", "toyota", "mercedes", "авто", "машин", "vehicle"), ["Автомобиль"]), ("Люди", "Портреты", ("portrait", "selfie", "family", "people", "человек", "семь", "портрет"), ["Люди"]), ("Природа и путешествия", "Пейзажи", ("travel", "mountain", "sea", "lake", "nature", "горы", "море", "путешеств"), ["Пейзаж"]), ("Товары и вещи", "Товары для продажи", ("product", "shop", "товар", "продаж", "каталог"), ["Товар"])]
    for category, subcategory, keywords, tags in rules:
        if any(keyword in name for keyword in keywords): return ClassificationResult(category, subcategory, _source(record), 0.62, tags, orientation=orientation, reason="Совпадение локальных признаков")
    return ClassificationResult("Разное", "Неопределённая категория", _source(record), 0.25, orientation=orientation, reason="Недостаточно достоверных признаков")

def _source(record: ImageRecord) -> str:
    metadata, name = record.metadata, record.path.name.lower(); make = str(metadata.get("Make", "")).lower()
    if make or metadata.get("DateTimeOriginal"): return "С телефона" if any(token in f"{make} {metadata.get('Model', '')}" for token in ("apple", "samsung", "xiaomi", "huawei", "pixel", "iphone")) else "С камеры"
    if any(token in name for token in ("telegram", "whatsapp", "viber", "messenger")): return "Из мессенджеров"
    if "instagram" in name or "facebook" in name: return "Из социальных сетей"
    if metadata.get("Software"): return "Из интернета"
    return SOURCES[-1]
