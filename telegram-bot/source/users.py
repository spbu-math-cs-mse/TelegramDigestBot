import aiohttp

class UserService:
    async def init(self, host, port):
        self.session = aiohttp.ClientSession()
        self.url = f'http://{host}:{port}'
        return self

    async def _ok(self, method, request, data):
        request = await self.session.request(method, self.url + "/" + request, json=data, headers={
            'Content-Type': 'application/json'
        })
        response = dict(await request.json())
        return response.get('ok', None)

    async def register_user(self, login, name) -> bool:
        return await self._ok("POST", "register", data={
            "login": login,
            "name": name
        }) is not None

    async def delete_user(self, user) -> bool:
        return await self._ok("DELETE", "drop", data={
            "login": user
        }) is not None
    
    async def get_limit(self, login) -> int | None:
        return await self._ok("GET", "limit", data={
            "login": login,
        })

    async def set_limit(self, login, limit) -> bool:
        return await self._ok("PUT", "limit", data={
            "login": login,
            "limit": limit
        }) is not None
    
    async def get_period(self, login) -> int | None:
        return await self._ok("GET", "period", data={
            "login": login,
        })

    async def set_period(self, login, period) -> bool:
        return await self._ok("PUT", "period", data={
            "login": login,
            "period": period
        }) is not None

    async def subscribe(self, login, channel = None, feed = None) -> bool:
        if channel is not None:
            return await self._ok("PUT", "subscribe", data={
                "login": login,
                "channel": channel
            }) is not None
        return await self._ok("PUT", "subscribe", data={
            "login": login,
            "feed": feed
        }) is not None
    
    async def unsubscribe(self, login, channel = None, feed = None) -> bool:
        if channel is not None:
            return await self._ok("PUT", "unsubscribe", data={
                "login": login,
                "channel": channel
            }) is not None
        return await self._ok("PUT", "unsubscribe", data={
            "login": login,
            "feed": feed
        }) is not None
    
    async def check_user(self, login) -> bool:
        return await self._ok("GET", "user", data={
            "login": login,
        }) is not None
    
    async def channels(self, user) -> list[str] | None:
        return await self._ok("GET", "/channels", data={
            "login": user
        })
    
    async def feeds(self, user) -> list[str] | None:
        return await self._ok("GET", "/feeds", data={
            "login": user
        })
