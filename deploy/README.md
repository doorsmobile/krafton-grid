# EC2 배포 (Ubuntu 24.04+/26.04)

```
GitHub (doorsmobile/krafton-grid · main)
        │ git pull
        ▼
/opt/krafton-grid ── krafton-grid-collector (systemd) ──▶ Redis 127.0.0.1:6379 ◀── krafton-grid-web (systemd, 127.0.0.1:8003) ◀── nginx :80 → :443 (Let's Encrypt)
```

| 작업 | 명령 (서버에서) |
|---|---|
| 최초 설치 | `sudo git clone https://github.com/doorsmobile/krafton-grid.git /opt/krafton-grid && sudo bash /opt/krafton-grid/deploy/setup_ec2.sh` |
| 업데이트 (main 최신으로) | `sudo bash /opt/krafton-grid/deploy/setup_ec2.sh` |
| 상태 | `systemctl status krafton-grid-collector krafton-grid-web` · `curl -s localhost/healthz` |
| 로그 | `journalctl -u krafton-grid-collector -u krafton-grid-web -f` |
| 로그인 비밀번호 확인 | `sudo grep ^AUTH_PASSWORD /etc/krafton-grid/grid.env` |
| 설정 변경 | `sudo nano /etc/krafton-grid/grid.env` → `sudo systemctl restart krafton-grid-collector krafton-grid-web` |
| HTTPS (도메인 연결 후) | `/etc/krafton-grid/grid.env`에 `DOMAIN` · `DOMAIN_ALIASES` · `LETSENCRYPT_EMAIL` · `LETSENCRYPT_AGREE_TOS=yes` 추가 → `sudo bash /opt/krafton-grid/deploy/setup_ec2.sh` (인증서 발급 · nginx HTTPS 전환 · 자동 갱신) |
| 인증서 갱신 확인 | `systemctl list-timers certbot.timer` · `sudo certbot renew --dry-run` |

- 보안 그룹: 22(내 IP), 80/443(전체). 인증서 발급 후 80은 **인증서 갱신 확인용으로만** 응답하고 나머지는 연결을 끊습니다(HTTP 사이트 없음). IP로 접속하면 TLS 단계에서 거부됩니다. 8003·6379는 열지 않음 — 둘 다 127.0.0.1에만 바인딩됨.
- Redis는 read-model 캐시(영속화 끔, 2 GB 한도). 수집기가 시작할 때 전부 다시 발행합니다.
- 예산 결재 데이터만 `/var/lib/krafton-grid/budget.json`에 남습니다.
