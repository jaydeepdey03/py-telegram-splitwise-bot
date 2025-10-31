"""
Standalone migration script to add group_members table
This script can be run directly without module imports
"""

import os
import sys
from sqlalchemy import create_engine, inspect, Table, Column, Integer, ForeignKey, DateTime, MetaData
from sqlalchemy.sql import func

# Get DATABASE_URL from environment or use default
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./billsplit.db")

# Connection arguments based on database type
connect_args = {}
engine_kwargs = {}

if "sqlite" in DATABASE_URL:
    connect_args = {"check_same_thread": False}
elif "postgresql" in DATABASE_URL:
    engine_kwargs = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }

# Create engine
engine = create_engine(
    DATABASE_URL, 
    connect_args=connect_args,
    **engine_kwargs
)

def migrate():
    """Add group_members table to existing database"""
    inspector = inspect(engine)
    
    # Check if group_members table already exists
    if 'group_members' in inspector.get_table_names():
        print("✅ group_members table already exists. No migration needed.")
        return
    
    print("🔄 Creating group_members table...")
    
    # Create metadata and reflect existing tables
    metadata = MetaData()
    metadata.reflect(bind=engine)
    
    # Define group_members table
    group_members = Table(
        'group_members',
        metadata,
        Column('group_id', Integer, ForeignKey('groups.id'), primary_key=True),
        Column('user_id', Integer, ForeignKey('telegram_users.id'), primary_key=True),
        Column('joined_at', DateTime(timezone=True), server_default=func.now())
    )
    
    # Create only the new table
    group_members.create(engine)
    
    print("✅ Migration completed successfully!")
    print(f"   Database: {DATABASE_URL}")
    print("\n📝 What changed:")
    print("  ✓ Added 'group_members' table to track which users belong to which groups")
    print("  ✓ This table links telegram_users and groups with a many-to-many relationship")
    print("\n📝 Next steps:")
    print("1. Users who send messages will automatically be added to group membership")
    print("2. Only users who are members of a group can be included in expenses for that group")
    print("3. This fixes the security issue where users from different groups could be mentioned")
    print("\n⚠️  Note: Existing users will need to send a message in each group to register")
    print("   their membership in that specific group.")

if __name__ == "__main__":
    try:
        migrate()
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
