import aiohttp

class UserService:
    def __init__(self, host, port):
        self.session = aiohttp.ClientSession()
        self.url = f'{host}:{port}'

    async def _ok(self, method, request, data):
        request = await self.session.request(method, self.url + "/" + request, data=data)
        response = dict(await request.json())
        return response.get('ok', default=None)

    async def register_user(self, login, name) -> bool:
        return await self._ok("POST", "register", data={
            "login": login,
            "name": name
        }) is not None

    async def delete_user(self, user) -> bool:
        return await self._ok("DELETE", "drop", data={
            "login": user
        }) is not None

    async def subscribe(self, user, channel) -> bool:
        return await self._ok("PUT", "subscribe", data={
            "user": user,
            "channel": channel
        }) is not None
    
    async def unsubscribe(self, user, channel) -> bool:
        return await self._ok("PUT", "unsubscribe", data={
            "user": user,
            "channel": channel
        }) is not None
    
    async def channels(self, user) -> list[str] | None:
        return await self._ok("GET", "/channels", data={
            "login": user
        })
