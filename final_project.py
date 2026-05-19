import sqlite3
import datetime
import hashlib
import random
import os
import shutil
import json
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify, send_file

app = Flask(__name__)
app.secret_key = 'supermarket-secret-key-change-in-production'


# ==================== CONFIGURATION MANAGER ====================
class ConfigManager:
    DEFAULT_CONFIG = {
        "company_name": "VICTOR'S SUPER MARKET",
        "currency": "Ksh",
        "tax_rates": [{"name": "VAT 16%", "rate": 0.16, "categories": ["general", "electronics", "beverages", "snacks"]}],
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
                user = json.load(f)
                merged = self.DEFAULT_CONFIG.copy()
                merged.update(user)
                return merged
        else:
            self.save_config(self.DEFAULT_CONFIG)
            return self.DEFAULT_CONFIG

    def save_config(self, config=None):
        with open(self.config_path, 'w') as f:
            json.dump(config or self.config, f, indent=4)

    def get_tax_rate(self, product_category):
        for t in self.config["tax_rates"]:
            if product_category in t.get("categories", []):
                return t["rate"]
        return 0.16


config_manager = ConfigManager()


# ==================== DATABASE ====================
class Database:
    def __init__(self, db_name="supermarket.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
        self.populate_initial_data()
        # Create a settings table for invoice counter if not exists
        self.cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        self.conn.commit()

    def create_tables(self):
        self.cursor.executescript('''
            CREATE TABLE IF NOT EXISTS products (
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
            );
            CREATE TABLE IF NOT EXISTS sales (
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
            );
            CREATE TABLE IF NOT EXISTS sale_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_no TEXT,
                product_id INTEGER,
                product_name TEXT,
                quantity INTEGER,
                unit_price REAL,
                total REAL,
                returned BOOLEAN DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT,
                role TEXT DEFAULT 'cashier',
                full_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                contact_person TEXT,
                phone TEXT,
                email TEXT,
                address TEXT
            );
            CREATE TABLE IF NOT EXISTS stock_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                movement_type TEXT,
                quantity INTEGER,
                reason TEXT,
                user TEXT,
                movement_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS returns (
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
            );
            CREATE TABLE IF NOT EXISTS loyalty (
                customer_phone TEXT PRIMARY KEY,
                customer_name TEXT,
                points INTEGER DEFAULT 0,
                tier TEXT DEFAULT 'Bronze',
                total_spent REAL DEFAULT 0,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                amount REAL,
                description TEXT,
                expense_date DATE,
                user TEXT
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT,
                action TEXT,
                table_name TEXT,
                record_id TEXT,
                old_value TEXT,
                new_value TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        self.conn.commit()

    def populate_initial_data(self):
        # Create admin user: victor / victor@123
        hashed_admin = hashlib.sha256("victor@123".encode()).hexdigest()
        if not self.fetch_one("SELECT id FROM users WHERE username='victor'"):
            self.execute_query("INSERT INTO users (username, password, role, full_name) VALUES (?,?,?,?)",
                               ("victor", hashed_admin, "admin", "Victor Admin"))

        # Create cashier user with no password (empty string)
        hashed_cashier = hashlib.sha256("".encode()).hexdigest()  # empty password
        if not self.fetch_one("SELECT id FROM users WHERE username='cashier'"):
            self.execute_query("INSERT INTO users (username, password, role, full_name) VALUES (?,?,?,?)",
                               ("cashier", hashed_cashier, "cashier", "Store Cashier"))

        # Many suppliers (20)
        if self.fetch_one("SELECT COUNT(*) FROM suppliers")[0] == 0:
            for i in range(1, 21):
                name = f"Supplier {i}"
                contact = f"Contact Person {i}"
                phone = f"07{random.randint(10000000, 99999999)}"
                email = f"supplier{i}@mail.com"
                address = f"Address {i}, Nairobi"
                self.execute_query("INSERT INTO suppliers (name,contact_person,phone,email,address) VALUES (?,?,?,?,?)",
                                   (name, contact, phone, email, address))

        # Many customers (random loyalty records)
        first_names = ['John', 'Jane', 'Michael', 'Sarah', 'David', 'Linda', 'James', 'Mary', 'Robert', 'Patricia']
        last_names = ['Doe', 'Smith', 'Johnson', 'Brown', 'Williams', 'Jones', 'Garcia', 'Miller', 'Davis', 'Wilson']
        if self.fetch_one("SELECT COUNT(*) FROM loyalty")[0] == 0:
            for _ in range(50):
                name = f"{random.choice(first_names)} {random.choice(last_names)}"
                phone = f"07{random.randint(10000000, 99999999)}"
                points = random.randint(0, 5000)
                spent = random.randint(0, 50000)
                self.execute_query("INSERT OR IGNORE INTO loyalty (customer_name, customer_phone, points, total_spent) VALUES (?,?,?,?)",
                                   (name, phone, points, spent))

        # Generate 500+ products (skip if already exist)
        self.populate_products()

    def populate_products(self):
        self.cursor.execute("SELECT COUNT(*) FROM products")
        if self.cursor.fetchone()[0] > 0:
            return  # products already exist

        # Get supplier names for random assignment
        self.cursor.execute("SELECT name FROM suppliers")
        suppliers = [row[0] for row in self.cursor.fetchall()]
        if not suppliers:
            suppliers = ["General Supplier"]

        # Categories with realistic product names (more than 500 unique)
        categories = {
            "Grains & Cereals": [
                "Rice (1kg)", "Rice (5kg)", "Rice (10kg)", "Maize Flour (1kg)", "Maize Flour (2kg)",
                "Wheat Flour (1kg)", "Wheat Flour (2kg)", "Brown Rice (1kg)", "Sorghum Flour", "Millet Flour",
                "Oats (500g)", "Oats (1kg)", "Quinoa (500g)", "Barley (500g)", "Semolina", "Buckwheat",
                "Corn Flour", "Bread Flour", "Self-Rising Flour", "Whole Wheat Flour"
            ],
            "Dairy & Eggs": [
                "Fresh Milk (1L)", "Fresh Milk (500ml)", "Long Life Milk (1L)", "Skimmed Milk (1L)",
                "Yogurt (500ml)", "Yogurt (1L)", "Cheese (250g)", "Cheese (500g)", "Butter (250g)",
                "Butter (500g)", "Margarine (250g)", "Eggs (6pcs)", "Eggs (12pcs)", "Eggs (30pcs)",
                "Cream (250ml)", "Cream (500ml)", "Sour Cream (200g)", "Cottage Cheese (200g)",
                "Mozzarella (250g)", "Parmesan (150g)"
            ],
            "Beverages": [
                "Mineral Water (500ml)", "Mineral Water (1L)", "Mineral Water (5L)", "Soda (330ml)",
                "Soda (2L)", "Juice (1L)", "Energy Drink (250ml)", "Sports Drink (500ml)", "Coffee (50g)",
                "Tea Bags (100)", "Green Tea (25)", "Hot Chocolate (200g)", "Milo (400g)", "Porridge Flour (500g)",
                "Chai Mix (250g)", "Cappuccino Mix (200g)", "Sparkling Water (1L)", "Tonic Water (1L)",
                "Coconut Water (500ml)", "Smoothie (300ml)"
            ],
            "Snacks & Confectionery": [
                "Potato Chips (50g)", "Potato Chips (100g)", "Corn Chips (100g)", "Peanuts (100g)",
                "Cashew Nuts (100g)", "Almonds (100g)", "Chocolate Bar (50g)", "Chocolate Bar (100g)",
                "Candy (50g)", "Gum (10pcs)", "Biscuits (100g)", "Cookies (150g)", "Crackers (200g)",
                "Popcorn (100g)", "Dates (250g)", "Dried Fruit (100g)", "Pretzels (100g)", "Rice Cakes (100g)",
                "Granola Bar (40g)", "Trail Mix (200g)"
            ],
            "Fruits & Vegetables": [
                "Apples (1kg)", "Bananas (1 bunch)", "Oranges (1kg)", "Mangoes (1kg)", "Grapes (500g)",
                "Pineapple (1pc)", "Watermelon (1kg)", "Avocado (1pc)", "Tomatoes (1kg)", "Onions (1kg)",
                "Potatoes (1kg)", "Cabbage (1pc)", "Spinach (250g)", "Carrots (1kg)", "Cucumber (1pc)",
                "Lettuce (1pc)", "Bell Peppers (3pcs)", "Broccoli (500g)", "Cauliflower (1pc)", "Zucchini (1kg)"
            ],
            "Meat & Fish": [
                "Beef (1kg)", "Chicken Whole (1pc)", "Chicken Breast (500g)", "Pork (500g)", "Lamb (500g)",
                "Minced Meat (500g)", "Sausages (8pcs)", "Bacon (250g)", "Fish Fillet (500g)", "Fish Whole (1pc)",
                "Prawns (250g)", "Sardines (can)", "Tuna (can)", "Mackerel (1pc)", "Salmon Fillet (250g)",
                "Turkey Breast (500g)", "Duck (1pc)", "Rabbit (1pc)", "Goat Meat (1kg)", "Liver (500g)"
            ],
            "Frozen Foods": [
                "Frozen Peas (500g)", "Frozen Mixed Veg (500g)", "Frozen Chips (1kg)", "Ice Cream (500ml)",
                "Ice Cream (1L)", "Frozen Chicken (1kg)", "Frozen Fish Fingers (300g)", "Pizza (400g)",
                "Spring Rolls (250g)", "Samosa (250g)", "Frozen Berries (500g)", "Frozen Spinach (400g)",
                "Frozen Broccoli (500g)", "Frozen Corn (500g)", "Frozen Prawns (500g)", "Frozen Burgers (4pcs)",
                "Frozen Waffles (6pcs)", "Frozen Pancakes (6pcs)", "Frozen Yogurt (500ml)", "Frozen Sorbet (500ml)"
            ],
            "Household & Cleaning": [
                "Detergent (1kg)", "Detergent Liquid (1L)", "Dish Soap (500ml)", "Fabric Softener (1L)",
                "Bleach (1L)", "All-Purpose Cleaner (500ml)", "Glass Cleaner (500ml)", "Floor Cleaner (1L)",
                "Toilet Cleaner (500ml)", "Air Freshener (300ml)", "Paper Towels (2 rolls)", "Toilet Paper (4 rolls)",
                "Trash Bags (10pcs)", "Sponges (3pcs)", "Gloves (1 pair)", "Mop (1pc)", "Broom (1pc)",
                "Dustpan (1pc)", "Laundry Basket", "Storage Containers (3pcs)"
            ],
            "Personal Care": [
                "Shampoo (250ml)", "Conditioner (250ml)", "Body Wash (500ml)", "Soap Bar (100g)",
                "Toothpaste (100g)", "Toothbrush (1pc)", "Deodorant (50ml)", "Perfume (50ml)", "Lotion (200ml)",
                "Face Cream (50g)", "Sunscreen (100ml)", "Razor (3pcs)", "Shaving Cream (150ml)",
                "Cotton Balls (100pcs)", "Tissues (100pcs)", "Hair Gel (150ml)", "Hair Spray (200ml)",
                "Lip Balm (5g)", "Nail Polish (10ml)", "Makeup Remover (200ml)"
            ],
            "Baby Products": [
                "Diapers (S)", "Diapers (M)", "Diapers (L)", "Baby Wipes (80pcs)", "Baby Powder (200g)",
                "Baby Oil (200ml)", "Baby Shampoo (200ml)", "Baby Lotion (200ml)", "Baby Cereal (250g)",
                "Formula Milk (400g)", "Fruit Puree (100g)", "Teething Biscuits (100g)", "Baby Bottle (250ml)",
                "Pacifier (1pc)", "Baby Blanket", "Baby Onesie (0-3m)", "Baby Hat", "Baby Socks (3pairs)",
                "Bibs (2pcs)", "Burp Cloths (3pcs)"
            ]
        }

        units = ["pcs", "kg", "L", "g", "ml", "pack"]
        product_count = 0

        for category, product_names in categories.items():
            for name in product_names:
                if product_count >= 520:
                    break
                buying_price = round(random.uniform(10, 800), 2)
                selling_price = round(buying_price * random.uniform(1.2, 1.8), 2)
                quantity = random.randint(20, 500)
                min_stock = random.randint(5, 30)
                unit = random.choice(units)
                barcode = f"890{random.randint(1000000000, 9999999999)}"
                supplier = random.choice(suppliers)

                self.cursor.execute('''INSERT INTO products 
                    (barcode, name, category, buying_price, selling_price, quantity, min_stock, unit, supplier)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                    (barcode, name, category, buying_price, selling_price, quantity, min_stock, unit,
                                     supplier))
                product_count += 1

                # Record initial stock movement
                self.cursor.execute('''INSERT INTO stock_movements 
                    (product_id, movement_type, quantity, reason, user)
                    VALUES (?, 'stock_in', ?, 'Initial stock', 'system')''',
                                    (product_count, quantity))

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

    def log_action(self, user, action, table, rid, old="", new=""):
        self.execute_query(
            "INSERT INTO audit_log (user,action,table_name,record_id,old_value,new_value) VALUES (?,?,?,?,?,?)",
            (user, action, table, str(rid), str(old), str(new)))

    def close(self):
        self.conn.close()


db = Database()


# ==================== HELPER FUNCTIONS ====================
def login_required(allowed_roles=None):
    def decorator(f):
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if allowed_roles and session.get('role') not in allowed_roles:
                return "Access denied", 403
            return f(*args, **kwargs)

        wrapper.__name__ = f.__name__
        return wrapper

    return decorator


def generate_invoice_no():
    today = datetime.now().date()
    last = db.fetch_one("SELECT invoice_no FROM sales WHERE DATE(sale_date) = ? ORDER BY id DESC LIMIT 1", (today,))
    if last:
        parts = last[0].split('-')
        last_num = int(parts[-1])
        seq = last_num + 1
    else:
        seq = 1
    return f"INV-{today.strftime('%Y%m%d')}-{seq:04d}"


# ==================== ROUTES ====================
@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']  # plain text
        hashed = hashlib.sha256(password.encode()).hexdigest()
        user = db.fetch_one("SELECT id, username, role, full_name FROM users WHERE username=? AND password=?",
                            (username, hashed))
        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[2]
            session['full_name'] = user[3]
            db.log_action(username, "LOGIN", "users", user[0], "", "Success")
            return redirect(url_for('dashboard'))
        else:
            return render_template_string('''
                {% extends "base.html" %}
                {% block content %}
                <div class="row justify-content-center"><div class="col-md-4"><div class="card"><div class="card-header">Login</div><div class="card-body">
                <div class="alert alert-danger">Invalid credentials</div>
                <form method="post"><div class="mb-3"><label>Username</label><input type="text" name="username" class="form-control" required></div><div class="mb-3"><label>Password</label><input type="password" name="password" class="form-control"></div><button type="submit" class="btn btn-primary w-100">LOGIN</button></form>
                <div class="mt-3 text-center small">Demo: victor/victor@123 (admin) | cashier/[blank] (cashier)</div>
                </div></div></div></div>
                {% endblock %}
            ''', title="Login", company=config_manager.config['company_name'], session=session,
                                          year=datetime.now().year)
    return render_template_string('''
        {% extends "base.html" %}
        {% block content %}
        <div class="row justify-content-center"><div class="col-md-4"><div class="card"><div class="card-header">Login</div><div class="card-body">
        <form method="post"><div class="mb-3"><label>Username</label><input type="text" name="username" class="form-control" required></div><div class="mb-3"><label>Password</label><input type="password" name="password" class="form-control"></div><button type="submit" class="btn btn-primary w-100">LOGIN</button></form>
        </div></div></div></div>
        {% endblock %}
    ''', title="Login", company=config_manager.config['company_name'], session=session, year=datetime.now().year)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required()
def dashboard():
    today = datetime.now().date()
    total_products = db.fetch_one("SELECT COUNT(*) FROM products")[0]
    low_stock = db.fetch_one("SELECT COUNT(*) FROM products WHERE quantity <= min_stock")[0]
    today_sales = db.fetch_one("SELECT COALESCE(SUM(net_amount),0), COUNT(*) FROM sales WHERE DATE(sale_date)=?",
                               (today,))
    total_sales = db.fetch_one("SELECT COALESCE(SUM(net_amount),0) FROM sales")[0]
    top_product_today = db.fetch_one("""
        SELECT p.name, SUM(si.quantity) 
        FROM sale_items si JOIN sales s ON si.invoice_no = s.invoice_no 
        JOIN products p ON si.product_id = p.id 
        WHERE DATE(s.sale_date)=? 
        GROUP BY si.product_id 
        ORDER BY SUM(si.quantity) DESC LIMIT 1
    """, (today,))
    top_product = (top_product_today[0], top_product_today[1]) if top_product_today else ('None', 0)
    month_start = today.replace(day=1)
    expenses_month = db.fetch_one("SELECT COALESCE(SUM(amount),0) FROM expenses WHERE expense_date BETWEEN ? AND ?",
                                  (month_start, today))[0]
    pending_returns = db.fetch_one("SELECT COUNT(*) FROM returns WHERE DATE(return_date)=?", (today,))[0]

    stats = {
        'total_products': total_products,
        'low_stock': low_stock,
        'today_sales': today_sales[0],
        'today_transactions': today_sales[1],
        'total_sales': total_sales,
        'top_product': top_product,
        'expenses_month': expenses_month,
        'pending_returns': pending_returns
    }
    return render_template_string('''
        {% extends "base.html" %}
        {% block content %}
        <div class="row mb-4">
            <div class="col-md-3"><div class="stat-card"><div>📦 Total Products</div><div class="stat-number">{{ stats.total_products }}</div><div>{{ stats.low_stock }} low stock</div></div></div>
            <div class="col-md-3"><div class="stat-card"><div>💰 Today's Sales</div><div class="stat-number">{{ currency }} {{ "{:,.2f}".format(stats.today_sales) }}</div><div>{{ stats.today_transactions }} transactions</div></div></div>
            <div class="col-md-3"><div class="stat-card"><div>📊 Total Revenue</div><div class="stat-number">{{ currency }} {{ "{:,.2f}".format(stats.total_sales) }}</div><div>Lifetime</div></div></div>
            <div class="col-md-3"><div class="stat-card"><div>🎯 Daily Target</div><div class="stat-number">{{ currency }} 100,000</div><div>Today's Goal</div></div></div>
        </div>
        <div class="row mb-4">
            <div class="col-md-4"><div class="stat-card"><div>🏆 Top Product Today</div><div class="stat-number">{{ stats.top_product[0] }}</div><div>Sold: {{ stats.top_product[1] }} units</div></div></div>
            <div class="col-md-4"><div class="stat-card"><div>💰 Expenses this Month</div><div class="stat-number">{{ currency }} {{ "{:,.2f}".format(stats.expenses_month) }}</div><div>Since {{ month_start }}</div></div></div>
            <div class="col-md-4"><div class="stat-card"><div>🔄 Pending Returns</div><div class="stat-number">{{ stats.pending_returns }}</div><div>Today</div></div></div>
        </div>
        <div class="row">
            {% if session.role == 'admin' %}
            <div class="col-md-4 mb-3"><a href="/pos" class="btn btn-success w-100 py-3">🛒 Point of Sale</a></div>
            <div class="col-md-4 mb-3"><a href="/inventory" class="btn btn-primary w-100 py-3">📦 Inventory</a></div>
            <div class="col-md-4 mb-3"><a href="/reports" class="btn btn-secondary w-100 py-3">📊 Reports</a></div>
            <div class="col-md-4 mb-3"><a href="/customers" class="btn btn-warning w-100 py-3">👥 Customers</a></div>
            <div class="col-md-4 mb-3"><a href="/suppliers" class="btn btn-info w-100 py-3">🏭 Suppliers</a></div>
            <div class="col-md-4 mb-3"><a href="/users" class="btn btn-danger w-100 py-3">👤 Users</a></div>
            <div class="col-md-4 mb-3"><a href="/stock_alerts" class="btn btn-outline-danger w-100 py-3">🔍 Stock Alerts {% if stats.low_stock > 0 %}<span class="badge bg-danger">{{ stats.low_stock }}</span>{% endif %}</a></div>
            <div class="col-md-4 mb-3"><a href="/returns" class="btn btn-outline-secondary w-100 py-3">🔄 Returns</a></div>
            <div class="col-md-4 mb-3"><a href="/loyalty" class="btn btn-outline-warning w-100 py-3">💎 Loyalty</a></div>
            <div class="col-md-4 mb-3"><a href="/expenses" class="btn btn-outline-info w-100 py-3">💰 Expenses</a></div>
            <div class="col-md-4 mb-3"><a href="/backup" class="btn btn-outline-dark w-100 py-3">💾 Backup</a></div>
            <div class="col-md-4 mb-3"><a href="/charts" class="btn btn-outline-success w-100 py-3">📈 Advanced Charts</a></div>
            {% else %}
            <div class="col-md-6 mx-auto mb-3"><a href="/pos" class="btn btn-success w-100 py-3">🛒 Point of Sale</a></div>
            <div class="col-md-6 mx-auto mb-3"><a href="/returns" class="btn btn-secondary w-100 py-3">🔄 Returns</a></div>
            <div class="col-md-6 mx-auto mb-3"><a href="/loyalty" class="btn btn-warning w-100 py-3">💎 Loyalty</a></div>
            {% endif %}
        </div>
        {% endblock %}
    ''', stats=stats, company=config_manager.config['company_name'], currency=config_manager.config['currency'],
                                  session=session, year=datetime.now().year, month_start=month_start)


@app.route('/pos', methods=['GET', 'POST'])
@login_required(allowed_roles=['admin', 'cashier'])
def pos():
    if request.method == 'POST':
        import json
        data = request.json
        cart = data['cart']
        customer_name = data.get('customer_name', '')
        customer_phone = data.get('customer_phone', '')
        subtotal = sum(item['total'] for item in cart)
        discount = data.get('discount', 0)
        tax = subtotal * 0.16
        net_total = subtotal - discount + tax
        invoice_no = generate_invoice_no()
        try:
            db.execute_query(
                "INSERT INTO sales (invoice_no, customer_name, customer_phone, total_amount, discount, tax, net_amount, payment_method, cashier) VALUES (?,?,?,?,?,?,?,?,?)",
                (invoice_no, customer_name, customer_phone, subtotal, discount, tax, net_total, "Cash",
                 session['username']))
            for item in cart:
                db.execute_query(
                    "INSERT INTO sale_items (invoice_no, product_id, product_name, quantity, unit_price, total) VALUES (?,?,?,?,?,?)",
                    (invoice_no, item['id'], item['name'], item['quantity'], item['price'], item['total']))
                db.execute_query("UPDATE products SET quantity = quantity - ? WHERE id=?",
                                 (item['quantity'], item['id']))
            if customer_phone:
                points = int(subtotal * 0.01)
                db.execute_query(
                    "UPDATE loyalty SET points = points + ?, total_spent = total_spent + ? WHERE customer_phone=?",
                    (points, net_total, customer_phone))
                if not db.fetch_one("SELECT customer_phone FROM loyalty WHERE customer_phone=?", (customer_phone,)):
                    db.execute_query("INSERT INTO loyalty (customer_phone, customer_name, points) VALUES (?,?,?)",
                                     (customer_phone, customer_name, points))
            db.log_action(session['username'], "SALE", "sales", invoice_no, "", f"Total: {net_total}")
            return jsonify({'status': 'success', 'invoice': invoice_no, 'net_total': net_total})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})
    else:
        products = db.fetch_all(
            "SELECT id, name, selling_price, quantity, category FROM products WHERE quantity > 0 ORDER BY name")
        customers = db.fetch_all("SELECT customer_name, customer_phone FROM loyalty ORDER BY customer_name")
        return render_template_string('''
            {% extends "base.html" %}
            {% block extra_head %}
            <style>.cart-item{cursor:pointer;}</style>
            {% endblock %}
            {% block content %}
            <div class="row">
                <div class="col-md-7">
                    <div class="card">
                        <div class="card-header">📦 Products</div>
                        <div class="card-body">
                            <div class="row mb-2">
                                <div class="col-md-6"><input type="text" id="barcodeInput" placeholder="Scan barcode" class="form-control"></div>
                                <div class="col-md-6"><select id="categoryFilter" class="form-select"><option value="all">All Categories</option>{% set cats = [] %}{% for p in products %}{% if p[4] not in cats %}{% set _ = cats.append(p[4]) %}<option value="{{ p[4] }}">{{ p[4] }}</option>{% endif %}{% endfor %}</select></div>
                            </div>
                            <input type="text" id="search" class="form-control mb-3" placeholder="Search product...">
                            <div style="height:500px; overflow-y:auto;">
                                <table class="table table-sm table-hover">
                                    <thead><tr><th>ID</th><th>Name</th><th>Price</th><th>Stock</th><th>Category</th><th></th></tr></thead>
                                    <tbody id="product-list">
                                        {% for p in products %}
                                        <tr data-category="{{ p[4] }}">
                                            <td>{{ p[0] }}</td>
                                            <td>{{ p[1] }}</td>
                                            <td>{{ currency }} {{ p[2] }}</td>
                                            <td>{{ p[3] }}</td>
                                            <td>{{ p[4] }}</td>
                                            <td><button class="btn btn-sm btn-success add-to-cart" data-id="{{ p[0] }}" data-name="{{ p[1] }}" data-price="{{ p[2] }}" data-stock="{{ p[3] }}">Add</button></td>
                                        </tr>
                                        {% endfor %}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="col-md-5">
                    <div class="card">
                        <div class="card-header">🛒 Shopping Cart</div>
                        <div class="card-body">
                            <div style="height:300px; overflow-y:auto;">
                                <table class="table table-sm">
                                    <thead><tr><th>Name</th><th>Qty</th><th>Price</th><th>Total</th><th></th></tr></thead>
                                    <tbody id="cart-items"></tbody>
                                </table>
                            </div>
                            <hr>
                            <div class="mb-2"><label>Customer Name</label><input type="text" id="cust_name" class="form-control" list="customerList"></div>
                            <div class="mb-2"><label>Customer Phone</label><input type="text" id="cust_phone" class="form-control" list="customerList"></div>
                            <datalist id="customerList">
                                {% for c in customers %}
                                <option value="{{ c[1] }}">{{ c[0] }} - {{ c[1] }}</option>
                                {% endfor %}
                            </datalist>
                            <div class="mb-2"><label>Discount (%)</label><input type="number" id="discount" class="form-control" value="0"></div>
                            <div class="mb-2"><label>Payment Method</label><select id="paymentMethod" class="form-select"><option>Cash</option><option>Card</option><option>MPESA</option><option>Bank Transfer</option></select></div>
                            <h4>Total: <span id="total">{{ currency }} 0.00</span></h4>
                            <button id="checkout-btn" class="btn btn-success w-100">Checkout</button>
                        </div>
                    </div>
                </div>
            </div>
            <script>
                let cart = [];
                function updateCartUI() {
                    let tbody = document.getElementById('cart-items');
                    tbody.innerHTML = '';
                    let total = 0;
                    cart.forEach((item, idx) => {
                        let row = tbody.insertRow();
                        row.insertCell(0).innerText = item.name;
                        row.insertCell(1).innerText = item.qty;
                        row.insertCell(2).innerText = '{{ currency }} ' + item.price.toFixed(2);
                        row.insertCell(3).innerText = '{{ currency }} ' + (item.price * item.qty).toFixed(2);
                        let delCell = row.insertCell(4);
                        let delBtn = document.createElement('button');
                        delBtn.innerText = '❌';
                        delBtn.className = 'btn btn-sm btn-danger';
                        delBtn.onclick = () => { cart.splice(idx,1); updateCartUI(); };
                        delCell.appendChild(delBtn);
                        total += item.price * item.qty;
                    });
                    document.getElementById('total').innerText = '{{ currency }} ' + total.toFixed(2);
                }
                function addToCart(id, name, price, stock) {
                    let qty = prompt('Enter quantity', '1');
                    if(qty && !isNaN(qty) && qty>0 && qty<=stock) {
                        let existing = cart.find(i => i.id == id);
                        if(existing) existing.qty += parseInt(qty);
                        else cart.push({id: id, name: name, price: price, qty: parseInt(qty)});
                        updateCartUI();
                    } else alert('Invalid quantity or out of stock');
                }
                document.querySelectorAll('.add-to-cart').forEach(btn => {
                    btn.addEventListener('click', () => {
                        let id = btn.dataset.id;
                        let name = btn.dataset.name;
                        let price = parseFloat(btn.dataset.price);
                        let stock = parseInt(btn.dataset.stock);
                        addToCart(id, name, price, stock);
                    });
                });
                document.getElementById('barcodeInput').addEventListener('change', function() {
                    let barcode = this.value;
                    fetch(`/product_by_barcode/${barcode}`)
                        .then(res => res.json())
                        .then(product => {
                            if(product && product.id) {
                                addToCart(product.id, product.name, product.price, product.stock);
                            } else {
                                alert('Product not found');
                            }
                            this.value = '';
                        });
                });
                document.getElementById('categoryFilter').addEventListener('change', function() {
                    let selected = this.value;
                    let rows = document.querySelectorAll('#product-list tr');
                    rows.forEach(row => {
                        let category = row.dataset.category;
                        if(selected === 'all' || category === selected) {
                            row.style.display = '';
                        } else {
                            row.style.display = 'none';
                        }
                    });
                });
                document.getElementById('search').addEventListener('keyup', function() {
                    let term = this.value.toLowerCase();
                    let rows = document.querySelectorAll('#product-list tr');
                    rows.forEach(row => {
                        let name = row.cells[1].innerText.toLowerCase();
                        if(name.includes(term)) row.style.display = '';
                        else row.style.display = 'none';
                    });
                });
                document.getElementById('cust_phone').addEventListener('change', function() {
                    let phone = this.value;
                    let customerList = document.getElementById('customerList').options;
                    for(let opt of customerList) {
                        if(opt.value === phone) {
                            document.getElementById('cust_name').value = opt.text.split(' - ')[0];
                            break;
                        }
                    }
                });
                document.getElementById('checkout-btn').addEventListener('click', () => {
    if(cart.length === 0) { alert('Cart empty'); return; }
    let discount = parseFloat(document.getElementById('discount').value) || 0;
    let subtotal = cart.reduce((s,i)=> s + i.price * i.qty, 0);
    let discountAmount = subtotal * discount / 100;
    let net = subtotal - discountAmount + (subtotal - discountAmount) * 0.16;
    fetch('/pos', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            cart: cart.map(i => ({id: i.id, name: i.name, quantity: i.qty, price: i.price, total: i.price * i.qty})),
            customer_name: document.getElementById('cust_name').value,
            customer_phone: document.getElementById('cust_phone').value,
            discount: discountAmount
        })
    }).then(res => res.json()).then(data => {
        if(data.status === 'success') {
            if(confirm('Sale complete! Print receipt?')) {
                let receipt = `🏪 ${'{{ company }}'}\\nInvoice: ${data.invoice}\\nTotal: {{ currency }} ${data.net_total.toFixed(2)}\\nThank you!\\n{{ receipt_footer }}`;
                let printWindow = window.open('', '_blank');
                printWindow.document.write(`<pre>${receipt}</pre>`);
                printWindow.print();
            }
            cart = [];
            updateCartUI();
            location.reload();
        } else alert('Error: '+data.message);
    });
});
            </script>
            {% endblock %}
        ''', products=products, customers=customers, company=config_manager.config['company_name'],
                                      currency=config_manager.config['currency'],
                                      receipt_footer=config_manager.config['receipt_footer'], session=session,
                                      year=datetime.now().year)


