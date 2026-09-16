# zulip_ntfy

---

## Компиляция в исполняемый файл (PyInstaller)

Чтобы запустить приложение на сервере без необходимости устанавливать Python и зависимости, его можно скомпилировать в один независимый исполняемый файл (бинарник).

1. Установите `PyInstaller` в вашем виртуальном окружении:
   ```bash
   pip install pyinstaller
   ```

2. Выполните сборку проекта одной командой:
   ```bash
   pyinstaller --onefile --name zulip-ntfy-service run.py
   ```

3. После успешного завершения процесса готовый файл появится в директории `dist/zulip-ntfy-service`.
4. Перенесите скомпилированный файл на целевой сервер (например, в папку `/usr/local/bin/`).

> **⚠️ Важно:** Файл конфигурации `zuliprc` должен лежать в той же папке, где находится скомпилированный исполняемый файл (благодаря встроенной в `run.py` проверке путей `sys.frozen`).

---

## ⚙️ Запуск как системная служба (Systemd в Linux)

Для того чтобы сервис работал непрерывно в фоновом режиме, автоматически запускался при старте сервера и корректно перезагружался при сбоях, настройте его как службу `systemd`.

### Шаг 1. Подготовка папки
Рекомендуется разместить исполняемый файл и конфигурацию в отдельной директории, например `/opt/zulip-ntfy/`:
```bash
sudo mkdir -p /opt/zulip-ntfy
sudo cp dist/zulip-ntfy-service /opt/zulip-ntfy/
sudo cp zuliprc /opt/zulip-ntfy/
```

### Шаг 2. Создание файла службы
Создайте конфигурационный файл службы:
```bash
sudo nano /etc/systemd/system/zulip-ntfy.service
```

Вставьте в него следующее содержимое:

```ini
[Unit]
Description=Zulip to ntfy Push Notification Bridge
After=network.target

[Service]
Type=simple
# Путь к рабочей директории, где лежит файл zuliprc
WorkingDirectory=/opt/zulip-ntfy
# Путь к исполняемому файлу
ExecStart=/opt/zulip-ntfy/zulip-ntfy-service
# Автоматический перезапуск службы при сбоях через 10 секунд
Restart=always
RestartSec=10
# Логирование вывода в системный журнал
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=zulip-ntfy

[Install]
WantedBy=multi-user.target
```

### Шаг 3. Активация и запуск службы
Выполните команды в терминале сервера для обновления конфигурации системных служб и запуска:

```bash
# Перезагрузить конфигурацию systemd, чтобы применить изменения
sudo systemctl daemon-reload

# Включить автоматический запуск службы при загрузке системы
sudo systemctl enable zulip-ntfy.service

# Запустить службу прямо сейчас
sudo systemctl start zulip-ntfy.service
```

### Шаг 4. Управление и просмотр логов
* Проверить **текущий статус** работы службы:
  ```bash
  sudo systemctl status zulip-ntfy.service
  ```
* Просмотр **логов приложения** в реальном времени:
  ```bash
  sudo journalctl -u zulip-ntfy.service -f
  ```
* **Перезапустить** службу после изменения файла `zuliprc`:
  ```bash
  sudo systemctl restart zulip-ntfy.service
  ```
