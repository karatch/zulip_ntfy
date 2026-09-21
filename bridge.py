import asyncio
import logging
import zulip
from pathlib import Path
import urllib.parse

from concurrent.futures import ThreadPoolExecutor


class ZulipNtfyBridge:
    def __init__(self, zulip_site: str, loop: asyncio.AbstractEventLoop, zuliprc_path: Path):
        self.zulip_site = zulip_site
        self.loop = loop
        self.zuliprc_path = zuliprc_path
        self.bot_email = None
        self.zulip_client = None
        self.session = None
        self.semaphore = asyncio.Semaphore(30)


    async def send_ntfy_push(
            self,
            stream_name: str,
            topic: str,
            sender_name: str,
            message_content: str,
            msg_url: str,
            zulip_id: str = "common"
    ) -> None:
        logging.info(f"[Bridge API] Попытка отправки пуша в ntfy для Zulip ID: {zulip_id}")

        if zulip_id == "common":
            url = f"https://ntfy.sh/zulip_goz"
        else:
            url = f"https://ntfy.sh/zulip_goz_{zulip_id}"

        headers = {
            "Title": f"Zulip [{stream_name}] -> {topic}",
            "X-Click": msg_url,
            "X-Tags": "speech_balloon,bell",
            "X-Priority": "4",
            "X-Markdown": "yes"  # поддержка Markdown-разметки
        }

        body = f"**От:** {sender_name}\n\n{message_content}"

        async with self.semaphore:
            try:
                async with self.session.post(url, data=body, headers=headers, timeout=3) as response:
                    if response.status == 200:
                        logging.info(f"[Bridge API] Пуш успешно доставлен в ntfy для ID {zulip_id}")
                    else:
                        res_text = await response.text()
                        logging.error(
                            f"[Bridge API] Ошибка ntfy API (Статус {response.status}) для ID {zulip_id}: {res_text}")
            except Exception as e:
                logging.error(f"[Bridge API] Исключение сети при отправке в ntfy для ID {zulip_id}: {e}")


    def get_stream_subscribers(self, stream_name: str, stream_id: int = None) -> list:
        try:
            result = self.zulip_client.get_subscribers(stream=stream_name)
            if result.get('result') != 'success' and stream_id is not None:
                result = self.zulip_client.get_subscribers(stream_id=stream_id)

            if result.get('result') == 'success':
                return result.get('subscribers', [])
            return []
        except Exception as e:
            logging.error(f"[Bridge] Исключение при получении подписчиков Zulip: {e}")
            return []

    def process_event(self, event: dict) -> None:
        if event.get('type') != 'message':
            return

        msg = event['message']
        if msg['sender_email'] == self.bot_email:
            return

        if msg['type'] == 'private':
            return

        sender_id = msg['sender_id']
        sender_name = msg['sender_full_name']
        topic = msg.get('subject', 'Без темы')

        # 'content_raw' для Markdown
        content = msg.get('content_raw', msg.get('content', ''))

        stream_name = msg.get('display_recipient', 'Неизвестный стрим')
        stream_id = msg.get('stream_id')
        message_id = msg.get('id')

        if not isinstance(stream_name, str):
            return

        logging.info(f"[Bridge] Перехвачено сообщение из [{stream_name}]")

        encoded_stream = f"{stream_id}-{stream_name.replace(' ', '.')}"
        encoded_topic = urllib.parse.quote(topic.replace(' ', '.'))
        msg_url = f"{self.zulip_site}/#narrow/stream/{encoded_stream}/topic/{encoded_topic}/near/{message_id}"

        subscribers = self.get_stream_subscribers(stream_name, stream_id)
        sent_counter = 0

        self.loop.call_soon_threadsafe(
            lambda sn=stream_name: asyncio.create_task(
                self.send_ntfy_push(sn, topic, sender_name, content, msg_url)
            )
        )

        for user_id in subscribers:
            if user_id == sender_id:
                continue

            sent_counter += 1
            self.loop.call_soon_threadsafe(
                lambda sn=stream_name, u_id=user_id: asyncio.create_task(
                    self.send_ntfy_push(sn, topic, sender_name, content, msg_url, str(u_id))
                )
            )

        logging.info(f"[Bridge] Всего отправлено уведомлений в ntfy: {sent_counter}")


    def start_zulip_listener(self):
        logging.info("[Bridge] Установка соединения и регистрация очереди событий Zulip для ВСЕХ стримов...")
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
                # изолированный пул потоков для блокирующего call_on_each_event
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