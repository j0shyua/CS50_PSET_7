from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import gettempdir

from helpers import *

# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# custom filter
app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = gettempdir()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    """ User's home page."""

    if request.method == "GET":
        # get the stock info for each row in index.html
        stock_info = db.execute("SELECT stock_name, stock_symbol, SUM(num_shares) AS shares FROM portfolio \
        WHERE user_id = :uid GROUP BY stock_name, stock_symbol ORDER BY stock_name", uid = session["user_id"])
        
        # find the user's cash left
        cash_list = db.execute("SELECT cash FROM users WHERE id = :id", id = session["user_id"])
        user_cash = cash_list[0]["cash"]
        
        # define stuff to store price data and grand total
        prices = []
        total_money = []
        grand_total = user_cash
        
        # get current price information for all stocks
        for info in stock_info:
            stockQuote = lookup(info["stock_symbol"])
            prices.append(usd(stockQuote['price']))
            total_money.append(usd(stockQuote['price'] * info['shares']))
            
            # calculate the user's grand total
            grand_total += (stockQuote['price'] * info['shares'])
        
        # render the template with the stored result sets from queries
        return render_template("index.html", total_money = total_money, user_cash = usd(user_cash),
        stock_info = stock_info, prices = prices, grand_total = usd(grand_total))
    
    if request.method == "POST":
        
        # require amount of money to be entered
        if not request.form.get("money"):
            apology("Enter amount of money to add")
            
        money_to_add = request.form.get("money")
        
        # only allow positive number of dollars
        if not (money_to_add.isdigit()):
            return apology("Enter positive integer for money")
            
        # get old amount of cash user owns
        old_cash = db.execute("SELECT cash FROM users WHERE id = :uid", uid = session["user_id"])

        if not old_cash:
            return apology("Failed to retrieve money from database")
            
        # add money gained from selling stock to user's account    
        updated = db.execute("UPDATE users SET cash = :new_cash WHERE id = :uid",
        new_cash = (old_cash[0]["cash"] + int(money_to_add)), uid = session["user_id"])
        
        if not updated:
            return apology("Something went wrong")
            
        # go back to "home" page   
        return redirect(url_for("index")) 
    
    else:
        return render_template("index.html")

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock."""
    
    # return buy.html when link is clicked/redirected
    if request.method == "GET":
        return render_template("buy.html")
        
    # once the form has been filled out    
    if request.method == "POST":
        
        # make sure stock is entered    
        if not request.form.get("stock"):
            return apology("Input stock to buy")
        
        # make sure number of shares is entered
        if not request.form.get("shares"):
            return apology("Input number of shares to buy")
            
        # only accept positive integer for number of shares    
        if not request.form.get("shares").isdigit():
            return apology("Not a valid number of shares")
        
        # stock name, price, symbol stored in this dict    
        purchase = lookup(request.form.get("stock"))
        
        # check if stock exists
        if not purchase:
            return apology("Not a valid stock")
            
        # calculate if user can afford a stock
        cash_list = db.execute("SELECT cash FROM users WHERE id = :id", id = session["user_id"])
        user_cash = int(cash_list[0]["cash"])
        total_purchase = int(request.form.get("shares")) * purchase['price']
        
        # complete the purchase/write to database if user can afford the stock
        if total_purchase <= user_cash:
            db.execute("UPDATE 'users' SET cash = :newCash WHERE id = :id", newCash = (user_cash - total_purchase), id = session["user_id"])
            
            # add all the purchase information to user's portfolio database table
            db.execute("INSERT INTO 'portfolio' (stock_name, stock_price, stock_symbol, num_shares, user_id) \
            VALUES (:name, :price, :symbol, :shares, :uid)", name = purchase['name'], price = purchase['price'],
            symbol = purchase['symbol'], shares = int(request.form.get("shares")), uid = session["user_id"])
            
            # go to user's portfolio page
            return redirect(url_for("index"))
            
        else:
            return apology("Not enough cash!")
        
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions."""
    
    # get the stock info for the purchased stocks
    stock_info = db.execute("SELECT stock_symbol, stock_price, num_shares, date_purchase \
    FROM portfolio WHERE user_id = :uid ORDER BY date_purchase", uid = session["user_id"])
    
    # get the stock info for the sold stocks
    stock_info_sold = db.execute("SELECT stock_symbol, stock_price, num_shares, date_sold \
    FROM sold WHERE user_id = :uid ORDER BY date_sold", uid = session["user_id"])

    # render the template with the stored result sets from queries
    return render_template("history.html", stock_info = stock_info, stock_info_sold = stock_info_sold)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password")

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out."""

    # forget any user_id
    session.clear()

    # redirect user to login form
    return redirect(url_for("login"))

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    
    if request.method == "GET":
        
        # redirect user to stock quote page
        return render_template("quote.html")

    if request.method == "POST":
        
        # stock name, price, symbol stored in this dict    
        stockQuote = lookup(request.form.get("stock"))
        
        # check if stock symbol is valid
        if not stockQuote:
            return apology("Not a valid stock symbol")
            
        # return info on the requested stock    
        return render_template("quoted.html", stockName = stockQuote['name'],
        stockPrice = stockQuote['price'], stockSymbol = stockQuote['symbol'])

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user."""
    
    if request.method == "POST":
    
        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")
    
        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")
            
        # ensure password was re-entered
        elif not request.form.get("password2"):
            return apology("must re-type password")
            
        # ensure passwords match
        elif not (request.form.get("password")) == (request.form.get("password2")):
            return apology("passwords do not match")
            
        # add username to database
        result = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
        username = request.form.get("username"), hash = pwd_context.encrypt(request.form.get("password")))    
        
        # ensure username is unique
        if not result:
            return apology("Username already exists!")
        
        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
        
        # log user in after registration
        session["user_id"] = rows[0]["id"]
        
        # redirect new user to home page
        return redirect(url_for("index"))
    
    # else if user clicked on link to get to registration page
    else:
        return render_template("register.html")
    
