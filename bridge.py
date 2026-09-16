import asyncio
import logging
import zulip
from pathlib import Path

# import database

# Фоновый мост Zulip -> ntfy

class ZulipNtfyBridge:
    def __init__(self, zulip_site: str, loop: asyncio.AbstractEventLoop, zuliprc_path: Path):
        self.zulip_site = zulip_site
        self.loop = loop
        self.zuliprc_path = zuliprc_path
        self.bot_email = None
        self.zulip_client = None
        self.session = None
        self.semaphore = asyncio.Semaphore(10)

    async def send_ntfy_push(self, zulip_id: str, stream_name: str, topic: str, sender_name: str, message_content: str,
                             msg_url: str) -> None:
        logging.info(f"[Bridge API] Попытка отправки пуша в ntfy для Zulip ID: {zulip_id}")

        # персональный URL топика ntfy для конкретного пользователя
        url = f"https://ntfy.sh/zulip_goz_{zulip_id}"

        headers = {
            "Title": f"Zulip [{stream_name}] -> {topic}".encode('utf-8'),  # Заголовок пуша
            "X-Click": msg_url,  # Ссылка при клике на пуш
            "X-Tags": "speech_balloon,bell",  # Иконки уведомления
            "X-Priority": "4"  # Высокий приоритет (важно)
        }

        body = f"От: {sender_name}\n\n{message_content}".encode('utf-8')

        async with self.semaphore:
            try:
                async with self.session.post(url, data=body, headers=headers, timeout=5) as response:
                    if response.status == 200:
                        logging.info(f"[Bridge API] Пуш успешно доставлен в ntfy для ID {zulip_id}")
                    else:
                        res_text = await response.text()
                        logging.error(
                            f"[Bridge API] Ошибка ntfy API (Статус {response.status}) для ID {zulip_id}: {res_text}")
            except Exception as e:
                logging.error(f"[Bridge API] Исключение сети при отправке в ntfy для ID {zulip_id}: {e}")