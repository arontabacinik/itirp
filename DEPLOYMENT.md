# Production Deployment Guide

## Overview

This guide covers deploying ITIRP to production environments with considerations for:
- Containerization (Docker)
- Orchestration (Kubernetes)
- Persistence (PostgreSQL, Redis)
- Message queues (Kafka)
- Monitoring & observability
- Security hardening
- High availability

---

## Quick Start (Development)

### Prerequisites

```bash
# Python 3.11+
python --version

# Install dependencies
pip install fastapi uvicorn pyjwt python-multipart --break-system-packages
```

### Run Locally

```bash
# Start the system
python itirp_complete.py

# In another terminal, run tests
python test_itirp.py

# Or run interactive demo
python demo_itirp.py
```

---

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    fastapi==0.109.0 \
    uvicorn[standard]==0.27.0 \
    pyjwt==2.8.0 \
    python-multipart==0.0.6

# Copy application
COPY itirp_complete.py .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/api/v1/health', timeout=2)"

# Run application
CMD ["python", "itirp_complete.py"]
```

### Build and Run

```bash
# Build image
docker build -t itirp:latest .

# Run container
docker run -d \
  --name itirp \
  -p 8000:8000 \
  --env SECRET_KEY="change-me-in-production" \
  --restart unless-stopped \
  itirp:latest

# Check logs
docker logs -f itirp

# Check health
curl http://localhost:8000/api/v1/health
```

### Docker Compose (Development Stack)

```yaml
# docker-compose.yml
version: '3.8'

services:
  itirp:
    build: .
    ports:
      - "8000:8000"
    environment:
      - SECRET_KEY=${SECRET_KEY:-dev-secret-key}
      - POSTGRES_URL=postgresql://itirp:password@postgres:5432/itirp
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - postgres
      - redis
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 3s
      retries: 3
  
  postgres:
    image: timescale/timescaledb:latest-pg15
    environment:
      - POSTGRES_DB=itirp
      - POSTGRES_USER=itirp
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
  
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
  
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
  
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana

volumes:
  postgres_data:
  redis_data:
  prometheus_data:
  grafana_data:
```

```bash
# Start stack
docker-compose up -d

# View logs
docker-compose logs -f itirp

# Stop stack
docker-compose down
```

---

## Kubernetes Deployment

### Namespace

```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: itirp-production
```

### ConfigMap

```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: itirp-config
  namespace: itirp-production
data:
  POSTGRES_URL: "postgresql://itirp:password@postgres-service:5432/itirp"
  REDIS_URL: "redis://redis-service:6379/0"
  LOG_LEVEL: "INFO"
```

### Secret

```yaml
# secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: itirp-secrets
  namespace: itirp-production
type: Opaque
stringData:
  SECRET_KEY: "production-secret-key-change-me"
  POSTGRES_PASSWORD: "secure-postgres-password"
```

### Deployment

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: itirp-api
  namespace: itirp-production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: itirp-api
  template:
    metadata:
      labels:
        app: itirp-api
    spec:
      containers:
      - name: itirp
        image: itirp:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 8000
        env:
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: itirp-secrets
              key: SECRET_KEY
        - name: POSTGRES_URL
          valueFrom:
            configMapKeyRef:
              name: itirp-config
              key: POSTGRES_URL
        - name: REDIS_URL
          valueFrom:
            configMapKeyRef:
              name: itirp-config
              key: REDIS_URL
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /api/v1/health
            port: 8000
          initialDelaySeconds: 15
          periodSeconds: 20
        readinessProbe:
          httpGet:
            path: /api/v1/health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
```

### Service

```yaml
# service.yaml
apiVersion: v1
kind: Service
metadata:
  name: itirp-service
  namespace: itirp-production
spec:
  selector:
    app: itirp-api
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: ClusterIP
```

### Ingress

```yaml
# ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: itirp-ingress
  namespace: itirp-production
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - itirp.yourdomain.com
    secretName: itirp-tls
  rules:
  - host: itirp.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: itirp-service
            port:
              number: 80
```

### Horizontal Pod Autoscaler

