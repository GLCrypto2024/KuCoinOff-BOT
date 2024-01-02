from telethon import TelegramClient, events, errors
from dotenv import load_dotenv
import os
import asyncio
import ccxt
from datetime import datetime, timedelta
import re
import websockets
import json
import requests
import hmac
import hashlib
import base64
import time
import pytz


# Load environment variables
load_dotenv()
api_id = os.getenv('TELEGRAM_API_ID')
api_hash = os.getenv('TELEGRAM_API_HASH')
#username = 't.me/KucoinNewsSpanish'  #WORKING
username = '@Kucoin_trading_2024_bot'
#username = 'mega_pump_group'

# Initialize the Telegram Client
client = TelegramClient('session_name', api_id, api_hash)

# Initialize Kucoin
kucoin = ccxt.kucoin({
    'apiKey': os.getenv('KUCOIN_API_KEY'),
    'secret': os.getenv('KUCOIN_SECRET'),
    'password': os.getenv('KUCOIN_PASSPHRASE'),
})

# Target sell percentage (%20.0)
TARGET_SELL_PERCENTAGE = 0.2

purchase_info = {} #To store variables and calculate profit when selling
admin_id = 't.me/KucoinNewsSpanish'

# Target sell percentage (%60)
#TARGET_SELL_PERCENTAGE = 0.60

# Function to get Kucoin public token
def get_kucoin_public_token():
    url = "https://api.kucoin.com/api/v1/bullet-public"  # Kucoin public token endpoint
    response = requests.post(url)
    data = response.json()

    if response.status_code == 200 and data['code'] == '200000':
        return data['data']['token'], data['data']['instanceServers'][0]['endpoint']
    else:
        raise Exception(f"Failed to get public token: {data}")
    
# Headers necessary to check the account balance    

def create_auth_headers(api_key, api_secret, api_passphrase, method, endpoint, body=''):
    now = int(time.time() * 1000)
    str_to_sign = str(now) + method + endpoint + body
    signature = base64.b64encode(
        hmac.new(api_secret.encode('utf-8'), str_to_sign.encode('utf-8'), hashlib.sha256).digest())

    passphrase = base64.b64encode(
        hmac.new(api_secret.encode('utf-8'), api_passphrase.encode('utf-8'), hashlib.sha256).digest())

    headers = {
        "KC-API-SIGN": signature,
        "KC-API-TIMESTAMP": str(now),
        "KC-API-KEY": api_key,
        "KC-API-PASSPHRASE": passphrase,
        "KC-API-KEY-VERSION": "2"
    }
    return headers
    

# Function to get account details
def get_account_details(account_id, currency):
    api_key = os.getenv('KUCOIN_API_KEY')
    api_secret = os.getenv('KUCOIN_SECRET')
    api_passphrase = os.getenv('KUCOIN_PASSPHRASE')
    method = 'GET'
    endpoint = f"/api/v1/accounts/{account_id}"
    headers = create_auth_headers(api_key, api_secret, api_passphrase, method, endpoint)
    url = f"https://api.kucoin.com{endpoint}"
    response = requests.get(url, headers=headers)
    data = response.json()


    if response.status_code == 200 and 'data' in data:
        # Check if data['data'] is a dictionary (as in your second output)
        if isinstance(data['data'], dict):
            if data['data']['currency'] == currency:
                return data['data']['available']
        # Check if data['data'] is a list (as in your first output)
        elif isinstance(data['data'], list):
            for account in data['data']:
                if account['currency'] == currency:
                    return account['available']
        else:
            raise Exception("Unexpected data format in response")
    else:
        raise Exception(f"Failed to get account details: {data}")
    
# Function to get account balance
    
def get_currency_account_id(currency):
    api_key = os.getenv('KUCOIN_API_KEY')
    api_secret = os.getenv('KUCOIN_SECRET')
    api_passphrase = os.getenv('KUCOIN_PASSPHRASE')

    method = 'GET'
    endpoint = "/api/v1/accounts"

    headers = create_auth_headers(api_key, api_secret, api_passphrase, method, endpoint)
    url = f"https://api.kucoin.com{endpoint}"

    response = requests.get(url, headers=headers)
    data = response.json()

    if response.status_code == 200 and 'data' in data and isinstance(data['data'], list):
        for account in data['data']:
            if account['currency'] == currency and account['type'] == 'trade':
                return account['id']
        raise Exception(f"Account ID for {currency} not found")
    else:
        raise Exception(f"Failed to fetch account IDs: {data}")

