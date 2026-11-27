# Nginx service incident runbook

## Symptoms

- The `nginx_up` metric is `0`.
- The Nginx service is stopped, or the exporter cannot scrape the status endpoint.
- The website may return a connection error or an HTTP 502/503 response.

## Investigation

1. Check the service: `sudo systemctl status nginx --no-pager`.
2. Review recent logs: `sudo journalctl -u nginx -n 50 --no-pager`.
3. Validate configuration: `sudo nginx -t`.
4. Check the local endpoint: `curl -I http://127.0.0.1/`.

## Safe recovery

- If Nginx is stopped and configuration validation passes, start it with `sudo systemctl start nginx`.
- Do not repeatedly restart Nginx when `nginx -t` fails. Correct or roll back the invalid configuration first.
- Verify `systemctl is-active nginx` and confirm `nginx_up` returns to `1`.

## Rollback

If Nginx does not start, inspect `/var/log/nginx/error.log` and restore the last known-good configuration.
