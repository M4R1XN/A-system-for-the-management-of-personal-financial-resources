import sqlite3
import bcrypt
import secrets
import logging

logging.basicConfig(level=logging.INFO)

def create_finance_db():
    conn = sqlite3.connect('finance.db')
    c = conn.cursor()

    # Create or Update Users Table
    c.execute("PRAGMA table_info(users)")
    user_columns = [col[1] for col in c.fetchall()]
    if 'is_admin' not in user_columns or 'secret_key' not in user_columns:
        logging.info("Updating 'users' table...")
        c.execute("DROP TABLE IF EXISTS users")
        c.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                secret_key TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0
            )
        ''')

    # Create Transactions Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            currency TEXT DEFAULT 'USD',
            user_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Create Planned Transactions Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS planned_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            planned_date TEXT NOT NULL,
            currency TEXT DEFAULT 'USD',
            user_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Create Categories Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Create Goals Table
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

    # Add Admin User
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        admin_password = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        admin_secret_key = secrets.token_hex(16)
        c.execute(
            "INSERT INTO users (username, password, is_admin, secret_key) VALUES (?, ?, 1, ?)",
            ("admin", admin_password, admin_secret_key)
        )
        logging.info("Admin user created with username 'admin' and password 'admin123'.")

    conn.commit()
    conn.close()
    logging.info("Database setup completed successfully.")

if __name__ == "__main__":
    create_finance_db()
