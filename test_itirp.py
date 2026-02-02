"""
ITIRP Test Suite
================

Comprehensive test suite demonstrating:
- Authentication flows
- Order processing pipeline
- Risk controls validation
- Event sourcing verification
- Resilience patterns
- RBAC enforcement

Run with: python test_itirp.py
"""

import asyncio
import json
import sys
from datetime import datetime
from typing import Dict, Optional

import requests

# Configuration
BASE_URL = "http://localhost:8000"
API_V1 = f"{BASE_URL}/api/v1"


class Colors:
    """ANSI colors for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


class TestRunner:
    """Test runner with statistics tracking"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.total = 0
        self.tokens: Dict[str, str] = {}

    def test(self, name: str, func):
        """Run a single test"""
        self.total += 1
        print(f"\n{Colors.BLUE}[TEST {self.total}]{Colors.END} {name}")
        try:
            result = func()
            if result:
                self.passed += 1
                print(f"{Colors.GREEN}✓ PASS{Colors.END}")
                return True
            else:
                self.failed += 1
                print(f"{Colors.RED}✗ FAIL{Colors.END}")
                return False
        except Exception as e:
            self.failed += 1
            print(f"{Colors.RED}✗ FAIL: {str(e)}{Colors.END}")
            return False

    def print_summary(self):
        """Print test results summary"""
        print(f"\n{'=' * 70}")
        print(f"{Colors.BOLD}TEST SUMMARY{Colors.END}")
        print(f"{'=' * 70}")
        print(f"Total Tests: {self.total}")
        print(f"{Colors.GREEN}Passed: {self.passed}{Colors.END}")
        print(f"{Colors.RED}Failed: {self.failed}{Colors.END}")

        if self.failed == 0:
            print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 ALL TESTS PASSED!{Colors.END}")
        else:
            print(f"\n{Colors.YELLOW}⚠ Some tests failed{Colors.END}")

        success_rate = (self.passed / self.total * 100) if self.total > 0 else 0
        print(f"Success Rate: {success_rate:.1f}%")
        print(f"{'=' * 70}\n")


