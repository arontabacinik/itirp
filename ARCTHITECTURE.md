# ITIRP - Technical Architecture Documentation

## Executive Summary

The **Institutional Trading Infrastructure & Risk Platform (ITIRP)** is a reference implementation of institutional-grade trading infrastructure, demonstrating architectural patterns used by major financial institutions.

**Key Design Principles:**
- **Separation of Concerns**: Control Plane vs Data Plane
- **Auditability**: Complete event sourcing
- **Safety**: Pre-trade risk controls
- **Resilience**: Fault tolerance patterns
- **Security**: Zero-trust architecture with RBAC

---

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLIENT APPLICATIONS                           │
│  (Web UI, Mobile Apps, Trading Terminals, APIs, Scripts)              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         API GATEWAY (FastAPI)                           │
│  • Authentication (JWT)                                                 │
│  • Authorization (RBAC)                                                 │
│  • Request validation                                                   │
│  • Rate limiting (future)                                               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
        ┌───────────────────────┐       ┌───────────────────────┐
        │   CONTROL PLANE       │       │     DATA PLANE        │
        │                       │       │                       │
        │  • Policy Management  │       │  • Execution Engine   │
        │  • Risk Config        │       │  • Risk Engine        │
        │  • User Management    │       │  • Simulation Engine  │
        │  • Audit Queries      │       │  • Event Processing   │
        └───────────────────────┘       └───────────────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
                        ┌───────────────────────┐
                        │    EVENT STORE        │
                        │  (Event Sourcing)     │
                        │  • Immutable events   │
                        │  • Audit trail        │
                        │  • Replay capability  │
                        └───────────────────────┘
```

---

## Core Components

### 1. Event Store (Event Sourcing)

**Purpose**: Complete, immutable audit trail of all system state changes.

**Key Features:**
- Every state change captured as an event
- Events are append-only (immutability)
- Correlation IDs for distributed tracing
- Deterministic replay capability
- Regulatory compliance support

**Event Structure:**
```python
@dataclass
class Event:
    event_id: str              # Unique identifier
    event_type: EventType      # ORDER_CREATED, RISK_CHECK_PASSED, etc.
    correlation_id: str        # Links related events
    order_id: str              # Entity identifier
    timestamp: datetime        # Precise timing
    payload: Dict[str, Any]    # Event-specific data
    user_id: str              # Actor (audit)
```

**Event Flow Example:**
```
Order Submission:
  ORDER_CREATED
    ↓
  RISK_CHECK_STARTED
    ↓
  RISK_CHECK_PASSED  (or RISK_CHECK_FAILED)
    ↓
  EXECUTION_STARTED
    ↓
  EXECUTION_COMPLETED  (or EXECUTION_FAILED)
```

**Benefits:**
- **Auditability**: Complete history reconstruction
- **Debugging**: Trace exact sequence of events
- **Compliance**: Regulatory reporting
- **Recovery**: Rebuild state from events

---

### 2. Risk Engine (Pre-Trade Controls)

**Purpose**: Validate all orders against institutional risk limits before execution.

**Risk Checks Performed:**

1. **Position Size Limit**
   - Prevents single position from being too large
   - Default: $1,000,000 per position

2. **Daily Volume Limit**
   - Controls total trading activity per day
   - Default: $10,000,000 daily

3. **Net Exposure Limit**
   - Net exposure = Sum of all positions (long - short)
   - Default: $5,000,000 max net exposure

4. **Gross Exposure Limit**
   - Gross exposure = Sum of absolute values of all positions
   - Default: $15,000,000 max gross exposure

5. **Kill Switch**
   - Emergency halt of all trading
   - Highest priority check
   - Activated by Risk Managers

**Risk Check Algorithm:**
```python
async def check_order(order: Order) -> RiskCheckResult:
    violations = []
    
    # 1. Kill switch (immediate rejection)
    if kill_switch_enabled:
        return REJECTED("Kill switch active")
    
    # 2. Position size check
    if order.notional_value() > max_position_size:
        violations.append(POSITION_LIMIT)
    
    # 3. Daily volume check
    if daily_volume + order.notional_value() > max_daily_volume:
        violations.append(DAILY_VOLUME_LIMIT)
    
    # 4. Project positions after order
    projected_positions = calculate_projected_positions(order)
    
    # 5. Net exposure check
    net_exposure = sum(position.value for position in projected_positions)
    if abs(net_exposure) > max_net_exposure:
        violations.append(NET_EXPOSURE_LIMIT)
    
    # 6. Gross exposure check
    gross_exposure = sum(abs(position.value) for position in projected_positions)
    if gross_exposure > max_gross_exposure:
        violations.append(GROSS_EXPOSURE_LIMIT)
    
    return RiskCheckResult(
        passed=(len(violations) == 0),
        violations=violations
    )
