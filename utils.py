import requests
import pandas as pd
import numpy as np
import json
import time
from db import *
from decode_tx import *


def last_signature(wallet_address):
    return get_last_signature(wallet_address)

def process_txs_from_sig(wallet_address, max_retries=3, retry_delay=5):
    sigs = return_not_processed_sigs(wallet_address)
    total_sigs = len(sigs)
    next_milestone = 1
    print(f"Processing {total_sigs} transactions for wallet: {wallet_address}")
    
    try:
        for idx, sig in enumerate(sigs):
            retries = 0
            success = False
            while retries < max_retries and not success:
                try:
                    # Fetch transaction details
                    tx_details = fetch_transaction_details(sig.signature)
                    if tx_details:
                        simplified_tx = identify_transaction_type(tx_details)
                        save_tx_detail(wallet_address, simplified_tx)
                        success = True  # Mark success if everything went well
                    else:
                        print(f"Failed to fetch transaction details for signature: {sig.signature}")
                except Exception as fetch_error:
                    print(f"Error fetching transaction details for signature: {sig.signature}, retrying... {retries+1}/{max_retries}")
                    retries += 1
                    time.sleep(retry_delay)
                
                if not success and retries == max_retries:
                    print(f"Max retries reached for signature: {sig.signature}. Skipping...")

                # Delay between processing transactions
                time.sleep(retry_delay)

            # Calculate progress percentage
            progress = ((idx + 1) / total_sigs) * 100

            # Print progress at milestones (10%, 20%, ..., 100%)
            if progress >= next_milestone:
                print(f"Progress: {progress:.2f}% ({idx + 1}/{total_sigs})")
                next_milestone += 10  # Move to the next milestone

    except Exception as e:
        print(f"An error occurred while processing transactions: {e} (Signature: {sig.signature})")


def fetch_transaction_details(signature, rpc_url="https://api.mainnet-beta.solana.com"):
    # Create the request payload
    params = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [
            signature,
            {
                "encoding": "jsonParsed",  # You can use "jsonParsed" for parsed output
                "commitment": "finalized",
                "maxSupportedTransactionVersion": 0
            }
        ]
    }

    # Send the request
    response = requests.post(rpc_url, json=params)
    data = response.json()

    # Check for errors
    if 'error' in data:
        print("Error fetching transaction details:", data['error'])
        return None
    return data

def fetch_and_save_signatures(
        address, 
        rpc_url="https://api.mainnet-beta.solana.com", 
        last_signature=None, 
        limit=1000):
    signatures = []

    while True:
        params = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [
                address,
                {
                    "limit": limit,
                    "before": last_signature  # Use last_signature to continue fetching
                }
            ]
        }

        response = requests.post(rpc_url, json=params)
        data = response.json()

        if 'error' in data:
            print("Error fetching signatures:", data['error'])
            break

        # Extract signatures from the result
        result = data.get('result', [])
        if not result:
            print("No more signatures to fetch.")
            break

        # Filter and append signatures
        for item in result:
            if 'err' in item and 'InstructionError' in str(item['err']):
                item['succeed'] = False
                item['err'] = json.dumps(item['err'])
            else:
                item['succeed'] = True
            item.pop('memo')
            item.pop('confirmationStatus')
            save_signatures(address, item)

        # Update the last_signature to continue fetching
        last_signature = result[-1]['signature']

        print(f"Fetched {len(result)} signatures, total after filtering: {len(signatures)}")
        time.sleep(4)
        
        # If less than the limit is returned, we have reached the end
        if len(result) < limit:
            break

def select_from_db(wallet_address):
    # Initialize the database and create a session
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Query the database for transactions associated with the given wallet_address
        transactions = session.query(Transaction).filter_by(wallet_address=wallet_address).all()

        # Extract the JSON data from each transaction
        txs = [json.loads(tx.data) for tx in transactions]
        return txs

    except Exception as e:
        print(f"Error fetching transactions from the database: {e}")
        return None

    finally:
        # Close the session
        session.close()

