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