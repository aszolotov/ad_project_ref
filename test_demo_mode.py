# Demo Mode Test Script
# Тестирование всего функционала без домена

import os
import sys

# Set DEMO_MODE before importing
os.environ["DEMO_MODE"] = "true"
os.environ["SECRET_KEY"] = "demo-secret-key-for-testing-only-change-in-production"

print("=" * 60)
print("DEMO MODE TEST - VibeCode AD Control System")
print("=" * 60)
print()

# Test 1: Config loading
print("[1/10] Testing configuration...")
try:
    from backend.core.config import settings
    print(f"✅ Config loaded successfully")
    print(f"   - DEMO_MODE: {settings.DEMO_MODE}")
    print(f"   - AD_SERVER: {settings.AD_SERVER}")
    print(f"   - DATABASE_URL: {settings.DATABASE_URL}")
except Exception as e:
    print(f"❌ Config failed: {e}")
    sys.exit(1)

# Test 2: Database
print("\n[2/10] Testing database...")
try:
    from backend.db.database import engine, Base
    Base.metadata.create_all(bind=engine)
    print("✅ Database initialized successfully")
except Exception as e:
    print(f"❌ Database failed: {e}")

# Test 3: Demo AD Service
print("\n[3/10] Testing Demo AD Service...")
try:
    from backend.services.demo_ad_service import demo_ad_service
    
    result = demo_ad_service.test_connection()
    print(f"✅ Demo AD Service initialized")
    print(f"   - Mode: {result['mode']}")
    print(f"   - Users: {result['users_count']}")
    print(f"   - Groups: {result['groups_count']}")
    print(f"   - Computers: {result['computers_count']}")
except Exception as e:
    print(f"❌ Demo AD Service failed: {e}")

# Test 4: Search users
print("\n[4/10] Testing user search...")
try:
    from backend.services.demo_ad_service import demo_ad_service
    
    result = demo_ad_service.search_users(page=1, per_page=10)
    print(f"✅ User search works")
    print(f"   - Total users: {result['total']}")
    print(f"   - Sample user: {result['users'][0]['cn'] if result['users'] else 'None'}")
except Exception as e:
    print(f"❌ User search failed: {e}")

# Test 5: Get specific user
print("\n[5/10] Testing get user...")
try:
    user = demo_ad_service.get_user("jdoe")
    if user:
        print(f"✅ Get user works")
        print(f"   - User: {user['cn']}")
        print(f"   - Department: {user['department']}")
        print(f"   - Groups: {len(user['memberOf'])}")
    else:
        print("❌ User not found")
except Exception as e:
    print(f"❌ Get user failed: {e}")

# Test 6: Create user (demo)
print("\n[6/10] Testing create user...")
try:
    new_user = demo_ad_service.create_user({
        "cn": "Demo User",
        "sAMAccountName": "demouser",
        "givenName": "Demo",
        "sn": "User",
        "mail": "demo@test.local",
        "enabled": True
    })
    print(f"✅ Create user works")
    print(f"   - Created: {new_user['cn']}")
except Exception as e:
    print(f"❌ Create user failed: {e}")

# Test 7: Update user
print("\n[7/10] Testing update user...")
try:
    updated = demo_ad_service.update_user("demouser", {
        "department": "Testing",
        "title": "Test Engineer"
    })
    print(f"✅ Update user works")
    print(f"   - Updated: {updated['cn']}")
    print(f"   - New dept: {updated['department']}")
except Exception as e:
    print(f"❌ Update user failed: {e}")

# Test 8: Search groups
print("\n[8/10] Testing group search...")
try:
    groups = demo_ad_service.search_groups()
    print(f"✅ Group search works")
    print(f"   - Total groups: {len(groups)}")
    print(f"   - Sample: {groups[0]['cn'] if groups else 'None'}")
except Exception as e:
    print(f"❌ Group search failed: {e}")

# Test 9: Search computers
print("\n[9/10] Testing computer search...")
try:
    computers = demo_ad_service.search_computers()
    print(f"✅ Computer search works")
    print(f"   - Total computers: {len(computers)}")
    print(f"   - Sample: {computers[0]['cn'] if computers else 'None'}")
except Exception as e:
    print(f"❌ Computer search failed: {e}")

# Test 10: Plugin Manager
print("\n[10/10] Testing Plugin Manager...")
try:
    from backend.services.plugin_manager import plugin_manager
    from backend.db.database import SessionLocal
    
    db = SessionLocal()
    plugin_manager.load_plugins(db_session=db)
    print(f"✅ Plugin Manager works")
    print(f"   - Loaded plugins: {len(plugin_manager.plugins)}")
    for p in plugin_manager.plugins:
        print(f"   - {p.get('name', 'Unknown')}")
except Exception as e:
    print(f"❌ Plugin Manager failed: {e}")

print("\n" + "=" * 60)
print("DEMO MODE TEST COMPLETED!")
print("=" * 60)
print("\nTo start the server in DEMO MODE:")
print("  set DEMO_MODE=true")
print("  set SECRET_KEY=your-secret-key")
print("  uvicorn backend.main:app --reload")
print()
