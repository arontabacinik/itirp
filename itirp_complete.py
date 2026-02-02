"""
Institutional Trading Infrastructure & Risk Platform (ITIRP)
=============================================================

Complete institutional-grade trading infrastructure in a single file.
Demonstrates control plane/data plane separation, event sourcing, pre-trade risk,
audit trails, and operational resilience patterns used by major financial institutions.

Architecture:
- Control Plane: Configuration, auth, orchestration (FastAPI)
- Data Plane: Execution, risk, simulation engines
- Event Store: Complete audit trail with event sourcing
- Observability: Metrics, tracing, structured logging

Author: Financial Engineering Demo
License: MIT
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import jwt
from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

# =============================================================================
# CONFIGURATION & CONSTANTS
# =============================================================================

SECRET_KEY = "institutional-grade-secret-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Risk limits (institutional standards)
DEFAULT_MAX_POSITION_SIZE = 1_000_000  # USD
DEFAULT_MAX_DAILY_VOLUME = 10_000_000  # USD
DEFAULT_MAX_NET_EXPOSURE = 5_000_000  # USD
DEFAULT_MAX_GROSS_EXPOSURE = 15_000_000  # USD

# Execution parameters
MAX_RETRY_ATTEMPTS = 3
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_TIMEOUT = 60  # seconds

# =============================================================================
# LOGGING SETUP (Structured Logging)
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ITIRP")


# =============================================================================
# ENUMS & DATA MODELS
# =============================================================================

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    RISK_CHECK = "RISK_CHECK"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class EventType(str, Enum):
    ORDER_CREATED = "ORDER_CREATED"
    RISK_CHECK_STARTED = "RISK_CHECK_STARTED"
    RISK_CHECK_PASSED = "RISK_CHECK_PASSED"
    RISK_CHECK_FAILED = "RISK_CHECK_FAILED"
    EXECUTION_STARTED = "EXECUTION_STARTED"
    EXECUTION_COMPLETED = "EXECUTION_COMPLETED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    ORDER_CANCELLED = "ORDER_CANCELLED"


class RiskViolationType(str, Enum):
    POSITION_LIMIT = "POSITION_LIMIT"
    DAILY_VOLUME_LIMIT = "DAILY_VOLUME_LIMIT"
    NET_EXPOSURE_LIMIT = "NET_EXPOSURE_LIMIT"
    GROSS_EXPOSURE_LIMIT = "GROSS_EXPOSURE_LIMIT"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"


class UserRole(str, Enum):
    TRADER = "TRADER"
    RISK_MANAGER = "RISK_MANAGER"
    COMPLIANCE = "COMPLIANCE"
    ADMIN = "ADMIN"


# =============================================================================
# PYDANTIC MODELS (API Contracts)
# =============================================================================

class OrderRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    side: OrderSide
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    strategy: str = Field(default="default", max_length=50)
    client_order_id: Optional[str] = None

    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, v):
        return v.upper()


class OrderResponse(BaseModel):
    order_id: str
    status: OrderStatus
    correlation_id: str
    timestamp: datetime
    message: Optional[str] = None


class RiskLimitsConfig(BaseModel):
    max_position_size: float = DEFAULT_MAX_POSITION_SIZE
    max_daily_volume: float = DEFAULT_MAX_DAILY_VOLUME
    max_net_exposure: float = DEFAULT_MAX_NET_EXPOSURE
    max_gross_exposure: float = DEFAULT_MAX_GROSS_EXPOSURE
    kill_switch_enabled: bool = False


class UserCredentials(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class PositionInfo(BaseModel):
    symbol: str
    quantity: float
    average_price: float
    market_value: float
    unrealized_pnl: float


class RiskMetrics(BaseModel):
    net_exposure: float
    gross_exposure: float
    daily_volume: float
    total_positions: int
    largest_position: float
    kill_switch_active: bool


# =============================================================================
# DATACLASSES (Internal Domain Models)
# =============================================================================

@dataclass
class Event:
    """Event Sourcing - every state change is an immutable event"""
    event_id: str
    event_type: EventType
    correlation_id: str
    order_id: str
    timestamp: datetime
    payload: Dict[str, Any]
    user_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['event_type'] = self.event_type.value
        return data


@dataclass
class Order:
    """Core order entity"""
    order_id: str
    correlation_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    strategy: str
    status: OrderStatus
    created_at: datetime
    user_id: str
    client_order_id: Optional[str] = None
    executed_quantity: float = 0.0
    executed_price: Optional[float] = None
    rejection_reason: Optional[str] = None
    retry_count: int = 0

    def notional_value(self) -> float:
        return self.quantity * self.price


@dataclass
class Position:
    """Position tracking"""
    symbol: str
    quantity: float
    average_price: float
    realized_pnl: float = 0.0


@dataclass
class RiskCheckResult:
    """Risk evaluation result"""
    passed: bool
    violations: List[RiskViolationType] = field(default_factory=list)
    message: str = ""


# =============================================================================
# EVENT STORE (Event Sourcing & Audit Trail)
# =============================================================================

class EventStore:
    """
    Institutional-grade event store with complete audit trail.
    All state changes are persisted as immutable events.
    Supports replay, correlation tracking, and regulatory reporting.
    """

    def __init__(self):
        self.events: List[Event] = []
        self.events_by_correlation: Dict[str, List[Event]] = defaultdict(list)
        self.events_by_order: Dict[str, List[Event]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def append(self, event: Event) -> None:
        """Append event with atomic guarantees"""
        async with self._lock:
            self.events.append(event)
            self.events_by_correlation[event.correlation_id].append(event)
            self.events_by_order[event.order_id].append(event)
            logger.info(
                f"Event stored: {event.event_type.value} | "
                f"Order: {event.order_id} | "
                f"Correlation: {event.correlation_id}"
            )

    async def get_by_correlation(self, correlation_id: str) -> List[Event]:
        """Retrieve complete event chain for correlation ID"""
        async with self._lock:
            return list(self.events_by_correlation.get(correlation_id, []))

    async def get_by_order(self, order_id: str) -> List[Event]:
        """Retrieve all events for specific order"""
        async with self._lock:
            return list(self.events_by_order.get(order_id, []))

    async def replay(self, correlation_id: str) -> List[Dict[str, Any]]:
        """Replay events for debugging/audit (deterministic reconstruction)"""
        events = await self.get_by_correlation(correlation_id)
        return [event.to_dict() for event in events]

    async def get_all_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent events for monitoring"""
        async with self._lock:
            return [e.to_dict() for e in self.events[-limit:]]


