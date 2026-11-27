import os

def run_command(host: str, user: str, command: str) -> str:
    import paramiko

    key_path = os.getenv("SSH_KEY_PATH", "/opt/aiops/.ssh/id_ed25519")
    client = paramiko.SSHClient()
    client.load_system_host_keys()

    try:
        client.connect(
            hostname=host,
            username=user,
            key_filename=key_path,
            timeout=10,
            banner_timeout=10,
            auth_timeout=10,
            allow_agent=False,
            look_for_keys=False,
        )
        _, stdout, stderr = client.exec_command(command, timeout=20)
        exit_code = stdout.channel.recv_exit_status()
        output = stdout.read().decode("utf-8", errors="replace").strip()
        error = stderr.read().decode("utf-8", errors="replace").strip()

        if exit_code:
            raise RuntimeError(error or f"Remote command exited with status {exit_code}")
        return output
    finally:
        client.close()
