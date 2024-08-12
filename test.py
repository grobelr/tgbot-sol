from utils import *
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Access the environment variables
HELIUS_API = os.getenv('HELIUS_API')
DATABASE_URL = os.getenv('DATABASE_URL')
TABLE_NAME = os.getenv('TABLE_NAME')
WALLET = os.getenv('WALLET')

# Get the last signature from the database
last_signature = get_last_signature(WALLET)

# fetch latest transactions and save to DB.
fetch_transactions(WALLET, HELIUS_API, last_signature)

# fetch all txs from db
txs = select_from_db(WALLET)

# transform and save to db (everything)
# TODO: transform just new txs.
# 3QHi4kSpHTVjAeheTJ79F6eoTiaPbHfbpDkmQT1TCHuYPVTJJXYBZh2HnLvbUXjzDqCWv7i9F9tUk9e56wC6YgoY
# 2QuyzrSSjs6ntMLBwGjUViiKvt688X6HytQprGkAWBsMySM6cJUqKoCsjauHYkv53jpmbML68UhyFnF8A3G6ns2K
df = transform_to_dataframe(WALLET, txs)
if not df.empty:
    save_to_database(df, DATABASE_URL, TABLE_NAME)

exit()

## Start the process
df_from_db = generate_dt(DATABASE_URL, TABLE_NAME)
generate_and_print_df(DATABASE_URL, TABLE_NAME)

# Group by 'signature' and apply the aggregation
grouped_df = df_from_db.groupby('signature').agg(lambda x: ' | '.join(x.astype(str))).reset_index()

# Expand grouped data
expanded_df = expand_grouped_data(grouped_df)

# Filter for SWAP transactions
expanded_df = expanded_df[expanded_df['type_1'] == 'SWAP'].copy()
expanded_df = expanded_df.sort_values(by='timestamp_1')

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
print(expanded_df)
# Filter PnL DataFrame
pnl_df = filter_pnl_dataframe(expanded_df)
print("pnl", pnl_df)
