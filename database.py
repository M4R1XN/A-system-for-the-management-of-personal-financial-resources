import os
import sqlite3
import bcrypt
import secrets
from encryption import fernet_encrypt, fernet_decrypt

def get_db_connection():
    """Establish a connection to the SQLite database."""
    conn = sqlite3.connect('finance.db')
    return conn, conn.cursor()

def init_db():
    """Initialize the database with the required tables."""
    conn, c = get_db_connection()
    try:
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                secret_key TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                amount BLOB NOT NULL,
                category BLOB NOT NULL,
                date TEXT NOT NULL,
                currency TEXT DEFAULT 'USD',
                user_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                target_amount REAL NOT NULL,
                current_savings REAL DEFAULT 0,
                deadline TEXT,
                user_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        # Continue with other tables as needed
        conn.commit()
    finally:
        conn.close()

def add_user(username, password, is_admin=False):
    """Add a new user to the database."""
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode('utf-8')
    secret_key = secrets.token_hex(16)
    conn, c = get_db_connection()
    try:
        c.execute('INSERT INTO users (username, password, is_admin, secret_key) VALUES (?, ?, ?, ?)', (username, hashed, is_admin, secret_key))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def regenerate_secret_key(user_id, save_to_file=False):
    """Regenerate the secret key for a user and optionally save it to a file."""
    new_secret_key = secrets.token_hex(16)
    conn, c = get_db_connection()
    try:
        c.execute('UPDATE users SET secret_key = ? WHERE id = ?', (new_secret_key, user_id))
        conn.commit()

        if save_to_file:
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            if not os.path.exists(desktop_path):
                os.makedirs(desktop_path)
            key_file_path = os.path.join(desktop_path, f"user_{user_id}_secret.key")
            with open(key_file_path, "w") as file:
                file.write(new_secret_key)
            print(f"Secret key saved to {key_file_path}")

        return new_secret_key
    except sqlite3.Error as e:
        print(f"Error regenerating secret key for user ID {user_id}: {e}")
        return None
    finally:
        conn.close()
        
