import requests
import pandas as pd
import numpy as np
import json
import time
from db import *
from decode_tx import *
import matplotlib.pyplot as plt
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)

async def fetch_tx(sig, rpc_url, timesleep, coro_id):
    try:
        tx_details = await asyncio.to_thread(fetch_transaction_details, sig.signature, rpc_url)
        if tx_details and tx_details.get('result') is not None:
            await asyncio.to_thread(update_signature_with_data, sig.signature, tx_details)
        else:
            logging.info(f"[Coroutine {coro_id}] Failed to fetch transaction details for signature: {sig.signature}")
    except Exception as e:
        logging.info(f"[Coroutine {coro_id}] Error fetching transaction details for signature: {sig.signature}: {e}")
    finally:
        await asyncio.sleep(timesleep)  # Delay between processing transactions

async def fetch_txs_from_sigs(wallet_address, max_retries=5, retry_delay=5, rpc_url="https://api.mainnet-beta.solana.com", timesleep=4):
    sigs = fetch_incompleted_signatures(wallet_address)
    total_sigs = len(sigs)
    if total_sigs == 0:
        logging.info(f"Nothing new for wallet: {wallet_address}")
        return

    next_milestone = 1
    logging.info(f"Processing {len(sigs)} txs for wallet: {wallet_address}")

    tasks = []
    for idx, sig in enumerate(sigs):
        task = fetch_tx(sig, rpc_url, timesleep, idx + 1)
        tasks.append(task)
    
    # Run all tasks concurrently
    await asyncio.gather(*tasks)

    # Print progress at milestones (10%, 20%, ..., 100%)
    progress = ((idx + 1) / total_sigs) * 100
    if progress >= next_milestone:
        logging.info(f"Progress: {progress:.2f}% ({idx + 1}/{total_sigs})")
        next_milestone += 10  # Move to the next milestone

# def fetch_txs_from_sigs(
#         wallet_address, 
#         max_retries=5, 
#         retry_delay=5,
#         rpc_url="https://api.mainnet-beta.solana.com",
#         timesleep=4
#         ):
#     sigs = fetch_incompleted_signatures(wallet_address)
#     total_sigs = len(sigs)
#     next_milestone = 1
#     logging.info(f"Processing {len(sigs)} txs from total {total_sigs} txs for wallet: {wallet_address}")
#     try:
#         for idx, sig in enumerate(sigs):
#             retries = 0
#             success = False
#             while retries < max_retries and not success:
#                 try:
#                     # Fetch transaction details
#                     tx_details = fetch_transaction_details(sig.signature, rpc_url)
#                     if tx_details and tx_details.get('result') is not None:
#                         update_signature_with_data(sig.signature, tx_details)
#                         success = True  # Mark success if everything went well
#                     else:
#                         logging.info(f"Failed to fetch transaction details for signature: {sig.signature}")
#                 except Exception as e:
#                     logging.info(f"Error fetching transaction {e} details for signature: {sig.signature}, retrying... {retries+1}/{max_retries}")
#                     retries += 1
#                     time.sleep(retry_delay)
                
#                 if not success and retries == max_retries:
#                     logging.info(f"Max retries reached for signature: {sig.signature}. Skipping...")

#                 # Delay between processing transactions
#                 time.sleep(timesleep)

#             # Calculate progress percentage
#             progress = ((idx + 1) / total_sigs) * 100

#             # Print progress at milestones (10%, 20%, ..., 100%)
#             if progress >= next_milestone:
#                 logging.info(f"Progress: {progress:.2f}% ({idx + 1}/{total_sigs})")
#                 next_milestone += 10  # Move to the next milestone

#     except Exception as e:
#         logging.error(f"An error occurred while processing transactions: {e} (Signature: {sig.signature})")

