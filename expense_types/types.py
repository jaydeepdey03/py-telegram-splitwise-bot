from pydantic import BaseModel, Field, field_validator
from typing import List, Optional

from langchain_core.prompts import PromptTemplate

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