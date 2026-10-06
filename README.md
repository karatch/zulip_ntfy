# Zulip to ntfy Channel Gateway

Асинхронный интеграционный шлюз (микросервис) на Python для мгновенной пересылки корпоративных push-уведомлений из одного конкретного канала **Zulip** в один общий топик на приватном сервере **ntfy**.


---

## Инструкция для сотрудников: Настройка ntfy на смартфоне

Чтобы начать мгновенно получать уведомления из целевого канала Zulip прямо на экран своего телефона, выполните 3 простых шага:

### Шаг 1. Установите приложение ntfy
1. Скачайте официальное бесплатное приложение **ntfy** из магазина приложений


### Шаг 2. Подключитесь к приватному серверу организации
1. Откройте приложение ntfy на смартфоне и нажмите на кнопку **«+» (Добавить подписку)**.
2. Нажмите на ссылку **«Use another server» (Использовать другой сервер)** или выберите кастомный хост в выпадающем списке.
3. В поле адреса сервера введите внутренний домен или IP-адрес вашей компании (например, `https://ntfy.company.com` или `https://193.10.0.128:8080`).
4. В поле **Topic name (Назвние темы)** введите имя общего корпоративного канала (например, `company_alerts`).
5. Нажмите кнопку **Subscribe (Подписаться)**.


### Шаг 3. Включите авторизацию (Если требуется)
1. Если на вашем корпоративном сервере включена защита, приложение выдаст запрос на ввод учетных данных.
2. Перейдите во вкладку настроек подписки и укажите ваш корпоративный **Логин** и **Пароль**, выданные администратором.

Теперь, когда кто-то опубликует важное сообщение или алерт в целевом канале Zulip, уведомление мгновенно отобразится на экране вашего смартфона с указанием автора, темы и текста сообщения, а также прямой ссылкой на чат.


## Инструкция по развертыванию для Администратора

### 1. Подготовка конфигурационных файлов
В корневой папке приложения должны находиться два файла конфигурации.

Создайте файл окружения **`.env`**:
```env
# Адрес вашего приватного сервера ntfy
NTFY_HOST=http://127.0.0.1:8080

# Токен авторизации на сервере ntfy с правами write (если включена ACL-защита)
NTFY_AUTH_TOKEN=tk_abcdef123456789

# Общий корпоративный топик ntfy, на который подписаны сотрудники
NTFY_TOPIC_PREFIX=secure_company_alerts

# ИМЯ КАНАЛА В ZULIP, КОТОРЫЙ СЛУШАЕТ ШЛЮЗ (Чувствительно к регистру!)
TARGET_ZULIP_CHANNEL=channel testing
```

Положите рядом стандартный файл авторизации **`zuliprc`** вашего Generic-бота с правами Администратора организации Zulip:
```ini
[api]
site = https://company.com
email = push-bot-bot@://company.com
key = abcdefghijklmnopqrstuvwxyz123456
```

### 2. Установка зависимостей и запуск
1. Установите необходимые библиотеки (из списка полностью исключены тяжелые движки СУБД):
   ```bash
   pip install -r requirements.txt
   ```
2. Запустите шлюз:
   ```bash
   python3 run.py
   ```

---

## Настройка фоновой службы Linux (Systemd)

Выполните сборку проекта одной командой:
   ```bash
   pyinstaller --onefile --name zulip-ntfy-service run_all.py
   ```

Для обеспечения непрерывной работы 24/7 настройте шлюз как системную службу от имени безопасного изолированного пользователя. Так как это Stateless-архитектура, процессу не нужны права на запись данных на диск.

1. Создайте системного пользователя и передайте ему права на папку проекта:
   ```bash
   sudo useradd -r -s /bin/false zulip-push
   sudo chown -R zulip-push:zulip-push /opt/zulip-ntfy
   ```

2. Создайте файл службы `/etc/systemd/system/zulip-ntfy-bridge.service`:
   ```ini
   [Unit]
   Description=Zulip to ntfy Ultra-Light Channel Push Gateway
   After=network.target

   [Service]
   Type=simple
   User=zulip-push
   Group=zulip-push
   WorkingDirectory=/opt/zulip-ntfy
   EnvironmentFile=/opt/zulip-ntfy/.env
   ExecStart=/usr/bin/python3 /opt/zulip-ntfy/run.py
   Restart=always
   RestartSec=10
   StandardOutput=syslog
   StandardError=syslog
   SyslogIdentifier=zulip-ntfy-bridge

   [Install]
   WantedBy=multi-user.target
   ```

3. Активируйте и запустите службу:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable zulip-ntfy-bridge.service
   sudo systemctl start zulip-ntfy-bridge.service
   ```

4. Мониторинг логов шлюза в реальном времени:
   ```bash
   sudo journalctl -u zulip-ntfy-bridge -f
   ```
