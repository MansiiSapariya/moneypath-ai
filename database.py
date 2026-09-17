from app import app, db, User, Transaction, Goal

with app.app_context():
    print("\n" + "="*50)
    print("FIXING DATABASE SCHEMA")
    print("="*50)
    
    # Drop all existing tables
    print("\n1. Dropping all tables...")
    db.drop_all()
    print("   ✓ Tables dropped")
    
    # Create all tables with correct schema
    print("\n2. Creating tables with correct schema...")
    db.create_all()
    print("   ✓ Tables created")
    
    # Verify schema
    print("\n3. Verifying schema...")
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    
    # Check users table
    user_columns = [col['name'] for col in inspector.get_columns('users')]
    print(f"\n✓ Users table columns ({len(user_columns)}):")
    for col in user_columns:
        print(f"   - {col}")
    
    # Check transactions table
    txn_columns = [col['name'] for col in inspector.get_columns('transactions')]
    print(f"\n✓ Transactions table columns ({len(txn_columns)}):")
    for col in txn_columns:
        print(f"   - {col}")
    
    # Check goals table
    goal_columns = [col['name'] for col in inspector.get_columns('goals')]
    print(f"\n✓ Goals table columns ({len(goal_columns)}):")
    for col in goal_columns:
        print(f"   - {col}")
    
    print("\n" + "="*50)
    print("DATABASE FIXED SUCCESSFULLY!")
    print("="*50 + "\n")
