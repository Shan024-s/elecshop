import os
import sqlite3
import random
from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)
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
    
    # 📊 ดึงสินค้าทั้งหมดสำหรับส่วน Admin (รวมตัวที่ stock = 0 ด้วย เพื่อให้กดเติมสต็อกได้)
    all_products_admin = conn.execute('SELECT * FROM products ORDER BY stock ASC').fetchall()
    low_stock_alerts = conn.execute('SELECT * FROM products WHERE stock <= 5 ORDER BY stock ASC').fetchall()
    
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
                           admin_products=all_products_admin,
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
        cart[product_id] = {'name': product_name, 'price': price, 'quantity': quantity}
        
    session.modified = True
    flash(f'เพิ่ม {product_name} ลงในตะกร้าแล้ว', 'success')
    return redirect(url_for('index'))

# 🗑️ ฟังก์ชัน: ล้างตะกร้า
@app.route('/clear_cart')
def clear_cart():
    session.pop('cart', None)
    flash('ล้างตะกร้าสินค้าเรียบร้อยแล้ว', 'success')
    return redirect(url_for('index'))

# 💳 ฟังก์ชัน: สั่งซื้อและตัดสต็อก
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
        last_order = conn.execute('SELECT order_id FROM orders ORDER BY CAST(order_id AS INTEGER) DESC LIMIT 1').fetchone()
        new_order_id = int(last_order['order_id']) + 1 if last_order and last_order['order_id'].isdigit() else random.randint(1000, 9999)
        
        cursor.execute("INSERT INTO orders (order_id, customer_id, order_date, total_price) VALUES (?, 'CU01', date('now'), ?)", (str(new_order_id), total_price))
        
        for product_id, item in cart.items():
            prod = conn.execute('SELECT stock FROM products WHERE product_id = ?', (product_id,)).fetchone()
            if prod['stock'] < item['quantity']:
                raise Exception(f"สินค้า {item['name']} ในคลังมีไม่พอ")
                
            subtotal = item['price'] * item['quantity']
            detail_id = f"OD{random.randint(1000, 9999)}"
            
            cursor.execute("INSERT INTO order_details (detail_id, order_id, product_id, quantity, subtotal) VALUES (?, ?, ?, ?, ?)", (detail_id, str(new_order_id), product_id, item['quantity'], subtotal))
            cursor.execute("UPDATE products SET stock = stock - ? WHERE product_id = ?", (item['quantity'], product_id))
            
        conn.commit()
        session.pop('cart', None)
        flash(f'สั่งซื้อสำเร็จ! ยอดรวม ฿{total_price:,.2f}', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'การสั่งซื้อล้มเหลว: {str(e)}', 'error')
    finally:
        conn.close()
    return redirect(url_for('index'))

# 🔥 [เพิ่มฟังก์ชันใหม่] ฟังก์ชันสำหรับให้เจ้าของร้านกดเติมสต็อกสินค้าผ่านหน้าเว็บ
@app.route('/update_stock', methods=['POST'])
def update_stock():
    product_id = request.form.get('product_id')
    add_quantity = int(request.form.get('add_quantity', 0))
    
    if not product_id or add_quantity <= 0:
        flash('กรุณาระบุจำนวนสต็อกที่ถูกต้อง', 'error')
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    try:
        # อัปเดตโดยการบวกสต็อกเพิ่มเข้าไปจากค่าเดิมที่มีอยู่ (+ add_quantity)
        conn.execute('UPDATE products SET stock = stock + ? WHERE product_id = ?', (add_quantity, product_id))
        conn.commit()
        flash('อัปเดตสต็อกสินค้าเรียบร้อยแล้ว!', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'ไม่สามารถเพิ่มสต็อกได้: {str(e)}', 'error')
    finally:
        conn.close()
        
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
