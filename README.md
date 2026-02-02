# Institutional Trading Infrastructure & Risk Platform (ITIRP)

## 🏦 Visão Geral

O **ITIRP** é uma plataforma institucional completa de infraestrutura de trading, risco e auditoria, implementada em **um único arquivo Python** para fins educacionais e demonstração de arquitetura.

Este sistema demonstra como **bancos de investimento e instituições financeiras** constroem infraestruturas críticas de trading com:

- ✅ **Controles pré-trade rigorosos**
- ✅ **Event sourcing completo** (auditoria total)
- ✅ **Separação Control Plane / Data Plane**
- ✅ **Resiliência operacional** (retry, circuit breaker, idempotency)
- ✅ **Autenticação JWT com RBAC**
- ✅ **Observabilidade e métricas**

---

## 🏗️ Arquitetura

### Control Plane vs Data Plane

```
┌─────────────────────────────────────────────────────────────────┐
│                        CONTROL PLANE                            │
│  • Autenticação (JWT)                                           │
│  • Autorização (RBAC)                                           │
│  • Configuração de políticas                                    │
│  • Gestão de limites de risco                                   │
│  • API REST (FastAPI)                                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         DATA PLANE                              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐ │
│  │ Execution Engine │  │   Risk Engine    │  │  Event Store  │ │
│  │  • Retry Logic   │  │  • Pre-trade     │  │  • Sourcing   │ │
│  │  • Circuit Break │  │  • Limit Check   │  │  • Audit      │ │
│  │  • Idempotency   │  │  • Kill Switch   │  │  • Replay     │ │
│  └──────────────────┘  └──────────────────┘  └───────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Componentes Principais

#### 1. **Event Store** (Event Sourcing)
- Toda mudança de estado é um evento imutável
- Correlation IDs para rastreamento end-to-end
- Replay determinístico para auditoria
- Compliance e relatórios regulatórios

#### 2. **Risk Engine** (Pre-Trade Controls)
- Validação de limites antes da execução:
  - Position size limits
  - Daily volume limits
  - Net exposure limits
  - Gross exposure limits
- Kill switch global (halt de emergência)
- Gestão de posições em tempo real

#### 3. **Execution Engine**
- Processamento assíncrono de ordens
- Retry com exponential backoff
- Circuit breaker para proteção sistêmica
- Idempotency (previne duplicação)
- Simulação de execução no mercado

#### 4. **Authentication & Authorization**
- JWT tokens com expiração
- Role-Based Access Control (RBAC):
  - `TRADER`: Submete ordens
  - `RISK_MANAGER`: Configura limites
  - `COMPLIANCE`: Acesso a auditorias
  - `ADMIN`: Acesso total

---

## 📋 Pré-requisitos

```bash
# Python 3.11+
python --version

# Instalar dependências
pip install fastapi uvicorn pyjwt --break-system-packages
```

---

## 🚀 Como Executar

### 1. Executar o sistema

```bash
python itirp_complete.py
```

O sistema estará disponível em:
- **API**: http://localhost:8000
- **Documentação interativa**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/api/v1/health

### 2. Autenticar

#### Usuários padrão:

| Username | Password   | Role          | Permissões                     |
|----------|------------|---------------|--------------------------------|
| trader1  | trader123  | TRADER        | Submeter ordens                |
| risk1    | risk123    | RISK_MANAGER  | Configurar limites, kill switch|
| admin    | admin123   | ADMIN         | Acesso total                   |

#### Obter token JWT:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "trader1", "password": "trader123"}'
```

**Resposta:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

**Use o token em todas as requisições:**
```bash
export TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

## 📊 Fluxo Completo de Ordem

### 1. Submeter ordem

```bash
curl -X POST http://localhost:8000/api/v1/orders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "side": "BUY",
    "quantity": 100,
    "price": 150.50,
    "strategy": "momentum"
  }'
```

**Resposta:**
```json
{
  "order_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "APPROVED",
  "correlation_id": "660e8400-e29b-41d4-a716-446655440001",
  "timestamp": "2026-01-30T14:30:00.123456",
  "message": "Order approved and submitted for execution"
}
```

### 2. Pipeline de processamento

```
PENDING → RISK_CHECK → APPROVED → EXECUTING → EXECUTED
                          ↓
                      REJECTED (se falhar risk check)
```

### 3. Verificar status da ordem

```bash
curl http://localhost:8000/api/v1/orders/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $TOKEN"
```

### 4. Ver audit trail completo

```bash
# Por correlation ID (todas as ordens relacionadas)
curl http://localhost:8000/api/v1/audit/correlation/660e8400-e29b-41d4-a716-446655440001 \
  -H "Authorization: Bearer $TOKEN"

# Por order ID específico
curl http://localhost:8000/api/v1/audit/order/550e8400-e29b-41d4-a716-446655440000/trail \
  -H "Authorization: Bearer $TOKEN"
