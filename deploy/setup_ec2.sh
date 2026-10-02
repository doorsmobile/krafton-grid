#!/usr/bin/env bash
# Krafton Grid (grid-claude) · install or update on Ubuntu (EC2). Idempotent — re-run to deploy the latest main.
#
#   first install :  sudo git clone https://github.com/doorsmobile/krafton-grid.git /opt/krafton-grid \
#                    && sudo bash /opt/krafton-grid/deploy/setup_ec2.sh
#   update        :  sudo bash /opt/krafton-grid/deploy/setup_ec2.sh
#
#   data path     :  collector (systemd) ──▶ Redis 127.0.0.1:6379 ──▶ web (systemd, 127.0.0.1:8003) ──▶ nginx :80/:443
#
#   HTTPS         :  in /etc/krafton-grid/grid.env set
#                      DOMAIN=krafton-grid.com            DOMAIN_ALIASES=www.krafton-grid.com
#                      LETSENCRYPT_EMAIL=you@example.com   LETSENCRYPT_AGREE_TOS=yes   (you accept the Let's Encrypt terms)
#                    then re-run this script: it obtains the certificate (webroot), switches nginx to HTTPS only
#                    (port 80 keeps answering renewal challenges and drops everything else; access by IP is refused),
#                    sets PUBLIC_URL=https://DOMAIN and leaves renewal to certbot's timer.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/doorsmobile/krafton-grid.git}"
BRANCH="${BRANCH:-main}"
APP_DIR=/opt/krafton-grid
DATA_DIR=/var/lib/krafton-grid
ETC_DIR=/etc/krafton-grid
ENV_FILE=$ETC_DIR/grid.env
APP_USER=grid