@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock."""
    
    if request.method == "GET":
        # get the stock info for each row in sell.html
        stock_info = db.execute("SELECT stock_name, stock_symbol, Sum(num_shares) AS shares FROM portfolio \
        WHERE user_id = :uid GROUP BY stock_name, stock_symbol ORDER BY stock_name", uid = session["user_id"])
        
        # find the user's cash left
        cash_list = db.execute("SELECT cash FROM users WHERE id = :id", id = session["user_id"])
        user_cash = cash_list[0]["cash"]
        
        # define stuff to store price data and grand total
        prices = []
        total_money = []
        grand_total = user_cash
        
        # get current price information for all stocks
        for info in stock_info:
            stockQuote = lookup(info["stock_symbol"])
            prices.append(usd(stockQuote['price']))
            total_money.append(usd(stockQuote['price'] * info['shares']))
            
            # calculate the user's grand total
            grand_total += (stockQuote['price'] * info['shares'])
            
        # render the template with the stored result sets from queries
        return render_template("sell.html", total_money = total_money, user_cash = usd(user_cash),
        stock_info = stock_info, prices = prices, grand_total = usd(grand_total))    
        
    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("sell_stock"):
            return apology("type in stock to sell")
    
        # calculate money to return to user
        current_info = lookup(request.form.get("sell_stock"))
        
        # check if stock exists
        if not current_info:
            return apology("Stock doesn't exist")
        
        # used to calculate returned money
        stock_value = current_info['price']
        
        # continuing calculation
        stock_shares = db.execute("SELECT num_shares FROM portfolio WHERE user_id = :uid AND stock_symbol = :sell_stock",
        uid = session["user_id"], sell_stock = (request.form.get("sell_stock").upper()))
        
        # error if stock doesn't exist
        if not stock_shares:
            return apology("Stock symbol not owned")
        
        # calculate amount of money to return to user
        money_return = stock_value * stock_shares[0]["num_shares"]
        
        # delete selected stock from table (case-sensitive)
        deleted = db.execute("DELETE FROM portfolio WHERE user_id = :uid AND stock_symbol = :sell_stock",
        uid = session["user_id"], sell_stock = (request.form.get("sell_stock").upper()))
        
        # record the sale in another table
        sold = db.execute("INSERT INTO sold (stock_name, stock_symbol, num_shares, stock_price, user_id) VALUES \
        (:stock_name, :stock_symbol, :num_shares, :stock_price, :uid)", stock_name = current_info['name'], 
        stock_symbol = current_info['symbol'], num_shares = -stock_shares[0]["num_shares"], stock_price = stock_value, uid = session["user_id"])
        
        # error if failed to add to :sold" database table
        if not sold:
            return apology("Couldn't add to \"sold\" database")
            
        # error if stock doesn't exist
        if not deleted:
            return apology("Error occured while selling")
        
        # get old amount of cash user owns
        old_cash = db.execute("SELECT cash FROM users WHERE id = :uid", uid = session["user_id"])
        if not old_cash:
            apology("Failed to return money")
            
        # add money gained from selling stock to user's account    
        returned = db.execute("UPDATE users SET cash = :new_cash WHERE id = :uid",
        new_cash = (old_cash[0]["cash"] + money_return), uid = session["user_id"])
        if not returned:
            apology("Something went wrong")
            
        return redirect(url_for("sell"))