# =============================================================================
# RISK ENGINE (Pre-Trade Risk Controls)
# =============================================================================

class RiskEngine:
    """
    Pre-trade risk engine with institutional controls.
    Validates all orders against position limits, exposure limits,
    and circuit breakers before execution.
    """

    def __init__(self, event_store: EventStore):
        self.event_store = event_store
        self.config = RiskLimitsConfig()
        self.positions: Dict[str, Position] = {}
        self.daily_volume: float = 0.0
        self.daily_volume_reset: datetime = datetime.utcnow()
        self._lock = asyncio.Lock()

    async def check_order(self, order: Order, correlation_id: str) -> RiskCheckResult:
        """
        Comprehensive pre-trade risk check.
        Returns violations if any limit is breached.
        """
        async with self._lock:
            # Reset daily volume if new day
            await self._reset_daily_volume_if_needed()

            # Emit risk check started event
            await self.event_store.append(Event(
                event_id=str(uuid.uuid4()),
                event_type=EventType.RISK_CHECK_STARTED,
                correlation_id=correlation_id,
                order_id=order.order_id,
                timestamp=datetime.utcnow(),
                payload={"order": order.order_id},
                user_id=order.user_id
            ))

            violations = []

            # Kill switch check (highest priority)
            if self.config.kill_switch_enabled:
                violations.append(RiskViolationType.KILL_SWITCH_ACTIVE)
                return RiskCheckResult(
                    passed=False,
                    violations=violations,
                    message="Kill switch is active - all trading halted"
                )

            # Position size check
            notional = order.notional_value()
            if notional > self.config.max_position_size:
                violations.append(RiskViolationType.POSITION_LIMIT)

            # Daily volume check
            if self.daily_volume + notional > self.config.max_daily_volume:
                violations.append(RiskViolationType.DAILY_VOLUME_LIMIT)

            # Net and gross exposure checks
            projected_positions = self._calculate_projected_positions(order)
            net_exposure = self._calculate_net_exposure(projected_positions)
            gross_exposure = self._calculate_gross_exposure(projected_positions)

            if abs(net_exposure) > self.config.max_net_exposure:
                violations.append(RiskViolationType.NET_EXPOSURE_LIMIT)

            if gross_exposure > self.config.max_gross_exposure:
                violations.append(RiskViolationType.GROSS_EXPOSURE_LIMIT)

            # Result
            passed = len(violations) == 0

            # Emit result event
            event_type = EventType.RISK_CHECK_PASSED if passed else EventType.RISK_CHECK_FAILED
            await self.event_store.append(Event(
                event_id=str(uuid.uuid4()),
                event_type=event_type,
                correlation_id=correlation_id,
                order_id=order.order_id,
                timestamp=datetime.utcnow(),
                payload={
                    "passed": passed,
                    "violations": [v.value for v in violations],
                    "net_exposure": net_exposure,
                    "gross_exposure": gross_exposure
                },
                user_id=order.user_id
            ))

            message = "Risk check passed" if passed else f"Risk violations: {', '.join(v.value for v in violations)}"

            return RiskCheckResult(
                passed=passed,
                violations=violations,
                message=message
            )

    async def update_position(self, order: Order) -> None:
        """Update positions after execution"""
        async with self._lock:
            if order.symbol not in self.positions:
                self.positions[order.symbol] = Position(
                    symbol=order.symbol,
                    quantity=0.0,
                    average_price=0.0
                )

            position = self.positions[order.symbol]
            quantity_delta = order.executed_quantity if order.side == OrderSide.BUY else -order.executed_quantity

            # Update average price
            if position.quantity + quantity_delta != 0:
                total_cost = (position.quantity * position.average_price +
                              quantity_delta * order.executed_price)
                position.quantity += quantity_delta
                position.average_price = total_cost / position.quantity
            else:
                position.quantity = 0
                position.average_price = 0

            # Update daily volume
            self.daily_volume += order.notional_value()

    async def get_metrics(self) -> RiskMetrics:
        """Get current risk metrics"""
        async with self._lock:
            await self._reset_daily_volume_if_needed()

            net_exposure = self._calculate_net_exposure(self.positions)
            gross_exposure = self._calculate_gross_exposure(self.positions)
            largest_position = max(
                [abs(p.quantity * p.average_price) for p in self.positions.values()],
                default=0.0
            )

            return RiskMetrics(
                net_exposure=net_exposure,
                gross_exposure=gross_exposure,
                daily_volume=self.daily_volume,
                total_positions=len(self.positions),
                largest_position=largest_position,
                kill_switch_active=self.config.kill_switch_enabled
            )

    def _calculate_projected_positions(self, order: Order) -> Dict[str, Position]:
        """Calculate positions if order executes"""
        projected = self.positions.copy()
        if order.symbol not in projected:
            projected[order.symbol] = Position(
                symbol=order.symbol,
                quantity=0.0,
                average_price=0.0
            )

        position = projected[order.symbol]
        quantity_delta = order.quantity if order.side == OrderSide.BUY else -order.quantity
        projected[order.symbol].quantity = position.quantity + quantity_delta

        return projected

    @staticmethod
    def _calculate_net_exposure(positions: Dict[str, Position]) -> float:
        """Net exposure = sum of all position values (long - short)"""
        return sum(p.quantity * p.average_price for p in positions.values())

    @staticmethod
    def _calculate_gross_exposure(positions: Dict[str, Position]) -> float:
        """Gross exposure = sum of absolute position values"""
        return sum(abs(p.quantity * p.average_price) for p in positions.values())

    async def _reset_daily_volume_if_needed(self) -> None:
        """Reset daily volume counter at day boundary"""
        now = datetime.utcnow()
        if now.date() > self.daily_volume_reset.date():
            self.daily_volume = 0.0
            self.daily_volume_reset = now
            logger.info("Daily volume counter reset")


