from aiohttp import web

# локальный мок-сервер NTFY API
# имитирует работу приватного инстанса ntfy с поддержкой авторизации

EXPECTED_AUTH_TOKEN = "tk_abcdef123456789"


async def handle_ntfy_post(request):
    topic_name = request.match_info.get('topic')

    auth_header = request.headers.get("Authorization", "")
    print(f"===== auth_header: {auth_header}")
    is_authorized = False

    if auth_header:
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[-1]
            if token == EXPECTED_AUTH_TOKEN:
                is_authorized = True
    else:
        pass

    title = request.headers.get("Title", "[Без заголовка]")
    click_url = request.headers.get("X-Click", "")
    tags = request.headers.get("X-Tags", "")
    priority = request.headers.get("X-Priority", "3")
    markdown_enabled = request.headers.get("X-Markdown", "no")

    body_bytes = await request.read()
    body_text = body_bytes.decode('utf-8')

    # информация о перехваченном пуше на экран
    print("\n" + "=" * 60)
    print(f"[ntfy Server] ПЕРЕХВАЧЕН ИСХОДЯЩИЙ ПУШ!")
    print(f"Целевой топик: {topic_name}")
    print(
        f"Статус авторизации: {'Успешно (Bearer)' if is_authorized else 'Анонимный/Неавторизованный (Заголовок отсутствует)'}")
    print("-" * 40)
    print(f"Заголовок (Title): {title}")
    print(f"Теги (X-Tags): {tags} | Приоритет: {priority}")
    print(f"Поддержка Markdown: {markdown_enabled}")
    print(f"Ссылка для клика (X-Click): {click_url}")
    print("-" * 40)
    print(f"Тело сообщения:\n{body_text}")
    print("=" * 60 + "\n")

    # успешный JSON ответ ntfy сервера
    response_data = {
        "id": "m_test12345abcde",
        "time": 1700000000,
        "expires": 1700043200,
        "event": "message",
        "topic": topic_name,
        "title": title,
        "message": body_text
    }
    return web.json_response(response_data, status=200)


app = web.Application()

# ntfy принимает POST-запросы прямо на корень эндпоинта топика (например, /zulip_goz_13)
app.router.add_post('/{topic}', handle_ntfy_post)

if __name__ == '__main__':
    print("Локальный Mock-сервер ntfy запущен на http://127.0.0.1:8081")
    web.run_app(app, port=8081)