say() { printf '\033[1;36m[krafton-grid]\033[0m %s\n' "$*"; }
[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
public_ip="$(curl -s -m 2 http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)"
if [[ -z $public_ip ]]; then   # IMDSv2
  tok="$(curl -s -m 2 -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' 2>/dev/null || true)"
  public_ip="$(curl -s -m 2 -H "X-aws-ec2-metadata-token: $tok" http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)"
fi

say "1/8 packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git python3 python3-venv python3-dev build-essential redis-server nginx curl openssl >/dev/null

say "2/8 service user and directories"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$APP_USER"
install -d -o "$APP_USER" -g "$APP_USER" -m 750 "$DATA_DIR"
install -d -o root -g "$APP_USER" -m 750 "$ETC_DIR"

say "3/8 code from $REPO_URL ($BRANCH)"
if [[ -d $APP_DIR/.git ]]; then
  chown -R "$APP_USER:$APP_USER" "$APP_DIR"
  sudo -u "$APP_USER" git -C "$APP_DIR" fetch -q origin "$BRANCH"
  sudo -u "$APP_USER" git -C "$APP_DIR" checkout -q "$BRANCH"
  sudo -u "$APP_USER" git -C "$APP_DIR" merge -q --ff-only "origin/$BRANCH"
else
  git clone -q --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
  chown -R "$APP_USER:$APP_USER" "$APP_DIR"
fi
say "    at $(sudo -u "$APP_USER" git -C "$APP_DIR" log --oneline -1)"

say "4/8 python environment"
[[ -x $APP_DIR/.venv/bin/python ]] || sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q --disable-pip-version-check --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q --disable-pip-version-check -r "$APP_DIR/requirements.txt"

say "5/8 environment file ($ENV_FILE)"
if [[ ! -f $ENV_FILE ]]; then
  gen() { openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c "$1"; }
  cat >"$ENV_FILE" <<EOF
# Krafton Grid (grid-claude) — read by krafton-grid-collector and krafton-grid-web
APP_HOST=127.0.0.1
APP_PORT=8003
PUBLIC_URL=http://${public_ip:-127.0.0.1}
GRID_STORE=redis
REDIS_URL=redis://127.0.0.1:6379/0
GRID_DATA_DIR=$DATA_DIR

# login (public host — keep enabled). Change AUTH_PASSWORD, then: sudo systemctl restart krafton-grid-web
AUTH_ENABLED=1
AUTH_USERNAME=krafton
AUTH_PASSWORD=$(gen 16)
SESSION_SECRET=$(gen 48)

# HTTPS (see the header of deploy/setup_ec2.sh)
# DOMAIN=krafton-grid.com
# DOMAIN_ALIASES=www.krafton-grid.com
# LETSENCRYPT_EMAIL=
# LETSENCRYPT_AGREE_TOS=yes

# optional
# ANTHROPIC_API_KEY=            # Claude in Mission Control (otherwise the built-in analyst answers)
# ALERTS_LIVE_DELIVERY=1        # really send Slack / webhook notifications
# SLACK_WEBHOOK_URL=
EOF
  say "    created with a generated login password (not printed)"
else
  say "    kept existing file"
fi
chown root:"$APP_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"

say "6/8 redis (read-model store: local only, no persistence — the collector republishes on start)"
cat >/etc/redis/krafton-grid.conf <<'EOF'
bind 127.0.0.1 -::1
protected-mode yes
maxmemory 2gb
maxmemory-policy noeviction
save ""
appendonly no
EOF
grep -q '^include /etc/redis/krafton-grid.conf' /etc/redis/redis.conf || echo 'include /etc/redis/krafton-grid.conf' >>/etc/redis/redis.conf
systemctl enable -q redis-server
systemctl restart redis-server

say "7/8 systemd services"
install -m 644 "$APP_DIR/deploy/systemd/krafton-grid-collector.service" /etc/systemd/system/
install -m 644 "$APP_DIR/deploy/systemd/krafton-grid-web.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable -q krafton-grid-collector krafton-grid-web
systemctl restart krafton-grid-collector
systemctl restart krafton-grid-web

say "8/8 nginx"
envval() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"' || true; }
DOMAIN="$(envval DOMAIN)"; ALIASES="$(envval DOMAIN_ALIASES)"
LE_EMAIL="$(envval LETSENCRYPT_EMAIL)"; LE_TOS="$(envval LETSENCRYPT_AGREE_TOS)"
install -d -m 755 /var/www/certbot
site=/etc/nginx/sites-available/krafton-grid
use_http() { install -m 644 "$APP_DIR/deploy/nginx/krafton-grid.conf" "$site"; }
use_https() {   # HTTPS only: :80 answers renewal challenges and drops everything else; IP / unknown names are refused
  local src="$APP_DIR/deploy/nginx/krafton-grid-https.conf"
  if [[ -z ${ALIASES//[ ,]/} ]]; then sed '/# BEGIN ALIASES/,/# END ALIASES/d' "$src"; else cat "$src"; fi \
    | sed -e "s/__DOMAIN__/$DOMAIN/g" -e "s/__ALIASES__/${ALIASES//,/ }/g" >"$site"
  chmod 644 "$site"
}
apply_nginx() { ln -sf "$site" /etc/nginx/sites-enabled/krafton-grid; rm -f /etc/nginx/sites-enabled/default; nginx -t -q; systemctl enable -q nginx; systemctl reload nginx || systemctl restart nginx; }

if [[ -z $DOMAIN ]]; then
  use_http; apply_nginx
  say "    HTTP only (set DOMAIN in $ENV_FILE for HTTPS)"
else
  cert=/etc/letsencrypt/live/$DOMAIN/fullchain.pem
  if [[ ! -f $cert ]]; then
    use_http; apply_nginx                                 # serves /.well-known/acme-challenge/ on :80
    if [[ $LE_TOS != "yes" ]]; then
      say "    DOMAIN=$DOMAIN but LETSENCRYPT_AGREE_TOS is not 'yes' — staying on HTTP"
    else
      apt-get install -y -qq certbot >/dev/null
      names=(-d "$DOMAIN")
      for a in ${ALIASES//,/ }; do
        if getent ahostsv4 "$a" | grep -q "${public_ip:-^}"; then names+=(-d "$a"); else say "    skipping $a (DNS does not point here yet)"; fi
      done
      if ! getent ahostsv4 "$DOMAIN" | grep -q "${public_ip:-^}"; then
        say "    WARNING: $DOMAIN does not resolve to ${public_ip:-this host} yet — certificate request will likely fail"
      fi
      mail=(--register-unsafely-without-email); [[ -n $LE_EMAIL ]] && mail=(-m "$LE_EMAIL" --no-eff-email)
      say "    requesting certificate for ${names[*]//-d /}"
      certbot certonly --webroot -w /var/www/certbot "${names[@]}" --non-interactive --agree-tos "${mail[@]}" \
        --deploy-hook "systemctl reload nginx" || say "    certificate request failed — staying on HTTP (see /var/log/letsencrypt/letsencrypt.log)"
    fi
  fi
  if [[ -f $cert ]]; then
    use_https; apply_nginx
    if [[ "$(envval PUBLIC_URL)" != "https://$DOMAIN" ]]; then
      sed -i "s#^PUBLIC_URL=.*#PUBLIC_URL=https://$DOMAIN#" "$ENV_FILE"
      grep -q '^PUBLIC_URL=' "$ENV_FILE" || echo "PUBLIC_URL=https://$DOMAIN" >>"$ENV_FILE"
      systemctl restart krafton-grid-collector krafton-grid-web     # secure cookies + https links
    fi
    say "    HTTPS on https://$DOMAIN (certificate renews automatically: systemctl list-timers certbot.timer)"
  fi
fi

say "waiting for data to flow …"
for _ in $(seq 1 90); do
  if curl -s http://127.0.0.1:8003/healthz | grep -q '"ok":true'; then
    say "healthy:"; curl -s http://127.0.0.1:8003/healthz; echo
    url="http://${public_ip:-<public-ip>}/"; [[ -n ${DOMAIN:-} && -f /etc/letsencrypt/live/${DOMAIN}/fullchain.pem ]] && url="https://$DOMAIN/"
    say "open $url  (login: krafton · password: sudo grep ^AUTH_PASSWORD $ENV_FILE)"
    exit 0
  fi
  sleep 2
done
say "not healthy yet — check: journalctl -u krafton-grid-collector -u krafton-grid-web -n 80"
curl -s http://127.0.0.1:8003/healthz || true
exit 1
