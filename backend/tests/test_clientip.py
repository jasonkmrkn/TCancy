import subprocess
import sys
import os
import ipaddress

import pytest
from starlette.requests import Request

from app.clientip import client_ip

NETS = lambda *items: tuple(ipaddress.ip_network(i) for i in items)  # noqa: E731
NEXT = NETS("172.18.0.0/16")


def req(peer, *forwarded):
    headers = [(b"x-forwarded-for", value.encode()) for value in forwarded]
    return Request({"type": "http", "client": (peer, 5000) if peer is not None else None, "headers": headers})


# --- no trusted proxies: headers are ignored ------------------------------------


@pytest.mark.parametrize("header", ["1.2.3.4", "1.2.3.4, 5.6.7.8", "garbage", "", "::1"])
def test_without_trusted_proxies_the_header_changes_nothing(header):
    assert client_ip(req("203.0.113.9", header), ()) == "203.0.113.9"


def test_by_default_nothing_is_trusted():
    assert client_ip(req("172.18.0.2", "1.2.3.4")) == "172.18.0.2"


# --- a trusted proxy in front ---------------------------------------------------


def test_the_client_is_the_rightmost_address_that_is_not_a_proxy():
    assert client_ip(req("172.18.0.2", "198.51.100.7"), NEXT) == "198.51.100.7"


def test_addresses_the_client_wrote_itself_are_never_used():
    # Cloudflare appends the real client; whatever the client put in front is to the left.
    assert client_ip(req("172.18.0.2", "6.6.6.6, 1.1.1.1, 198.51.100.7"), NEXT) == "198.51.100.7"


def test_several_proxies_in_a_row_are_skipped():
    assert client_ip(req("172.18.0.2", "198.51.100.7, 172.18.0.9, 172.18.0.5"), NEXT) == "198.51.100.7"


def test_a_forged_proxy_address_does_not_move_the_answer():
    # Left of the real client, so it is never looked at, however trusted it looks.
    assert client_ip(req("172.18.0.2", "172.18.0.77, 198.51.100.7"), NEXT) == "198.51.100.7"


def test_a_peer_that_is_not_a_trusted_proxy_cannot_set_the_address():
    assert client_ip(req("203.0.113.9", "198.51.100.7"), NEXT) == "203.0.113.9"


def test_without_a_header_the_proxy_itself_is_the_answer():
    assert client_ip(req("172.18.0.2"), NEXT) == "172.18.0.2"


def test_a_header_made_only_of_proxies_gives_the_peer():
    assert client_ip(req("172.18.0.2", "172.18.0.9, 172.18.0.5"), NEXT) == "172.18.0.2"


def test_junk_where_a_client_address_should_be_gives_the_peer():
    assert client_ip(req("172.18.0.2", "198.51.100.7, not-an-ip"), NEXT) == "172.18.0.2"
    assert client_ip(req("172.18.0.2", "198.51.100.7, "), NEXT) == "172.18.0.2"  # empty entry on the right
    assert client_ip(req("172.18.0.2", ""), NEXT) == "172.18.0.2"


def test_a_header_sent_in_several_lines_is_one_list():
    assert client_ip(req("172.18.0.2", "6.6.6.6", "198.51.100.7"), NEXT) == "198.51.100.7"


@pytest.mark.parametrize(
    "entry,expected",
    [("198.51.100.7:4433", "198.51.100.7"), ("  198.51.100.7  ", "198.51.100.7"),
     ("[2001:db8:1:2::9]:443", "2001:db8:1:2::/64"), ("::ffff:198.51.100.7", "198.51.100.7")],
)
def test_ports_spaces_and_mapped_addresses_are_understood(entry, expected):
    assert client_ip(req("172.18.0.2", entry), NEXT) == expected


def test_a_single_address_and_a_range_both_work():
    assert client_ip(req("10.0.0.5", "198.51.100.7"), NETS("10.0.0.5")) == "198.51.100.7"
    assert client_ip(req("10.0.0.6", "198.51.100.7"), NETS("10.0.0.5")) == "10.0.0.6"
    assert client_ip(req("10.9.9.9", "198.51.100.7"), NETS("10.0.0.0/8")) == "198.51.100.7"


def test_ipv6_proxies_and_ipv4_proxies_do_not_mix():
    assert client_ip(req("fd00::2", "198.51.100.7"), NETS("fd00::/8")) == "198.51.100.7"
    assert client_ip(req("fd00::2", "198.51.100.7"), NETS("10.0.0.0/8")) == "fd00::/64"


# --- IPv6 is counted per /64 ----------------------------------------------------


