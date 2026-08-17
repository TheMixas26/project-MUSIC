import socket
from zeroconf import ServiceInfo, Zeroconf

_zeroconf = None

def get_local_ip():
    """Определяем IP машины в LAN."""

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        s.connect(("192.168.0.1", 80))
        return s.getsockname()[0]
    finally:
        s.close()

def register_mdns(port=8000, service_name="musicplayer"):
    """
    Анонсирует сервер как <service_name>._musicplayer._tcp.local.
    ESP32 сможет найти его через mDNS-запрос типа сервиса "_musicplayer".
    """
    global _zeroconf

    ip = get_local_ip()
    info = ServiceInfo(
        "_musicplayer._tcp.local.",
        f"{service_name}._musicplayer._tcp.local.",
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties={},
        server=f"{service_name}.local.",
    )

    _zeroconf = Zeroconf()
    _zeroconf.register_service(info)
    print(f"[mDNS] Анонсирован как {service_name}.local ({ip}:{port})")


def unregister_mdns():
    if _zeroconf:
        _zeroconf.close()
