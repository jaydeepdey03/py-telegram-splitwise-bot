"""
Migration script to convert Integer columns to BigInteger for Telegram IDs
Run this script to fix the integer overflow issue
"""
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./splitwise_bot.db")

def migrate_postgres():
    """Migrate PostgreSQL database"""
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        print("Starting migration...")
        
        # Alter telegram_users table
        print("Altering telegram_users.telegram_id to BIGINT...")
        conn.execute(text("ALTER TABLE telegram_users ALTER COLUMN telegram_id TYPE BIGINT"))
        conn.commit()
        
        # Alter groups table
        print("Altering groups.telegram_chat_id to BIGINT...")
        conn.execute(text("ALTER TABLE groups ALTER COLUMN telegram_chat_id TYPE BIGINT"))
        conn.commit()
        
        # Alter expenses table
        print("Altering expenses.created_by to BIGINT...")
        conn.execute(text("ALTER TABLE expenses ALTER COLUMN created_by TYPE BIGINT"))
        conn.commit()
        
        print("✅ Migration completed successfully!")

def migrate_sqlite():
    """For SQLite, we need to recreate tables"""
    print("SQLite detected. Please delete the database file and restart the bot.")
    print("The bot will automatically create tables with correct types.")
    db_file = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    print(f"\nRun: rm {db_file}")

if __name__ == "__main__":
    if "postgresql" in DATABASE_URL or "postgres" in DATABASE_URL:
        migrate_postgres()
    elif "sqlite" in DATABASE_URL:
        migrate_sqlite()
    else:
        print("Unknown database type")
