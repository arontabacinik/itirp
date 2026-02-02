#!/usr/bin/env python3
"""
ITIRP Interactive Demo
======================

Interactive demonstration of institutional trading infrastructure capabilities.
Walks through complete order lifecycle, risk controls, and audit trails.

Run with: python demo_itirp.py
"""

import time
from datetime import datetime

import requests

BASE_URL = "http://localhost:8000/api/v1"


class Demo:
    def __init__(self):
        self.trader_token = None
        self.risk_token = None
        self.order_id = None
        self.correlation_id = None

    @staticmethod
    def print_header(title):
        print(f"\n{'=' * 80}")
        print(f"  {title}")
        print(f"{'=' * 80}\n")

    @staticmethod
    def print_step(step_num, description):
        print(f"\n[STEP {step_num}] {description}")
        print("-" * 80)

    @staticmethod
    def print_json(data, indent=2):
        import json
        print(json.dumps(data, indent=indent))

    def pause(self, message="Press Enter to continue..."):
        input(f"\n{message}")

    def login(self, username, password):
        """Login and return token"""
        resp = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": username, "password": password}
        )
        if resp.status_code == 200:
            return resp.json()["access_token"]
        raise Exception(f"Login failed: {resp.status_code}")

    def make_request(self, method, endpoint, token, json_data=None, params=None):
        """Make authenticated request"""
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{BASE_URL}{endpoint}"

        if method == "GET":
            return requests.get(url, headers=headers, params=params)
        elif method == "POST":
            return requests.post(url, headers=headers, json=json_data, params=params)
        elif method == "PUT":
            return requests.put(url, headers=headers, json=json_data)

    def run(self):
        """Run complete demo"""

        self.print_header("INSTITUTIONAL TRADING INFRASTRUCTURE DEMO")
        print("This demo showcases:")
        print("  • Complete order lifecycle")
        print("  • Pre-trade risk controls")
        print("  • Event sourcing & audit trails")
        print("  • Role-based access control")
        print("  • Resilience patterns")
        print("  • Observability & metrics")

        self.pause()

        # =====================================================================
        # AUTHENTICATION
        # =====================================================================

        self.print_step(1, "AUTHENTICATION & AUTHORIZATION")

        print("\n1.1 Logging in as TRADER...")
        self.trader_token = self.login("trader1", "trader123")
        print("✓ Trader authenticated")

        print("\n1.2 Logging in as RISK MANAGER...")
        self.risk_token = self.login("risk1", "risk123")
        print("✓ Risk Manager authenticated")

        self.pause()

        # =====================================================================
        # RISK CONFIGURATION
        # =====================================================================

        self.print_step(2, "RISK LIMITS CONFIGURATION")

        print("\n2.1 Viewing current risk metrics...")
        resp = self.make_request("GET", "/risk/metrics", self.trader_token)
        metrics = resp.json()
        print(f"\nCurrent Risk Metrics:")
        print(f"  Net Exposure:    ${metrics['net_exposure']:,.2f}")
        print(f"  Gross Exposure:  ${metrics['gross_exposure']:,.2f}")
        print(f"  Daily Volume:    ${metrics['daily_volume']:,.2f}")
        print(f"  Total Positions: {metrics['total_positions']}")
        print(f"  Kill Switch:     {'ACTIVE' if metrics['kill_switch_active'] else 'INACTIVE'}")

        self.pause()

        print("\n2.2 Viewing current risk limits...")
        resp = self.make_request("GET", "/risk/limits", self.risk_token)
        limits = resp.json()
        print(f"\nRisk Limits:")
        print(f"  Max Position Size:   ${limits['max_position_size']:,.0f}")
        print(f"  Max Daily Volume:    ${limits['max_daily_volume']:,.0f}")
        print(f"  Max Net Exposure:    ${limits['max_net_exposure']:,.0f}")
        print(f"  Max Gross Exposure:  ${limits['max_gross_exposure']:,.0f}")

        self.pause()

        # =====================================================================
        # ORDER SUBMISSION
        # =====================================================================

        self.print_step(3, "ORDER SUBMISSION & PROCESSING")

        print("\n3.1 Submitting BUY order for AAPL...")
        order_request = {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 100,
            "price": 175.50,
            "strategy": "momentum",
            "client_order_id": f"demo-{int(time.time())}"
        }

        print("\nOrder Request:")
        self.print_json(order_request)

        resp = self.make_request("POST", "/orders", self.trader_token, json_data=order_request)
        order_response = resp.json()

        self.order_id = order_response["order_id"]
        self.correlation_id = order_response["correlation_id"]

        print("\nOrder Response:")
        print(f"  Order ID:       {order_response['order_id']}")
        print(f"  Status:         {order_response['status']}")
        print(f"  Correlation ID: {order_response['correlation_id']}")
        print(f"  Message:        {order_response.get('message', 'N/A')}")

        self.pause()

        print("\n3.2 Checking order status (after processing)...")
        time.sleep(1)  # Allow time for execution

        resp = self.make_request("GET", f"/orders/{self.order_id}", self.trader_token)
        order = resp.json()

        print(f"\nOrder Details:")
        print(f"  Symbol:            {order['symbol']}")
        print(f"  Side:              {order['side']}")
        print(f"  Quantity:          {order['quantity']}")
        print(f"  Price:             ${order['price']:.2f}")
        print(f"  Status:            {order['status']}")
        print(f"  Executed Quantity: {order.get('executed_quantity', 0)}")
        if order.get('executed_price'):
            print(f"  Executed Price:    ${order['executed_price']:.2f}")

        self.pause()

        # =====================================================================
        # AUDIT TRAIL
        # =====================================================================

        self.print_step(4, "AUDIT TRAIL & EVENT SOURCING")

        print("\n4.1 Replaying complete event chain for correlation ID...")
        print(f"Correlation ID: {self.correlation_id}")

        # Need admin/compliance role for audit
        admin_token = self.login("admin", "admin123")

        resp = self.make_request("GET", f"/audit/correlation/{self.correlation_id}", admin_token)
        audit_data = resp.json()

        print(f"\nTotal Events: {audit_data['total_events']}")
        print("\nEvent Chain:")

        for idx, event in enumerate(audit_data['events'], 1):
            print(f"\n  Event {idx}:")
            print(f"    Type:      {event['event_type']}")
            print(f"    Timestamp: {event['timestamp']}")
            print(f"    Event ID:  {event['event_id']}")

        self.pause()

        print("\n4.2 Viewing order-specific audit trail...")
        resp = self.make_request("GET", f"/audit/order/{self.order_id}/trail", admin_token)
        trail = resp.json()

        print(f"\nOrder Audit Trail ({trail['total_events']} events):")
        for event in trail['events']:
            print(f"  → {event['event_type']}")

        self.pause()

        # =====================================================================
        # RISK CONTROLS DEMO
        # =====================================================================

        self.print_step(5, "PRE-TRADE RISK CONTROLS")

        print("\n5.1 Attempting to submit order that exceeds position limit...")
        large_order = {
            "symbol": "TSLA",
            "side": "BUY",
            "quantity": 50000,  # Very large
            "price": 250,
            "strategy": "test"
        }

        resp = self.make_request("POST", "/orders", self.trader_token, json_data=large_order)
        rejection = resp.json()

        print(f"\nResult:")
        print(f"  Status:  {rejection['status']}")
        print(f"  Message: {rejection.get('message', 'N/A')}")

        if rejection['status'] == 'REJECTED':
            print("\n✓ Order correctly rejected by risk engine")

        self.pause()

        # =====================================================================
        # KILL SWITCH DEMO
        # =====================================================================

        self.print_step(6, "KILL SWITCH (Emergency Halt)")

        print("\n6.1 Activating kill switch...")
        resp = self.make_request(
            "POST",
            "/risk/kill-switch",
            self.risk_token,
            params={"enabled": True}
        )
        result = resp.json()
        print(f"  {result['message']}")

        self.pause()

        print("\n6.2 Attempting to submit order with kill switch active...")
        test_order = {
            "symbol": "MSFT",
            "side": "BUY",
            "quantity": 10,
            "price": 380,
            "strategy": "test"
        }

        resp = self.make_request("POST", "/orders", self.trader_token, json_data=test_order)
        blocked = resp.json()

        print(f"\nResult:")
        print(f"  Status:  {blocked['status']}")
        print(f"  Message: {blocked.get('message', 'N/A')}")

        if blocked['status'] == 'REJECTED':
            print("\n✓ Order correctly blocked by kill switch")

        self.pause()

        print("\n6.3 Deactivating kill switch...")
        resp = self.make_request(
            "POST",
            "/risk/kill-switch",
            self.risk_token,
            params={"enabled": False}
        )
        result = resp.json()
        print(f"  {result['message']}")

        self.pause()

        # =====================================================================
        # RBAC DEMO
        # =====================================================================

        self.print_step(7, "ROLE-BASED ACCESS CONTROL")

        print("\n7.1 Attempting to update risk limits as TRADER (should fail)...")
        resp = self.make_request(
            "PUT",
            "/risk/limits",
            self.trader_token,
            json_data={"max_position_size": 999999}
        )

        if resp.status_code == 403:
            print("✓ Access denied (403 Forbidden) - RBAC working correctly")
        else:
            print(f"✗ Unexpected response: {resp.status_code}")

        self.pause()

        print("\n7.2 Updating risk limits as RISK MANAGER (should succeed)...")
        new_limits = {
            "max_position_size": 750000,
            "max_daily_volume": 7500000,
            "max_net_exposure": 3000000,
            "max_gross_exposure": 12000000,
            "kill_switch_enabled": False
        }

        resp = self.make_request("PUT", "/risk/limits", self.risk_token, json_data=new_limits)

        if resp.status_code == 200:
            updated = resp.json()
            print("✓ Limits updated successfully")
            print(f"\nNew Limits:")
            print(f"  Max Position Size: ${updated['max_position_size']:,.0f}")
            print(f"  Max Daily Volume:  ${updated['max_daily_volume']:,.0f}")

        self.pause()

        # =====================================================================
        # OBSERVABILITY
        # =====================================================================

        self.print_step(8, "SYSTEM METRICS & OBSERVABILITY")

        print("\n8.1 Viewing system-wide metrics...")
        resp = self.make_request("GET", "/metrics", self.trader_token)
        sys_metrics = resp.json()

        print(f"\nSystem Metrics:")
        print(f"  Total Orders:  {sys_metrics['total_orders']}")
        print(f"  Total Events:  {sys_metrics['total_events']}")

        print(f"\n  Order Status Breakdown:")
        for status, count in sys_metrics['order_status_breakdown'].items():
            print(f"    {status}: {count}")

        print(f"\n  Circuit Breaker:")
        cb = sys_metrics['circuit_breaker']
        print(f"    Status:   {cb['status']}")
        print(f"    Failures: {cb['failures']}")

        self.pause()

        print("\n8.2 Viewing current positions...")
        resp = self.make_request("GET", "/risk/positions", self.trader_token)
        positions = resp.json()

        print(f"\nCurrent Positions ({positions['total_positions']}):")
        for pos in positions['positions']:
            value = pos['market_value']
            print(f"  {pos['symbol']}: {pos['quantity']} shares @ ${pos['average_price']:.2f} = ${value:,.2f}")

        self.pause()

        # =====================================================================
        # SUMMARY
        # =====================================================================

        self.print_header("DEMO COMPLETE")

        print("Demonstrated Capabilities:")
        print("  ✓ JWT Authentication & RBAC")
        print("  ✓ Order submission and processing")
        print("  ✓ Pre-trade risk validation")
        print("  ✓ Kill switch emergency halt")
        print("  ✓ Event sourcing & complete audit trail")
        print("  ✓ Position tracking")
        print("  ✓ System metrics & observability")
        print("  ✓ Role-based access control enforcement")

        print("\n" + "=" * 80)
        print("  This demonstrates institutional-grade architecture patterns:")
        print("  • Control Plane / Data Plane separation")
        print("  • Event Sourcing for auditability")
        print("  • Pre-trade risk controls")
        print("  • Resilience patterns (retry, circuit breaker, idempotency)")
        print("  • Security & compliance (JWT, RBAC, audit)")
        print("=" * 80 + "\n")


def main():
    """Main entry point"""
    try:
        demo = Demo()
        demo.run()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.\n")
    except requests.exceptions.ConnectionError:
        print("\n" + "=" * 80)
        print("ERROR: Cannot connect to ITIRP system")
        print("=" * 80)
        print("\nPlease ensure the system is running:")
        print("  python itirp_complete.py")
        print("\nThen run this demo again:")
        print("  python demo_itirp.py")
        print()
    except Exception as e:
        print(f"\nError during demo: {str(e)}\n")


if __name__ == "__main__":
    main()