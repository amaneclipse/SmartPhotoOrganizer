# Windows Release

Для разработчика:

```bat
build_windows.bat
```

Готовая папка появится в `dist/SmartPhotoOrganizer/`. Модели не включаются в EXE: пользователь устанавливает их отдельно, чтобы не раздувать размер дистрибутива.

GitHub Actions запускает ту же сборку при создании tag `v*` и прикладывает ZIP к GitHub Release.
