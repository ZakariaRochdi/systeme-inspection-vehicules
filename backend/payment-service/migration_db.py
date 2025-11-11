"""
Database Migration Script for Payments
Adds new columns to payments table:
- payment_type
- invoice_number
"""

import asyncio
import asyncpg
import sys

async def migrate_database():
    try:
        # Connect to database
        conn = await asyncpg.connect(
            host='localhost',
            port=5432,
            user='postgres',
            password='azerty5027',
            database='payments_db'
        )
        
        print("✓ Connected to payments database")
        
        # Check if columns exist
        columns = await conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'payments'
        """)
        column_names = [col['column_name'] for col in columns]
        
        print(f"✓ Existing columns: {', '.join(column_names)}")
        
        # Add payment_type if it doesn't exist
        if 'payment_type' not in column_names:
            print("Adding payment_type column...")
            await conn.execute("""
                ALTER TABLE payments 
                ADD COLUMN payment_type VARCHAR(50) NOT NULL DEFAULT 'reservation'
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_payment_type ON payments(payment_type)
            """)
            print("✓ Added payment_type column")
        else:
            print("✓ payment_type column already exists")
        
        # Add invoice_number if it doesn't exist
        if 'invoice_number' not in column_names:
            print("Adding invoice_number column...")
            await conn.execute("""
                ALTER TABLE payments 
                ADD COLUMN invoice_number VARCHAR(100) NULL UNIQUE
            """)
            print("✓ Added invoice_number column")
        else:
            print("✓ invoice_number column already exists")
        
        # Verify the changes
        columns_after = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'payments'
            ORDER BY ordinal_position
        """)
        
        print("\n=== Final Schema ===")
        for col in columns_after:
            print(f"  {col['column_name']}: {col['data_type']}")
        
        await conn.close()
        print("\n✓ Migration completed successfully!")
        
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(migrate_database())
