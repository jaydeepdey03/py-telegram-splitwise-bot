from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from database.database import get_db
from database.models import TelegramUser, Group, Expense, Split

app = FastAPI(title="Bill Split Bot API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic schemas for API
class UserSchema(BaseModel):
    id: int
    telegram_id: int
    username: str
    first_name: Optional[str]
    last_name: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True

class GroupSchema(BaseModel):
    id: int
    telegram_chat_id: int
    name: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class SplitSchema(BaseModel):
    id: int
    user_id: int
    paid_amount: float
    owed_amount: float
    is_settled: bool
    
    class Config:
        from_attributes = True

class ExpenseSchema(BaseModel):
    id: int
    group_id: int
    amount: float
    description: Optional[str]
    created_by: int
    created_at: datetime
    splits: List[SplitSchema]
    
    class Config:
        from_attributes = True

class ExpenseCreateSchema(BaseModel):
    group_id: int
    amount: float
    description: Optional[str]
    created_by: int
    participants: List[dict]  # [{"user_id": 1, "paid": 100, "owed": 50}]

class BalanceSchema(BaseModel):
    user_id: int
    username: str
    net_balance: float  # positive means they owe you, negative means you owe them

# API Endpoints

@app.get("/")
async def root():
    return {"message": "Bill Split Bot API", "version": "1.0.0"}

@app.get("/users", response_model=List[UserSchema])
async def get_users(db: Session = Depends(get_db)):
    """Get all users"""
    users = db.query(TelegramUser).all()
    return users

@app.get("/users/{user_id}", response_model=UserSchema)
async def get_user(user_id: int, db: Session = Depends(get_db)):
    """Get user by ID"""
    user = db.query(TelegramUser).filter(TelegramUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.get("/groups", response_model=List[GroupSchema])
async def get_groups(db: Session = Depends(get_db)):
    """Get all groups"""
    groups = db.query(Group).all()
    return groups

@app.get("/groups/{group_id}", response_model=GroupSchema)
async def get_group(group_id: int, db: Session = Depends(get_db)):
    """Get group by ID"""
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group

@app.get("/groups/{group_id}/expenses", response_model=List[ExpenseSchema])
async def get_group_expenses(
    group_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get expenses for a group"""
    expenses = db.query(Expense).filter(
        Expense.group_id == group_id
    ).order_by(Expense.created_at.desc()).offset(skip).limit(limit).all()
    return expenses

@app.get("/expenses/{expense_id}", response_model=ExpenseSchema)
async def get_expense(expense_id: int, db: Session = Depends(get_db)):
    """Get expense by ID"""
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense

@app.post("/expenses", response_model=ExpenseSchema)
async def create_expense(expense: ExpenseCreateSchema, db: Session = Depends(get_db)):
    """Create a new expense"""
    # Validate group exists
    group = db.query(Group).filter(Group.id == expense.group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Create expense
    db_expense = Expense(
        group_id=expense.group_id,
        amount=expense.amount,
        description=expense.description,
        created_by=expense.created_by
    )
    db.add(db_expense)
    db.commit()
    db.refresh(db_expense)
    
    # Create splits
    for participant in expense.participants:
        split = Split(
            expense_id=db_expense.id,
            user_id=participant["user_id"],
            paid_amount=participant["paid"],
            owed_amount=participant["owed"]
        )
        db.add(split)
    
    db.commit()
    db.refresh(db_expense)
    
    return db_expense

@app.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    """Delete an expense"""
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    db.delete(expense)
    db.commit()
    
    return {"message": "Expense deleted successfully"}

@app.get("/users/{user_id}/balances", response_model=List[BalanceSchema])
async def get_user_balances(
    user_id: int,
    group_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get user's balances with other users"""
    user = db.query(TelegramUser).filter(TelegramUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Calculate balances
    balances = {}
    
    # Get all splits for this user
    query = db.query(Split).join(Expense).join(Group)
    
    if group_id:
        query = query.filter(Group.id == group_id)
    
    splits = query.filter(Split.user_id == user_id).all()
    
    for split in splits:
        expense = split.expense
        user_paid = split.paid_amount
        user_owed = split.owed_amount
        
        # Calculate balance with each other participant
        for other_split in expense.splits:
            if other_split.user_id != user_id:
                other_user = db.query(TelegramUser).get(other_split.user_id)
                other_paid = other_split.paid_amount
                other_owed = other_split.owed_amount
                
                # If I paid more than I owe, others owe me
                # If I paid less than I owe, I owe others
                my_net = user_paid - user_owed
                
                if other_user.id not in balances:
                    balances[other_user.id] = {
                        "user_id": other_user.id,
                        "username": other_user.username,
                        "net_balance": 0
                    }
                
                # Simplify: if I overpaid and they underpaid, they owe me
                balances[other_user.id]["net_balance"] += my_net / (len(expense.splits) - 1)
    
    return list(balances.values())

@app.get("/groups/{group_id}/summary")
async def get_group_summary(group_id: int, db: Session = Depends(get_db)):
    """Get summary statistics for a group"""
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    expenses = db.query(Expense).filter(Expense.group_id == group_id).all()
    
    if not expenses:
        return {
            "group_id": group_id,
            "total_expenses": 0,
            "total_amount": 0,
            "average_expense": 0,
            "participant_count": 0
        }
    
    total_amount = sum(exp.amount for exp in expenses)
    total_expenses = len(expenses)
    
    # Get unique participants
    participants = set()
    for exp in expenses:
        for split in exp.splits:
            participants.add(split.user_id)
    
    return {
        "group_id": group_id,
        "group_name": group.name,
        "total_expenses": total_expenses,
        "total_amount": total_amount,
        "average_expense": total_amount / total_expenses,
        "participant_count": len(participants)
    }

@app.put("/splits/{split_id}/settle")
async def settle_split(split_id: int, db: Session = Depends(get_db)):
    """Mark a split as settled"""
    split = db.query(Split).filter(Split.id == split_id).first()
    if not split:
        raise HTTPException(status_code=404, detail="Split not found")
    
    split.is_settled = True
    db.commit()
    
    return {"message": "Split marked as settled"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

@app.get("/groups/{group_id}/simplify")
async def simplify_group_debts(group_id: int, db: Session = Depends(get_db)):
    """Get simplified debt settlement plan for a group"""
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Calculate net balance for each user
    user_balances = {}
    
    expenses = db.query(Expense).filter_by(group_id=group_id).all()
    
    for expense in expenses:
        for split in expense.splits:
            user_id = split.user_id
            if user_id not in user_balances:
                user_balances[user_id] = 0
            user_balances[user_id] += split.paid_amount - split.owed_amount
    
    # Separate creditors and debtors
    creditors = []
    debtors = []
    
    for user_id, balance in user_balances.items():
        user = db.query(TelegramUser).get(user_id)
        if balance > 0.01:
            creditors.append({"user_id": user_id, "username": user.username, "amount": balance})
        elif balance < -0.01:
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
        
        amount = min(debtor["amount"], creditor["amount"])
        
        if amount > 0.01:
            transactions.append({
                "from_user_id": debtor["user_id"],
                "from_username": debtor["username"],
                "to_user_id": creditor["user_id"],
                "to_username": creditor["username"],
                "amount": round(amount, 2)
            })
        
        debtor["amount"] -= amount
        creditor["amount"] -= amount
        
        if debtor["amount"] < 0.01:
            i += 1
        if creditor["amount"] < 0.01:
            j += 1
    
    return {
        "group_id": group_id,
        "group_name": group.name,
        "transactions": transactions,
        "transaction_count": len(transactions),
        "message": f"Settle all debts with only {len(transactions)} transaction(s)"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, port=8000)