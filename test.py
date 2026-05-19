import sqlite3
import datetime
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, scrolledtext, filedialog
from datetime import datetime, timedelta
import hashlib
import random
import os
import shutil
import csv
import json
import threading
import time
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageTk
import schedule

# ==================== CONFIGURATION MANAGER ====================
class ConfigManager:
    DEFAULT_CONFIG = {
        "company_name": "VICTOR'S SUPER MARKET",   # Changed to Victor's
        "currency": "Ksh",
        "tax_rates": [
            {"name": "VAT 16%", "rate": 0.16, "categories": ["general", "electronics", "beverages", "snacks"]},
            {"name": "Zero Rated", "rate": 0.0, "categories": ["basic_food", "medicines", "fruits_vegetables"]},
            {"name": "Exempt", "rate": 0.0, "categories": ["services"]}
        ],
        "payment_methods": ["Cash", "Card", "MPESA", "Bank Transfer", "Voucher"],
        "loyalty_points_per_ksh": 0.01,
        "low_stock_threshold": 5,
        "auto_backup": True,
        "backup_interval_days": 1,
        "receipt_footer": "Thank you for shopping with us!\nVisit again!",
        "enable_branch_support": False,
        "branches": [{"id": 1, "name": "Main Store", "location": "Nairobi"}]
    }

    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.config = self.load_config()

    def load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                user_config = json.load(f)
                merged = self.DEFAULT_CONFIG.copy()
                merged.update(user_config)
                return merged
        else:
            self.save_config(self.DEFAULT_CONFIG)
            return self.DEFAULT_CONFIG

    def save_config(self, config=None):
        with open(self.config_path, 'w') as f:
            json.dump(config or self.config, f, indent=4)

    def get_tax_rate(self, product_category):
        for tax in self.config["tax_rates"]:
            if product_category in tax.get("categories", []):
                return tax["rate"]
        return self.config["tax_rates"][0]["rate"]

    def get_payment_methods(self):
        return self.config["payment_methods"]

