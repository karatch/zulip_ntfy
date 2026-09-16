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