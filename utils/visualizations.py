import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import matplotlib.pyplot as plt

def plot_portfolio_growth(portfolio_values, title="Portfolio Growth"):
    """
    Create a line chart showing portfolio value over time.
    
    Args:
        portfolio_values: Series containing portfolio values with date index
        title: Chart title
    
    Returns:
        Plotly figure object
    """
    fig = px.line(
        portfolio_values, 
        x=portfolio_values.index, 
        y=portfolio_values.values,
        title=title,
        labels={'x': 'Date', 'y': 'Portfolio Value'},
    )
    
    fig.update_layout(
        hovermode='x unified',
        xaxis_title='Date',
        yaxis_title='Value',
        xaxis=dict(
            type='date',
            tickformat='%b %Y'
        ),
        yaxis=dict(
            tickprefix='$',
            showgrid=True
        )
    )
    
    return fig

def plot_annual_returns(annual_returns, title="Annual Returns"):
    """
    Create a bar chart displaying annual returns.
    
    Args:
        annual_returns: Dictionary with years as keys and returns as values
        title: Chart title
    
    Returns:
        Plotly figure object
    """
    years = list(annual_returns.keys())
    returns = list(annual_returns.values())
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=years,
        y=[r * 100 for r in returns],
        marker_color=['#1f77b4' if r >= 0 else '#d62728' for r in returns],
        text=[f"{r*100:.1f}%" for r in returns],
        textposition='auto',
    ))
    
    fig.update_layout(
        title=title,
        xaxis_title='Year',
        yaxis_title='Return (%)',
        yaxis=dict(
            ticksuffix='%',
            zeroline=True,
            zerolinewidth=2,
            zerolinecolor='black',
            showgrid=True
        )
    )
    
    return fig

def plot_asset_allocation(assets_df, column='Category', title=None):
    """
    Create a pie chart showing asset allocation.
    
    Args:
        assets_df: DataFrame containing asset information
        column: Column to use for categorization
        title: Chart title
    
    Returns:
        Plotly figure object
    """
    # Group by category and sum weights
    allocation_data = assets_df.groupby(column)['Weight'].sum().reset_index()
    
    # Create pie chart
    fig = px.pie(
        allocation_data, 
        values='Weight', 
        names=column,
        title=title if title else f"Allocation by {column}",
        hole=0.3,
    )
    
    fig.update_traces(
        textposition='inside',
        textinfo='percent+label',
        hoverinfo='label+percent+value',
        texttemplate='%{label}<br>%{percent:.1%}'
    )
    
    return fig

def plot_drawdowns(portfolio_values, title="Portfolio Drawdowns"):
    """
    Create a line chart showing portfolio drawdowns over time.
    
    Args:
        portfolio_values: Series containing portfolio values with date index
        title: Chart title
    
    Returns:
        Plotly figure object
    """
    # Calculate rolling maximum
    rolling_max = portfolio_values.cummax()
    
    # Calculate drawdowns
    drawdowns = (portfolio_values / rolling_max - 1) * 100
    
    fig = px.line(
        drawdowns, 
        x=drawdowns.index, 
        y=drawdowns.values,
        title=title,
        labels={'x': 'Date', 'y': 'Drawdown (%)'},
    )
    
    fig.update_layout(
        hovermode='x unified',
        xaxis_title='Date',
        yaxis_title='Drawdown (%)',
        xaxis=dict(
            type='date',
            tickformat='%b %Y'
        ),
        yaxis=dict(
            ticksuffix='%',
            zeroline=True,
            zerolinewidth=1,
            zerolinecolor='grey',
            showgrid=True
        )
    )
    
    # Color the line red and fill area
    fig.update_traces(
        line=dict(color='#d62728', width=1.5),
        fill='tozeroy',
        fillcolor='rgba(214, 39, 40, 0.2)'
    )
    
    return fig

def plot_monthly_returns_heatmap(returns, title="Monthly Returns"):
    """
    Create a heatmap showing monthly returns by year.
    
    Args:
        returns: Series containing returns with date index
        title: Chart title
    
    Returns:
        Plotly figure object
    """
    # Resample to monthly if not already
    if not isinstance(returns.index.freq, pd.tseries.offsets.MonthEnd):
        monthly_returns = returns.resample('M').apply(lambda x: (1 + x).prod() - 1)
    else:
        monthly_returns = returns
    
    # Create a DataFrame with years as rows and months as columns
    returns_by_month = pd.DataFrame({
        'Year': monthly_returns.index.year,
        'Month': monthly_returns.index.month,
        'Return': monthly_returns.values
    })
    
    # Pivot the data
    heatmap_data = returns_by_month.pivot(index='Year', columns='Month', values='Return')
    
    # Replace column numbers with month names
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    heatmap_data.columns = month_names[:len(heatmap_data.columns)]
    
    # Create the heatmap
    fig = px.imshow(
        heatmap_data * 100,  # Convert to percentage
        labels=dict(x="Month", y="Year", color="Return (%)"),
        x=heatmap_data.columns,
        y=heatmap_data.index,
        color_continuous_scale=[[0, 'rgb(165,0,38)'], 
                                [0.5, 'rgb(255,255,255)'], 
                                [1, 'rgb(0,104,55)']],
        zmin=-10,  # Minimum percentage for color scale
        zmax=10,   # Maximum percentage for color scale
        aspect="auto",
        title=title
    )
    
    # Add return values as text
    for i, year in enumerate(heatmap_data.index):
        for j, month in enumerate(heatmap_data.columns):
            if pd.notna(heatmap_data.iloc[i, j]):
                value = heatmap_data.iloc[i, j] * 100
                text_color = 'black' if abs(value) < 5 else 'white'
                fig.add_annotation(
                    x=month,
                    y=year,
                    text=f"{value:.1f}%",
                    showarrow=False,
                    font=dict(color=text_color)
                )
    
    fig.update_layout(
        xaxis_title="",
        yaxis_title="",
        coloraxis_colorbar=dict(
            title="Return (%)",
            ticksuffix="%"
        )
    )
    
    return fig

