import asyncio
import logging
import zulip
from pathlib import Path
import urllib.parse
from concurrent.futures import ThreadPoolExecutor


class ZulipNtfyBridge:
    def __init__(
            self,
            zulip_site: str,
            ntfy_host: str,
            ntfy_topic: str,
            ntfy_token: str,
            target_stream_id: int,
            loop: asyncio.AbstractEventLoop,
            zuliprc_path: Path
    ):
        self.zulip_site = zulip_site
        self.ntfy_host = ntfy_host.rstrip('/')
        self.ntfy_token = ntfy_token
        self.ntfy_topic = ntfy_topic
        self.target_stream_id = target_stream_id
        self.loop = loop
        self.zuliprc_path = zuliprc_path
        self.bot_email = None
        self.zulip_client = None
        self.session = None
        self.semaphore = asyncio.Semaphore(30)
        self.active_push_tasks = set()
        self._listener_task = None
        self._stop_listener_event = asyncio.Event()

    async def send_ntfy_push(
            self,
            stream_name: str,
            topic: str,
            sender_name: str,
            message_content: str,
            msg_url: str
    ) -> None:
        url = f"{self.ntfy_host}/{self.ntfy_topic}"

        logging.info(f"[Bridge API] Отправка пуша в топик ntfy: {self.ntfy_topic}")

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
                task = asyncio.current_task()
                self.active_push_tasks.add(task)
                # TODO (SECURITY): ssl=False отключает проверку сертификатов.
                # используется только для отладки с самоподписанными сертификатами.
                # в продакшене удалить и настроить ssl=SSLContext с корпоративным CA.
                async with self.session.post(url, data=body.encode('utf-8'), headers=headers, timeout=3,
                                             ssl=False) as response:
                    if response.status == 200:
                        logging.info(f"[Bridge API] Пуш успешно доставлен в топик {self.ntfy_topic}")
                    else:
                        res_text = await response.text()
                        logging.error(f"[Bridge API] Ошибка ntfy API (Статус {response.status}): {res_text}")
            except Exception as e:
                logging.error(f"[Bridge API] Исключение сети при отправке пуша в ntfy: {e}")
            finally:
                self.active_push_tasks.discard(task)

    def process_event(self, event: dict) -> None:
        if event.get('type') != 'message':
            return None

        msg = event['message']
        if msg['sender_email'] == self.bot_email or msg['type'] != 'stream':
            return None

        stream_name = msg.get('display_recipient')
        if not isinstance(stream_name, str):
            return None

        # выходим, если у сообщения нет stream_id (ошибка API) или ID не совпадает с целевым
        event_stream_id = msg.get('stream_id')
        if event_stream_id is None or event_stream_id != self.target_stream_id:
            return None

        sender_name = msg['sender_full_name']
        topic = msg.get('subject', 'Без темы')
        content = msg.get('content_raw', msg.get('content', ''))
        message_id = msg.get('id')
        # stream_id = msg.get('stream_id')

        logging.info(f"[Bridge] Перехвачено сообщение из [{stream_name}]. Автор Zulip ID: {msg['sender_id']}")

        channel_slug = f"{event_stream_id}-{stream_name.lower().replace(' ', '-')}"
        encoded_topic = urllib.parse.quote(topic)
        msg_url = f"{self.zulip_site}/#narrow/channel/{channel_slug}/topic/{encoded_topic}/with/{message_id}"

        self.loop.call_soon_threadsafe(
            lambda: asyncio.create_task(
                self.send_ntfy_push(stream_name, topic, sender_name, content, msg_url),
                name="ntfy-push-sender"
            )
        )
        return None

    def start_zulip_listener(self):
        logging.info(f"[Bridge] Запуск слушателя Zulip для канала: [{self.target_stream_id}]...")
        try:
            self.zulip_client.call_on_each_event(
                callback=self.process_event,
                event_types=['message'],
                all_public_streams=True
            )
        except Exception as e:
            if not self._stop_listener_event.is_set():
                logging.error(f"[Bridge] Слушатель Zulip прерван ошибкой: {e}")
            else:
                logging.info("[Bridge] Слушатель Zulip остановлен по флагу.")

    async def start(self, session, stop_event: asyncio.Event):
        self.session = session

        # авторизация в Zulip
        while not stop_event.is_set():
            try:
                self.zulip_client = await asyncio.wait_for(
                    self.loop.run_in_executor(None, lambda: zulip.Client(config_file=str(self.zuliprc_path))),
                    timeout=10.0
                )
                self.bot_email = self.zulip_client.email
                logging.info(f"[Bridge] Успешная авторизация в Zulip: {self.bot_email}")
                break
            except Exception as e:
                logging.error(f"[Bridge] Ошибка авторизации в Zulip: {e}. Повтор через 15 секунд...")
                # await asyncio.sleep(15)
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=15.0)
                except asyncio.TimeoutError:
                    pass

        # запуск цикла жизни слушателя
        async def listener_wrapper():
            while not stop_event.is_set():
                executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ZulipListener")
                for thread in executor._threads:
                    thread.daemon = True

                try:
                    await self.loop.run_in_executor(executor, self.start_zulip_listener)
                except Exception as e:
                    logging.error(f"[Bridge] Поток слушателя Zulip аварийно завершился: {e}")
                finally:
                    executor.shutdown(wait=False)

                if not stop_event.is_set():
                    logging.info("[Bridge] Соединение с Zulip потеряно. Перезапуск через 15 секунд...")
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=15.0)
                    except asyncio.TimeoutError:
                        pass

        # сохраняю задачу для корректной отмены в shutdown
        self._listener_task = asyncio.create_task(listener_wrapper())

    async def shutdown(self):
        logging.info("[Bridge] Инициализация завершения работы...")

        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                logging.info("[Bridge] Задача слушателя Zulip отменена.")

        if self.active_push_tasks:
            logging.info(f"[Bridge] Ожидаем завершения {len(self.active_push_tasks)} активных отправок...")
            await asyncio.wait(self.active_push_tasks)

        if self.session:
            await self.session.close()

        logging.info("[Bridge] Завершение работы моста завершено.")