def test_one_ipv6_network_is_one_client():
    a = client_ip(req("2001:db8:1:2:aaaa:bbbb:cccc:dddd"), ())
    b = client_ip(req("2001:db8:1:2:1111:2222:3333:4444"), ())
    c = client_ip(req("2001:db8:1:3::1"), ())
    assert a == b == "2001:db8:1:2::/64"
    assert c == "2001:db8:1:3::/64" != a


def test_ipv4_stays_an_exact_address():
    assert client_ip(req("203.0.113.9"), ()) == "203.0.113.9"
    assert client_ip(req("203.0.113.10"), ()) != client_ip(req("203.0.113.9"), ())


def test_a_mapped_peer_is_the_ipv4_address():
    assert client_ip(req("::ffff:203.0.113.9"), ()) == "203.0.113.9"


# --- peers that are not addresses -----------------------------------------------


def test_a_peer_that_is_not_an_address_is_used_as_it_is():
    assert client_ip(req("testclient", "1.2.3.4"), NETS("10.0.0.0/8")) == "testclient"


def test_no_peer_at_all():
    assert client_ip(req(None), ()) == "unknown"


# --- configuration --------------------------------------------------------------


def load_config(**env):
    done = subprocess.run(
        [sys.executable, "-c", "from app import config; print(config.TRUSTED_PROXIES)"],
        env={**os.environ, **env}, capture_output=True, text=True,
    )
    return done


def test_trusted_proxies_are_read_from_the_environment():
    done = load_config(TRUSTED_PROXIES=" 172.18.0.0/16 , 10.0.0.5,fd00::/8 ")
    assert done.returncode == 0, done.stderr
    assert "172.18.0.0/16" in done.stdout and "10.0.0.5/32" in done.stdout and "fd00::/8" in done.stdout


@pytest.mark.parametrize("value", ["", "  ", ",,"])
def test_empty_means_no_trusted_proxies(value):
    done = load_config(TRUSTED_PROXIES=value)
    assert done.returncode == 0 and done.stdout.strip() == "()"


@pytest.mark.parametrize("value", ["*", "0.0.0.0/0", "::/0", "172.18.0.0/16,*", "not-an-ip", "10.0.0.0/33", "10.0.0.1 10.0.0.2"])
def test_a_trusted_proxies_list_that_trusts_everyone_or_is_broken_stops_the_app(value):
    done = load_config(TRUSTED_PROXIES=value)
    assert done.returncode != 0
    assert "TRUSTED_PROXIES" in done.stderr

# --- client_address: the exact address, found by the same rules ------------------

from app.clientip import client_address  # noqa: E402


def test_the_exact_address_keeps_all_of_an_ipv6_address():
    assert client_address(req("2001:db8:1:2:aaaa:bbbb:cccc:dddd"), ()) == "2001:db8:1:2:aaaa:bbbb:cccc:dddd"
    assert client_ip(req("2001:db8:1:2:aaaa:bbbb:cccc:dddd"), ()) == "2001:db8:1:2::/64"  # the key is unchanged


@pytest.mark.parametrize(
    "peer,header,proxies,expected",
    [
        ("203.0.113.9", None, (), "203.0.113.9"),
        ("203.0.113.9", "1.2.3.4", (), "203.0.113.9"),
        ("::ffff:203.0.113.9", None, (), "203.0.113.9"),
        ("testclient", "1.2.3.4", NETS("10.0.0.0/8"), "testclient"),
        (None, None, (), "unknown"),
        ("172.18.0.2", "6.6.6.6, 1.1.1.1, 198.51.100.7", NEXT, "198.51.100.7"),
        ("172.18.0.2", "198.51.100.7, 172.18.0.9", NEXT, "198.51.100.7"),
        ("172.18.0.2", "198.51.100.7, not-an-ip", NEXT, "172.18.0.2"),
        ("172.18.0.2", "172.18.0.9", NEXT, "172.18.0.2"),
        ("203.0.113.9", "198.51.100.7", NEXT, "203.0.113.9"),
        ("172.18.0.2", "[2001:db8:1:2::9]:443", NEXT, "2001:db8:1:2::9"),
        ("172.18.0.2", "::ffff:198.51.100.7", NEXT, "198.51.100.7"),
        ("172.18.0.2", "198.51.100.7:4433", NEXT, "198.51.100.7"),
    ],
)
def test_the_exact_address_follows_the_same_trust_rules_as_the_key(peer, header, proxies, expected):
    request = req(peer, header) if header is not None else req(peer)
    assert client_address(request, proxies) == expected


def test_the_exact_address_is_the_key_for_everything_but_ipv6():
    for peer in ("203.0.113.9", "::ffff:203.0.113.9", "testclient"):
        assert client_address(req(peer), ()) == client_ip(req(peer), ())


def test_the_exact_address_reads_the_configured_proxies_by_default(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "TRUSTED_PROXIES", NEXT)
    assert client_address(req("172.18.0.2", "198.51.100.7")) == "198.51.100.7"