@app.route('/product_by_barcode/<barcode>')
@login_required(allowed_roles=['admin', 'cashier'])
def product_by_barcode(barcode):
    prod = db.fetch_one("SELECT id, name, selling_price, quantity FROM products WHERE barcode=? AND quantity>0",
                        (barcode,))
    if prod:
        return jsonify({'id': prod[0], 'name': prod[1], 'price': prod[2], 'stock': prod[3]})
    return jsonify({}), 404


@app.route('/update_stock/<int:pid>', methods=['POST'])
@login_required(allowed_roles=['admin'])
def update_stock(pid):
    qty = request.args.get('qty')
    if qty is None:
        return '', 400
    db.execute_query("UPDATE products SET quantity = ? WHERE id=?", (int(qty), pid))
    db.log_action(session['username'], "UPDATE_STOCK", "products", pid, "", f"New quantity: {qty}")
    return '', 204


@app.route('/inventory')
@login_required(allowed_roles=['admin'])
def inventory():
    products = db.fetch_all(
        "SELECT id, barcode, name, category, buying_price, selling_price, quantity, min_stock, unit, supplier FROM products")
    return render_template_string('''
        {% extends "base.html" %}
        {% block content %}
        <h2>📦 Inventory Management</h2>
        <button class="btn btn-success mb-3" data-bs-toggle="modal" data-bs-target="#addModal">+ Add Product</button>
        <table class="table table-bordered bg-white">
            <thead><tr><th>ID</th><th>Barcode</th><th>Name</th><th>Category</th><th>Buying</th><th>Selling</th><th>Stock</th><th>Min</th><th>Unit</th><th>Supplier</th><th>Action</th></tr></thead>
            <tbody>
                {% for p in products %}
                <tr>
                    <td>{{ p[0] }}</td><td>{{ p[1] }}</td><td>{{ p[2] }}</td><td>{{ p[3] }}</td>
                    <td>{{ currency }} {{ p[4] }}</td><td>{{ currency }} {{ p[5] }}</td>
                    <td id="stock-{{ p[0] }}">{{ p[6] }}</td><td>{{ p[7] }}</td><td>{{ p[8] }}</td><td>{{ p[9] }}</td>
                    <td>
                        <a href="/inventory/delete/{{ p[0] }}" class="btn btn-danger btn-sm" onclick="return confirm('Delete?')">Delete</a>
                        <button class="btn btn-warning btn-sm" onclick="updateStock({{ p[0] }})">✏️ Stock</button>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        <div class="modal fade" id="addModal"><div class="modal-dialog"><div class="modal-content"><form method="post" action="/inventory/add"><div class="modal-header"><h5 class="modal-title">Add Product</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><div class="modal-body"><div class="mb-2"><label>Name</label><input type="text" name="name" class="form-control" required></div><div class="mb-2"><label>Barcode (optional)</label><input type="text" name="barcode" class="form-control"></div><div class="mb-2"><label>Category</label><input type="text" name="category" class="form-control"></div><div class="mb-2"><label>Buying Price</label><input type="number" step="0.01" name="buying_price" class="form-control"></div><div class="mb-2"><label>Selling Price</label><input type="number" step="0.01" name="selling_price" class="form-control" required></div><div class="mb-2"><label>Quantity</label><input type="number" name="quantity" class="form-control"></div><div class="mb-2"><label>Min Stock</label><input type="number" name="min_stock" class="form-control" value="5"></div><div class="mb-2"><label>Unit</label><input type="text" name="unit" class="form-control" value="pcs"></div><div class="mb-2"><label>Supplier</label><input type="text" name="supplier" class="form-control"></div></div><div class="modal-footer"><button type="submit" class="btn btn-primary">Save</button><button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button></div></form></div></div></div>
        <script>
            function updateStock(pid) {
                let newQty = prompt('Enter new quantity:');
                if(newQty && !isNaN(newQty)) {
                    fetch(`/update_stock/${pid}?qty=${newQty}`, {method:'POST'})
                        .then(() => location.reload());
                }
            }
        </script>
        {% endblock %}
    ''', products=products, currency=config_manager.config['currency'], company=config_manager.config['company_name'],
                                  session=session, year=datetime.now().year)


