#!/bin/bash

# Initialize Redis (Single Instance)
echo "Initializing Redis..."

# Wait for Redis to be ready
echo "Waiting for Redis to start..."
sleep 5

# Check if Redis is ready
if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
    echo "Redis is ready and responding"
    
    # Verify Redis info
    echo "Redis info:"
    docker compose exec -T redis redis-cli info server | head -10
    
    echo "Redis setup complete"
    exit 0
else
    echo "Failed to connect to Redis"
    exit 1
fi
