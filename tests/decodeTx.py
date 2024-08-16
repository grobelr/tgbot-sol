import base64
from borsh_construct import *
from solders.pubkey import Pubkey
from solana.transaction import Instruction

PublicKeyBorsh = Vec(U8, 32)

# Step 1: Define the structure according to Raydium's IDL using Borsh
# Example structure for a swap instruction, adjust based on the actual Raydium IDL
RaydiumSwapInstruction = CStruct(
    "instruction_type" / U8,
    "amount_in" / U64,
    "minimum_amount_out" / U64,
    "user_source" / PublicKeyBorsh,  # 32 bytes
    "user_destination" / PublicKeyBorsh,  # 32 bytes
    "raydium_pool" / PublicKeyBorsh,  # 32 bytes
)

# Step 2: Decode the ray_log base64 string
log_message = "Program log: ray_log: A4CEHgAAAAAA1/w9hgAAAAACAAAAAAAAAH5JDgEAAAAAt8oa7RoAAABV39zIR4QAAO7ji5UAAAAA"
encoded_log = log_message.split("ray_log: ")[-1]
decoded_log = base64.b64decode(encoded_log)

# Step 3: Parse the decoded log using the Borsh structure
try:
    parsed_log = RaydiumSwapInstruction.parse(decoded_log)
    print("Instruction Type:", parsed_log.instruction_type)
    print("Amount In:", parsed_log.amount_in)
    print("Minimum Amount Out:", parsed_log.minimum_amount_out)
    print("User Source Account:", parsed_log.user_source)
    print("User Destination Account:", parsed_log.user_destination)
    print("Raydium Pool Address:", parsed_log.raydium_pool)
except Exception as e:
    print(f"Error parsing ray_log with Borsh: {e}")
