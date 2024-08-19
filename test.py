from utils import *
from dotenv import load_dotenv
import os
from tx import txData
from decode_tx import *

# Load environment variables from .env file
load_dotenv()

# Access the environment variables
HELIUS_API = os.getenv('HELIUS_API')
DATABASE_URL = os.getenv('DATABASE_URL')
TABLE_NAME = os.getenv('TABLE_NAME')
WALLET = os.getenv('WALLET')

# Step 1: Get all the signatures 
last_signature = get_last_signature(WALLET)
fetch_and_save_signatures(address=WALLET, last_signature=last_signature)
# Step 2: Process all txs
process_txs_from_sig(WALLET)

# Step3: Load transactions to dataframe
df = load_transactions_to_dataframe(WALLET)
wallet_summary = summarize_wallet_performance(df)
print(wallet_summary)