# fix_asset_types.py

from app import db
from app.models import Asset
from app.market_fetcher import fetch_and_map_asset_details
from flask import Flask

def fix_asset_types():
    """Scan all assets and fix missing or wrong asset types."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////Users/wangjinchan/Desktop/Duke/2025_SPRING/512/portfolio_optimization_tool/instance/portfolio.db"  # <-- Adjust your DB path if needed
    app.secret_key = "secret_key"  # Dummy key
    db.init_app(app)

    with app.app_context():
        assets = Asset.query.all()
        print(f"Found {len(assets)} assets to scan and patch.")

        updated = 0
        skipped = 0

        for asset in assets:
            try:
                print(f"Processing {asset.symbol} (Current type: {asset.asset_type})")

                # Skip if already good
                if asset.asset_type and asset.asset_type.lower() in ["stock", "etf", "crypto", "bond"]:
                    print(f"  Skipped (already valid type): {asset.symbol}")
                    skipped += 1
                    continue

                # Fetch fresh details
                details = fetch_and_map_asset_details(asset.symbol)

                if details and details.get('type') and details['type'] != 'Unknown':
                    print(f"  Updating {asset.symbol}: setting type to '{details['type']}' and name to '{details['name']}'")
                    asset.asset_type = details['type']
                    asset.company_name = details['name']  # Optional: update name too
                    updated += 1
                else:
                    print(f"  Could not fetch valid type for {asset.symbol}. Leaving unchanged.")
                    skipped += 1

            except Exception as e:
                print(f"Error processing {asset.symbol}: {e}")
                skipped += 1

        db.session.commit()
        print(f"Finished fixing assets. Updated: {updated}, Skipped: {skipped}")

if __name__ == "__main__":
    fix_asset_types()
