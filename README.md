# Telegram Bill Splitting Bot 💰

A sophisticated Telegram bot that uses AI to parse natural language and help groups split bills effortlessly. Built with FastAPI, SQLAlchemy, LangChain, and OpenAI.

## Features

✨ **AI-Powered Natural Language Processing**
- Parse expenses from natural language: "split 500 between @user1 and @user2"
- Automatically detect equal vs unequal splits
- Extract descriptions from messages

🎯 **Smart Bill Splitting**
- Equal splits: "split 500 between @me @user1 @user2"
- Unequal splits: "split 500 between @me @user1, I paid 300, @user1 paid 200"
- Validates total amounts match breakdown
- **Ensures participants are in the group and registered**
- Automatic user registration on first message

👥 **User Management**
- Users auto-register when they send any message
- `/register` - Manually register yourself
- `/members` - See all registered members in group
- **Error thrown if mentioned user is not registered**

💳 **Comprehensive Commands**
- `/start` - Get started with the bot
- `/help` - Show help and usage examples
- `/register` - Register yourself in the system
- `/members` - List all registered members in the group
- `/balance` - Check your balance with each person
- `/summary` - View group expense summary
- `/myexpenses` - See your recent expenses
- `/groupstats` - View group statistics
- `/simplify` or `/settle` - **Get simplified payment plan** (minimizes transactions!)

🧮 **Smart Debt Simplification**
- Uses greedy algorithm to minimize number of transactions
- Example: If A owes B ₹200, A owes C ₹400, and B owes C ₹200
- Instead of 3 payments, simplifies to: A pays C ₹600 (only 1 transaction!)
- Saves time and reduces payment overhead

🔒 **Robust Backend**
- FastAPI REST API with full CRUD operations
- SQLAlchemy ORM for database management
- SQLite/PostgreSQL support
- Comprehensive API documentation

## Architecture

```
┌─────────────────┐
│  Telegram Bot   │
│   (Frontend)    │
└────────┬────────┘
         │
         ├─────────────────┐
         │                 │
┌────────▼────────┐  ┌────▼─────────┐
│   LangChain +   │  │   FastAPI    │
│     OpenAI      │  │   Backend    │
│  (NL Parsing)   │  │  (REST API)  │
└────────┬────────┘  └────┬─────────┘
         │                │
         └────────┬───────┘
                  │
         ┌────────▼────────┐
         │   SQLAlchemy    │
         │      ORM        │
         └────────┬────────┘
                  │
         ┌────────▼────────┐
         │    Database     │
         │ (SQLite/Postgres)│
         └─────────────────┘
```

## Installation

### Prerequisites
- Python 3.9+
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- OpenAI API Key

### Setup Steps