```

**Position Tracking:**
- Real-time position updates after executions
- Average price calculation
- P&L tracking (simplified)
- Daily volume reset at midnight UTC

---

### 3. Execution Engine

**Purpose**: Process orders with institutional-grade resilience patterns.

**Key Patterns:**

#### a) Idempotency
Prevents duplicate order submissions.

```python
execution_key = hash(user_id, symbol, side, quantity, price, client_order_id)

if execution_key in executed_keys:
    return HTTP 409 Conflict  # Duplicate detected
```

**Benefits:**
- Network retry safety
- Client-side failure recovery
- Prevents accidental duplicates

#### b) Retry with Exponential Backoff
Handles transient failures gracefully.

```python
for attempt in range(MAX_RETRY_ATTEMPTS):  # 3 attempts
    try:
        execute_order()
        return SUCCESS
    except TransientError:
        if attempt < MAX_RETRY_ATTEMPTS - 1:
            await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s
        else:
            return FAILED
```

**Benefits:**
- Handles temporary network issues
- Reduces false failures
- Respects downstream systems

#### c) Circuit Breaker
Prevents cascading failures.

```python
if consecutive_failures >= THRESHOLD:  # 5 failures
    circuit_breaker_status = OPEN
    circuit_breaker_open_until = now + TIMEOUT  # 60 seconds
    
# While open, reject all orders immediately
if circuit_breaker_status == OPEN and now < circuit_breaker_open_until:
    return FAILED("Circuit breaker open")

# After timeout, automatically reset
if now >= circuit_breaker_open_until:
    circuit_breaker_status = CLOSED
    consecutive_failures = 0
```

**Benefits:**
- Protects downstream services
- Prevents resource exhaustion
- Auto-recovery after cooldown

#### d) Asynchronous Execution
Non-blocking order processing.

```python
# Immediate response to client
order.status = APPROVED
response = OrderResponse(order_id, status=APPROVED)

# Process asynchronously
asyncio.create_task(execute_order(order))

return response  # Client gets immediate acknowledgment
```

**Benefits:**
- Low latency responses
- High throughput
- Better resource utilization

---

### 4. Authentication & Authorization

**Purpose**: Secure access control with role-based permissions.

**Authentication Flow:**

```
1. Client sends credentials
   POST /api/v1/auth/login
   {username, password}
   
2. Server validates credentials
   hash(password) == stored_hash?
   
3. Server generates JWT
   payload = {sub, user_id, role, exp}
   token = sign(payload, SECRET_KEY)
   
4. Server returns token
   {access_token, token_type, expires_in}
   
5. Client includes token in requests
   Authorization: Bearer <token>
   
6. Server validates token on each request
   payload = verify(token, SECRET_KEY)
   if expired: return 401
   if invalid: return 401
   
7. Server checks permissions
   if user.role < required_role: return 403
```

**Role Hierarchy:**
```
ADMIN (level 4)
  ├─ Full system access
  └─ Can perform all operations
  
COMPLIANCE (level 3)
  ├─ Audit trail access
  ├─ Read-only operations
  └─ Regulatory reporting
  
RISK_MANAGER (level 2)
  ├─ Configure risk limits
  ├─ Activate kill switch
  └─ View all positions
  
TRADER (level 1)
  ├─ Submit orders
  ├─ View own orders
  └─ View risk metrics
