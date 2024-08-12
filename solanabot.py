#!/usr/bin/env python
# pylint: disable=unused-argument

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from utils import *
from dotenv import load_dotenv
import os

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Load environment variables from .env file
load_dotenv()

# Access the environment variables
HELIUS_API = os.getenv('HELIUS_API')
DATABASE_URL = os.getenv('DATABASE_URL')
TABLE_NAME = os.getenv('TABLE_NAME')
BOT_API = os.getenv('BOT_API')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Hi! Use /wallet <address> to fetch wallet information")


async def send_wallet_info(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send wallet info"""
    job = context.job
    await context.bot.send_message(job.chat_id, text=f"Wait a moment.. Generating stats")
    # Get the last signature from the database
    last_signature = get_last_signature(job.data)
    # fetch latest transactions and save to DB.
    fetch_transactions(job.data, HELIUS_API, last_signature)

    # fetch all txs from db
    txs = select_from_db(job.data)
    await context.bot.send_message(job.chat_id, text=f"Number of transactions filtered: {len(txs)}")

def remove_job_if_exists(name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Remove job with given name. Returns whether job was removed."""
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True


async def fetch_wallet_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a job to the queue."""
    chat_id = update.effective_message.chat_id
    try:
        # args[0] should contain the time for the timer in seconds
        address = str(context.args[0])
        if len(address) < 10:
            await update.effective_message.reply_text("Enter a wallet address")
            return

        job_removed = remove_job_if_exists(str(chat_id), context)
        context.job_queue.run_once(send_wallet_info, 0, chat_id=chat_id, name=str(chat_id), data=address)

        text = "Wait a little bit, fetching wallet transactions"
        if job_removed:
            text += " Old one was removed."
        await update.effective_message.reply_text(text)

    except (IndexError, ValueError):
        await update.effective_message.reply_text("Usage: /wallet <address>")

def main() -> None:
    """Run bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_API).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler(["start", "help"], start))
    application.add_handler(CommandHandler("wallet", fetch_wallet_data))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()