def plot_rolling_returns(returns, window=36, title="Rolling Returns"):
    """
    Create a line chart showing rolling returns over time.
    
    Args:
        returns: Series containing returns with date index
        window: Rolling window in months
        title: Chart title
    
    Returns:
        Plotly figure object
    """
    # Convert to monthly if needed
    if not isinstance(returns.index.freq, pd.tseries.offsets.MonthEnd):
        monthly_returns = returns.resample('M').apply(lambda x: (1 + x).prod() - 1)
    else:
        monthly_returns = returns
    
    # Calculate rolling returns (annualized)
    rolling_return = (1 + monthly_returns).rolling(window=window).apply(
        lambda x: np.prod(1 + x) ** (12 / window) - 1, 
        raw=True
    )
    
    fig = px.line(
        rolling_return * 100,  # Convert to percentage
        title=f"{title} ({window // 12}-Year Rolling)",
        labels={'value': f'Annualized Return (%)'}
    )
    
    fig.update_layout(
        xaxis_title='Date',
        yaxis_title='Annualized Return (%)',
        yaxis=dict(
            ticksuffix='%',
            zeroline=True,
            zerolinewidth=1,
            zerolinecolor='grey',
            showgrid=True
        )
    )
    
    return fig

def plot_asset_returns_comparison(returns_data, period='1Y', title=None):
    """
    Create a horizontal bar chart comparing asset returns.
    
    Args:
        returns_data: Dictionary with asset returns Series
        period: Time period for comparison ('3M', 'YTD', '1Y', '3Y', '5Y')
        title: Chart title
    
    Returns:
        Plotly figure object
    """
    # Initialize data
    assets = []
    period_returns = []
    
    # Calculate returns for the specified period
    for asset, returns in returns_data.items():
        if len(returns) == 0:
            continue
            
        # Calculate return based on period
        if period == '3M':
            # Last 3 months
            if len(returns) >= 3:
                period_return = (1 + returns.tail(3)).prod() - 1
            else:
                period_return = np.nan
        elif period == 'YTD':
            # Year to date
            current_year = returns.index[-1].year
            ytd_returns = returns[returns.index.year == current_year]
            period_return = (1 + ytd_returns).prod() - 1 if not ytd_returns.empty else np.nan
        elif period == '1Y':
            # Last 12 months
            if len(returns) >= 12:
                period_return = (1 + returns.tail(12)).prod() - 1
            else:
                period_return = (1 + returns).prod() - 1
        elif period == '3Y':
            # Last 3 years (annualized)
            if len(returns) >= 36:
                period_return = (1 + returns.tail(36)).prod() ** (1/3) - 1
            else:
                period_return = np.nan
        elif period == '5Y':
            # Last 5 years (annualized)
            if len(returns) >= 60:
                period_return = (1 + returns.tail(60)).prod() ** (1/5) - 1
            else:
                period_return = np.nan
        else:
            period_return = np.nan
            
        if not np.isnan(period_return):
            assets.append(asset)
            period_returns.append(period_return * 100)  # Convert to percentage
    
    # Sort by return
    sorted_indices = np.argsort(period_returns)
    sorted_assets = [assets[i] for i in sorted_indices]
    sorted_returns = [period_returns[i] for i in sorted_indices]
    
    # Create horizontal bar chart
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        y=sorted_assets,
        x=sorted_returns,
        orientation='h',
        marker_color=['#1f77b4' if r >= 0 else '#d62728' for r in sorted_returns],
        text=[f"{r:.1f}%" for r in sorted_returns],
        textposition='auto',
    ))
    
    # Set title based on period
    period_descriptions = {
        '3M': '3-Month',
        'YTD': 'Year-to-Date',
        '1Y': '1-Year',
        '3Y': '3-Year Annualized',
        '5Y': '5-Year Annualized'
    }
    chart_title = title if title else f"{period_descriptions.get(period, period)} Returns"
    
    fig.update_layout(
        title=chart_title,
        xaxis_title='Return (%)',
        yaxis_title='Asset',
        xaxis=dict(
            ticksuffix='%',
            zeroline=True,
            zerolinewidth=2,
            zerolinecolor='black',
            showgrid=True
        )
    )
    
    return fig
