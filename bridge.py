import asyncio
import logging
import os
import zulip
from pathlib import Path
import urllib.parse

from concurrent.futures import ThreadPoolExecutor


class ZulipNtfyBridge:
    def __init__(
            self,
            zulip_site: str,
            ntfy_host: str,
            ntfy_prefix: str,
            ntfy_token: str,
            loop: asyncio.AbstractEventLoop,
            zuliprc_path: Path
    ):
        self.zulip_site = zulip_site
        self.ntfy_host = ntfy_host.rstrip('/')
        self.ntfy_token = ntfy_token
        self.ntfy_topic = ntfy_prefix
        self.loop = loop
        self.zuliprc_path = zuliprc_path
        self.bot_email = None
        self.zulip_client = None
        self.session = None
        self.semaphore = asyncio.Semaphore(30)

        self.target_channel = os.getenv("TARGET_ZULIP_CHANNEL", "").strip().lower()
        if not self.target_channel:
            logging.warning("[Bridge] Переменная TARGET_ZULIP_CHANNEL не задана в .env!")


    async def send_ntfy_push(
            self,
            stream_name: str,
            topic: str,
            sender_name: str,
            message_content: str,
            msg_url: str
    ) -> None:
        url = f"{self.ntfy_host}/{self.ntfy_topic}"

        logging.info(f"[Bridge API] Отправка одного общего пуша в топик ntfy: {self.ntfy_topic}")

        headers = {
            "Title": f"Zulip [{stream_name}] -> {topic}",
            "X-Click": msg_url,
            "X-Tags": "speech_balloon,bell",
            "X-Priority": "4",
            "X-Markdown": "yes"
        }
        if self.ntfy_token:
            headers["Authorization"] = f"Bearer {self.ntfy_token}"

        body = f"**От:** {sender_name}\n\n{message_content}"

        async with self.semaphore:
            try:
                # один асинхронный POST-запрос с флагом ssl=False
                async with self.session.post(url, data=body.encode('utf-8'), headers=headers, timeout=3,
                                             ssl=False) as response:
                    if response.status == 200:
                        logging.info(f"[Bridge API] Общий пуш успешно доставлен в топик {self.ntfy_topic}")
                    else:
                        res_text = await response.text()
                        logging.error(f"[Bridge API] Ошибка ntfy API (Статус {response.status}): {res_text}")
            except Exception as e:
                logging.error(f"[Bridge API] Исключение сети при отправке общего пуша в ntfy: {e}")


    def process_event(self, event: dict) -> None:
        if event.get('type') != 'message':
            return

        msg = event['message']
        if msg['sender_email'] == self.bot_email:
            return

        if msg['type'] == 'private':
            return

        stream_name = msg.get('display_recipient', 'Неизвестный стрим')
        stream_id = msg.get('stream_id')

        if not isinstance(stream_name, str):
            return

        if stream_name.strip().lower() != self.target_channel:
            return

        sender_id = msg['sender_id']
        sender_name = msg['sender_full_name']
        topic = msg.get('subject', 'Без темы')
        content = msg.get('content_raw', msg.get('content', ''))
        message_id = msg.get('id')

        logging.info(f"[Bridge] Перехвачено сообщение из ЦЕЛЕВОГО канала [{stream_name}]. Автор Zulip ID: {sender_id}")

        # диплинк для Zulip 2026
        channel_slug = f"{stream_id}-{stream_name.lower().replace(' ', '-')}"
        encoded_topic = urllib.parse.quote(topic)
        msg_url = f"{self.zulip_site}/#narrow/channel/{channel_slug}/topic/{encoded_topic}/with/{message_id}"

        self.loop.call_soon_threadsafe(
            lambda sn=stream_name: asyncio.create_task(
                self.send_ntfy_push(sn, topic, sender_name, content, msg_url)
            )
        )


    def start_zulip_listener(self):
        logging.info(
            f"[Bridge] Установка соединения и запуск слушателя для целевого канала: [{os.getenv('TARGET_ZULIP_CHANNEL')}]...")
        try:
            self.zulip_client.call_on_each_event(
                callback=self.process_event,
                event_types=['message'],
                all_public_streams=True
            )
        except Exception as e:
            logging.critical(f"[Bridge] Критическая ошибка потока прослушивания событий Zulip: {e}")

    async def start(self, session):
        self.session = session

        while True:
            try:
                self.zulip_client = await asyncio.wait_for(
                    self.loop.run_in_executor(None, lambda: zulip.Client(config_file=str(self.zuliprc_path))),
                    timeout=10.0
                )
                self.bot_email = self.zulip_client.email
                logging.info(f"[Bridge] Успешная авторизация в Zulip: {self.bot_email}")
                break
            except (asyncio.TimeoutError, Exception) as e:
                logging.error(f"[Bridge] Ошибка авторизации в Zulip: {e}. Повтор через 15 секунд...")
                await asyncio.sleep(15)

        async def safe_listener_loop():
            while True:
                executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ZulipListener")

                for thread in executor._threads:
                    thread.daemon = True

                try:
                    logging.info("[Bridge] Запуск слушателя событий Zulip в выделенном системном потоке...")
                    await self.loop.run_in_executor(executor, self.start_zulip_listener)
                except Exception as e:
                    logging.error(f"[Bridge] Поток слушателя Zulip аварийно завершился: {e}")
                finally:
                    executor.shutdown(wait=False)

                logging.info("[Bridge] Соединение с Zulip потеряно. Перезапуск слушателя через 15 секунд...")
                await asyncio.sleep(15)

        asyncio.create_task(safe_listener_loop())