# =============================================================================
# EXECUTION ENGINE (Order Processing & Execution)
# =============================================================================

class ExecutionEngine:
    """
    Execution engine with retry logic, circuit breakers, and idempotency.
    Simulates institutional-grade order execution with resilience patterns.
    """

    def __init__(self, event_store: EventStore, risk_engine: RiskEngine):
        self.event_store = event_store
        self.risk_engine = risk_engine
        self.orders: Dict[str, Order] = {}
        self.execution_keys: Set[str] = set()  # Idempotency tracking
        self.circuit_breaker_failures = 0
        self.circuit_breaker_open_until: Optional[datetime] = None
        self._lock = asyncio.Lock()

    async def submit_order(self, request: OrderRequest, user_id: str) -> OrderResponse:
        """
        Submit order with complete processing pipeline:
        1. Idempotency check
        2. Risk evaluation
        3. Execution
        4. Position update
        """
        correlation_id = str(uuid.uuid4())
        order_id = str(uuid.uuid4())

        # Idempotency: prevent duplicate submissions
        execution_key = self._generate_execution_key(request, user_id)
        async with self._lock:
            if execution_key in self.execution_keys:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Duplicate order submission detected"
                )
            self.execution_keys.add(execution_key)

        # Create order
        order = Order(
            order_id=order_id,
            correlation_id=correlation_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            strategy=request.strategy,
            status=OrderStatus.PENDING,
            created_at=datetime.utcnow(),
            user_id=user_id,
            client_order_id=request.client_order_id
        )

        async with self._lock:
            self.orders[order_id] = order

        # Emit order created event
        await self.event_store.append(Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.ORDER_CREATED,
            correlation_id=correlation_id,
            order_id=order_id,
            timestamp=datetime.utcnow(),
            payload={
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": order.quantity,
                "price": order.price,
                "strategy": order.strategy
            },
            user_id=user_id
        ))

        # Risk check
        order.status = OrderStatus.RISK_CHECK
        risk_result = await self.risk_engine.check_order(order, correlation_id)

        if not risk_result.passed:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = risk_result.message
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                correlation_id=correlation_id,
                timestamp=datetime.utcnow(),
                message=risk_result.message
            )

        # Execute order (async)
        order.status = OrderStatus.APPROVED
        asyncio.create_task(self._execute_order(order))

        return OrderResponse(
            order_id=order_id,
            status=OrderStatus.APPROVED,
            correlation_id=correlation_id,
            timestamp=datetime.utcnow(),
            message="Order approved and submitted for execution"
        )

    async def _execute_order(self, order: Order) -> None:
        """
        Execute order with retry logic and circuit breaker.
        Simulates market execution with configurable failure scenarios.
        """
        # Circuit breaker check
        if self.circuit_breaker_open_until:
            if datetime.utcnow() < self.circuit_breaker_open_until:
                order.status = OrderStatus.FAILED
                order.rejection_reason = "Circuit breaker open"
                logger.warning(f"Circuit breaker blocked order {order.order_id}")
                return
            else:
                # Reset circuit breaker
                self.circuit_breaker_open_until = None
                self.circuit_breaker_failures = 0

        order.status = OrderStatus.EXECUTING

        # Emit execution started event
        await self.event_store.append(Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.EXECUTION_STARTED,
            correlation_id=order.correlation_id,
            order_id=order.order_id,
            timestamp=datetime.utcnow(),
            payload={"retry_attempt": order.retry_count},
            user_id=order.user_id
        ))

        # Simulate execution with retry logic
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                # Simulate market execution (can be replaced with real broker API)
                await asyncio.sleep(0.1)  # Simulate network latency

                # Simulated execution (90% success rate)
                import random
                if random.random() < 0.9:
                    # Successful execution
                    order.executed_quantity = order.quantity
                    order.executed_price = order.price * (1 + random.uniform(-0.001, 0.001))
                    order.status = OrderStatus.EXECUTED

                    # Update position
                    await self.risk_engine.update_position(order)

                    # Emit success event
                    await self.event_store.append(Event(
                        event_id=str(uuid.uuid4()),
                        event_type=EventType.EXECUTION_COMPLETED,
                        correlation_id=order.correlation_id,
                        order_id=order.order_id,
                        timestamp=datetime.utcnow(),
                        payload={
                            "executed_quantity": order.executed_quantity,
                            "executed_price": order.executed_price,
                            "retry_attempt": attempt
                        },
                        user_id=order.user_id
                    ))

                    logger.info(f"Order {order.order_id} executed successfully")
                    return
                else:
                    raise Exception("Simulated market rejection")

            except Exception as e:
                order.retry_count += 1
                logger.warning(f"Execution attempt {attempt + 1} failed for {order.order_id}: {str(e)}")

                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    # Exponential backoff
                    await asyncio.sleep(2 ** attempt)
                else:
                    # Final failure
                    order.status = OrderStatus.FAILED
                    order.rejection_reason = f"Execution failed after {MAX_RETRY_ATTEMPTS} attempts"

                    # Circuit breaker logic
                    self.circuit_breaker_failures += 1
                    if self.circuit_breaker_failures >= CIRCUIT_BREAKER_THRESHOLD:
                        self.circuit_breaker_open_until = datetime.utcnow() + timedelta(
                            seconds=CIRCUIT_BREAKER_TIMEOUT
                        )
                        logger.error("Circuit breaker opened due to repeated failures")

                    # Emit failure event
                    await self.event_store.append(Event(
                        event_id=str(uuid.uuid4()),
                        event_type=EventType.EXECUTION_FAILED,
                        correlation_id=order.correlation_id,
                        order_id=order.order_id,
                        timestamp=datetime.utcnow(),
                        payload={
                            "reason": order.rejection_reason,
                            "retry_attempts": order.retry_count
                        },
                        user_id=order.user_id
                    ))

    async def get_order(self, order_id: str) -> Optional[Order]:
        """Retrieve order by ID"""
        async with self._lock:
            return self.orders.get(order_id)

    async def get_all_orders(self) -> List[Order]:
        """Get all orders"""
        async with self._lock:
            return list(self.orders.values())

    @staticmethod
    def _generate_execution_key(request: OrderRequest, user_id: str) -> str:
        """Generate idempotency key from order parameters"""
        key_data = f"{user_id}:{request.symbol}:{request.side.value}:{request.quantity}:{request.price}:{request.client_order_id}"
        return hashlib.sha256(key_data.encode()).hexdigest()


