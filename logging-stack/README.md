# Logging Stack Setup

Hệ thống logging thu thập log từ các service và hiển thị trên Grafana.

## Kiến trúc

```
┌─────────────────────┐     ┌─────────────────────┐
│  dangbaitudong-api  │     │ ChatbotMobileStore  │
│                     │     │                     │
│   logs/app.log      │     │   logs/app.log      │
└─────────┬───────────┘     └─────────┬───────────┘
          │                           │
          │    (Docker Volume)        │
          ▼                           ▼
┌─────────────────────────────────────────────────┐
│                   Filebeat                       │
│   Thu thập log JSON từ các file                 │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│               Elasticsearch                      │
│   Index: app-logs-YYYY.MM.DD                    │
└─────────────────────┬───────────────────────────┘
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│     Grafana     │     │     Kibana      │
│   Port: 3000    │     │   Port: 5601    │
└─────────────────┘     └─────────────────┘
```

## Yêu cầu

- Docker & Docker Compose v2+
- Các service chạy trên cùng Docker network (`shared_datanet`)

## Cách chạy

### 1. Tạo Docker volume cho log (chạy 1 lần)

```bash
docker volume create dangbaitudong_logs
```

### 2. Khởi động logging stack (trên máy chạy ChatbotMobileStore)

```bash
cd /path/to/ChatbotMobileStore
docker-compose up -d elasticsearch kibana filebeat grafana
```

### 3. Cấu hình service để ghi log

#### ChatbotMobileStore

Đặt biến môi trường:
```bash
export LOG_DIR=./logs
export SERVICE_NAME=chatbotmobilestore-api
```

Hoặc trong `.env`:
```env
LOG_DIR=./logs
SERVICE_NAME=chatbotmobilestore-api
```

#### dangbaitudong

Đặt biến môi trường:
```bash
export LOG_DIR=./logs
export SERVICE_NAME=dangbaitudong-api
```

Nếu chạy trong Docker, mount volume:
```yaml
volumes:
  - dangbaitudong_logs:/app/logs
environment:
  - LOG_DIR=/app/logs
```

### 4. Truy cập Dashboard

- **Grafana**: http://localhost:3000
  - Username: `admin`
  - Password: `admin123`
  - Dashboard: "Application Logs Dashboard"

- **Kibana**: http://localhost:5601
  - Index pattern: `app-logs-*`

## Cấu trúc Log JSON

Mỗi dòng log là 1 JSON object:

```json
{
  "@timestamp": "2024-01-15T10:30:00.123456Z",
  "log.level": "ERROR",
  "service.name": "chatbotmobilestore-api",
  "trace.id": "abc123def456",
  "event.category": "chatbot",
  "event.action": "chatbot.chat",
  "source.layer": "controller",
  "source.controller": "chat_routes",
  "source.function": "chat",
  "error.type": "ValueError",
  "error.code": "INVALID_INPUT",
  "error.ref_id": "A1B2C3D4",
  "error.message": "Bạn chưa thêm API key",
  "http.status_code": 400,
  "request.method": "POST",
  "request.path": "/chat/thread-123"
}
```

## Query mẫu trong Grafana/Kibana

### Tìm tất cả lỗi của 1 service
```
service.name:"chatbotmobilestore-api" AND log.level:ERROR
```

### Truy vết theo trace.id
```
trace.id:"abc123def456"
```

### Tìm lỗi theo error.ref_id (để support khách hàng)
```
error.ref_id:"A1B2C3D4"
```

### Lỗi theo category
```
event.category:"chatbot" AND log.level:ERROR
```

### Lỗi trong 1 giờ qua
```
log.level:ERROR AND @timestamp:[now-1h TO now]
```

## Kết nối từ máy khác (cùng network)

Nếu `dangbaitudong` chạy trên máy khác nhưng cùng Docker network:

1. Đảm bảo network `shared_datanet` được tạo với driver `overlay` (cho Docker Swarm) hoặc expose port 9200.

2. Cấu hình `dangbaitudong` gửi log trực tiếp tới Elasticsearch:

```python
# Trong code Python (alternative - không dùng Filebeat)
from elasticsearch import Elasticsearch

es = Elasticsearch(["http://<ES_HOST>:9200"])
es.index(index="app-logs-2024.01.15", body=log_payload)
```

3. Hoặc chạy Filebeat riêng trên máy dangbaitudong:

```bash
# Sửa filebeat.yml output.elasticsearch.hosts
output.elasticsearch:
  hosts: ["<ES_HOST>:9200"]
```

## Troubleshooting

### Filebeat không gửi log

1. Kiểm tra log của Filebeat:
```bash
docker logs filebeat
```

2. Kiểm tra file log có được tạo:
```bash
ls -la ./logs/
cat ./logs/app.log
```

3. Kiểm tra kết nối Elasticsearch:
```bash
curl http://localhost:9200/_cat/indices
```

### Grafana không hiển thị data

1. Kiểm tra data source đã được cấu hình:
   - Settings → Data Sources → Elasticsearch-Logs

2. Kiểm tra index pattern:
   - Phải match với `app-logs-*`

3. Kiểm tra time range trong dashboard

### Log không có trace.id

- Đảm bảo middleware `CorrelationIdMiddleware` được thêm vào app
- Kiểm tra header `X-Request-ID` hoặc `X-Correlation-ID` có được truyền