# ==================== DATABASE SETUP ====================
class Database:
    def __init__(self, db_name="supermarket.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.create_tables()
        self.populate_products()

    def create_tables(self):
        # Products table
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode TEXT UNIQUE,
            name TEXT NOT NULL,
            category TEXT,
            buying_price REAL,
            selling_price REAL NOT NULL,
            quantity INTEGER DEFAULT 0,
            min_stock INTEGER DEFAULT 5,
            unit TEXT DEFAULT 'pcs',
            supplier TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # Sales table
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no TEXT UNIQUE,
            customer_name TEXT,
            customer_phone TEXT,
            total_amount REAL,
            discount REAL DEFAULT 0,
            tax REAL DEFAULT 0,
            net_amount REAL,
            payment_method TEXT,
            cash_tendered REAL,
            change_given REAL,
            cashier TEXT,
            sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            branch_id INTEGER DEFAULT 1
        )''')

        # Sale items table
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no TEXT,
            product_id INTEGER,
            product_name TEXT,
            quantity INTEGER,
            unit_price REAL,
            total REAL,
            returned BOOLEAN DEFAULT 0
        )''')

        # Users table
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT DEFAULT 'cashier',
            full_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # Suppliers table
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            contact_person TEXT,
            phone TEXT,
            email TEXT,
            address TEXT
        )''')

        # Stock movements table
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            movement_type TEXT,
            quantity INTEGER,
            reason TEXT,
            user TEXT,
            movement_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # Returns table
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS returns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_invoice TEXT,
            return_invoice TEXT UNIQUE,
            product_id INTEGER,
            product_name TEXT,
            quantity INTEGER,
            refund_amount REAL,
            reason TEXT,
            cashier TEXT,
            return_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # Loyalty table
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS loyalty (
            customer_phone TEXT PRIMARY KEY,
            customer_name TEXT,
            points INTEGER DEFAULT 0,
            tier TEXT DEFAULT 'Bronze',
            total_spent REAL DEFAULT 0,
            joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # Expenses table
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            amount REAL,
            description TEXT,
            expense_date DATE,
            user TEXT
        )''')

        # Branches table
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS branches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            location TEXT,
            phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # Audit log table
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            action TEXT,
            table_name TEXT,
            record_id TEXT,
            old_value TEXT,
            new_value TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # Product variants table
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS product_variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            variant_name TEXT,
            sku TEXT UNIQUE,
            extra_price REAL DEFAULT 0,
            stock_quantity INTEGER DEFAULT 0,
            FOREIGN KEY(product_id) REFERENCES products(id)
        )''')

        # Promotions table
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS promotions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            discount_type TEXT,
            discount_value REAL,
            start_date DATE,
            end_date DATE,
            product_id INTEGER,
            min_quantity INTEGER DEFAULT 1,
            is_active BOOLEAN DEFAULT 1
        )''')

        # Insert default admin user
        self.cursor.execute("SELECT * FROM users WHERE username='admin'")
        if not self.cursor.fetchone():
            hashed_pwd = hashlib.sha256("victor@123".encode()).hexdigest()
            self.cursor.execute("INSERT INTO users (username, password, role, full_name) VALUES (?, ?, ?, ?)",
                                ("victor", hashed_pwd, "admin", "System Administrator"))

        # Insert default cashier user
        self.cursor.execute("SELECT * FROM users WHERE username='cashier'")
        if not self.cursor.fetchone():
            hashed_pwd = hashlib.sha256("".encode()).hexdigest()
            self.cursor.execute("INSERT INTO users (username, password, role, full_name) VALUES (?, ?, ?, ?)",
                                ("cashier", hashed_pwd, "cashier", "Store Cashier"))

        # Insert default branch
        self.cursor.execute("SELECT COUNT(*) FROM branches")
        if self.cursor.fetchone()[0] == 0:
            self.cursor.execute("INSERT INTO branches (name, location, phone) VALUES (?, ?, ?)",
                                ("Main Store", "Nairobi", "+254700000000"))

        # Insert sample suppliers if empty
        self.cursor.execute("SELECT COUNT(*) FROM suppliers")
        if self.cursor.fetchone()[0] == 0:
            sample_suppliers = [
                ("Local Suppliers Ltd", "John Doe", "0712345678", "john@localsuppliers.com", "Nairobi"),
                ("Farm Fresh Kenya", "Jane Smith", "0723456789", "jane@farmfresh.com", "Kiambu"),
                ("Bakery Supplies Co", "Bob Wilson", "0734567890", "bob@bakery.com", "Mombasa"),
                ("Dairy Masters Ltd", "Alice Brown", "0745678901", "alice@dairymasters.com", "Nakuru"),
                ("Beverage Distributors", "Charlie Davis", "0756789012", "charlie@beverages.com", "Kisumu"),
                ("Canned Foods Inc", "Diana Evans", "0767890123", "diana@cannedfoods.com", "Eldoret"),
            ]
            for supplier in sample_suppliers:
                self.cursor.execute(
                    "INSERT INTO suppliers (name, contact_person, phone, email, address) VALUES (?, ?, ?, ?, ?)",
                    supplier)

        self.conn.commit()

    def populate_products(self):
        """Generate 500 products automatically"""
        self.cursor.execute("SELECT COUNT(*) FROM products")
        if self.cursor.fetchone()[0] > 0:
            return  # products already exist

        self.cursor.execute("SELECT name FROM suppliers")
        suppliers = [row[0] for row in self.cursor.fetchall()]
        if not suppliers:
            suppliers = ["General Supplier"]

        categories = [
            "Grains", "Dairy", "Beverages", "Snacks", "Fruits",
            "Vegetables", "Meat", "Frozen", "Household", "Personal Care"
        ]
        units = ["pcs", "kg", "L", "g", "ml", "pack"]

        product_count = 0
        for i in range(1, 501):
            cat = random.choice(categories)
            # Create a realistic product name
            if cat == "Grains":
                name = random.choice(["Rice", "Maize Flour", "Wheat Flour", "Oats", "Quinoa"]) + f" {random.randint(1,5)}kg"
            elif cat == "Dairy":
                name = random.choice(["Milk", "Yogurt", "Cheese", "Butter", "Cream"]) + f" {random.choice(['250ml','500ml','1L'])}"
            elif cat == "Beverages":
                name = random.choice(["Mineral Water", "Soda", "Juice", "Energy Drink", "Coffee"]) + f" {random.choice(['330ml','500ml','1L'])}"
            elif cat == "Snacks":
                name = random.choice(["Potato Chips", "Chocolate Bar", "Biscuits", "Popcorn", "Peanuts"]) + f" {random.randint(50,200)}g"
            elif cat == "Fruits":
                name = random.choice(["Apple", "Banana", "Orange", "Mango", "Grapes"]) + f" {random.choice(['1kg','500g','bunch'])}"
            elif cat == "Vegetables":
                name = random.choice(["Tomato", "Onion", "Potato", "Cabbage", "Carrot"]) + f" {random.choice(['1kg','500g','piece'])}"
            elif cat == "Meat":
                name = random.choice(["Beef", "Chicken", "Pork", "Fish Fillet", "Sausages"]) + f" {random.choice(['500g','1kg','pack'])}"
            elif cat == "Frozen":
                name = random.choice(["Frozen Peas", "Ice Cream", "Frozen Chips", "Frozen Chicken", "Pizza"]) + f" {random.choice(['500g','1kg','400g'])}"
            elif cat == "Household":
                name = random.choice(["Detergent", "Dish Soap", "Bleach", "Paper Towels", "Trash Bags"]) + f" {random.choice(['500ml','1L','pack'])}"
            else:  # Personal Care
                name = random.choice(["Shampoo", "Soap", "Toothpaste", "Deodorant", "Lotion"]) + f" {random.choice(['250ml','500ml','100g'])}"

            buying_price = round(random.uniform(10, 500), 2)
            selling_price = round(buying_price * random.uniform(1.2, 1.8), 2)
            quantity = random.randint(20, 500)
            min_stock = random.randint(5, 20)
            unit = random.choice(units)
            barcode = f"890{random.randint(1000000000, 9999999999)}"
            supplier = random.choice(suppliers)

            self.cursor.execute('''INSERT INTO products 
                (barcode, name, category, buying_price, selling_price, quantity, min_stock, unit, supplier)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (barcode, name, cat, buying_price, selling_price, quantity, min_stock, unit, supplier))
            product_count += 1

            # Record initial stock movement
            self.cursor.execute('''INSERT INTO stock_movements 
                (product_id, movement_type, quantity, reason, user)
                VALUES (?, 'stock_in', ?, 'Initial stock', 'system')''',
                (product_count, quantity))

        # Add sample sales
        for _ in range(100):
            random_date = datetime.now() - timedelta(days=random.randint(1, 90))
            invoice_no = f"INV-{random_date.strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
            total = random.randint(500, 15000)
            customer_name = random.choice(['John Doe', 'Jane Smith', 'Bob Wilson', 'Alice Brown', 'Walk-in Customer'])
            self.cursor.execute('''INSERT INTO sales 
                (invoice_no, customer_name, total_amount, tax, net_amount, payment_method, cashier, sale_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (invoice_no, customer_name, total, total*0.16, total*1.16,
                 random.choice(['Cash', 'Card', 'MPESA']),
                 random.choice(['admin', 'cashier']), random_date))

        self.conn.commit()
        print(f"✅ Successfully added {product_count} products to inventory!")

    def execute_query(self, query, params=()):
        self.cursor.execute(query, params)
        self.conn.commit()
        return self.cursor

    def fetch_all(self, query, params=()):
        self.cursor.execute(query, params)
        return self.cursor.fetchall()

    def fetch_one(self, query, params=()):
        self.cursor.execute(query, params)
        return self.cursor.fetchone()

    def log_action(self, user, action, table_name, record_id, old_value="", new_value=""):
        self.execute_query(
            "INSERT INTO audit_log (user, action, table_name, record_id, old_value, new_value) VALUES (?,?,?,?,?,?)",
            (user, action, table_name, str(record_id), str(old_value), str(new_value))
        )

    def close(self):
        self.conn.close()

# ==================== MAIN APPLICATION CLASS (GREEN THEME) ====================
class SupermarketSystem:
    def __init__(self, root):
        self.root = root
        self.root.title("🏪 VICTOR'S SUPER MARKET - Green Edition")
        self.root.state('zoomed')
        self.root.configure(bg='#e8f5e9')

        self.db = Database()
        self.config = ConfigManager()
        self.current_user = None
        self.cart = []

        self.colors = {
            'primary': '#2e7d32',
            'secondary': '#1b5e20',
            'success': '#43a047',
            'danger': '#d32f2f',
            'warning': '#f9a825',
            'info': '#388e3c',
            'light': '#f1f8e9',
            'dark': '#1b5e20',
            'accent': '#66bb6a',
            'purple': '#9c27b0',
            'teal': '#009688',
            'indigo': '#3f51b5'
        }

        if self.config.config["auto_backup"]:
            self.start_backup_scheduler()

        self.show_login()

    def start_backup_scheduler(self):
        def backup_job():
            self.manual_backup()
        schedule.every(self.config.config["backup_interval_days"]).days.at("23:00").do(backup_job)
        def run_scheduler():
            while True:
                schedule.run_pending()
                time.sleep(60)
        threading.Thread(target=run_scheduler, daemon=True).start()

    # ---------- LOGIN PAGE (green, fully visible) ----------
    def show_login(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        main_container = tk.Frame(self.root, bg=self.colors['primary'])
        main_container.pack(fill='both', expand=True)

        login_card = tk.Frame(main_container, bg='white', relief='raised', bd=2,
                              highlightbackground=self.colors['accent'], highlightthickness=2)
        login_card.place(relx=0.5, rely=0.5, anchor='center', width=500, height=500)

        tk.Label(login_card, text="🛒", font=('Segoe UI', 56), bg='white', fg=self.colors['primary']).pack(pady=(30,10))
        tk.Label(login_card, text="VICTOR'S SUPER MARKET", font=('Segoe UI', 22, 'bold'), bg='white', fg=self.colors['primary']).pack()
        tk.Label(login_card, text="Login to Continue", font=('Segoe UI', 12), bg='white', fg=self.colors['secondary']).pack(pady=5)

        form_frame = tk.Frame(login_card, bg='white')
        form_frame.pack(pady=30, padx=40, fill='both', expand=True)

        tk.Label(form_frame, text="USERNAME", font=('Segoe UI', 11, 'bold'), bg='white', fg=self.colors['dark']).pack(anchor='w', pady=(0,5))
        self.username_entry = tk.Entry(form_frame, font=('Segoe UI', 12), bg=self.colors['light'], relief='solid', bd=1)
        self.username_entry.pack(fill='x', pady=(0,15), ipady=8)

        tk.Label(form_frame, text="PASSWORD", font=('Segoe UI', 11, 'bold'), bg='white', fg=self.colors['dark']).pack(anchor='w', pady=(0,5))
        self.password_entry = tk.Entry(form_frame, font=('Segoe UI', 12), show='•', bg=self.colors['light'], relief='solid', bd=1)
        self.password_entry.pack(fill='x', pady=(0,25), ipady=8)

        login_btn = tk.Button(form_frame, text="SIGN IN", command=self.login, bg=self.colors['primary'], fg='white',
                              font=('Segoe UI', 12, 'bold'), relief='flat', cursor='hand2')
        login_btn.pack(fill='x', ipady=10)

        def on_enter(e): login_btn['bg'] = self.colors['secondary']
        def on_leave(e): login_btn['bg'] = self.colors['primary']
        login_btn.bind('<Enter>', on_enter)
        login_btn.bind('<Leave>', on_leave)

        demo_frame = tk.Frame(form_frame, bg='white')
        demo_frame.pack(pady=15)
        tk.Label(demo_frame, text="Demo accounts:", font=('Segoe UI', 9), bg='white', fg='gray').pack(side='left')
        tk.Label(demo_frame, text=" admin/admin123 | cashier/cashier123", font=('Segoe UI', 9, 'italic'), bg='white', fg=self.colors['primary']).pack(side='left', padx=5)

        self.username_entry.bind('<Return>', lambda e: self.login())
        self.password_entry.bind('<Return>', lambda e: self.login())

    def login(self):
        username = self.username_entry.get()
        password = hashlib.sha256(self.password_entry.get().encode()).hexdigest()
        user = self.db.fetch_one("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        if user:
            self.current_user = {'id': user[0], 'username': user[1], 'role': user[3], 'full_name': user[4]}
            self.db.log_action(username, "LOGIN", "users", user[0], "", "Successful login")
            messagebox.showinfo("Success", f"✨ Welcome back, {self.current_user['full_name']}! ✨")
            self.show_main_menu()
        else:
            messagebox.showerror("Error", "❌ Invalid username or password!")

    # ---------- MAIN MENU (green header and buttons) ----------
    def show_main_menu(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        header_frame = tk.Frame(self.root, height=80)
        header_frame.pack(fill='x')
        tk.Frame(header_frame, bg=self.colors['primary'], height=40).pack(fill='x')
        tk.Frame(header_frame, bg=self.colors['accent'], height=40).pack(fill='x')
        tk.Label(header_frame, text="🏪 VICTOR'S SUPER MARKET", font=('Segoe UI', 22, 'bold'), bg=self.colors['primary'], fg='white').place(x=30, y=25)

        user_frame = tk.Frame(header_frame, bg=self.colors['primary'])
        user_frame.place(relx=0.92, rely=0.15, anchor='ne')
        tk.Label(user_frame, text="👤", font=('Segoe UI', 16), bg=self.colors['primary'], fg='white').pack(side='left')
        tk.Label(user_frame, text=f"{self.current_user['full_name']} ({self.current_user['role']})", font=('Segoe UI', 10, 'bold'), bg=self.colors['primary'], fg='white').pack(side='left', padx=10)
        tk.Button(user_frame, text="🚪 Logout", command=self.logout, bg=self.colors['danger'], fg='white', font=('Segoe UI', 10, 'bold'), relief='flat', cursor='hand2', padx=15, pady=5).pack(side='left')

        self.show_dashboard_stats(self.root)

        buttons_frame = tk.Frame(self.root, bg='#e8f5e9')
        buttons_frame.pack(fill='both', expand=True, padx=30, pady=20)
        for i in range(4): buttons_frame.grid_columnconfigure(i, weight=1)
        for i in range(3): buttons_frame.grid_rowconfigure(i, weight=1)

        menu_buttons = [
            ("🛒", "Point of Sale", self.show_pos, self.colors['success']),
            ("📦", "Inventory", self.show_inventory, self.colors['info']),
            ("📊", "Reports", self.show_reports, self.colors['primary']),
            ("👥", "Customers", self.show_customers, '#e67e22'),
            ("🏭", "Suppliers", self.show_suppliers, '#16a085'),
            ("👤", "Users", self.show_users, '#c0392b'),
            ("📈", "Dashboard", self.show_dashboard, self.colors['secondary']),
            ("🔍", "Stock Alerts", self.show_stock_alerts, '#e67e22'),
            ("🔄", "Returns", self.show_returns, '#8e44ad'),
            ("💎", "Loyalty", self.show_loyalty, '#f39c12'),
            ("💰", "Expenses", self.show_expenses, '#1abc9c'),
            ("💾", "Backup", self.manual_backup, '#34495e'),
            ("📈", "Advanced Charts", self.show_advanced_charts, '#9c27b0'),
            ("🏷️", "Print Barcode", self.barcode_print_dialog, '#009688'),
        ]

        row, col = 0, 0
        for icon, text, command, color in menu_buttons:
            if text == "Users" and self.current_user['role'] != 'admin':
                continue
            btn_card = tk.Frame(buttons_frame, bg='white', relief='ridge', bd=1, highlightbackground='#d0d0d0', highlightthickness=1)
            btn_card.grid(row=row, column=col, padx=15, pady=15, sticky='nsew')
            btn = tk.Button(btn_card, text=f"{icon}\n{text}", command=command, bg=color, fg='white', font=('Segoe UI', 13, 'bold'), width=18, height=4, relief='flat', cursor='hand2')
            btn.pack(fill='both', expand=True, padx=2, pady=2)
            def on_enter(e, btn=btn, c=color): btn['bg'] = self.lighten_color(c)
            def on_leave(e, btn=btn, c=color): btn['bg'] = c
            btn.bind('<Enter>', on_enter)
            btn.bind('<Leave>', on_leave)
            col += 1
            if col >= 4:
                col = 0
                row += 1

    def lighten_color(self, color):
        color_map = {
            '#2e7d32': '#4caf50', '#1b5e20': '#2e7d32', '#43a047': '#66bb6a', '#388e3c': '#4caf50',
            '#27ae60': '#2ecc71', '#1a73e8': '#4285f4', '#3498db': '#5dade2', '#e67e22': '#f39c12',
            '#16a085': '#1abc9c', '#c0392b': '#e74c3c', '#8e44ad': '#9b59b6', '#f39c12': '#f1c40f',
            '#1abc9c': '#16a085', '#34495e': '#2c3e50', '#9c27b0': '#ab47bc', '#009688': '#26a69a', '#3f51b5': '#5c6bc0'
        }
        return color_map.get(color, color)

    def show_dashboard_stats(self, parent):
        stats_frame = tk.Frame(parent, bg='#e8f5e9', height=120)
        stats_frame.pack(fill='x', padx=20, pady=20)
        today = datetime.now().date()
        total_products = self.db.fetch_one("SELECT COUNT(*) FROM products")[0]
        low_stock = self.db.fetch_one("SELECT COUNT(*) FROM products WHERE quantity <= min_stock")[0]
        today_sales = self.db.fetch_one('''SELECT COALESCE(SUM(net_amount), 0), COUNT(*) FROM sales WHERE DATE(sale_date) = ?''', (today,))
        total_sales = self.db.fetch_one("SELECT COALESCE(SUM(net_amount), 0) FROM sales")[0]
        stats = [
            ("📦 Total Products", f"{total_products:,}", f"{low_stock} Low Stock", self.colors['info']),
            ("💰 Today's Sales", f"{self.config.config['currency']} {today_sales[0]:,.2f}", f"{today_sales[1]} Transactions", self.colors['success']),
            ("📊 Total Revenue", f"{self.config.config['currency']} {total_sales:,.2f}", "Lifetime Sales", self.colors['primary']),
            ("🎯 Daily Target", f"{self.config.config['currency']} 100,000", "Today's Goal", self.colors['accent']),
        ]
        for title, value, subtitle, color in stats:
            card = tk.Frame(stats_frame, bg='white', relief='raised', bd=0, highlightbackground='#d0d0d0', highlightthickness=1)
            card.pack(side='left', expand=True, fill='both', padx=10, pady=5)
            tk.Label(card, text=title, font=('Segoe UI',11), bg='white', fg=self.colors['secondary']).pack(pady=(15,5))
            tk.Label(card, text=value, font=('Segoe UI',20,'bold'), bg='white', fg=color).pack(pady=5)
            tk.Label(card, text=subtitle, font=('Segoe UI',10), bg='white', fg=self.colors['secondary']).pack(pady=(5,15))

    # ---------- INVENTORY (green buttons) ----------
    def show_inventory(self):
        inv_window = tk.Toplevel(self.root)
        inv_window.title("📦 Inventory Management")
        inv_window.state('zoomed')
        inv_window.configure(bg='#e8f5e9')
        header = tk.Frame(inv_window, bg=self.colors['primary'], height=60)
        header.pack(fill='x')
        tk.Label(header, text="📦 INVENTORY MANAGEMENT", font=('Segoe UI', 20, 'bold'), bg=self.colors['primary'], fg='white').pack(pady=15)
        main_frame = tk.Frame(inv_window, bg='#e8f5e9')
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)
        filter_frame = tk.Frame(main_frame, bg='white', relief='raised', bd=0)
        filter_frame.pack(fill='x', padx=10, pady=10)
        filter_frame.config(highlightbackground='#d0d0d0', highlightthickness=1)
        search_frame = tk.Frame(filter_frame, bg='white')
        search_frame.pack(fill='x', padx=15, pady=10)
        tk.Label(search_frame, text="🔍 Search:", font=('Segoe UI',11,'bold'), bg='white').pack(side='left', padx=5)
        search_entry = tk.Entry(search_frame, font=('Segoe UI',11), width=30, relief='solid', bd=1)
        search_entry.pack(side='left', padx=5, ipady=5)
        tk.Label(search_frame, text="Category:", font=('Segoe UI',11,'bold'), bg='white').pack(side='left', padx=(20,5))
        categories = self.db.fetch_all("SELECT DISTINCT category FROM products ORDER BY category")
        category_list = [cat[0] for cat in categories]
        category_combo = ttk.Combobox(search_frame, values=['All'] + category_list, width=20)
        category_combo.set('All')
        category_combo.pack(side='left', padx=5)
        stats_label = tk.Label(search_frame, text="", font=('Segoe UI',10,'bold'), bg='white', fg=self.colors['success'])
        stats_label.pack(side='right', padx=20)
        tree_frame = tk.Frame(main_frame, bg='#e8f5e9')
        tree_frame.pack(fill='both', expand=True, padx=10, pady=10)
        vsb = ttk.Scrollbar(tree_frame, orient='vertical')
        hsb = ttk.Scrollbar(tree_frame, orient='horizontal')
        columns = ('ID','Barcode','Name','Category','Buying Price','Selling Price','Stock','Min Stock','Unit','Supplier')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', yscrollcommand=vsb.set, xscrollcommand=hsb.set, height=25)
        vsb.config(command=tree.yview)
        hsb.config(command=tree.xview)
        col_widths = {'ID':60,'Barcode':140,'Name':250,'Category':120,'Buying Price':120,'Selling Price':120,'Stock':80,'Min Stock':80,'Unit':70,'Supplier':150}
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=col_widths.get(col,100))
        tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        tree.tag_configure('low_stock', background='#ffebee')
        tree.tag_configure('critical_stock', background='#ffcdd2')

        def load_products():
            for item in tree.get_children(): tree.delete(item)
            search_term = search_entry.get().lower()
            selected_category = category_combo.get()
            if selected_category != 'All':
                products = self.db.fetch_all("""SELECT id, barcode, name, category, buying_price, selling_price, quantity, min_stock, unit, supplier 
                    FROM products WHERE LOWER(name) LIKE ? AND category = ? ORDER BY name""", (f'%{search_term}%', selected_category))
            else:
                products = self.db.fetch_all("""SELECT id, barcode, name, category, buying_price, selling_price, quantity, min_stock, unit, supplier 
                    FROM products WHERE LOWER(name) LIKE ? ORDER BY name""", (f'%{search_term}%',))
            for prod in products:
                stock_status = 'low_stock' if prod[6] <= prod[7] else ''
                if prod[6] == 0: stock_status = 'critical_stock'
                values = list(prod)
                values[4] = f"{self.config.config['currency']} {prod[4]:.2f}" if prod[4] else "N/A"
                values[5] = f"{self.config.config['currency']} {prod[5]:.2f}"
                tree.insert('', 'end', values=values, tags=(stock_status,))
            stats_label.config(text=f"📊 Total Products: {len(products)}")
        search_entry.bind('<KeyRelease>', lambda e: load_products())
        category_combo.bind('<<ComboboxSelected>>', lambda e: load_products())
        btn_frame = tk.Frame(main_frame, bg='#e8f5e9')
        btn_frame.pack(fill='x', padx=10, pady=10)
        tk.Button(btn_frame, text="➕ Add Product", command=self.add_product_dialog, bg=self.colors['success'], fg='white', font=('Segoe UI',11,'bold'), relief='flat', padx=20, pady=8).pack(side='left', padx=5)
        tk.Button(btn_frame, text="✏️ Edit Product", command=lambda: self.edit_product_dialog(tree), bg=self.colors['info'], fg='white', font=('Segoe UI',11,'bold'), relief='flat', padx=20, pady=8).pack(side='left', padx=5)
        tk.Button(btn_frame, text="🔄 Refresh", command=load_products, bg=self.colors['primary'], fg='white', font=('Segoe UI',11,'bold'), relief='flat', padx=20, pady=8).pack(side='left', padx=5)
        tk.Button(btn_frame, text="📊 Export to Excel", command=self.export_inventory, bg=self.colors['purple'], fg='white', font=('Segoe UI',11,'bold'), relief='flat', padx=20, pady=8).pack(side='right', padx=5)
        summary_frame = tk.Frame(main_frame, bg='white', relief='raised', bd=0)
        summary_frame.pack(fill='x', padx=10, pady=10)
        summary_frame.config(highlightbackground='#d0d0d0', highlightthickness=1)
        total_value = self.db.fetch_one("SELECT COALESCE(SUM(quantity * selling_price), 0) FROM products")[0]
        total_cost = self.db.fetch_one("SELECT COALESCE(SUM(quantity * buying_price), 0) FROM products")[0]
        potential_profit = total_value - total_cost
        tk.Label(summary_frame, text=f"💰 Inventory Value: {self.config.config['currency']} {total_value:,.2f}", font=('Segoe UI',12,'bold'), bg='white', fg=self.colors['success']).pack(side='left', padx=20, pady=10)
        tk.Label(summary_frame, text=f"📊 Potential Profit: {self.config.config['currency']} {potential_profit:,.2f}", font=('Segoe UI',12,'bold'), bg='white', fg=self.colors['info']).pack(side='left', padx=20, pady=10)
        load_products()

    def add_product_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Add New Product")
        dialog.geometry("500x550")
        dialog.configure(bg='white')
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (500 // 2)
        y = (dialog.winfo_screenheight() // 2) - (550 // 2)
        dialog.geometry(f'500x550+{x}+{y}')
        fields = {}
        labels = [("Product Name:", "name", True), ("Barcode:", "barcode", False), ("Category:", "category", True),
                  ("Buying Price (Ksh):", "buying_price", True), ("Selling Price (Ksh):", "selling_price", True),
                  ("Quantity:", "quantity", True), ("Minimum Stock:", "min_stock", True), ("Unit:", "unit", True),
                  ("Supplier:", "supplier", False)]
        for i, (label, key, required) in enumerate(labels):
            tk.Label(dialog, text=label, font=('Segoe UI',10,'bold'), bg='white', fg=self.colors['dark']).grid(row=i, column=0, padx=20, pady=8, sticky='w')
            entry = tk.Entry(dialog, font=('Segoe UI',11), width=30, relief='solid', bd=1)
            entry.grid(row=i, column=1, padx=20, pady=8, ipady=5)
            fields[key] = entry
            if key == 'unit': entry.insert(0, 'pcs')
            elif key == 'min_stock': entry.insert(0, '5')
        def save():
            try:
                name = fields['name'].get().strip()
                if not name:
                    messagebox.showerror("Error", "Product name required")
                    return
                selling_price = float(fields['selling_price'].get())
                if selling_price <= 0:
                    messagebox.showerror("Error", "Selling price must be > 0")
                    return
                barcode = fields['barcode'].get().strip()
                if not barcode:
                    barcode = f"890{random.randint(1000000000,9999999999)}"
                self.db.execute_query('''INSERT INTO products (barcode, name, category, buying_price, selling_price, quantity, min_stock, unit, supplier)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (barcode, name, fields['category'].get(), float(fields['buying_price'].get() or 0), selling_price,
                     int(fields['quantity'].get()), int(fields['min_stock'].get()), fields['unit'].get(), fields['supplier'].get()))
                self.db.log_action(self.current_user['username'], "INSERT", "products", name, "", f"Added product {name}")
                messagebox.showinfo("Success", "Product added!")
                dialog.destroy()
                self.show_inventory()
            except ValueError as e:
                messagebox.showerror("Error", f"Invalid: {str(e)}")
        tk.Button(dialog, text="Save Product", command=save, bg=self.colors['success'], fg='white', font=('Segoe UI',12,'bold'), relief='flat', padx=30, pady=10).grid(row=len(labels), column=0, columnspan=2, pady=20)

    def edit_product_dialog(self, tree):
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Select a product to edit")
            return
        values = tree.item(selected[0])['values']
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Product")
        dialog.geometry("500x550")
        dialog.configure(bg='white')
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (500 // 2)
        y = (dialog.winfo_screenheight() // 2) - (550 // 2)
        dialog.geometry(f'500x550+{x}+{y}')
        fields = {}
        labels = [("Product Name:", "name"), ("Barcode:", "barcode"), ("Category:", "category"),
                  ("Buying Price (Ksh):", "buying_price"), ("Selling Price (Ksh):", "selling_price"),
                  ("Quantity:", "quantity"), ("Minimum Stock:", "min_stock"), ("Unit:", "unit"), ("Supplier:", "supplier")]
        for i, (label, key) in enumerate(labels):
            tk.Label(dialog, text=label, font=('Segoe UI',10,'bold'), bg='white', fg=self.colors['dark']).grid(row=i, column=0, padx=20, pady=8, sticky='w')
            entry = tk.Entry(dialog, font=('Segoe UI',11), width=30, relief='solid', bd=1)
            entry.grid(row=i, column=1, padx=20, pady=8, ipady=5)
            fields[key] = entry
            if key == 'name': entry.insert(0, values[2])
            elif key == 'barcode': entry.insert(0, values[1])
            elif key == 'category': entry.insert(0, values[3])
            elif key == 'buying_price':
                price = str(values[4]).replace(self.config.config['currency'], '').strip()
                entry.insert(0, price)
            elif key == 'selling_price':
                price = str(values[5]).replace(self.config.config['currency'], '').strip()
                entry.insert(0, price)
            elif key == 'quantity': entry.insert(0, values[6])
            elif key == 'min_stock': entry.insert(0, values[7])
            elif key == 'unit': entry.insert(0, values[8])
            elif key == 'supplier': entry.insert(0, values[9] if len(values)>9 else '')
        def update():
            try:
                self.db.execute_query('''UPDATE products SET name=?, barcode=?, category=?, buying_price=?, selling_price=?, quantity=?, min_stock=?, unit=?, supplier=? WHERE id=?''',
                    (fields['name'].get(), fields['barcode'].get(), fields['category'].get(),
                     float(fields['buying_price'].get() or 0), float(fields['selling_price'].get()),
                     int(fields['quantity'].get()), int(fields['min_stock'].get()), fields['unit'].get(), fields['supplier'].get(), values[0]))
                self.db.log_action(self.current_user['username'], "UPDATE", "products", values[0], "", f"Updated product {fields['name'].get()}")
                messagebox.showinfo("Success", "Product updated!")
                dialog.destroy()
                self.show_inventory()
            except ValueError as e:
                messagebox.showerror("Error", f"Invalid: {str(e)}")
        tk.Button(dialog, text="Update Product", command=update, bg=self.colors['success'], fg='white', font=('Segoe UI',12,'bold'), relief='flat', padx=30, pady=10).grid(row=len(labels), column=0, columnspan=2, pady=20)

    def export_inventory(self):
        try:
            filename = f"inventory_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            products = self.db.fetch_all("SELECT * FROM products")
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['ID','Barcode','Name','Category','Buying Price','Selling Price','Quantity','Min Stock','Unit','Supplier','Created At'])
                writer.writerows(products)
            messagebox.showinfo("Success", f"Exported to {filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {str(e)}")

    # ---------- POINT OF SALE (green theme) ----------
    def show_pos(self):
        pos_window = tk.Toplevel(self.root)
        pos_window.title("🛒 Point of Sale")
        pos_window.state('zoomed')
        pos_window.configure(bg='#e8f5e9')
        header = tk.Frame(pos_window, bg=self.colors['primary'], height=60)
        header.pack(fill='x')
        tk.Label(header, text="🛒 POINT OF SALE", font=('Segoe UI', 20, 'bold'), bg=self.colors['primary'], fg='white').pack(pady=15)
        main_frame = tk.Frame(pos_window, bg='#e8f5e9')
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)
        main_frame.grid_columnconfigure(0, weight=3)
        main_frame.grid_columnconfigure(1, weight=2)
        main_frame.grid_rowconfigure(0, weight=1)

        products_panel = tk.Frame(main_frame, bg='white', relief='raised', bd=0)
        products_panel.grid(row=0, column=0, sticky='nsew', padx=(0,10))
        products_panel.grid_rowconfigure(1, weight=1)
        products_panel.grid_columnconfigure(0, weight=1)
        tk.Label(products_panel, text="📦 Products", font=('Segoe UI',16,'bold'), bg='white', fg=self.colors['primary']).grid(row=0, column=0, pady=10)

        search_frame = tk.Frame(products_panel, bg='white')
        search_frame.grid(row=1, column=0, sticky='ew', padx=10, pady=5)
        search_frame.grid_columnconfigure(1, weight=1)
        tk.Label(search_frame, text="🔍 Search:", bg='white', font=('Segoe UI',11)).grid(row=0, column=0, padx=5)
        search_entry = tk.Entry(search_frame, font=('Segoe UI',11), relief='solid', bd=1)
        search_entry.grid(row=0, column=1, sticky='ew', padx=5, ipady=5)
        tk.Label(search_frame, text="📷 Barcode:", bg='white', font=('Segoe UI',11)).grid(row=0, column=2, padx=5)
        barcode_entry = tk.Entry(search_frame, font=('Segoe UI',11), relief='solid', bd=1, width=20)
        barcode_entry.grid(row=0, column=3, padx=5, ipady=5)

        tree_frame = tk.Frame(products_panel, bg='white')
        tree_frame.grid(row=2, column=0, sticky='nsew', padx=10, pady=10)
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        vsb = ttk.Scrollbar(tree_frame, orient='vertical')
        products_tree = ttk.Treeview(tree_frame, columns=('ID','Name','Price','Stock'), show='headings', yscrollcommand=vsb.set, height=25)
        vsb.config(command=products_tree.yview)
        products_tree.heading('ID', text='ID')
        products_tree.heading('Name', text='Product Name')
        products_tree.heading('Price', text=f'Price ({self.config.config["currency"]})')
        products_tree.heading('Stock', text='Stock')
        products_tree.column('ID', width=50)
        products_tree.column('Name', width=350)
        products_tree.column('Price', width=100)
        products_tree.column('Stock', width=80)
        products_tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')

        cart_panel = tk.Frame(main_frame, bg='white', relief='raised', bd=0)
        cart_panel.grid(row=0, column=1, sticky='nsew', padx=(10,0))
        cart_panel.grid_rowconfigure(1, weight=1)
        cart_panel.grid_columnconfigure(0, weight=1)
        tk.Label(cart_panel, text="🛒 Shopping Cart", font=('Segoe UI',16,'bold'), bg='white', fg=self.colors['success']).grid(row=0, column=0, pady=10)

        cart_frame = tk.Frame(cart_panel, bg='white')
        cart_frame.grid(row=1, column=0, sticky='nsew', padx=10, pady=10)
        cart_frame.grid_rowconfigure(0, weight=1)
        cart_frame.grid_columnconfigure(0, weight=1)
        cart_vsb = ttk.Scrollbar(cart_frame, orient='vertical')
        cart_tree = ttk.Treeview(cart_frame, columns=('Name','Qty','Price','Total'), show='headings', yscrollcommand=cart_vsb.set, height=20)
        cart_vsb.config(command=cart_tree.yview)
        for col in ('Name','Qty','Price','Total'):
            cart_tree.heading(col, text=col)
            cart_tree.column(col, width=140)
        cart_tree.grid(row=0, column=0, sticky='nsew')
        cart_vsb.grid(row=0, column=1, sticky='ns')

        customer_frame = tk.Frame(cart_panel, bg=self.colors['light'], relief='sunken', bd=1)
        customer_frame.grid(row=2, column=0, sticky='ew', padx=10, pady=5)
        tk.Label(customer_frame, text="Customer Name:", bg=self.colors['light'], font=('Segoe UI',10)).pack(side='left', padx=5)
        customer_name_entry = tk.Entry(customer_frame, font=('Segoe UI',10), width=20)
        customer_name_entry.pack(side='left', padx=5)
        tk.Label(customer_frame, text="Phone:", bg=self.colors['light'], font=('Segoe UI',10)).pack(side='left', padx=5)
        customer_phone_entry = tk.Entry(customer_frame, font=('Segoe UI',10), width=15)
        customer_phone_entry.pack(side='left', padx=5)

        total_frame = tk.Frame(cart_panel, bg='white')
        total_frame.grid(row=3, column=0, sticky='ew', padx=10, pady=10)
        tk.Label(total_frame, text="TOTAL:", font=('Segoe UI',20,'bold'), bg='white', fg=self.colors['dark']).pack(side='left')
        total_label = tk.Label(total_frame, text=f"{self.config.config['currency']} 0.00", font=('Segoe UI',20,'bold'), bg='white', fg=self.colors['success'])
        total_label.pack(side='right')

        btn_frame = tk.Frame(cart_panel, bg='white')
        btn_frame.grid(row=4, column=0, sticky='ew', padx=10, pady=10)

        def load_products():
            for item in products_tree.get_children(): products_tree.delete(item)
            for p in self.db.fetch_all("SELECT id, name, selling_price, quantity FROM products WHERE quantity > 0 ORDER BY name"):
                products_tree.insert('', 'end', values=p[:4])
        def search_products_pos():
            term = search_entry.get().lower()
            for item in products_tree.get_children(): products_tree.delete(item)
            for p in self.db.fetch_all("SELECT id, name, selling_price, quantity FROM products WHERE LOWER(name) LIKE ? AND quantity > 0", (f'%{term}%',)):
                products_tree.insert('', 'end', values=p[:4])
        def scan_barcode():
            bc = barcode_entry.get().strip()
            if bc:
                prod = self.db.fetch_one("SELECT id, name, selling_price, quantity FROM products WHERE barcode=? AND quantity>0", (bc,))
                if prod:
                    qty = simpledialog.askinteger("Quantity", f"Quantity for {prod[1]}:", minvalue=1, maxvalue=prod[3])
                    if qty:
                        self.cart.append({'id':prod[0],'name':prod[1],'quantity':qty,'price':float(prod[2]),'total':float(prod[2])*qty})
                        update_cart()
                        barcode_entry.delete(0, tk.END)
                else:
                    messagebox.showerror("Error", "Product not found!")
                    barcode_entry.delete(0, tk.END)
        def update_cart():
            for item in cart_tree.get_children(): cart_tree.delete(item)
            total = 0
            for item in self.cart:
                cart_tree.insert('', 'end', values=(item['name'], item['quantity'], f"{self.config.config['currency']} {item['price']:.2f}", f"{self.config.config['currency']} {item['total']:.2f}"))
                total += item['total']
            total_label.config(text=f"{self.config.config['currency']} {total:.2f}")
        def add_to_cart():
            sel = products_tree.selection()
            if not sel: return
            vals = products_tree.item(sel[0])['values']
            pid, name, price, stock = vals
            qty = simpledialog.askinteger("Quantity", f"Quantity for {name}:", minvalue=1, maxvalue=stock)
            if qty:
                self.cart.append({'id':pid, 'name':name, 'quantity':qty, 'price':float(price), 'total':float(price)*qty})
                update_cart()
        def remove_from_cart():
            sel = cart_tree.selection()
            if sel:
                idx = cart_tree.index(sel[0])
                self.cart.pop(idx)
                update_cart()
        def clear_cart():
            self.cart = []
            update_cart()
            customer_name_entry.delete(0, tk.END)
            customer_phone_entry.delete(0, tk.END)
        def checkout():
            if not self.cart:
                messagebox.showwarning("Warning", "Cart is empty!")
                return
            subtotal = sum(i['total'] for i in self.cart)
            discount_amount = 0
            manual_discount = simpledialog.askfloat("Discount", "Apply additional discount (%)", minvalue=0, maxvalue=100)
            if manual_discount:
                discount_amount += subtotal * (manual_discount / 100)
            tax_amount = subtotal * 0.16
            net_total = subtotal - discount_amount + tax_amount
            invoice_no = f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100,999)}"
            try:
                self.db.execute_query('''INSERT INTO sales (invoice_no, customer_name, customer_phone, total_amount, discount, tax, net_amount, payment_method, cashier)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (invoice_no, customer_name_entry.get(), customer_phone_entry.get(), subtotal, discount_amount, tax_amount, net_total, 'Cash', self.current_user['username']))
                for item in self.cart:
                    self.db.execute_query('''INSERT INTO sale_items (invoice_no, product_id, product_name, quantity, unit_price, total)
                        VALUES (?, ?, ?, ?, ?, ?)''', (invoice_no, item['id'], item['name'], item['quantity'], item['price'], item['total']))
                    self.db.execute_query("UPDATE products SET quantity = quantity - ? WHERE id = ?", (item['quantity'], item['id']))
                self.db.log_action(self.current_user['username'], "SALE", "sales", invoice_no, "", f"Total: {net_total}")
                receipt = f"\n{'='*40}\n{self.config.config['company_name']}\nInvoice: {invoice_no}\nDate: {datetime.now()}\nCashier: {self.current_user['full_name']}\nTotal: {self.config.config['currency']} {net_total:.2f}\n{'='*40}\n"
                messagebox.showinfo("✅ Sale Complete", receipt)
                self.cart = []
                update_cart()
                load_products()
                customer_name_entry.delete(0, tk.END)
                customer_phone_entry.delete(0, tk.END)
                pos_window.destroy()
                self.show_pos()
            except Exception as e:
                messagebox.showerror("Error", str(e))

        tk.Button(btn_frame, text="➕ Add to Cart", command=add_to_cart, bg=self.colors['success'], fg='white', font=('Segoe UI',11,'bold'), relief='flat', padx=15, pady=5).pack(side='left', padx=5)
        tk.Button(btn_frame, text="❌ Remove", command=remove_from_cart, bg=self.colors['danger'], fg='white', font=('Segoe UI',11,'bold'), relief='flat', padx=15, pady=5).pack(side='left', padx=5)
        tk.Button(btn_frame, text="🗑 Clear Cart", command=clear_cart, bg=self.colors['warning'], fg='white', font=('Segoe UI',11,'bold'), relief='flat', padx=15, pady=5).pack(side='left', padx=5)
        tk.Button(btn_frame, text="💳 Checkout", command=checkout, bg=self.colors['primary'], fg='white', font=('Segoe UI',11,'bold'), relief='flat', padx=30, pady=5).pack(side='right', padx=5)

        products_tree.bind('<Double-Button-1>', lambda e: add_to_cart())
        search_entry.bind('<KeyRelease>', lambda e: search_products_pos())
        barcode_entry.bind('<Return>', lambda e: scan_barcode())
        load_products()

    # ---------- REPORTS (green button) ----------
    def show_reports(self):
        report_window = tk.Toplevel(self.root)
        report_window.title("📊 Reports & Analytics")
        report_window.state('zoomed')
        report_window.configure(bg='#e8f5e9')
        header = tk.Frame(report_window, bg=self.colors['primary'], height=60)
        header.pack(fill='x')
        tk.Label(header, text="📊 REPORTS & ANALYTICS", font=('Segoe UI',20,'bold'), bg=self.colors['primary'], fg='white').pack(pady=15)
        main_frame = tk.Frame(report_window, bg='#e8f5e9')
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)
        date_frame = tk.Frame(main_frame, bg='white', relief='raised', bd=0)
        date_frame.pack(fill='x', padx=10, pady=10)
        date_frame.config(highlightbackground='#d0d0d0', highlightthickness=1)
        tk.Label(date_frame, text="From Date:", font=('Segoe UI',12), bg='white').pack(side='left', padx=15, pady=10)
        from_date = tk.Entry(date_frame, font=('Segoe UI',12), width=15, relief='solid', bd=1)
        from_date.insert(0, (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        from_date.pack(side='left', padx=5, pady=10, ipady=4)
        tk.Label(date_frame, text="To Date:", font=('Segoe UI',12), bg='white').pack(side='left', padx=15, pady=10)
        to_date = tk.Entry(date_frame, font=('Segoe UI',12), width=15, relief='solid', bd=1)
        to_date.insert(0, datetime.now().strftime('%Y-%m-%d'))
        to_date.pack(side='left', padx=5, pady=10, ipady=4)
        report_text = scrolledtext.ScrolledText(main_frame, font=('Courier',10), height=30)
        report_text.pack(fill='both', expand=True, padx=10, pady=10)

        def generate_report():
            report_text.delete(1.0, tk.END)
            start = from_date.get()
            end = to_date.get()
            sales = self.db.fetch_all('''SELECT DATE(sale_date), COUNT(*), SUM(net_amount), AVG(net_amount)
                FROM sales WHERE DATE(sale_date) BETWEEN ? AND ? GROUP BY DATE(sale_date) ORDER BY sale_date''', (start, end))
            top = self.db.fetch_all('''SELECT p.name, SUM(si.quantity), SUM(si.total)
                FROM sale_items si JOIN products p ON si.product_id = p.id JOIN sales s ON si.invoice_no = s.invoice_no
                WHERE DATE(s.sale_date) BETWEEN ? AND ? GROUP BY si.product_id ORDER BY SUM(si.quantity) DESC LIMIT 10''', (start, end))
            payments = self.db.fetch_all('''SELECT payment_method, COUNT(*), SUM(net_amount)
                FROM sales WHERE DATE(sale_date) BETWEEN ? AND ? GROUP BY payment_method''', (start, end))
            report_text.insert(tk.END, "="*80 + "\n")
            report_text.insert(tk.END, f"{self.config.config['company_name']} - SALES REPORT\nPeriod: {start} to {end}\n")
            report_text.insert(tk.END, "="*80 + "\n\n")
            report_text.insert(tk.END, "📊 DAILY SALES\n")
            report_text.insert(tk.END, f"{'Date':<12} {'Count':<8} {'Total':<15} {'Average':<12}\n")
            report_text.insert(tk.END, "-"*80 + "\n")
            total_sales = 0
            for s in sales:
                report_text.insert(tk.END, f"{s[0]:<12} {s[1]:<8} {self.config.config['currency']} {s[2]:<14,.2f} {self.config.config['currency']} {s[3]:<10,.2f}\n")
                total_sales += s[2]
            report_text.insert(tk.END, f"\nTOTAL REVENUE: {self.config.config['currency']} {total_sales:,.2f}\n\n")
            report_text.insert(tk.END, "🏆 TOP PRODUCTS\n")
            for p in top:
                report_text.insert(tk.END, f"{p[0][:35]:35} {p[1]:5} units - {self.config.config['currency']} {p[2]:,.2f}\n")
            report_text.insert(tk.END, "\n💳 PAYMENT METHODS\n")
            for pm in payments:
                report_text.insert(tk.END, f"{pm[0]:10} : {pm[1]} transactions, {self.config.config['currency']} {pm[2]:,.2f}\n")
        tk.Button(date_frame, text="📊 Generate Report", command=generate_report, bg=self.colors['success'], fg='white', font=('Segoe UI',11,'bold'), relief='flat', padx=20, pady=8).pack(side='left', padx=20, pady=10)

    # ---------- ADVANCED CHARTS (green line) ----------
    def show_advanced_charts(self):
        chart_window = tk.Toplevel(self.root)
        chart_window.title("📈 Advanced Analytics")
        chart_window.geometry("800x600")
        chart_window.configure(bg='#e8f5e9')
        data = self.db.fetch_all("""SELECT DATE(sale_date), SUM(net_amount) FROM sales WHERE sale_date >= date('now', '-30 days') GROUP BY DATE(sale_date) ORDER BY sale_date""")
        if not data:
            messagebox.showinfo("Info","No sales data")
            return
        dates = [row[0] for row in data]
        amounts = [row[1] for row in data]
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10,4))
        ax1.plot(dates, amounts, marker='o', color=self.colors['primary'])
        ax1.set_title('Daily Sales Trend (Last 30 Days)')
        ax1.set_xlabel('Date')
        ax1.set_ylabel(f'Revenue ({self.config.config["currency"]})')
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')
        cat_data = self.db.fetch_all("""SELECT p.category, SUM(si.total) FROM sale_items si JOIN products p ON si.product_id = p.id GROUP BY p.category ORDER BY SUM(si.total) DESC LIMIT 5""")
        categories = [c[0] for c in cat_data]
        sales_by_cat = [c[1] for c in cat_data]
        ax2.pie(sales_by_cat, labels=categories, autopct='%1.1f%%', startangle=90)
        ax2.set_title('Top 5 Categories by Revenue')
        plt.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=chart_window)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    # ---------- CUSTOMERS ----------
    def show_customers(self):
        win = tk.Toplevel(self.root)
        win.title("👥 Customer Management")
        win.geometry("1000x600")
        win.configure(bg='#e8f5e9')
        header = tk.Frame(win, bg=self.colors['primary'], height=50)
        header.pack(fill='x')
        tk.Label(header, text="👥 Customer Management", font=('Segoe UI',18,'bold'), bg=self.colors['primary'], fg='white').pack(pady=10)
        main = tk.Frame(win, bg='#e8f5e9')
        main.pack(fill='both', expand=True, padx=20, pady=20)
        tree = ttk.Treeview(main, columns=('Name','Phone','Visits','Total Spent'), show='headings', height=18)
        for col in ('Name','Phone','Visits','Total Spent'): tree.heading(col, text=col); tree.column(col, width=220)
        customers = self.db.fetch_all('''SELECT DISTINCT customer_name, customer_phone, COUNT(*) as visits, SUM(net_amount) as total_spent
            FROM sales WHERE customer_name IS NOT NULL AND customer_name != '' GROUP BY customer_name, customer_phone ORDER BY total_spent DESC''')
        for c in customers:
            tree.insert('', 'end', values=(c[0], c[1] or 'N/A', c[2], f"{self.config.config['currency']} {c[3]:,.2f}"))
        tree.pack(fill='both', expand=True, padx=10, pady=10)

    # ---------- SUPPLIERS ----------
    def show_suppliers(self):
        win = tk.Toplevel(self.root)
        win.title("🏭 Supplier Management")
        win.geometry("1000x600")
        win.configure(bg='#e8f5e9')
        header = tk.Frame(win, bg=self.colors['primary'], height=50)
        header.pack(fill='x')
        tk.Label(header, text="🏭 Supplier Management", font=('Segoe UI',18,'bold'), bg=self.colors['primary'], fg='white').pack(pady=10)
        main = tk.Frame(win, bg='#e8f5e9')
        main.pack(fill='both', expand=True, padx=20, pady=20)
        tree = ttk.Treeview(main, columns=('ID','Name','Contact Person','Phone','Email'), show='headings', height=18)
        for col in ('ID','Name','Contact Person','Phone','Email'): tree.heading(col, text=col); tree.column(col, width=180)
        suppliers = self.db.fetch_all("SELECT id, name, contact_person, phone, email FROM suppliers")
        for s in suppliers:
            tree.insert('', 'end', values=s)
        tree.pack(fill='both', expand=True, padx=10, pady=10)

    # ---------- USERS (admin only) ----------
    def show_users(self):
        if self.current_user['role'] != 'admin':
            messagebox.showerror("Access Denied", "Admin access required!")
            return
        win = tk.Toplevel(self.root)
        win.title("👤 User Management")
        win.geometry("900x550")
        win.configure(bg='#e8f5e9')
        header = tk.Frame(win, bg=self.colors['primary'], height=50)
        header.pack(fill='x')
        tk.Label(header, text="👤 User Management", font=('Segoe UI',18,'bold'), bg=self.colors['primary'], fg='white').pack(pady=10)
        main = tk.Frame(win, bg='#e8f5e9')
        main.pack(fill='both', expand=True, padx=20, pady=20)
        tree = ttk.Treeview(main, columns=('ID','Username','Role','Full Name'), show='headings', height=15)
        for col in ('ID','Username','Role','Full Name'): tree.heading(col, text=col); tree.column(col, width=200)
        users = self.db.fetch_all("SELECT id, username, role, full_name FROM users")
        for u in users:
            tree.insert('', 'end', values=u)
        tree.pack(fill='both', expand=True, padx=10, pady=10)

    # ---------- DASHBOARD ----------
    def show_dashboard(self):
        win = tk.Toplevel(self.root)
        win.title("📈 Dashboard")
        win.state('zoomed')
        win.configure(bg='#e8f5e9')
        header = tk.Frame(win, bg=self.colors['primary'], height=60)
        header.pack(fill='x')
        tk.Label(header, text="📈 ANALYTICS DASHBOARD", font=('Segoe UI',20,'bold'), bg=self.colors['primary'], fg='white').pack(pady=15)
        main = tk.Frame(win, bg='#e8f5e9')
        main.pack(fill='both', expand=True, padx=20, pady=20)
        stats_frame = tk.Frame(main, bg='#e8f5e9')
        stats_frame.pack(fill='x', pady=20)
        today = datetime.now().date()
        total_products = self.db.fetch_one("SELECT COUNT(*) FROM products")[0]
        low_stock = self.db.fetch_one("SELECT COUNT(*) FROM products WHERE quantity <= min_stock")[0]
        today_sales = self.db.fetch_one('''SELECT COALESCE(SUM(net_amount),0), COUNT(*) FROM sales WHERE DATE(sale_date) = ?''', (today,))
        total_sales = self.db.fetch_one("SELECT COALESCE(SUM(net_amount),0) FROM sales")[0]
        stats = [
            ("📦 Total Products", f"{total_products:,}", f"{low_stock} Low Stock", self.colors['info']),
            ("💰 Today's Sales", f"{self.config.config['currency']} {today_sales[0]:,.2f}", f"{today_sales[1]} Transactions", self.colors['success']),
            ("📊 Total Revenue", f"{self.config.config['currency']} {total_sales:,.2f}", "Lifetime Sales", self.colors['primary']),
            ("🏪 Active Branches", "1", "Main Store", self.colors['accent']),
        ]
        for i, (title, val, sub, color) in enumerate(stats):
            card = tk.Frame(stats_frame, bg='white', relief='raised', bd=0)
            card.grid(row=0, column=i, padx=15, pady=10, sticky='nsew')
            card.config(highlightbackground='#d0d0d0', highlightthickness=1)
            tk.Label(card, text=title, font=('Segoe UI',12), bg='white', fg=self.colors['secondary']).pack(pady=(15,5))
            tk.Label(card, text=val, font=('Segoe UI',20,'bold'), bg='white', fg=color).pack(pady=5)
            tk.Label(card, text=sub, font=('Segoe UI',10), bg='white', fg=self.colors['secondary']).pack(pady=(5,15))
        for i in range(4):
            stats_frame.grid_columnconfigure(i, weight=1)
        recent_frame = tk.LabelFrame(main, text="📋 Recent Transactions", font=('Segoe UI',14,'bold'), bg='white')
        recent_frame.pack(fill='both', expand=True, padx=10, pady=10)
        rec_tree = ttk.Treeview(recent_frame, columns=('Invoice','Customer','Amount','Date','Cashier'), show='headings', height=15)
        for col in ('Invoice','Customer','Amount','Date','Cashier'): rec_tree.heading(col, text=col); rec_tree.column(col, width=200)
        recent = self.db.fetch_all('''SELECT invoice_no, customer_name, net_amount, sale_date, cashier FROM sales ORDER BY sale_date DESC LIMIT 30''')
        for r in recent:
            rec_tree.insert('', 'end', values=(r[0], r[1] or 'Walk-in', f"{self.config.config['currency']} {r[2]:.2f}", r[3], r[4]))
        rec_tree.pack(fill='both', expand=True, padx=10, pady=10)

    # ---------- STOCK ALERTS ----------
    def show_stock_alerts(self):
        low = self.db.fetch_all("SELECT name, quantity, min_stock, supplier FROM products WHERE quantity <= min_stock ORDER BY quantity ASC")
        win = tk.Toplevel(self.root)
        win.title("🔍 Stock Alerts")
        win.state('zoomed')
        win.configure(bg='#e8f5e9')
        header = tk.Frame(win, bg=self.colors['warning'], height=60)
        header.pack(fill='x')
        tk.Label(header, text="🔍 STOCK ALERTS", font=('Segoe UI',20,'bold'), bg=self.colors['warning'], fg='white').pack(pady=15)
        main = tk.Frame(win, bg='#e8f5e9')
        main.pack(fill='both', expand=True, padx=20, pady=20)
        if low:
            summary = tk.Frame(main, bg='white', relief='raised', bd=0)
            summary.pack(fill='x', padx=10, pady=10)
            summary.config(highlightbackground='#d0d0d0', highlightthickness=1)
            critical = sum(1 for i in low if i[1]==0)
            urgent = sum(1 for i in low if 0<i[1]<=i[2]//2)
            warning = len(low)-critical-urgent
            tk.Label(summary, text=f"⚠️ Total Low Stock: {len(low)}", font=('Segoe UI',14,'bold'), bg='white', fg=self.colors['danger']).pack(side='left', padx=20, pady=10)
            tk.Label(summary, text=f"🔴 Critical: {critical}", font=('Segoe UI',12), bg='white', fg='#d93025').pack(side='left', padx=20, pady=10)
            tk.Label(summary, text=f"🟠 Urgent: {urgent}", font=('Segoe UI',12), bg='white', fg='#ff9800').pack(side='left', padx=20, pady=10)
            tk.Label(summary, text=f"🟡 Warning: {warning}", font=('Segoe UI',12), bg='white', fg='#f9ab00').pack(side='left', padx=20, pady=10)
            canvas = tk.Canvas(main, bg='#e8f5e9', highlightthickness=0)
            scroll = ttk.Scrollbar(main, orient='vertical', command=canvas.yview)
            scrollable = tk.Frame(canvas, bg='#e8f5e9')
            scrollable.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
            canvas.create_window((0,0), window=scrollable, anchor='nw')
            canvas.configure(yscrollcommand=scroll.set)
            for item in low:
                if item[1]==0: sev,col,bgcol = "CRITICAL",self.colors['danger'],'#ffebee'
                elif item[1]<=item[2]//2: sev,col,bgcol = "URGENT",'#ff9800','#fff3e0'
                else: sev,col,bgcol = "WARNING",self.colors['warning'],'#fff9c4'
                card = tk.Frame(scrollable, bg=bgcol, relief='raised', bd=1)
                card.pack(fill='x', padx=20, pady=5)
                card.config(highlightbackground='#d0d0d0', highlightthickness=1)
                tk.Label(card, text=f"📦 {item[0]}", font=('Segoe UI',13,'bold'), bg=bgcol, fg=self.colors['dark']).pack(side='left', padx=15, pady=10)
                tk.Label(card, text=f"Stock: {item[1]} units", font=('Segoe UI',11), bg=bgcol, fg=col).pack(side='left', padx=15, pady=10)
                tk.Label(card, text=f"Min: {item[2]}", font=('Segoe UI',11), bg=bgcol, fg=self.colors['secondary']).pack(side='left', padx=15, pady=10)
                tk.Label(card, text=sev, font=('Segoe UI',10,'bold'), bg=col, fg='white', padx=15, pady=5).pack(side='right', padx=15, pady=10)
                def reorder(p=item[0]):
                    messagebox.showinfo("Reorder", f"Reorder initiated for {p}\nSuggested Qty: {item[2]*2}")
                    with open("auto_po.txt","a") as f:
                        f.write(f"{datetime.now()}: Reorder {p} from {item[3] or 'Unknown'} - {item[2]*2} units\n")
                tk.Button(card, text="🔄 Reorder", command=reorder, bg=self.colors['primary'], fg='white', font=('Segoe UI',9), relief='flat', padx=10, pady=3).pack(side='right', padx=10)
            canvas.pack(side='left', fill='both', expand=True)
            scroll.pack(side='right', fill='y')
        else:
            tk.Label(main, text="✅ No low stock items found!", font=('Segoe UI',20,'bold'), fg='green', bg='#e8f5e9').pack(pady=100)

    # ---------- RETURNS ----------
    def show_returns(self):
        win = tk.Toplevel(self.root)
        win.title("🔄 Returns Management")
        win.geometry("600x450")
        win.configure(bg='#e8f5e9')
        win.transient(self.root)
        win.grab_set()
        x = (win.winfo_screenwidth()//2)-300
        y = (win.winfo_screenheight()//2)-225
        win.geometry(f'600x450+{x}+{y}')
        header = tk.Frame(win, bg='#8e44ad', height=50)
        header.pack(fill='x')
        tk.Label(header, text="🔄 Returns Management", font=('Segoe UI',18,'bold'), bg='#8e44ad', fg='white').pack(pady=10)
        main = tk.Frame(win, bg='#e8f5e9')
        main.pack(fill='both', expand=True, padx=30, pady=30)
        tk.Label(main, text="Enter Invoice Number:", font=('Segoe UI',12), bg='#e8f5e9').pack(pady=10)
        inv_entry = tk.Entry(main, font=('Segoe UI',12), width=30, relief='solid', bd=1)
        inv_entry.pack(pady=10, ipady=8)
        tk.Label(main, text="Reason for Return:", font=('Segoe UI',12), bg='#e8f5e9').pack(pady=10)
        reason = ttk.Combobox(main, values=['Damaged','Wrong item','Expired','Other'], width=27)
        reason.pack(pady=10)
        def process():
            inv = inv_entry.get()
            rsn = reason.get()
            if not inv:
                messagebox.showerror("Error","Invoice required")
                return
            sale = self.db.fetch_one("SELECT invoice_no, net_amount FROM sales WHERE invoice_no=?", (inv,))
            if sale:
                refund = sale[1] * 0.95
                msg = f"Return approved for {inv}\nRefund: {self.config.config['currency']} {refund:.2f}\nReason: {rsn}"
                messagebox.showinfo("Return Processed", msg)
                inv_entry.delete(0, tk.END)
                reason.set('')
            else:
                messagebox.showerror("Error","Invoice not found")
        tk.Button(main, text="Process Return", command=process, bg=self.colors['primary'], fg='white', font=('Segoe UI',12,'bold'), relief='flat', padx=40, pady=10).pack(pady=20)

    # ---------- LOYALTY ----------
    def show_loyalty(self):
        win = tk.Toplevel(self.root)
        win.title("💎 Loyalty Program")
        win.geometry("1000x600")
        win.configure(bg='#e8f5e9')
        header = tk.Frame(win, bg='#f39c12', height=50)
        header.pack(fill='x')
        tk.Label(header, text="💎 Loyalty Program", font=('Segoe UI',18,'bold'), bg='#f39c12', fg='white').pack(pady=10)
        main = tk.Frame(win, bg='#e8f5e9')
        main.pack(fill='both', expand=True, padx=20, pady=20)
        add_frame = tk.Frame(main, bg='white', relief='raised', bd=0)
        add_frame.pack(fill='x', padx=10, pady=10)
        add_frame.config(highlightbackground='#d0d0d0', highlightthickness=1)
        tk.Label(add_frame, text="Register New Customer:", font=('Segoe UI',12,'bold'), bg='white').pack(side='left', padx=15, pady=10)
        tk.Label(add_frame, text="Name:", bg='white').pack(side='left', padx=5)
        name_e = tk.Entry(add_frame, width=20, relief='solid', bd=1)
        name_e.pack(side='left', padx=5, ipady=3)
        tk.Label(add_frame, text="Phone:", bg='white').pack(side='left', padx=5)
        phone_e = tk.Entry(add_frame, width=15, relief='solid', bd=1)
        phone_e.pack(side='left', padx=5, ipady=3)
        def add_cust():
            n = name_e.get()
            p = phone_e.get()
            if n and p:
                self.db.execute_query("INSERT OR REPLACE INTO loyalty (customer_name, customer_phone, points, tier) VALUES (?,?,0,'Bronze')", (n,p))
                messagebox.showinfo("Success","Customer registered")
                name_e.delete(0,tk.END)
                phone_e.delete(0,tk.END)
                load_loyalty()
            else:
                messagebox.showerror("Error","Name and phone required")
        tk.Button(add_frame, text="➕ Register", command=add_cust, bg=self.colors['success'], fg='white', font=('Segoe UI',10,'bold'), relief='flat', padx=15, pady=5).pack(side='left', padx=15)
        tree = ttk.Treeview(main, columns=('Customer','Phone','Points','Tier','Total Spent'), show='headings', height=18)
        for col in ('Customer','Phone','Points','Tier','Total Spent'): tree.heading(col, text=col); tree.column(col, width=180)
        def load_loyalty():
            for i in tree.get_children(): tree.delete(i)
            for l in self.db.fetch_all("SELECT customer_name, customer_phone, points, tier, total_spent FROM loyalty ORDER BY points DESC"):
                tree.insert('', 'end', values=l)
        tree.pack(fill='both', expand=True, padx=10, pady=10)
        load_loyalty()

    # ---------- EXPENSES ----------
    def show_expenses(self):
        win = tk.Toplevel(self.root)
        win.title("💰 Expense Tracking")
        win.geometry("1100x650")
        win.configure(bg='#e8f5e9')
        header = tk.Frame(win, bg='#1abc9c', height=50)
        header.pack(fill='x')
        tk.Label(header, text="💰 Expense Tracking", font=('Segoe UI',18,'bold'), bg='#1abc9c', fg='white').pack(pady=10)
        main = tk.Frame(win, bg='#e8f5e9')
        main.pack(fill='both', expand=True, padx=20, pady=20)
        form = tk.Frame(main, bg='white', relief='raised', bd=0)
        form.pack(fill='x', padx=10, pady=10)
        form.config(highlightbackground='#d0d0d0', highlightthickness=1)
        tk.Label(form, text="Category:", font=('Segoe UI',11), bg='white').grid(row=0, column=0, padx=10, pady=10)
        cat = ttk.Combobox(form, values=['Rent','Salaries','Utilities','Supplies','Marketing','Other'], width=15)
        cat.grid(row=0, column=1, padx=10, pady=10)
        tk.Label(form, text=f"Amount ({self.config.config['currency']}):", font=('Segoe UI',11), bg='white').grid(row=0, column=2, padx=10, pady=10)
        amt = tk.Entry(form, width=15, font=('Segoe UI',11), relief='solid', bd=1)
        amt.grid(row=0, column=3, padx=10, pady=10, ipady=4)
        tk.Label(form, text="Description:", font=('Segoe UI',11), bg='white').grid(row=0, column=4, padx=10, pady=10)
        desc = tk.Entry(form, width=25, font=('Segoe UI',11), relief='solid', bd=1)
        desc.grid(row=0, column=5, padx=10, pady=10, ipady=4)
        def add_exp():
            if cat.get() and amt.get():
                self.db.execute_query("INSERT INTO expenses (category, amount, description, expense_date, user) VALUES (?,?,?,?,?)",
                    (cat.get(), float(amt.get()), desc.get(), datetime.now().date(), self.current_user['username']))
                messagebox.showinfo("Success","Expense added")
                cat.set(''); amt.delete(0,tk.END); desc.delete(0,tk.END)
                load_exp()
        tk.Button(form, text="➕ Add Expense", command=add_exp, bg=self.colors['success'], fg='white', font=('Segoe UI',11,'bold'), relief='flat', padx=15, pady=5).grid(row=0, column=6, padx=15, pady=10)
        tree = ttk.Treeview(main, columns=('Date','Category','Amount','User'), show='headings', height=15)
        for col in ('Date','Category','Amount','User'): tree.heading(col, text=col); tree.column(col, width=180)
        tree.pack(fill='both', expand=True, padx=10, pady=10)
        total_lbl = tk.Label(main, text=f"Total Expenses: {self.config.config['currency']} 0.00", font=('Segoe UI',14,'bold'), bg='#e8f5e9', fg=self.colors['danger'])
        total_lbl.pack(pady=10)
        def load_exp():
            for i in tree.get_children(): tree.delete(i)
            exps = self.db.fetch_all("SELECT expense_date, category, amount, user FROM expenses ORDER BY expense_date DESC")
            total = 0
            for e in exps:
                tree.insert('', 'end', values=e)
                total += e[2]
            total_lbl.config(text=f"Total Expenses: {self.config.config['currency']} {total:,.2f}")
        load_exp()

    # ---------- BARCODE PRINT ----------
    def barcode_print_dialog(self):
        pid = simpledialog.askinteger("Print Barcode", "Enter Product ID:")
        if pid:
            prod = self.db.fetch_one("SELECT name, barcode FROM products WHERE id=?", (pid,))
            if prod and prod[1]:
                try:
                    code = barcode.get('code128', prod[1], writer=ImageWriter())
                    fn = code.save(f"barcode_{pid}")
                    img = Image.open(fn)
                    img.show()
                    messagebox.showinfo("Barcode", f"Barcode for {prod[0]} generated.")
                except Exception as e:
                    messagebox.showerror("Error", str(e))
            else:
                messagebox.showerror("Error", "Product or barcode missing")

    # ---------- BACKUP ----------
    def manual_backup(self):
        try:
            os.makedirs("backups", exist_ok=True)
            fn = f"backups/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy2("supermarket.db", fn)
            messagebox.showinfo("Success", f"✅ Backup saved to {fn}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def logout(self):
        if messagebox.askyesno("Logout", "Are you sure?"):
            self.db.log_action(self.current_user['username'], "LOGOUT", "users", self.current_user['id'], "", "")
            self.current_user = None
            self.show_login()

if __name__ == "__main__":
    if os.path.exists("supermarket.db"):
        os.remove("supermarket.db")
    root = tk.Tk()
    app = SupermarketSystem(root)
    root.mainloop()