def load_transactions_to_dataframe(wallet_address):
    txs = fetch_transactions(wallet_address)
    # Convert query results to list of dictionaries (needed for DataFrame conversion)
    data = [
        {
            'wallet': tx.wallet_address,
            'mint': tx.mint,
            'signature': tx.signature,
            'slot': tx.slot,
            'timestamp': tx.blockTime,
            'fee': tx.fee,
            'source': tx.source,
            'typetx': tx.typetx,
            'typeop': tx.typeop,
            'source_amount': tx.source_amount,
            'token_amount': tx.token_amount,
        }
        for tx in txs
    ]
    
    # Convert to DataFrame
    if not data:
        return pd.DataFrame()  # Return an empty DataFrame if no data
    
    df = pd.DataFrame(data)
    
    # Convert timestamp to datetime format
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
    
    return df

def transform_to_dataframe(wallet_address, transactions):
    data = []
    for tx in transactions:
        # Find Mint, operation type
        mints = set()
        typeop = 'UNKNOWN'
        fee_payer = tx.get('feePayer', '')
        # check if the signer is wallet_address, if not, skip
        if wallet_address != fee_payer:
            continue
        source = tx.get('source')
        source_amount = 0
        token_amount = 0
        if source == 'RAYDIUM' or 'JUPITER':
            ## Resolve buy/sell raydium swap
            for transfer in tx.get('tokenTransfers', []):
                mint = transfer.get('mint')
                if mint and mint != 'So11111111111111111111111111111111111111112':
                    mints.add(mint)
                
                if transfer.get('fromUserAccount') == fee_payer:
                    if mint == 'So11111111111111111111111111111111111111112':
                        typeop = 'BUY'
                        source_amount = transfer.get('tokenAmount')
                    else:
                        typeop = 'SELL'
                        token_amount = transfer.get('tokenAmount')
                elif transfer.get('toUserAccount') == fee_payer:
                    if mint == 'So11111111111111111111111111111111111111112':
                        typeop = 'SELL'
                        source_amount = transfer.get('tokenAmount')
                    else:
                        typeop = 'BUY'
                        token_amount = transfer.get('tokenAmount')
        elif source == 'SYSTEM_PROGRAM':
            for instruction in tx.get('instructions', []):
                if instruction.get('programId') == "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P":
                    source = "PUMPFUN"
                    for transfer in tx.get('tokenTransfers', []):
                        mint = transfer.get('mint')
                        mints.add(mint)
                        if transfer.get('fromUserAccount') == fee_payer:
                            typeop = 'SELL'
                            token_amount = transfer.get('tokenAmount')
                        elif transfer.get('toUserAccount') == fee_payer:
                            typeop = 'BUY'
                            token_amount = transfer.get('tokenAmount')
                    for account_entry in tx.get('accountData', []):
                        if account_entry.get('account') == fee_payer:
                            nativeChange = account_entry.get('nativeBalanceChange')
                            source_amount = abs(nativeChange) / 1_000_000_000
        else:
            continue
        if len(mints) > 1:
            print(f"Alert: Multiple different mints found in transaction {tx.get('signature', '')}: {mints}")
        
        mint_value = mints.pop() if mints else None

        if source.upper() in ['PUMPFUN', 'JUPITER', 'RAYDIUM']:
            print(source)
            data.append({
                'wallet': tx.get('feePayer', ''),
                'mint': mint_value,
                'signature': tx.get('signature', ''),
                'slot': tx.get('slot', 0),
                'timestamp': tx.get('timestamp', 0),
                'fee': tx.get('fee', 0),
                'source': source,
                'typetx': tx.get('type', ''),
                'typeop': typeop,
                'source_amount': source_amount,
                'token_amount': token_amount,
            })

    if not data:
        return pd.DataFrame
        
    df = pd.DataFrame(data)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
    return df

