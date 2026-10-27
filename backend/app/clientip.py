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


def _resolve(request: Request, proxies):
    """The client as an address object, or the peer text when that is not an address."""
    proxies = config.TRUSTED_PROXIES if proxies is None else proxies
    peer = request.client.host if request.client else ""
    peer_ip = _parse(peer)
    if peer_ip is None:
        return peer or "unknown"  # not an address (the test client, a unix socket): use it as is
    if not _trusted(peer_ip, proxies):
        return peer_ip

    header = ",".join(request.headers.getlist("x-forwarded-for"))
    for entry in reversed(header.split(",")):
        ip = _parse(entry)
        if ip is None:
            break  # junk where a proxy's address should be: believe nothing further left
        if not _trusted(ip, proxies):
            return ip
    return peer_ip  # no client address in the header: the proxy itself is all we know


def client_ip(request: Request, proxies=None) -> str:
    """The key to count this client under: an IPv4 address, or an IPv6 /64 such as 2001:db8::/64."""
    found = _resolve(request, proxies)
    return found if isinstance(found, str) else _key(found)


def client_address(request: Request, proxies=None) -> str:
    """The client's exact address (IPv6 in full), found by the same rules as client_ip."""
    found = _resolve(request, proxies)
    if isinstance(found, str):
        return found
    if found.version == 6 and found.ipv4_mapped is not None:
        found = found.ipv4_mapped
    return str(found)