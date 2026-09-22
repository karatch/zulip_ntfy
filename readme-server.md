## Развертывание приватного сервера ntfy (Self-Hosted)

Для обеспечения максимальной конфиденциальности и защиты корпоративных данных рекомендуется развернуть собственный изолированный сервер **ntfy** в Docker. В этом режиме анонимный доступ из интернета полностью блокируется, а шлюз и пользователи авторизуются по токенам и паролям.

### 1. Подготовка инфраструктуры
```bash
mkdir -p /opt/ntfy-server && cd /opt/ntfy-server
```

### 2. Создание конфигурации сервера `server.yml`
```bash
nano server.yml
```
Вставьте следующее содержимое (замените `://company.com` на ваш домен или IP-адрес):
```yaml
base-url: "https://company.com"
auth-file: "/var/lib/ntfy/user.db"
auth-default-access: "deny-all"
behind-proxy: true
cache-file: "/var/lib/ntfy/cache.db"
cache-duration: "12h"
```

### 3. Создание манифеста `docker-compose.yml`
Создайте файл для запуска контейнера:
```bash
nano docker-compose.yml
```
Вставьте конфигурацию:
```yaml
version: '3.8'

services:
  ntfy:
    image: binwiederhier/ntfy:latest
    container_name: ntfy-server
    command: serve
    volumes:
      - ./data:/var/lib/ntfy
      - ./server.yml:/etc/ntfy/server.yml:ro
    ports:
      - "8080:80"
    environment:
      - TZ=Europe/Moscow
    restart: always
```

### 4. Запуск сервера
Запустите контейнер в фоновом режиме:
```bash
docker compose up -d
```

### 5. Настройка прав доступа и генерация токенов
После запуска сервера необходимо через встроенную утилиту внутри контейнера создать пользователей и выдать права.

**Шаг A. Создание Администратора (для управления сервером):**
```bash
docker exec -it ntfy-server ntfy user add --role=admin admin_user
```
*(Введите и подтвердите надежный пароль).*

**Шаг Б. Создание пользователя для Python-шлюза и генерация токена:**
Нашему шлюзу нужно право **писать** (`write`) во все топики. Создаем пользователя, даем права и выпускаем токен:
```bash
# Добавление пользователя шлюза
docker exec -it ntfy-server ntfy user add push_bridge_user

# Предоставление прав на запись (write) во все топики (*)
docker exec -it ntfy-server ntfy access push_bridge_user "*" write

# Генерация бессрочного токена доступа
docker exec -it ntfy-server ntfy token add push_bridge_user
```
*Скопируйте сгенерированный токен (начинается на `tk_...`) и вставьте его в файл `.env` вашего приложения в переменную `NTFY_AUTH_TOKEN`.*

**Шаг В. Создание пользователя для сотрудников (Чтение пушей):**
Сотрудникам нужно право только на **чтение** (`read`) уведомлений:
```bash
# Добавление пользователя для команды
docker exec -it ntfy-server ntfy user add goz_user

# Предоставление прав на чтение (read) всех топиков (*)
docker exec -it ntfy-server ntfy access goz_user "*" read
```
*Пароль от `goz_user` сотрудники будут использовать для входа в мобильное приложение ntfy.*
