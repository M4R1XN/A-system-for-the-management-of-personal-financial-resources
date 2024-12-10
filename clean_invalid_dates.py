import sqlite3
import pandas as pd

# Establish a database connection
def get_db_connection():
    """Connect to the SQLite database."""
    conn = sqlite3.connect('finance.db')
    return conn, conn.cursor()

def clean_invalid_dates():
    """Clean invalid dates in the transactions table."""
    conn, c = get_db_connection()
    try:
        # Fetch all transaction IDs and dates
        c.execute("SELECT id, date FROM transactions")
        transactions = c.fetchall()

        for t_id, date in transactions:
            try:
                # Try parsing the date to check if it is valid
                pd.to_datetime(date, format='%Y-%m-%d')
            except ValueError:
                # Handle invalid date by either updating or deleting
                print(f"Invalid date detected for transaction ID {t_id}: {date}")
                
                # Option 1: Update the date to a default value (e.g., "2024-01-01")
                c.execute("UPDATE transactions SET date = ? WHERE id = ?", ("2024-01-01", t_id))
                
                # Option 2: Uncomment the following line to delete invalid transactions
                # c.execute("DELETE FROM transactions WHERE id = ?", (t_id,))

        # Commit changes to the database
        conn.commit()
        print("Database cleaned successfully.")
    except Exception as e:
        print(f"Error cleaning invalid dates: {e}")
    finally:
        conn.close()

# Run the cleanup function
if __name__ == "__main__":
    clean_invalid_dates()
