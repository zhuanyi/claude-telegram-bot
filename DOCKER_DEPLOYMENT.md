# Docker Deployment Guide for Linux

This guide covers deploying the Claude Telegram Bot to any Linux environment using Docker.

## Prerequisites

1. **Linux server** with Docker installed
2. **Docker Compose** (optional, but recommended)
3. **Git** for cloning the repository

## Method 1: Direct Docker Commands

### 1.1 Clone Repository
```bash
git clone https://github.com/YOUR_USERNAME/claude-telegram-bot-multiple.git
cd claude-telegram-bot-multiple
```

### 1.2 Create Environment File
```bash
cp .env.example .env
nano .env  # or use vim, gedit, etc.
```

Fill in your actual values:
```bash
TELEGRAM_BOT_TOKEN=your_actual_telegram_token
ANTHROPIC_API_KEY=your_actual_anthropic_key
ALLOWED_USERS=123456789,987654321  # optional
```

### 1.3 Build and Run Container
```bash
# Build the image
docker build -t claude-telegram-bot .

# Run the container
docker run -d \
  --name claude-bot \
  --env-file .env \
  --restart unless-stopped \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/bot_data.db:/app/bot_data.db \
  claude-telegram-bot
```

### 1.4 Manage Container
```bash
# View logs
docker logs -f claude-bot

# Stop container
docker stop claude-bot

# Start container
docker start claude-bot

# Restart container
docker restart claude-bot

# Remove container
docker rm claude-bot

# View running containers
docker ps
```

## Method 2: Docker Compose (Recommended)

### 2.1 Create docker-compose.yml
```bash
cat > docker-compose.yml << EOF
version: '3.8'

services:
  claude-bot:
    build: .
    container_name: claude-telegram-bot
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./logs:/app/logs
      - ./bot_data.db:/app/bot_data.db
    environment:
      - PYTHONUNBUFFERED=1
    healthcheck:
      test: ["CMD", "python", "-c", "import sys; sys.exit(0)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  # Optional: Add a database service
  # postgres:
  #   image: postgres:15-alpine
  #   container_name: claude-bot-db
  #   restart: unless-stopped
  #   environment:
  #     POSTGRES_DB: claude_bot
  #     POSTGRES_USER: bot_user
  #     POSTGRES_PASSWORD: secure_password
  #   volumes:
  #     - postgres_data:/var/lib/postgresql/data
  #   ports:
  #     - "5432:5432"

volumes:
  postgres_data:
EOF
```

### 2.2 Deploy with Docker Compose
```bash
# Build and start
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Restart services
docker-compose restart

# View status
docker-compose ps
```

## Method 3: Pre-built Image from Registry

### 3.1 Build and Push to Registry (Optional)
```bash
# Tag image
docker tag claude-telegram-bot your-registry.com/claude-telegram-bot:latest

# Push to registry
docker push your-registry.com/claude-telegram-bot:latest
```

### 3.2 Deploy from Registry
```bash
# Pull and run
docker run -d \
  --name claude-bot \
  --env-file .env \
  --restart unless-stopped \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/bot_data.db:/app/bot_data.db \
  your-registry.com/claude-telegram-bot:latest
```

## Production Deployment Considerations

### 3.1 Systemd Service (Alternative to Docker restart policies)
```bash
# Create systemd service
sudo tee /etc/systemd/system/claude-bot.service << EOF
[Unit]
Description=Claude Telegram Bot
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=true
WorkingDirectory=/path/to/claude-telegram-bot-multiple
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl enable claude-bot.service
sudo systemctl start claude-bot.service
```

### 3.2 Nginx Reverse Proxy (if adding web interface later)
```nginx
# /etc/nginx/sites-available/claude-bot
server {
    listen 80;
    server_name your-domain.com;

    location /webhook {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 3.3 Log Rotation
```bash
# Create logrotate config
sudo tee /etc/logrotate.d/claude-bot << EOF
/path/to/claude-telegram-bot-multiple/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    postrotate
        docker restart claude-bot
    endscript
}
EOF
```

## Environment-Specific Configurations

### 3.4 Development Environment
```bash
# docker-compose.dev.yml
version: '3.8'
services:
  claude-bot:
    build: .
    volumes:
      - .:/app
      - ./logs:/app/logs
    environment:
      - LOG_LEVEL=DEBUG
      - ENABLE_FILE_LOGGING=true
    command: python -u main.py
```

### 3.5 Production Environment
```bash
# docker-compose.prod.yml
version: '3.8'
services:
  claude-bot:
    build: .
    restart: unless-stopped
    environment:
      - LOG_LEVEL=INFO
      - ENABLE_FILE_LOGGING=true
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
        reservations:
          memory: 256M
          cpus: '0.25'
```

## Monitoring and Maintenance

### 4.1 Health Checks
```bash
# Check container health
docker inspect --format='{{.State.Health.Status}}' claude-bot

# Custom health check script
cat > health_check.sh << EOF
#!/bin/bash
if docker ps | grep -q claude-bot; then
    echo "Bot is running"
    exit 0
else
    echo "Bot is not running"
    exit 1
fi
EOF
chmod +x health_check.sh
```

### 4.2 Backup Strategy
```bash
# Backup script
cat > backup.sh << EOF
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/claude-bot"
mkdir -p $BACKUP_DIR

# Stop bot
docker-compose down

# Backup database and logs
tar -czf "$BACKUP_DIR/claude-bot-backup-$DATE.tar.gz" \
    bot_data.db logs/ .env

# Start bot
docker-compose up -d

echo "Backup completed: claude-bot-backup-$DATE.tar.gz"
EOF
chmod +x backup.sh
```

### 4.3 Update Procedure
```bash
# Update script
cat > update.sh << EOF
#!/bin/bash
echo "Updating Claude Telegram Bot..."

# Pull latest code
git pull origin main

# Rebuild and restart
docker-compose down
docker-compose up -d --build

echo "Update completed"
EOF
chmod +x update.sh
```

## Troubleshooting

### Common Issues:

1. **Permission Issues**:
   ```bash
   sudo chown -R $(id -u):$(id -g) .
   ```

2. **Port Conflicts**: Bot doesn't need exposed ports (not a web server)

3. **Memory Issues**:
   ```bash
   # Check container memory usage
   docker stats claude-bot
   ```

4. **Database Persistence**:
   ```bash
   # Ensure volume is mounted correctly
   docker inspect claude-bot | grep Mounts -A 10
   ```

### Debug Commands:
```bash
# Enter running container
docker exec -it claude-bot /bin/bash

# Check environment variables
docker exec claude-bot env

# View container configuration
docker inspect claude-bot

# Check logs from specific time
docker logs claude-bot --since="2024-01-01T00:00:00"
```

## Advantages of Docker Deployment on Linux

1. **Consistency**: Same environment across dev/staging/production
2. **Isolation**: Container doesn't affect host system
3. **Easy Updates**: Build new image and restart container
4. **Resource Control**: Set memory and CPU limits
5. **Monitoring**: Built-in health checks and logging
6. **Portability**: Move between different Linux servers easily
7. **Rollback**: Keep previous images for quick rollback

The Docker setup provides the same reliable deployment whether you're using Ubuntu, CentOS, Debian, or any other Linux distribution!