# Telegram username for receiving confirmation messages
    
async def send_telegram_message(message):
    receiver_username = '@GLCrypto24'  # Replace with your Telegram username
    await client.send_message(receiver_username, message)

async def kucoin_ws_monitor_price_and_sell(coin, target_price, account_id):
    token, endpoint = get_kucoin_public_token()
    async with websockets.connect(endpoint + '?token=' + token) as ws:
        # Wait for the welcome message
        welcome_msg = await ws.recv()
        #print("Received:", welcome_msg)

        # Subscribe to the topic
        subscribe_message = {
            "id": str(datetime.now().timestamp()),
            "type": "subscribe",
            "topic": f"/market/ticker:{coin}-USDT",
            "response": True
        }
        await ws.send(json.dumps(subscribe_message))

        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=30)
                data = json.loads(msg)

                if data['type'] == 'pong':
                    continue

                if data['type'] == 'message':
                    current_price = float(data['data']['price'])
                    current_price_formatted = "{:.4f}".format(current_price)
                    target_price_formatted = "{:.4f}".format(target_price)
                    print(f"Current price of {coin}: {current_price_formatted} - Target: |{target_price_formatted}|")
                    if current_price >= target_price:
                        print(f"Target price reached. Attempting to sell {coin}. Current price: {current_price_formatted}, Target: {target_price_formatted}")
                        await send_telegram_message(f"Target price reached. Attempting to sell {coin}. Current price: {current_price_formatted}, Target: {target_price_formatted}")

                        while True:
                            try:
                                account_id = get_currency_account_id(coin)
                                available_balance = get_account_details(account_id, coin)
                                if float(available_balance) > 0:
                                    # Attempt to create a sell order
                                    sell_order = None
                                    try:
                                        sell_order = kucoin.create_order(coin + '/USDT', 'market', 'sell', float(available_balance))
                                    except Exception as e:
                                        print(f"Error creating sell order for {coin}: {e}")
                                        # Log the full exception details
                                        import traceback
                                        traceback.print_exc()

                                        sell_order = None

                                    if sell_order and 'id' in sell_order:
                                        # Calculate profit
                                        sell_amount = float(available_balance)
                                        purchase_amount = purchase_info[coin]['quantity'] * purchase_info[coin]['purchase_price']
                                        sell_total = sell_amount * current_price
                                        profit = sell_total - purchase_amount

                                        message = f"Sell order placed for {sell_amount} {coin}. Order ID: {sell_order['id']}. Profit: {profit:.2f} USD."
                                        print(message)
                                        await send_telegram_message(message)
                                    else:
                                        print(f"Failed to place sell order for {coin}. Response: {sell_order}")
                                        await send_telegram_message(f"Failed to place sell order for {coin}. Check logs for details.")
                                    
                                    break  # Exit the while loop if successful
                                else:
                                    print(f"No balance available to sell for {coin}. Retrying...")
                                    await asyncio.sleep(2)  # Wait for 2 seconds before retrying
                            except Exception as e:
                                print(f"Error in selling {coin}: {e}. Retrying...")
                                await send_telegram_message(f"Error in selling {coin}: {e}. Retrying...")
                                await asyncio.sleep(2)  # Wait for 2 seconds before retrying

                        # Removed 'await client.disconnect()' to keep the client connected
                        return

            except asyncio.TimeoutError:
                await ws.send(json.dumps({"id": str(datetime.now().timestamp()), "type": "ping"}))

            except Exception as e:
                print(f"WebSocket error: {e}")
                await asyncio.sleep(2) # Wait 2 seconds before retrying