def save_all_token_accounts(wallet_address):
    try:
        sigs = fetch_unprocessed_token_account_signatures(wallet_address)
        for sig in sigs:
            try:
                # Deserialize the JSON string into a dictionary
                tx_details = json.loads(sig.data)

                if not isinstance(tx_details, dict):
                    raise ValueError(f"tx_details is not a dictionary after deserialization: {type(tx_details)}")
                if 'result' not in tx_details or not isinstance(tx_details['result'], dict):
                    raise ValueError(f"tx_details['result'] is missing or not a dictionary: {tx_details}")
                update_signature_with_processed(sig.signature, processed=True)
                token_accounts = extract_token_account_details(tx_details)
                if token_accounts == []:
                    continue
                for account in token_accounts:
                    try:
                        save_token_account_create(account, sig.signature)
                    except Exception as e:
                        logging.error(f"Error saving token account {account}: {e}")
            except json.JSONDecodeError as e:
                logging.error(f"Error decoding JSON for signature {sig.signature}: {e}")
            except Exception as e:
                logging.error(f"Error processing signature {sig.signature}: {e}")
    except Exception as e:
        logging.error(f"Error fetching token accounts: {e}")

def process_txs(wallet_address):
    try:
        sigs = fetch_processed_signatures_not_in_transactions(wallet_address)
        logging.info(f"Fetched {len(sigs)} signatures to process for wallet: {wallet_address}")
        
        for sig in sigs:
            try:
                tx_details = sig.data
                
                # Debug: Log the type and content of tx_details
                logging.debug(f"tx_details type: {type(tx_details)}")
                logging.debug(f"tx_details content: {tx_details}")
                
                # If tx_details is a string, parse it as JSON
                if isinstance(tx_details, str):
                    try:
                        tx_details = json.loads(tx_details)
                        logging.debug("tx_details successfully parsed from JSON string.")
                    except json.JSONDecodeError as e:
                        logging.error(f"JSON decoding failed for signature {sig.signature}: {e}")
                        continue  # Skip this iteration
                
                # Proceed only if tx_details is a dictionary
                if not isinstance(tx_details, dict):
                    logging.error(f"tx_details has unexpected type for signature {sig.signature}: {type(tx_details)}")
                    continue  # Skip this iteration

                # Now attempt to identify the transaction type
                simplified_tx = identify_transaction_type(tx_details)
                
                if simplified_tx:
                    # logging.info(f"simplified_tx: {simplified_tx}")
                    save_tx_detail(wallet_address, simplified_tx)
                else:
                    logging.warning(f"Could not identify transaction type for signature: {sig.signature}")
            
            except Exception as e:
                logging.error(f"Exception occurred while processing signature {sig.signature}: {e}")
                logging.debug("Traceback:", exc_info=True)
                
    except Exception as e:
        logging.error(f"Exception occurred in process_txs: {e}")
        logging.debug("Traceback:", exc_info=True)

def process_txs_from_sig(
        wallet_address,
        rpc_url="https://api.mainnet-beta.solana.com",
        timesleep=4
        ):
    logging.info("Fetching transactions...")

    # Run the asynchronous fetch_txs_from_sigs
    # asyncio.create_task(fetch_txs_from_sigs(wallet_address, rpc_url=rpc_url, timesleep=timesleep))

    asyncio.run(fetch_txs_from_sigs(wallet_address, rpc_url=rpc_url, timesleep=timesleep))

    logging.info("Processing Token Accounts...")
    save_all_token_accounts(wallet_address)
    logging.info("Processing the Swaps...")
    process_txs(wallet_address)

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
        logging.error("Error fetching transaction details:", data['error'])
        return None
    return data

def fetch_and_save_signatures(
        address, 
        rpc_url="https://api.mainnet-beta.solana.com", 
        last_signature=None, 
        limit=1000,
        timesleep=4):
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
            logging.error("Error fetching signatures:", data['error'])
            break

        # Extract signatures from the result
        result = data.get('result', [])
        if not result:
            logging.info("No more signatures to fetch.")
            break

        # Filter and append signatures
        for item in result:
            if'err' in item and ('InstructionError' in str(item['err']) or 'InsufficientFundsForRent' in str(item['err'])):
                item['succeed'] = False
                item['err'] = json.dumps(item['err'])
            else:
                item['succeed'] = True
            item.pop('memo')
            item.pop('confirmationStatus')
            save_signatures(address, item)

        # Update the last_signature to continue fetching
        last_signature = result[-1]['signature']

        logging.info(f"Fetched {len(result)} signatures, total after filtering: {len(signatures)}")
        time.sleep(timesleep)
        
        # If less than the limit is returned, we have reached the end
        if len(result) < limit:
            break

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
            logging.info(f"Alert: Multiple different mints found in transaction {tx.get('signature', '')}: {mints}")
        
        mint_value = mints.pop() if mints else None

        if source.upper() in ['PUMPFUN', 'JUPITER', 'RAYDIUM']:
            logging.info(source)
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
        logging.error(f"Failed to save transaction {signature}: {e}")

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
    logging.info(df_from_db)

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

