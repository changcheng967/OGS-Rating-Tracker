from flask import Flask, render_template, jsonify
from supabase import create_client
import requests
import threading
import time
from datetime import datetime
import pytz
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Initialize Supabase client
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

# Toronto timezone
TORONTO_TZ = pytz.timezone('America/Toronto')

# Convert UTC datetime to Toronto time
def convert_to_toronto_time(utc_dt):
    utc_dt = pytz.utc.localize(utc_dt)  # Ensure UTC datetime is timezone-aware
    return utc_dt.astimezone(TORONTO_TZ)

# Fetch latest rating data
def fetch_ratings():
    try:
        res = requests.get('https://online-go.com/termination-api/player/1734688')
        if res.status_code == 429:
            print('Rate limited.')
            return None
        data = res.json()['ratings']
        return {
            'overall': data['overall']['rating'],
            '9x9': data['9x9']['rating'],
            '13x13': data['13x13']['rating'],
            '19x19': data['19x19']['rating'],
        }
    except Exception as e:
        print('Error fetching:', e)
        return None

# Store ratings in database (if changed)
def store_ratings():
    while True:
        ratings = fetch_ratings()
        if ratings:
            now_utc = datetime.utcnow()
            now_toronto = convert_to_toronto_time(now_utc)
            for category, rating in ratings.items():
                response = supabase.table('ratings').select('*').eq('category', category).order('timestamp', desc=True).limit(1).execute()
                existing_data = response.data
                if not existing_data or abs(existing_data[0]['rating'] - rating) > 0.0001:
                    supabase.table('ratings').insert({
                        "category": category,
                        "timestamp": now_toronto.isoformat(),
                        "rating": rating
                    }).execute()
                    print(f'[{now_toronto}] {category}: {rating}')
                    update_extreme_ratings(category, rating)
        time.sleep(5)

# Update extreme ratings (highest and lowest)
def update_extreme_ratings(category, new_rating):
    try:
        extreme_rating = supabase.table('extreme_ratings').select('*').eq('category', category).execute().data
        if not extreme_rating:
            supabase.table('extreme_ratings').insert({
                "category": category,
                "highest": new_rating,
                "lowest": new_rating
            }).execute()
        else:
            highest = extreme_rating[0]['highest']
            lowest = extreme_rating[0]['lowest']
            if new_rating > highest:
                supabase.table('extreme_ratings').update({"highest": new_rating}).eq('category', category).execute()
            if new_rating < lowest:
                supabase.table('extreme_ratings').update({"lowest": new_rating}).eq('category', category).execute()
    except Exception as e:
        print(f"Error updating extreme ratings for {category}: {e}")

# Start background thread
threading.Thread(target=store_ratings, daemon=True).start()

# Routes
@app.route('/')
def index():
    try:
        extreme_ratings = supabase.table('extreme_ratings').select('*').execute().data
        if not extreme_ratings:
            print("No extreme ratings found.")
        return render_template('index.html', extreme_ratings=extreme_ratings)
    except Exception as e:
        print(f"Error fetching extreme ratings: {e}")
        return render_template('index.html', extreme_ratings=None)

@app.route('/history/<category>')
def history(category):
    data = []
    try:
        response = supabase.table('ratings').select('timestamp', 'rating').eq('category', category).order('timestamp').execute()
        for entry in response.data:
            timestamp = datetime.fromisoformat(entry['timestamp']).astimezone(TORONTO_TZ)
            data.append({
                'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S %Z'),
                'rating': entry['rating']
            })
    except Exception as e:
        print(f"Error fetching history for {category}: {e}")
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True)