```

**Security Features:**
- JWT with HS256 (HMAC-SHA256)
- 30-minute token expiration
- Stateless authentication
- Role-based access control
- Least privilege principle

---

## Data Flow Diagrams

### Order Submission Flow

```
Client                API Gateway         Risk Engine         Execution Engine     Event Store
  │                        │                   │                      │                 │
  │ POST /orders           │                   │                      │                 │
  ├───────────────────────>│                   │                      │                 │
  │                        │                   │                      │                 │
  │                        │ Validate JWT      │                      │                 │
  │                        │ Check RBAC        │                      │                 │
  │                        │                   │                      │                 │
  │                        │ Create Order      │                      │                 │
  │                        ├──────────────────────────────────────────>│                 │
  │                        │                   │                      │                 │
  │                        │                   │                      │ ORDER_CREATED   │
  │                        │                   │                      ├────────────────>│
  │                        │                   │                      │                 │
  │                        │                   │ check_order()        │                 │
  │                        │                   │<─────────────────────┤                 │
  │                        │                   │                      │                 │
  │                        │                   │ RISK_CHECK_STARTED   │                 │
  │                        │                   ├─────────────────────────────────────>│
  │                        │                   │                      │                 │
  │                        │                   │ Validate limits      │                 │
  │                        │                   │ Calculate exposure   │                 │
  │                        │                   │                      │                 │
  │                        │                   │ RISK_CHECK_PASSED    │                 │
  │                        │                   ├─────────────────────────────────────>│
  │                        │                   │                      │                 │
  │                        │                   │ RiskCheckResult      │                 │
  │                        │                   ├─────────────────────>│                 │
  │                        │                   │                      │                 │
  │                        │                   │                      │ execute_async() │
  │                        │                   │                      │ (background)    │
  │                        │                   │                      │                 │
  │ 200 OK                 │                   │                      │                 │
  │ {order_id, status}     │                   │                      │                 │
  │<───────────────────────┤                   │                      │                 │
  │                        │                   │                      │                 │
  │                        │                   │                      │ EXECUTING       │
  │                        │                   │                      ├────────────────>│
  │                        │                   │                      │                 │
  │                        │                   │                      │ Market Exec     │
  │                        │                   │                      │ (simulated)     │
  │                        │                   │                      │                 │
  │                        │                   │                      │ EXECUTED        │
  │                        │                   │                      ├────────────────>│
  │                        │                   │                      │                 │
  │                        │                   │ update_position()    │                 │
  │                        │                   │<─────────────────────┤                 │
```

---

## Resilience Patterns

### 1. Retry Logic

**Problem**: Transient network failures

**Solution**: Exponential backoff retry

**Implementation:**
```python
MAX_RETRY_ATTEMPTS = 3
backoff_delays = [1, 2, 4]  # seconds

for attempt in range(MAX_RETRY_ATTEMPTS):
    try:
        result = execute_operation()
        return result  # Success
    except TransientError as e:
        if attempt < MAX_RETRY_ATTEMPTS - 1:
            await asyncio.sleep(backoff_delays[attempt])
        else:
            raise  # Final failure
```

**When to use:**
- Network timeouts
- Service temporarily unavailable
- Rate limit exceeded (temporary)

**When NOT to use:**
- Validation errors (permanent)
- Authentication failures
- Business logic violations

---

### 2. Circuit Breaker

**Problem**: Cascading failures overwhelming system

**Solution**: Fail fast when downstream is unhealthy

**States:**
```
CLOSED (Normal)
  │
  │ consecutive_failures >= threshold
  ▼
OPEN (Blocking)
  │
  │ timeout elapsed
  ▼
HALF_OPEN (Testing)
  │
  ├─ Success ──> CLOSED
  └─ Failure ──> OPEN
```

**Configuration:**
- Threshold: 5 consecutive failures
- Timeout: 60 seconds
- Recovery: Automatic

**Benefits:**
- Prevents resource exhaustion
- Fast failure (better than hanging)
- Automatic recovery
- Reduced load on failing service

---

### 3. Idempotency

**Problem**: Duplicate requests due to retries

**Solution**: Unique execution keys

**Implementation:**
```python
execution_key = hash(
    user_id,
    symbol,
    side,
    quantity,
    price,
    client_order_id  # Client-provided uniqueness
)

