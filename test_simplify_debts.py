"""
Test script to verify the debt simplification algorithm
"""

def simplify_debts(balances):
    """
    Simplify debts using greedy algorithm to minimize transactions
    
    Args:
        balances: dict of {username: net_balance}
                 positive = creditor (should receive)
                 negative = debtor (should pay)
    
    Returns:
        List of transactions: [{"from": username, "to": username, "amount": float}]
    """
    # Separate creditors and debtors
    creditors = []  # People who should receive money
    debtors = []    # People who should pay money
    
    for username, balance in balances.items():
        if balance > 0.01:  # Creditor
            creditors.append({"username": username, "amount": balance})
        elif balance < -0.01:  # Debtor
            debtors.append({"username": username, "amount": -balance})
    
    # Sort for optimal matching (largest first)
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


def print_test_result(test_name, balances, expected_txn_count=None):
    """Print test results in a readable format"""
    print("=" * 70)
    print(f"TEST: {test_name}")
    print("=" * 70)
    
    print("\n📊 Initial Balances:")
    total_positive = 0
    total_negative = 0
    
    for username, balance in balances.items():
        if balance > 0:
            print(f"  ✅ @{username}: +₹{balance:.2f} (should receive)")
            total_positive += balance
        elif balance < 0:
            print(f"  ❌ @{username}: -₹{abs(balance):.2f} (should pay)")
            total_negative += abs(balance)
        else:
            print(f"  ⚖️  @{username}: ₹0.00 (settled)")
    
    print(f"\n  Total to receive: ₹{total_positive:.2f}")
    print(f"  Total to pay: ₹{total_negative:.2f}")
    print(f"  Balanced: {abs(total_positive - total_negative) < 0.01} ✓" if abs(total_positive - total_negative) < 0.01 else f"  ⚠️  WARNING: Not balanced!")
    
    transactions = simplify_debts(balances)
    
    print(f"\n💸 Simplified Payment Plan ({len(transactions)} transaction(s)):")
    if not transactions:
        print("  🎉 Everyone is settled up! No payments needed.")
    else:
        for i, txn in enumerate(transactions, 1):
            print(f"  {i}. @{txn['from']} pays @{txn['to']}: ₹{txn['amount']:.2f}")
    
    # Verify the solution
    print("\n🔍 Verification:")
    final_balances = {username: balance for username, balance in balances.items()}
    
    for txn in transactions:
        final_balances[txn['from']] += txn['amount']
        final_balances[txn['to']] -= txn['amount']
    
    all_settled = all(abs(balance) < 0.01 for balance in final_balances.values())
    
    if all_settled:
        print("  ✅ All debts settled correctly!")
    else:
        print("  ❌ ERROR: Some debts remain!")
        for username, balance in final_balances.items():
            if abs(balance) > 0.01:
                print(f"     @{username}: ₹{balance:.2f}")
    
    if expected_txn_count is not None:
        if len(transactions) == expected_txn_count:
            print(f"  ✅ Transaction count matches expected: {expected_txn_count}")
        else:
            print(f"  ⚠️  Expected {expected_txn_count} transactions, got {len(transactions)}")
    
    print()


# Test Case 1: Simple two-person debt
print_test_result(
    "Simple Two-Person Debt",
    balances={
        "alice": 100,    # Alice should receive ₹100
        "bob": -100      # Bob should pay ₹100
    },
    expected_txn_count=1
)

# Test Case 2: Three people in a chain
print_test_result(
    "Three-Person Chain",
    balances={
        "alice": 150,    # Alice should receive ₹150
        "bob": -50,      # Bob should pay ₹50
        "charlie": -100  # Charlie should pay ₹100
    },
    expected_txn_count=2
)

# Test Case 3: Complex scenario - multiple creditors and debtors
print_test_result(
    "Complex Multi-Person Scenario",
    balances={
        "alice": 200,    # Alice paid ₹200 extra
        "bob": 100,      # Bob paid ₹100 extra
        "charlie": -150, # Charlie owes ₹150
        "david": -150    # David owes ₹150
    },
    expected_txn_count=3  # Optimal: 3 transactions instead of 4
)

# Test Case 4: Everyone is settled
print_test_result(
    "Everyone Settled",
    balances={
        "alice": 0,
        "bob": 0,
        "charlie": 0
    },
    expected_txn_count=0
)

# Test Case 5: One person paid everything
print_test_result(
    "One Person Paid Everything",
    balances={
        "alice": 300,    # Alice paid for everyone
        "bob": -100,     # Bob owes his share
        "charlie": -100, # Charlie owes his share
        "david": -100    # David owes his share
    },
    expected_txn_count=3
)

# Test Case 6: Real-world scenario
print_test_result(
    "Real-World Dinner Scenario",
    balances={
        "alice": 450,    # Alice paid ₹900 (bill + tip), owes ₹450
        "bob": -150,     # Bob paid ₹300, owes ₹450
        "charlie": 0,    # Charlie paid ₹450, owes ₹450 (settled)
        "david": -300    # David paid ₹150, owes ₹450
    },
    expected_txn_count=2
)

# Test Case 7: Circular debt scenario
print_test_result(
    "Circular Debt Pattern",
    balances={
        "alice": 50,
        "bob": 100,
        "charlie": -75,
        "david": -75
    },
    expected_txn_count=3
)

# Test Case 8: Large group with various amounts
print_test_result(
    "Large Group (6 people)",
    balances={
        "alice": 250,
        "bob": 150,
        "charlie": -100,
        "david": -150,
        "eve": -50,
        "frank": -100
    },
    expected_txn_count=5  # Optimized from potential 10+ transactions
)

# Test Case 9: Floating point precision test
print_test_result(
    "Floating Point Precision",
    balances={
        "alice": 33.33,
        "bob": 33.34,
        "charlie": -66.67
    },
    expected_txn_count=2
)

# Test Case 10: Everyone owes one person
print_test_result(
    "Everyone Owes One Person",
    balances={
        "alice": 1000,   # Alice paid for entire group
        "bob": -200,
        "charlie": -200,
        "david": -200,
        "eve": -200,
        "frank": -200
    },
    expected_txn_count=5
)

print("=" * 70)
print("✨ All tests completed!")
print("=" * 70)
