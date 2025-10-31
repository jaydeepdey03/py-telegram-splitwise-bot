import os
import re
from typing import List, Dict, Optional
from datetime import datetime
from telegram import Update, User
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pydantic import BaseModel, Field, field_validator
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
import logging

from database.database import SessionLocal, init_db
from database.models import Group, TelegramUser, Expense, Split
from fastapi_backend import app as fastapi_app
import uvicorn
import threading

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Pydantic models for LangChain structured output
class ExpenseParticipant(BaseModel):
    username: str = Field(description="Telegram username without @ symbol")
    paid: Optional[float] = Field(default=None, description="Amount paid by this user, None if not specified")
    
class ExpenseData(BaseModel):
    total_amount: float = Field(description="Total expense amount")
    participants: List[ExpenseParticipant] = Field(description="List of participants in the expense")
    description: Optional[str] = Field(default="", description="Description of the expense")
    is_equal_split: bool = Field(description="True if split equally, False if amounts are specified")
    
    @field_validator('participants')
    def validate_participants(cls, v):
        if len(v) < 2:
            raise ValueError("At least 2 participants required")
        return v
    
    @field_validator('total_amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError("Amount must be positive")
        return v

class BillSplitBot:
    def __init__(self, telegram_token: str, openai_api_key: str):
        self.telegram_token = telegram_token
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            openai_api_key=openai_api_key,
            temperature=0
        )
        self.parser = PydanticOutputParser(pydantic_object=ExpenseData)
        
        # Keywords to detect expense-related messages
        self.expense_keywords = ['split', 'paid', 'expense', 'bill', 'owes', 'owe']
        
    def is_expense_message(self, text: str) -> bool:
        """Check if message is likely about expense splitting"""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.expense_keywords)
    
    async def parse_expense(self, text: str) -> ExpenseData:
        """Parse natural language expense using LangChain and OpenAI"""
        prompt = PromptTemplate(
            template="""You are a bill splitting assistant. Parse the following expense message and extract structured information.

Rules:
1. Extract the total amount of the expense
2. Identify all participants (usernames mentioned with @)
3. If individual amounts paid are mentioned, extract them (is_equal_split=False)
4. If no individual amounts mentioned, it's an equal split (is_equal_split=True)
5. Extract any description about what the expense is for
6. Remove @ symbol from usernames

{format_instructions}

Message: {message}

Parse the expense:""",
            input_variables=["message"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()}
        )
        
        chain = prompt | self.llm | self.parser
        result = await chain.ainvoke({"message": text})
        return result
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_message = """
👋 Welcome to Bill Splitting Bot!

I help you split bills and track expenses in your group.

**How to use:**
• `split 500 between @me and @user1` - Split 500 equally
• `split 500 between @me and @user1, I paid 200, @user1 paid 300` - Split with breakdown
• Add descriptions: `split 200 for dinner between @me @user1 @user2`

**Commands:**
/help - Show this help message
/register - Register yourself (or just send any message)
/members - List all registered members in group
/balance - Check your balance with each person
/summary - Group expense summary
/myexpenses - Your recent expenses
/groupstats - Group statistics
/simplify - Get simplified payment plan (minimize transactions)
/settle - Alias for /simplify

⚠️ **Important:** Users must be registered before being mentioned in expenses. Ask them to send any message or use /register!

💡 Use /simplify to see the minimum number of payments needed to settle all debts!

Start splitting bills! 💰
"""
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        await self.start(update, context)
    
    async def balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's balance with each person"""
        db = SessionLocal()
        try:
            user_id = update.effective_user.id
            chat_id = update.effective_chat.id
            
            # Get user from DB
            user = db.query(TelegramUser).filter_by(telegram_id=user_id).first()
            if not user:
                await update.message.reply_text("You don't have any expenses yet!")
                return
            
            # Calculate balances
            balances = self._calculate_user_balances(db, user_id, chat_id)
            
            if not balances:
                await update.message.reply_text("You're all settled up! 🎉")
                return
            
            message = "💰 *Your Balances:*\n\n"
            for other_user, amount in balances.items():
                if amount > 0:
                    message += f"• @{other_user} owes you: ₹{amount:.2f}\n"
                elif amount < 0:
                    message += f"• You owe @{other_user}: ₹{abs(amount):.2f}\n"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        finally:
            db.close()
    
    def _calculate_user_balances(self, db, user_id: int, chat_id: int) -> Dict[str, float]:
        """Calculate net balances between users"""
        balances = {}
        
        # Get all splits involving this user in this group
        splits = db.query(Split).join(Expense).join(Group).filter(
            Group.telegram_chat_id == chat_id,
            Split.user_id == user_id
        ).all()
        
        for split in splits:
            expense = split.expense
            # Find what this user paid
            user_paid = next((s.paid_amount for s in expense.splits if s.user_id == user_id), 0)
            
            # Calculate with each other participant
            for other_split in expense.splits:
                if other_split.user_id != user_id:
                    other_user = db.query(TelegramUser).get(other_split.user_id)
                    username = other_user.username
                    
                    # Net amount: what I paid - what I owe
                    net = user_paid - split.owed_amount
                    
                    if username not in balances:
                        balances[username] = 0
                    balances[username] += net / (len(expense.splits) - 1)
        
        return {k: v for k, v in balances.items() if abs(v) > 0.01}
    
    def _simplify_debts(self, db, chat_id: int) -> List[Dict]:
        """Simplify all debts in a group using debt simplification algorithm"""
        # Get all users in the group
        group = db.query(Group).filter_by(telegram_chat_id=chat_id).first()
        if not group:
            return []
        
        # Calculate net balance for each user
        user_balances = {}  # {user_id: net_balance}
        
        expenses = db.query(Expense).filter_by(group_id=group.id).all()
        
        for expense in expenses:
            for split in expense.splits:
                user_id = split.user_id
                if user_id not in user_balances:
                    user_balances[user_id] = 0
                # Net: what they paid minus what they owe
                user_balances[user_id] += split.paid_amount - split.owed_amount
        
        # Separate creditors (positive balance) and debtors (negative balance)
        creditors = []  # People who should receive money
        debtors = []    # People who should pay money
        
        for user_id, balance in user_balances.items():
            if balance > 0.01:  # Creditor
                user = db.query(TelegramUser).get(user_id)
                creditors.append({"user_id": user_id, "username": user.username, "amount": balance})
            elif balance < -0.01:  # Debtor
                user = db.query(TelegramUser).get(user_id)
                debtors.append({"user_id": user_id, "username": user.username, "amount": -balance})
        
        # Sort for optimal matching
        creditors.sort(key=lambda x: x["amount"], reverse=True)
        debtors.sort(key=lambda x: x["amount"], reverse=True)
        
        # Greedy algorithm to minimize transactions
        transactions = []
        i, j = 0, 0
        
        while i < len(debtors) and j < len(creditors):
            debtor = debtors[i]
            creditor = creditors[j]
            
            # Amount to settle
            amount = min(debtor["amount"], creditor["amount"])
            
            if amount > 0.01:  # Only add if meaningful
                transactions.append({
                    "from": debtor["username"],
                    "to": creditor["username"],
                    "amount": round(amount, 2)
                })
            
            # Update remaining amounts
            debtor["amount"] -= amount
            creditor["amount"] -= amount
            
            # Move to next if settled
            if debtor["amount"] < 0.01:
                i += 1
            if creditor["amount"] < 0.01:
                j += 1
        
        return transactions
    
    async def summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show group expense summary"""
        db = SessionLocal()
        try:
            chat_id = update.effective_chat.id
            
            # Get group from DB
            group = db.query(Group).filter_by(telegram_chat_id=chat_id).first()
            if not group:
                await update.message.reply_text("No expenses recorded for this group yet!")
                return
            
            expenses = db.query(Expense).filter_by(group_id=group.id).order_by(Expense.created_at.desc()).limit(10).all()
            
            if not expenses:
                await update.message.reply_text("No expenses recorded yet!")
                return
            
            message = "📊 *Recent Expenses:*\n\n"
            total = 0
            
            for exp in expenses:
                participants = [f"@{db.query(TelegramUser).get(s.user_id).username}" for s in exp.splits]
                message += f"• ₹{exp.amount:.2f} - {exp.description or 'No description'}\n"
                message += f"  👥 {', '.join(participants)}\n"
                message += f"  📅 {exp.created_at.strftime('%d %b %Y')}\n\n"
                total += exp.amount
            
            message += f"*Total: ₹{total:.2f}*"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        finally:
            db.close()
    
    async def my_expenses(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's recent expenses"""
        db = SessionLocal()
        try:
            user_id = update.effective_user.id
            chat_id = update.effective_chat.id
            
            user = db.query(TelegramUser).filter_by(telegram_id=user_id).first()
            if not user:
                await update.message.reply_text("You don't have any expenses yet!")
                return
            
            # Get expenses where user participated
            expenses = db.query(Expense).join(Split).join(Group).filter(
                Split.user_id == user.id,
                Group.telegram_chat_id == chat_id
            ).order_by(Expense.created_at.desc()).limit(10).all()
            
            if not expenses:
                await update.message.reply_text("You don't have any expenses yet!")
                return
            
            message = "📝 *Your Recent Expenses:*\n\n"
            
            for exp in expenses:
                user_split = next(s for s in exp.splits if s.user_id == user.id)
                message += f"• ₹{exp.amount:.2f} - {exp.description or 'No description'}\n"
                message += f"  You paid: ₹{user_split.paid_amount:.2f} | You owe: ₹{user_split.owed_amount:.2f}\n"
                message += f"  📅 {exp.created_at.strftime('%d %b %Y')}\n\n"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        finally:
            db.close()
    
    async def group_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show group statistics"""
        db = SessionLocal()
        try:
            chat_id = update.effective_chat.id
            
            group = db.query(Group).filter_by(telegram_chat_id=chat_id).first()
            if not group:
                await update.message.reply_text("No expenses recorded for this group yet!")
                return
            
            expenses = db.query(Expense).filter_by(group_id=group.id).all()
            
            if not expenses:
                await update.message.reply_text("No expenses recorded yet!")
                return
            
            total_amount = sum(exp.amount for exp in expenses)
            total_expenses = len(expenses)
            avg_expense = total_amount / total_expenses
            
            message = f"""📈 *Group Statistics:*

