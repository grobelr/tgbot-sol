import requests
import time 

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

    # Print the returned JSON data
    print("Transaction Details:")
    print(data)

def fetch_signatures(address, rpc_url="https://api.mainnet-beta.solana.com", limit=1000):
    signatures = []
    last_signature = None

    while True:
        # Create the request payload
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

        # Send the request
        response = requests.post(rpc_url, json=params)
        data = response.json()

        # Check for errors
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
            # Ignore if there's an InstructionError
            if 'err' in item and 'InstructionError' in str(item['err']):
                item['succeed'] = False
            else:
                item['succeed'] = True
            item.pop('memo')
            item.pop('confirmationStatus')
            print(item)
            signatures.append(item)

        # Update the last_signature to continue fetching
        last_signature = result[-1]['signature']

        print(f"Fetched {len(result)} signatures, total after filtering: {len(signatures)}")
        break
        time.sleep(4)
        # If less than the limit is returned, we have reached the end
        if len(result) < limit:
            break

    return signatures

# Example usage
# address = "4jgU7a7Gx6sK3Lcn9nHnfdwTjZSkW5Cxn2xDgH8hXXF6"
address = "BfwRPhWViYr5rK8JPQVDEFvRqbyUowU2MiBJgbJEKc4t"
# fetch_transaction_details("4FMKhBt9dD57A1cFyjGER8ntdnQcdnKkDy1izoW71EHGn6S2TXT2e3rkqFT46EsRiod6zgPbBDkwu7KHmAQ9DweM")
signatures = fetch_signatures(address)
# print(f"Total signatures fetched: {len(signatures)}")

