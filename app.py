import os
import sqlite3
import random
from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)
# กำหนด Secret Key เพื่อให้ระบบ Session ตะกร้าสินค้าทำงานได้
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
    
    # ระบบกรองสินค้าตามหมวดหมู่
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
    
    # 📊 ส่วนของเจ้าของร้าน (Admin Dashboard)
    # 1. แจ้งเตือนสินค้าสต็อกใกล้หมด (เหลือชิ้นส่วนน้อยกว่าหรือเท่ากับ 5 ชิ้น)
    low_stock_alerts = conn.execute('SELECT * FROM products WHERE stock <= 5 ORDER BY stock ASC').fetchall()
    
    # 🔥 [จุดที่แก้ไข] ปรับ SQL ให้เรียงลำดับเอา Order ล่าสุด (ID มากที่สุด) ขึ้นมาอยู่บนสุดเสมอ
    recent_orders = conn.execute('''
        SELECT od.order_id, o.order_date, o.total_price, od.quantity, p.product_name, od.subtotal
        FROM order_details od
        JOIN orders o ON od.order_id = o.order_id
        JOIN products p ON od.product_id = p.product_id
        ORDER BY CAST(o.order_id AS INTEGER) DESC, od.detail_id DESC LIMIT 10
    ''').fetchall()
    
    conn.close()
    cart = session.get('cart', {})
    
    return render_template('index.html', 
                           categories=categories, 
                           products=products, 
                           current_category=category_id,
                           low_stock=low_stock_alerts,
                           recent_orders=recent_orders,
                           cart=cart)

# 🛒 ฟังก์ชัน: เพิ่มสินค้าลงตะกร้า
@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    product_id = request.form.get('product_id')
    product_name = request.form.get('product_name')
    price = float(request.form.get('price', 0))
    quantity = int(request.form.get('quantity', 1))
    
    if 'cart' not in session:
        session['cart'] = {}
        
    cart = session['cart']
    
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

# 🗑️ ฟังก์ชัน: ล้างสินค้าในตะกร้าทั้งหมด
@app.route('/clear_cart')
def clear_cart():
    session.pop('cart', None)
    flash('ล้างตะกร้าสินค้าเรียบร้อยแล้ว', 'success')
    return redirect(url_for('index'))

# 💳 ฟังก์ชัน: สั่งซื้อและตัดสต็อก (Real-time อัปเดต)
@app.route('/checkout', methods=['POST'])
def checkout():
    cart = session.get('cart', {})
    if not cart:
        flash('ไม่มีสินค้าในตะกร้า', 'error')
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        total_price = sum(item['price'] * item['quantity'] for item in cart.values())
        
        # ค้นหาค่า Order ID ที่มากที่สุดในตารางตอนนี้ แล้วบวกเพิ่มทีละ 1 เพื่อให้รหัสรันต่อกันขึ้นไปเรื่อยๆ
        last_order = conn.execute('SELECT order_id FROM orders ORDER BY CAST(order_id AS INTEGER) DESC LIMIT 1').fetchone()
        if last_order and last_order['order_id'].isdigit():
            new_order_id = int(last_order['order_id']) + 1
        else:
            new_order_id = random.randint(1000, 9999) # กรณีตารางว่างให้สุ่มเลขเริ่มต้น
        
        # 1. บันทึกลงตาราง orders โดยดึงวันที่ปัจจุบันของเซิร์ฟเวอร์
        cursor.execute('''
            INSERT INTO orders (order_id, customer_id, order_date, total_price) 
            VALUES (?, 'CU01', date('now'), ?)
        ''', (str(new_order_id), total_price))
        
        # 2. บันทึกสินค้าลงตาราง order_details และหักสต็อกออกจาก products
        for product_id, item in cart.items():
            prod = conn.execute('SELECT stock FROM products WHERE product_id = ?', (product_id,)).fetchone()
            if prod['stock'] < item['quantity']:
                raise Exception(f"สินค้า {item['name']} มีจำนวนในคลังไม่พอ")
                
            subtotal = item['price'] * item['quantity']
            detail_id = f"OD{random.randint(1000, 9999)}"
            
            # บันทึกรายละเอียดออเดอร์
            cursor.execute('''
                INSERT INTO order_details (detail_id, order_id, product_id, quantity, subtotal) 
                VALUES (?, ?, ?, ?, ?)
            ''', (detail_id, str(new_order_id), product_id, item['quantity'], subtotal))
            
            # อัปเดตตัดสต็อกสินค้าในคลัง
            cursor.execute('''
                UPDATE products 
                SET stock = stock - ? 
                WHERE product_id = ?
            ''', (item['quantity'], product_id))
            
        conn.commit()
        session.pop('cart', None) # ล้างตะกร้าหลังซื้อเสร็จสิ้น
        flash(f'สั่งซื้อสำเร็จ! ยอดรวมทั้งสิ้น ฿{total_price:,.2f} ระบบบันทึกประวัติและตัดสต็อกเรียบร้อย', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'การสั่งซื้อล้มเหลว: {str(e)}', 'error')
        
    finally:
        conn.close()
        
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