# =============================================================================
# AUTHENTICATION & AUTHORIZATION (Control Plane Security)
# =============================================================================

class AuthManager:
    """
    JWT-based authentication with RBAC.
    Simulates institutional identity management.
    """

    def __init__(self):
        # Simulated user database (replace with real DB in production)
        self.users = {
            "trader1": {
                "password_hash": self._hash_password("trader123"),
                "role": UserRole.TRADER,
                "user_id": str(uuid.uuid4())
            },
            "risk1": {
                "password_hash": self._hash_password("risk123"),
                "role": UserRole.RISK_MANAGER,
                "user_id": str(uuid.uuid4())
            },
            "admin": {
                "password_hash": self._hash_password("admin123"),
                "role": UserRole.ADMIN,
                "user_id": str(uuid.uuid4())
            }
        }

    def authenticate(self, username: str, password: str) -> Optional[TokenResponse]:
        """Authenticate user and return JWT token"""
        user = self.users.get(username)
        if not user:
            return None

        if not self._verify_password(password, user["password_hash"]):
            return None

        # Generate JWT
        expires = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {
            "sub": username,
            "user_id": user["user_id"],
            "role": user["role"].value,
            "exp": expires
        }

        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT and return payload"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError:
            logger.warning("Invalid token")
            return None

    def check_permission(self, user_role: str, required_role: UserRole) -> bool:
        """Check if user has required permission"""
        role_hierarchy = {
            UserRole.TRADER: 1,
            UserRole.RISK_MANAGER: 2,
            UserRole.COMPLIANCE: 3,
            UserRole.ADMIN: 4
        }

        user_level = role_hierarchy.get(UserRole(user_role), 0)
        required_level = role_hierarchy.get(required_role, 0)

        return user_level >= required_level

    @staticmethod
    def _hash_password(password: str) -> str:
        """Hash password (simplified - use bcrypt in production)"""
        return hashlib.sha256(password.encode()).hexdigest()

    @staticmethod
    def _verify_password(password: str, password_hash: str) -> bool:
        """Verify password against hash"""
        return AuthManager._hash_password(password) == password_hash


