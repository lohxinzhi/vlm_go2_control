"""Block Python network access throughout the Task 3 suite; ROS uses local DDS."""
import socket
import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    attempts = []
    def blocked(*args, **kwargs):
        attempts.append(True)
        raise AssertionError('Network is forbidden in Task 3 tests')
    monkeypatch.setattr(socket.socket, 'connect', blocked)
    monkeypatch.setattr(socket.socket, 'connect_ex', blocked)
    monkeypatch.setattr(socket, 'create_connection', blocked)
    monkeypatch.setattr(socket, 'getaddrinfo', blocked)
    yield
    assert not attempts, 'A Task 3 test attempted real network access'
