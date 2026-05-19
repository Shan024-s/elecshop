import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = 'iot_final_secret_key'

# ตั้งค่า Path ให้รองรับทั้งการทดสอบในเครื่องและการรันบน PythonAnywhere
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
    
    # กรองสินค้าตามหมวดหมู่ที่กดเลือก
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
        
    conn.close()
    return render_template('index.html', categories=categories, products=products, current_category=category_id)

@app.route('/buy', methods=['POST'])
def buy_product():
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity', 1))
    
    if not product_id:
        flash('ไม่พบข้อมูลสินค้า', 'error')
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    product = conn.execute('SELECT * FROM products WHERE product_id = ?', (product_id,)).fetchone()
    
    if product:
        if product['stock'] < quantity:
            flash(f"สินค้าไม่พอ! เหลือในคลัง {product['stock']} ชิ้น", 'error')
            conn.close()
            return redirect(url_for('index'))
            
        subtotal = product['price'] * quantity
        
        try:
            cursor = conn.cursor()
            
            # บันทึกลงตาราง orders (ดึงรหัสลูกค้าคนแรกในตารางมาใช้อ้างอิงชั่วคราว)
            cursor.execute('''
                INSERT INTO orders (customer_id, order_date, total_price) 
                VALUES ('CU01', CURRENT_TIMESTAMP, ?)
            ''', (subtotal,))
            order_id = cursor.lastrowid
            
            # บันทึกลงตาราง order_details (สร้าง detail_id แบบสุ่มง่าย ๆ)
            import random
            detail_id = f"OD{random.randint(100, 999)}"
            cursor.execute('''
                INSERT INTO order_details (detail_id, order_id, product_id, quantity, subtotal) 
                VALUES (?, ?, ?, ?, ?)
            ''', (detail_id, str(order_id), product_id, quantity, subtotal))
            
            # หักสต็อกสินค้า
            cursor.execute('UPDATE products SET stock = stock - ? WHERE product_id = ?', (quantity, product_id))
            
            conn.commit()
            flash(f"สั่งซื้อ {product['product_name']} สำเร็จ ยอดรวม ฿{subtotal:,.2f}!", 'success')
        except Exception as e:
            conn.rollback()
            flash(f"เกิดข้อผิดพลาดในการบันทึก: {str(e)}", 'error')
    else:
        flash('ไม่พบสินค้าชิ้นนี้', 'error')
        
    conn.close()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
