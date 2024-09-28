import asyncio
import json
from loguru import logger
from urllib.parse import quote_plus
import websockets
import base64
from aiohttp import ClientSession

ws_url = "ws://localhost:31740/ws"  # websocket server url
auth = "http_through_auth"  # authentication token
target_url = "http://localhost:12430"  # http request target url

requestUserAgent = f"HTTP Through (WS) v1.0 (+https://github.com/MeiHuaGuangShuo/http_through)"


def url_combine(url, path_qs):
    if "http" not in url:
        url = "http://" + url
    if "?" in url:
        raise ValueError("url should not contain query string")
    if url.endswith("/"):
        url = url[:-1]
    return url + path_qs


async def main():
    while True:
        uri = '%s?auth=%s' % (ws_url, quote_plus(auth))
        headers = {'User-Agent': requestUserAgent}
        try:
            async with websockets.connect(uri, extra_headers=headers) as websocket:
                logger.info(f"Websocket connected")
                async with ClientSession() as session:
                    try:
                        async for raw_message in websocket:
                            mes = json.loads(raw_message)
                            request_id = mes.get('id')
                            method = mes.get('method')
                            try:
                                async with session.request(
                                        method=method,
                                        url=url_combine(target_url, mes.get('path')),
                                        headers=mes.get('headers'),
                                        data=base64.b64decode(mes.get('body')),
                                        allow_redirects=False
                                ) as response:
                                    await websocket.send(json.dumps({
                                        'id'     : request_id,
                                        'status' : response.status,
                                        'headers': dict(response.headers),
                                        'body'   : base64.b64encode(await response.read()).decode('utf-8'),
                                    }))
                            except Exception as err:
                                logger.error(f"[{request_id}] {err.__class__.__name__}: {err}")
                                await websocket.send(json.dumps({
                                    'id'     : request_id,
                                    'status' : 500,
                                    'headers': {},
                                    'body'   : base64.b64encode(b"Internal Server Error").decode('utf-8'),
                                }))
                    except asyncio.CancelledError:
                        logger.warning(f"Closing the websocket connections...")
                        await websocket.close()
                        break
                    except Exception as err:
                        logger.exception(err)
                        logger.warning(f"The stream connection will be reconnected after 5 seconds")
                        await asyncio.sleep(5)
        except Exception as err:
            logger.exception(err)
            logger.warning(f"The stream connection will be reconnected after 5 seconds")
            await asyncio.sleep(5)

    logger.info(f"Stream connection was stopped.")


if __name__ == '__main__':
    asyncio.run(main())
