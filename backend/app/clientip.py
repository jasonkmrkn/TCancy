import ipaddress

from fastapi import Request

from app import config

IPV6_PREFIX = 64


def _parse(text: str):
    """An IP address from an X-Forwarded-For entry (which may carry a port), or None."""
    text = text.strip()
    if text.startswith("["):  # [v6]:port
        text = text[1 : text.find("]")] if "]" in text else ""
    elif text.count(":") == 1:  # v4:port
        text = text.split(":", 1)[0]
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        return None


def _trusted(ip, proxies) -> bool:
    return any(ip in net for net in proxies if net.version == ip.version)


def _key(ip) -> str:
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.version == 6:
        return str(ipaddress.ip_network((ip, IPV6_PREFIX), strict=False))
    return str(ip)


def client_ip(request: Request, proxies=None) -> str:
    """The key to count this client under: an IPv4 address, or an IPv6 /64 such as 2001:db8::/64."""
    proxies = config.TRUSTED_PROXIES if proxies is None else proxies
    peer = request.client.host if request.client else ""
    peer_ip = _parse(peer)
    if peer_ip is None:
        return peer or "unknown"  
    if not _trusted(peer_ip, proxies):
        return _key(peer_ip)

    header = ",".join(request.headers.getlist("x-forwarded-for"))
    for entry in reversed(header.split(",")):
        ip = _parse(entry)
        if ip is None:
            break  
        if not _trusted(ip, proxies):
            return _key(ip)
    return _key(peer_ip) 