@app.route('/inventory/add', methods=['POST'])
@login_required(allowed_roles=['admin'])
def add_product():
    data = request.form
    name = data['name']
    barcode = data.get('barcode') or f"890{random.randint(1000000000, 9999999999)}"
    category = data.get('category', '')
    buying_price = float(data.get('buying_price', 0))
    selling_price = float(data['selling_price'])
    quantity = int(data.get('quantity', 0))
    min_stock = int(data.get('min_stock', 5))
    unit = data.get('unit', 'pcs')
    supplier = data.get('supplier', '')
    db.execute_query(
        "INSERT INTO products (barcode,name,category,buying_price,selling_price,quantity,min_stock,unit,supplier) VALUES (?,?,?,?,?,?,?,?,?)",
        (barcode, name, category, buying_price, selling_price, quantity, min_stock, unit, supplier))
    db.log_action(session['username'], "INSERT", "products", name, "", f"Added product {name}")
    return redirect(url_for('inventory'))


@app.route('/inventory/delete/<int:pid>')
@login_required(allowed_roles=['admin'])
def delete_product(pid):
    db.execute_query("DELETE FROM products WHERE id=?", (pid,))
    return redirect(url_for('inventory'))


@app.route('/reports')
@login_required()
def reports():
    from_date = request.args.get('from_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.args.get('to_date', datetime.now().strftime('%Y-%m-%d'))
    sales = db.fetch_all(
        '''SELECT DATE(sale_date), COUNT(*), SUM(net_amount) FROM sales WHERE DATE(sale_date) BETWEEN ? AND ? GROUP BY DATE(sale_date) ORDER BY sale_date''',
        (from_date, to_date))
    top_products = db.fetch_all(
        '''SELECT p.name, SUM(si.quantity), SUM(si.total) FROM sale_items si JOIN products p ON si.product_id=p.id JOIN sales s ON si.invoice_no=s.invoice_no WHERE DATE(s.sale_date) BETWEEN ? AND ? GROUP BY si.product_id ORDER BY SUM(si.quantity) DESC LIMIT 10''',
        (from_date, to_date))
    payments = db.fetch_all(
        '''SELECT payment_method, COUNT(*), SUM(net_amount) FROM sales WHERE DATE(sale_date) BETWEEN ? AND ? GROUP BY payment_method''',
        (from_date, to_date))
    return render_template_string('''
        {% extends "base.html" %}
        {% block content %}
        <h2>📊 Sales Reports</h2>
        <form method="get" class="row g-3 mb-4"><div class="col-auto"><input type="date" name="from_date" value="{{ from_date }}" class="form-control"></div><div class="col-auto"><input type="date" name="to_date" value="{{ to_date }}" class="form-control"></div><div class="col-auto"><button type="submit" class="btn btn-primary">Generate</button></div></form>
        <h4>Daily Sales</h4><table class="table table-bordered bg-white"><thead><tr><th>Date</th><th>Transactions</th><th>Total ({{ currency }})</th></tr></thead><tbody>{% for s in sales %}<tr><td>{{ s[0] }}</td><td>{{ s[1] }}</td><td>{{ s[2] }}</td></tr>{% endfor %}</tbody></table>
        <h4>Top Products</h4><table class="table bg-white"><thead><tr><th>Product</th><th>Quantity</th><th>Revenue</th></tr></thead><tbody>{% for p in top_products %}<tr><td>{{ p[0] }}</td><td>{{ p[1] }}</td><td>{{ currency }} {{ p[2] }}</td></tr>{% endfor %}</tbody></table>
        <h4>Payment Methods</h4><table class="table bg-white"><thead><tr><th>Method</th><th>Count</th><th>Amount</th></tr></thead><tbody>{% for pm in payments %}<tr><td>{{ pm[0] }}</td><td>{{ pm[1] }}</td><td>{{ currency }} {{ pm[2] }}</td></tr>{% endfor %}</tbody></table>
        {% endblock %}
    ''', sales=sales, top_products=top_products, payments=payments, from_date=from_date, to_date=to_date,
                                  currency=config_manager.config['currency'],
                                  company=config_manager.config['company_name'], session=session,
                                  year=datetime.now().year)


@app.route('/customers')
@login_required()
def customers():
    rows = db.fetch_all(
        '''SELECT DISTINCT customer_name, customer_phone, COUNT(*) as visits, SUM(net_amount) as total_spent FROM sales WHERE customer_name IS NOT NULL AND customer_name != '' GROUP BY customer_name, customer_phone ORDER BY total_spent DESC''')
    return render_template_string('''
        {% extends "base.html" %}
        {% block content %}
        <h2>👥 Customer Management</h2>
        <table class="table bg-white"><thead><tr><th>Name</th><th>Phone</th><th>Visits</th><th>Total Spent ({{ currency }})</th></tr></thead><tbody>{% for c in customers %}<tr><td>{{ c[0] }}</td><td>{{ c[1] }}</td><td>{{ c[2] }}</td><td>{{ c[3] }}</td></tr>{% endfor %}</tbody></table>
        {% endblock %}
    ''', customers=rows, currency=config_manager.config['currency'], company=config_manager.config['company_name'],
                                  session=session, year=datetime.now().year)


@app.route('/suppliers')
@login_required(allowed_roles=['admin'])
def suppliers():
    rows = db.fetch_all("SELECT id, name, contact_person, phone, email FROM suppliers")
    return render_template_string('''
        {% extends "base.html" %}
        {% block content %}
        <h2>🏭 Supplier Management</h2>
        <table class="table bg-white"><thead><tr><th>ID</th><th>Name</th><th>Contact Person</th><th>Phone</th><th>Email</th></tr></thead><tbody>{% for s in suppliers %}<tr><td>{{ s[0] }}</td><td>{{ s[1] }}</td><td>{{ s[2] }}</td><td>{{ s[3] }}</td><td>{{ s[4] }}</td></tr>{% endfor %}</tbody></table>
        {% endblock %}
    ''', suppliers=rows, company=config_manager.config['company_name'], session=session, year=datetime.now().year)


@app.route('/users', methods=['GET', 'POST'])
@login_required(allowed_roles=['admin'])
def users():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form.get('password', '')
        hashed = hashlib.sha256(password.encode()).hexdigest()
        role = request.form['role']
        full_name = request.form['full_name']
        if not db.fetch_one("SELECT id FROM users WHERE username=?", (username,)):
            db.execute_query("INSERT INTO users (username, password, role, full_name) VALUES (?,?,?,?)",
                             (username, hashed, role, full_name))
            db.log_action(session['username'], "INSERT", "users", username, "", f"Added user {username}")
        return redirect(url_for('users'))
    rows = db.fetch_all("SELECT id, username, role, full_name FROM users")
    return render_template_string('''
        {% extends "base.html" %}
        {% block content %}
        <h2>👤 User Management</h2>
        <button class="btn btn-success mb-3" data-bs-toggle="modal" data-bs-target="#addModal">+ Add User</button>
        <table class="table bg-white"><thead><tr><th>ID</th><th>Username</th><th>Role</th><th>Full Name</th></tr></thead><tbody>{% for u in users %}<tr><td>{{ u[0] }}</td><td>{{ u[1] }}</td><td>{{ u[2] }}</td><td>{{ u[3] }}</td></tr>{% endfor %}</tbody></table>
        <div class="modal fade" id="addModal"><div class="modal-dialog"><div class="modal-content"><form method="post"><div class="modal-header"><h5 class="modal-title">Add User</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><div class="modal-body"><div class="mb-2"><label>Username</label><input type="text" name="username" class="form-control" required></div><div class="mb-2"><label>Password</label><input type="text" name="password" class="form-control"></div><div class="mb-2"><label>Role</label><select name="role" class="form-select"><option>admin</option><option>cashier</option></select></div><div class="mb-2"><label>Full Name</label><input type="text" name="full_name" class="form-control" required></div></div><div class="modal-footer"><button type="submit" class="btn btn-primary">Save</button><button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button></div></form></div></div></div>
        {% endblock %}
    ''', users=rows, company=config_manager.config['company_name'], session=session, year=datetime.now().year)


@app.route('/stock_alerts')
@login_required()
def stock_alerts():
    low = db.fetch_all("SELECT name, quantity, min_stock FROM products WHERE quantity <= min_stock")
    return render_template_string('''
        {% extends "base.html" %}
        {% block content %}
        <h2>🔍 Low Stock Alerts</h2>
        {% if low %}
        <table class="table bg-white"><thead><tr><th>Product</th><th>Current Stock</th><th>Min Stock</th></tr></thead><tbody>{% for l in low %}<tr><td>{{ l[0] }}</td><td>{{ l[1] }}</td><td>{{ l[2] }}</td></tr>{% endfor %}</tbody></table>
        {% else %}<div class="alert alert-success">No low stock items</div>{% endif %}
        {% endblock %}
    ''', low=low, company=config_manager.config['company_name'], session=session, year=datetime.now().year)


@app.route('/returns', methods=['GET', 'POST'])
@login_required()
def returns():
    if request.method == 'POST':
        invoice = request.form['invoice']
        reason = request.form['reason']
        sale = db.fetch_one("SELECT invoice_no, net_amount FROM sales WHERE invoice_no=?", (invoice,))
        if sale:
            refund = sale[1] * 0.95
            ret_inv = f"RET-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            db.execute_query(
                "INSERT INTO returns (original_invoice, return_invoice, refund_amount, reason, cashier) VALUES (?,?,?,?,?)",
                (invoice, ret_inv, refund, reason, session['username']))
            items = db.fetch_all("SELECT product_id, quantity FROM sale_items WHERE invoice_no=?", (invoice,))
            for it in items:
                db.execute_query("UPDATE products SET quantity = quantity + ? WHERE id=?", (it[1], it[0]))
            return render_template_string('''
                {% extends "base.html" %}
                {% block content %}
                <h2>🔄 Returns Management</h2>
                <div class="alert alert-success">Return processed, refund: {{ currency }} {{ refund }}</div>
                <a href="/returns" class="btn btn-secondary">Back</a>
                {% endblock %}
            ''', refund=refund, currency=config_manager.config['currency'],
                                          company=config_manager.config['company_name'], session=session,
                                          year=datetime.now().year)
        else:
            return render_template_string('''
                {% extends "base.html" %}
                {% block content %}
                <h2>🔄 Returns Management</h2>
                <div class="alert alert-danger">Invoice not found</div>
                <form method="post"><div class="mb-3"><label>Invoice Number</label><input type="text" name="invoice" class="form-control" required></div><div class="mb-3"><label>Reason</label><select name="reason" class="form-select"><option>Damaged</option><option>Wrong item</option><option>Expired</option><option>Other</option></select></div><button type="submit" class="btn btn-warning">Process Return</button></form>
                {% endblock %}
            ''', company=config_manager.config['company_name'], session=session, year=datetime.now().year)
    return render_template_string('''
        {% extends "base.html" %}
        {% block content %}
        <h2>🔄 Returns Management</h2>
        <form method="post"><div class="mb-3"><label>Invoice Number</label><input type="text" name="invoice" class="form-control" required></div><div class="mb-3"><label>Reason</label><select name="reason" class="form-select"><option>Damaged</option><option>Wrong item</option><option>Expired</option><option>Other</option></select></div><button type="submit" class="btn btn-warning">Process Return</button></form>
        {% endblock %}
    ''', company=config_manager.config['company_name'], session=session, year=datetime.now().year)


