from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import threading
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

app = Flask(__name__)
CORS(app)

# Store active bots here
active_bots = {}

class MyntraBot:
    def __init__(self, account_id):
        self.account_id = account_id
        self.driver = None
        self.ready = False
        self.place_order_btn = None

    def start(self):
        """Opens browser and logs in"""
        options = webdriver.ChromeOptions()
        options.add_argument("--disable-blink-features=Automation")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        # Headless mode saves resources but you won't see what's happening
        # options.add_argument("--headless") 
        
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        self.driver.get("https://www.myntra.com/")
        
        try:
            login_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='loginButton']"))
            )
            login_btn.click()
            return self.account_id, "Browser Opened"
        except Exception as e:
            return self.account_id, f"Error: {e}"

    def enter_otp(self, otp):
        """Enters the OTP provided by user"""
        try:
            otp_input = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.NAME, "otp"))
            )
            otp_input.clear()
            otp_input.send_keys(otp)
            
            submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            submit_btn.click()
            
            # Wait for successful login
            WebDriverWait(self.driver, 20).until(
                EC.url_contains("myntra.com") and "login" not in self.driver.current_url.lower()
            )
            self.ready = True
            return self.account_id, "Logged In"
        except Exception as e:
            return self.account_id, f"OTP Error: {e}"

    def prepare_order(self, product_url):
        """Adds item to cart and finds the 'Place Order' button"""
        if not self.ready:
            return self.account_id, "Not Logged In"
            
        try:
            self.driver.get(product_url)
            
            # Add to Cart
            add_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='addCartBtn']"))
            )
            add_btn.click()
            
            # Go to Cart
            cart_icon = self.driver.find_element(By.CSS_SELECTOR, "a[data-testid='cartIcon']")
            cart_icon.click()
            
            # Find Place Order Button
            place_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.place-order-btn"))
            )
            self.place_order_btn = place_btn
            return self.account_id, "Ready to Order"
        except Exception as e:
            return self.account_id, f"Cart Error: {e}"

    def click_order(self):
        """Actually clicks the button"""
        if self.place_order_btn:
            self.place_order_btn.click()
            return self.account_id, "Ordered!"
        return self.account_id, "Failed"

def sync_order(accounts_data):
    """Syncs all bots to order at the exact same time"""
    n = len(accounts_data)
    barrier = threading.Barrier(n)
    results = []

    def worker(bot_obj, url, coupon):
        try:
            bot_obj.prepare_order(url)
            # All bots wait here until everyone has reached this line
            barrier.wait(timeout=30)
            result = bot_obj.click_order()
            results.append(result)
        except Exception as e:
            results.append((bot_obj.account_id, f"Sync Error: {e}"))

    threads = []
    for item in accounts_data:
        t = threading.Thread(target=worker, args=(item[0], item[1], item[2]))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    return results

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    account_id = data['id']
    phone = data['phone']
    
    if account_id in active_bots:
        return jsonify({"status": "Already Active"})

    bot = MyntraBot(account_id)
    active_bots[account_id] = bot
    
    # Start browser in background thread
    def start_thread():
        status_msg = bot.start()[1]
    
    threading.Thread(target=start_thread, daemon=True).start()
    return jsonify({"status": "Opening Browser..."})

@app.route('/api/otp', methods=['POST'])
def api_otp():
    data = request.json
    account_id = data['id']
    otp = data['otp']
    
    if account_id in active_bots:
        res = active_bots[account_id].enter_otp(otp)
        return jsonify({"status": res[1]})
    return jsonify({"status": "Account not found"})

@app.route('/api/order', methods=['POST'])
def api_order():
    data = request.json
    url = data['url']
    coupon = data.get('coupon', '')
    
    # Gather all ready bots
    accounts_to_sync = []
    for acc_id, bot in active_bots.items():
        accounts_to_sync.append([bot, url, coupon])
        
    results = sync_order(accounts_to_sync)
    return jsonify({"results": results})

@app.route('/')
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Myntra Bot</title>
        <style>
            body { font-family: sans-serif; padding: 20px; background: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
            input, button { padding: 10px; margin: 5px 0; width: 100%; box-sizing: border-box; }
            button { background: #ff3f6c; color: white; border: none; cursor: pointer; }
            .log { background: #eee; padding: 10px; height: 150px; overflow-y: scroll; font-size: 12px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Myntra Bot Controller</h1>
            <input type="text" id="accId" placeholder="Account Name">
            <input type="text" id="accPhone" placeholder="Phone Number">
            <button onclick="loginAccount()">Login Account</button>
            <input type="text" id="otpInput" placeholder="Enter OTP Here">
            <button onclick="submitOtp()">Submit OTP</button>
            <hr>
            <input type="text" id="prodUrl" placeholder="Product URL">
            <input type="text" id="couponCode" placeholder="Coupon Code">
            <button onclick="placeOrder()" style="background: green;">START ORDER</button>
            <div class="log" id="logs"></div>
        </div>
        <script>
            function log(msg) {
                const div = document.getElementById('logs');
                div.innerHTML += `<div>${new Date().toLocaleTimeString()}: ${msg}</div>`;
                div.scrollTop = div.scrollHeight;
            }
            async function loginAccount() {
                const id = document.getElementById('accId').value;
                const phone = document.getElementById('accPhone').value;
                await fetch('/api/login', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id, phone}) });
                log(`Account ${id} opened.`);
            }
            async function submitOtp() {
                const id = document.getElementById('accId').value;
                const otp = document.getElementById('otpInput').value;
                const res = await fetch('/api/otp', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id, otp}) });
                const data = await res.json();
                log(`OTP Status: ${data.status}`);
            }
            async function placeOrder() {
                const url = document.getElementById('prodUrl').value;
                const coupon = document.getElementById('couponCode').value;
                log("Sending order...");
                const res = await fetch('/api/order', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url, coupon}) });
                const data = await res.json();
                log("Results: " + JSON.stringify(data.results));
            }
        </script>
    </body>
    </html>
    """)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