@client.on(events.NewMessage(chats=username))
async def handler(event):
        message_text = event.message.text
        print("Message received")
    #sender = event.message.sender_id

    # Check if the message is from the group admin and not a reply
    #if sender == admin_id and not event.message.is_reply:  
    #    print('New message received:', message_text)

        # Check if the message contains either "#NewListing" or "#NuevoListado"
        if "#NewListing" in message_text or "#NuevoListado" in message_text:
            # Extract coin name in caps inside the first set of parentheses
            coin_match = re.search(r'\(([A-Z]+)\)', message_text)
            if coin_match:
                coinToBuy = coin_match.group(1)
                print("Coin to buy:", coinToBuy)

                # Extract date and time
                date_time_match = re.search(r'(\d{2}:\d{2}) del (\d{1,2}) de (\w+) de (\d{4})', message_text)
                if date_time_match:
                    time_str, day, month, year = date_time_match.groups()
                    # Convert Spanish month name to English if necessary
                    month_translation = {
                        'enero': 'January', 'febrero': 'February', 'marzo': 'March',
                        'abril': 'April', 'mayo': 'May', 'junio': 'June',
                        'julio': 'July', 'agosto': 'August', 'septiembre': 'September',
                        'octubre': 'October', 'noviembre': 'November', 'diciembre': 'December'
                    }
                    month_english = month_translation.get(month.lower(), month)
                    date_time_str = f"{day} {month_english} {year} {time_str}"
                    buy_time = datetime.strptime(date_time_str, '%d %B %Y %H:%M').replace(tzinfo=pytz.UTC)

                    print(f"Scheduled buy time (UTC): {buy_time}")
                    # Schedule buy operation
                    asyncio.create_task(schedule_buy(coinToBuy, buy_time))
                else:
                    print("Date and time format not recognized in message.")
            else:
                print("Coin name not found in message.")
        else:
            print("Message does not contain '#NewListing' or '#NuevoListado'")
    #else:
    #    print("Message is not from the admin or is a reply.")

async def schedule_buy(coin, buy_time):
    # Convert buy_time to UTC if necessary
    buy_time_utc = buy_time.replace(tzinfo=pytz.UTC)
    delay_seconds = (buy_time_utc - datetime.now(pytz.UTC)).total_seconds()
    if delay_seconds > 0:
        message = f"Scheduling buy operation for {coin} at {buy_time_utc} UTC"
        print(message)
        await send_telegram_message(message)
        await asyncio.sleep(delay_seconds)
        await execute_buy_order(coin)
    else:
        message = "Scheduled buy time is in the past."
        print(message)
        await send_telegram_message(message) 
                            
async def execute_buy_order(coin):
    try:
        message = f"Attempting to buy {coin}"
        print(message)
        await send_telegram_message(message)

        # Retrieve the account ID for the coin
        account_id = get_currency_account_id(coin)
        if account_id is None:
            print(f"Failed to get account ID for {coin}")
            return
        
        # Fetch current price and calculate amount
        symbol = coin + '/USDT'
        ticker = kucoin.fetch_ticker(symbol)
        current_price = (ticker['ask'] + ticker['bid']) / 2

        amount_in_usdt = 100  # THE AMOUNT OF USD YOU WANT TO SPEND IN THE BUYING #
        amount = amount_in_usdt / current_price

        # Place the buy order using the account ID
        buy_order = kucoin.create_order(symbol, 'market', 'buy', amount)
        message = f"Order placed for {coin}. Purchased amount: {amount} At {current_price} USD"  # Log the response
        print("Order placed for", coin, '. Purchased amount:', amount, 'At price:', current_price, 'USD')
        await send_telegram_message(message)

        purchase_info[coin] = {
            'purchase_price': current_price,
            'quantity': amount,
        }

        # Schedule to monitor and sell at target percentage
        target_sell_price = current_price * (1 + TARGET_SELL_PERCENTAGE)
        asyncio.create_task(kucoin_ws_monitor_price_and_sell(coin, target_sell_price, amount))
       
    except Exception as e:
        message = f"Exception in execute_buy_order for {coin}: {e}"
        print(message)
        await send_telegram_message(message)
        import traceback
        traceback.print_exc()  # Print the full traceback

async def main():
    await client.start()
    try:
        await client.get_entity(username)
        print(f"Listening for messages in group/user: {username}")
    except (ValueError):
        print(f"Error: Group/User '{username}' not found.")
        return

    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        token, endpoint = get_kucoin_public_token()
        print("Received Kucoin public token and endpoint.")
    except Exception as e:
        print(f"Error obtaining Kucoin public token: {e}")
        exit(1)

# Running the client
with client:
    client.loop.run_until_complete(main())
