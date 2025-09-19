import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def run_migration():
    """
    Migrates the order tables by replacing the 'is_called' boolean column
    with a 'status' string column.
    """
    tables = ["product_orders", "service_orders", "accessory_orders"]
    
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            for table in tables:
                print(f"🚀 Starting migration for table: {table}")

                # Step 1: Add the new 'status' column.
                # Using a temporary nullable status to handle existing rows.
                print(f"   - Adding 'status' column to {table}...")
                connection.execute(text(f"""
                    ALTER TABLE {table}
                    ADD COLUMN status VARCHAR(50)
                """))
                print(f"   ✅ Added 'status' column to {table}")

                # Step 2: Update the 'status' column based on the 'is_called' column.
                print(f"   - Migrating data from 'is_called' to 'status' in {table}...")
                connection.execute(text(f"""
                    UPDATE {table}
                    SET status = CASE
                        WHEN is_called = TRUE THEN 'Đã gọi'
                        ELSE 'Chưa gọi'
                    END
                """))
                print(f"   ✅ Data migrated for {table}")

                # Step 3: Drop the old 'is_called' column.
                print(f"   - Dropping 'is_called' column from {table}...")
                connection.execute(text(f"""
                    ALTER TABLE {table}
                    DROP COLUMN is_called
                """))
                print(f"   ✅ Dropped 'is_called' column from {table}")

                # Step 4: Alter the 'status' column to be NOT NULL with a default.
                print(f"   - Setting NOT NULL and default for 'status' column in {table}...")
                connection.execute(text(f"""
                    ALTER TABLE {table}
                    ALTER COLUMN status SET NOT NULL,
                    ALTER COLUMN status SET DEFAULT 'Chưa gọi'
                """))
                print(f"   ✅ Finalized 'status' column for {table}")
                
                print(f"🎉 Successfully migrated table: {table}\n")

            transaction.commit()
            print("🎉 All tables migrated successfully!")
            
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            print("   - Rolling back changes...")
            transaction.rollback()
            raise

if __name__ == "__main__":
    run_migration()
