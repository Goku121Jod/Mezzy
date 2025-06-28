import discord
from discord.ext import commands
import json
import re
import os

with open("config.json") as f:
    config = json.load(f)

TOKEN = config["TOKEN"]
PREFIX = config["PREFIX"]

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

BALANCE_FILE = "balances.json"
FAKE_LTC_RATE = 85.0
pending_withdrawals = {}

def load_balances():
    if not os.path.exists(BALANCE_FILE):
        return {}
    with open(BALANCE_FILE, "r") as f:
        return json.load(f)

def save_balances(balances):
    with open(BALANCE_FILE, "w") as f:
        json.dump(balances, f, indent=4)

def get_user_balance(balances, user_id):
    user_id = str(user_id)
    if user_id not in balances:
        balances[user_id] = {"ltc": 0.0}
    return balances[user_id]

@bot.command(aliases=["bals"])
async def bal(ctx, coin: str = "ltc"):
    if coin.lower() != "ltc":
        await ctx.reply("❌ Unsupported coin. Use `ltc`.")
        return

    balances = load_balances()
    user_balance = get_user_balance(balances, ctx.author.id)
    ltc = user_balance["ltc"]
    usd = ltc * FAKE_LTC_RATE

    embed = discord.Embed(
        title=f"{ctx.author.display_name}'s Litecoin wallet",
        color=discord.Color.dark_gray()
    )
    embed.add_field(
        name="Balance",
        value=f"**{ltc:.4f} LTC** (≈ ${usd:.2f})",
        inline=False
    )
    embed.set_footer(text="Try $balances command to see all of your balances.")
    await ctx.reply(embed=embed)

@bot.command()
async def tip(ctx, member: discord.Member, amount_str: str, coin: str):
    if member == ctx.author:
        await ctx.send("You can't tip yourself.")
        return

    match = re.match(r"(\d+(?:\.\d+)?)\$", amount_str)
    if not match:
        await ctx.send("Please use the format like `10$`.")
        return

    usd = float(match.group(1))
    ltc_amount = round(usd / FAKE_LTC_RATE, 4)

    balances = load_balances()
    sender = get_user_balance(balances, ctx.author.id)
    receiver = get_user_balance(balances, member.id)

    if sender["ltc"] < ltc_amount:
        await ctx.reply(f"❌ You don't have enough LTC. Your balance: {sender['ltc']} LTC.")
        return

    sender["ltc"] -= ltc_amount
    receiver["ltc"] += ltc_amount
    save_balances(balances)

    await ctx.reply(f"{ctx.author.mention} sent {member.mention} {ltc_amount} LTC (≈ ${usd:.2f}).")

@bot.command()
async def withdraw(ctx, coin: str = None):
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.reply("❌ Withdrawals must be done in DMs.")
        return

    if coin != "ltc":
        await ctx.send("❌ Only `ltc` withdrawals are supported.")
        return

    embed = discord.Embed(
        title="❓ Enter your **Litecoin (LTC)** destination address.",
        description="Reply with `cancel` to cancel.",
        color=discord.Color.blurple()
    )
    await ctx.send(embed=embed)
    pending_withdrawals[ctx.author.id] = {"stage": "awaiting_address"}

@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if not isinstance(message.channel, discord.DMChannel):
        return

    user_id = message.author.id
    if user_id not in pending_withdrawals:
        return

    data = pending_withdrawals[user_id]
    balances = load_balances()
    user_balance = get_user_balance(balances, user_id)

    if message.content.lower().strip() == "cancel":
        del pending_withdrawals[user_id]
        await message.channel.send("❌ Withdrawal canceled.")
        return

    if data["stage"] == "awaiting_address":
        data["address"] = message.content.strip()
        data["stage"] = "awaiting_amount"

        embed = discord.Embed(
            title="❓ How much **Litecoin (LTC)** do you want to withdraw?",
            description=(
                f"You have **{user_balance['ltc']:.8f} LTC**.\n"
                "Reply with `all` to withdraw all.\n"
                "Reply with `cancel` to cancel."
            ),
            color=discord.Color.blurple()
        )
        await message.channel.send(embed=embed)

    elif data["stage"] == "awaiting_amount":
        if message.content.lower().strip() == "all":
            embed = discord.Embed(
                title="⛔ Command error",
                description="Cannot make a withdrawal at this moment.\nPlease try again later.",
                color=discord.Color.red()
            )
            await message.channel.send(embed=embed)
            del pending_withdrawals[user_id]
            return

        try:
            amount = float(message.content)
        except ValueError:
            await message.channel.send("❌ Invalid amount. Please enter a number or `all`.")
            return

        if amount <= 0 or amount > user_balance["ltc"]:
            await message.channel.send("❌ Invalid or insufficient balance.")
            return

        user_balance["ltc"] -= amount
        save_balances(balances)
        del pending_withdrawals[user_id]
        await message.channel.send(f"✅ Sent {amount:.4f} LTC to `{data['address']}` successfully.")

bot.run(TOKEN)
  