def update_sol_spent_received(df):
# Iterate over each row and update the sol_spent and sol_received columns
    df['sol_spent'] = 0.0
    df['sol_received'] = 0.0

    for i in range(len(df)):
        row = df.iloc[i]
        typeop = row['typeop']
        mint = row['mint']
        source_amount = row['source_amount']

        # Update sol_spent when typeop == 'BUY'
        if typeop == 'BUY':
            previous_rows = df[(df['typeop'] == 'BUY') & (df['mint'] == mint) & (df.index < i)]
            if not previous_rows.empty:
                last_row_index = previous_rows.index[-1]
                sol_spent_previous = df.at[last_row_index, 'sol_spent']
                df.at[i, 'sol_spent'] = sol_spent_previous + source_amount
            else:
                df.at[i, 'sol_spent'] = source_amount

        # Update sol_received when typeop == 'SELL'
        if typeop == 'SELL':
            previous_rows = df[(df['typeop'] == 'SELL') & (df['mint'] == mint) & (df.index < i)]
            if not previous_rows.empty:
                last_row_index = previous_rows.index[-1]
                sol_received_previous = df.at[last_row_index, 'sol_received']
                df.at[i, 'sol_received'] = sol_received_previous + source_amount
            else:
                df.at[i, 'sol_received'] = source_amount
    return df

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

def calculate_amounts(df):

    # Initialize the previous amount and new amount columns
    df['previous amount'] = 0.0
    df['new amount'] = 0.0

    # Iterate over each row and update the previous amount and new amount columns
    for i in range(len(df)):
        row = df.iloc[i]
        mint = row['mint']
        token_amount = row['token_amount']

        # Find the previous row with the same mint
        previous_rows = df[(df['mint'] == mint) & (df.index < i)]
        if not previous_rows.empty:
            last_row_index = previous_rows.index[-1]
            previous_amount = df.at[last_row_index, 'new amount']
        else:
            previous_amount = 0.0

        # Set the previous amount
        df.at[i, 'previous amount'] = previous_amount

        # Calculate the new amount
        if row['typeop'] == 'BUY':
            new_amount = previous_amount + token_amount
        elif row['typeop'] == 'SELL':
            new_amount = previous_amount - token_amount

        # Set the new amount
        df.at[i, 'new amount'] = new_amount

    return df

# Calculate Trade Price Function
def calculate_trade_price(expanded_df):
    expanded_df['trade_price'] = expanded_df.apply(
        lambda row: row['tokenAmount_1'] / row['tokenAmount_2'] if row['action'] == 'buy' else row['tokenAmount_2'] / row['tokenAmount_1'],
        axis=1
    )
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

def calculate_final_pnl(df):
    # Calculate trade_price by dividing source_amount by token_amount
    df['trade_price'] = (df['source_amount'] / df['token_amount']).round(6)

    # Initialize the final_pnl columns
    df['final_pnl %'] = 0.0
    df['final_pnl'] = 0.0

    # Define a small threshold for floating point comparison
    threshold = 1e-9

    for i in range(len(df)):
        row = df.iloc[i]
        mint = row['mint']
        action = row['typeop']
        new_amount = row['new amount']

        # Check if action is 'SELL' and new amount is close to zero within the threshold
        if action == 'SELL' and np.isclose(new_amount, 0, atol=threshold):
            # Find the previous row with the same mint and action 'BUY'
            previous_rows = df[(df['mint'] == mint) & (df['typeop'] == 'BUY') & (df.index < i)]
            if not previous_rows.empty:
                last_row_index = previous_rows.index[-1]
                sol_spent_previous = df.at[last_row_index, 'sol_spent']
                sol_received_current = row['sol_received']
                if sol_spent_previous != 0:
                    final_pnl_percentage = (sol_received_current / sol_spent_previous - 1) * 100  # Convert to percentage
                    final_pnl = sol_received_current - sol_spent_previous  # Calculate absolute PnL
                    df.at[i, 'final_pnl %'] = round(final_pnl_percentage, 5)
                    df.at[i, 'final_pnl'] = round(final_pnl, 5)
    return df

