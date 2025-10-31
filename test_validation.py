"""
Test script to show the validation logic
"""

def validate_unequal_split(expense_data):
    """Simulate the validation logic"""
    
    # Check that all participants have paid amounts specified
    missing_amounts = []
    for participant in expense_data['participants']:
        if participant['paid'] is None:
            missing_amounts.append(participant['username'])
    
    if missing_amounts:
        users_str = ", ".join([f"@{u}" for u in missing_amounts])
        print(f"❌ ERROR: For unequal split, all participants must specify how much they paid.")
        print(f"   Missing amounts for: {users_str}\n")
        return False
    
    # Calculate total paid
    total_paid = sum(p['paid'] for p in expense_data['participants'])
    
    # Validate that total paid equals total amount
    if abs(total_paid - expense_data['total_amount']) > 0.01:
        # Build detailed breakdown for error message
        breakdown = "\n".join([f"  • @{p['username']}: ₹{p['paid']:.2f}" for p in expense_data['participants']])
        print(
            f"❌ ERROR: The amounts don't add up!\n"
            f"   Total expense: ₹{expense_data['total_amount']:.2f}\n"
            f"   Total paid: ₹{total_paid:.2f}\n"
            f"   Difference: ₹{abs(total_paid - expense_data['total_amount']):.2f}\n\n"
            f"   Breakdown:\n{breakdown}\n"
        )
        return False
    
    print(f"✅ SUCCESS: Validation passed!")
    print(f"   Total: ₹{expense_data['total_amount']:.2f}")
    print(f"   Paid amounts add up correctly\n")
    return True


# Test cases
print("=" * 60)
print("TEST CASE 1: Valid unequal split")
print("=" * 60)
expense1 = {
    'total_amount': 500,
    'participants': [
        {'username': 'me', 'paid': 200},
        {'username': 'jkdey05', 'paid': 300}
    ],
    'is_equal_split': False
}
validate_unequal_split(expense1)

print("=" * 60)
print("TEST CASE 2: Invalid - amounts don't add up")
print("=" * 60)
expense2 = {
    'total_amount': 500,
    'participants': [
        {'username': 'me', 'paid': 200},
        {'username': 'jkdey05', 'paid': 250}  # Only 450 total
    ],
    'is_equal_split': False
}
validate_unequal_split(expense2)

print("=" * 60)
print("TEST CASE 3: Invalid - missing paid amount")
print("=" * 60)
expense3 = {
    'total_amount': 500,
    'participants': [
        {'username': 'me', 'paid': 200},
        {'username': 'jkdey05', 'paid': None}  # Missing
    ],
    'is_equal_split': False
}
validate_unequal_split(expense3)

print("=" * 60)
print("TEST CASE 4: Valid - three people")
print("=" * 60)
expense4 = {
    'total_amount': 1000,
    'participants': [
        {'username': 'me', 'paid': 400},
        {'username': 'user1', 'paid': 350},
        {'username': 'user2', 'paid': 250}
    ],
    'is_equal_split': False
}
validate_unequal_split(expense4)
