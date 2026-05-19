import os
import sqlite3
from flask import Flask, render_template, request

app = Flask(__name__)

# กำหนด Path ของฐานข้อมูลให้รองรับการรันบน PythonAnywhere
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'Project Final.db')

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    conn = get_db_connection()
    
    # ดึงข้อมูลหมวดหมู่ทั้งหมดสำหรับแท็บตัวกรอง
    categories = conn.execute('SELECT * FROM categories').fetchall()
    
    # รับค่าการค้นหาและตัวกรองหมวดหมู่
    search_query = request.args.get('search', '')
    category_filter = request.args.get('category', '')
    
    # สร้าง SQL Query แบบ Dynamic ตามเงื่อนไขการค้นหา
    query = '''
        SELECT p.*, c.category_name 
        FROM products p
        JOIN categories c ON p.category_id = c.category_id
        WHERE 1=1
    '''
    params = []
    
    if search_query:
        query += ' AND p.product_name LIKE ?'
        params.append(f'%{search_query}%')
        
    if category_filter:
        query += ' AND p.category_id = ?'
        params.append(category_filter)
        
    products = conn.execute(query, params).fetchall()
    conn.close()
    
    return render_template('index.html', products=products, categories=categories, search_query=search_query, current_category=category_filter)

@app.route('/product/<product_id>')
def detail(product_id):
    conn = get_db_connection()
    
    # ดึงรายละเอียดสินค้าพร้อมชื่อหมวดหมู่และชื่อผู้จัดจำหน่าย (Supplier)
    product = conn.execute('''
        SELECT p.*, c.category_name, s.supplier_name, s.phone as supplier_phone, s.address as supplier_address
        FROM products p
        JOIN categories c ON p.category_id = c.category_id
        JOIN suppliers s ON p.supplier_id = s.supplier_id
        WHERE p.product_id = ?
    ''', (product_id,)).fetchone()
    
    # ดึงสินค้าแนะนำในหมวดหมู่เดียวกัน (ไม่รวมชิ้นปัจจุบัน)
    related_products = []
    if product:
        related_products = conn.execute('''
            SELECT * FROM products 
            WHERE category_id = ? AND product_id != ? 
            LIMIT 4
        ''', (product['category_id'], product_id)).fetchall()
        
    conn.close()
    
    if product is None:
        return "Product not found", 404
        
    return render_template('detail.html', product=product, related_products=related_products)

if __name__ == '__main__':
    app.run(debug=True)
