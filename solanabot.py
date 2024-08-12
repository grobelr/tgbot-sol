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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Hi! Use /wallet <address> to fetch wallet information")


async def send_wallet_info(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send wallet info"""
    job = context.job
    ## Fetch information from helius
    # txs = fetch_transactions(job.data, HELIUS_API)
    # df = transform_to_dataframe(txs)
    # save_to_database(df, DATABASE_URL, TABLE_NAME)
    # await context.bot.send_message(job.chat_id, text=f"Wallet address {job.data} saved to database, number of txs: {len(txs)}")
    await context.bot.send_message(job.chat_id, text=f"Generating stats")

    ## Start the process
    df_from_db = generate_dt(DATABASE_URL, TABLE_NAME)
    print(df_from_db)

    # Group by 'signature' and apply the aggregation
    grouped_df = df_from_db.groupby('signature').agg(lambda x: ' | '.join(x.astype(str))).reset_index()
    print(grouped_df)

    # Expand grouped data
    expanded_df = expand_grouped_data(grouped_df)

    # Filter for SWAP transactions
    expanded_df = expanded_df[expanded_df['type_1'] == 'SWAP'].copy()
    expanded_df = expanded_df.sort_values(by='timestamp_1')
    print(expanded_df)

    # Drop unnecessary columns
    expanded_df.drop(columns=['wallet_1', 'wallet_2', 'type_1', 'type_2', 'source_2', 'fee_2', 'feePayer_2', 'slot_2', 'timestamp_2', 'tokenStandard_1', 'tokenStandard_2'], inplace=True)

    # Determine transaction actions
    expanded_df = expanded_df.apply(determine_transaction_action, axis=1)

    # Update sol_spent and sol_received
    expanded_df = update_sol_spent_received(expanded_df)

    # Create token and trade size columns
    expanded_df = create_token_trade_size(expanded_df)

    # Calculate previous and new amounts
    expanded_df = calculate_amounts(expanded_df)

    # Calculate trade price
    expanded_df = calculate_trade_price(expanded_df)

    # Calculate final PnL
    expanded_df = calculate_final_pnl(expanded_df)

    # Calculate accumulated PnL
    expanded_df = calculate_accumulated_pnl(expanded_df)

    # Filter PnL DataFrame
    pnl_df = filter_pnl_dataframe(expanded_df)
    print(pnl_df)
    await context.bot.send_message(job.chat_id, text='done!')

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
    application = Application.builder().token("6891497433:AAHe7DpyFa4a-G-zoUpltw0FkjK31C4kk2U").build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler(["start", "help"], start))
    application.add_handler(CommandHandler("wallet", fetch_wallet_data))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()