import os
import json
import requests
import threading
import pandas as pd
import matplotlib.pyplot as plt
import tkinter as tk
from tkinter import messagebox, ttk, filedialog
from tkcalendar import DateEntry
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import timedelta
import bcrypt
import sqlite3
import shutil
import secrets
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
import io
import seaborn as sns  # Import here to avoid unnecessary imports at the top
import logging
import openpyxl

logging.basicConfig(filename='app.log', level=logging.ERROR)

# Database connection
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
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                currency TEXT DEFAULT 'USD',
                user_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        # Add planned_transactions table
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
        conn.commit()
    finally:
        conn.close()

def migrate_is_admin_column():
    """Ensure that all users have the 'is_admin' column properly set."""
    conn, c = get_db_connection()
    try:
        c.execute('UPDATE users SET is_admin = 0 WHERE is_admin IS NULL')
        conn.commit()
    except sqlite3.OperationalError as e:
        print(f"Database error during migration: {e}")
    finally:
        conn.close()

def setup_admin_user():
    """Create or ensure an admin user exists."""
    username = "admin"
    password = "admin123"


    conn, c = get_db_connection()
    try:
        # Check if admin user exists
        c.execute("SELECT id FROM users WHERE username = ?", (username,))
        if not c.fetchone():
            # Add admin user
            hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
            secret_key = secrets.token_hex(16)
            c.execute(
                'INSERT INTO users (username, password, secret_key, is_admin) VALUES (?, ?, ?, ?)',
                (username, hashed_password, secret_key, 1)
            )
            conn.commit()
            print("Admin user added.")
        else:
            print("Admin user already exists.")
    finally:
        conn.close()