```

**Eventos gerados:**
```
ORDER_CREATED → RISK_CHECK_STARTED → RISK_CHECK_PASSED → 
EXECUTION_STARTED → EXECUTION_COMPLETED
```

---

## 🛡️ Gestão de Risco

### Ver métricas de risco

```bash
curl http://localhost:8000/api/v1/risk/metrics \
  -H "Authorization: Bearer $TOKEN"
```

**Resposta:**
```json
{
  "net_exposure": 150500.00,
  "gross_exposure": 150500.00,
  "daily_volume": 450000.00,
  "total_positions": 3,
  "largest_position": 150500.00,
  "kill_switch_active": false
}
```

### Configurar limites de risco

```bash
# Login como risk manager
export RISK_TOKEN="..." # Token do risk1

curl -X PUT http://localhost:8000/api/v1/risk/limits \
  -H "Authorization: Bearer $RISK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "max_position_size": 500000,
    "max_daily_volume": 5000000,
    "max_net_exposure": 2000000,
    "max_gross_exposure": 10000000,
    "kill_switch_enabled": false
  }'
```

### Ativar kill switch (emergência)

```bash
curl -X POST "http://localhost:8000/api/v1/risk/kill-switch?enabled=true" \
  -H "Authorization: Bearer $RISK_TOKEN"
```

**Quando ativado:**
- ❌ Todas as novas ordens são rejeitadas imediatamente
- ✅ Ordens em execução completam normalmente
- 📋 Evento é registrado no audit trail

### Ver posições atuais

```bash
curl http://localhost:8000/api/v1/risk/positions \
  -H "Authorization: Bearer $TOKEN"
```

---

## 📈 Observabilidade

### System metrics

```bash
curl http://localhost:8000/api/v1/metrics \
  -H "Authorization: Bearer $TOKEN"
```

**Resposta:**
```json
{
  "total_orders": 15,
  "total_events": 75,
  "order_status_breakdown": {
    "EXECUTED": 12,
    "REJECTED": 2,
    "EXECUTING": 1
  },
  "circuit_breaker": {
    "status": "closed",
    "failures": 0,
    "open_until": null
  },
  "risk_metrics": { ... },
  "timestamp": "2026-01-30T14:35:00.123456"
}
```

### Circuit Breaker

O circuit breaker abre automaticamente após **5 falhas consecutivas** de execução:
- Status: `open` (bloqueando) ou `closed` (normal)
- Timeout: 60 segundos (reabre automaticamente após)
- Previne cascata de falhas

---

## 🔐 Segurança

### Segregação de funções (RBAC)

| Endpoint                        | TRADER | RISK_MGR | COMPLIANCE | ADMIN |
|---------------------------------|--------|----------|------------|-------|
| POST /api/v1/orders             | ✅     | ✅       | ✅         | ✅    |
| GET /api/v1/orders              | ✅     | ✅       | ✅         | ✅    |
| PUT /api/v1/risk/limits         | ❌     | ✅       | ✅         | ✅    |
| POST /api/v1/risk/kill-switch   | ❌     | ✅       | ✅         | ✅    |
| GET /api/v1/audit/*             | ❌     | ❌       | ✅         | ✅    |

### Token JWT

- Expiração: 30 minutos
- Algoritmo: HS256
- Payload: `{sub, user_id, role, exp}`

---

## 🧪 Casos de Teste

### 1. Order rejection por limite de posição

```bash
# Ordem muito grande (excede max_position_size)
curl -X POST http://localhost:8000/api/v1/orders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "TSLA",
    "side": "BUY",
    "quantity": 100000,
    "price": 200
  }'
```

**Resposta:**
```json
{
  "order_id": "...",
  "status": "REJECTED",
  "message": "Risk violations: POSITION_LIMIT"
}
```

### 2. Kill switch ativo

```bash
# 1. Ativar kill switch
curl -X POST "http://localhost:8000/api/v1/risk/kill-switch?enabled=true" \
  -H "Authorization: Bearer $RISK_TOKEN"

# 2. Tentar submeter ordem
curl -X POST http://localhost:8000/api/v1/orders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "side": "BUY", "quantity": 10, "price": 150}'
```

**Resposta:**
```json
{
  "order_id": "...",
  "status": "REJECTED",
  "message": "Risk violations: KILL_SWITCH_ACTIVE"
}
```

### 3. Idempotency (prevenção de duplicatas)

```bash
# Submeter a mesma ordem 2x
curl -X POST http://localhost:8000/api/v1/orders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "side": "BUY",
    "quantity": 100,
    "price": 150,
    "client_order_id": "unique-123"
  }'

