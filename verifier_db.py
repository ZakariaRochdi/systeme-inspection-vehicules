import asyncio
import asyncpg

async def check_database():
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='postgres',
        password='azerty5027',
        database='appointments_db'
    )
    
    # Check table schema
    schema = await conn.fetch("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'appointments'
    """)
    print("\n=== Table Schema ===")
    for row in schema:
        print(f"{row['column_name']}: {row['data_type']}")
    
    # Check actual data
    appointments = await conn.fetch("SELECT id, user_id, payment_id, status FROM appointments LIMIT 5")
    print("\n=== Sample Data ===")
    for apt in appointments:
        print(f"ID: {apt['id']} (type: {type(apt['id'])})")
        print(f"User ID: {apt['user_id']} (type: {type(apt['user_id'])})")
        print(f"Payment ID: {apt['payment_id']} (type: {type(apt['payment_id'])})")
        print(f"Status: {apt['status']}")
        print("---")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_database())
