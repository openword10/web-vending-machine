

### Project Introduction
VENDIX is a Discord-based private shop platform for digital goods.  
It combines a web admin panel, shop pages for users, license-based activation, charge request handling, auto-approval logic, and instant product delivery in one service.

This project is designed for small Discord server operators who want to open and manage a simple shop without building a full commerce system from scratch.

### Problem Solving
This project solves the following problems:

- Manual balance charging is slow and repetitive.
- Product delivery for digital goods often depends on manual operator response.
- Small Discord communities usually do not have a lightweight shop system built for their workflow.
- Operators need one place to manage products, users, charge requests, purchase logs, and licenses.
- Auto-charge approval can reduce repetitive operator work when transfer proof matches predefined rules.

### Architecture
The system is split into two main parts:

1. Discord Bot
- Handles license creation and registration.
- Connects a Discord server to its own shop database.

2. Web Platform
- Admin panel for operators.
- Public shop pages for end users.
- Purchase, charge, approval, and delivery flows.

Data flow overview:

1. A license is created and registered through the Discord bot.
2. A server-specific SQLite database is prepared.
3. The admin logs in through the web panel.
4. The admin configures shop information, products, and bank details.
5. End users sign up and log in to the shop page.
6. Users submit charge requests or spend existing balance.
7. The system approves charges manually or automatically.
8. Purchased digital stock is delivered immediately and stored in purchase history.

### Technology
- Backend: Python, Flask
- Database: SQLite
- Bot: Nextcord
- Frontend: HTML, Bootstrap, jQuery, custom CSS
- File handling: Werkzeug upload utilities
- Password security: Werkzeug password hashing
- OCR-based auto approval: Python OCR flow integrated into the web service
- Logging: audit log, charge log, purchase log

### Demo
Main demo points:

- Admin panel login
- Shop basic settings
- Product creation and stock input
- User signup and login
- Charge request submission
- Auto/manual charge approval
- Product purchase and instant delivery
- Purchase history and charge history

Recommended demo flow:

1. Register a server license through the Discord bot
2. Log in to `/login`
3. Add a product in the admin panel
4. Open the public shop page `/<server_id>`
5. Sign up as a shop user
6. Submit a charge request
7. Approve the request
8. Purchase a product and confirm delivery

### Installation
Windows PowerShell example:

```powershell
cd "C:\Users\사용자\OneDrive\바탕 화면\web-vending-machine_real_play"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Create `config.py` in the project root:

```python
token = "YOUR_DISCORD_BOT_TOKEN"
GUILD_ID = 123456789012345678
```

Run the web panel:

```powershell
$env:VENEX_SECRET_KEY="your-secret-key"
$env:VENEX_HOST="0.0.0.0"
$env:VENEX_PORT="5000"
python web.py
```

Run the Discord bot in another terminal:

```powershell
.\.venv\Scripts\activate
python app.py
```