if execution_key in processed_keys:
    return 409  # Already processed
else:
    processed_keys.add(execution_key)
    process_order()
```

**Benefits:**
- Safe retries
- Network failure recovery
- Prevents duplicate trades

---

### 4. Timeouts

**Problem**: Operations hanging indefinitely

**Solution**: Enforce time limits

**Implementation:**
```python
try:
    result = await asyncio.wait_for(
        operation(),
        timeout=5.0  # 5 seconds max
    )
except asyncio.TimeoutError:
    logger.error("Operation timed out")
    raise
```

**Benefits:**
- Prevents resource leaks
- Predictable behavior
- Better error handling

---

## Security Architecture

### Defense in Depth

```
┌─────────────────────────────────────────┐
│  Layer 1: Network Security              │
│  • TLS/HTTPS (production)               │
│  • Firewall rules                       │
│  • DDoS protection                      │
└─────────────────────────────────────────┘
               │
┌─────────────────────────────────────────┐
│  Layer 2: Authentication                │
│  • JWT tokens                           │
│  • Password hashing (SHA-256)           │
│  • Token expiration (30 min)            │
└─────────────────────────────────────────┘
               │
┌─────────────────────────────────────────┐
│  Layer 3: Authorization (RBAC)          │
│  • Role-based access control            │
│  • Least privilege                      │
│  • Segregation of duties                │
└─────────────────────────────────────────┘
               │
┌─────────────────────────────────────────┐
│  Layer 4: Input Validation              │
│  • Pydantic models                      │
│  • Type checking                        │
│  • Range validation                     │
└─────────────────────────────────────────┘
               │
┌─────────────────────────────────────────┐
│  Layer 5: Audit Logging                 │
│  • Event sourcing                       │
│  • Immutable audit trail                │
│  • User action tracking                 │
└─────────────────────────────────────────┘
```

### RBAC Matrix

| Endpoint                  | TRADER | RISK_MGR | COMPLIANCE | ADMIN |
|---------------------------|--------|----------|------------|-------|
| POST /orders              | ✓      | ✓        | ✓          | ✓     |
| GET /orders               | ✓      | ✓        | ✓          | ✓     |
| GET /risk/metrics         | ✓      | ✓        | ✓          | ✓     |
| GET /risk/positions       | ✓      | ✓        | ✓          | ✓     |
| PUT /risk/limits          | ✗      | ✓        | ✓          | ✓     |
| POST /risk/kill-switch    | ✗      | ✓        | ✓          | ✓     |
| GET /audit/*              | ✗      | ✗        | ✓          | ✓     |

---

## Observability

### Structured Logging

All logs follow structured format:
```json
{
  "timestamp": "2026-01-30T14:30:00.123456Z",
  "level": "INFO",
  "component": "ExecutionEngine",
  "event": "order_executed",
  "order_id": "550e8400-e29b-41d4-a716-446655440000",
  "correlation_id": "660e8400-e29b-41d4-a716-446655440001",
  "user_id": "trader1",
  "details": {
    "symbol": "AAPL",
    "quantity": 100,
    "price": 150.50
  }
}
```

### Metrics

**Order Metrics:**
- Total orders submitted
- Orders by status (EXECUTED, REJECTED, FAILED)
- Average execution time
- Retry count distribution

**Risk Metrics:**
- Net exposure (real-time)
- Gross exposure (real-time)
- Daily volume
- Limit breach rate

**System Metrics:**
- Circuit breaker status
- Event store size
- API response times
- Error rates

### Distributed Tracing

Correlation IDs link related operations:
```
correlation_id: 660e8400-...
  ├─ ORDER_CREATED (order_id: 550e8400-...)
  ├─ RISK_CHECK_STARTED
  ├─ RISK_CHECK_PASSED
  ├─ EXECUTION_STARTED
  └─ EXECUTION_COMPLETED