def add_user(username, password, secret_key):
    """Add a new user to the database."""
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    conn, c = get_db_connection()
    try:
        c.execute(
            'INSERT INTO users (username, password, secret_key) VALUES (?, ?, ?)',
            (username, hashed_password.decode('utf-8'), secret_key)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Handle case where username is not unique
        return False
    finally:
        conn.close()

def verify_user(username, password, secret_key):
    """Verify user credentials including the secret key."""
    conn, c = get_db_connection()
    try:
        c.execute('SELECT id, password, secret_key, is_admin FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        if user:
            user_id, hashed_password, stored_secret_key, is_admin = user
            if bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8')) and stored_secret_key == secret_key:
                return user_id, bool(is_admin)  # Return user ID and admin status
        return None, False
    finally:
        conn.close()
        
def get_users():
    """Retrieve all users."""
    conn, c = get_db_connection()
    try:
        c.execute('SELECT id, username, is_admin FROM users')
        users = c.fetchall()
        return [{'id': user[0], 'username': user[1], 'is_admin': user[2]} for user in users]
    finally:
        conn.close()

def get_planned_transactions(user_id, is_admin=False):
    conn, c = get_db_connection()
    try:
        if is_admin:
            c.execute('SELECT * FROM planned_transactions')
        else:
            c.execute('SELECT * FROM planned_transactions WHERE user_id = ?', (user_id,))
        
        transactions = c.fetchall()
        columns = [desc[0] for desc in c.description]  # Extract column names
        return [dict(zip(columns, transaction)) for transaction in transactions]  # Convert to a list of dictionaries
    finally:
        conn.close()

def add_planned_transaction(user_id, trans_type, amount, category, planned_date, currency='USD'):
    conn, c = get_db_connection()
    try:
        c.execute('''
            INSERT INTO planned_transactions (type, amount, category, planned_date, currency, user_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (trans_type, amount, category, planned_date, currency, user_id))
        conn.commit()
    finally:
        conn.close()

def update_planned_transaction(transaction_id, trans_type, amount, category, planned_date, currency):
    conn, c = get_db_connection()
    try:
        c.execute('''
            UPDATE planned_transactions
            SET type = ?, amount = ?, category = ?, planned_date = ?, currency = ?
            WHERE id = ?
        ''', (trans_type, amount, category, planned_date, currency, transaction_id))
        conn.commit()
    finally:
        conn.close()

def delete_planned_transaction(transaction_id):
    conn, c = get_db_connection()
    try:
        c.execute('DELETE FROM planned_transactions WHERE id = ?', (transaction_id,))
        conn.commit()
    finally:
        conn.close()

def get_transactions(user_id, is_admin=False):
    conn, c = get_db_connection()
    try:
        if is_admin:
            c.execute('SELECT id, type, amount, category, date, currency FROM transactions')
        else:
            c.execute('SELECT id, type, amount, category, date, currency FROM transactions WHERE user_id = ?', (user_id,))
        transactions = c.fetchall()
        return [
            {
                'id': t[0],
                'type': t[1],
                'amount': t[2],
                'category': t[3],
                'date': t[4],  # Ensure this field exists in your database and query
                'currency': t[5]
            }
            for t in transactions
        ]
    finally:
        conn.close()

def backup_database():
    """Backup the current database."""
    try:
        shutil.copy('finance.db', 'finance_backup.db')
        print("Database backup created as finance_backup.db")
        messagebox.showinfo("Success", "Database backup created successfully.")
    except Exception as e:
        print(f"Error creating database backup: {e}")
        messagebox.showerror("Error", f"Failed to create database backup: {e}")

def restore_database():
    """Restore the database from a backup."""
    try:
        shutil.copy('finance_backup.db', 'finance.db')
        print("Database restored from finance_backup.db")
        messagebox.showinfo("Success", "Database restored successfully.")
    except Exception as e:
        print(f"Error restoring database: {e}")
        messagebox.showerror("Error", f"Failed to restore database: {e}")

def generate_and_save_secret_key(username, admin_id, is_admin):
    """Generate a secret key for the user and save it to a file on the desktop."""
    if not is_admin:
        raise PermissionError("Only admins can regenerate secret keys.")
    
    secret_key = secrets.token_hex(16)  # Generate a random secret key

    # Get the desktop directory dynamically
    desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.exists(desktop_dir):
        os.makedirs(desktop_dir)  # Create the directory if it doesn't exist

    file_path = os.path.join(desktop_dir, f"{username}_secret.key")

    # Save the key to the file
    with open(file_path, 'w') as key_file:
        key_file.write(secret_key)

    print(f"Secret key for {username} saved to {file_path}. Please store this file securely.")
    return secret_key, file_path

def delete_all_users():
    """Delete all users from the database."""
    conn, c = get_db_connection()
    try:
        c.execute('DELETE FROM users')
        conn.commit()
        print("All users have been deleted.")
    except Exception as e:
        print(f"Error deleting users: {e}")
    finally:
        conn.close()

# Constants
CURRENCY_FILE = "selected_currencies.json"
REMINDER_THRESHOLD = 100

# Utility functions
def get_current_exchange_rates():
    urls = [
        "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json",
        "https://api.exchangerate-api.com/v4/latest/USD"
    ]
    rates = {}
    for url in urls:
        try:
            response = requests.get(url)
            response.raise_for_status()
            if "bank.gov.ua" in url:
                data = response.json()
                rates.update({item["cc"]: item["rate"] for item in data})
            elif "exchangerate-api" in url:
                data = response.json()
                rates.update(data.get('rates', {}))
        except Exception as e:
            print(f"Error fetching exchange rates from {url}: {e}")
    if not rates:
        print("Using fallback exchange rates.")
        rates = {"USD": 1, "UAH": 36.8, "EUR": 0.94}  # Example fallback rates
    return rates

def load_selected_currencies():
    if os.path.exists(CURRENCY_FILE):
        with open(CURRENCY_FILE, 'r') as file:
            return json.load(file)
    return []

def save_selected_currencies(currencies):
    with open(CURRENCY_FILE, 'w') as file:
        json.dump(currencies, file)

# Tooltip Class
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tw = None  # Initialize tooltip window as None
        self.widget.bind("<Enter>", self.show)
        self.widget.bind("<Leave>", self.hide)

    def show(self, event):
        x, y, _, _ = self.widget.bbox("insert") or (event.x_root, event.y_root)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25

        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")

        label = ttk.Label(
            self.tw,
            text=self.text,
            style="Tooltip.TLabel"
        )
        label.pack(ipadx=1)

    def hide(self, event):
        if self.tw:
            self.tw.destroy()

# Main Application Class
class FinanceApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.listbox_exchange_rates = None
        self.verification_code = None
        self.user_id = None
        self.is_admin = False
        self.selected_color_scheme = tk.StringVar(value="Light")
        self.exchange_rates = get_current_exchange_rates()
        self.selected_currencies = load_selected_currencies()
        self.balance_var = tk.StringVar(value="Balance: $0.00")

        self.title("Finance Management System")
        self.geometry("1000x700")
        self.state('zoomed')

        self.define_color_schemes()
        self.setup_styles()
        self.create_widgets()  # Create all widgets here
        self.start_auto_refresh()  # Start refreshing after widgets are initialized
        self.filter_summary_var = tk.StringVar(value="No filters applied")
        self.comparison_result_frame = ttk.Frame(self.tabs['reports'])
        self.comparison_result_frame.pack(fill=tk.BOTH, expand=True)

        self.plot_type = tk.StringVar(value="Bar Chart")  # Default plot type

    def populate_planned_transactions(self):
        """Populate the planned transactions table in the Dashboard."""
    # Clear the tree view
        for row in self.tree_planned_transactions.get_children():
            self.tree_planned_transactions.delete(row)

    # Fetch planned transactions for the current user or all (if admin)
        planned_transactions = get_planned_transactions(self.user_id, is_admin=self.is_admin)

    # Populate the tree view
        for transaction in planned_transactions:
            self.tree_planned_transactions.insert(
                '', 'end',
                values=(
                    transaction['id'],
                    transaction['type'],
                    transaction['amount'],
                    transaction['category'],
                    transaction['planned_date'],
                    transaction['currency']
                )
            )

    def create_planned_transactions_tab(self):
        """Create the Planned Transactions and Notes tab."""
        frame_planned = ttk.LabelFrame(self.tabs['dashboard'], text="Planned Transactions and Notes", padding=10)
        frame_planned.grid(row=1, column=1, padx=10, pady=10, sticky='nsew')

    # Planned Transactions Section
        planned_frame = ttk.Frame(frame_planned)
        planned_frame.pack(side="left", fill=tk.BOTH, expand=True, padx=5, pady=5)

        ttk.Label(planned_frame, text="Planned Transactions").pack(pady=5)
        self.tree_planned_transactions = ttk.Treeview(
            planned_frame,
            columns=("ID", "Type", "Amount", "Category", "Planned Date", "Currency"),
            show="headings",
        )
        for col in self.tree_planned_transactions["columns"]:
            self.tree_planned_transactions.heading(col, text=col)
            self.tree_planned_transactions.column(col, width=100)

        self.tree_planned_transactions.pack(fill=tk.BOTH, expand=True)

        button_frame = ttk.Frame(planned_frame)
        button_frame.pack(fill='x', pady=5)

        ttk.Button(button_frame, text="Add Planned Transaction", command=self.add_planned_transaction).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Edit Selected", command=self.edit_selected_planned_transaction).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Delete Selected", command=self.delete_selected_planned_transaction).pack(side=tk.LEFT, padx=5)

    # Populate Data
        self.populate_planned_transactions()

    def add_planned_transaction(self):
        self.open_transaction_editor(mode="add")

    def edit_selected_planned_transaction(self):
        selected = self.tree_planned_transactions.selection()
        if not selected:
            messagebox.showwarning("Warning", "No planned transaction selected!")
            return
        transaction_id = self.tree_planned_transactions.item(selected[0], "values")[0]
        self.open_transaction_editor(mode="edit", transaction_id=transaction_id)

    def delete_selected_planned_transaction(self):
        selected = self.tree_planned_transactions.selection()
        if not selected:
            messagebox.showwarning("Warning", "No planned transaction selected!")
            return
        transaction_id = self.tree_planned_transactions.item(selected[0], "values")[0]
        delete_planned_transaction(transaction_id)
        self.populate_planned_transactions()

    def display_transaction_history(self, df):
        """Display a table of transactions in the report frame."""
        for widget in self.report_frame.winfo_children():
            widget.destroy()  # Clear the frame

    def open_transaction_editor(self, mode="add", transaction_id=None):
        """Open the Planned Transaction Editor in add or edit mode."""
    # Create Editor Window
        editor = tk.Toplevel(self)
        editor.title("Planned Transaction Editor")
        editor.geometry("400x500")
        editor.resizable(False, False)

    # Title
        ttk.Label(editor, text="Planned Transaction Editor", font=("Arial", 14, "bold")).pack(pady=10)

    # Transaction Type
        frame_type = ttk.Frame(editor)
        frame_type.pack(fill='x', padx=20, pady=5)
        ttk.Label(frame_type, text="Transaction Type:", font=("Arial", 12)).grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        trans_type_var = tk.StringVar(value="expense")
        ttk.Radiobutton(frame_type, text="Expense", variable=trans_type_var, value="expense").grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Radiobutton(frame_type, text="Income", variable=trans_type_var, value="income").grid(row=0, column=2, sticky=tk.W, padx=5)

    # Amount
        frame_amount = ttk.Frame(editor)
        frame_amount.pack(fill='x', padx=20, pady=5)
        ttk.Label(frame_amount, text="Amount:", font=("Arial", 12)).grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        amount_var = tk.StringVar()
        ttk.Entry(frame_amount, textvariable=amount_var).grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        frame_amount.columnconfigure(1, weight=1)

    # Category
        frame_category = ttk.Frame(editor)
        frame_category.pack(fill='x', padx=20, pady=5)
        ttk.Label(frame_category, text="Category:", font=("Arial", 12)).grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        category_var = tk.StringVar()
        ttk.Entry(frame_category, textvariable=category_var).grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        frame_category.columnconfigure(1, weight=1)

    # Planned Date
        frame_date = ttk.Frame(editor)
        frame_date.pack(fill='x', padx=20, pady=5)
        ttk.Label(frame_date, text="Planned Date:", font=("Arial", 12)).grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        planned_date_var = tk.StringVar()
        DateEntry(frame_date, textvariable=planned_date_var, date_pattern="yyyy-mm-dd").grid(row=0, column=1, padx=5, pady=5, sticky='ew')

    # Currency
        frame_currency = ttk.Frame(editor)
        frame_currency.pack(fill='x', padx=20, pady=5)
        ttk.Label(frame_currency, text="Currency:", font=("Arial", 12)).grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        currency_var = tk.StringVar(value="USD")
        ttk.Combobox(frame_currency, textvariable=currency_var, values=["USD", "UAH", "EUR"]).grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        frame_currency.columnconfigure(1, weight=1)

    # Action Buttons
        frame_buttons = ttk.Frame(editor)
        frame_buttons.pack(fill='x', padx=20, pady=10)
        ttk.Button(frame_buttons, text="Save", command=lambda: self.save_planned_transaction(
            editor, mode, transaction_id, trans_type_var.get(), amount_var.get(),
            category_var.get(), planned_date_var.get(), currency_var.get()
        )).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_buttons, text="Cancel", command=editor.destroy).pack(side=tk.RIGHT, padx=5)

    # Pre-fill values if editing
        if mode == "edit" and transaction_id:
            self.prefill_transaction_fields(transaction_id, trans_type_var, amount_var, category_var, planned_date_var, currency_var)

    def prefill_transaction_fields(self, transaction_id, trans_type_var, amount_var, category_var, planned_date_var, currency_var):
        """Prefill the fields with existing transaction data for editing."""
        transaction = next(
            (t for t in get_planned_transactions(self.user_id, self.is_admin) if t[0] == transaction_id), None
        )
        if transaction:
            trans_type_var.set(transaction['type'])
            amount_var.set(transaction['amount'])
            category_var.set(transaction['category'])
            planned_date_var.set(transaction['planned_date'])
            currency_var.set(transaction['currency'])

    def save_planned_transaction(self, editor, mode, transaction_id, trans_type, amount, category, planned_date, currency):
        """Handle save action for planned transactions."""
        try:
            if mode == "add":
                add_planned_transaction(self.user_id, trans_type, float(amount), category, planned_date, currency)
                messagebox.showinfo("Success", "Planned transaction added successfully!")
            elif mode == "edit":
                update_planned_transaction(transaction_id, trans_type, float(amount), category, planned_date, currency)
                messagebox.showinfo("Success", "Planned transaction updated successfully!")
            self.populate_planned_transactions()
            editor.destroy()
        except ValueError:
            messagebox.showerror("Error", "Invalid amount. Please enter a valid number.")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {e}")

    def validate_transaction_fields(self, amount, category, date, transaction_type):
        if not amount or not category or not date:
            messagebox.showwarning("Error", "All fields are required!")
            return False
        if not self.validate_amount(amount):
            messagebox.showwarning("Error", "Invalid amount format!")
            return False
        if not self.validate_date(date):
            messagebox.showwarning("Error", "Invalid date format! Use YYYY-MM-DD.")
            return False
        if transaction_type not in ["income", "expense"]:
            messagebox.showwarning("Error", "Transaction type must be 'income' or 'expense'.")
            return False
        return True

    def convert_currency(self, amount, from_currency, to_currency):
        """
        Convert an amount from one currency to another using the exchange rates.

        Args:
            amount (float): The amount to convert.
            from_currency (str): The source currency code.
            to_currency (str): The target currency code.

        Returns:
            float: The converted amount rounded to two decimal places, or None if an error occurs.
        """
        try:
            amount = float(amount)
            if amount < 0:
                raise ValueError("Amount must be a positive number.")

            from_rate = self.exchange_rates.get(from_currency)
            to_rate = self.exchange_rates.get(to_currency)

            if from_rate is None or to_rate is None:
                raise ValueError(f"Exchange rate for {from_currency} or {to_currency} not found.")

            converted_amount = (amount / from_rate) * to_rate
            return round(converted_amount, 2)
        except (ValueError, TypeError) as e:
            print(f"Conversion error: {e}")
            return None

    def get_monthly_income(self):
        """Calculate total income for the current month in USD, UAH, and EUR."""
        transactions = get_transactions(self.user_id, is_admin=self.is_admin)
        if not transactions:
            return 0.0, 0.0, 0.0

        df = pd.DataFrame(transactions)
        df['Date'] = pd.to_datetime(df['date'], errors='coerce')
        current_month = pd.Timestamp.now().month
        current_year = pd.Timestamp.now().year

        income_transactions = df[
            (df['Date'].dt.month == current_month) &
            (df['Date'].dt.year == current_year) &
            (df['type'] == 'income')
        ]

        total_income_usd = 0.0
        total_income_uah = 0.0
        total_income_eur = 0.0

        for _, row in income_transactions.iterrows():
            amount = row['amount']
            currency = row['currency']
            total_income_usd += self.convert_currency(amount, currency, "USD") or 0
            total_income_uah += self.convert_currency(amount, currency, "UAH") or 0
            total_income_eur += self.convert_currency(amount, currency, "EUR") or 0

        return round(total_income_usd, 2), round(total_income_uah, 2), round(total_income_eur, 2)

    def get_monthly_expenses(self):
        """Calculate total expenses for the current month in USD, UAH, and EUR."""
        transactions = get_transactions(self.user_id, is_admin=self.is_admin)
        if not transactions:
            return 0.0, 0.0, 0.0

        df = pd.DataFrame(transactions)
        df['Date'] = pd.to_datetime(df['date'], errors='coerce')
        current_month = pd.Timestamp.now().month
        current_year = pd.Timestamp.now().year

        expense_transactions = df[
            (df['Date'].dt.month == current_month) &
            (df['Date'].dt.year == current_year) &
            (df['type'] == 'expense')
        ]

        total_expenses_usd = 0.0
        total_expenses_uah = 0.0
        total_expenses_eur = 0.0

        for _, row in expense_transactions.iterrows():
            amount = row['amount']
            currency = row['currency']
            total_expenses_usd += self.convert_currency(amount, currency, "USD") or 0
            total_expenses_uah += self.convert_currency(amount, currency, "UAH") or 0
            total_expenses_eur += self.convert_currency(amount, currency, "EUR") or 0

        return round(total_expenses_usd, 2), round(total_expenses_uah, 2), round(total_expenses_eur, 2)

    def get_budget_usage(self):
        """Calculate the budget usage percentage for the current month."""
        income_usd, _, _ = self.get_monthly_income()
        expenses_usd, _, _ = self.get_monthly_expenses()

        if income_usd == 0:
            return 0.0  # Avoid division by zero
        return (expenses_usd / income_usd) * 100

    def define_color_schemes(self):
        """Define improved color schemes for accessibility."""
        self.color_schemes = {
            "Light": {
                "bg": "#FFFFFF",          # White background
                "fg": "#000000",          # Black text
                "button_bg": "#E0E0E0",   # Light gray for buttons
                "highlight": "#007ACC",   # Blue for highlights
                "text": "#000000",        # Black text
                "error": "#FF0000",       # Red for errors
                "success": "#008000",     # Green for success
            },
            "Dark": {
                "bg": "#121212",          # Deep black background
                "fg": "#E0E0E0",          # Light gray text
                "button_bg": "#1F1F1F",   # Slightly lighter black for buttons
                "highlight": "#BB86FC",   # Purple accent (Material Design style)
                "text": "#E0E0E0",        # Light gray text
                "error": "#CF6679",       # Material Design red for errors
                "success": "#03DAC6",     # Teal for success
            },
            "High Contrast": {
                "bg": "#000000",          # Black background
                "fg": "#FFFFFF",          # White text
                "button_bg": "#FFD700",   # Bright yellow for buttons
                "highlight": "#FF4500",   # Orange-red for highlights
                "text": "#FFFFFF",        # White text
                "error": "#FF6347",       # Tomato red for errors
                "success": "#32CD32",     # Lime green for success
            }
        }

    def setup_styles(self):
        """Apply the selected color scheme."""
        scheme = self.color_schemes[self.selected_color_scheme.get()]
        self.configure(bg=scheme["bg"])
        self.style = ttk.Style(self)
        self.style.theme_use("clam")

    # General styles
        self.style.configure(
            "TLabel",
            background=scheme["bg"],
            foreground=scheme["fg"],
            font=("Arial", 12)
        )
        self.style.configure(
            "TFrame",
            background=scheme["bg"]
        )
        self.style.configure(
            "TButton",
            background=scheme["button_bg"],
            foreground=scheme["fg"],
            font=("Arial", 12),
            borderwidth=1
        )
        self.style.map(
            "TButton",
            background=[("active", scheme["highlight"])],
            foreground=[("active", scheme["text"])]
        )
        self.style.configure(
            "Treeview",
            background=scheme["bg"],
            foreground=scheme["fg"],
            fieldbackground=scheme["bg"],
            borderwidth=1
        )
        self.style.map(
            "Treeview",
            background=[("selected", scheme["highlight"])],
            foreground=[("selected", scheme["text"])]
        )
        self.style.configure(
            "Treeview.Heading",
            background=scheme["button_bg"],
            foreground=scheme["fg"],
            font=("Arial", 12, "bold")
        )

    # Tooltip customization for the dark theme
        self.style.configure(
            "Tooltip.TLabel",
            background=scheme["highlight"],
            foreground=scheme["text"],
            font=("Arial", 10)
        )

    # Login-specific styles
        self.style.configure(
            "LoginForm.TFrame",
            background=scheme["bg"],
            relief="solid",
            bordercolor=scheme["highlight"],
            borderwidth=2,
        )
        self.style.configure(
            "LoginFormTitle.TLabel",
            font=("Arial", 20, "bold"),
            foreground=scheme["highlight"],
        )
        self.style.configure(
            "LoginFormLabel.TLabel",
            font=("Arial", 12),
            foreground=scheme["fg"]
        )
        self.style.configure(
            "LoginButton.TButton",
            background=scheme["highlight"],
            foreground=scheme["text"]
        )
        self.style.configure(
            "RegisterButton.TButton",
            background=scheme["success"],
            foreground=scheme["text"]
        )

    def create_widgets(self):
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.create_login_tab()
        self.create_main_tab()
        self.create_reports_tab()

    def create_reports_tab(self):
        """Create the enhanced Reports tab."""
        frame_reports = ttk.Frame(self.tabs['reports'])
        frame_reports.pack(fill='both', expand=True, padx=20, pady=10)

    # Report Selection Section
        report_selection_frame = ttk.LabelFrame(frame_reports, text="Report Options", padding=10)
        report_selection_frame.grid(row=0, column=0, columnspan=2, pady=10, sticky='nsew')

        ttk.Label(report_selection_frame, text="Select Report Type:", font=("Arial", 12)).grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.report_type_var = tk.StringVar(value="Bar Chart")  # Default report type
        report_types = ["Bar Chart", "Line Chart", "Histogram", "Table View", "Heatmap"]
        report_dropdown = ttk.Combobox(report_selection_frame, textvariable=self.report_type_var, values=report_types, state="readonly", font=("Arial", 12))
        report_dropdown.grid(row=0, column=1, padx=5, pady=5)
        report_dropdown.bind("<<ComboboxSelected>>", self.update_report)

    # Export Buttons
        export_frame = ttk.Frame(report_selection_frame)
        export_frame.grid(row=0, column=2, padx=10, pady=5, sticky=tk.E)
        ttk.Button(export_frame, text="Export to PDF", command=self.export_to_pdf).pack(side=tk.LEFT, padx=5)
        ttk.Button(export_frame, text="Export to Excel", command=self.export_to_excel).pack(side=tk.LEFT, padx=5)

    # Filter Section
        filter_frame = ttk.LabelFrame(frame_reports, text="Filters", padding=10)
        filter_frame.grid(row=1, column=0, columnspan=2, pady=10, sticky='nsew')

        ttk.Label(filter_frame, text="Category:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.filter_category = tk.StringVar(value="All")
        categories = ["All"] + list(set(t['category'] for t in get_transactions(self.user_id)))
        ttk.Combobox(filter_frame, textvariable=self.filter_category, values=categories, state="readonly").grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(filter_frame, text="Date Range:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.filter_start_date = DateEntry(filter_frame, date_pattern='yyyy-mm-dd')
        self.filter_start_date.grid(row=0, column=3, padx=5, pady=5)
        self.filter_end_date = DateEntry(filter_frame, date_pattern='yyyy-mm-dd')
        self.filter_end_date.grid(row=0, column=4, padx=5, pady=5)

        ttk.Button(filter_frame, text="Apply Filters", command=self.apply_filters).grid(row=0, column=5, padx=10, pady=5)

    # Report Display Area
        display_frame = ttk.LabelFrame(frame_reports, text="Report Display", padding=10)
        display_frame.grid(row=2, column=0, columnspan=2, pady=10, sticky='nsew')

        self.report_frame = ttk.Frame(display_frame)
        self.report_frame.pack(fill='both', expand=True, padx=10, pady=10)

    # Comparison Section
        comparison_frame = ttk.LabelFrame(frame_reports, text="Comparison Tools", padding=10)
        comparison_frame.grid(row=3, column=0, columnspan=2, pady=10, sticky='nsew')

        ttk.Label(comparison_frame, text="Select Comparison Type:", font=("Arial", 12)).grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.comparison_type_var = tk.StringVar(value="Monthly")
        comparison_types = ["Monthly", "Yearly"]
        comparison_dropdown = ttk.Combobox(comparison_frame, textvariable=self.comparison_type_var, values=comparison_types, state="readonly")
        comparison_dropdown.grid(row=0, column=1, padx=5, pady=5)

        ttk.Button(comparison_frame, text="Generate Comparison", command=self.generate_comparison_report).grid(row=0, column=2, padx=5, pady=5)

    # Dynamic Grid Configuration for Responsiveness
        frame_reports.grid_columnconfigure(0, weight=1)
        frame_reports.grid_columnconfigure(1, weight=1)
        frame_reports.grid_rowconfigure(2, weight=1)

    # Initialize Default Report (Bar Chart)
        self.update_report()

    def update_report(self, event=None):
        """Update the displayed report based on the selected type."""
        for widget in self.report_frame.winfo_children():
            widget.destroy()

        transactions = get_transactions(self.user_id, is_admin=self.is_admin)
        if not transactions:
            ttk.Label(self.report_frame, text="No data available to generate reports.", font=("Arial", 14)).pack(pady=20)
            return

        df = pd.DataFrame(transactions)
        df['Amount'] = pd.to_numeric(df['amount'], errors='coerce')
        df['Date'] = pd.to_datetime(df['date'], errors='coerce')

        report_type = self.report_type_var.get()
        if report_type == "Bar Chart":
            self.plot_bar_chart(df)
        elif report_type == "Line Chart":
            self.plot_line_chart(df)
        elif report_type == "Histogram":
            self.plot_histogram(df)
        elif report_type == "Table View":
            self.display_transaction_history(df)
        elif report_type == "Heatmap":
            self.plot_heatmap(df)

    def plot_bar_chart(self, df):
        """Generate a bar chart showing monthly or yearly trends."""
        fig, ax = plt.subplots(figsize=(10, 5))
        df['Month'] = df['Date'].dt.to_period('M')
        monthly_summary = df.groupby('Month')['Amount'].sum()
        monthly_summary.plot(kind='bar', ax=ax, color='skyblue')
        ax.set_title("Monthly Financial Trends")
        ax.set_xlabel("Month")
        ax.set_ylabel("Total Amount ($)")
        canvas = FigureCanvasTkAgg(fig, master=self.report_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_line_chart(self, df):
        """Generate a line chart showing financial trends over time."""
        fig, ax = plt.subplots(figsize=(10, 5))
        df.set_index('Date').resample('M')['Amount'].sum().plot(kind='line', ax=ax, color='green', marker='o')
        ax.set_title("Financial Trends Over Time")
        ax.set_xlabel("Date")
        ax.set_ylabel("Total Amount ($)")
        canvas = FigureCanvasTkAgg(fig, master=self.report_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_histogram(self, df):
        """Generate a histogram showing the distribution of transaction amounts."""
        fig, ax = plt.subplots(figsize=(10, 5))
        df['Amount'].plot(kind='hist', bins=20, ax=ax, color='orange', edgecolor='black')
        ax.set_title("Distribution of Transaction Amounts")
        ax.set_xlabel("Amount")
        ax.set_ylabel("Frequency")
        canvas = FigureCanvasTkAgg(fig, master=self.report_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_heatmap(self, df):
    # Create a pivot table with categories as rows and types (income/expense) as columns
        pivot_table = df.pivot_table(
            index='category',  # Rows: Transaction categories
            columns='type',    # Columns: Transaction types (income/expense)
            values='Amount',   # Values: Transaction amounts
            aggfunc='sum',     # Aggregation function: Sum amounts
            fill_value=0       # Fill missing values with 0
        )

    # Plot the heatmap using seaborn
        fig, ax = plt.subplots(figsize=(10, 5))
        sns.heatmap(
            pivot_table,       # Data: Pivot table
            annot=True,        # Annotate cells with numeric values
            fmt=".2f",         # Format values to 2 decimal places
            cmap="YlGnBu",     # Color map: Yellow-Green-Blue gradient
            ax=ax              # Axes to plot on
        )
        ax.set_title('Expense/Income Heatmap by Category')

    # Embed the chart in the application interface
        canvas = FigureCanvasTkAgg(fig, master=self.report_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def generate_comparison_report(self):
        """Generate an enhanced comparison report."""
        comparison_type = self.comparison_type_var.get()

    # Fetch and process transactions
        transactions = get_transactions(self.user_id, is_admin=self.is_admin)
        if not transactions:
            messagebox.showwarning("Warning", "No transactions found to generate comparisons.")
            return

        df = pd.DataFrame(transactions)
        df['Amount'] = pd.to_numeric(df['amount'], errors='coerce')
        df['Date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['Amount', 'Date'])

        if comparison_type == "Monthly":
            self.generate_monthly_comparison(df)
        elif comparison_type == "Yearly":
            self.generate_yearly_comparison(df)
        elif comparison_type == "Category Comparison":
            self.generate_category_comparison(df)

    def generate_category_comparison(self, df):
        """Generate comparison of categories over time."""
    # Group by category and month
        df['Month'] = df['Date'].dt.to_period('M')
        category_totals = df.groupby(['Month', 'category'])['Amount'].sum().unstack(fill_value=0)

    # Plot category comparison as stacked bar chart
        fig, ax = plt.subplots(figsize=(12, 6))
        category_totals.plot(kind='bar', stacked=True, ax=ax, colormap="viridis")
        ax.set_title("Category Comparison Over Time")
        ax.set_xlabel("Month")
        ax.set_ylabel("Total Amount ($)")
        ax.legend(title="Category", bbox_to_anchor=(1.05, 1), loc='upper left')

    # Add chart to the UI
        self.display_comparison_results(fig, "Category Comparison Over Time")

    def generate_monthly_comparison(self, df):
        """Generate monthly comparison report."""
        df['Month'] = df['Date'].dt.to_period('M').astype(str)
        monthly_totals = df.groupby(['Month', 'type'])['Amount'].sum().unstack(fill_value=0)

    # Calculate percentage changes
        monthly_totals['Income Change (%)'] = monthly_totals.get('income', 0).pct_change() * 100
        monthly_totals['Expense Change (%)'] = monthly_totals.get('expense', 0).pct_change() * 100

    # Plot data
        fig, ax = plt.subplots(figsize=(12, 6))
        monthly_totals[['income', 'expense']].plot(kind='bar', ax=ax, color=['green', 'red'])
        ax.set_title("Monthly Income and Expense Comparison")
        ax.set_xlabel("Month")
        ax.set_ylabel("Amount ($)")

    # Annotate percentage changes
        for i, row in monthly_totals.iterrows():
            if 'Income Change (%)' in row:
                ax.text(i, row['income'], f"{row['Income Change (%)']:.1f}%", ha='center', color='green')
            if 'Expense Change (%)' in row:
                ax.text(i, row['expense'], f"{row['Expense Change (%)']:.1f}%", ha='center', color='red')

        self.display_comparison_results(fig, "Monthly Comparison")

    def display_comparison_results(self, fig, title):
        """Display comparison results."""
        for widget in self.comparison_result_frame.winfo_children():
            widget.destroy()

        canvas = FigureCanvasTkAgg(fig, master=self.comparison_result_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_custom_report(self, df):
        """Placeholder for custom report functionality."""
        ttk.Label(self.report_frame, text="Custom Report Feature Coming Soon!", font=("Arial", 14)).pack(pady=20)

    def create_login_tab(self):
        """Create a visually appealing login tab."""
    # Clear any existing widgets
        for widget in self.main_frame.winfo_children():
            widget.destroy()

    # Frame for centering the login form
        self.login_frame = ttk.Frame(self.main_frame, padding=20)
        self.login_frame.pack(fill=tk.BOTH, expand=True)

    # Inner frame with border for the login form
        form_frame = ttk.Frame(
            self.login_frame, padding=30, relief="solid", style="LoginForm.TFrame"
        )
        form_frame.place(relx=0.5, rely=0.5, anchor="center")  # Center the form

    # Title
        ttk.Label(
            form_frame,
            text="Welcome to Waллet",
            font=("Arial", 20, "bold"),
            style="LoginFormTitle.TLabel",
        ).pack(pady=10)

    # Username dropdown
        ttk.Label(
            form_frame, text="Username:", font=("Arial", 12), style="LoginFormLabel.TLabel"
        ).pack(anchor="w", pady=5)
        users_data = get_users()
        usernames = [user["username"] for user in users_data]
        self.combo_users = ttk.Combobox(
            form_frame, values=usernames, state="readonly", font=("Arial", 12)
        )
        self.combo_users.pack(fill=tk.X, padx=10, pady=5)

    # Password field
        ttk.Label(
            form_frame, text="Password:", font=("Arial", 12), style="LoginFormLabel.TLabel"
        ).pack(anchor="w", pady=5)
        self.entry_password = ttk.Entry(form_frame, show="*", font=("Arial", 12))
        self.entry_password.pack(fill=tk.X, padx=10, pady=5)

    # Secret key selector
        ttk.Button(form_frame, text="Select Secret Key", command=self.select_secret_key).pack(
            pady=5
        )
        self.secret_key_path_var = tk.StringVar(value="No key selected")
        ttk.Label(
            form_frame,
            textvariable=self.secret_key_path_var,
            font=("Arial", 10),
            foreground="gray",
        ).pack()

    # Login button
        ttk.Button(
            form_frame, text="Login", command=self.login, style="LoginButton.TButton"
        ).pack(fill=tk.X, padx=10, pady=10)

    # Register button
        ttk.Button(
            form_frame,
            text="Register New User",
            command=self.open_registration_window,
            style="RegisterButton.TButton",
        ).pack(fill=tk.X, padx=10, pady=5)

    # Apply color scheme
        self.apply_color_scheme()

    def select_secret_key(self):
        secret_key_file = filedialog.askopenfilename(
            title="Select Your Secret Key File", 
            filetypes=[("Key files", "*.key")]
        )
        if secret_key_file and os.path.exists(secret_key_file):
            self.secret_key_path_var.set(secret_key_file)
            print(f"Secret key file selected: {secret_key_file}")
        else:
            self.secret_key_path_var.set("No key selected")
            messagebox.showwarning("Warning", "Invalid or no file selected.")

    def login(self):
        username = self.combo_users.get()
        password = self.entry_password.get()
        secret_key_file = self.secret_key_path_var.get()

        if not username or not password or secret_key_file == "No key selected":
            messagebox.showerror("Error", "Please fill in all fields and select your secret key file.")
            return

    # Verify if the secret key file exists
        if not os.path.exists(secret_key_file):
            messagebox.showerror("Error", "Selected secret key file does not exist.")
            return

    # Read the secret key from the file
        try:
            with open(secret_key_file, 'r') as file:
                secret_key = file.read().strip()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read the secret key file: {e}")
            return

        print(f"Attempting login with Username: {username}, Secret Key: {secret_key}")

    # Verify user credentials
        self.user_id, is_admin = verify_user(username, password, secret_key)

        if self.user_id:
            print(f"Login successful for user_id: {self.user_id}")
            self.handle_successful_login(self.user_id, is_admin)  # Pass the required arguments
        else:
            messagebox.showerror("Error", "Invalid username, password, or secret key.")

    def handle_successful_login(self):
        print(f"Login successful for user_id: {self.user_id}")
        self.is_admin = self.is_admin  # Set admin status
        self.login_frame.pack_forget()
        self.create_main_tab()  # Recreate main tabs based on user role
        self.main_tab_frame.pack(fill=tk.BOTH, expand=True)
        self.populate_transactions()
        self.calculate_balance()

    def register(self):
        username = self.entry_username.get()
        password = self.entry_password_reg.get()
        password_confirm = self.entry_password_confirm.get()

        if not username or not password or not password_confirm:
            messagebox.showerror("Error", "All fields are required for registration.")
            return

        if password != password_confirm:
            messagebox.showerror("Error", "Passwords do not match.")
            return

    # Add user and handle the result
        if add_user(username, password):
            messagebox.showinfo("Success", "User registered successfully.")
            self.registration_window.destroy()
        else:
            messagebox.showerror("Error", "User already exists.")

    def open_registration_window(self):
        self.registration_window = tk.Toplevel(self)
        self.registration_window.title("Register")
        self.registration_window.geometry("300x250")
        self.create_registration_widgets(self.registration_window)

    def create_registration_widgets(self, window):
        ttk.Label(window, text="Username:").pack(pady=5)
        self.entry_username = ttk.Entry(window)
        self.entry_username.pack(pady=5)
        ttk.Label(window, text="Password:").pack(pady=5)
        self.entry_password_reg = ttk.Entry(window, show="*")
        self.entry_password_reg.pack(pady=5)
        ttk.Label(window, text="Confirm Password:").pack(pady=5)
        self.entry_password_confirm = ttk.Entry(window, show="*")
        self.entry_password_confirm.pack(pady=5)
        ttk.Button(window, text="Register", command=self.register_user).pack(pady=5)

    def register_user(self):
        username = self.entry_username.get()
        password = self.entry_password_reg.get()
        password_confirm = self.entry_password_confirm.get()

        if password != password_confirm:
            messagebox.showerror("Error", "Passwords do not match")
            return

    # Generate and save the secret key
        secret_key, file_path = generate_and_save_secret_key(username)

        if add_user(username, password, secret_key):  # Pass secret_key as the third argument
            download_dir = filedialog.asksaveasfilename(
                defaultextension=".key",
                initialfile=f"{username}_secret.key",
                title="Save Secret Key As",
                filetypes=[("Key files", "*.key")],
            )
            if download_dir:
                shutil.copy(file_path, download_dir)
                messagebox.showinfo("Success", f"User registered successfully. Secret key saved to {download_dir}")
            else:
                messagebox.showwarning("Registration", "User registered, but the secret key file was not saved.")

        # Refresh the dropdown to include the new user
            self.refresh_user_data()
        
            self.registration_window.destroy()
        else:
            messagebox.showerror("Error", "Username is already taken")

    def refresh_user_data(self):
        """Reload user data from the database and update the dropdown menu."""
        try:
        # Fetch updated user data from the database
            users_data = get_users()  # Ensure this function works as expected
            usernames = [user["username"] for user in users_data]
        
        # Debug: Print the list of usernames
            print("Updated user list:", usernames)

        # Update the login dropdown
            if hasattr(self, 'combo_users'):
                self.combo_users['values'] = usernames
                print("Login dropdown updated with new user list.")
        except Exception as e:
            print(f"Error refreshing user data: {e}")

    def handle_successful_login(self):
        print(f"Login successful for user_id: {self.user_id}")
        self.login_frame.pack_forget()
        self.main_tab_frame.pack(fill=tk.BOTH, expand=True)
        self.populate_transactions()
        self.calculate_balance()

    def verify_user(username, password):
        """Verify user credentials and check if the user is an admin."""
        conn, c = get_db_connection()
        try:
            c.execute('SELECT id, password, is_admin FROM users WHERE username = ?', (username,))
            user = c.fetchone()
            if user and bcrypt.checkpw(password.encode(), user[1]):
                return user[0], bool(user[2])  # Return user ID and is_admin status
            return None, False
        finally:
            conn.close()

    def handle_successful_login(self, user_id, is_admin):
        self.user_id = user_id
        self.is_admin = is_admin

        self.login_frame.pack_forget()
        self.create_main_tab()  # Recreate tabs based on user role
        self.main_tab_frame.pack(fill=tk.BOTH, expand=True)

    # Populate transactions for the user
        self.populate_transactions()
        self.calculate_balance()

        if self.is_admin:
            print("Logged in as admin.")
        else:
            print("Logged in as a regular user.")

    def create_main_tab(self):
        self.main_tab_frame = ttk.Frame(self.main_frame)
        self.notebook = ttk.Notebook(self.main_tab_frame)
        self.notebook.pack(expand=True, fill='both')

    # Add common tabs
        self.tabs = {
            'dashboard': ttk.Frame(self.notebook),
            'reports': ttk.Frame(self.notebook),
            'settings': ttk.Frame(self.notebook)
        }
        self.notebook.add(self.tabs['dashboard'], text='Dashboard')
        self.notebook.add(self.tabs['reports'], text='Reports')
        self.notebook.add(self.tabs['settings'], text='Settings')

        self.create_dashboard_tab()
        self.create_reports_tab()
        self.create_settings_tab()

    # Add Admin Tab if user is admin
        if self.is_admin:
            self.create_admin_tab()

        self.main_tab_frame.pack_forget()

    def create_currency_tools(self, parent):
        """Create a unified Currency Tools section."""
        currency_tools_frame = ttk.LabelFrame(parent, text="Currency Tools", padding=10)
        currency_tools_frame.pack(fill='both', expand=True, padx=10, pady=10)

    # Right Side: Currency Converter
        converter_frame = ttk.Frame(currency_tools_frame)
        converter_frame.pack(side='right', fill='both', expand=True, padx=5, pady=5)

        ttk.Label(converter_frame, text="Amount:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.amount_var = tk.StringVar()
        self.amount_var.trace("w", self.dynamic_conversion)
        ttk.Entry(converter_frame, textvariable=self.amount_var).grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(converter_frame, text="From:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.from_currency_var = tk.StringVar(value="USD")
        from_currency_dropdown = ttk.Combobox(
            converter_frame, textvariable=self.from_currency_var, values=list(self.exchange_rates.keys()), state="readonly"
        )
        from_currency_dropdown.grid(row=1, column=1, padx=5, pady=5)
        from_currency_dropdown.bind("<<ComboboxSelected>>", self.dynamic_conversion)

        ttk.Label(converter_frame, text="To:").grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        self.to_currency_var = tk.StringVar(value="UAH")
        to_currency_dropdown = ttk.Combobox(
            converter_frame, textvariable=self.to_currency_var, values=list(self.exchange_rates.keys()), state="readonly"
        )
        to_currency_dropdown.grid(row=2, column=1, padx=5, pady=5)
        to_currency_dropdown.bind("<<ComboboxSelected>>", self.dynamic_conversion)

        ttk.Label(converter_frame, text="Result:").grid(row=3, column=0, padx=5, pady=5, sticky=tk.W)
        self.conversion_result_var = tk.StringVar(value="Result: 0.00")
        ttk.Label(converter_frame, textvariable=self.conversion_result_var, font=("Arial", 12, "bold")).grid(
            row=3, column=1, padx=5, pady=5, sticky=tk.W
        )

    def dynamic_conversion(self, *args):
        """Dynamically convert currencies based on user input."""
        try:
            amount = self.amount_var.get()
            from_currency = self.from_currency_var.get()
            to_currency = self.to_currency_var.get()

            result = self.convert_currency(amount, from_currency, to_currency)

            if result is not None:
                self.conversion_result_var.set(f"Result: {result:.2f} {to_currency}")
            else:
                self.conversion_result_var.set("Result: Conversion Error")
        except Exception as e:
            print(f"Error in dynamic conversion: {e}")
            self.conversion_result_var.set("Result: Invalid Input")

    def calculate_balance(self):
        """
        Calculate and display the balance for each currency, including conversions to USD, UAH, and EUR.
        """
        if self.user_id is None:
            return  # Skip calculation if no user is logged in

    # Fetch transactions for the logged-in user or admin
        transactions = get_transactions(self.user_id, is_admin=self.is_admin)
        if not transactions:
            self.balance_var.set("No transactions available.")
            return

    # Group balances by currency
        balance_by_currency = {}
        for transaction in transactions:
            try:
                amount = float(transaction['amount'])
                currency = transaction['currency']
                if transaction['type'] == 'income':
                    balance_by_currency[currency] = balance_by_currency.get(currency, 0) + amount
                elif transaction['type'] == 'expense':
                    balance_by_currency[currency] = balance_by_currency.get(currency, 0) - amount
            except (ValueError, KeyError):
                print(f"Invalid transaction data: {transaction}")

    # Prepare balances in USD, UAH, and EUR
        total_balance_usd = sum(
            self.convert_currency(balance, currency, "USD") or 0
            for currency, balance in balance_by_currency.items()
        )
        total_balance_uah = sum(
            self.convert_currency(balance, currency, "UAH") or 0
            for currency, balance in balance_by_currency.items()
        )
        total_balance_eur = sum(
            self.convert_currency(balance, currency, "EUR") or 0
            for currency, balance in balance_by_currency.items()
        )

    # Update the display with balances in multiple currencies
        balances = [
            f"{currency}: {balance:.2f}"
            for currency, balance in balance_by_currency.items()
        ]
        balances.append(f"USD: {total_balance_usd:.2f}")
        balances.append(f"UAH: {total_balance_uah:.2f}")
        balances.append(f"EUR: {total_balance_eur:.2f}")
        self.balance_var.set(" | ".join(balances))

    # Notify user if total balance in USD falls below the threshold
        self.check_balance_notification(total_balance_usd)

    def create_currency_converter(self, parent):
        converter_frame = ttk.LabelFrame(parent, text="Currency Converter", padding=10)
        converter_frame.grid(row=3, column=0, padx=20, pady=10, sticky='nsew')

        ttk.Label(converter_frame, text="Amount:").grid(row=0, column=0, padx=5, pady=5)
        self.amount_var = tk.StringVar()
        ttk.Entry(converter_frame, textvariable=self.amount_var).grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(converter_frame, text="From:").grid(row=1, column=0, padx=5, pady=5)
        self.from_currency_var = tk.StringVar(value="USD")
        currency_options = list(self.exchange_rates.keys())
        ttk.Combobox(converter_frame, textvariable=self.from_currency_var, values=currency_options).grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(converter_frame, text="To:").grid(row=2, column=0, padx=5, pady=5)
        self.to_currency_var = tk.StringVar(value="UAH")
        ttk.Combobox(converter_frame, textvariable=self.to_currency_var, values=currency_options).grid(row=2, column=1, padx=5, pady=5)

        ttk.Button(converter_frame, text="Convert", command=self.convert_currency).grid(row=3, column=0, columnspan=2, pady=10)

        self.conversion_result_var = tk.StringVar(value="Result:")
        ttk.Label(converter_frame, textvariable=self.conversion_result_var, font=("Arial", 12, "bold")).grid(row=4, column=0, columnspan=2, pady=10)

    def create_transaction_buttons(self, parent):
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=5, column=0, columnspan=3, pady=10)

        ttk.Button(button_frame, text="Add Transaction", command=self.add_transaction).grid(row=0, column=0, padx=5)
        ttk.Button(button_frame, text="Update Transaction", command=self.update_transaction).grid(row=0, column=1, padx=5)
        ttk.Button(button_frame, text="Delete Transaction", command=self.delete_transaction).grid(row=0, column=2, padx=5)

    def create_transactions_treeview(self, parent):
        self.tree_transactions = ttk.Treeview(parent, columns=("ID", "Type", "Amount", "Category", "Date", "Currency"), show="headings")
        for col in self.tree_transactions["columns"]:
            self.tree_transactions.heading(col, text=col)
            self.tree_transactions.column(col, width=100)
        self.tree_transactions.pack(fill=tk.BOTH, expand=True)


    def create_tooltips(self):
        ToolTip(self.entry_amount, "Enter the amount of the transaction")
        ToolTip(self.entry_category, "Enter the category of the transaction")
        ToolTip(self.entry_date, "Select the date of the transaction")
        ToolTip(self.currency_menu, "Select the currency of the transaction")
        ToolTip(self.listbox_exchange_rates, "Displays current exchange rates")

    def create_dashboard_tab(self):
        frame_dashboard = ttk.Frame(self.tabs['dashboard'])
        frame_dashboard.pack(fill='both', expand=True, padx=20, pady=10)

    # Dashboard Title
        title_frame = ttk.Frame(frame_dashboard)
        title_frame.grid(row=0, column=0, columnspan=2, pady=10, sticky='nsew')
        ttk.Label(
            title_frame,
            text="Welcome to Your Financial Dashboard",
            font=("Helvetica", 20, "bold"),
            anchor="center"
        ).pack(pady=10)

    # Key Indicators Frame
        frame_key_indicators = ttk.LabelFrame(
            frame_dashboard, text="Key Indicators",
            padding=10, style="Accent.TLabelframe"
        )
        frame_key_indicators.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky='nsew')

# Balance in multiple currencies
        ttk.Label(
            frame_key_indicators, textvariable=self.balance_var,
            font=("Helvetica", 14, "bold")
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, padx=5)

# Monthly indicators
        try:
            monthly_income_usd, monthly_income_uah, monthly_income_eur = self.get_monthly_income()
            monthly_expenses_usd, monthly_expenses_uah, monthly_expenses_eur = self.get_monthly_expenses()
            budget_usage = self.get_budget_usage()
        except KeyError as e:
            print(f"Error calculating indicators: {e}")
            monthly_income_usd = monthly_income_uah = monthly_income_eur = 0.0
            monthly_expenses_usd = monthly_expenses_uah = monthly_expenses_eur = 0.0
            budget_usage = 0.0

# Display Monthly Income
        ttk.Label(
            frame_key_indicators, text=f"Monthly Income: ${monthly_income_usd:.2f} | ₴{monthly_income_uah:.2f} | €{monthly_income_eur:.2f}",
            font=("Helvetica", 12)
        ).grid(row=1, column=0, columnspan=3, sticky=tk.W, padx=5)

# Display Monthly Expenses
        ttk.Label(
            frame_key_indicators, text=f"Monthly Expenses: ${monthly_expenses_usd:.2f} | ₴{monthly_expenses_uah:.2f} | €{monthly_expenses_eur:.2f}",
            font=("Helvetica", 12)
        ).grid(row=2, column=0, columnspan=3, sticky=tk.W, padx=5)

# Display Budget Usage
        ttk.Label(
            frame_key_indicators, text=f"Budget Used: {budget_usage:.2f}%",
            font=("Helvetica", 12)
        ).grid(row=3, column=0, columnspan=3, sticky=tk.W, padx=5)

    # Transaction Details Frame
        frame_transactions = ttk.LabelFrame(
            frame_dashboard, text="Transaction Details",
            padding=10, style="Accent.TLabelframe"
        )
        frame_transactions.grid(row=1, column=0, padx=10, pady=10, sticky='nsew')

    # Transaction Form
        self.trans_type = tk.StringVar(value="expense")
        ttk.Label(frame_transactions, text="Transaction Type:", font=("Helvetica", 12)).grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Radiobutton(frame_transactions, text="Expense", variable=self.trans_type, value="expense").grid(row=0, column=1, sticky=tk.W)
        ttk.Radiobutton(frame_transactions, text="Income", variable=self.trans_type, value="income").grid(row=0, column=2, sticky=tk.W)

        self.entry_amount = self.create_labeled_entry(frame_transactions, "Amount:", 1, ttk.Entry, font=("Helvetica", 12))
        self.entry_category = self.create_labeled_entry(frame_transactions, "Category:", 2, ttk.Entry, font=("Helvetica", 12))
        self.entry_date = self.create_labeled_entry(frame_transactions, "Date (YYYY-MM-DD):", 3, DateEntry, font=("Helvetica", 12), date_pattern='yyyy-mm-dd')

        self.currency = tk.StringVar(value="USD")
        self.currency_menu = self.create_labeled_entry(
            frame_transactions, "Currency:", 4, ttk.Combobox,
            textvariable=self.currency, values=["USD", "UAH", "EUR"], font=("Helvetica", 12)
        )

    # Transaction Buttons with Icons
        ttk.Button(frame_transactions, text="➕ Add Transaction", command=self.add_transaction).grid(row=5, column=0, pady=10, padx=5)
        ttk.Button(frame_transactions, text="✏️ Update Transaction", command=self.update_transaction).grid(row=5, column=1, pady=10, padx=5)
        ttk.Button(frame_transactions, text="🗑️ Delete Transaction", command=self.delete_transaction).grid(row=5, column=2, pady=10, padx=5)

    # Transactions Table
        self.tree_transactions = ttk.Treeview(
            frame_transactions,
            columns=("ID", "Type", "Amount", "Category", "Date", "Currency"),
            show="headings",
            style="Treeview"
        )
        for col in self.tree_transactions["columns"]:
            self.tree_transactions.heading(col, text=col, anchor="center")
            self.tree_transactions.column(col, width=100, anchor=tk.CENTER)
        self.tree_transactions.grid(row=6, column=0, columnspan=3, padx=10, pady=10, sticky='nsew')
        self.tree_transactions.bind("<Double-1>", self.on_transaction_select)

    # Currency Converter Frame
        frame_currency_converter = ttk.LabelFrame(frame_dashboard, text="Currency Converter", padding=10)
        frame_currency_converter.grid(row=2, column=0, padx=10, pady=10, sticky='nsew')

    # Amount Entry
        ttk.Label(frame_currency_converter, text="Amount:", font=("Helvetica", 12)).grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.amount_var = tk.StringVar()
        self.amount_var.trace("w", self.dynamic_conversion)
        ttk.Entry(frame_currency_converter, textvariable=self.amount_var, font=("Helvetica", 12)).grid(row=0, column=1, padx=5, pady=5)

    # From Currency Dropdown
        ttk.Label(frame_currency_converter, text="From:", font=("Helvetica", 12)).grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.from_currency_var = tk.StringVar(value="USD")
        self.from_currency_dropdown = ttk.Combobox(
            frame_currency_converter,
            textvariable=self.from_currency_var,
            values=list(self.exchange_rates.keys()),
            state="readonly", font=("Helvetica", 12)
        )
        self.from_currency_dropdown.grid(row=1, column=1, padx=5, pady=5)
        self.from_currency_dropdown.bind("<<ComboboxSelected>>", self.dynamic_conversion)

    # To Currency Dropdown
        ttk.Label(frame_currency_converter, text="To:", font=("Helvetica", 12)).grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        self.to_currency_var = tk.StringVar(value="UAH")
        self.to_currency_dropdown = ttk.Combobox(
            frame_currency_converter,
            textvariable=self.to_currency_var,
            values=list(self.exchange_rates.keys()),
            state="readonly", font=("Helvetica", 12)
        )
        self.to_currency_dropdown.grid(row=2, column=1, padx=5, pady=5)
        self.to_currency_dropdown.bind("<<ComboboxSelected>>", self.dynamic_conversion)

    # Conversion Result
        ttk.Label(frame_currency_converter, text="Result:", font=("Helvetica", 12)).grid(row=3, column=0, padx=5, pady=5, sticky=tk.W)
        self.conversion_result_var = tk.StringVar(value="Result: 0.00")
        ttk.Label(frame_currency_converter, textvariable=self.conversion_result_var, font=("Helvetica", 12, "bold")).grid(
            row=3, column=1, padx=5, pady=5, sticky=tk.W
        )

    # Dynamic Tooltips
        ToolTip(self.from_currency_dropdown, "Select the currency to convert from.")
        ToolTip(self.to_currency_dropdown, "Select the currency to convert to.")
        ToolTip(self.entry_amount, "Enter the amount of the transaction.")

    # Add Planned Transactions section
        frame_planned = ttk.LabelFrame(frame_dashboard, text="Planned Transactions", padding=10)
        frame_planned.grid(row=1, column=1, padx=10, pady=10, sticky='nsew')

        self.tree_planned_transactions = ttk.Treeview(
            frame_planned,
            columns=("ID", "Type", "Amount", "Category", "Planned Date", "Currency"),
            show="headings",
        )
        for col in self.tree_planned_transactions["columns"]:
            self.tree_planned_transactions.heading(col, text=col)
            self.tree_planned_transactions.column(col, width=100)

        self.tree_planned_transactions.pack(fill=tk.BOTH, expand=True)

    # Buttons for Planned Transactions
        button_frame = ttk.Frame(frame_planned)
        button_frame.pack(fill='x', pady=5)

# Add Planned Transaction Button
        ttk.Button(button_frame, text="Add Planned Transaction", command=self.add_planned_transaction).pack(side=tk.LEFT, padx=5)

# Edit Planned Transaction Button
        ttk.Button(button_frame, text="Edit Selected", command=self.edit_selected_planned_transaction).pack(side=tk.LEFT, padx=5)

# Delete Planned Transaction Button
        ttk.Button(button_frame, text="Delete Selected", command=self.delete_selected_planned_transaction).pack(side=tk.LEFT, padx=5)

    # Populate the data
        self.populate_planned_transactions()

    def create_labeled_entry(self, parent, label_text, row, widget_type, **widget_options):
        label = ttk.Label(parent, text=label_text)    
        label.grid(row=row, column=0, sticky=tk.W, padx=10, pady=5)
        entry = widget_type(parent, **widget_options)    
        entry.grid(row=row, column=1, padx=10, pady=5, sticky='ew')
        parent.columnconfigure(1, weight=1)  # Allow the entry to expand with the window    return entry

    def create_filter_options(self, parent):
        filter_frame = ttk.LabelFrame(parent, text="Filter Options", padding=10)
        filter_frame.pack(fill='x', padx=10, pady=10)
        ttk.Label(filter_frame, text="Category:").grid(row=0, column=0, padx=5, pady=5)
        self.filter_category = tk.StringVar(value="All")
        categories = ["All"] + list(set(t['category'] for t in get_transactions(self.user_id)))
        ttk.Combobox(filter_frame, textvariable=self.filter_category, values=categories).grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(filter_frame, text="Date Range:").grid(row=0, column=2, padx=5, pady=5)
        self.filter_start_date = DateEntry(filter_frame, date_pattern='yyyy-mm-dd')
        self.filter_start_date.grid(row=0, column=3, padx=5, pady=5)
        self.filter_end_date = DateEntry(filter_frame, date_pattern='yyyy-mm-dd')
        self.filter_end_date.grid(row=0, column=4, padx=5, pady=5)
        ttk.Button(filter_frame, text="Apply Filters", command=self.apply_filters).grid(row=0, column=5, padx=5, pady=5)

    def generate_report(self):
        transactions = get_transactions(self.user_id)
        if not transactions:
            messagebox.showwarning("Warning", "No transactions found to generate the report.")
            return

        df = pd.DataFrame(transactions)
    # Process DataFrame: Ensure numeric amounts and valid dates
        df['Amount'] = pd.to_numeric(df['amount'], errors='coerce')
        df['Date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['Amount', 'Date'])

    # Generate and display summary or detailed reports based on user selection
        report_type = self.report_type_var.get()
        if report_type == "Overview":
            summary = df.groupby('category')['Amount'].sum().reset_index()
            print(summary)  # Replace with visualizations or GUI integration
        elif report_type == "Income vs Expenses":
            self.plot_income_vs_expenses(df)
        elif report_type == "Category Trends":
            self.plot_category_trends(df)

    def apply_filters(self):
        """Apply filters to the transactions and update the report."""
        try:
            transactions = get_transactions(self.user_id, is_admin=self.is_admin)
            if not transactions:
                self.update_report_message("No transactions found for the selected filters.")
                return

        # Convert transactions to DataFrame
            df = pd.DataFrame(transactions)

        # Ensure valid data types
            df['Date'] = pd.to_datetime(df['date'], errors='coerce')
            df['Amount'] = pd.to_numeric(df['amount'], errors='coerce')
            df = df.dropna(subset=['Date', 'Amount'])  # Drop rows with invalid dates or amounts

        # Apply category filter
            category_filter = self.filter_category.get()
            if category_filter != "All":
                df = df[df['category'] == category_filter]

        # Apply date range filter
            start_date = pd.to_datetime(self.filter_start_date.get())
            end_date = pd.to_datetime(self.filter_end_date.get())
            df = df[(df['Date'] >= start_date) & (df['Date'] <= end_date)]

        # Show filter summary
            self.display_filter_summary(category_filter, start_date, end_date)

        # Update the report area with filtered data
            if df.empty:
                self.update_report_message("No data found for the applied filters.")
            else:
                self.update_report_with_filtered_data(df)

        except Exception as e:
            print(f"Error applying filters: {e}")
            self.update_report_message("Error applying filters. Please check your inputs.")

    def display_filter_summary(self, category, start_date, end_date):
        """Display the summary of applied filters."""
        summary_text = f"Filters Applied: Category: {category}, Date Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
        self.filter_summary_var.set(summary_text)

    def update_report_message(self, message):
        """Update the report area with a message."""
        for widget in self.report_frame.winfo_children():
            widget.destroy()
        ttk.Label(self.report_frame, text=message, font=("Arial", 14)).pack(pady=20)

    def update_report_with_filtered_data(self, df):
        """Update the report area with filtered data."""
        for widget in self.report_frame.winfo_children():
            widget.destroy()

    # Create a scrollable frame for large datasets
        canvas = tk.Canvas(self.report_frame)
        scrollbar = ttk.Scrollbar(self.report_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    # Display filtered data
        for index, row in df.iterrows():
            ttk.Label(scrollable_frame, text=f"{row['Date'].strftime('%Y-%m-%d')} - {row['category']} - {row['Amount']} {row['currency']}", font=("Arial", 12)).pack(anchor="w", padx=10, pady=2)  

    def plot_financial_data(self, event=None):
    # Ensure a user is logged in before attempting to plot
        if self.user_id is None:
            print("No user logged in. Skipping plot generation.")
            return

    # Fetch transactions for the admin or the user
        transactions = get_transactions(self.user_id, is_admin=self.is_admin)
        if not transactions:
            messagebox.showwarning("Warning", "No transactions found to plot.")
            return

    # Create a DataFrame and process data
        df = pd.DataFrame(transactions)

    # Debugging: Print DataFrame to identify issues
        print("Transactions DataFrame:", df)

    # Ensure 'amount' column contains only numeric values
        try:
            df['Amount'] = pd.to_numeric(df['amount'], errors='coerce')  # Convert non-numeric to NaN
            df = df.dropna(subset=['Amount'])  # Drop rows with NaN in the 'Amount' column
        except KeyError:
            messagebox.showerror("Error", "Data is missing the 'amount' field.")
            return

    # Debugging: Print cleaned DataFrame
        print("Cleaned DataFrame for plotting:", df)

    # Plot based on the selected plot type
        if self.plot_type.get() == "Line Chart":
            self.plot_line_chart(df)
        elif self.plot_type.get() == "Histogram":
            self.plot_histogram(df)
        elif self.plot_type.get() == "Heatmap":
            self.plot_heatmap(df)
        else:
            self.plot_pie_or_bar_chart(df)

    def plot_pie_or_bar_chart(self, df):
        expenses = df[df['type'] == 'expense']
        income = df[df['type'] == 'income']
        exp_sums = expenses.groupby('category')['Amount'].sum()
        inc_sums = income.groupby('category')['Amount'].sum()
        fig, ax = plt.subplots(1, 2, figsize=(12, 6))
        if self.plot_type.get() == "Pie Chart":
            exp_sums.plot(kind='pie', ax=ax[0], autopct='%1.1f%%')
            ax[0].set_title('Expenses by Category')
            inc_sums.plot(kind='pie', ax=ax[1], autopct='%1.1f%%')
            ax[1].set_title('Income by Category')
            for a in ax:
                a.set_ylabel('')
        elif self.plot_type.get() == "Bar Chart":
            exp_sums.plot(kind='bar', ax=ax[0])
            ax[0].set_title('Expenses by Category')
            ax[0].set_ylabel('Amount')
            inc_sums.plot(kind='bar', ax=ax[1])
            ax[1].set_title('Income by Category')
            ax[1].set_ylabel('Amount')
        canvas = FigureCanvasTkAgg(fig, master=self.report_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_line_chart(self, df):
        fig, ax = plt.subplots(figsize=(10, 5))
        df.groupby('date')['Amount'].sum().plot(ax=ax, kind='line')
        ax.set_title('Trends Over Time')
        ax.set_ylabel('Amount')
        canvas = FigureCanvasTkAgg(fig, master=self.report_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_histogram(self, df):
        fig, ax = plt.subplots(figsize=(10, 5))
        df['Amount'].plot(ax=ax, kind='hist', bins=20)
        ax.set_title('Distribution of Amounts')
        ax.set_xlabel('Amount')
        canvas = FigureCanvasTkAgg(fig, master=self.report_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_heatmap(self, df):
        pivot_table = df.pivot_table(index='category', columns='type', values='Amount', aggfunc='sum', fill_value=0)
        fig, ax = plt.subplots(figsize=(10, 5))
        sns.heatmap(pivot_table, annot=True, fmt=".2f", cmap="YlGnBu", ax=ax)
        ax.set_title('Expense/Income Heatmap by Category')
        canvas = FigureCanvasTkAgg(fig, master=self.report_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def create_admin_tab(self):
        """Create an admin-specific tab for managing the system."""
        if 'admin' not in self.tabs:
            self.tabs['admin'] = ttk.Frame(self.notebook)
            self.notebook.add(self.tabs['admin'], text='Admin Panel')

        frame_admin = ttk.Frame(self.tabs['admin'])
        frame_admin.grid(row=0, column=0, sticky='nsew', padx=20, pady=10)

    # User Management Section
        user_frame = ttk.LabelFrame(frame_admin, text="User Management", padding=10)
        user_frame.grid(row=0, column=0, sticky='nsew', padx=10, pady=10)

    # Treeview and scrollbar
        ttk.Label(user_frame, text="Manage Users:").grid(row=0, column=0, columnspan=4, sticky=tk.W, pady=5)

        self.tree_users = ttk.Treeview(
            user_frame,
            columns=("ID", "Username", "Admin Status"),
            show="headings",
            selectmode="browse"
        )
        for col in ("ID", "Username", "Admin Status"):
            self.tree_users.heading(col, text=col)
            self.tree_users.column(col, width=150)

        self.tree_users.grid(row=1, column=0, columnspan=3, sticky='nsew', padx=5, pady=5)

        user_scrollbar = ttk.Scrollbar(user_frame, orient=tk.VERTICAL, command=self.tree_users.yview)
        self.tree_users.configure(yscrollcommand=user_scrollbar.set)
        user_scrollbar.grid(row=1, column=3, sticky='ns')

    # Buttons for user actions
        ttk.Button(user_frame, text="Delete Selected User", command=self.delete_selected_users).grid(row=2, column=0, pady=5, padx=5)
        ttk.Button(user_frame, text="Promote to Admin", command=self.promote_user_to_admin).grid(row=2, column=1, pady=5, padx=5)
        ttk.Button(user_frame, text="Demote from Admin", command=self.demote_user_from_admin).grid(row=2, column=2, pady=5, padx=5)
        ttk.Button(user_frame, text="Regenerate Secret Key", command=self.regenerate_secret_key).grid(row=2, column=3, pady=5, padx=5)

    # System Settings Section
        settings_frame = ttk.LabelFrame(frame_admin, text="System Settings", padding=10)
        settings_frame.grid(row=1, column=0, sticky='nsew', padx=10, pady=10)

        ttk.Button(settings_frame, text="Backup Database", command=backup_database).grid(row=0, column=0, pady=5, padx=5)
        ttk.Button(settings_frame, text="Restore Database", command=restore_database).grid(row=0, column=1, pady=5, padx=5)

    # Logout button
        ttk.Button(frame_admin, text="Logout", command=self.logout_admin).grid(row=2, column=0, sticky=tk.E, pady=10, padx=10)

    # Ensure frame_admin resizes properly
        frame_admin.rowconfigure(0, weight=1)
        frame_admin.columnconfigure(0, weight=1)

    def regenerate_secret_key(self):
        """Allow admin to regenerate a secret key for a selected user."""
        selected_items = self.tree_users.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "No user selected!")
            return

        try:
            user_id = self.tree_users.item(selected_items[0], "values")[0]
            username = self.tree_users.item(selected_items[0], "values")[1]

        # Verify admin privileges
            if not self.is_admin:
                raise PermissionError("Only admins can regenerate secret keys.")

        # Generate a new secret key
            secret_key, file_path = generate_and_save_secret_key(username, self.user_id, self.is_admin)

        # Update the secret key in the database
            conn, c = get_db_connection()
            c.execute('UPDATE users SET secret_key = ? WHERE id = ?', (secret_key, user_id))
            conn.commit()
            conn.close()

            messagebox.showinfo("Success", f"Secret key for {username} regenerated and saved at {file_path}.")
        except PermissionError as e:
            messagebox.showerror("Permission Denied", str(e))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to regenerate secret key: {e}")

    def logout_admin(self):
        """Log out the admin and navigate back to the login screen."""
        self.user_id = None
        self.is_admin = False

    # Clear the main frame
        for widget in self.main_frame.winfo_children():
            widget.destroy()

    # Show the login tab
        self.create_login_tab()
        self.login_frame.pack(fill=tk.BOTH, expand=True)

    def confirm_delete_all_users(self):
        """Confirm and delete all users."""
        if messagebox.askyesno("Confirm", "Are you sure you want to delete all users? This action cannot be undone."):
            delete_all_users()
            messagebox.showinfo("Success", "All users have been deleted.")
            self.refresh_users()

    def refresh_users(self):
        """Refresh the list of users in the Treeview."""
        try:
            for row in self.user_tree.get_children():
                self.user_tree.delete(row)

            users = get_users()
            for user in users:
                is_admin = user.get('is_admin', 0)  # Default to 0 if not present
                self.user_tree.insert('', 'end', values=(user['id'], user['username'], "Yes" if is_admin else "No"))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refresh user list: {e}")

    def search_users(self):
        """Search for users based on the search query."""
        query = self.user_search_var.get().lower()
        for row in self.user_tree.get_children():
            self.user_tree.delete(row)

        users = get_users()
        filtered_users = [u for u in users if query in u['username'].lower()]
        for user in filtered_users:
            self.user_tree.insert('', 'end', values=(user['id'], user['username'], "Yes" if user['is_admin'] else "No"))

    def delete_selected_users(self):
        """Delete the selected users from the Treeview and database."""
        selected_items = self.tree_users.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "No users selected!")
            return

        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete the selected {len(selected_items)} user(s)?"
        )
        if not confirm:
            return

        conn, c = get_db_connection()
        try:
            for item in selected_items:
                user_id = self.tree_users.item(item, "values")[0]  # Get the user ID
                c.execute('DELETE FROM users WHERE id = ?', (user_id,))
                self.tree_users.delete(item)  # Remove from Treeview
            conn.commit()
            messagebox.showinfo("Success", "Selected user(s) deleted successfully!")
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Failed to delete user(s): {e}")
        finally:
            conn.close()

    def promote_user_to_admin(self):
        selected_items = self.tree_users.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "No users selected!")
            return

        conn, c = get_db_connection()
        try:
            for item in selected_items:
                user_id = self.tree_users.item(item, "values")[0]
                c.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
            conn.commit()
            messagebox.showinfo("Success", "Selected users promoted to admin.")
        finally:
            conn.close()

        self.populate_user_tree()  # Refresh user list

    def demote_user_from_admin(self):
        selected_items = self.tree_users.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "No users selected!")
            return

        conn, c = get_db_connection()
        try:
            for item in selected_items:
                user_id = self.tree_users.item(item, "values")[0]
                c.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user_id,))
            conn.commit()
            messagebox.showinfo("Success", "Selected admins demoted to regular users.")
        finally:
            conn.close()

        self.populate_user_tree()  # Refresh user list

    def populate_user_tree(self):
        """Populate the Treeview with user data."""
        for row in self.tree_users.get_children():
            self.tree_users.delete(row)

        users = get_users()
        for user in users:
            is_admin = "Yes" if user.get('is_admin', 0) else "No"
            self.tree_users.insert('', 'end', values=(user['id'], user['username'], is_admin))

    def generate_detailed_report(self):
        transactions = get_transactions(self.user_id)
        if not transactions:
            messagebox.showwarning("Warning", "No transactions found to generate the report.")
            return

        df = pd.DataFrame(transactions)
        # Ensure 'amount' column is numeric and 'date' is valid
        try:
            df['Amount'] = pd.to_numeric(df['amount'], errors='coerce')
            df['Date'] = pd.to_datetime(df['date'], errors='coerce')  # Convert invalid dates to NaT
            df = df.dropna(subset=['Amount', 'Date'])  # Drop rows with NaN in 'Amount' or 'Date'
        except KeyError:
            messagebox.showerror("Error", "Data is missing required fields.")
            return


        # Analyze trends and comparisons
        monthly_summary = df.resample('M', on='Date').sum()
        monthly_summary['Month'] = monthly_summary.index.strftime('%B %Y')

        # Comparison with the previous period
        monthly_summary['Previous'] = monthly_summary['Amount'].shift(1)
        monthly_summary['Change'] = monthly_summary['Amount'] - monthly_summary['Previous']

        # Create a PDF report
        self.create_pdf_report(monthly_summary)

    def create_pdf_report(self, monthly_summary):
        try:
            output_filename = "detailed_monthly_report.pdf"
            pdf = SimpleDocTemplate(
                output_filename,
                pagesize=landscape(letter),
                rightMargin=30,
                leftMargin=30,
                topMargin=30,
                bottomMargin=18
            )

            elements = []
            styles = getSampleStyleSheet()
            title_style = styles['Title']
            normal_style = styles['BodyText']
            table_style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), '#CCCCCC'),
                ('TEXTCOLOR', (0, 0), (-1, 0), '#000000'),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), '#FFFFFF'),
                ('GRID', (0, 0), (-1, -1), 1, '#000000'),
            ])

        # Add the report title
            elements.append(Paragraph("Monthly Financial Report", title_style))
            elements.append(Paragraph("Summary of financial transactions by month.", normal_style))
            elements.append(Paragraph(" ", normal_style))  # Add space

        # Prepare data for the table
            data = [["Month", "Total Amount ($)", "Change from Previous ($)"]]
            for _, row in monthly_summary.iterrows():
                data.append([
                    row['Month'],
                    f"{row['Amount']:.2f}",
                    f"{row['Change']:.2f}" if not pd.isna(row['Change']) else "N/A"
                ])

        # Create the table
            table = Table(data)
            table.setStyle(table_style)
            elements.append(table)

        # Generate the PDF
            pdf.build(elements)
            print(f"PDF generated successfully: {output_filename}")
        except Exception as e:
            print(f"Error creating PDF: {e}")
            messagebox.showerror("Error", f"Failed to create PDF report: {e}")

    def export_to_pdf(self):
        try:
            print("Export to PDF initiated")
            self.generate_detailed_report()
            messagebox.showinfo("Success", "PDF Report Generated Successfully!")
        except Exception as e:
            print(f"Error exporting PDF: {e}")
            messagebox.showerror("Error", f"Failed to generate PDF report: {e}")

    def export_to_excel(self):
        try:
            transactions = get_transactions(self.user_id)
            if not transactions:
                messagebox.showwarning("Warning", "No transactions found to export.")
                return

            df = pd.DataFrame(transactions)

        # Ensure proper data types
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
            df = df.dropna(subset=['amount', 'date'])  # Drop invalid rows

            file_path = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx")],
                title="Save Excel Report",
                initialfile="transactions_report.xlsx"
            )

            if not file_path:
                return  # User canceled

            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name="Transactions")
                workbook = writer.book
                worksheet = writer.sheets["Transactions"]

            # Format columns
                for col in worksheet.iter_cols(min_row=2, max_row=worksheet.max_row, min_col=1, max_col=len(df.columns)):
                    for cell in col:
                        if isinstance(cell.value, float):
                            cell.number_format = "#,##0.00"

            messagebox.showinfo("Success", f"Transactions exported successfully to {file_path}")
        except Exception as e:
            print(f"Error exporting to Excel: {e}")
            messagebox.showerror("Error", f"Failed to export Excel report: {e}")

    def create_labeled_entry(self, parent, label_text, row, widget_type, **widget_options):
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky=tk.W, padx=10, pady=5)
        entry = widget_type(parent, **widget_options)
        entry.grid(row=row, column=1, padx=10, pady=5)
        return entry

    def create_settings_tab(self):
        frame_settings = ttk.Frame(self.tabs['settings'])
        frame_settings.pack(fill='both', expand=True, pady=20)
        ttk.Label(frame_settings, text="Font Size:").pack(pady=5)
        self.font_size = tk.IntVar(value=10)
        ttk.Spinbox(frame_settings, from_=8, to=20, textvariable=self.font_size, command=self.update_font_size).pack(pady=5)
        ttk.Label(frame_settings, text="Select Color Scheme:").pack(pady=5)
        color_scheme_menu = ttk.Combobox(frame_settings, textvariable=self.selected_color_scheme, values=list(self.color_schemes.keys()))
        color_scheme_menu.pack(pady=5)
        color_scheme_menu.bind("<<ComboboxSelected>>", lambda event: self.apply_color_scheme())
        ttk.Button(frame_settings, text="Backup Database", command=backup_database).pack(pady=10)
        ttk.Button(frame_settings, text="Restore Database", command=restore_database).pack(pady=10)
        ttk.Button(frame_settings, text="Logout", command=self.logout).pack(pady=10)

    def apply_color_scheme(self):
        self.setup_styles()

    def update_font_size(self):
        new_size = self.font_size.get()
        self.style.configure('TLabel', font=("tahoma", new_size))
        self.style.configure('TButton', font=("tahoma", new_size))
        self.style.configure('TEntry', font=("tahoma", new_size))
        self.style.configure('TCombobox', font=("tahoma", new_size))

    def validate_amount(self, amount):
        try:
            float(amount)
            return True
        except ValueError:
            return False

    def validate_date(self, date):
        try:
            pd.to_datetime(date, format='%Y-%m-%d')
            return True
        except ValueError:
            return False
        
    def validate_transaction_fields(self, amount, category, date):
        if not amount or not category or not date:
            messagebox.showwarning("Error", "All fields are required!")
            return False
        if not self.validate_amount(amount):
            messagebox.showwarning("Error", "Invalid amount format!")
            return False
        if not self.validate_date(date):
            messagebox.showwarning("Error", "Invalid date format! Use YYYY-MM-DD.")
            return False
        return True

    def add_transaction(self):
        trans_type = self.trans_type.get()
        amount = self.entry_amount.get()
        category = self.entry_category.get()
        date = self.entry_date.get()
        currency = self.currency.get()

    # Validate fields
        if not self.validate_transaction_fields(amount, category, date):
            return

        try:
            self.insert_transaction(trans_type, float(amount), category, date, self.user_id, currency)
            messagebox.showinfo("Success", "Transaction added!")
            self.clear_fields()
            self.refresh_data()
            self.populate_transactions()
            self.calculate_balance()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add transaction: {e}")
            self.calculate_balance()

    def insert_transaction(self, trans_type, amount, category, date, user_id, currency):    
        if not self.validate_date(date):
            raise ValueError(f"Invalid date format: {date}. Use YYYY-MM-DD format.")
        
        conn, c = get_db_connection()    
        try:
        # Ensure the order of the values matches the schema: (type, amount, category, date, currency, user_id)        
            c.execute(
                'INSERT INTO transactions (type, amount, category, date, currency, user_id) VALUES (?, ?, ?, ?, ?, ?)',            
                (trans_type, amount, category, date, currency, user_id)
            )       
            conn.commit()
        except sqlite3.Error as e:        
            print(f"Error inserting transaction: {e}")
            messagebox.showerror("Database Error", f"Unable to insert transaction: {e}")    
        finally:
            conn.close()

    def on_transaction_select(self, event):
        try:
            selected_item = self.tree_transactions.selection()[0]
            transaction = self.tree_transactions.item(selected_item, "values")
            print("Selected transaction:", transaction)

            self.trans_type.set(transaction[1])  # Set type
            self.entry_amount.delete(0, tk.END)
            self.entry_amount.insert(0, transaction[2])  # Set amount
            self.entry_category.delete(0, tk.END)
            self.entry_category.insert(0, transaction[3])  # Set category

        # Validate and set date
            try:
                valid_date = pd.to_datetime(transaction[4], format='%Y-%m-%d')
                self.entry_date.set_date(valid_date.strftime('%Y-%m-%d'))
            except ValueError:
                messagebox.showerror("Error", f"Invalid date format in transaction: {transaction[4]}")
                self.entry_date.set_date(pd.to_datetime("today").strftime('%Y-%m-%d'))

            self.currency.set(transaction[5])  # Set currency
            self.selected_transaction_id = transaction[0]
        except IndexError:
            print("No transaction selected.")
            messagebox.showwarning("Selection Error", "Please select a transaction to edit.")

    def update_transaction(self):
        if not hasattr(self, 'selected_transaction_id'):
            messagebox.showwarning("Error", "No transaction selected!")
            return
        trans_type = self.trans_type.get()
        amount = self.entry_amount.get()
        category = self.entry_category.get()
        date = self.entry_date.get()
        currency = self.currency.get()
        if not amount or not category or not date:
            messagebox.showwarning("Error", "Fill all fields!")
            return
        if not self.validate_amount(amount):
            messagebox.showwarning("Error", "Invalid amount!")
            return
        if not self.validate_date(date):
            messagebox.showwarning("Error", "Invalid date format!")
            return
        try:
            self.modify_transaction(self.selected_transaction_id, trans_type, amount, category, date, currency)
            messagebox.showinfo("Success", "Transaction updated!")
            self.clear_fields()
            self.populate_transactions()
            self.calculate_balance()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update transaction: {e}")
            self.calculate_balance()

    def modify_transaction(self, transaction_id, trans_type, amount, category, date, currency):
        conn, c = get_db_connection()
        try:
            c.execute(
                'UPDATE transactions SET type=?, amount=?, category=?, date=?, currency=? WHERE id=?',
                (trans_type, amount, category, date, currency, transaction_id)
            )
            conn.commit()
        except sqlite3.Error as e:
            print(f"Error updating transaction: {e}")
            messagebox.showerror("Database Error", f"Unable to update transaction: {e}")
        finally:
            conn.close()

    def delete_transaction(self):
        if not hasattr(self, 'selected_transaction_id'):
            messagebox.showwarning("Error", "No transaction selected!")
            return
        try:
            self.remove_transaction(self.selected_transaction_id)
            messagebox.showinfo("Success", "Transaction deleted!")
            self.clear_fields()
            self.populate_transactions()
            self.calculate_balance()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete transaction: {e}")
            self.calculate_balance()

    def remove_transaction(self, transaction_id):
        conn, c = get_db_connection()
        try:
            c.execute('DELETE FROM transactions WHERE id=?', (transaction_id,))
            conn.commit()
        except sqlite3.Error as e:
            print(f"Error deleting transaction: {e}")
            messagebox.showerror("Database Error", f"Unable to delete transaction: {e}")
        finally:
            conn.close()

    def populate_transactions(self):
        self.update()  # Ensure immediate UI refresh
        for row in self.tree_transactions.get_children():
            self.tree_transactions.delete(row)

        transactions = get_transactions(self.user_id, is_admin=self.is_admin)
        if not transactions:
            print("No transactions found.")  # Debugging line
            return

        for transaction in transactions:
            print("Adding transaction:", transaction)  # Debugging line
            self.tree_transactions.insert(
                '', 'end',
                values=(transaction['id'], transaction['type'], transaction['amount'], transaction['category'], transaction['date'], transaction['currency'])
            )

    # Fetch transactions for the logged-in user or all transactions for admin
    def populate_transactions(self):    
        for row in self.tree_transactions.get_children():
            self.tree_transactions.delete(row)
        
        transactions = get_transactions(self.user_id, is_admin=self.is_admin)    
        if not transactions:
            print("No transactions found or data structure is empty.")        
            return
        for transaction in transactions:
            print("Inserting transaction:", transaction)  # Debugging line        
            self.tree_transactions.insert('', 'end', values=(
                transaction['id'],            
                transaction['type'],
                transaction['amount'],            
                transaction['category'],
                transaction['date'],            
                transaction['currency']
            ))

    def clear_fields(self):
        self.entry_amount.delete(0, tk.END)
        self.entry_category.delete(0, tk.END)
        self.entry_date.set_date(pd.to_datetime("today").strftime('%Y-%m-%d'))
        self.currency.set("USD")
        self.trans_type.set("expense")
        self.selected_transaction_id = None

    def calculate_balance(self):
        """
        Calculate and display the balance for each currency based on the transactions.
        """
        if self.user_id is None:
            return  # Skip calculation if no user is logged in

    # Fetch transactions for the logged-in user or admin
        transactions = get_transactions(self.user_id, is_admin=self.is_admin)
        if not transactions:
            self.balance_var.set("No transactions available.")
            return

    # Group balances by currency
        balance_by_currency = {}
        for transaction in transactions:
            try:
                amount = float(transaction['amount'])
                currency = transaction['currency']
                if transaction['type'] == 'income':
                    balance_by_currency[currency] = balance_by_currency.get(currency, 0) + amount
                elif transaction['type'] == 'expense':
                    balance_by_currency[currency] = balance_by_currency.get(currency, 0) - amount
            except (ValueError, KeyError):
                print(f"Invalid transaction data: {transaction}")

    # Format the balance display
        balances = [f"{currency}: {balance:.2f}" for currency, balance in balance_by_currency.items()]
        self.balance_var.set(" | ".join(balances))

    # Optional: Notify user if total balance in USD falls below the threshold
        total_balance_usd = sum(
            self.convert_currency(balance, currency, "USD") or 0
            for currency, balance in balance_by_currency.items()
        )
        self.check_balance_notification(total_balance_usd)

    def check_balance_notification(self, balance):
        if self.user_id is None:
        # Skip notification if no user is logged in
            return

        if balance < REMINDER_THRESHOLD:
            messagebox.showwarning("Low Balance Alert", "Your balance is below the set threshold!")

    def check_planned_transaction_reminders(self):
        """Check and remind about planned transactions occurring within the next 7 days."""
        planned_transactions = get_planned_transactions(self.user_id, is_admin=self.is_admin)
    
    # Convert to DataFrame for easier manipulation
        df = pd.DataFrame(planned_transactions)
    
        if not df.empty and 'planned_date' in df.columns:
        # Ensure planned_date is in datetime format
            df['Planned Date'] = pd.to_datetime(df['planned_date'], errors='coerce')
            today = pd.Timestamp.now()
            upcoming_plans = df[(df['Planned Date'] > today) & (df['Planned Date'] <= today + timedelta(days=7))]
        
            if not upcoming_plans.empty:
                message = "You have the following planned transactions in the next 7 days:\n\n"
                for _, row in upcoming_plans.iterrows():
                    message += (
                        f"- {row['type'].capitalize()} of {row['amount']} {row['currency']} "
                        f"in category '{row['category']}' planned for {row['Planned Date'].strftime('%Y-%m-%d')}.\n"
                    )
                messagebox.showinfo("Planned Transactions Reminder", message)
            else:
                print("No planned transactions within the next 7 days.")
        else:
            print("No planned transactions available or data structure is empty.")

    def logout(self):
        self.destroy()
        FinanceApp().mainloop()

    def start_auto_refresh(self, interval=60000):
        self.auto_refresh = threading.Event()
        self.refresh_data()
        self.after(interval, self.auto_refresh_callback)

    def auto_refresh_callback(self):
        if not self.auto_refresh.is_set():
            self.refresh_data()
            self.after(60000, self.auto_refresh_callback)

    def refresh_data(self):
        self.exchange_rates = get_current_exchange_rates()
        self.populate_transactions()
        self.calculate_balance()
        self.check_planned_transaction_reminders()

    def quit_app(self, event=None):
        """Gracefully exit the application."""
        if hasattr(self, "auto_refresh") and self.auto_refresh:
            self.auto_refresh.set()  # Stop the auto-refresh thread
        self.destroy()  # Properly destroy the Tkinter app

class DeleteUserWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Delete User")
        self.geometry("300x400")
        self.create_widgets()

    def create_widgets(self):
        ttk.Label(self, text="Select User to Delete:").pack(pady=5)
        self.listbox_users = tk.Listbox(self)
        self.listbox_users.pack(pady=5, fill=tk.BOTH, expand=True)
        self.populate_listbox()
        ttk.Button(self, text="Delete Selected User", command=self.delete_user).pack(pady=5)

    def populate_listbox(self):
        users = get_users()
        for user in users:
            self.listbox_users.insert(tk.END, f"{user['id']} - {user['username']}")

    def delete_user(self):
        selected = self.listbox_users.curselection()
        if not selected:
            messagebox.showerror("Error", "No user selected!")
            return

        user_info = self.listbox_users.get(selected[0])
        user_id = int(user_info.split(" - ")[0])  # Extract user ID
        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete user with ID {user_id}?"
        )
        if not confirm:
            return

        try:
            self.remove_user(user_id)
            self.listbox_users.delete(selected[0])  # Remove from Listbox
            messagebox.showinfo("Success", "User deleted successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete user: {e}")

    def remove_user(self, user_id):
        """Delete a user from the database by their user_id."""
        conn, c = get_db_connection()
        try:
            c.execute('DELETE FROM users WHERE id = ?', (user_id,))
            conn.commit()
            print(f"User with ID {user_id} deleted successfully.")
        except Exception as e:
            print(f"Error deleting user: {e}")
            messagebox.showerror("Error", f"Failed to delete user: {e}")
        finally:
            conn.close()

if __name__ == "__main__":
    init_db()
    setup_admin_user()  # Ensure an admin user exists
    print("Starting FinanceApp...")
    app = FinanceApp()
    app.mainloop()
