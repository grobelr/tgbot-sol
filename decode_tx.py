import base58

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
                # user_source_account = instruction.get('accounts')[15]
                # user_destination_account = instruction.get('accounts')[16]
                raw_data = base58.b58decode(instruction.get('data'))
                # amount_in = int.from_bytes(raw_data[1:9], "0")
                print('===> raydium data:', raw_data[0])
                if raw_data[0] == 9:
                    source = 'RAYDIUM'
                    typetx = 'SWAP/ROUTE'
                    amounts  = resolve_ray_swap(rt, fee_payer)
                    typeop = amounts[0]
                    source_amount = amounts[1]
                    token_amount = amounts[2]
                    mints = amounts[3]
                    # for ix in innerInstructions:
                    #     if ix['index'] == idx:
                    #         for inInst in ix['instructions']:
                    #             if inInst['parsed']['info']['source'] == user_source_account:
                    #                 print('Source_amount', inInst['parsed']['info']['amount'])
                    #             elif inInst['parsed']['info']['destination'] == user_destination_account:
                    #                 print('token_amount', inInst['parsed']['info']['amount'])
                    #     print("call calculate")
                    mint_value = mints.pop() if mints else None
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
            ## JUPITER / PUMPFUN
            else:
                continue
    # except KeyError:
    #     return {'type': 'INVALID'}
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

def resolve_ray_swap(tx, fee_payer):
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