```yaml
# hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: itirp-hpa
  namespace: itirp-production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: itirp-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### Deploy to Kubernetes

```bash
# Create namespace
kubectl apply -f namespace.yaml

# Create ConfigMap and Secrets
kubectl apply -f configmap.yaml
kubectl apply -f secret.yaml

# Deploy application
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml
kubectl apply -f hpa.yaml

# Check deployment
kubectl get pods -n itirp-production
kubectl get svc -n itirp-production
kubectl get ingress -n itirp-production

# View logs
kubectl logs -f -n itirp-production -l app=itirp-api

# Scale manually
kubectl scale deployment itirp-api --replicas=5 -n itirp-production
```

---

## Production Considerations

### 1. Database (PostgreSQL)

**Event Store Schema:**

```sql
-- events table (event sourcing)
CREATE TABLE events (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    correlation_id UUID NOT NULL,
    order_id UUID NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    user_id VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_events_correlation ON events(correlation_id);
CREATE INDEX idx_events_order ON events(order_id);
CREATE INDEX idx_events_timestamp ON events(timestamp DESC);
CREATE INDEX idx_events_type ON events(event_type);

-- Orders table (materialized view)
CREATE TABLE orders (
    order_id UUID PRIMARY KEY,
    correlation_id UUID NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(20,8) NOT NULL,
    price DECIMAL(20,8) NOT NULL,
    status VARCHAR(20) NOT NULL,
    user_id VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_orders_user ON orders(user_id);
CREATE INDEX idx_orders_symbol ON orders(symbol);
CREATE INDEX idx_orders_status ON orders(status);

-- Positions table
CREATE TABLE positions (
    symbol VARCHAR(20) PRIMARY KEY,
    quantity DECIMAL(20,8) NOT NULL,
    average_price DECIMAL(20,8) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- TimescaleDB hypertable for time-series data
SELECT create_hypertable('events', 'timestamp');
```

**Connection Pooling:**

```python
import asyncpg

pool = await asyncpg.create_pool(
    dsn=DATABASE_URL,
    min_size=10,
    max_size=50,
    command_timeout=60
)
```

### 2. Caching (Redis)

**Use Cases:**
- Position cache
- Risk metrics cache
- Rate limiting
- Session storage

**Implementation:**

```python
import redis.asyncio as redis

redis_client = await redis.from_url(
    REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
    max_connections=50
)

# Cache positions
await redis_client.setex(
    f"position:{symbol}",
    300,  # 5 minute TTL
    json.dumps(position)
)

# Get cached position
cached = await redis_client.get(f"position:{symbol}")
```

### 3. Message Queue (Kafka)

**Topics:**
- `orders.created`
- `orders.executed`
- `risk.violations`
- `audit.events`

**Producer:**

```python
from aiokafka import AIOKafkaProducer

producer = AIOKafkaProducer(
    bootstrap_servers='kafka:9092',
    value_serializer=lambda v: json.dumps(v).encode()
)

await producer.send(
    'orders.created',
    value={
        'order_id': order.order_id,
        'timestamp': datetime.utcnow().isoformat()
    }
)
```

**Consumer:**

```python
from aiokafka import AIOKafkaConsumer

consumer = AIOKafkaConsumer(
    'orders.created',
    bootstrap_servers='kafka:9092',
    group_id='risk-engine',
    value_deserializer=lambda v: json.loads(v.decode())
)

async for msg in consumer:
    await process_order(msg.value)
```

### 4. Monitoring

**Prometheus Metrics:**

```python
from prometheus_client import Counter, Histogram, Gauge

# Counters
orders_total = Counter('orders_total', 'Total orders submitted')
orders_executed = Counter('orders_executed', 'Orders executed')
orders_rejected = Counter('orders_rejected', 'Orders rejected')

# Histograms
order_latency = Histogram('order_latency_seconds', 'Order processing latency')

# Gauges
active_positions = Gauge('active_positions', 'Number of active positions')
net_exposure = Gauge('net_exposure_usd', 'Net exposure in USD')
```

**Grafana Dashboards:**

```json
{
  "dashboard": {
    "title": "ITIRP Trading Dashboard",
    "panels": [
      {
        "title": "Order Rate",
        "targets": [
          {
            "expr": "rate(orders_total[5m])"
          }
        ]
      },
      {
        "title": "Success Rate",
        "targets": [
          {
            "expr": "rate(orders_executed[5m]) / rate(orders_total[5m])"
          }
        ]
      },
      {
        "title": "Net Exposure",
        "targets": [
          {
            "expr": "net_exposure_usd"
          }
        ]
      }
    ]
  }
}
```

### 5. Security Hardening

**Environment Variables:**

```bash
# .env (never commit to git)
SECRET_KEY=<256-bit-random-key>
POSTGRES_PASSWORD=<secure-password>
ALLOWED_ORIGINS=https://yourdomain.com
RATE_LIMIT_PER_MINUTE=100
```

**TLS/SSL:**

```python
# For production
uvicorn.run(
    app,
    host="0.0.0.0",
    port=8000,
    ssl_keyfile="/path/to/key.pem",
    ssl_certfile="/path/to/cert.pem"
)
```

**Rate Limiting:**

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/api/v1/orders")
@limiter.limit("10/minute")
async def submit_order(...):
    ...
```

### 6. Backup & Recovery

**Database Backups:**

```bash
# Daily backup script
#!/bin/bash
BACKUP_DIR=/backups
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

pg_dump -h postgres -U itirp itirp > $BACKUP_DIR/itirp_$TIMESTAMP.sql
gzip $BACKUP_DIR/itirp_$TIMESTAMP.sql

# Upload to S3
aws s3 cp $BACKUP_DIR/itirp_$TIMESTAMP.sql.gz s3://backups/itirp/

# Retention: keep 30 days
find $BACKUP_DIR -name "itirp_*.sql.gz" -mtime +30 -delete
```

**Disaster Recovery:**

```bash
# Restore from backup
gunzip itirp_20260130_120000.sql.gz
psql -h postgres -U itirp itirp < itirp_20260130_120000.sql

# Event replay (rebuild state)
python rebuild_state.py --from-events
```

---

## Performance Tuning

### 1. Database Optimization

```sql
-- Connection pooling
ALTER SYSTEM SET max_connections = 200;

-- Query performance
ALTER SYSTEM SET shared_buffers = '4GB';
ALTER SYSTEM SET effective_cache_size = '12GB';
ALTER SYSTEM SET work_mem = '64MB';
ALTER SYSTEM SET maintenance_work_mem = '1GB';

-- Write-ahead log
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
```

### 2. Application Tuning

```python
# Worker configuration
uvicorn.run(
    app,
    host="0.0.0.0",
    port=8000,
    workers=4,  # Number of CPU cores
    loop="uvloop",  # Faster event loop
    http="httptools",  # Faster HTTP parser
    access_log=False  # Disable in production
)
```

### 3. Caching Strategy

```python
# Multi-layer cache
from functools import lru_cache

# L1: In-memory LRU cache
@lru_cache(maxsize=1000)
def get_risk_config():
    return load_risk_config()

# L2: Redis cache
async def get_position(symbol: str):
    # Try cache first
    cached = await redis.get(f"position:{symbol}")
    if cached:
        return json.loads(cached)
    
    # Cache miss - load from DB
    position = await db.fetch_position(symbol)
    await redis.setex(f"position:{symbol}", 300, json.dumps(position))
    return position
```

---

## High Availability Architecture

```
                    ┌─────────────────┐
                    │   CloudFlare    │
                    │  (DDoS, CDN)    │
                    └─────────────────┘
                            │
                    ┌─────────────────┐
                    │  Load Balancer  │
                    │   (HAProxy)     │
                    └─────────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
    ┌──────────┐      ┌──────────┐      ┌──────────┐
    │  API-1   │      │  API-2   │      │  API-3   │
    │ (Zone A) │      │ (Zone B) │      │ (Zone C) │
    └──────────┘      └──────────┘      └──────────┘
          │                 │                 │
          └─────────────────┼─────────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
    ┌──────────┐      ┌──────────┐      ┌──────────┐
    │  Exec-1  │      │  Exec-2  │      │  Exec-3  │
    │ (Zone A) │      │ (Zone B) │      │ (Zone C) │
    └──────────┘      └──────────┘      └──────────┘
          │                 │                 │
          └─────────────────┼─────────────────┘
                            │
          ┌─────────────────┴─────────────────┐
          ▼                                   ▼
    ┌──────────────┐                  ┌──────────────┐
    │  PostgreSQL  │◄────replication──┤  PostgreSQL  │
    │   Primary    │                  │   Standby    │
    │  (Zone A)    │                  │  (Zone B)    │
    └──────────────┘                  └──────────────┘
          │
          ▼
    ┌──────────────┐
    │ Redis Cluster│
    │   (Zones)    │
    └──────────────┘
```

**Features:**
- Multi-AZ deployment
- Auto-failover
- Data replication
- Zero-downtime deployments

---

## Cost Optimization

### AWS Pricing (Example)

**Compute (EKS):**
- 3x t3.large instances: ~$150/month
- 3x execution engines: ~$200/month

**Database:**
- RDS PostgreSQL (db.r5.large): ~$300/month
- ElastiCache Redis (cache.r5.large): ~$200/month

**Networking:**
- Load Balancer: ~$20/month
- Data transfer: ~$50/month

**Storage:**
- S3 backups: ~$20/month

**Total: ~$940/month**

### Cost Reduction Strategies:

1. **Reserved Instances**: Save 30-40%
2. **Spot Instances**: For non-critical workloads
3. **Auto-scaling**: Scale down during low traffic
4. **Data compression**: Reduce storage costs
5. **CloudFront CDN**: Reduce origin load

---

## Compliance Checklist

- [ ] TLS 1.3 for all connections
- [ ] JWT tokens with short expiration
- [ ] RBAC enforced on all endpoints
- [ ] Audit logging enabled
- [ ] Data encryption at rest
- [ ] Regular security audits
- [ ] Penetration testing
- [ ] Disaster recovery plan
- [ ] Backup verification
- [ ] Incident response plan
- [ ] GDPR compliance (if EU)
- [ ] SOC 2 compliance
- [ ] PCI DSS (if handling payments)

---

## Migration from Single-File

### Step 1: Extract Components

```
itirp/
├── api/
│   ├── __init__.py
│   ├── auth.py
│   ├── orders.py
│   └── risk.py
├── core/
│   ├── __init__.py
│   ├── models.py
│   └── config.py
├── engines/
│   ├── __init__.py
│   ├── execution.py
│   └── risk.py
├── storage/
│   ├── __init__.py
│   ├── events.py
│   └── database.py
└── main.py
```

### Step 2: Add Persistence

```python
# storage/database.py
import asyncpg

class DatabaseEventStore:
    async def append(self, event: Event):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO events (event_id, event_type, correlation_id, ...)
                VALUES ($1, $2, $3, ...)
            """, event.event_id, event.event_type, ...)
```

### Step 3: Add Message Queue

```python
# engines/execution.py
from aiokafka import AIOKafkaProducer

class ExecutionEngine:
    async def execute_order(self, order):
        # Execute
        result = await self._execute(order)
        
        # Publish event
        await self.kafka_producer.send(
            'orders.executed',
            value={'order_id': order.order_id, ...}
        )
```

---

## Conclusion

This guide provides a roadmap for taking ITIRP from a single-file demo to a production-grade, highly available system capable of handling institutional trading workloads.

**Key Production Requirements:**
1. Persistent storage (PostgreSQL)
2. Distributed caching (Redis)
3. Message queuing (Kafka)
4. Container orchestration (Kubernetes)
5. Monitoring & alerting (Prometheus/Grafana)
6. Security hardening (TLS, RBAC, rate limiting)
7. High availability (multi-AZ, auto-failover)
8. Disaster recovery (backups, replay)

The single-file implementation demonstrates all core concepts, while production deployment adds the infrastructure needed for scale, reliability, and compliance.