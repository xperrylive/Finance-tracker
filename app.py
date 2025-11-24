import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

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



@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    stocks = db.execute("SELECT * FROM holdings WHERE user_id = ?;", session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    shares = []
    total_wallet_value = float(cash[0]["cash"])
    total_profit_and_loss = 0.0
    for row in stocks:
        # calculate current holding value
        quote = lookup(row["symbol"])
        if not quote:
            continue           
        total_wallet_value += (row["shares"] * quote["price"])
        unrealized_PnL= (quote["price"] - row["average_cost_basis"]) * row["shares"]
        total_profit_and_loss += unrealized_PnL
        shares.append(
            {"symbol": row["symbol"],
                "shares": row["shares"],
                "price": usd(quote["price"]),
                "total": usd(row["shares"] * quote["price"]),
                "PnL": usd(unrealized_PnL)
            }
        )
    # profit_and_loss = 
    return render_template("home.html", shares=shares, cash=usd(cash[0]["cash"]), total_wallet_value=usd(total_wallet_value),total_profit_and_loss=usd(total_profit_and_loss) )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol", "").upper().strip()
        try:
            shares = int(request.form.get("shares_amount"))
            if shares <= 0:
                flash("Number of shares must be positive.")
                return render_template("buy.html")
        except (ValueError, TypeError):
            flash("Invalid number of shares.")
            return render_template("buy.html")
        
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
                average_cost_basis = ?;
            """, shares,avg_cost_basis)

        flash(f"Bought {shares} shares of {stock['symbol']} successfully!")
        return redirect("/")
    
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session["user_id"]
    data = db.execute("SELECT * FROM transactions WHERE user_id = ?", user_id)
    return render_template("history.html",transactions=data)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

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
    return apology("TODO")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        if not request.form.get("username") or not request.form.get("password"):
            return apology("Please provide username AND password")
        
        if request.form.get("password") != request.form.get("confirm_password"):
            return apology("Passwords do not match")

        exists = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username").lower())

        if exists:
            return apology("Username already exists")
        
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
    if request.method == "post":
        symbol = request.form.get("symbol")
        if symbol not in data:
            flash("Invalid stock symbol.")
            return render_template("sell.html",holdings=data)
        try:
            shares = int(request.form.get("shares_amount"))
            if shares <= 0:
                flash("Number of shares must be positive.")
                return render_template("sell.html",holdings=data)
        except (ValueError, TypeError):
            flash("Invalid number of shares.")
            return render_template("sell.html",holdings=data)
        for row in data:
            if row[symbol]:
                if shares > row["shares"]:
                    flash("Insufficient shares to sell.")
                    return render_template("sell.html",holdings=data)
        # Log transaction  
        # db.execute("INSERT INTO transactions (user_id, symbol, shares, price, event) VALUES (?,?,?,?, 'buy')", user_id, symbol, shares, stock["price"])
    else:
        return render_template("sell.html",holdings=data)

        
    return apology("TODO")

if __name__ == "__main__":
    app.run(debug=True)