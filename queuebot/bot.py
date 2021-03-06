# -*- coding: utf-8 -*-
import datetime
import importlib
import inspect
import logging
import typing
from pathlib import Path

import aiohttp
import discord
from asyncpg.pool import Pool
from discord.ext import commands

from queuebot.cog import Cog
from queuebot.context import Context

logger = logging.getLogger(__name__)


class Queuebot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Remove default help command.
        self.remove_command('help')

        #: OAuth2 application owner.
        self.owner: discord.User = None

        #: List of extension names to load. We store this because `self.extensions` is volatile during reload.
        self.to_load: typing.List[str] = None

        self.config = kwargs.pop('config')

        # Database connection to PostgreSQL
        self.db: Pool = kwargs.pop('db')

        self.session = aiohttp.ClientSession(loop=self.loop)

    @property
    def council_roles(self):
        return set(self.config.get('council_roles', []))

    @property
    def blob_emoji(self) -> discord.Guild:
        suggestions_channel = self.get_channel(self.config.suggestions_channel)
        if suggestions_channel is None:
            return None
        return suggestions_channel.guild

    async def close(self):
        logger.info('Closing.')
        await super().close()
        await self.db.close()
        await self.session.close()

    async def on_ready(self):
        # Grab owner from application info.
        self.owner = (await self.application_info()).owner

        logger.info('Ready! Logged in as %s (%d)', self.user, self.user.id)

    async def log(self, content, **kwargs) -> typing.Union[discord.Message, None]:
        timestamp = f'`[{datetime.datetime.utcnow().strftime("%H:%M")}]`'
        channel = self.get_channel(self.config.bot_log)
        if not channel:
            return None
        return await channel.send(f'{timestamp} {content}', **kwargs)

    async def is_owner(self, user):
        if user.id in self.config.get('admins', []):
            return True
        return await super().is_owner(user)

    async def on_message(self, msg: discord.Message):
        # Ignore messages from bots.
        if msg.author.bot:
            return

        # Do not process commands until we are ready.
        await self.wait_until_ready()

        context = await self.get_context(msg, cls=Context)
        await self.invoke(context)

    def load_extension(self, name: str):
        extension_module = importlib.import_module(name)

        # Find Cog subclasses in the module.
        cogs = inspect.getmembers(
            extension_module, predicate=lambda obj: inspect.isclass(obj) and issubclass(obj, Cog) and obj is not Cog
        )

        # Add all Cog subclasses.
        for _, cog in cogs:
            logger.info('Automatically adding cog: %s', cog.__name__)
            self.add_cog(cog(self))

        # Call setup(), if there is one.
        if hasattr(extension_module, 'setup'):
            extension_module.setup(self)

        self.extensions[name] = extension_module

    def discover_exts(self, directory: str):
        """Loads all extensions from a directory."""
        ignore = {'__pycache__', '__init__'}

        exts = [
            p.stem for p in Path(directory).resolve().iterdir()
            if p.stem not in ignore
        ]

        logger.info('Loading extensions: %s', exts)

        for ext in exts:
            self.load_extension('queuebot.cogs.' + ext)

        self.to_load = list(self.extensions.keys()).copy()
        logger.info('To load: %s', self.to_load)
