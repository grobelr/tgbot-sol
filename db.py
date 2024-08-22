from sqlalchemy import create_engine, Column, Integer, Text, Float, String, Boolean, inspect, text, func, select
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, aliased
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from dotenv import load_dotenv
import os
import json
import logging

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger('sqlalchemy.pool').setLevel(logging.INFO)

DATABASE_URL = os.getenv('DATABASE_URL')

# Define the base class
Base = declarative_base()

class Signature(Base):
    __tablename__ = 'signatures'
    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet_address = Column(String, nullable=False)
    signature = Column(String, nullable=False, unique=True)
    blockTime = Column(Integer, nullable=False)
    slot = Column(Integer, nullable=False)
    err = Column(String)
    succeed = Column(Boolean, nullable=False)
    data = Column(Text, nullable=True, default=None)
    processed = Column(Boolean, default=False)

    def __repr__(self):
        return (f"<Signature(id={self.id}, wallet_address='{self.wallet_address}', signature='{self.signature}', "
                f"blockTime={self.blockTime}, slot={self.slot}, succeed={self.succeed}, "
                f"data={self.data})>, processed={self.processed})>")

class Transaction(Base):
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet_address = Column(String, nullable=False)
    mint = Column(String, nullable=True)
    signature = Column(String, nullable=False, unique=True)
    slot = Column(Integer, nullable=False)
    blockTime = Column(Integer, nullable=False)
    fee = Column(Integer, nullable=False)
    source = Column(String, nullable=True)
    typetx = Column(String, nullable=True)
    typeop = Column(String, nullable=True)
    source_amount = Column(Float, nullable=True)
    token_amount = Column(Float, nullable=True)

class TokenAccount(Base):
    __tablename__ = 'token_account'

    token_account = Column(String, primary_key=True, nullable=False)
    wallet_address = Column(String, nullable=False)
    mint = Column(String, nullable=True)
    signature = Column(String, nullable=False)

    def __repr__(self):
        return (f"<TokenAccount(token_account='{self.token_account}', wallet_address='{self.wallet_address}', "
                f"mint='{self.mint} signature='{self.signature}')>")

    
# Initialize the database
engine = create_engine(
   DATABASE_URL,
    # pool_size=10,
    # max_overflow=20,
    poolclass=NullPool,
)
Base.metadata.create_all(engine)

# Create a session
Session = sessionmaker(bind=engine)

def save_signatures(wallet_address, item):
    session = Session()
    signature = item.get('signature')
    blockTime = item.get('blockTime')
    slot = item.get('slot')
    err = item.get('err')
    succeed = item.get('succeed')

    new_sig = Signature(
        wallet_address=wallet_address,
        signature=signature,
        blockTime=blockTime,
        slot=slot,
        err=err,
        succeed=succeed
    )
    
    # Add the transaction to the session and commit it to the database
    session.add(new_sig)
    try:
        session.commit()
    except Exception as e:
        print(e)
        session.rollback()
    finally:
        # Close the session
        session.close()

def get_last_signature(wallet_address):
    session = Session()
    try:
        # Query the database for the last signature based on blockTime
        last_signature = session.query(Signature).filter_by(wallet_address=wallet_address).order_by(Signature.blockTime.asc()).first()

        if last_signature:
            return last_signature.signature  # Access the signature attribute directly
        else:
            return None  # Return None if no signature is found
    finally:
        # Close the session
        session.close()

def fetch_incompleted_signatures(wallet_address):
    session = Session()
    try:
        # Select signatures that have succeeded and do not have data, ordered by blockTime
        sigs = session.query(Signature).filter(
            Signature.wallet_address == wallet_address,
            Signature.succeed == True
        ).filter(
            func.json_extract(Signature.data, '$.result').is_(None)
        ).order_by(Signature.blockTime.asc()).all()

        return sigs
    except Exception as e:
        print(f"An error occurred while fetching not processed signatures: {e}")
    finally:
        session.close()

