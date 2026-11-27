# Changelog

## Unreleased

- Добавлен provider-agnostic слой `app/ai` с локальным, OpenAI и OpenAI-compatible режимами.
- Добавлено хранение ключей через `keyring`/Windows Credential Manager без plaintext fallback.
- Добавлены лимиты изображений/запросов, rate limiting и подтверждение облачной отправки.
- Добавлены GitHub-документы, PyInstaller-конфигурация и workflow Windows-сборки.

## 0.1.0

- Первый локальный MVP: сканирование, EXIF, screenshot heuristics, SQLite, preview и безопасное копирование.