# Test runner instance
runner = TestRunner()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def check_system_health() -> bool:
    """Verify system is running"""
    try:
        resp = requests.get(f"{API_V1}/health", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print(f"  System Status: {data['status']}")
            return data['status'] == 'healthy'
        return False
    except requests.exceptions.ConnectionError:
        print(f"  {Colors.RED}ERROR: Cannot connect to {BASE_URL}{Colors.END}")
        print(f"  Please start the system first: python itirp_complete.py")
        return False


def login(username: str, password: str) -> Optional[str]:
    """Login and return JWT token"""
    resp = requests.post(
        f"{API_V1}/auth/login",
        json={"username": username, "password": password}
    )

    if resp.status_code == 200:
        token = resp.json()["access_token"]
        print(f"  Logged in as {username}")
        return token
    else:
        print(f"  Login failed: {resp.status_code}")
        return None


def make_request(method: str, endpoint: str, token: Optional[str] = None,
                 json_data: Optional[dict] = None, params: Optional[dict] = None):
    """Make authenticated API request"""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{API_V1}{endpoint}"

    if method == "GET":
        return requests.get(url, headers=headers, params=params)
    elif method == "POST":
        return requests.post(url, headers=headers, json=json_data, params=params)
    elif method == "PUT":
        return requests.put(url, headers=headers, json=json_data)
    else:
        raise ValueError(f"Unsupported method: {method}")


# =============================================================================
# AUTHENTICATION TESTS
# =============================================================================

def test_health_check():
    """Test system health endpoint"""
    return check_system_health()


def test_login_trader():
    """Test trader login"""
    token = login("trader1", "trader123")
    if token:
        runner.tokens["trader"] = token
        return True
    return False


def test_login_risk_manager():
    """Test risk manager login"""
    token = login("risk1", "risk123")
    if token:
        runner.tokens["risk"] = token
        return True
    return False


def test_login_admin():
    """Test admin login"""
    token = login("admin", "admin123")
    if token:
        runner.tokens["admin"] = token
        return True
    return False


def test_invalid_credentials():
    """Test login with invalid credentials"""
    resp = requests.post(
        f"{API_V1}/auth/login",
        json={"username": "invalid", "password": "wrong"}
    )
    return resp.status_code == 401


# =============================================================================
# ORDER PROCESSING TESTS
# =============================================================================

def test_submit_valid_order():
    """Test submitting a valid order"""
    token = runner.tokens.get("trader")
    if not token:
        print("  Skipping: No trader token")
        return False

    resp = make_request(
        "POST",
        "/orders",
        token=token,
        json_data={
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 100,
            "price": 150.50,
            "strategy": "test"
        }
    )

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Order ID: {data['order_id']}")
        print(f"  Status: {data['status']}")
        print(f"  Correlation ID: {data['correlation_id']}")

        # Store for later tests
        runner.tokens["last_order_id"] = data["order_id"]
        runner.tokens["last_correlation_id"] = data["correlation_id"]

        return data['status'] in ['APPROVED', 'PENDING']
    else:
        print(f"  Failed: {resp.status_code} - {resp.text}")
        return False


def test_get_order_details():
    """Test retrieving order details"""
    token = runner.tokens.get("trader")
    order_id = runner.tokens.get("last_order_id")

    if not token or not order_id:
        print("  Skipping: No token or order ID")
        return False

    resp = make_request("GET", f"/orders/{order_id}", token=token)

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Symbol: {data['symbol']}")
        print(f"  Status: {data['status']}")
        return True
    return False


def test_list_all_orders():
    """Test listing all orders"""
    token = runner.tokens.get("trader")
    if not token:
        return False

    resp = make_request("GET", "/orders", token=token)

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Total orders: {data['total']}")
        return data['total'] > 0
    return False


def test_order_too_large():
    """Test order rejection due to position size limit"""
    token = runner.tokens.get("trader")
    if not token:
        return False

    # Try to submit order larger than max position size
    resp = make_request(
        "POST",
        "/orders",
        token=token,
        json_data={
            "symbol": "TSLA",
            "side": "BUY",
            "quantity": 100000,  # Very large
            "price": 200,
            "strategy": "test"
        }
    )

    if resp.status_code == 200:
        data = resp.json()
        is_rejected = data['status'] == 'REJECTED'
        if is_rejected:
            print(f"  Rejection reason: {data.get('message', 'N/A')}")
        return is_rejected
    return False


def test_duplicate_order_prevention():
    """Test idempotency (duplicate prevention)"""
    token = runner.tokens.get("trader")
    if not token:
        return False

    order_data = {
        "symbol": "MSFT",
        "side": "BUY",
        "quantity": 50,
        "price": 300,
        "strategy": "test",
        "client_order_id": "unique-test-123"
    }

    # First submission
    resp1 = make_request("POST", "/orders", token=token, json_data=order_data)

    # Immediate duplicate submission
    resp2 = make_request("POST", "/orders", token=token, json_data=order_data)

    # Second submission should fail with 409 Conflict
    duplicate_prevented = resp2.status_code == 409

    if duplicate_prevented:
        print("  Duplicate detected and prevented")

    return duplicate_prevented


# =============================================================================
# RISK MANAGEMENT TESTS
# =============================================================================

def test_get_risk_metrics():
    """Test retrieving risk metrics"""
    token = runner.tokens.get("trader")
    if not token:
        return False

    resp = make_request("GET", "/risk/metrics", token=token)

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Net Exposure: ${data['net_exposure']:,.2f}")
        print(f"  Gross Exposure: ${data['gross_exposure']:,.2f}")
        print(f"  Daily Volume: ${data['daily_volume']:,.2f}")
        print(f"  Total Positions: {data['total_positions']}")
        print(f"  Kill Switch: {'ACTIVE' if data['kill_switch_active'] else 'INACTIVE'}")
        return True
    return False


def test_get_positions():
    """Test retrieving current positions"""
    token = runner.tokens.get("trader")
    if not token:
        return False

    resp = make_request("GET", "/risk/positions", token=token)

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Total positions: {data['total_positions']}")
        for pos in data['positions']:
            print(f"    {pos['symbol']}: {pos['quantity']} @ ${pos['average_price']:.2f}")
        return True
    return False


def test_update_risk_limits():
    """Test updating risk limits (requires RISK_MANAGER role)"""
    token = runner.tokens.get("risk")
    if not token:
        print("  Skipping: No risk manager token")
        return False

    new_limits = {
        "max_position_size": 500000,
        "max_daily_volume": 5000000,
        "max_net_exposure": 2000000,
        "max_gross_exposure": 10000000,
        "kill_switch_enabled": False
    }

    resp = make_request("PUT", "/risk/limits", token=token, json_data=new_limits)

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Max Position: ${data['max_position_size']:,.0f}")
        print(f"  Max Daily Volume: ${data['max_daily_volume']:,.0f}")
        return True
    return False


def test_trader_cannot_update_limits():
    """Test RBAC: trader cannot update risk limits"""
    token = runner.tokens.get("trader")
    if not token:
        return False

    resp = make_request(
        "PUT",
        "/risk/limits",
        token=token,
        json_data={"max_position_size": 1000000}
    )

    # Should fail with 403 Forbidden
    forbidden = resp.status_code == 403
    if forbidden:
        print("  Access correctly denied (403)")
    return forbidden


def test_kill_switch_activation():
    """Test kill switch activation"""
    token = runner.tokens.get("risk")
    if not token:
        return False

    # Activate kill switch
    resp = make_request(
        "POST",
        "/risk/kill-switch",
        token=token,
        params={"enabled": True}
    )

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Kill switch: {data['message']}")
        return data['kill_switch_enabled'] is True
    return False


def test_kill_switch_blocks_orders():
    """Test that kill switch blocks new orders"""
    token = runner.tokens.get("trader")
    if not token:
        return False

    # Try to submit order with kill switch active
    resp = make_request(
        "POST",
        "/orders",
        token=token,
        json_data={
            "symbol": "GOOGL",
            "side": "BUY",
            "quantity": 10,
            "price": 100,
            "strategy": "test"
        }
    )

    if resp.status_code == 200:
        data = resp.json()
        is_rejected = data['status'] == 'REJECTED'
        has_kill_switch_msg = 'kill switch' in data.get('message', '').lower()

        if is_rejected and has_kill_switch_msg:
            print("  Order correctly blocked by kill switch")
            return True

    return False


def test_kill_switch_deactivation():
    """Test kill switch deactivation"""
    token = runner.tokens.get("risk")
    if not token:
        return False

    # Deactivate kill switch
    resp = make_request(
        "POST",
        "/risk/kill-switch",
        token=token,
        params={"enabled": False}
    )

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Kill switch: {data['message']}")
        return data['kill_switch_enabled'] is False
    return False


# =============================================================================
# AUDIT & COMPLIANCE TESTS
# =============================================================================

def test_get_audit_trail_by_correlation():
    """Test retrieving audit trail by correlation ID"""
    # Login as compliance officer (using admin for demo)
    token = runner.tokens.get("admin")
    correlation_id = runner.tokens.get("last_correlation_id")

    if not token or not correlation_id:
        print("  Skipping: No token or correlation ID")
        return False

    resp = make_request("GET", f"/audit/correlation/{correlation_id}", token=token)

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Total events: {data['total_events']}")
        print(f"  Event chain:")
        for event in data['events']:
            print(f"    - {event['event_type']} @ {event['timestamp']}")
        return data['total_events'] > 0
    return False


def test_get_audit_trail_by_order():
    """Test retrieving audit trail by order ID"""
    token = runner.tokens.get("admin")
    order_id = runner.tokens.get("last_order_id")

    if not token or not order_id:
        return False

    resp = make_request("GET", f"/audit/order/{order_id}/trail", token=token)

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Total events: {data['total_events']}")
        return data['total_events'] > 0
    return False


def test_trader_cannot_access_audit():
    """Test RBAC: trader cannot access audit endpoints"""
    token = runner.tokens.get("trader")
    if not token:
        return False

    resp = make_request("GET", "/audit/events", token=token)

    # Should fail with 403 Forbidden
    forbidden = resp.status_code == 403
    if forbidden:
        print("  Access correctly denied (403)")
    return forbidden


def test_get_recent_events():
    """Test retrieving recent events"""
    token = runner.tokens.get("admin")
    if not token:
        return False

    resp = make_request("GET", "/audit/events", token=token, params={"limit": 20})

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Total events retrieved: {data['total']}")
        return data['total'] > 0
    return False


# =============================================================================
# OBSERVABILITY TESTS
# =============================================================================

def test_system_metrics():
    """Test retrieving system metrics"""
    token = runner.tokens.get("trader")
    if not token:
        return False

    resp = make_request("GET", "/metrics", token=token)

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Total orders: {data['total_orders']}")
        print(f"  Total events: {data['total_events']}")
        print(f"  Circuit breaker: {data['circuit_breaker']['status']}")

        breakdown = data.get('order_status_breakdown', {})
        print(f"  Order status breakdown:")
        for status, count in breakdown.items():
            print(f"    {status}: {count}")

        return True
    return False


# =============================================================================
# MAIN TEST EXECUTION
# =============================================================================

def main():
    """Run all tests"""
    print(f"\n{Colors.BOLD}{'=' * 70}{Colors.END}")
    print(f"{Colors.BOLD}ITIRP Test Suite{Colors.END}")
    print(f"{Colors.BOLD}Institutional Trading Infrastructure & Risk Platform{Colors.END}")
    print(f"{Colors.BOLD}{'=' * 70}{Colors.END}\n")

    # System health
    print(f"\n{Colors.BOLD}=== SYSTEM HEALTH ==={Colors.END}")
    if not runner.test("System health check", test_health_check):
        print(f"\n{Colors.RED}System is not running. Please start it first.{Colors.END}\n")
        sys.exit(1)

    # Authentication
    print(f"\n{Colors.BOLD}=== AUTHENTICATION ==={Colors.END}")
    runner.test("Login as trader", test_login_trader)
    runner.test("Login as risk manager", test_login_risk_manager)
    runner.test("Login as admin", test_login_admin)
    runner.test("Invalid credentials rejected", test_invalid_credentials)

    # Order processing
    print(f"\n{Colors.BOLD}=== ORDER PROCESSING ==={Colors.END}")
    runner.test("Submit valid order", test_submit_valid_order)
    runner.test("Get order details", test_get_order_details)
    runner.test("List all orders", test_list_all_orders)
    runner.test("Reject order too large", test_order_too_large)
    runner.test("Prevent duplicate orders (idempotency)", test_duplicate_order_prevention)

    # Risk management
    print(f"\n{Colors.BOLD}=== RISK MANAGEMENT ==={Colors.END}")
    runner.test("Get risk metrics", test_get_risk_metrics)
    runner.test("Get current positions", test_get_positions)
    runner.test("Update risk limits (RISK_MGR)", test_update_risk_limits)
    runner.test("Trader cannot update limits (RBAC)", test_trader_cannot_update_limits)

    # Kill switch
    print(f"\n{Colors.BOLD}=== KILL SWITCH ==={Colors.END}")
    runner.test("Activate kill switch", test_kill_switch_activation)
    runner.test("Kill switch blocks orders", test_kill_switch_blocks_orders)
    runner.test("Deactivate kill switch", test_kill_switch_deactivation)

    # Audit & compliance
    print(f"\n{Colors.BOLD}=== AUDIT & COMPLIANCE ==={Colors.END}")
    runner.test("Get audit trail by correlation ID", test_get_audit_trail_by_correlation)
    runner.test("Get audit trail by order ID", test_get_audit_trail_by_order)
    runner.test("Trader cannot access audit (RBAC)", test_trader_cannot_access_audit)
    runner.test("Get recent events", test_get_recent_events)

    # Observability
    print(f"\n{Colors.BOLD}=== OBSERVABILITY ==={Colors.END}")
    runner.test("Get system metrics", test_system_metrics)

    # Summary
    runner.print_summary()

    # Exit code based on results
    sys.exit(0 if runner.failed == 0 else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Tests interrupted by user{Colors.END}\n")
        sys.exit(1)