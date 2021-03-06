import datetime
import discord
from discord.ext import commands
import logging
import re
import sys
import time
import traceback

from resources.utilities.embed import embed as imported_embed
from resources.utilities.list_of_perms import get_list_of_user_permissions

logger = logging.getLogger('wall_e')


class ManageCog(commands.Cog):

    def __init__(self, bot, config):
        logger.info("[ManageCog __init__()] initializing the TestCog")
        bot.add_check(self.check_test_environment)
        bot.add_check(self.check_privilege)
        self.bot = bot
        self.config = config
        self.help_dict = self.config.get_help_json()
        if self.config.enabled("database", option="DB_ENABLED"):
            import psycopg2 # noqa
            self.psycopg2 = psycopg2

    @commands.command(hidden=True)
    async def debuginfo(self, ctx):
        logger.info("[ManageCog debuginfo()] debuginfo command detected from {}".format(ctx.message.author))
        if self.config.get_config_value("basic_config", "ENVIRONMENT") == 'TEST':
            fmt = '```You are testing the latest commit of branch or pull request: {0}```'
            await ctx.send(fmt.format(self.config.get_config_value('basic_config', 'BRANCH_NAME')))
        return

    # this check is used by the TEST guild to ensur that each TEST container will only process incoming commands
    # that originate from channels that match the name of their branch
    def check_test_environment(self, ctx):
        if self.config.get_config_value('basic_config', 'ENVIRONMENT') == 'TEST':
            if ctx.message.guild is not None and \
               ctx.channel.name != self.config.get_config_value('basic_config', 'BRANCH_NAME').lower():
                return False
        return True

    # this check is used to ensure that users can only access commands that they have the rights to
    async def check_privilege(self, ctx):
        command_used = "{}".format(ctx.command)
        if command_used == "exit":
            return True
        if command_used not in self.help_dict:
            return False
        command_info = self.help_dict[command_used]
        if command_info['access'] == 'roles':
            user_roles = [
                role.name for role in sorted(ctx.author.roles, key=lambda x: int(x.position), reverse=True)
            ]
            shared_roles = set(user_roles).intersection(command_info['roles'])
            if (len(shared_roles) == 0):
                await ctx.send(
                    "You do not have adequate permission to execute this command, incident will be reported"
                )
            return (len(shared_roles) > 0)
        if command_info['access'] == 'permissions':
            user_perms = await get_list_of_user_permissions(ctx)
            shared_perms = set(user_perms).intersection(command_info['permissions'])
            if (len(shared_perms) == 0):
                await ctx.send(
                    "You do not have adequate permission to execute this command, incident will be reported"
                )
            return (len(shared_roles) > 0)
        return False

    ########################################################
    # Function that gets called whenever a commmand      ##
    # gets called, being use for data gathering purposes ##
    ########################################################
    @commands.Cog.listener()
    async def on_command(self, ctx):
        if self.check_test_environment(ctx) and  \
           self.config.enabled("database", option="DB_ENABLED"):
            try:
                host = '{}_wall_e_db'.format(self.config.get_config_value('basic_config', 'COMPOSE_PROJECT_NAME'))
                db_connection_string = (
                    "dbname='{}' user='{}' host='{}'".format(
                        self.config.get_config_value('database', 'WALL_E_DB_DBNAME'),
                        self.config.get_config_value('database', 'WALL_E_DB_USER'),
                        host)
                )
                logger.info(
                    "[ManageCog on_command()] db_connection_string=[{}]".format(db_connection_string))
                conn = self.psycopg2.connect(
                    "{} password='{}'".format(
                        db_connection_string,
                        self.config.get_config_value('database', 'WALL_E_DB_PASSWORD')
                    )
                )
                logger.info("[ManageCog on_command()] PostgreSQL connection established")
                conn.set_isolation_level(self.psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
                curs = conn.cursor()
                epoch_time = int(time.time())
                now = datetime.datetime.now()
                current_year = str(now.year)
                current_month = str(now.month)
                current_day = str(now.day)
                current_hour = str(now.hour)
                channel_name = str(ctx.channel).replace("\'", "[single_quote]").strip()
                command = str(ctx.command).replace("\'", "[single_quote]").strip()
                method_of_invoke = str(ctx.invoked_with).replace("\'", "[single_quote]").strip()
                invoked_subcommand = str(ctx.invoked_subcommand).replace("\'", "[single_quote]").strip()

                # this next part is just setup to keep inserting until it finsd a primary key that is not in use
                successful = False
                while not successful:
                    try:
                        sql_command = (
                            "INSERT INTO CommandStats ( epoch_time, YEAR, "
                            "MONTH, DAY, HOUR, channel_name, Command, invoked_with, "
                            "invoked_subcommand) VALUES ({},{} ,{},{},{} ,'{}', "
                            "'{}','{}','{}');".format(
                                epoch_time,
                                current_year,
                                current_month,
                                current_day,
                                current_hour,
                                channel_name,
                                command,
                                method_of_invoke,
                                invoked_subcommand
                            )
                        )
                        logger.info("[ManageCog on_command()] sql_command=[{}]".format(sql_command))
                        curs.execute(sql_command)
                    except self.psycopg2.IntegrityError as e:
                        logger.error("[ManageCog on_command()] "
                                     "enountered following exception when trying to insert the"
                                     " record\n{}".format(e))
                        epoch_time += 1
                        logger.info("[ManageCog on_command()] incremented the epoch_time to {} and"
                                    " will try again.".format(epoch_time))
                    else:
                        successful = True
                curs.close()
                conn.close()
            except Exception as e:
                logger.error("[ManageCog on_command()] enountered following exception when setting up PostgreSQL "
                             "connection\n{}".format(e))

    ####################################################
    # Function that gets called when the script cant ##
    # understand the command that the user invoked   ##
    ####################################################
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if self.check_test_environment(ctx):
            if isinstance(error, commands.MissingRequiredArgument):
                logger.error('[ManageCog on_command_error()] Missing argument: {0}'.format(error.param))
                e_obj = await imported_embed(
                    ctx,
                    author=self.config.get_config_value('bot_profile', 'BOT_NAME'),
                    avatar=self.config.get_config_value('bot_profile', 'BOT_AVATAR'),
                    description="Missing argument: {}".format(error.param)
                )
                if e_obj is not False:
                    await ctx.send(embed=e_obj)
            else:
                # only prints out an error to the log if the string that was entered doesnt contain just "."
                pattern = r'[^\.]'
                if re.search(pattern, str(error)[9:-14]):
                    # author = ctx.author.nick or ctx.author.name
                    # await ctx.send('Error:\n```Sorry '+author+', seems like the command
                    # \"'+str(error)[9:-14]+'\"" doesn\'t exist :(```')
                    if type(error) is discord.ext.commands.errors.CheckFailure:
                        logger.warning(
                            "[ManageCog on_command_error()] user {} "
                            "probably tried to access a command they arent supposed to".format(ctx.author)
                        )
                    else:
                        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
                        return

    # this command is used by the TEST guild to create the channel from which this TEST container will process
    # commands
    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("[ManageCog on_ready()] acquired {} channels".format(len(self.bot.guilds[0].channels)))
        if self.config.get_config_value("basic_config", "ENVIRONMENT") == 'TEST':
            logger.info("[ManageCog on_ready()] ENVIRONMENT detected to be 'TEST' ENVIRONMENT")
            channels = self.bot.guilds[0].channels
            branch_name = self.config.get_config_value('basic_config', 'BRANCH_NAME').lower()
            if discord.utils.get(channels, name=branch_name) is None:
                logger.info(
                    "[ManageCog on_ready()] creating the text channel {}".format(
                        self.config.get_config_value('basic_config', 'BRANCH_NAME').lower()
                    )
                )
                await self.bot.guilds[0].create_text_channel(branch_name)
