"""Shared structured-output contract for image classification."""
CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {"category": {"type": "string"}, "subcategory": {"type": "string"}, "source": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}, "confidence": {"type": "number"}, "vehicle_make": {"type": ["string", "null"]}, "vehicle_model": {"type": ["string", "null"]}, "is_screenshot": {"type": "boolean"}, "screenshot_kind": {"type": "string"}, "text": {"type": "string"}},
    "required": ["category", "subcategory", "source", "tags", "confidence", "vehicle_make", "vehicle_model", "is_screenshot", "screenshot_kind", "text"],
    "additionalProperties": False,
}
CLASSIFICATION_PROMPT = """Классифицируй изображение для локального фотоархива. Не угадывай личность людей и не выдумывай марку/модель автомобиля. Если уверенность низкая, укажи confidence ниже 0.60. Верни только JSON по заданной схеме. Категории: Автомобили, Люди, Дом и интерьер, Товары и вещи, Природа и путешествия, Работа и бизнес, Документы, Разное, Скриншоты. Источники: С телефона, Из интернета, Скриншоты, С камеры, Из мессенджеров, Из социальных сетей, Неизвестный источник."""
