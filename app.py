import os
import sqlite3
import random
from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)
# กำหนด Secret Key เพื่อให้ระบบ Session (ตะกร้าสินค้า) ทำงานได้
app.secret_key = 'iot_final_project_super_secret_key'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'Project Final.db')

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    conn = get_db_connection()
    categories = conn.execute('SELECT * FROM categories').fetchall()
    
    # ตัวกรองหมวดหมู่สินค้า
    category_id = request.args.get('category_id')
    if category_id:
        products = conn.execute('''
            SELECT p.*, c.category_name 
            FROM products p
            JOIN categories c ON p.category_id = c.category_id
            WHERE p.category_id = ? AND p.stock > 0
        ''', (category_id,)).fetchall()
    else:
        products = conn.execute('''
            SELECT p.*, c.category_name 
            FROM products p
            JOIN categories c ON p.category_id = c.category_id
            WHERE p.stock > 0
        ''').fetchall()
    
    # --- ฟังก์ชันดึงข้อมูลสำหรับฝั่งเจ้าของร้าน (Admin Zone) ---
    # 1. แจ้งเตือนสินค้าใกล้หมด (สต็อกน้อยกว่าหรือเท่ากับ 5 ชิ้น)
    low_stock_alerts = conn.execute('SELECT * FROM products WHERE stock <= 5 ORDER BY stock ASC').fetchall()
    
    # 2. ดึงประวัติการสั่งซื้อล่าสุด 5 รายการ
    recent_orders = conn.execute('''
        SELECT o.order_id, o.order_date, o.total_price, od.quantity, p.product_name
        FROM orders o
        JOIN order_details od ON o.order_id = od.order_id
        JOIN products p ON od.product_id = p.product_id
        ORDER BY o.order_date DESC LIMIT 5
    ''').fetchall()
    
    conn.close()

    # ดึงข้อมูลสินค้าที่อยู่ในตะกร้าปัจจุบันมาคำนวณแสดงผล
    cart = session.get('cart', {})
    
    return render_template('index.html', 
                           categories=categories, 
                           products=products, 
                           current_category=category_id,
                           low_stock=low_stock_alerts,
                           recent_orders=recent_orders,
                           cart=cart)

# --- 🛒 ฟังก์ชันที่ 1: เพิ่มสินค้าลงตะกร้า ---
@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    product_id = request.form.get('product_id')
    product_name = request.form.get('product_name')
    price = float(request.form.get('price', 0))
    quantity = int(request.form.get('quantity', 1))
    
    if 'cart' not in session:
        session['cart'] = {}
        
    cart = session['cart']
    
    # ถ้ามีสินค้าในตะกร้าอยู่แล้วให้บวกจำนวนเพิ่ม ถ้ายังไม่มีให้สร้างใหม่
    if product_id in cart:
        cart[product_id]['quantity'] += quantity
    else:
        cart[product_id] = {
            'name': product_name,
            'price': price,
            'quantity': quantity
        }
        
    session.modified = True
    flash(f'เพิ่ม {product_name} ลงในตะกร้าแล้ว', 'success')
    return redirect(url_for('index'))

# --- 🗑️ ฟังก์ชันที่ 2: ล้างสินค้าในตะกร้าทั้งหมด ---
@app.route('/clear_cart')
def clear_cart():
    session.pop('cart', None)
    flash('ล้างตะกร้าสินค้าเรียบร้อยแล้ว', 'success')
    return redirect(url_for('index'))

# --- 💳 ฟังก์ชันที่ 3: สั่งซื้อสินค้าทั้งหมดในตะกร้า (ตัดสต็อกและบันทึกลง DB) ---
@app.route('/checkout', methods=['POST'])
def checkout():
    cart = session.get('cart', {})
    if not cart:
        flash('ไม่มีสินค้าในตะกร้า', 'error')
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # คำนวณราคารวมทั้งหมดในตะกร้า
        total_price = sum(item['price'] * item['quantity'] for item in cart.values())
        
        # 1. บันทึกลงตาราง orders หนึ่งครั้งต่อหนึ่งตะกร้า
        cursor.execute('''
            INSERT INTO orders (customer_id, order_date, total_price) 
            VALUES ('CU01', CURRENT_TIMESTAMP, ?)
        ''', (total_price,))
        order_id = cursor.lastrowid
        
        # 2. วนลูปบันทึกสินค้าแต่ละชิ้นลงตาราง order_details และหักสต็อก
        for product_id, item in cart.items():
            # เช็คสต็อกจริงใน DB ก่อนตัด
            prod = conn.execute('SELECT stock FROM products WHERE product_id = ?', (product_id,)).fetchone()
            if prod['stock'] < item['quantity']:
                raise Exception(f"สินค้า {item['name']} ในคลังมีไม่พอ (เหลือ {prod['stock']} ชิ้น)")
                
            subtotal = item['price'] * item['quantity']
            detail_id = f"OD{random.randint(1000, 9999)}"
            
            # บันทึกรายละเอียดสินค้า
            cursor.execute('''
                INSERT INTO order_details (detail_id, order_id, product_id, quantity, subtotal) 
                VALUES (?, ?, ?, ?, ?)
            ''', (detail_id, str(order_id), product_id, item['quantity'], subtotal))
            
            # หักสต็อกสินค้าในตาราง products
            cursor.execute('''
                UPDATE products 
                SET stock = stock - ? 
                WHERE product_id = ?
            ''', (item['quantity'], product_id))
            
        conn.commit()
        session.pop('cart', None) # ซื้อเสร็จแล้วล้างตะกร้า
        flash(f'สั่งซื้อสินค้าในตะกร้าทั้งหมดสำเร็จ! ยอดรวม ฿{total_price:,.2f}', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'การสั่งซื้อล้มเหลว: {str(e)}', 'error')
        
    finally:
        conn.close()
        
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