@app.route('/loyalty')
@login_required()
def loyalty():
    rows = db.fetch_all(
        "SELECT customer_name, customer_phone, points, tier, total_spent FROM loyalty ORDER BY points DESC")
    return render_template_string('''
        {% extends "base.html" %}
        {% block content %}
        <h2>💎 Loyalty Program</h2>
        {% if session.role == 'admin' %}
        <button class="btn btn-success mb-3" data-bs-toggle="modal" data-bs-target="#addModal">+ Register Customer</button>
        <div class="modal fade" id="addModal"><div class="modal-dialog"><div class="modal-content"><form method="post" action="/loyalty/add"><div class="modal-header"><h5 class="modal-title">Register Customer</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><div class="modal-body"><div class="mb-2"><label>Name</label><input type="text" name="name" class="form-control" required></div><div class="mb-2"><label>Phone</label><input type="text" name="phone" class="form-control" required></div></div><div class="modal-footer"><button type="submit" class="btn btn-primary">Save</button><button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button></div></form></div></div></div>
        {% endif %}
        <table class="table bg-white"><thead><tr><th>Customer</th><th>Phone</th><th>Points</th><th>Tier</th><th>Total Spent ({{ currency }})</th></tr></thead><tbody>{% for l in rows %}<tr><td>{{ l[0] }}</td><td>{{ l[1] }}</td><td>{{ l[2] }}</td><td>{{ l[3] }}</td><td>{{ l[4] }}</td></tr>{% endfor %}</tbody></table>
        {% endblock %}
    ''', rows=rows, currency=config_manager.config['currency'], company=config_manager.config['company_name'],
                                  session=session, year=datetime.now().year)


