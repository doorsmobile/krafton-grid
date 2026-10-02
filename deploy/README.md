# EC2 배포 (Ubuntu 24.04+/26.04)

```
GitHub (doorsmobile/krafton-grid · main)
        │ git pull
        ▼
/opt/krafton-grid ── krafton-grid-collector (systemd) ──▶ Redis 127.0.0.1:6379 ◀── krafton-grid-web (systemd, 127.0.0.1:8003) ◀── nginx :80
```

| 작업 | 명령 (서버에서) |
|---|---|
| 최초 설치 | `sudo git clone https://github.com/doorsmobile/krafton-grid.git /opt/krafton-grid && sudo bash /opt/krafton-grid/deploy/setup_ec2.sh` |
| 업데이트 (main 최신으로) | `sudo bash /opt/krafton-grid/deploy/setup_ec2.sh` |
| 상태 | `systemctl status krafton-grid-collector krafton-grid-web` · `curl -s localhost/healthz` |
| 로그 | `journalctl -u krafton-grid-collector -u krafton-grid-web -f` |
| 로그인 비밀번호 확인 | `sudo grep ^AUTH_PASSWORD /etc/krafton-grid/grid.env` |
| 설정 변경 | `sudo nano /etc/krafton-grid/grid.env` → `sudo systemctl restart krafton-grid-collector krafton-grid-web` |
| HTTPS (도메인 연결 후) | `sudo apt install -y certbot python3-certbot-nginx && sudo certbot --nginx -d <domain>` |

- 보안 그룹: 22(내 IP), 80/443(전체). 8003·6379는 열지 않음 — 둘 다 127.0.0.1에만 바인딩됨.
- Redis는 read-model 캐시(영속화 끔, 2 GB 한도). 수집기가 시작할 때 전부 다시 발행합니다.
- 예산 결재 데이터만 `/var/lib/krafton-grid/budget.json`에 남습니다.
