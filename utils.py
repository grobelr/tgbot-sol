import requests
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, Text, String, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import re
import numpy as np
import json
import re
import time

# Define the base class
Base = declarative_base()

# Define the model
class Transaction(Base):
    __tablename__ = 'helius_txs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet_address = Column(String, nullable=False)
    signature = Column(String, nullable=False, unique=True)
    data = Column(Text, nullable=False)

# Initialize the database
engine = create_engine('sqlite:///helius_txs.db')
Base.metadata.create_all(engine)

# Create a session
Session = sessionmaker(bind=engine)

def get_last_signature(wallet_address, table_name='helius_txs'):
    session = Session()
    # Ensure the table exists in the database
    inspector = inspect(session.bind)
    if table_name in inspector.get_table_names():
        query = f'''
            SELECT signature
            FROM {table_name}
            WHERE wallet_address = :wallet
            ORDER BY json_extract(data, '$.timestamp') ASC
            LIMIT 1
        '''
        result = session.execute(text(query), {'wallet': wallet_address}).fetchone()
        if result and result[0]:  # Access the first element of the tuple
            return result[0]
    return None
    
def fetch_transactions(wallet_address, api_key, last_signature=None):
    base_url = f'https://api.helius.xyz/v0/addresses/{wallet_address}/transactions'
    params = {'api-key': api_key}
    retries = 10

    # Create a session
    session = Session()

    while True:
        if last_signature:
            params['before'] = last_signature

        url = base_url
        print(f"Fetching transactions with URL: {url}, Params: {params}")  # Debugging line
        try:
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200:
                transactions = response.json()
                if transactions:
                    for transaction in transactions:
                        save_transaction_to_db(session, wallet_address, transaction)  # Save each transaction to the DB
                    last_signature = transactions[-1]['signature']
                else:
                    print("No more transactions available.")
                    break
            elif response.status_code == 400 or response.status_code == 404:
                error_msg = response.json().get('error', '')
                match = re.search(r"` parameter set to (.+)", error_msg)
                if match:
                    before_value = match.group(1).strip('. ')  # Strip trailing dot and space
                    print(f"Extracted 'before' value: {before_value}")  # Debugging line
                    last_signature = before_value
                    continue
                else:
                    print(f"Error fetching transactions: {response.status_code} - {response.text}")
                    break
            else:
                print(f"Error fetching transactions: {response.status_code} - {response.text}")
                break
        except requests.exceptions.Timeout:
            print("Request timed out. Retrying...")
            retries -= 1
            if retries == 0:
                print("Max retries reached. Exiting.")
                break
            time.sleep(5)
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            break

    # Close the session
    session.close()

def select_from_db(wallet_address):
    # Initialize the database and create a session
    engine = create_engine('sqlite:///helius_txs.db')
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
        if source == 'RAYDIUM':
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
        if source == 'SYSTEM_PROGRAM':
            print(source)
            for instruction in tx.get('instructions', []):
                print(instruction)
                if instruction.get('programId') == "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P":
                    source = "PUMPFUN"
                    print(source)
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
        if len(mints) > 1:
            print(f"Alert: Multiple different mints found in transaction {tx.get('signature', '')}: {mints}")
        
        mint_value = mints.pop() if mints else None

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
    engine = create_engine(database_url)
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