def accu_pnl_df(df):
    # Filter the DataFrame to only rows where 'final_pnl' is not zero and reset the index
    df_pnl = df[df['final_pnl %'] != 0].reset_index(drop=True)

    # Initialize the accumulated_pnl column
    df_pnl['accumulated_pnl'] = 0.0

    # Initialize the accumulated PnL
    accumulated_pnl = 0.0

    for i in range(len(df_pnl)):
        row = df_pnl.iloc[i]
        final_pnl = row['final_pnl']

        # Accumulate the PnL
        accumulated_pnl += final_pnl
        df_pnl.at[i, 'accumulated_pnl'] = round(accumulated_pnl, 5)

    return df_pnl

def summarize_wallet_performance(df, chat_id=None):
    # Step4: Calculate pnls
    df = df.sort_values(by="timestamp").reset_index(drop=True)
    df = update_sol_spent_received(df)
    df = calculate_amounts(df)
    df = calculate_final_pnl(df)
    df_pnl = accu_pnl_df(df)

    # Step 5: Filter the DataFrame for positive values on balance only (to avoid outliers)
    filtered_df = df[(df['previous amount'] >= 0) & (df['new amount'] >= 0)]

    # Step 6: Calculate the cumulative sums for sol_spent, sol_received, and fees
    filtered_df['accumulated_sol_spent'] = filtered_df['sol_spent'].cumsum()
    filtered_df['accumulated_sol_received'] = filtered_df['sol_received'].cumsum()
    filtered_df['accumulated_fees'] = filtered_df['fee'].cumsum()

    # Step 7: Get the last values of accumulated_sol_spent and accumulated_sol_received
    total_sol_spent = filtered_df['accumulated_sol_spent'].iloc[-1].round(5)
    total_sol_received = filtered_df['accumulated_sol_received'].iloc[-1].round(5)

    # Step 8: Calculate the estimated PnL for trades not closed
    estimated_pnl = (total_sol_received - total_sol_spent).round(5)

    # Step 9: Fees calculation - Get the last value of accumulated_fees
    total_fee_spent = (filtered_df['accumulated_fees'].iloc[-1] / 1000000000).round(5)
    avg_fee = (total_fee_spent/df['mint'].nunique()).round(5)

    # Find the first and last trades
    first_trade_timestamp = filtered_df['timestamp'].iloc[0]
    last_trade_timestamp = filtered_df['timestamp'].iloc[-1]

    avg_trade_size = (filtered_df['accumulated_sol_spent'].iloc[-1]/filtered_df['mint'].nunique()).round(5)

    # Step 1: Extract unique values from the 'mint' column in both DataFrames
    unique_pnl_mints = set(df_pnl['mint'].dropna().unique())
    unique_filtered_mints = set(filtered_df['mint'].dropna().unique())

    # Step 2: Find mints that are in df_pnl but not in filtered_df
    missing_in_filtered = unique_pnl_mints - unique_filtered_mints

    # Step 3: Find mints that are in filtered_df but not in df_pnl
    missing_in_pnl = unique_filtered_mints - unique_pnl_mints

    # Calculate the number of unique values in the 'mint' column
    tokens_traded = filtered_df['mint'].nunique() 
    trades_closed = df_pnl['mint'].nunique()
    trades_open = tokens_traded - trades_closed

    # Basic statistics for final_pnl
    mean_pnl = df_pnl['final_pnl'].mean()
    median_pnl = df_pnl['final_pnl'].median()
    std_pnl = df_pnl['final_pnl'].std()
    min_pnl = df_pnl['final_pnl'].min()
    max_pnl = df_pnl['final_pnl'].max()
    percentiles_pnl = df_pnl['final_pnl'].quantile([0.1, 0.25, 0.5, 0.75, 0.9])
    total_pnl = df_pnl['final_pnl'].sum()

    # Basic statistics for final_pnl %
    mean_pnl_percent = df_pnl['final_pnl %'].mean()
    median_pnl_percent = df_pnl['final_pnl %'].median()
    std_pnl_percent = df_pnl['final_pnl %'].std()
    min_pnl_percent = df_pnl['final_pnl %'].min()
    max_pnl_percent = df_pnl['final_pnl %'].max()
    percentiles_pnl_percent = df_pnl['final_pnl %'].quantile([0.1, 0.25, 0.5, 0.75, 0.9])
    total_pnl_percent = df_pnl['final_pnl %'].sum()

    # Calc win rate
    wins = (df_pnl['final_pnl'] > 0).sum()
    losses = (df_pnl['final_pnl'] < 0).sum()
    win_rate = wins / (losses + wins) * 100 

    summary = {}

    # General wallet performance
    summary['general_performance'] = {
        'first_trade_timestamp': first_trade_timestamp,
        'last_trade_timestamp': last_trade_timestamp,
        'tokens_traded': tokens_traded,
        'trades_closed': trades_closed,
        'trades_open': trades_open,
        'total_sol_spent': total_sol_spent,
        'total_sol_received': total_sol_received,
        'net_sol': estimated_pnl,
    }

    # Individual closed trades stats
    summary['closed_trades_overview'] = {
        'winners': wins,
        'losses': losses,
        'win_rate_percent': win_rate,
        'average_trade_size_sol': avg_trade_size,
        'mean_pnl_sol': mean_pnl,
        'mean_pnl_percent': mean_pnl_percent,
        'std_pnl_sol': std_pnl,
        'std_pnl_percent': std_pnl_percent,
        'min_pnl_sol': min_pnl,
        'min_pnl_percent': min_pnl_percent,
        '25th_percentile_pnl_sol': percentiles_pnl[0.25],
        '25th_percentile_pnl_percent': percentiles_pnl_percent[0.25],
        '50th_percentile_pnl_sol': percentiles_pnl[0.5],
        '50th_percentile_pnl_percent': percentiles_pnl_percent[0.5],
        '75th_percentile_pnl_sol': percentiles_pnl[0.75],
        '75th_percentile_pnl_percent': percentiles_pnl_percent[0.75],
        'max_pnl_sol': max_pnl,
        'max_pnl_percent': max_pnl_percent,
        'total_pnl_sol': total_pnl,
        'total_pnl_percent': total_pnl_percent,
    }

    # Fees
    summary['fees'] = {
        'total_fee_spent_sol': total_fee_spent,
        'avg_fee_per_trade_sol': avg_fee,
    }

    ## matplot
    # Convert timestamps to only date and hour
    df_pnl['timestamp'] = pd.to_datetime(df_pnl['timestamp']).dt.strftime('%Y-%m-%d %H:00')

    # Add an initial value of 0 for the accumulated PnL
    initial_row = pd.DataFrame({'timestamp': [df_pnl['timestamp'].min()], 'accumulated_pnl': [0]})
    df_pnl = pd.concat([initial_row, df_pnl], ignore_index=True)

    # Plot the accumulated PnL over time
    plt.figure(figsize=(14, 8))

    # Plot cumulative PnL
    plt.subplot(2, 1, 1)
    plt.plot(df_pnl['timestamp'], df_pnl['accumulated_pnl'], marker='o', linestyle='-', color='b')
    plt.xlabel('Time')
    plt.ylabel('Accumulated PnL')
    plt.title('Accumulated PnL Over Time')
    plt.xticks(ticks=df_pnl['timestamp'][:], rotation=45, fontsize=8)  
    plt.grid()
    # Save the plot to a file
    plt.tight_layout()  # Adjusts the layout to make sure everything fits without overlapping
    filename = f"imgs/{int(time.time())}_{chat_id}.png"
    plt.savefig(filename, format='png')  # You can change the format to 'jpeg', 'pdf', etc.
    plt.close()  # Close the plot to free memory
    summary['graph_filename'] = filename
    return summary