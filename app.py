from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


price_cache = {}

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    stocks = db.execute("SELECT symbol,shares,average_cost_basis FROM holdings WHERE user_id = ?;", session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    shares = []
    total_wallet_value = float(cash[0]["cash"])
    total_profit_and_loss = 0.0
    for row in stocks:
        if row["symbol"] in price_cache and (datetime.now() - price_cache[row["symbol"]]["timestamp"]) < timedelta(seconds=60):
            quote = price_cache[row["symbol"]]
        else:
            quote = lookup(row["symbol"])
            if not quote:
                continue           
            price_cache[row["symbol"]] = quote
        total_wallet_value += (row["shares"] * quote["price"])
        unrealized_PnL= (quote["price"] - row["average_cost_basis"]) * row["shares"]
        total_profit_and_loss += unrealized_PnL
        shares.append(
            {"symbol": row["symbol"],
                "shares": row["shares"],
                "price": quote["price"],
                "total": row["shares"] * quote["price"],
                "PnL": unrealized_PnL
            }
        )
    # profit_and_loss = 
    return render_template("home.html", shares=shares, cash=cash[0]["cash"], total_wallet_value=total_wallet_value,total_profit_and_loss=total_profit_and_loss)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        try:
            shares = int(request.form.get("shares_amount"))
            if shares <= 0:
                flash("Number of shares must be positive.")
                return render_template("buy.html")
        except (ValueError, TypeError):
            flash("Invalid number of shares.")
            return render_template("buy.html")
        
        symbol = request.form.get("symbol", "").upper().strip()
        
        if not symbol:
            flash("Please enter a stock symbol.")
            return render_template("buy.html")
        
        stock = lookup(symbol)
        if not stock:
            flash("Incorrect stock symbol.")
            return render_template("buy.html")
        
        user_id = session["user_id"]
        cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        total_cost = shares * stock["price"]

        if total_cost > cash[0]["cash"]:
            flash(f"Insufficient funds.")
            return render_template("buy.html")
        
        # Deduct cash                
        db.execute("UPDATE users SET cash = cash - ? WHERE id = ?",total_cost, user_id)

        # Log transaction 
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, event) VALUES (?,?,?,?, 'buy')", user_id, symbol, shares, stock["price"])
        
        # Update holdings
        data = db.execute("SELECT shares,average_cost_basis FROM holdings WHERE user_id = ? AND symbol = ?;", user_id, symbol)
        if not data:
            db.execute("""
            INSERT INTO holdings (user_id, symbol, shares, average_cost_basis) 
            VALUES (?,?,?,?);
            """, user_id, symbol, shares,stock["price"])
        else:
            avg_cost_basis = ((data[0]["average_cost_basis"] * data[0]["shares"]) + (stock["price"] * shares)) / (data[0]["shares"] + shares)
            db.execute("""
            UPDATE holdings 
            SET shares = shares + ?,
                average_cost_basis = ?
            WHERE user_id = ? AND symbol = ?;
            """, shares,avg_cost_basis, user_id, symbol)

        flash(f"Bought {shares} shares of {stock['symbol']} successfully!")
        return redirect("/")
    
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session["user_id"]
    data = db.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY timestamp DESC", user_id)
    return render_template("history.html",transactions=data)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            flash("must provide username", 403)
            return render_template("login.html")

        # Ensure password was submitted
        elif not request.form.get("password"):
            flash("must provide password", 403)
            return render_template("login.html")
        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            flash("invalid username and/or password", 403)
            return render_template("login.html")

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        if session.get("user_id"):
            flash("You are already logged in")
            return redirect("/")
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()
    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("stock")
        if not symbol:
            flash("Enter a stock symbol.")
            return render_template("quote.html")
        stock = lookup(symbol)
        if not stock:
            flash("Incorrect stock symbol.")
            return render_template("quote.html")
        return render_template("quoted.html", stock=stock)
    else:
        return render_template("quote.html")
    


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username").strip()
        password = request.form.get("password").strip()
        confirm_password = request.form.get("confirm_password").strip()
        if not username or not password:
            flash("Please provide username AND password")
            return render_template("register.html")
        
        if password != confirm_password:
            flash("Passwords do not match")
            return render_template("register.html")
        exists = db.execute("SELECT * FROM users WHERE username = ?", username.lower().strip())

        if exists:
            flash("Username already exists")
            return render_template("register.html")
        
        hash = generate_password_hash(request.form.get("password"))
        
        db.execute(
            "INSERT INTO users (username, hash) VALUES (?,?)",
            request.form.get("username").lower(), 
            hash
        )

        session["user_id"] = db.execute("SELECT id FROM users WHERE username = ?", request.form.get("username").lower())[0]["id"]
        flash("Registered Successfully!")
        return redirect("/")

    else:
        return render_template("register.html")
    


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session["user_id"]
    data = db.execute("SELECT symbol,shares FROM holdings WHERE user_id = ?", user_id)
    if request.method == "POST":
        try:
            shares = int(request.form.get("shares-to-sell"))
            if shares <= 0:
                flash("Number of shares must be positive.")
                return render_template("sell.html",holdings=data)
        except (ValueError, TypeError):
            flash("Invalid number of shares.")
            return render_template("sell.html",holdings=data)
        
        symbol = request.form.get("stock-selected")
        exist = db.execute("SELECT symbol,shares FROM holdings WHERE user_id = ? AND symbol = ?", user_id, symbol)
        if not symbol:
            flash("Please select a stock to sell.")
            return render_template("sell.html",holdings=data)
        if not exist:
            flash("You do not own any shares of this stock.")
            return render_template("sell.html",holdings=data)
        if shares > exist[0]["shares"]:
            flash("You do not have enough shares to sell.")
            return render_template("sell.html",holdings=data)
        stock = lookup(symbol) 
        if not stock:
            flash("Incorrect stock symbol.")
            return render_template("sell.html",holdings=data)
        total_earnings = stock["price"] * shares
        
        if shares == exist[0]["shares"]:
            db.execute("DELETE FROM holdings WHERE user_id = ? AND symbol = ?", user_id, symbol)
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?;", total_earnings, user_id)
        db.execute("UPDATE holdings SET shares = shares - ? WHERE symbol = ? AND user_id = ?", shares, symbol, user_id)
        # Log transaction  
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, event) VALUES (?,?,?,?, 'sell')", user_id, symbol, shares, stock["price"])
        flash(f"Sold {shares} shares of {symbol} successfully!")
        return redirect("/")
                
    else:
        return render_template("sell.html",holdings=data)

        

if __name__ == "__main__":
    app.run(debug=True)