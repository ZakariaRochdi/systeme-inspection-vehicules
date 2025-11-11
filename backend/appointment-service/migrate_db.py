"""
Database Migration Script
Adds new columns to appointments table:
- inspection_status
- inspection_payment_id
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
            database='appointments_db'
        )
        
        print("✓ Connected to database")
        
        # Check if columns exist
        columns = await conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'appointments'
        """)
        column_names = [col['column_name'] for col in columns]
        
        print(f"✓ Existing columns: {', '.join(column_names)}")
        
        # Add inspection_status if it doesn't exist
        if 'inspection_status' not in column_names:
            print("Adding inspection_status column...")
            await conn.execute("""
                ALTER TABLE appointments 
                ADD COLUMN inspection_status VARCHAR(50) NOT NULL DEFAULT 'not_checked'
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_inspection_status ON appointments(inspection_status)
            """)
            print("✓ Added inspection_status column")
        else:
            print("✓ inspection_status column already exists")
        
        # Add inspection_payment_id if it doesn't exist
        if 'inspection_payment_id' not in column_names:
            print("Adding inspection_payment_id column...")
            await conn.execute("""
                ALTER TABLE appointments 
                ADD COLUMN inspection_payment_id UUID NULL
            """)
            print("✓ Added inspection_payment_id column")
        else:
            print("✓ inspection_payment_id column already exists")
        
        # Verify the changes
        columns_after = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'appointments'
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