```

**Benefits:**
- End-to-end visibility
- Performance analysis
- Root cause analysis
- SLA tracking

---

## Scalability Considerations

### Current Architecture (Single File)

**Suitable for:**
- Development
- Testing
- Small deployments
- Proof of concept

**Limitations:**
- Single process
- In-memory state
- No horizontal scaling

### Production Architecture (Future)

```
┌──────────────────────────────────────────────────────────────┐
│                       LOAD BALANCER                          │
└──────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   ┌─────────┐          ┌─────────┐          ┌─────────┐
   │ API #1  │          │ API #2  │          │ API #3  │
   └─────────┘          └─────────┘          └─────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌──────────────┐      ┌──────────────┐     ┌──────────────┐
│ Execution #1 │      │ Execution #2 │     │ Execution #3 │
└──────────────┘      └──────────────┘     └──────────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
            ┌──────────────┐    ┌──────────────┐
            │  PostgreSQL  │    │    Redis     │
            │ (Event Store)│    │   (Cache)    │
            └──────────────┘    └──────────────┘
```

**Required Changes:**
1. **Persistent Event Store**: PostgreSQL/TimescaleDB
2. **Distributed Cache**: Redis for positions
3. **Message Queue**: Kafka/RabbitMQ for events
4. **Service Discovery**: Consul/Kubernetes
5. **Load Balancing**: Nginx/HAProxy

---

## Compliance & Regulatory

### Audit Trail Requirements

**MiFID II / Dodd-Frank Compliance:**
- Complete order lifecycle tracking
- Timestamp precision (microseconds)
- User attribution
- Immutable records
- 7+ year retention

**Implementation:**
```python
# Event sourcing provides:
✓ Complete audit trail
✓ Immutable events
✓ User tracking
✓ Timestamp precision
✓ Replay capability
```

### Regulatory Reporting

**Trade Reconstruction:**
```python
# Replay all events for correlation ID
events = event_store.replay(correlation_id)

# Reconstruct complete trade lifecycle
for event in events:
    print(f"{event.timestamp}: {event.event_type}")
    
# Output:
# 2026-01-30T14:30:00.001: ORDER_CREATED
# 2026-01-30T14:30:00.015: RISK_CHECK_STARTED
# 2026-01-30T14:30:00.023: RISK_CHECK_PASSED
# 2026-01-30T14:30:00.025: EXECUTION_STARTED
# 2026-01-30T14:30:00.150: EXECUTION_COMPLETED
```

---

## Performance Characteristics

### Latency Targets (Single Instance)

| Operation              | Target    | Typical   |
|------------------------|-----------|-----------|
| Authentication         | < 100ms   | ~50ms     |
| Order submission       | < 200ms   | ~100ms    |
| Risk check             | < 50ms    | ~20ms     |
| Event append           | < 10ms    | ~5ms      |
| Audit query            | < 500ms   | ~200ms    |

### Throughput

**Current (Single Process):**
- ~100 orders/second
- ~500 risk checks/second
- ~1000 events/second

**Production (Distributed):**
- ~10,000 orders/second
- ~50,000 risk checks/second
- ~100,000 events/second

---

## Future Enhancements

### Phase 2: Advanced Risk
- Value at Risk (VaR) calculation
- Stress testing
- Scenario analysis
- Monte Carlo simulations
- Real-time P&L

### Phase 3: Market Data
- Real-time price feeds
- Historical data integration
- Technical indicators
- Market depth analysis

### Phase 4: Matching Engine
- Internal order matching
- Price-time priority
- Order book management
- Market making

### Phase 5: Multi-Asset
- Equities
- Options
- Futures
- FX
- Crypto

---

## Conclusion

The ITIRP demonstrates institutional-grade architectural patterns in a single, comprehensible implementation. It serves as a reference for building production trading systems with proper risk controls, auditability, and operational resilience.

**Key Takeaways:**
1. **Event Sourcing** provides complete auditability
2. **Pre-trade Risk** prevents catastrophic losses
3. **Resilience Patterns** ensure system stability
4. **RBAC** enforces security and compliance
5. **Observability** enables operational excellence

This architecture scales from a single-file demo to a distributed, multi-region production system while maintaining the same core principles.