def verify_user(username, password):
    """Verify user credentials."""
    conn, c = get_db_connection()
    try:
        c.execute('SELECT id, password FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        if user and bcrypt.checkpw(password.encode(), user[1]):
            return user[0], True  # Return user ID and is_admin status
        return None, False
    finally:
        conn.close()

def get_users():
    """Retrieve all users."""
    conn, c = get_db_connection()
    try:
        c.execute('SELECT id, username FROM users')  # Fixed the query (removed the dangling comma)
        users = c.fetchall()
        return [{'id': user[0], 'username': user[1]} for user in users]  # Corrected the dictionary structure
    finally:
        conn.close()

def add_transaction(trans_type, amount, category, date, user_id, currency='USD'):
    """Add a new transaction for a user."""
    encrypted_amount = fernet_encrypt(str(amount))
    encrypted_category = fernet_encrypt(category)
    conn, c = get_db_connection()
    try:
        c.execute('INSERT INTO transactions (type, amount, category, date, currency, user_id) VALUES (?, ?, ?, ?, ?, ?)',
                  (trans_type, encrypted_amount, encrypted_category, date, currency, user_id))
        conn.commit()
    finally:
        conn.close()

def get_transactions(user_id):
    """Retrieve transactions for a specific user."""
    conn, c = get_db_connection()
    try:
        c.execute('SELECT * FROM transactions WHERE user_id = ?', (user_id,))
        data = c.fetchall()
        transactions = []
        for row in data:
            decrypted_amount = fernet_decrypt(row[2])
            decrypted_category = fernet_decrypt(row[3])
            transactions.append({
                'id': row[0],
                'type': row[1],
                'amount': decrypted_amount,
                'category': decrypted_category,
                'date': row[4],
                'currency': row[5]
            })
        return transactions
    finally:
        conn.close()

def update_transaction(transaction_id, trans_type, amount, category, date, currency):
    """Update an existing transaction."""
    encrypted_amount = fernet_encrypt(str(amount))
    encrypted_category = fernet_encrypt(category)
    conn, c = get_db_connection()
    try:
        c.execute('UPDATE transactions SET type = ?, amount = ?, category = ?, date = ?, currency = ? WHERE id = ?',
                  (trans_type, encrypted_amount, encrypted_category, date, currency, transaction_id))
        conn.commit()
    finally:
        conn.close()

def delete_transaction(transaction_id):
    """Delete a transaction."""
    conn, c = get_db_connection()
    try:
        c.execute('DELETE FROM transactions WHERE id = ?', (transaction_id,))
        conn.commit()
    finally:
        conn.close()

def delete_user(user_id):
    """Delete a user and their associated data."""
    conn, c = get_db_connection()
    try:
        c.execute('DELETE FROM transactions WHERE user_id = ?', (user_id,))
        c.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
    finally:
        conn.close()

def add_category(name, user_id):
    """Add a new category for a user."""
    conn, c = get_db_connection()
    try:
        c.execute('INSERT INTO categories (name, user_id) VALUES (?, ?)', (name, user_id))
        conn.commit()
    finally:
        conn.close()

def get_categories(user_id):
    """Retrieve categories for a specific user."""
    conn, c = get_db_connection()
    try:
        c.execute('SELECT name FROM categories WHERE user_id = ?', (user_id,))
        data = c.fetchall()
        return [category[0] for category in data]
    finally:
        conn.close()

def add_currency_rate(code, rate, date):
    """Add or update a currency rate."""
    conn, c = get_db_connection()
    try:
        c.execute('INSERT OR REPLACE INTO currencies (code, rate, date) VALUES (?, ?, ?)', (code, rate, date))
        conn.commit()
    finally:
        conn.close()

def get_currency_rate(code):
    """Retrieve currency rate by code."""
    conn, c = get_db_connection()
    try:
        c.execute('SELECT rate FROM currencies WHERE code=?', (code,))
        data = c.fetchone()
        return data[0] if data else None
    finally:
        conn.close()

def add_budget(category, amount, user_id):
    """Add or update a budget for a category."""
    conn, c = get_db_connection()
    try:
        c.execute('INSERT OR REPLACE INTO budgets (category, amount, user_id) VALUES (?, ?, ?)', (category, amount, user_id))
        conn.commit()
    finally:
        conn.close()

def get_budgets(user_id):
    """Retrieve budgets for a specific user."""
    conn, c = get_db_connection()
    try:
        c.execute('SELECT category, amount FROM budgets WHERE user_id = ?', (user_id,))
        data = c.fetchall()
        return [{'category': row[0], 'amount': row[1]} for row in data]
    finally:
        conn.close()

def add_recurring_transaction(trans_type, amount, category, start_date, frequency, user_id, currency='USD'):
    """Add a recurring transaction."""
    conn, c = get_db_connection()
    try:
        c.execute('INSERT INTO recurring_transactions (type, amount, category, start_date, frequency, user_id, currency) VALUES (?, ?, ?, ?, ?, ?, ?)',
                  (trans_type, amount, category, start_date, frequency, user_id, currency))
        conn.commit()
    finally:
        conn.close()

def get_recurring_transactions(user_id):
    """Retrieve recurring transactions for a user."""
    conn, c = get_db_connection()
    try:
        c.execute('SELECT * FROM recurring_transactions WHERE user_id = ?', (user_id,))
        data = c.fetchall()
        return [{'id': row[0], 'type': row[1], 'amount': row[2], 'category': row[3], 'start_date': row[4], 'frequency': row[5], 'currency': row[6]} for row in data]
    finally:
        conn.close()

def backup_database():
    """Backup the current database."""
    import shutil
    shutil.copy('finance.db', 'finance_backup.db')
    print("Database backup created as finance_backup.db")

def restore_database():
    """Restore the database from a backup."""
    import shutil
    shutil.copy('finance_backup.db', 'finance.db')
    print("Database restored from finance_backup.db")