# =============================================================================
# FASTAPI APPLICATION (Control Plane)
# =============================================================================

# Global instances
event_store = EventStore()
risk_engine = RiskEngine(event_store)
execution_engine = ExecutionEngine(event_store, risk_engine)
auth_manager = AuthManager()

# Security
security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> Dict[str, Any]:
    """Dependency for protected endpoints"""
    token = credentials.credentials
    payload = auth_manager.verify_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    return payload


def require_role(required_role: UserRole):
    """Dependency factory for role-based access control"""

    async def role_checker(
        current_user: Dict[str, Any] = Depends(get_current_user)
    ) -> Dict[str, Any]:
        user_role = current_user.get("role")
        if not auth_manager.check_permission(user_role, required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {required_role.value}"
            )
        return current_user

    return role_checker


# Application lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("ITIRP Control Plane starting...")
    logger.info("Event Store initialized")
    logger.info("Risk Engine initialized")
    logger.info("Execution Engine initialized")
    yield
    logger.info("ITIRP Control Plane shutting down...")


# FastAPI app
app = FastAPI(
    title="Institutional Trading Infrastructure & Risk Platform",
    description="Institutional-grade trading infrastructure with risk controls, audit trails, and observability",
    version="1.0.0",
    lifespan=lifespan
)

# CORS (configure appropriately for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# API ENDPOINTS
# =============================================================================

