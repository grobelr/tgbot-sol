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
RPC_URL = os.getenv('RPC_URL')

if RPC_URL:
    rpc_url = RPC_URL
else:
    rpc_url = 'https://api.mainnet-beta.solana.com'

timesleep = 0

# exit()

# Step 1: Get all the signatures 
print(f"Using endpoint: {rpc_url}")
last_signature = get_last_signature(WALLET)
fetch_and_save_signatures(address=WALLET, last_signature=last_signature, rpc_url=rpc_url, timesleep=timesleep)
# Step 2: Process all txs
process_txs_from_sig(wallet_address=WALLET, rpc_url=rpc_url, timesleep=timesleep)

# Step3: Load transactions to dataframe
print("load tx to dataframe")
df = load_transactions_to_dataframe(WALLET)
print("calling summarize")
wallet_summary = summarize_wallet_performance(df, WALLET)
print(wallet_summary)