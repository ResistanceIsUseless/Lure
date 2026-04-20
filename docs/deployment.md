# Deployment guide

## Prerequisites

- A VPS with a public IP (e.g., Hetzner, DigitalOcean, Linode)
- A domain with DNS you control (e.g., Cloudflare)
- Docker and Docker Compose installed
- Ports open: 53 (UDP+TCP), 80, 443, 25, 389, 21, 8443

## DNS delegation

Interactsh needs to be the authoritative DNS server for the OOB domain. This requires NS delegation.

### Step 1: Create the nameserver A record

In your DNS provider (e.g., Cloudflare), create:

```
ns.example.com    A    <YOUR_PUBLIC_IP>
```

### Step 2: Delegate the OOB subdomain

Create an NS record delegating `oob.example.com` to your nameserver:

```
oob.example.com   NS   ns.example.com
```

This means all queries for `*.oob.example.com` will be answered by Interactsh running on your server. No glue records required — `ns.example.com` resolves through the parent zone. Propagation typically takes 5–15 minutes.

### Step 3: Point the content domain

Create a standard A record for the Python vector server:

```
content.example.com   A   <YOUR_PUBLIC_IP>
```

### Verify delegation

```bash
# Should return your server's IP
dig +short ns.example.com

# Should show NS pointing to ns.example.com
dig NS oob.example.com

# After Interactsh is running, should get a response
dig test.oob.example.com @<YOUR_PUBLIC_IP>
```

## Configuration

### Environment variables

```bash
cd vector_server
cp .env.example .env
```

Edit `.env`:

```env
OOB_DOMAIN=oob.example.com
CONTENT_DOMAIN=content.example.com
PUBLIC_IP=203.0.113.50

INTERACTSH_URL=http://127.0.0.1:80
INTERACTSH_TOKEN=<generate-a-strong-random-token>

ADMIN_TOKEN=<generate-a-different-strong-token>
```

Generate tokens:

```bash
openssl rand -hex 32
```

### Caddyfile

If using Cloudflare for DNS-01 TLS challenges (required for wildcard certs on the OOB domain), set the `CF_API_TOKEN` environment variable. The token needs Zone:DNS:Edit permissions for your domain.

```bash
export CF_API_TOKEN=<your-cloudflare-api-token>
export ACME_EMAIL=you@example.com
```

The default `deploy/Caddyfile` routes:
- `content.example.com` → Python vector server (127.0.0.1:8443)
- `*.oob.example.com` → Interactsh HTTP (127.0.0.1:80)

## Docker deployment

```bash
cd deploy

# Set required environment variables
export PUBLIC_IP=203.0.113.50
export OOB_DOMAIN=oob.example.com
export CONTENT_DOMAIN=content.example.com
export INTERACTSH_TOKEN=$(openssl rand -hex 32)

docker compose up -d
```

### Services

| Service | Image | Network | Purpose |
|---------|-------|---------|---------|
| `interactsh` | `projectdiscovery/interactsh-server:latest` | host | OOB callback capture (DNS/HTTP/SMTP/LDAP/FTP) |
| `vector-server` | Built from `vector_server/Dockerfile` | bridge (port 8443) | Vector content generation + admin UI |
| `caddy` | `caddy:2-alpine` | host | TLS termination + reverse proxy |

### Interactsh flags

Key flags passed to `interactsh-server`:

| Flag | Purpose |
|------|---------|
| `-domain` | OOB domain for callback capture |
| `-ip` | Public IP for DNS responses |
| `-listen-ip 0.0.0.0` | Bind to all interfaces |
| `-auth -token` | Require token for `/events` polling |
| `-skip-acme` | Let Caddy handle TLS instead |
| `-responder` | Enable all protocol responders |
| `-http-index ""` | Disable default HTTP landing page |

## TLS configuration

### Option A: Caddy with Cloudflare DNS (recommended)

Caddy handles TLS for both domains. Wildcard certs for `*.oob.example.com` require DNS-01 challenges, which the Cloudflare DNS plugin handles automatically.

```
*.oob.example.com {
    tls {
        dns cloudflare {$CF_API_TOKEN}
    }
    reverse_proxy 127.0.0.1:80
}
```

### Option B: Interactsh self-ACME

Interactsh can solve DNS-01 challenges itself (it's the authoritative DNS server for the OOB domain). Remove `-skip-acme` and provide cert paths:

```bash
interactsh-server \
  -domain oob.example.com \
  -cert /etc/ssl/oob.example.com.crt \
  -key /etc/ssl/oob.example.com.key
```

In this case, Caddy only handles `content.example.com`.

## Verification

After deployment:

```bash
# 1. Health check
curl https://content.example.com/health

# 2. Admin UI (use your admin token)
open "https://content.example.com/admin/ui?token=YOUR_ADMIN_TOKEN"

# 3. DNS callback test
dig test123.oob.example.com

# 4. HTTP callback test
curl -s https://test123.oob.example.com/

# 5. Download a POC bundle
curl -O https://content.example.com/bundle/10-settings-hook.zip

# 6. Check admin for callback events
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  https://content.example.com/admin/events
```

## Production hardening

### Firewall

```bash
# Allow required ports
ufw allow 53/udp
ufw allow 53/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 25/tcp    # SMTP callbacks
ufw allow 389/tcp   # LDAP callbacks
ufw allow 21/tcp    # FTP callbacks

# Restrict admin access to your IP
ufw allow from <YOUR_IP> to any port 8443
```

### Admin access control

The admin routes (`/admin/*`) require a bearer token. For additional security:

1. IP-allowlist the admin endpoints in Caddy or your firewall
2. Use a strong, randomly generated `ADMIN_TOKEN`
3. Access the admin UI only over HTTPS

### Resource limits

Add to `docker-compose.yml` for each service:

```yaml
deploy:
  resources:
    limits:
      memory: 512M
      cpus: '1.0'
```

### Log rotation

Docker logs grow unbounded by default:

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

### Monitoring

- `/health` returns `{"status": "ok", "stats": {...}}` with token/callback counts
- Admin SSE stream at `/admin/stream` for real-time callback monitoring
- Poll `/admin/stats` for aggregate metrics

## Architecture: arm64 (Apple Silicon) dev → amd64 deploy

If developing on Apple Silicon and deploying to amd64:

```bash
# Build for amd64
docker buildx build --platform=linux/amd64 -t vector-server ../vector_server

# interactsh-server image is multi-arch (no special handling needed)
```

## Troubleshooting

**No DNS callbacks**: Verify NS delegation with `dig NS oob.example.com`. Ensure port 53 (UDP+TCP) is open and not blocked by the hosting provider.

**Interactsh registration fails**: The Python server retries on first poll. Check that `INTERACTSH_URL` and `INTERACTSH_TOKEN` match between services.

**TLS errors on wildcard domain**: DNS-01 challenges require the Cloudflare API token to have Zone:DNS:Edit permissions. Check Caddy logs: `docker compose logs caddy`.

**Callbacks received but not correlated**: Tokens in callback URLs must match registered tokens. Check `/admin/events` — unmatched callbacks appear without payload metadata.