# --- Authentication ---

@app.post("/api/v1/auth/login", response_model=TokenResponse, tags=["Authentication"])
async def login(credentials: UserCredentials):
    """
    Authenticate user and receive JWT token.
    
    Default users:
    - trader1/trader123 (TRADER role)
    - risk1/risk123 (RISK_MANAGER role)
    - admin/admin123 (ADMIN role)
    """
    token_response = auth_manager.authenticate(credentials.username, credentials.password)

    if not token_response:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    return token_response


# --- Order Management (Data Plane Interface) ---

@app.post("/api/v1/orders", response_model=OrderResponse, tags=["Trading"])
async def submit_order(
        request: OrderRequest,
        current_user: Dict[str, Any] = Depends(require_role(UserRole.TRADER))
):
    """
    Submit order for execution.
    
    Order flow:
    1. Idempotency check
    2. Pre-trade risk validation
    3. Execution (async with retry)
    4. Position update
    
    All steps are audited in event store.
    """
    try:
        response = await execution_engine.submit_order(request, current_user["user_id"])
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Order submission failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Order submission failed"
        )


@app.get("/api/v1/orders/{order_id}", tags=["Trading"])
async def get_order(
        order_id: str,
        current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get order details by ID"""
    order = await execution_engine.get_order(order_id)

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    return {
        "order_id": order.order_id,
        "correlation_id": order.correlation_id,
        "symbol": order.symbol,
        "side": order.side.value,
        "quantity": order.quantity,
        "price": order.price,
        "status": order.status.value,
        "executed_quantity": order.executed_quantity,
        "executed_price": order.executed_price,
        "created_at": order.created_at.isoformat(),
        "rejection_reason": order.rejection_reason
    }


@app.get("/api/v1/orders", tags=["Trading"])
async def list_orders(
        current_user: Dict[str, Any] = Depends(get_current_user)
):
    """List all orders"""
    orders = await execution_engine.get_all_orders()

    return {
        "orders": [
            {
                "order_id": o.order_id,
                "symbol": o.symbol,
                "side": o.side.value,
                "quantity": o.quantity,
                "status": o.status.value,
                "created_at": o.created_at.isoformat()
            }
            for o in orders
        ],
        "total": len(orders)
    }


# --- Risk Management ---

@app.get("/api/v1/risk/metrics", response_model=RiskMetrics, tags=["Risk Management"])
async def get_risk_metrics(
        current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get current risk metrics and exposure"""
    return await risk_engine.get_metrics()


@app.get("/api/v1/risk/limits", response_model=RiskLimitsConfig, tags=["Risk Management"])
async def get_risk_limits(
        current_user: Dict[str, Any] = Depends(require_role(UserRole.RISK_MANAGER))
):
    """Get current risk limit configuration"""
    return risk_engine.config


@app.put("/api/v1/risk/limits", response_model=RiskLimitsConfig, tags=["Risk Management"])
async def update_risk_limits(
        config: RiskLimitsConfig,
        current_user: Dict[str, Any] = Depends(require_role(UserRole.RISK_MANAGER))
):
    """Update risk limit configuration (requires RISK_MANAGER role)"""
    risk_engine.config = config
    logger.info(f"Risk limits updated by {current_user['sub']}")
    return config


@app.post("/api/v1/risk/kill-switch", tags=["Risk Management"])
async def toggle_kill_switch(
        enabled: bool,
        current_user: Dict[str, Any] = Depends(require_role(UserRole.RISK_MANAGER))
):
    """
    Toggle kill switch (emergency halt of all trading).
    Requires RISK_MANAGER role.
    """
    risk_engine.config.kill_switch_enabled = enabled
    status_text = "activated" if enabled else "deactivated"
    logger.warning(f"Kill switch {status_text} by {current_user['sub']}")

    return {
        "kill_switch_enabled": enabled,
        "message": f"Kill switch {status_text}",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/v1/risk/positions", tags=["Risk Management"])
async def get_positions(
        current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get all current positions"""
    positions = risk_engine.positions

    return {
        "positions": [
            {
                "symbol": p.symbol,
                "quantity": p.quantity,
                "average_price": p.average_price,
                "market_value": p.quantity * p.average_price,
                "unrealized_pnl": 0.0  # Simplified
            }
            for p in positions.values()
        ],
        "total_positions": len(positions)
    }


# --- Audit & Compliance ---

@app.get("/api/v1/audit/events", tags=["Audit & Compliance"])
async def get_events(
        limit: int = 100,
        current_user: Dict[str, Any] = Depends(require_role(UserRole.COMPLIANCE))
):
    """
    Get recent events (requires COMPLIANCE role).
    Used for audit trail and regulatory reporting.
    """
    events = await event_store.get_all_events(limit=limit)
    return {
        "events": events,
        "total": len(events)
    }


@app.get("/api/v1/audit/correlation/{correlation_id}", tags=["Audit & Compliance"])
async def get_correlation_trail(
        correlation_id: str,
        current_user: Dict[str, Any] = Depends(require_role(UserRole.COMPLIANCE))
):
    """
    Replay complete event chain for correlation ID.
    Enables deterministic reconstruction of order lifecycle.
    """
    events = await event_store.replay(correlation_id)

    if not events:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No events found for correlation ID"
        )

    return {
        "correlation_id": correlation_id,
        "events": events,
        "total_events": len(events)
    }


@app.get("/api/v1/audit/order/{order_id}/trail", tags=["Audit & Compliance"])
async def get_order_trail(
        order_id: str,
        current_user: Dict[str, Any] = Depends(require_role(UserRole.COMPLIANCE))
):
    """Get complete audit trail for specific order"""
    events = await event_store.get_by_order(order_id)

    if not events:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No events found for order ID"
        )

    return {
        "order_id": order_id,
        "events": [e.to_dict() for e in events],
        "total_events": len(events)
    }


# --- System Health & Observability ---

@app.get("/api/v1/health", tags=["System"])
async def health_check():
    """System health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "event_store": "operational",
            "risk_engine": "operational",
            "execution_engine": "operational"
        }
    }


@app.get("/api/v1/metrics", tags=["System"])
async def system_metrics(
        current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get system-wide metrics for observability.
    Includes order counts, event counts, circuit breaker status.
    """
    orders = await execution_engine.get_all_orders()
    events = await event_store.get_all_events(limit=1000)

    order_status_counts = defaultdict(int)
    for order in orders:
        order_status_counts[order.status.value] += 1

    circuit_breaker_status = "closed"
    if execution_engine.circuit_breaker_open_until:
        if datetime.utcnow() < execution_engine.circuit_breaker_open_until:
            circuit_breaker_status = "open"

    return {
        "total_orders": len(orders),
        "total_events": len(events),
        "order_status_breakdown": dict(order_status_counts),
        "circuit_breaker": {
            "status": circuit_breaker_status,
            "failures": execution_engine.circuit_breaker_failures,
            "open_until": execution_engine.circuit_breaker_open_until.isoformat()
            if execution_engine.circuit_breaker_open_until else None
        },
        "risk_metrics": await risk_engine.get_metrics(),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/", tags=["System"])
async def root():
    """API root - system information"""
    return {
        "system": "Institutional Trading Infrastructure & Risk Platform (ITIRP)",
        "version": "1.0.0",
        "status": "operational",
        "documentation": "/docs",
        "architecture": {
            "control_plane": "FastAPI + JWT + RBAC",
            "data_plane": "Event-Driven Execution + Pre-Trade Risk",
            "audit": "Event Sourcing with Complete Trail",
            "resilience": "Retry Logic + Circuit Breakers + Idempotency"
        },
        "endpoints": {
            "auth": "/api/v1/auth/login",
            "trading": "/api/v1/orders",
            "risk": "/api/v1/risk/*",
            "audit": "/api/v1/audit/*",
            "health": "/api/v1/health"
        }
    }


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    print("""
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║                                                                          ║
    ║      Institutional Trading Infrastructure & Risk Platform (ITIRP)       ║
    ║                                                                          ║
    ║  Enterprise-grade trading infrastructure demonstrating:                 ║
    ║  • Control Plane / Data Plane separation                                ║
    ║  • Pre-trade risk controls with institutional limits                    ║
    ║  • Complete event sourcing and audit trails                             ║
    ║  • Resilience patterns (retry, circuit breaker, idempotency)            ║
    ║  • JWT authentication with RBAC                                         ║
    ║  • Observability and metrics                                            ║
    ║                                                                          ║
    ║  API Documentation: http://localhost:8000/docs                          ║
    ║                                                                          ║
    ║  Default Users:                                                         ║
    ║  • trader1/trader123 (TRADER role)                                      ║
    ║  • risk1/risk123 (RISK_MANAGER role)                                    ║
    ║  • admin/admin123 (ADMIN role)                                          ║
    ║                                                                          ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "itirp_complete:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )