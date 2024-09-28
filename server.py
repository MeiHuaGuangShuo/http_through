import asyncio
import base64
import hashlib
import json
import time
import uuid
from collections import deque
from aiohttp import web
from loguru import logger
from rich.pretty import pretty_repr
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor

auth = "http_through_auth"
logs: List[dict] = []
handle_times = deque([], 50)
websockets_list: List[web.WebSocketResponse] = []
response_queue: Dict[str, dict] = {}
INTRODUCE_HTML = """\
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>WebSocket转发工具</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      text-align: center;
      padding: 50px;
    }
    h1 {
      font-size: 28px;
      margin-bottom: 20px;
    }
    p {
      font-size: 18px;
      margin-bottom: 10px;
    }
  </style>
</head>
<body>
  <h1><a href="https://github.com/MeiHuaGuangShuo/php_debug_console">WebSocket转发工具</a></h1>
  <p>转发服务端</p>
</body>
</html>
"""


def get_client_ip(request: web.Request, headers: dict):
    return headers.get("CF-Connecting-IP", request.remote)


def uuid_to_short_hash(uuid_str):
    hash_object = hashlib.sha256(uuid_str.encode())
    hash_hex = hash_object.hexdigest()
    hash_bytes = hash_hex.encode()
    hash_base64 = base64.urlsafe_b64encode(hash_bytes).decode()
    return hash_base64[:7]


async def handle_websocket(request: web.Request):
    global websockets_list
    request_headers = dict(request.headers)
    ticket = request.query.get('auth', '')
    if not request_headers:
        return web.json_response({"success": False, "reason": "Headers does not valid"}, status=400)
    if ("http" in request_headers.get("User-Agent", '') or "Mozilla" in request_headers.get("User-Agent",
                                                                                            '')) and not ticket:
        return web.Response(text=INTRODUCE_HTML, content_type='text/html')
    clientIp = get_client_ip(request, request_headers)
    logger.info(f"Connect Request from {clientIp}")
    if ticket != auth:
        logger.warning(f"{clientIp} Authentication failed. Headers: {dict(request_headers)} Ticket: {ticket}")
        return web.Response(status=400)
    websocket = web.WebSocketResponse()
    await websocket.prepare(request)
    logger.info(f"{clientIp} Connected.")
    if len(websockets_list) > 1:
        logger.warning(f"There are more than one connection. Close the old one.")
        await websockets_list[0].close(code=1008, message=b'Too many connections.')
    websockets_list.append(websocket)
    try:
        async for message in websocket:
            try:
                data = json.loads(str(message.data))
                response_queue[data['id']] = data
            except Exception as err:
                logger.error(
                    f'Invalid Response.\n{err.__class__.__name__}: {err}\nClient: {clientIp}\nMessage:\n>{pretty_repr(message)}')
                await websocket.close(code=1008, message=b'Invalid Response.')
                break
            else:
                logger.info(f"[{data['id']}]{clientIp} <- {data['status']}")
    except Exception as err:
        logger.error(f'{clientIp} -> [bold red]{err.__class__.__name__}[/]: [white bold]{err}[/]')
    websockets_list.remove(websocket)
    logger.info(f"{clientIp} Disconnected.")


def filter_headers(headers: dict):
    disallowed_headers = {
        'Via', 'X-Forwarded-For',
        'X-Forwarded-Host', 'X-Forwarded-Proto',
        'Cache-Control', 'Pragma', 'Expires', 'Upgrade',
        'Transfer-Encoding'
    }
    return {k: v for k, v in headers.items() if k not in disallowed_headers}


async def receive_http_request(request: web.Request):
    if len(websockets_list) == 0:
        return web.Response(status=503)
    path = request.path_qs
    if path.startswith("//"):
        path = path[1:]
    method = request.method
    headers = filter_headers(dict(request.headers))
    clientIp = get_client_ip(request, headers)
    body = await request.read()
    body = base64.b64encode(body).decode()
    request_id = uuid_to_short_hash(str(uuid.uuid1()))
    request_time = time.time()
    data = {
        "id"      : request_id,
        "path"    : path,
        "method"  : method,
        "headers" : headers,
        "body"    : body,
        "clientIp": clientIp
    }
    logger.info(f"[{request_id}]{clientIp} -> {path}")
    await websockets_list[0].send_json(data)
    while time.time() - request_time < 10:
        if request_id in response_queue:
            response = response_queue.pop(request_id)
            body = base64.b64decode(response['body'])
            headers = response['headers']
            status_code = response['status']
            handle_time = time.time() - request_time
            handle_times.append(handle_time)
            logger.info(
                f"{clientIp} <- {status_code} {handle_time:.2f}s "
                f"Avg(last {len(handle_times)}): {sum(handle_times) / len(handle_times):.2f}s"
            )
            return web.Response(body=body, headers=headers, status=status_code)
        await asyncio.sleep(0.1)
    return web.Response(status=504)


@web.middleware
async def handle_all_other_requests(request, handler):
    if request.match_info:
        return await handler(request)
    elif request.path == '/ws':
        return await handle_websocket(request)
    else:
        return await receive_http_request(request)


async def main():
    app = web.Application(middlewares=[handle_all_other_requests])
    app.add_routes([web.get('/ws', handle_websocket)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 31740)
    await site.start()
    logger.info('Server started.')
    await asyncio.gather(*asyncio.all_tasks())


if __name__ == '__main__':
    with ThreadPoolExecutor() as pool:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
