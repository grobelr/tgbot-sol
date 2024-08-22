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
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Load environment variables from .env file
load_dotenv()

# Access the environment variables
HELIUS_API = os.getenv('HELIUS_API')
DATABASE_URL = os.getenv('DATABASE_URL')
TABLE_NAME = os.getenv('TABLE_NAME')
BOT_API = os.getenv('BOT_API')
RPC_URL = os.getenv('RPC_URL')

if RPC_URL:
    rpc_url = RPC_URL
else:
    rpc_url = 'https://api.mainnet-beta.solana.com'

timesleep = 0.2

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Hi! Use /wallet <address> to fetch wallet information")


async def send_wallet_info(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send wallet info"""
    job = context.job
    await context.bot.send_message(job.chat_id, text=f"Wait a moment.. Generating stats")
    
    # Load the transactions into a dataframe
    last_signature = get_last_signature(job.data)
    logging.info(f"Fetch sig for {job.data}")
    
    fetch_and_save_signatures(address=job.data, last_signature=last_signature, rpc_url=RPC_URL, timesleep=timesleep)
    # Step 2: Process all txs
    logging.info(f"process txs {job.data}")
    process_txs_from_sig(wallet_address=job.data, rpc_url=rpc_url, timesleep=timesleep)
    df = load_transactions_to_dataframe(job.data)
    
    # Generate the wallet summary
    logging.info(f"Summarize {job.data}")
    wallet_summary = summarize_wallet_performance(df, job.chat_id)
    
    # Prepare the message with all the information
    message = f"""
🚀 *Wallet Performance Summary* 🚀

🗓 *First Trade:* {wallet_summary['general_performance']['first_trade_timestamp']}
🗓 *Last Trade:* {wallet_summary['general_performance']['last_trade_timestamp']}
💼 *Unique Tokens Traded:* {wallet_summary['general_performance']['tokens_traded']}
📈 *Trades Closed:* {wallet_summary['general_performance']['trades_closed']}
📉 *Trades Open:* {wallet_summary['general_performance']['trades_open']}

💰 *Total SOL Spent (Buys):* {wallet_summary['general_performance']['total_sol_spent']:.6f}
💸 *Total SOL Received (Sells):* {wallet_summary['general_performance']['total_sol_received']:.6f}
📊 *Net SOL:* {wallet_summary['general_performance']['net_sol']:.6f}

 *Closed Trades Overview:*
✅ *Winners:* {wallet_summary['closed_trades_overview']['winners']}
❌ *Losses:* {wallet_summary['closed_trades_overview']['losses']}
🏆 *Win Rate:* {wallet_summary['closed_trades_overview']['win_rate_percent']:.2f}%
📏 *Average Trade Size (SOL):* {wallet_summary['closed_trades_overview']['average_trade_size_sol']:.4f}
🔄 *Mean PnL:* {wallet_summary['closed_trades_overview']['mean_pnl_sol']:.4f} SOL ({wallet_summary['closed_trades_overview']['mean_pnl_percent']:.2f}%)
📉 *Min PnL:* {wallet_summary['closed_trades_overview']['min_pnl_sol']:.4f} SOL ({wallet_summary['closed_trades_overview']['min_pnl_percent']:.2f}%)
📈 *Max PnL:* {wallet_summary['closed_trades_overview']['max_pnl_sol']:.4f} SOL ({wallet_summary['closed_trades_overview']['max_pnl_percent']:.2f}%)

🎯 *Percentiles of PnL:*
25th: {wallet_summary['closed_trades_overview']['25th_percentile_pnl_sol']:.4f} SOL ({wallet_summary['closed_trades_overview']['25th_percentile_pnl_percent']:.2f}%)
50th (Median): {wallet_summary['closed_trades_overview']['50th_percentile_pnl_sol']:.4f} SOL ({wallet_summary['closed_trades_overview']['50th_percentile_pnl_percent']:.2f}%)
75th: {wallet_summary['closed_trades_overview']['75th_percentile_pnl_sol']:.4f} SOL ({wallet_summary['closed_trades_overview']['75th_percentile_pnl_percent']:.2f}%)

📊 *Total PnL:* {wallet_summary['closed_trades_overview']['total_pnl_sol']:.4f} SOL ({wallet_summary['closed_trades_overview']['total_pnl_percent']:.2f}%)

💸 *Fees Overview:*
💰 *Total SOL Spent on Fees:* {wallet_summary['fees']['total_fee_spent_sol']:.6f} SOL
💵 *Average Fee per Trade:* {wallet_summary['fees']['avg_fee_per_trade_sol']:.6f} SOL
    """
    
    # Send the prepared message
    await context.bot.send_message(
        chat_id=job.chat_id, 
        text=message,
        parse_mode='Markdown'
    )
    # Send the plot image
    with open(f"imgs/{wallet_summary['graph_filename']}", 'rb') as photo:
        await context.bot.send_photo(chat_id=job.chat_id, photo=photo)

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