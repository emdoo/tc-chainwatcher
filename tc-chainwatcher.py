#!/usr/bin/env python3

import tcpython
import os

from datetime import datetime
from discord.ext import commands,tasks
from discord import Interaction, Intents, Embed, Colour, app_commands

intents = Intents.default()
intents.message_content = True

class TCChainWatcher(commands.Bot):
    def __init__(self, *args, **kwargs):
        kwargs["intents"] = intents
        kwargs["command_prefix"] = "/"
        super().__init__(*args, **kwargs)

        self.discord_channel_id = int(kwargs["discord_channel_id"])
        self.torn_token = str(kwargs["torn_token"])
        self.chain_time_threshold = int(kwargs["chain_time_threshold"])
        self.alert_time_threshold = int(kwargs["alert_time_threshold"])
        
        
        self.channel = None
        self.faction = tcpython.faction(key=self.torn_token)
        self.chain = None
        self.chain_end = datetime.now().timestamp()
        self.last_alert = datetime.now().timestamp()
        self.delay = datetime.now().timestamp()
        self.watching = False

    async def setup_hook(self) -> None:
        self.update_chain.start()

    @tasks.loop(seconds=10)
    async def update_chain(self):
        if not self.watching:
            return

        now_time = datetime.now().timestamp()

        if now_time < self.delay-5:
            return

        if self.channel is None:
            self.channel = self.get_channel(self.discord_channel_id)
            return

        if self.chain is None or now_time >= (self.chain_end-self.chain_time_threshold):
            print("Updating chain details...")
            self.chain = self.faction.chain()

        if self.chain == False:
            print("Failed to retrieve chain details: unknown reason")
            return

        if "error" in self.chain.keys():
            print("Failed to retrieve chain details: ", self.chain["error"]["error"])
            return

        if self.chain["start"] == 0 or self.chain["cooldown"] > 0 or self.chain["max"] == 10:
            ## No chain running.. or just ended.. or in warm-up
            print("No chain running, delaying next check %s seconds" % (120, ))
            self.delay = now_time + 120
            return

        self.chain_end = self.chain["end"]

        remaining = int(self.chain_end - now_time)
        print("Remaining time: ", remaining)
        if remaining >= self.chain_time_threshold:
            ## SHOULD be an active chain, with timout >= threshold
            return

        if now_time <= self.last_alert+self.alert_time_threshold:
            ## Last notification was too recent
            return

        self.last_alert = now_time
        print("Alerting")
        embed = Embed(
            title=":bell: Chain Alert :bell:",
            description="The chain is nearing end, only `%d` seconds left!" % (remaining, ),
            colour=Colour.red(),
        )
        embed.add_field(name="Hits", value=self.chain["current"])
        embed.add_field(name="Goal", value=self.chain["max"])
        embed.add_field(name="Modifier", value="%sx" % (self.chain["modifier"], ))
        await self.channel.send(content="@here", embed=embed)

if __name__ == "__main__":
    cw = TCChainWatcher(
        torn_token=os.environ.get("TORN_TOKEN"),
        discord_channel_id=os.environ.get("DISCORD_CHANNEL_ID"),
        chain_time_threshold=os.environ.get("CHAIN_TIME_THRESHOLD"),
        alert_time_threshold=os.environ.get("ALERT_TIME_THRESHOLD"),
    )

    cw_group = app_commands.Group(name="chainwatch", description="Torn Chain Watch commands")

    @cw_group.command(name="enable", description="Enable the chain watcher")
    async def cw_enable(interaction:Interaction):
        cw.watching = True
        return await interaction.response.send_message("says:\n:green_square: Enabled!")

    @cw_group.command(name="disable", description="Disable the chain watcher")
    async def cw_disable(interaction:Interaction):
        cw.watching = False
        return await interaction.response.send_message("says:\n:red_square: Disabled!")

    @cw_group.command(name="threshold", description="Get or set time threshold in seconds, preferably divisible by 10")
    async def cw_threshold(interaction:Interaction, chain:int|None, alert:int|None):
        response = "says:\n"
        if chain is None and alert is None:
            response += ":book: Current threshold values are: Chain `%d` | Alert `%d`" % (cw.chain_time_threshold, cw.alert_time_threshold, )

        if chain is not None:
            if chain >= 30 and chain <= 300:
                cw.chain_time_threshold = chain
                response += ":white_check_mark: Chain threshold set to `%d` second(s)!\n" % (chain, )
            else:
                response += ":no_entry_sign: Chain threshold value must be between 30 and 300 seconds"

        if alert is not None:
            if alert >= 10 and alert <= 300:
                cw.alert_time_threshold = alert
                response += ":white_check_mark: Alert threshold set to `%d` second(s)!\n" % (alert, )
            else:
                response += ":no_entry_sign: Alert threshold value must be between 10 and 300 seconds"

        return await interaction.response.send_message(response.rstrip("\n"))

    @cw.event
    async def on_ready():
        cw.tree.add_command(cw_group)
        await cw.tree.sync()

    cw.run(token=str(os.environ.get("DISCORD_TOKEN")))