@app.route('/loyalty/add', methods=['POST'])
@login_required(allowed_roles=['admin'])
def add_loyalty():
    name = request.form['name']
    phone = request.form['phone']
    db.execute_query("INSERT OR REPLACE INTO loyalty (customer_name, customer_phone) VALUES (?,?)", (name, phone))
    return redirect(url_for('loyalty'))


@app.route('/expenses', methods=['GET', 'POST'])
@login_required(allowed_roles=['admin'])
def expenses():
    if request.method == 'POST':
        category = request.form['category']
        amount = float(request.form['amount'])
        description = request.form['description']
        db.execute_query("INSERT INTO expenses (category, amount, description, expense_date, user) VALUES (?,?,?,?,?)",
                         (category, amount, description, datetime.now().date(), session['username']))
        return redirect(url_for('expenses'))
    rows = db.fetch_all(
        "SELECT expense_date, category, amount, description, user FROM expenses ORDER BY expense_date DESC")
    total = sum(r[2] for r in rows)
    return render_template_string('''
        {% extends "base.html" %}
        {% block content %}
        <h2>💰 Expense Tracking</h2>
        <form method="post" class="row g-3 mb-4"><div class="col-auto"><input type="text" name="category" placeholder="Category" class="form-control" required></div><div class="col-auto"><input type="number" step="0.01" name="amount" placeholder="Amount" class="form-control" required></div><div class="col-auto"><input type="text" name="description" placeholder="Description" class="form-control"></div><div class="col-auto"><button type="submit" class="btn btn-primary">Add Expense</button></div></form>
        <table class="table bg-white"><thead><tr><th>Date</th><th>Category</th><th>Amount ({{ currency }})</th><th>Description</th><th>User</th></tr></thead><tbody>{% for e in expenses %}<tr><td>{{ e[0] }}</td><td>{{ e[1] }}</td><td>{{ e[2] }}</td><td>{{ e[3] }}</td><td>{{ e[4] }}</td></tr>{% endfor %}</tbody></table>
        <h4>Total: {{ currency }} {{ total }}</h4>
        {% endblock %}
    ''', expenses=rows, total=total, currency=config_manager.config['currency'],
                                  company=config_manager.config['company_name'], session=session,
                                  year=datetime.now().year)