def save_transaction_to_db(session, wallet_address, transaction_data):
    signature = transaction_data.get('signature')
    transaction_json = json.dumps(transaction_data)
    
    new_transaction = Transaction(
        wallet_address=wallet_address,
        signature=signature,
        data=transaction_json
    )
    
    # Add the transaction to the session and commit it to the database
    session.add(new_transaction)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Failed to save transaction {signature}: {e}")

def save_to_database(df, database_url, table_name):
    engine = (database_url)
    with engine.connect() as connection:
        df.to_sql(table_name, con=connection, if_exists='append', index=False)

# Function to generate and print the DataFrame
def generate_and_print_df(database_url, table_name):
    # Load data from the database into a DataFrame
    engine = create_engine(database_url)
    df_from_db = pd.read_sql_table(table_name, con=engine)

    # Set display options to avoid truncation
    pd.set_option('display.max_rows', None)  # Display all rows
    pd.set_option('display.max_columns', None)  # Display all columns
    pd.set_option('display.max_colwidth', None)  # Display full column width
    pd.set_option('display.expand_frame_repr', False)  # Disable wrapping to new lines

    # Print the entire DataFrame
    print(df_from_db)

def generate_dt(database_url, table_name):
    engine = create_engine(database_url)

    # Load data from the database into a DataFrame
    return pd.read_sql_table(table_name, con=engine)

def expand_grouped_data(grouped):
    max_len = grouped.applymap(lambda x: len(x.split(' | '))).max().max()

    expanded_df = pd.DataFrame()

    for col in grouped.columns:
        if col == 'signature':
            expanded_df[col] = grouped[col]
        else:
            expanded_cols = grouped[col].apply(lambda x: pd.Series(x.split(' | ')))
            expanded_cols.columns = [f"{col}_{i+1}" for i in range(max_len)]
            expanded_df = pd.concat([expanded_df, expanded_cols], axis=1)

    return expanded_df

def determine_transaction_action(row):
    if row['mint_1'] == 'So11111111111111111111111111111111111111112':
        row['action'] = 'buy'
    else:
        row['action'] = 'sell'
    return row

# Update Columns for Solana Spend and Receive Function
def update_sol_spent_received(expanded_df):
    # Ensure tokenAmount_1 and tokenAmount_2 are cast to float
    expanded_df['tokenAmount_1'] = expanded_df['tokenAmount_1'].astype(float)
    expanded_df['tokenAmount_2'] = expanded_df['tokenAmount_2'].astype(float)
    expanded_df['sol_spent'] = 0.0
    expanded_df['sol_received'] = 0.0

    for i in range(len(expanded_df)):
        row = expanded_df.iloc[i]
        mint_2 = row['mint_2']
        mint_1 = row['mint_1']
        tokenAmount_1 = row['tokenAmount_1']
        tokenAmount_2 = row['tokenAmount_2']

        # Update sol_spent
        if mint_2 != 'So11111111111111111111111111111111111111112':
            previous_rows = expanded_df[(expanded_df['mint_2'] == mint_2) & (expanded_df.index < i)]
            if not previous_rows.empty:
                last_row_index = previous_rows.index[-1]
                sol_spent_previous = expanded_df.at[last_row_index, 'sol_spent']
                print(sol_spent_previous, tokenAmount_1)
                expanded_df.at[i, 'sol_spent'] = sol_spent_previous + tokenAmount_1
            else:
                expanded_df.at[i, 'sol_spent'] = tokenAmount_1

        # Update sol_received
        if mint_1 != 'So11111111111111111111111111111111111111112':
            previous_rows = expanded_df[(expanded_df['mint_1'] == mint_1) & (expanded_df.index < i)]
            if not previous_rows.empty:
                last_row_index = previous_rows.index[-1]
                sol_received_previous = expanded_df.at[last_row_index, 'sol_received']
                expanded_df.at[i, 'sol_received'] = sol_received_previous + tokenAmount_2
            else:
                expanded_df.at[i, 'sol_received'] = tokenAmount_2
    return expanded_df

