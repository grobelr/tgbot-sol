from solders.pubkey import Pubkey
from solders.signature import Signature
from solana.rpc.async_api import AsyncClient
import asyncio
from utils import *




async def main():
    transaction_signature = "4caFrxRPJdRKmKyAwDuUertQ3tPWg5d9oDdVqzSByTp7XEJTHRXUEuWHTnHXD6Vf2LSwVVqT5NAkxSWMgv6YqwKH"
    tx_details = fetch_transaction_details(transaction_signature)
    if tx_details:
        ## Extract token Account Creation (used to match with swaps)
        tkAccount = extract_token_account_details(tx_details)
        if tkAccount:
            logging.info(f"{tkAccount} {transaction_signature}")

# Run the async main function
if __name__ == "__main__":
    asyncio.run(main())