💰 Total Amount: ₹{total_amount:.2f}
📊 Total Expenses: {total_expenses}
📉 Average Expense: ₹{avg_expense:.2f}
👥 Group Name: {group.name or 'Unnamed Group'}
"""
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        finally:
            db.close()
    
    async def simplify_payments(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show simplified payment plan for the group"""
        db = SessionLocal()
        try:
            chat_id = update.effective_chat.id
            
            # Get simplified transactions
            transactions = self._simplify_debts(db, chat_id)
            
            if not transactions:
                await update.message.reply_text("🎉 Everyone is settled up! No payments needed.")
                return
            
            message = "💸 *Simplified Payment Plan:*\n\n"
            message += "To settle all debts with minimum transactions:\n\n"
            
            for i, txn in enumerate(transactions, 1):
                message += f"{i}. @{txn['from']} pays @{txn['to']}: ₹{txn['amount']:.2f}\n"
            
            message += f"\n✨ Only {len(transactions)} transaction(s) needed!"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        finally:
            db.close()
    
    async def list_members(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all registered members in this group"""
        db = SessionLocal()
        try:
            chat_id = update.effective_chat.id
            
            # Get group
            group = db.query(Group).filter_by(telegram_chat_id=chat_id).first()
            if not group:
                await update.message.reply_text("No members registered yet! Send any message to register yourself.")
                return
            
            # Get all members from the group_members relationship
            members = group.members
            
            if not members:
                await update.message.reply_text("No members registered yet! Send any message to register yourself.")
                return
            
            message = "👥 *Registered Members in this Group:*\n\n"
            
            for user in members:
                name = user.first_name or user.username
                message += f"• @{user.username} ({name})\n"
            
            message += f"\n📊 Total: {len(members)} member(s)"
            message += "\n\n💡 *Tip:* Any user mentioned in an expense must be a member of this group. Ask them to send any message in this group to register!"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        finally:
            db.close()
    
    async def register_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Register the user in the system"""
        db = SessionLocal()
        try:
            sender = update.effective_user
            chat_id = update.effective_chat.id
            chat_title = update.effective_chat.title or "Private Chat"
            
            # Get or create user
            user = db.query(TelegramUser).filter_by(telegram_id=sender.id).first()
            
            if not user:
                user = TelegramUser(
                    telegram_id=sender.id,
                    username=sender.username or f"user_{sender.id}",
                    first_name=sender.first_name,
                    last_name=sender.last_name
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            
            # Get or create group
            group = db.query(Group).filter_by(telegram_chat_id=chat_id).first()
            if not group:
                group = Group(telegram_chat_id=chat_id, name=chat_title)
                db.add(group)
                db.commit()
                db.refresh(group)
            
            # Add user to group if not already a member
            if user not in group.members:
                group.members.append(user)
                db.commit()
                await update.message.reply_text(
                    f"✅ Welcome @{user.username}! You're now registered in {group.name} and can be mentioned in expenses."
                )
            else:
                await update.message.reply_text(
                    f"✅ You're already registered as @{user.username} in {group.name}!"
                )
            
        finally:
            db.close()
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages and parse expenses"""
        message_text = update.message.text
        
        # First, register/update the user in our database AND track group membership
        db = SessionLocal()
        try:
            sender = update.effective_user
            chat_id = update.effective_chat.id
            chat_title = update.effective_chat.title or "Private Chat"
            
            # Get or create user
            user = db.query(TelegramUser).filter_by(telegram_id=sender.id).first()
            
            if not user:
                # New user - register them
                user = TelegramUser(
                    telegram_id=sender.id,
                    username=sender.username or f"user_{sender.id}",
                    first_name=sender.first_name,
                    last_name=sender.last_name
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            else:
                # Update user info if changed
                updated = False
                if sender.username and user.username != sender.username:
                    user.username = sender.username
                    updated = True
                if sender.first_name and user.first_name != sender.first_name:
                    user.first_name = sender.first_name
                    updated = True
                if sender.last_name and user.last_name != sender.last_name:
                    user.last_name = sender.last_name
                    updated = True
                if updated:
                    db.commit()
            
            # Get or create group
            group = db.query(Group).filter_by(telegram_chat_id=chat_id).first()
            if not group:
                group = Group(telegram_chat_id=chat_id, name=chat_title)
                db.add(group)
                db.commit()
                db.refresh(group)
            
            # Add user to group if not already a member
            if user not in group.members:
                group.members.append(user)
                db.commit()
                logger.info(f"Added user @{user.username} to group {group.name} ({chat_id})")
                
        finally:
            db.close()
        
        # Ignore if not expense-related to save AI costs
        if not self.is_expense_message(message_text):
            return
        
        db = SessionLocal()
        try:
            # Parse expense using AI
            expense_data = await self.parse_expense(message_text)
            
            # Validate and create expense
            await self._create_expense(db, update, expense_data)
            
        except ValueError as e:
            await update.message.reply_text(str(e))
        except Exception as e:
            logger.error(f"Error parsing expense: {e}")
            await update.message.reply_text("❌ Sorry, I couldn't understand that expense. Please try again or use /help for examples.")
        finally:
            db.close()
    
    async def _create_expense(self, db, update: Update, expense_data: ExpenseData):
        """Create expense in database after validation"""
        chat_id = update.effective_chat.id
        chat_title = update.effective_chat.title or "Private Chat"
        
        # Get or create group
        group = db.query(Group).filter_by(telegram_chat_id=chat_id).first()
        if not group:
            group = Group(telegram_chat_id=chat_id, name=chat_title)
            db.add(group)
            db.commit()
        
        # Validate participants are in THIS group
        telegram_users = []
        not_found_users = []
        
        for participant in expense_data.participants:
            username = participant.username.lstrip('@')
            
            # Special case: "me" refers to the message sender
            if username.lower() == 'me':
                sender = update.effective_user
                user = db.query(TelegramUser).filter_by(telegram_id=sender.id).first()
                if not user:
                    user = TelegramUser(
                        telegram_id=sender.id,
                        username=sender.username or f"user_{sender.id}",
                        first_name=sender.first_name,
                        last_name=sender.last_name
                    )
                    db.add(user)
                    db.commit()
                    db.refresh(user)
                    # Add to group if not already a member
                    if user not in group.members:
                        group.members.append(user)
                        db.commit()
                telegram_users.append(user)
                continue
            
            # Try to find user in database first
            user = db.query(TelegramUser).filter_by(username=username).first()
            
            if user:
                # CRITICAL: Check if user is a member of THIS group in our database
                if user not in group.members:
                    logger.warning(f"User @{username} (ID: {user.telegram_id}) is in DB but not a member of group {group.name} ({chat_id})")
                    not_found_users.append(username)
                    continue
                
                # Double-check: Verify user is still in the Telegram chat
                try:
                    member = await update.effective_chat.get_member(user.telegram_id)
                    if member.status in ['left', 'kicked', 'banned']:
                        logger.warning(f"User @{username} has left/kicked from group {group.name} ({chat_id})")
                        # Remove from our group membership
                        group.members.remove(user)
                        db.commit()
                        not_found_users.append(username)
                        continue
                    telegram_users.append(user)
                except Exception as e:
                    # User not in this Telegram chat
                    logger.warning(f"User @{username} not in Telegram chat {chat_id}: {e}")
                    not_found_users.append(username)
                    continue
            else:
                # User not in our database, try to find them in the chat
                try:
                    # Try to get chat administrators (they're usually in the group)
                    admins = await update.effective_chat.get_administrators()
                    found = False
                    
                    for admin in admins:
                        if admin.user.username and admin.user.username.lower() == username.lower():
                            # Found the user - add them to DB and group
                            user = TelegramUser(
                                telegram_id=admin.user.id,
                                username=admin.user.username,
                                first_name=admin.user.first_name,
                                last_name=admin.user.last_name
                            )
                            db.add(user)
                            db.commit()
                            db.refresh(user)
                            # Add to group
                            group.members.append(user)
                            db.commit()
                            telegram_users.append(user)
                            found = True
                            logger.info(f"Auto-registered admin @{username} to group {group.name}")
                            break
                    
                    if not found:
                        not_found_users.append(username)
                        
                except Exception as e:
                    logger.warning(f"Could not find user @{username} in chat admins: {e}")
                    not_found_users.append(username)
        
        # If any users not found, raise error
        if not_found_users:
            if len(not_found_users) == 1:
                raise ValueError(f"❌ User @{not_found_users[0]} is not in this group or hasn't interacted with the bot yet. Ask them to send any message in the group first!")
            else:
                users_str = ", ".join([f"@{u}" for u in not_found_users])
                raise ValueError(f"❌ Users {users_str} are not in this group or haven't interacted with the bot yet. Ask them to send any message in the group first!")
        
        # Validate amounts if unequal split
        if not expense_data.is_equal_split:
            total_paid = sum(p.paid for p in expense_data.participants if p.paid is not None)
            if abs(total_paid - expense_data.total_amount) > 0.01:
                raise ValueError(f"Individual amounts ({total_paid}) don't add up to total ({expense_data.total_amount})!")
        
        # Create expense
        expense = Expense(
            group_id=group.id,
            amount=expense_data.total_amount,
            description=expense_data.description,
            created_by=update.effective_user.id
        )
        db.add(expense)
        db.commit()
        
        # Create splits
        num_participants = len(expense_data.participants)
        equal_share = expense_data.total_amount / num_participants
        
        for i, participant in enumerate(expense_data.participants):
            user = telegram_users[i]
            
            if expense_data.is_equal_split:
                paid_amount = equal_share
            else:
                paid_amount = participant.paid or 0
            
            split = Split(
                expense_id=expense.id,
                user_id=user.id,
                paid_amount=paid_amount,
                owed_amount=equal_share
            )
            db.add(split)
        
        db.commit()
        
        # Send confirmation
        participants_str = ", ".join([f"@{p.username}" for p in expense_data.participants])
        
        # Build split details
        if expense_data.is_equal_split:
            split_details = f"💵 Each owes: ₹{equal_share:.2f}"
        else:
            split_details = "💵 Split breakdown:\n"
            for i, participant in enumerate(expense_data.participants):
                user = telegram_users[i]
                paid_amount = participant.paid or 0
                balance = paid_amount - equal_share
                
                if abs(balance) < 0.01:  # Settled
                    split_details += f"  • @{participant.username}: Paid ₹{paid_amount:.2f} (settled)\n"
                elif balance > 0:  # Overpaid
                    split_details += f"  • @{participant.username}: Paid ₹{paid_amount:.2f} (gets back ₹{balance:.2f})\n"
                else:  # Underpaid
                    split_details += f"  • @{participant.username}: Paid ₹{paid_amount:.2f} (owes ₹{abs(balance):.2f})\n"
        
        message = f"""✅ *Expense Added!*

💰 Amount: ₹{expense_data.total_amount:.2f}
👥 Split between: {participants_str}
📝 Description: {expense_data.description or 'None'}
{split_details}
"""
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    def run(self):
        """Start the bot"""
        # Initialize database
        init_db()
        
        # Create application
        application = Application.builder().token(self.telegram_token).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("register", self.register_user))
        application.add_handler(CommandHandler("members", self.list_members))
        application.add_handler(CommandHandler("balance", self.balance))
        application.add_handler(CommandHandler("summary", self.summary))
        application.add_handler(CommandHandler("myexpenses", self.my_expenses))
        application.add_handler(CommandHandler("groupstats", self.group_stats))
        application.add_handler(CommandHandler("simplify", self.simplify_payments))
        application.add_handler(CommandHandler("settle", self.simplify_payments))  # Alias
        
        # Handle all text messages
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Start FastAPI in separate thread
        def run_fastapi():
            uvicorn.run(fastapi_app, host="0.0.0.0", port=8000)
        
        fastapi_thread = threading.Thread(target=run_fastapi, daemon=True)
        fastapi_thread.start()
        
        logger.info("Bot started!")
        application.run_polling()

if __name__ == "__main__":
    # Set your tokens
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")
    
    bot = BillSplitBot(TELEGRAM_BOT_TOKEN, OPENAI_API_KEY)
    bot.run()