def fetch_unprocessed_token_account_signatures(wallet_address):
    session = Session()
    try:
        subquery = select(TokenAccount.signature)
        sigs = session.query(Signature).filter(
            Signature.wallet_address == wallet_address,
            Signature.succeed == True,
            Signature.processed == False,
            Signature.signature.notin_(subquery)
        ).order_by(Signature.blockTime.asc()).all()
        return sigs
    except Exception as e:
        print(f"An error occurred while fetching not processed signatures: {e}")
    finally:
        session.close()

def fetch_processed_signatures_not_in_transactions(wallet_address):
    session = Session()
    try:
        # Create a subquery to find signatures already in the Transaction table
        subquery = select(Transaction.signature)

        # Select signatures that have succeeded, are processed, and are not in the Transaction table
        sigs = session.query(Signature).filter(
            Signature.wallet_address == wallet_address,
            Signature.succeed == True,
            Signature.processed == True,  # Looking for processed signatures
            Signature.signature.notin_(subquery)  # Exclude signatures already in Transaction
        ).order_by(Signature.blockTime.asc()).all()  # Order by blockTime in ascending order

        return sigs
    except Exception as e:
        print(f"An error occurred while fetching processed signatures: {e}")
    finally:
        session.close()

def save_tx_detail(wallet_address, simplified_tx):
    session = Session()
    try:
        # Iterate over the list of simplified transactions
        for tx in simplified_tx:
            # Create a new Transaction object with the provided details
            new_transaction = Transaction(
                wallet_address=wallet_address,
                mint=tx.get('mint', ''),
                signature=tx.get('signature', ''),
                slot=tx.get('slot', 0),
                blockTime=tx.get('timestamp', 0),  # Assuming 'timestamp' is equivalent to 'blockTime'
                fee=tx.get('fee', 0),
                source=tx.get('source', ''),
                typetx=tx.get('typetx', ''),
                typeop=tx.get('typeop', ''),
                source_amount=tx.get('source_amount', 0.0),
                token_amount=tx.get('token_amount', 0.0)
            )
            
            # Add the transaction to the session
            session.add(new_transaction)
        # Commit the session to save all transactions
        session.commit()

    except Exception as e:
        print(f"Error saving transactions: {e}")
        session.rollback()
    finally:
        # Close the session
        session.close()

def save_token_account_create(token, signature):
    session = Session()

    try:
        new_token_account = TokenAccount(
            wallet_address=token['wallet'],
            mint=token['mint'],
            token_account=token['token_account'],
            signature=signature
        )
        
        # Add the transaction to the session
        session.add(new_token_account)
        # Commit the session to save all transactions
        session.commit()

    except IntegrityError as e:
        if "UNIQUE constraint failed" in str(e):
            next
            # print(f"Skipping duplicate token account: {tk['token_account']}")
        else:
            print(f"Error saving token account: {e}")

    except Exception as e:
        print(f"Error saving token account: {e}")
        session.rollback()
    finally:
        # Close the session
        session.close()

def fetch_transactions(wallet_address):
    session = Session()
    # Query the transactions for the given wallet address
    transactions = session.query(Transaction).filter_by(wallet_address=wallet_address).all()
    return transactions

def fetch_token_account(token_account):
    try: 
        session = Session()
        # Query the transactions for the given wallet address
        token_account = session.query(TokenAccount).filter_by(token_account=token_account).first()
        return token_account
    except Exception as e:
        print(f"Error fetching: {e}")


def update_signature_with_data(signature, data):
    session = Session()
    try:
        # Fetch the corresponding signature record
        signature_record = session.query(Signature).filter_by(signature=signature).first()

        if signature_record:
            # Update the data field with the fetched details
            signature_record.data = json.dumps(data)  # Store the details as JSON
            session.commit()
        else:
            print(f"Signature {signature} not found.")
    except Exception as e:
        print(f"Error updating signature: {e}")
        session.rollback()
    finally:
        # Close the session
        session.close()

def update_signature_with_processed(signature, processed=True):
    session = Session()
    try:
        # Fetch the corresponding signature record
        signature_record = session.query(Signature).filter_by(signature=signature).first()

        if signature_record:
            # Update the processed field
            signature_record.processed = processed
            session.commit()
        else:
            print(f"Signature {signature} not found.")
    except Exception as e:
        print(f"Error updating signature: {e}")
        session.rollback()
    finally:
        # Close the session
        session.close()


