#!/bin/bash

# Generate self-signed SSL certificates for development
# For production, replace with proper SSL certificates

mkdir -p /etc/nginx/ssl

# Generate private key
openssl genrsa -out /etc/nginx/ssl/nginx.key 2048

# Generate certificate signing request
openssl req -new -key /etc/nginx/ssl/nginx.key -out /etc/nginx/ssl/nginx.csr -subj "/C=US/ST=CA/L=San Francisco/O=Voice Assistant/CN=localhost"

# Generate self-signed certificate
openssl x509 -req -days 365 -in /etc/nginx/ssl/nginx.csr -signkey /etc/nginx/ssl/nginx.key -out /etc/nginx/ssl/nginx.crt

# Set proper permissions
chmod 600 /etc/nginx/ssl/nginx.key
chmod 644 /etc/nginx/ssl/nginx.crt

echo "SSL certificates generated successfully"
