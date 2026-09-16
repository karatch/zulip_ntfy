#!/usr/bin/env python3
import asyncio
import os
import configparser
import logging
import sys
import aiohttp
import urllib3
from pathlib import Path

from bridge import ZulipNtfyBridge

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

ZULIPRC_PATH = BASE_DIR / "zuliprc"

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
        return {"zulip_site": zulip_site}
    except Exception as e:
        raise KeyError(f"Ошибка чтения секций в zuliprc: {e}")


async def main():
    loop = asyncio.get_running_loop()

    try:
        config = load_config()
    except Exception as e:
        logging.critical(f"[Main] Не удалось запустить приложение: {e}")
        return

    logging.info("[Main] Инициализация объекта ZulipNtfyBridge...")
    bridge = ZulipNtfyBridge(zulip_site=config["zulip_site"], loop=loop, zuliprc_path=ZULIPRC_PATH)

    try:
        async with aiohttp.ClientSession() as session:
            logging.info("[Main] Запуск фонового моста Zulip -> ntfy...")
            await bridge.start(session)

            # бесконечный цикл, удерживающий работу асинхронного приложения
            while True:
                await asyncio.sleep(3600)
    except Exception as e:
        logging.exception(f"[Main] Критическая ошибка в основном цикле: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("[Main] Сервис остановлен пользователем через Ctrl+C.")