# Segunda chamada retorna erro 409
```

### 4. Replay de eventos (auditoria)

```bash
# 1. Submeter ordem e pegar correlation_id
ORDER_RESP=$(curl -X POST http://localhost:8000/api/v1/orders ...)
CORRELATION_ID=$(echo $ORDER_RESP | jq -r .correlation_id)

# 2. Replay completo
curl http://localhost:8000/api/v1/audit/correlation/$CORRELATION_ID \
  -H "Authorization: Bearer $TOKEN"
```

---

## 🏛️ Padrões Institucionais Implementados

### 1. Event Sourcing
- ✅ Estado reconstruído de eventos
- ✅ Auditoria completa e imutável
- ✅ Replay determinístico
- ✅ Compliance regulatório

### 2. Pre-Trade Risk
- ✅ Validação antes da execução
- ✅ Múltiplos níveis de limite
- ✅ Kill switch global
- ✅ Position tracking em tempo real

### 3. Resilience Patterns
- ✅ **Retry**: 3 tentativas com exponential backoff
- ✅ **Circuit Breaker**: Proteção contra cascata de falhas
- ✅ **Idempotency**: Prevenção de duplicatas
- ✅ **Timeouts**: Proteção contra hang

### 4. Observability
- ✅ Structured logging
- ✅ Correlation IDs (distributed tracing)
- ✅ Metrics aggregation
- ✅ Health checks

### 5. Security
- ✅ JWT authentication
- ✅ RBAC (role-based access control)
- ✅ Least privilege principle
- ✅ Segregation of duties

---

## 📚 Endpoints Completos

### Authentication
- `POST /api/v1/auth/login` - Login e obtenção de JWT

### Trading
- `POST /api/v1/orders` - Submeter ordem
- `GET /api/v1/orders/{order_id}` - Detalhes da ordem
- `GET /api/v1/orders` - Listar todas as ordens

### Risk Management
- `GET /api/v1/risk/metrics` - Métricas de risco atuais
- `GET /api/v1/risk/limits` - Ver limites configurados
- `PUT /api/v1/risk/limits` - Atualizar limites (RISK_MGR+)
- `POST /api/v1/risk/kill-switch` - Toggle kill switch (RISK_MGR+)
- `GET /api/v1/risk/positions` - Ver posições atuais

### Audit & Compliance
- `GET /api/v1/audit/events` - Eventos recentes (COMPLIANCE+)
- `GET /api/v1/audit/correlation/{id}` - Replay por correlation (COMPLIANCE+)
- `GET /api/v1/audit/order/{id}/trail` - Trail de ordem específica (COMPLIANCE+)

### System
- `GET /api/v1/health` - Health check
- `GET /api/v1/metrics` - System metrics
- `GET /` - System info

---

## 🎯 Objetivos Demonstrados

Este projeto demonstra capacidade de:

1. **Arquitetura institucional**: Separação control/data plane
2. **Risk management**: Controles pré-trade rigorosos
3. **Auditabilidade**: Event sourcing completo
4. **Resiliência**: Retry, circuit breaker, idempotency
5. **Segurança**: JWT + RBAC
6. **Observabilidade**: Logs, metrics, tracing
7. **Código limpo**: Type hints, documentação, patterns

---

## 🔄 Próximos Passos (Roadmap Institucional)

### Fase 2: Persistência
- PostgreSQL para event store
- Redis para cache de posições
- TimescaleDB para metrics

### Fase 3: Escalabilidade
- Kafka/RabbitMQ para event streaming
- Horizontal scaling de engines
- Load balancing

### Fase 4: Advanced Risk
- VaR (Value at Risk)
- Stress testing automatizado
- Scenario analysis
- Monte Carlo simulations

### Fase 5: Compliance
- Regulatory reporting (MiFID II, Dodd-Frank)
- Trade reconstruction
- Best execution analysis

### Fase 6: Resilience
- Multi-region deployment
- Disaster recovery
- Chaos engineering
- Zero-downtime deployments

---

## 📖 Referências

Este projeto implementa padrões descritos em:

- **"Building Microservices"** - Sam Newman
- **"Site Reliability Engineering"** - Google
- **"Release It!"** - Michael Nygard
- **"Enterprise Integration Patterns"** - Gregor Hohpe

E reflete práticas de:
- Goldman Sachs (SecDB)
- Morgan Stanley (Matrix)
- Jane Street (OCaml trading systems)
- Two Sigma (Venn platform)

---

## 📄 Licença

MIT License - Uso educacional e demonstração de arquitetura

---

## 👨‍💻 Contato

Este é um projeto de demonstração de arquitetura institucional.

**Características:**
- ✅ Production-grade architecture
- ✅ Institutional patterns
- ✅ Complete observability
- ✅ Regulatory compliance ready
- ✅ Battle-tested resilience patterns

**Ideal para:**
- Entrevistas técnicas (Staff/Principal Engineer)
- Demonstração de system design
- Referência de arquitetura
- Treinamento de engenheiros