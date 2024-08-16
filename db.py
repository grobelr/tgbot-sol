from sqlalchemy import create_engine, Column, Integer, Text, Float, String, Boolean, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, aliased
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

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

# Initialize the database
engine = create_engine(DATABASE_URL)
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

def return_not_processed_sigs(wallet_address):
    session = Session()
    try:
        # Create an alias for the Transaction table
        tx_alias = aliased(Transaction)

        # Step 1: Select signatures that have succeeded and do not have a corresponding entry in the Transaction table
        sigs = session.query(Signature).outerjoin(
            tx_alias, Signature.signature == tx_alias.signature
        ).filter(
            Signature.wallet_address == wallet_address,
            Signature.succeed == True,
            tx_alias.signature == None  # Filter for signatures not in the Transaction table
        ).all()
        return sigs
    except Exception as e:
        print(f"An error occurred while processing transactions: {e}")
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

def fetch_transactions(wallet_address):
    session = Session()
    # Query the transactions for the given wallet address
    transactions = session.query(Transaction).filter_by(wallet_address=wallet_address).all()
    return transactions

