"""
Migration script to add group_members table for tracking group membership
Run this from the project root: python3 -m database.migrate_add_group_members
"""

from sqlalchemy import inspect
from database import engine, DATABASE_URL
from models import group_members

def migrate():
    """Add group_members table to existing database"""
    inspector = inspect(engine)
    
    # Check if group_members table already exists
    if 'group_members' in inspector.get_table_names():
        print("✅ group_members table already exists. No migration needed.")
        return
    
    print("🔄 Creating group_members table...")
    
    # Create only the group_members table
    group_members.create(engine)
    
    print("✅ Migration completed successfully!")
    print(f"   Database: {DATABASE_URL}")
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
        import sys
        sys.exit(1)
