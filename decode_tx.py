import base58
import logging
from db import *

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)

def extract_token_account_details(tx_details):
    token_accounts = []

    # Function to extract token account details from a given instruction
    def extract_from_instruction(instruction):
        if instruction.get('program') == 'spl-associated-token-account' and instruction.get('parsed', {}).get('type') in ['create', 'createIdempotent']:
            info = instruction['parsed']['info']
            token_accounts.append({
                'token_account': info.get('account'),
                'mint': info.get('mint'),
                'wallet': info.get('wallet')
            })

    # Search through all inner instructions
    for inner_instruction in tx_details['result']['meta']['innerInstructions']:
        for instruction in inner_instruction['instructions']:
            extract_from_instruction(instruction)
    
    # Search through main instructions
    for instruction in tx_details['result']['transaction']['message']['instructions']:
        extract_from_instruction(instruction)
    
    return token_accounts


def identify_transaction_type(tx_details):
    data = []
    mints = set()
    typeop = 'UNKNOWN'
    fee_payer = extract_fee_payer(tx_details['result'])
    source = ''
    timestamp = tx_details['result']['blockTime']
    fee = tx_details['result']['meta']['fee']
    slot = tx_details['result']['slot']
    source_amount = 0.0
    token_amount = 0.0
    signature = tx_details['result']['transaction']['signatures'][0]
    try:
        instructions = tx_details['result']['transaction']['message']['instructions']
        innerInstructions = tx_details['result']['meta']['innerInstructions']
        rt = calculate_value_changes(tx_details['result'])
        for idx, instruction in enumerate(instructions):
            ## IF RAYDIUM
            if instruction.get('programId') == '675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8':
                raw_data = base58.b58decode(instruction.get('data'))
                if raw_data[0] in [9, 11]:
                    source = 'RAYDIUM'
                    typetx = 'SWAP'
                    # amounts  = resolve_ray_swap_balances(rt, fee_payer)
                    amounts = resolve_ray_swap(idx, innerInstructions, fee_payer)
                    typeop = amounts[0]
                    mint_value = amounts[1]
                    token_decimals = get_decimals(amounts[1], tx_details['result']['meta']['preTokenBalances'])
                    source_amount = amounts[2] / (10 ** 9)
                    token_amount = amounts[3] / (10 ** token_decimals)
                    data.append({
                        'wallet': fee_payer,
                        'mint': mint_value,
                        'signature': signature,
                        'slot': slot,
                        'timestamp': timestamp,
                        'fee': fee,
                        'source': source,
                        'typetx': typetx,
                        'typeop': typeop,
                        'source_amount': source_amount,
                        'token_amount': token_amount,
                    })
                else:
                    logging.info(f'===> raydium data: {raw_data[0]}, {signature}')
            ## JUPITER / PUMPFUN
            else:
                continue
    except Exception as e:
        logging.error(f"Error processing tx {signature} {e}")
    finally:
        return data

def calculate_value_changes(transaction_json):
    # Extract necessary fields from the JSON
    pre_token_balances = transaction_json["meta"]["preTokenBalances"]
    post_token_balances = transaction_json["meta"]["postTokenBalances"]
    pre_balances = transaction_json["meta"]["preBalances"]
    post_balances = transaction_json["meta"]["postBalances"]
    account_keys = transaction_json["transaction"]["message"]["accountKeys"]

    # Create lists to store token and native transfers
    token_transfers = []
    native_transfers = []

    # Process token balances
    balance_changes = {}

    # Process preTokenBalances
    for balance in pre_token_balances:
        owner = balance["owner"]
        mint = balance["mint"]
        amount = int(balance["uiTokenAmount"]["amount"])
        decimals = balance["uiTokenAmount"]["decimals"]

        if (owner, mint) not in balance_changes:
            balance_changes[(owner, mint)] = {"pre_amount": amount, "post_amount": 0, "decimals": decimals}
        else:
            balance_changes[(owner, mint)]["pre_amount"] = amount

    # Process postTokenBalances
    for balance in post_token_balances:
        owner = balance["owner"]
        mint = balance["mint"]
        amount = int(balance["uiTokenAmount"]["amount"])
        decimals = balance["uiTokenAmount"]["decimals"]

        if (owner, mint) not in balance_changes:
            balance_changes[(owner, mint)] = {"pre_amount": 0, "post_amount": amount, "decimals": decimals}
        else:
            balance_changes[(owner, mint)]["post_amount"] = amount

    # Calculate the value changes for tokens
    for (owner, mint), values in balance_changes.items():
        pre_amount = values["pre_amount"]
        post_amount = values["post_amount"]
        decimals = values["decimals"]

        # Calculate the change, adjusting for decimals
        value_changed = (post_amount - pre_amount) / (10 ** decimals)

        # Append the result to token_transfers only if valueChanged is not 0
        if value_changed != 0:
            token_transfers.append({
                "wallet": owner,
                "mint": mint,
                "valueChanged": value_changed
            })

    # Process native SOL balances
    for idx, (pre_balance, post_balance) in enumerate(zip(pre_balances, post_balances)):
        account = account_keys[idx]
        value_changed = (post_balance - pre_balance) / (10 ** 9)  # SOL has 9 decimals

        # Append the result to native_transfers only if valueChanged is not 0
        if value_changed != 0:
            native_transfers.append({
                "wallet": account,
                "mint": "SOL",
                "valueChanged": value_changed
            })

    # Combine and return the results
    return {
        "tokenTransfers": token_transfers,
        "nativeTransfers": native_transfers
    }