1. **Clone the repository**
```bash
git clone <repository-url>
cd telegram-bill-bot
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**
```bash
cp .env.example .env
```

Edit `.env` and add your tokens:
```bash
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key
DATABASE_URL=sqlite:///./billsplit.db
```

5. **Run the bot**
```bash
python bot.py
```

The bot will:
- Initialize the database
- Start the Telegram bot
- Launch FastAPI server on http://localhost:8000
- API docs available at http://localhost:8000/docs

## Usage Examples

### Equal Split
```
split 500 between @alice and @bob
```
Each person owes ₹250

### Unequal Split
```
split 600 between @alice @bob @charlie
I paid 400, @bob paid 200
```
Each person owes ₹200 (their share)

### With Description
```
split 1000 for dinner between @alice @bob @charlie
@alice paid 500, @bob paid 300, @charlie paid 200
```

### Simplified Payments
```
/simplify
```
Bot will show: "A pays C: ₹600" instead of multiple transactions!

## Database Schema

### TelegramUser
- `id`: Primary key
- `telegram_id`: Unique Telegram user ID
- `username`: Telegram username
- `first_name`, `last_name`: User details

### Group
- `id`: Primary key
- `telegram_chat_id`: Unique Telegram chat ID
- `name`: Group name

### Expense
- `id`: Primary key
- `group_id`: Foreign key to Group
- `amount`: Total expense amount
- `description`: Optional description
- `created_by`: Telegram ID of creator

### Split
- `id`: Primary key
- `expense_id`: Foreign key to Expense
- `user_id`: Foreign key to TelegramUser
- `paid_amount`: Amount user paid
- `owed_amount`: Amount user owes
- `is_settled`: Settlement status

## API Endpoints

### Users
- `GET /users` - List all users
- `GET /users/{user_id}` - Get user details
- `GET /users/{user_id}/balances` - Get user balances

### Groups
- `GET /groups` - List all groups
- `GET /groups/{group_id}` - Get group details
- `GET /groups/{group_id}/expenses` - Get group expenses
- `GET /groups/{group_id}/summary` - Get group statistics

### Expenses
- `GET /expenses/{expense_id}` - Get expense details
- `POST /expenses` - Create new expense
- `DELETE /expenses/{expense_id}` - Delete expense

### Splits
- `PUT /splits/{split_id}/settle` - Mark split as settled

### Debt Simplification
- `GET /groups/{group_id}/simplify` - Get simplified payment plan (minimizes transactions)

Full API documentation: http://localhost:8000/docs

## Debt Simplification Algorithm

The bot uses a **greedy algorithm** to minimize the number of transactions needed to settle all debts:

### Example:
**Before simplification:**
- A owes B: ₹200
- A owes C: ₹400  
- B owes C: ₹200

This requires 3 separate transactions.

**After simplification:**
- A pays C: ₹600

Only 1 transaction needed! ✨

### How it works:
1. Calculate net balance for each user (total paid - total owed)
2. Separate users into creditors (positive balance) and debtors (negative balance)
3. Sort both lists by amount (largest first)
4. Match debtors with creditors greedily:
   - Take largest debtor and largest creditor
   - Settle as much as possible between them
   - Move to next when one is settled
5. Result: Minimum number of transactions

This is implemented in the `_simplify_debts()` method and available via:
- `/simplify` command in Telegram
- `GET /groups/{group_id}/simplify` API endpoint

## AI Optimization

The bot uses keyword detection to avoid unnecessary AI calls:
- Only processes messages containing: "split", "paid", "expense", "bill", "owes", "owe"
- Saves OpenAI API costs
- Reduces latency for non-expense messages

## Error Handling

The bot validates:
- ✅ All participants are in the group **and registered**
- ✅ Total amount matches individual breakdown
- ✅ Amounts are positive numbers
- ✅ At least 2 participants per expense
- ✅ Proper message format

### User Registration:

**Automatic:** Users are automatically registered when they send any message in the group.

**Manual:** Users can use `/register` command.

**Verification:** Use `/members` to see all registered users.

### Error Examples:

```
❌ User @john is not in this group or hasn't interacted with the bot yet. 
   Ask them to send any message in the group first!
```

```
❌ Users @alice, @bob are not in this group or haven't interacted with the bot yet. 
   Ask them to send any message in the group first!
```

**Solution:** Ask the mentioned user to:
1. Send ANY message in the group (even "hi")
2. Or use `/register` command
3. Then try creating the expense again

## Production Deployment

### Using PostgreSQL
Update `.env`:
```bash
DATABASE_URL=postgresql://user:password@host:5432/billsplit
```

### Using Docker
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "bot.py"]
```

Build and run:
```bash
docker build -t bill-split-bot .
docker run -d --env-file .env bill-split-bot
```

### Environment Variables for Production
```bash
TELEGRAM_BOT_TOKEN=production_token
OPENAI_API_KEY=production_key
DATABASE_URL=postgresql://user:pass@host/db
API_HOST=0.0.0.0
API_PORT=8000
```

## File Structure

```
telegram-bill-bot/
├── bot.py                 # Main bot file with handlers
├── models.py              # SQLAlchemy database models
├── database.py            # Database configuration
├── fastapi_backend.py     # FastAPI REST API
├── requirements.txt       # Python dependencies
├── .env.example          # Environment variables template
├── README.md             # This file
└── billsplit.db          # SQLite database (auto-created)
```

## Troubleshooting

### Bot not responding
- Check if bot token is correct
- Ensure bot is added to the group
- Verify bot has permission to read messages

### AI parsing errors
- Check OpenAI API key is valid
- Ensure sufficient API credits
- Review message format matches examples

### Database errors
- Check DATABASE_URL is correct
- Ensure write permissions for SQLite
- Verify PostgreSQL connection if using Postgres

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - feel free to use and modify!

## Support

For issues and questions:
- Open an issue on GitHub
- Check API docs at `/docs`
- Review usage examples above

## Future Enhancements

- [ ] Multi-currency support
- [ ] Receipt image OCR parsing
- [ ] Export to CSV/PDF
- [ ] Recurring expenses
- [ ] Payment integrations
- [ ] Web dashboard
- [ ] Analytics and insights

---

Built with ❤️ using Python, Telegram Bot API, LangChain, OpenAI, FastAPI, and SQLAlchemy
