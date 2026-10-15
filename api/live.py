from fastapi import WebSocket


class LiveSensorManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(
        self,
        sensor_id: str,
        websocket: WebSocket,
    ):
        await websocket.accept()

        if sensor_id not in self.connections:
            self.connections[sensor_id] = []

        self.connections[sensor_id].append(websocket)

    def disconnect(
        self,
        sensor_id: str,
        websocket: WebSocket,
    ):
        connections = self.connections.get(sensor_id, [])

        if websocket in connections:
            connections.remove(websocket)

        if not connections and sensor_id in self.connections:
            del self.connections[sensor_id]

    async def broadcast(
        self,
        sensor_id: str,
        data: dict,
    ):
        connections = list(
            self.connections.get(sensor_id, [])
        )

        dead_connections = []

        for websocket in connections:
            try:
                await websocket.send_json(data)
            except Exception:
                dead_connections.append(websocket)

        for websocket in dead_connections:
            self.disconnect(sensor_id, websocket)


live_manager = LiveSensorManager()