def extract_fee_payer(transaction_json):
    # Extract the fee payer (signer: True)
    account_keys = transaction_json["transaction"]["message"]["accountKeys"]
    for account in account_keys:
        if account.get("signer", False):  # Check if this account is the signer
            return account["pubkey"]
    return None

def resolve_ray_swap_balances(tx, fee_payer):
    typeop = None
    source_amount = None
    token_amount = None
    mints = set()
    # Resolve buy/sell Raydium swap using the new tokenTransfers structure
    for transfer in tx.get('tokenTransfers', []):
        mint = transfer.get('mint')
        wallet = transfer.get('wallet')
        value_changed = transfer.get('valueChanged')

        # Collect all mints except WSOL (So11111111111111111111111111111111111111112)
        if mint and mint != 'So11111111111111111111111111111111111111112':
            mints.add(mint)

        # Determine if it's a BUY or SELL operation
        if wallet == fee_payer:
            if mint == 'So11111111111111111111111111111111111111112':  # WSOL
                if value_changed < 0:
                    typeop = 'BUY'
                    source_amount = -value_changed  # Convert to positive for amount
                else:
                    typeop = 'SELL'
                    source_amount = value_changed
            else:
                if value_changed < 0:
                    typeop = 'SELL'
                    token_amount = -value_changed  # Convert to positive for amount
                else:
                    typeop = 'BUY'
                    token_amount = value_changed
        else:
            if mint == 'So11111111111111111111111111111111111111112':  # WSOL
                if value_changed > 0:
                    typeop = 'SELL'
                    source_amount = value_changed
                else:
                    typeop = 'BUY'
                    source_amount = -value_changed  # Convert to positive for amount
            else:
                if value_changed > 0:
                    typeop = 'BUY'
                    token_amount = value_changed
                else:
                    typeop = 'SELL'
                    token_amount = -value_changed  # Convert to positive for amount

    # Now you have typeop, source_amount, token_amount, and mints
    return typeop, source_amount, token_amount, mints

def resolve_ray_swap(
        idx, 
        innerInstructions, 
        fee_payer,
        RAYDIUM_ACC='5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1'
        ):
    try:
        swap = []
        for inner in innerInstructions:
            if inner['index'] == idx:
                for inner_instruction in inner['instructions']:
                    if inner_instruction['program'] == "spl-token":
                        info = inner_instruction['parsed']['info']
                        authority = info.get('authority')
                        if authority == fee_payer:
                            # When the authority is the fee_payer, we care about the source account.
                            source_account = info['source']
                            token_account = fetch_token_account(source_account)
                            if token_account:
                                if token_account.wallet_address != fee_payer:
                                    logging.error(f"Source account {source_account} does not match fee_payer {fee_payer}!")
                                swap.append({
                                    'from': fee_payer,
                                    'to': info['destination'],
                                    'amount': info['amount'],
                                    'mint': token_account.mint
                                })
                            else:
                                logging.error(f"{source_account} not found")
                        elif authority == RAYDIUM_ACC:
                            # When the authority is the Raydium account, we care about the destination account.
                            destination_account = info['destination']
                            token_account = fetch_token_account(destination_account)
                            if token_account:
                                if token_account.wallet_address != fee_payer:
                                    logging.error(f"Destination account {destination_account} does not match fee_payer {fee_payer}!")
                                swap.append({
                                    'from': info['source'],
                                    'to': fee_payer,
                                    'amount': info['amount'],
                                    'mint': token_account.mint
                                })
                            else:
                                logging.error(f"{destination_account} not found")

        return determine_transaction_type(swap, fee_payer)
    except Exception as e:
        logging.error(f'An error occurred: {e}', exc_info=True)

def determine_transaction_type(transfers, fee_payer):
    source_amount = 0
    token_amount = 0
    typeop = None
    mint = None  # Initialize mint to None to determine later

    for transfer in transfers:
        from_account = transfer['from']
        to_account = transfer['to']
        amount = int(transfer['amount'])

        # Skip WSOL for mint selection; we'll handle it separately
        if transfer['mint'] != 'So11111111111111111111111111111111111111112':
            mint = transfer['mint']  # This will be the actual token's mint

        # Check if the fee_payer is the sender or receiver
        if from_account == fee_payer:
            if transfer['mint'] == 'So11111111111111111111111111111111111111112':  # WSOL
                typeop = 'BUY'
                source_amount = amount  # WSOL is being sent to buy tokens
            else:
                typeop = 'SELL'
                token_amount = amount  # Token is being sent in exchange for WSOL
        elif to_account == fee_payer:
            if transfer['mint'] == 'So11111111111111111111111111111111111111112':  # WSOL
                typeop = 'SELL'
                source_amount = amount  # WSOL is being received from selling tokens
            else:
                typeop = 'BUY'
                token_amount = amount  # Token is being received in exchange for WSOL

    return typeop, mint, source_amount, token_amount

def get_decimals(mint, postTokenBalances):
    for balance in postTokenBalances:
        if balance['mint'] == mint:
            return balance['uiTokenAmount']['decimals']
    return 0  # Default to 0 if not found