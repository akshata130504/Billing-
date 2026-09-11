"""Lightweight local SMTP server for Rooman Billing development and testing.

Listens on 127.0.0.1:1025 and accepts all standard SMTP transactions (HELO, EHLO,
AUTH LOGIN/PLAIN, MAIL FROM, RCPT TO, DATA, RSET, QUIT).
Logs received emails to stdout.
"""
import asyncio
import sys


class LocalSMTPServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 1025):
        self.host = host
        self.port = port

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        writer.write(b"220 127.0.0.1 ESMTP Rooman Local Mail Server Ready\r\n")
        await writer.drain()
        in_data = False
        data_buffer = []

        while True:
            line = await reader.readline()
            if not line:
                break

            if in_data:
                if line == b".\r\n" or line == b".\n":
                    in_data = False
                    raw_message = b"".join(data_buffer).decode("utf-8", errors="replace")
                    print(f"[SMTP Server] Delivered message ({len(raw_message)} bytes)", flush=True)
                    writer.write(b"250 2.0.0 Ok: message queued for delivery\r\n")
                    await writer.drain()
                    data_buffer = []
                else:
                    data_buffer.append(line)
                continue

            cmd_line = line.decode("utf-8", errors="replace").strip()
            upper = cmd_line.upper()

            if upper.startswith("QUIT"):
                writer.write(b"221 2.0.0 Bye\r\n")
                await writer.drain()
                break
            elif upper.startswith("EHLO") or upper.startswith("HELO"):
                writer.write(b"250-127.0.0.1\r\n250-8BITMIME\r\n250-AUTH LOGIN PLAIN\r\n250 OK\r\n")
            elif upper.startswith("AUTH"):
                if "LOGIN" in upper:
                    writer.write(b"334 VXNlcm5hbWU6\r\n")
                    await writer.drain()
                    await reader.readline()
                    writer.write(b"334 UGFzc3dvcmQ6\r\n")
                    await writer.drain()
                    await reader.readline()
                    writer.write(b"235 2.7.0 Authentication successful\r\n")
                else:
                    writer.write(b"235 2.7.0 Authentication successful\r\n")
            elif upper.startswith("MAIL FROM:"):
                writer.write(b"250 2.1.0 Sender ok\r\n")
            elif upper.startswith("RCPT TO:"):
                writer.write(b"250 2.1.5 Recipient ok\r\n")
            elif upper.startswith("DATA"):
                in_data = True
                writer.write(b"354 Start mail input; end with <CRLF>.<CRLF>\r\n")
            elif upper.startswith("RSET") or upper.startswith("NOOP"):
                writer.write(b"250 2.0.0 Ok\r\n")
            else:
                writer.write(b"250 2.0.0 Ok\r\n")
            await writer.drain()

        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def main():
    server_handler = LocalSMTPServer("127.0.0.1", 1025)
    server = await asyncio.start_server(server_handler.handle_client, server_handler.host, server_handler.port)
    print(f"Rooman local SMTP server running on {server_handler.host}:{server_handler.port}...", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("SMTP server stopped.")
