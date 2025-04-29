# app/routes/admin.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from app.models import User, Transaction, Portfolio, PortfolioAsset, Asset
from flask_login import login_required, current_user
import random
import string
from sqlalchemy import func, desc, extract
from datetime import datetime, timedelta, UTC

# Initialize Blueprint
admin_bp = Blueprint('admin_bp', __name__)


def generate_random_password():
    """Generates a random password."""
    length = 12
    characters = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(characters) for _ in range(length))


@admin_bp.route('/admin', methods=['GET', 'POST'])
@login_required
def admin_dashboard():
    """
    Render the main Admin Dashboard, allowing:
    - Viewing & managing users
    - Viewing system transactions
    - Showing summary metrics at the top
    """
    if not current_user.is_admin:
        flash('You are not authorized to view this page.', 'danger')
        return redirect(url_for('portfolio.home'))

    # --- Core data for users & transactions tables ---
    users = User.query.all()
    transactions = Transaction.query.order_by(Transaction.transaction_date.desc()).all()

    # --- Summary metrics for the dashboard header ---
    total_users        = User.query.count()
    active_users       = User.query.filter_by(is_active=True).count()
    total_portfolios   = Portfolio.query.count()
    total_transactions = Transaction.query.count()

    # --- Handle user actions (disable / reset password) ---
    if request.method == 'POST':
        action  = request.form.get('action')
        user_id = request.form.get('user_id')
        user    = User.query.get(user_id)

        if not user:
            flash('User not found!', 'danger')
        elif action == 'disable':
            user.is_active = False
            db.session.commit()
            flash(f'User {user.username} has been disabled.', 'success')
        elif action == 'reset_password':
            new_password = generate_random_password()
            user.set_password(new_password)
            db.session.commit()
            flash(f'Password for {user.username} has been reset. New password: {new_password}', 'success')

        return redirect(url_for('admin_bp.admin_dashboard'))

    return render_template(
        'admin.html',
        users=users,
        transactions=transactions,
        total_users=total_users,
        active_users=active_users,
        total_portfolios=total_portfolios,
        total_transactions=total_transactions
    )


# ──────────────────────────────────────────────────────────────────────
# Portfolio Analysis Endpoint (basic version)
# ──────────────────────────────────────────────────────────────────────
@admin_bp.route('/analysis/portfolios', methods=['GET'])
@login_required
def analyze_portfolios():
    """
    Returns JSON with:
      - Total portfolios
      - Avg / max / min tickers per portfolio
      - Top 10 most-used tickers
    (Advanced metrics removed for now.)
    """
    if not current_user.is_admin:
        return jsonify({'error': 'Forbidden'}), 403

    # Total portfolios
    total_portfolios = Portfolio.query.count()

    # Count tickers in each portfolio

    counts_q = (
        db.session.query(
            PortfolioAsset.portfolio_id,
            func.count(PortfolioAsset.id).label('n_tickers')
        )
        .group_by(PortfolioAsset.portfolio_id)
        .all()
    )
    counts = [row.n_tickers for row in counts_q]
    avg_tickers = round(sum(counts) / len(counts), 2) if counts else 0
    max_tickers = max(counts) if counts else 0
    min_tickers = min(counts) if counts else 0
    raw = (
        db.session.query(
            Asset.symbol,
            func.count(PortfolioAsset.id).label('freq')
        )
        .join(Asset, PortfolioAsset.asset_id == Asset.id)
        .group_by(Asset.symbol, PortfolioAsset.asset_id)
        .order_by(desc('freq'))
        .limit(50)    # fetch extra in case we drop duplicates below
        .all()
    )

    top_map = {}
    for symbol, freq in raw:
        if symbol not in top_map or freq > top_map[symbol]:
            top_map[symbol] = freq

    # 4) Build a sorted list of the top 10 symbols by freq
    top_data = sorted(
        [{"symbol": s, "freq": f} for s, f in top_map.items()],
        key=lambda x: x["freq"],
        reverse=True
    )[:10]

    # 5) Return everything as JSON
    return jsonify({
        "total_portfolios":            total_portfolios,
        "avg_tickers_per_portfolio":   avg_tickers,
        "max_tickers_in_portfolio":    max_tickers,
        "min_tickers_in_portfolio":    min_tickers,
        "top_10":                      top_data
    })