@app.route('/backup')
@login_required(allowed_roles=['admin'])
def backup():
    try:
        os.makedirs("backups", exist_ok=True)
        fn = f"backups/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2("supermarket.db", fn)
        return f"Backup saved to {fn}"
    except Exception as e:
        return f"Backup failed: {str(e)}"


@app.route('/charts')
@login_required()
def charts():
    return render_template_string('''
        {% extends "base.html" %}
        {% block extra_head %}
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        {% endblock %}
        {% block content %}
        <h2>📈 Sales Analytics</h2>
        <canvas id="salesChart" width="800" height="400"></canvas>
        <canvas id="categoryChart" width="800" height="400"></canvas>
        <script>
            fetch('/api/sales_trend')
                .then(res => res.json())
                .then(data => {
                    new Chart(document.getElementById('salesChart'), {
                        type: 'line',
                        data: { labels: data.dates, datasets: [{ label: 'Revenue ({{ currency }})', data: data.amounts, borderColor: '#2e7d32', fill: false }] },
                        options: { responsive: true, maintainAspectRatio: false }
                    });
                });
            fetch('/api/category_sales')
                .then(res => res.json())
                .then(data => {
                    new Chart(document.getElementById('categoryChart'), {
                        type: 'pie',
                        data: { labels: data.categories, datasets: [{ data: data.sales, backgroundColor: ['#2e7d32','#43a047','#66bb6a','#81c784','#a5d6a7'] }] }
                    });
                });
        </script>
        {% endblock %}
    ''', company=config_manager.config['company_name'], currency=config_manager.config['currency'], session=session,
                                  year=datetime.now().year)


@app.route('/api/sales_trend')
@login_required()
def api_sales_trend():
    data = db.fetch_all(
        "SELECT DATE(sale_date), SUM(net_amount) FROM sales WHERE sale_date >= date('now', '-30 days') GROUP BY DATE(sale_date) ORDER BY sale_date")
    dates = [d[0] for d in data]
    amounts = [d[1] for d in data]
    return jsonify({'dates': dates, 'amounts': amounts})


@app.route('/api/category_sales')
@login_required()
def api_category_sales():
    cat_data = db.fetch_all(
        "SELECT p.category, SUM(si.total) FROM sale_items si JOIN products p ON si.product_id=p.id GROUP BY p.category ORDER BY SUM(si.total) DESC LIMIT 5")
    categories = [c[0] for c in cat_data]
    sales_by_cat = [c[1] for c in cat_data]
    return jsonify({'categories': categories, 'sales': sales_by_cat})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)