# Create Token and Trade Size Columns Function
def create_token_trade_size(expanded_df):
    expanded_df['token'] = expanded_df.apply(
        lambda row: row['mint_1'] if row['mint_1'] != 'So11111111111111111111111111111111111111112' else row['mint_2'],
        axis=1
    )

    expanded_df['trade_size'] = expanded_df.apply(
        lambda row: row['tokenAmount_1'] if row['action'] == 'sell' else row['tokenAmount_2'],
        axis=1
    )
    return expanded_df

# Calculate Previous and New Amount Function
def calculate_amounts(expanded_df):
    expanded_df['previous amount'] = 0.0
    expanded_df['new amount'] = 0.0

    for i in range(len(expanded_df)):
        row = expanded_df.iloc[i]
        token = row['token']
        trade_size = row['trade_size']

        # Find the previous row with the same token
        previous_rows = expanded_df[(expanded_df['token'] == token) & (expanded_df.index < i)]
        if not previous_rows.empty:
            last_row_index = previous_rows.index[-1]
            previous_amount = expanded_df.at[last_row_index, 'new amount']
        else:
            previous_amount = 0.0

        # Set the previous amount
        expanded_df.at[i, 'previous amount'] = previous_amount

        # Calculate the new amount
        if row['action'] == 'buy':
            new_amount = previous_amount + trade_size
        elif row['action'] == 'sell':
            new_amount = previous_amount - trade_size

        # Set the new amount
        expanded_df.at[i, 'new amount'] = new_amount
    return expanded_df

# Calculate Trade Price Function
def calculate_trade_price(expanded_df):
    expanded_df['trade_price'] = expanded_df.apply(
        lambda row: row['tokenAmount_1'] / row['tokenAmount_2'] if row['action'] == 'buy' else row['tokenAmount_2'] / row['tokenAmount_1'],
        axis=1
    )
    return expanded_df

def calculate_final_pnl(expanded_df):
    expanded_df['final_pnl %'] = 0.0
    expanded_df['final_pnl'] = 0.0

    threshold = 1e-9

    for i in range(len(expanded_df)):
        row = expanded_df.iloc[i]
        token = row['token']
        action = row['action']
        new_amount = row['new amount']
        print(token, action, new_amount)
        if action == 'sell' and np.isclose(new_amount, 0, atol=threshold):
            previous_rows = expanded_df[(expanded_df['token'] == token) & (expanded_df['action'] == 'buy') & (expanded_df.index < i)]
            if not previous_rows.empty:  # Corrected here
                last_row_index = previous_rows.index[-1]
                sol_spent_previous = expanded_df.at[last_row_index, 'sol_spent']
                sol_received_current = row['sol_received']
                if sol_spent_previous != 0:
                    final_pnl_percentage = (sol_received_current / sol_spent_previous - 1) * 100
                    final_pnl = sol_received_current - sol_spent_previous
                    expanded_df.at[i, 'final_pnl %'] = round(final_pnl_percentage, 5)
                    expanded_df.at[i, 'final_pnl'] = round(final_pnl, 5)
    return expanded_df

# Calculate Accumulated PnL Function
def calculate_accumulated_pnl(expanded_df):
    expanded_df['accumulated_pnl'] = 0.0

    accumulated_pnl = 0.0

    for i in range(len(expanded_df)):
        row = expanded_df.iloc[i]
        final_pnl = row['final_pnl']

        accumulated_pnl += final_pnl
        expanded_df.at[i, 'accumulated_pnl'] = round(accumulated_pnl, 5)
    return expanded_df

# Filter PnL DataFrame Function
def filter_pnl_dataframe(expanded_df):
    expanded_df['final_pnl'] = expanded_df['final_pnl'].astype(float)
    pnl_df = expanded_df[expanded_df['final_pnl'] != 0].reset_index(drop=True)
    return pnl_df