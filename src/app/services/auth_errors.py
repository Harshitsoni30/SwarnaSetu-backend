class AuthError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class DeliveryError(Exception):
    def __init__(self, channel: str) -> None:
        super().__init__(channel)
        self.channel = channel
