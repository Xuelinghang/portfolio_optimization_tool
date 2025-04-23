# run.py

import os
import threading
from app import create_app, db # Import db here if init_market_data needs access to db

# Assuming market_fetcher has init and fetch_market_data
from app.market_fetcher import init as init_market_scheduler
from app.market_fetcher import fetch_market_data

# Create the Flask app instance
app = create_app()

# --- Market Data Scheduler Initialization ---
# This should happen once when the application starts
def initialize_and_start_market_data():
    with app.app_context(): # Ensure it runs within the Flask application context
        try:
            print("Initializing and starting market data scheduler...")
            # Initialize the scheduler
            scheduler = init_market_scheduler(app) # Pass app if scheduler needs context
            print("Market data scheduler initialized.")

            # Optionally, perform an initial data fetch on startup
            print("[Performing initial market data fetch...]")
            fetch_market_data(historical=False) # Fetch recent data
            # fetch_market_data(historical=True) # Uncomment if you need historical data populated immediately on startup
            print("Initial market data fetch attempted.")

            # Start the scheduler if it's not already running
            # Check scheduler state if necessary before starting
            if scheduler and not scheduler.running:
                 print("Starting market data scheduler...")
                 scheduler.start()
                 print("Market data scheduler started.")
            elif scheduler:
                 print("Market data scheduler is already running.")
            else:
                 print("Warning: Market data scheduler could not be initialized.")


        except Exception as e:
            print(f"CRITICAL ERROR during market data initialization: {e}")
            import traceback
            print(traceback.format_exc())
            # The app can still run, but market data fetching might not work


# Run market data initialization in a separate thread to avoid blocking the main Flask app startup
# Ensure this doesn't happen multiple times if using reloader (debug=True)
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
    # Only run this in the main process, not the reloader process
    market_init_thread = threading.Thread(target=initialize_and_start_market_data)
    market_init_thread.daemon = True # Allows the main thread to exit
    market_init_thread.start()
    print("Market data initialization thread started.")
else:
    print("Skipping market data initialization in reloader process.")

# --- Main App Execution ---
if __name__ == '__main__':
    print("Starting Flask application...")
    # Ensure SECRET_KEY is set in your environment or app config for session
    # In production, use a production-ready WSGI server (gunicorn, uwsgi)
    # debug=True enables the debugger and auto-reloader
    app.run(host='0.0.0.0', port=5050, debug=True)
    print("Flask application stopped.")
