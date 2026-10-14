from flask import Flask, render_template, request, redirect, url_for, jsonify
import yfinance as yf
import smtplib
from email.mime.text import MIMEText
from apscheduler.schedulers.background import BackgroundScheduler
import random
import os
import requests

app = Flask(__name__)
alerts_db = []

# ================= การตั้งค่า Session =================
session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
})

# ================= การตั้งค่าอีเมล =================
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "thawatchai2547123@gmail.com")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "vqjxfivgsgkdedyk")

def get_live_price(symbol):
    if not symbol: return 0.0
    try:
        stock = yf.Ticker(symbol, session=session)
        try:
            val = stock.fast_info.get('lastPrice')
            if val and float(val) > 0: return round(float(val), 2)
        except: pass
        try:
            df = stock.history(period="1d", session=session)
            if not df.empty:
                val = df['Close'].iloc[-1]
                if val and float(val) > 0: return round(float(val), 2)
        except: pass
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d"
        res = session.get(url, timeout=5)
        data = res.json()
        val = data['chart']['result'][0]['meta']['regularMarketPrice']
        if val and float(val) > 0: return round(float(val), 2)
    except Exception as e:
        print(f"❌ ดึงราคา {symbol} ไม่สำเร็จ: {e}")
    return 0.0

def send_email(to_email, subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
        print(f"✅ ส่งอีเมลแจ้งเตือนไปยัง {to_email} สำเร็จ!")
    except Exception as e:
        print(f"❌ ส่งอีเมลไม่สำเร็จ: {e}")

def check_stock_prices():
    if not alerts_db:
        return # ถ้าไม่มีหุ้นให้ข้ามไป เพื่อไม่ให้เปลืองทรัพยากร
    print(f"🔄 กำลังเช็คราคาหุ้นเบื้องหลัง... (รายการทั้งหมด: {len(alerts_db)})")
    for alert in alerts_db:
        if alert.get('alerted'): continue
        try:
            current_price = get_live_price(alert['symbol'])
            if current_price <= 0: continue
            
            if alert['sell'] and current_price >= float(alert['sell']):
                send_email(alert['email'], f"📈 แจ้งเตือน: {alert['symbol']} ถึงเป้าขาย!", f"ราคาถึง {alert['sell']} แล้ว (ปัจจุบัน: {current_price})")
                alert['alerted'] = True
            elif alert['buy'] and current_price <= float(alert['buy']):
                send_email(alert['email'], f"📉 แจ้งเตือน: {alert['symbol']} ถึงเป้าซื้อ!", f"ราคาลงมาถึง {alert['buy']} แล้ว (ปัจจุบัน: {current_price})")
                alert['alerted'] = True
        except Exception as e:
            print(f"⚠️ เช็คราคาผิดพลาด ({alert['symbol']}): {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(func=check_stock_prices, trigger="interval", minutes=1)
scheduler.start()

@app.route('/get_price')
def get_price():
    symbol = request.args.get('symbol', '').upper().strip()
    if not symbol: return jsonify({'price': 0})
    price = get_live_price(symbol)
    return jsonify({'price': price})

# เพิ่ม Endpoint นี้สำหรับใช้ทำระบบรัน 24 ชม. ในขั้นตอนที่ 3
@app.route('/ping')
def ping():
    return "OK", 200

@app.route('/')
def index():
    # ลบ AAPL ออก เปลี่ยนเป็นรอรับค่าว่าง
    selected_symbol = request.args.get('symbol', '').upper().strip()
    error_msg = request.args.get('error')
    
    news_data = []
    ai_data = None

    if selected_symbol:
        try:
            stock = yf.Ticker(selected_symbol, session=session)
            raw_news = stock.news[:3]
            for n in raw_news:
                news_data.append({'title': n.get('title', ''), 'link': n.get('link', '#'), 'publisher': n.get('publisher', '')})
        except:
            pass

        random.seed(selected_symbol) 
        buy_pct = random.randint(20, 80)
        ai_data = {
            'buy': buy_pct, 
            'sell': 100 - buy_pct,
            'status': 'สะสม (Accumulate)' if buy_pct >= 50 else 'ชะลอลงทุน (Wait)'
        }

    return render_template('index.html', alerts=alerts_db, selected=selected_symbol, news=news_data, ai=ai_data, error=error_msg)

@app.route('/add_alert', methods=['POST'])
def add_alert():
    symbol = request.form['symbol'].upper().strip()
    user_email = request.form['user_email'].strip()
    target_buy_str = request.form.get('target_buy', '').strip()
    target_sell_str = request.form.get('target_sell', '').strip()

    if not symbol:
        return redirect(url_for('index', error="กรุณาระบุชื่อหุ้น"))

    if not target_buy_str and not target_sell_str:
        return redirect(url_for('index', symbol=symbol, error="กรุณากำหนดราคาแนวรับหรือแนวต้านอย่างน้อย 1 ช่อง"))

    current_price = get_live_price(symbol)
    if current_price <= 0:
        return redirect(url_for('index', symbol=symbol, error=f"ไม่สามารถดึงราคาปัจจุบันของหุ้น '{symbol}' ได้ในขณะนี้"))

    target_buy = float(target_buy_str) if target_buy_str else None
    target_sell = float(target_sell_str) if target_sell_str else None

    if target_buy is not None and target_buy >= current_price:
        return redirect(url_for('index', symbol=symbol, error=f"ราคาแนวรับ ({target_buy}) ต้องต่ำกว่าราคาปัจจุบัน ({current_price:.2f})"))

    if target_sell is not None and target_sell <= current_price:
        return redirect(url_for('index', symbol=symbol, error=f"ราคาแนวต้าน ({target_sell}) ต้องสูงกว่าราคาปัจจุบัน ({current_price:.2f})"))

    alerts_db.append({
        'symbol': symbol,
        'email': user_email,
        'buy': target_buy,
        'sell': target_sell,
        'alerted': False
    })
    return redirect(f"/?symbol={symbol}")

@app.route('/delete/<int:index>', methods=['POST'])
def delete_index(index):
    if 0 <= index < len(alerts_db):
        alerts_db.pop(index)
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
