import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def add_is_called_column():
    """Add is_called column to all order tables"""
    with engine.connect() as connection:
        try:
            # Add is_called column to product_orders table
            connection.execute(text("""
                ALTER TABLE product_orders 
                ADD COLUMN is_called BOOLEAN DEFAULT FALSE NOT NULL
            """))
            print("✅ Added is_called column to product_orders table")
            
            # Add is_called column to service_orders table
            connection.execute(text("""
                ALTER TABLE service_orders 
                ADD COLUMN is_called BOOLEAN DEFAULT FALSE NOT NULL
            """))
            print("✅ Added is_called column to service_orders table")
            
            # Add is_called column to accessory_orders table
            connection.execute(text("""
                ALTER TABLE accessory_orders 
                ADD COLUMN is_called BOOLEAN DEFAULT FALSE NOT NULL
            """))
            print("✅ Added is_called column to accessory_orders table")
            
            connection.commit()
            print("🎉 Migration completed successfully!")
            
        except Exception as e:
            connection.rollback()
            print(f"❌ Migration failed: {e}")
            raise

if __name__ == "__main__":
    add_is_called_column()