# ──────────────────────────────────────────────────────────────────────
# Transactions Analysis Endpoint
# ──────────────────────────────────────────────────────────────────────
@admin_bp.route('/analysis/transactions', methods=['GET'])
@login_required
def analyze_transactions():
    # Only admins allowed
    if not current_user.is_admin:
        return jsonify({'error': 'Forbidden'}), 403

    # 1) Total transactions
    total_tx = Transaction.query.count()

    # 2) Daily volume (grouped by date)
    daily_q = (
        db.session.query(
            func.date(Transaction.transaction_date).label('day'),
            func.count().label('cnt')
        )
        .group_by('day')
        .order_by('day')
        .all()
    )
    daily_volume = []
    for day_val, cnt in daily_q:
        # day_val might already be a 'YYYY-MM-DD' string
        if isinstance(day_val, str):
            day_str = day_val
        else:
            day_str = day_val.strftime('%Y-%m-%d')
        daily_volume.append({"day": day_str, "count": cnt})

    # 3) Average transactions per user per day
    user_count = User.query.count()
    avg_tx_per_user_per_day = (
        round(total_tx / (user_count * len(daily_volume)), 4)
        if daily_volume and user_count else 0
    )

    # 4) Peak transaction hours
    peak_q = (
        db.session.query(
            extract('hour', Transaction.transaction_date).label('hour'),
            func.count().label('cnt')
        )
        .group_by('hour')
        .order_by(desc('cnt'))
        .all()
    )
    peak_hours = [{"hour": int(hr), "count": cnt} for hr, cnt in peak_q]

    # 5) Most-traded assets (join to Asset for symbol)
    traded_q = (
        db.session.query(
            Asset.symbol,
            func.count(Transaction.id).label('freq')
        )
        .join(Asset, Transaction.asset_id == Asset.id)
        .group_by(Asset.symbol)
        .order_by(desc('freq'))
        .limit(10)
        .all()
    )
    most_traded = [sym for sym, _ in traded_q]

    # 6) Return JSON
    return jsonify({
        "total_transactions":                total_tx,
        "avg_transactions_per_user_per_day": avg_tx_per_user_per_day,
        "daily_volume":                      daily_volume,
        "peak_hours":                        peak_hours,
        "most_traded_assets":                most_traded
    })

# ──────────────────────────────────────────────────────────────────────
# Users Analysis Endpoint
# ──────────────────────────────────────────────────────────────────────
@admin_bp.route('/analysis/users', methods=['GET'])
@login_required
def analyze_users():
    if not current_user.is_admin:
        return jsonify({'error': 'Forbidden'}), 403

    # Summary metrics
    total_users  = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()

    # Avg portfolios per user
    user_port_counts = (
        db.session.query(
            Portfolio.user_id,
            func.count(Portfolio.id).label('cnt')
        )
        .group_by(Portfolio.user_id)
        .all()
    )
    counts = [cnt for _, cnt in user_port_counts]
    avg_ports = round(sum(counts) / len(counts), 2) if counts else 0

    # Distribution: how many users have 1 portfolio, 2 portfolios, etc.
    # (This can stay as-is or you can improve it to use a subquery if you like.)
    dist_q = (
        db.session.query(
            func.count(Portfolio.id).label('n_portfolios'),
            func.count().label('n_users')
        )
        .group_by(Portfolio.user_id)
        .order_by('n_portfolios')
        .all()
    )
    distribution = [{"n_portfolios": n, "n_users": u} for n, u in dist_q]

    # Top 10 users by transaction count
    top_users_q = (
        db.session.query(
            User.username,
            func.count(Transaction.id).label('tx_count')
        )
        .join(Transaction, Transaction.user_id == User.id)
        .group_by(User.username)
        .order_by(desc('tx_count'))
        .limit(10)
        .all()
    )
    top_active_users = [{"user": name, "tx_count": cnt} for name, cnt in top_users_q]

    return jsonify({
        "total_users":             total_users,
        "active_users":            active_users,
        "avg_portfolios_per_user": avg_ports,
        "portfolio_distribution":  distribution,
        "top_active_users":        top_active_users
    })

@admin_bp.route('/admin/portfolios')
@login_required
def admin_portfolios_page():
    if not current_user.is_admin:
        flash('Not authorized', 'danger')
        return redirect(url_for('portfolio.home'))
    return render_template('admin_portfolio_analysis.html')

@admin_bp.route('/admin/transactions', methods=['GET'])
@login_required
def admin_transactions_page():
    """
    Renders the Transactions Analysis page for admins.
    """
    if not current_user.is_admin:
        flash('Not authorized', 'danger')
        return redirect(url_for('portfolio.home'))
    return render_template('admin_transactions_analysis.html')

@admin_bp.route('/admin/users', methods=['GET'])
@login_required
def admin_users_page():
    """
    Renders the Users Analysis page for admins.
    """
    if not current_user.is_admin:
        flash('Not authorized', 'danger')
        return redirect(url_for('portfolio.home'))
    return render_template('admin_users_analysis.html')

