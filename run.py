#!/usr/bin/env python3
import asyncio
import os
import configparser
import logging
import signal
import sys
import aiohttp
import urllib3
from pathlib import Path
from dotenv import load_dotenv

from bridge import ZulipNtfyBridge

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

ZULIPRC_PATH = BASE_DIR / "zuliprc"
DOTENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=DOTENV_PATH)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)


def load_config():
    logging.info(f"[Main] Чтение конфигурационного файла: {ZULIPRC_PATH}")
    if not os.path.exists(ZULIPRC_PATH):
        raise FileNotFoundError(f"Критическая ошибка: Файл {ZULIPRC_PATH} не найден!")

    config = configparser.ConfigParser()
    config.read(ZULIPRC_PATH)
    try:
        zulip_site = config.get('api', 'site').rstrip('/')
        ntfy_host = os.getenv("NTFY_HOST", "https://ntfy.sh").rstrip('/')
        ntfy_token = os.getenv("NTFY_AUTH_TOKEN", None)
        ntfy_prefix = os.getenv("NTFY_TOPIC_PREFIX", "zulip_goz")

        logging.info(f"[Main] Конфигурация успешно загружена. Целевой ntfy: {ntfy_host}")
        return {
            "zulip_site": zulip_site,
            "ntfy_host": ntfy_host,
            "ntfy_token": ntfy_token,
            "ntfy_prefix": ntfy_prefix
        }
    except Exception as e:
        raise KeyError(f"Ошибка чтения конфигурации: {e}")


async def main():
    stop_event = asyncio.Event()

    def handle_exit_signal():
        logging.info("[Система] Получен сигнал остановки. Ожидаем завершения фоновых задач...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, handle_exit_signal)
    loop.add_signal_handler(signal.SIGTERM, handle_exit_signal)  # Добавлен SIGTERM для работы в Docker/K8s

    try:
        config = load_config()
    except Exception as e:
        logging.critical(f"[Main] Не удалось запустить приложение: {e}")
        return

    logging.info("[Main] Инициализация объекта ZulipNtfyBridge...")
    bridge = ZulipNtfyBridge(
        zulip_site=config["zulip_site"],
        ntfy_host=config["ntfy_host"],
        ntfy_token=config["ntfy_token"],
        ntfy_prefix=config["ntfy_prefix"],
        loop=loop,
        zuliprc_path=ZULIPRC_PATH
    )

    try:
        async with aiohttp.ClientSession() as session:
            logging.info("[Main] Запуск фонового моста Zulip -> ntfy...")
            await bridge.start(session, stop_event)

            await stop_event.wait()

            # 10 секунд мосту на завершение
            try:
                await asyncio.wait_for(bridge.shutdown(), timeout=10.0)
            except asyncio.TimeoutError:
                logging.warning("[Main] Мост не успел завершить работу за 10 секунд, принудительный выход.")

    except Exception as e:
        logging.exception(f"[Main] Критическая ошибка в основном цикле: {e}")


if __name__ == "__main__":
    asyncio.run(main())

