# -*- coding: utf-8 -*-
class Cog:
    def __init__(self, bot: 'queuebot.bot.Queuebot'):
        self.bot = bot
        self.config = bot.config
        self.db = bot.db
