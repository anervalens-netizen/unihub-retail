from __future__ import annotations

from services.grile_sheets import close_services


class Closable:
    def __init__(self) -> None:
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


class Resource:
    def __init__(self, transport: Closable) -> None:
        self._http = transport


def test_close_services_closes_direct_resources_and_shared_transports_once() -> None:
    direct = Closable()
    transport = Closable()

    close_services(direct, Resource(transport), Resource(transport), None)

    assert direct.close_count == 1
    assert transport.close_count == 1
